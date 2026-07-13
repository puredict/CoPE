from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path
from types import SimpleNamespace
import imageio, numpy as np

from libero_experiment_core import (
    extract_episode_status,
    json_safe,
    make_budget_report,
    move_free_joint_xy as audited_move_free_joint_xy,
    refresh_observation_after_sim_change,
    select_target_joint,
)

sys.path.insert(0, "/home/lijingsu/vla/src/openvla")
sys.path.insert(0, "/home/lijingsu/vla/src/LIBERO")
os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from libero.libero import benchmark
from experiments.robot.libero.libero_utils import get_libero_dummy_action, get_libero_env, get_libero_image, quat2axisangle
from experiments.robot.openvla_utils import get_processor
from experiments.robot.robot_utils import get_action, get_image_resize_size, get_model, invert_gripper_action, normalize_gripper_action, set_seed_everywhere


def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument("--checkpoint", default="/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial")
    p.add_argument("--task-suite", default="libero_spatial")
    p.add_argument("--tasks", default="0")
    p.add_argument("--max-steps", type=int, default=220)
    p.add_argument("--num-steps-wait", type=int, default=10)
    p.add_argument("--disturbance-step", type=int, default=70)
    p.add_argument("--target-joint", default="auto")
    p.add_argument("--dx", type=float, default=0.10)
    p.add_argument("--dy", type=float, default=0.05)
    p.add_argument("--out-dir", default="/home/lijingsu/vla/baseline_outputs/stage_backtrack")
    p.add_argument("--seed", type=int, default=7)
    return p.parse_args()


def make_cfg(args):
    return SimpleNamespace(model_family="openvla", pretrained_checkpoint=args.checkpoint, load_in_8bit=False, load_in_4bit=False, center_crop=True, unnorm_key=args.task_suite)

def sim_from_env(env): return env.env.sim if hasattr(env, "env") else env.sim

def toks(text): return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t)>1}

def choose_target_joint(env, task_description):
    selection=select_target_joint(env, task_description, "auto")
    if selection.selected_joint is None:
        raise ValueError(f"target selection did not produce a joint: {selection.reason}")
    return selection.selected_joint

def object_phrase_from_joint(joint):
    s=joint.replace("_joint0", "").replace("akita_", "").replace("_1", "")
    return s.replace("_", " ")

def infer_goal_phrase(task_desc):
    # LIBERO-Spatial tasks here are black bowl -> plate. Keep simple and explicit.
    if "plate" in task_desc.lower():
        return "the plate"
    return "the target location"

def move_free_joint_xy(env, joint_name, dx, dy):
    sim=sim_from_env(env); jid=sim.model.joint_name2id(joint_name); qaddr=int(sim.model.jnt_qposadr[jid])
    before=sim.data.qpos[qaddr:qaddr+7].copy()
    sim.data.qpos[qaddr]+=dx; sim.data.qpos[qaddr+1]+=dy; sim.forward()
    after=sim.data.qpos[qaddr:qaddr+7].copy()
    return {"joint":joint_name,"before_qpos":before.astype(float).tolist(),"after_qpos":after.astype(float).tolist(),"delta_xy":[dx,dy]}

def save_video(images,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    w=imageio.get_writer(path,fps=30)
    for im in images: w.append_data(im)
    w.close()

def policy_step(cfg, model, processor, obs, task_desc, resize_size):
    img=get_libero_image(obs, resize_size)
    observation={"full_image":img,"state":np.concatenate((obs["robot0_eef_pos"], quat2axisangle(obs["robot0_eef_quat"]), obs["robot0_gripper_qpos"]))}
    action=get_action(cfg, model, observation, task_desc, processor=processor)
    raw=action.astype(float).tolist(); action=normalize_gripper_action(action,binarize=True)
    if cfg.model_family=="openvla": action=invert_gripper_action(action)
    return img, raw, np.asarray(action,dtype=float)

def rollout(cfg, model, processor, task_suite, task_id, mode, args, out_dir):
    task=task_suite.get_task(task_id); init_states=task_suite.get_task_init_states(task_id)
    env, task_desc=get_libero_env(task,cfg.model_family,resolution=256)
    resize_size=get_image_resize_size(cfg)
    env.reset(); obs=env.set_init_state(init_states[0])
    for _ in range(args.num_steps_wait): obs,reward,done,info=env.step(get_libero_dummy_action(cfg.model_family))
    target_selection=select_target_joint(env,task_desc,args.target_joint)
    target_joint=target_selection.selected_joint
    if target_joint is None:
        raise ValueError(f"target selection did not produce a joint: {target_selection.reason}")
    obj=object_phrase_from_joint(target_joint); goal=infer_goal_phrase(task_desc)
    current_prompt=task_desc
    replay=[]; actions=[]; disturbance=None; recovery=None; done=False; reward=0.0; info={}
    extra_env_steps=0
    stopped_by_verifier=False
    for pt in range(args.max_steps):
        if pt == args.disturbance_step:
            disturbance=audited_move_free_joint_xy(env,target_joint,args.dx,args.dy)
            obs,refresh=refresh_observation_after_sim_change(env,cfg)
            disturbance["refresh"]=refresh
            extra_env_steps += int(bool(refresh.get("consumed_noop_env_step")))
            if mode == "verifier_stop":
                stopped_by_verifier=True
                recovery={"type":"verifier_stop","decision":"stop_or_full_replan","baseline_property":"programmed_oracle_event_stop"}
                break
            if mode == "stage_backtrack_subgoal":
                # Stage backtracking: return to the affected manipulation stage in the CURRENT world.
                current_prompt=f"pick up the {obj} from its current position and place it on {goal}"
                recovery={"type":"stage_backtrack_subgoal_current_world","affected_object":obj,"new_prompt":current_prompt,"progress_preserved":"unaffected_world_state_preserved_but_current_stage_restarted"}
            if mode == "structured_relocalize_prompt":
                current_prompt=f"relocalize the {obj} at its current position, then complete the original task: {task_desc}"
                recovery={"type":"structured_relocalize_prompt","affected_object":obj,"new_prompt":current_prompt}
        img, raw, action=policy_step(cfg,model,processor,obs,current_prompt,resize_size)
        replay.append(img)
        obs,reward,done,info=env.step(action.tolist())
        actions.append({"t":pt,"task_prompt":current_prompt,"raw_action":raw,"env_action":action.tolist(),"reward":float(reward),"done":bool(done)})
        if done: break
    status_info=dict(info)
    if stopped_by_verifier:
        status_info["stopped_by_verifier"]=True
    episode_status=extract_episode_status(reward,done,status_info,len(actions),args.max_steps)
    pre_steps=min(len(actions),args.disturbance_step) if disturbance else len(actions)
    budget=make_budget_report(
        policy_step_budget=args.max_steps,
        warmup_simulator_steps=args.num_steps_wait,
        policy_inference_steps=len(actions),
        extra_environment_steps=extra_env_steps,
        pre_disturbance_policy_steps=pre_steps,
        reset_count=0,
        rollback_count=0,
        success=episode_status.success,
    )
    video=out_dir/f"{mode}_task{task_id}_success{episode_status.success}.mp4"; save_video(replay,video)
    env.close()
    return {
        "mode":mode,
        "task_id":task_id,
        "task_description":task_desc,
        "target_joint":target_joint,
        "target_selection":json_safe(target_selection),
        "status":episode_status.status,
        "episode_status":json_safe(episode_status),
        "success":episode_status.success,
        "timeout":episode_status.timeout,
        "stopped":episode_status.stopped,
        "stopped_by_verifier":stopped_by_verifier,
        "simulator_error":episode_status.simulator_error,
        "success_source":episode_status.source if episode_status.success else None,
        "final_reward":float(reward),
        "num_policy_steps":len(actions),
        "policy_step_budget":budget.policy_step_budget,
        "warmup_simulator_steps":budget.warmup_simulator_steps,
        "policy_inference_steps":budget.policy_inference_steps,
        "environment_control_steps":budget.environment_control_steps,
        "pre_disturbance_policy_steps":budget.pre_disturbance_policy_steps,
        "recovery_policy_steps":budget.recovery_policy_steps,
        "success_within_original_budget":budget.success_within_original_budget,
        "total_policy_steps_consumed":budget.total_policy_steps_consumed,
        "reset_count":budget.reset_count,
        "rollback_count":budget.rollback_count,
        "budget":json_safe(budget),
        "disturbance":disturbance,
        "recovery":recovery,
        "video_path":str(video),
        "actions":actions,
    }

def main():
    args=parse_args(); set_seed_everywhere(args.seed)
    out_dir=Path(args.out_dir)/time.strftime("%Y_%m_%d-%H_%M_%S"); out_dir.mkdir(parents=True,exist_ok=True)
    cfg=make_cfg(args); model=get_model(cfg)
    if cfg.unnorm_key not in model.norm_stats and f"{cfg.unnorm_key}_no_noops" in model.norm_stats: cfg.unnorm_key=f"{cfg.unnorm_key}_no_noops"
    processor=get_processor(cfg); suite=benchmark.get_benchmark_dict()[args.task_suite]()
    task_ids=[int(x) for x in args.tasks.split(",") if x.strip()]
    modes=["reactive_disturbed","verifier_stop","structured_relocalize_prompt","stage_backtrack_subgoal"]
    rows=[]; jsonl=out_dir/"episodes.jsonl"
    for tid in task_ids:
        for mode in modes:
            rec=rollout(cfg,model,processor,suite,tid,mode,args,out_dir)
            rows.append(rec); jsonl.open("a",encoding="utf-8").write(json.dumps(rec)+"\n")
            print(mode,"task",tid,"success",rec["success"],"steps",rec["num_policy_steps"],"video",rec["video_path"],flush=True)
    summary={"args":vars(args),"records":rows,"success_by_mode":{m:float(np.mean([r["success"] for r in rows if r["mode"]==m])) for m in modes},"jsonl_path":str(jsonl)}
    (out_dir/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k!="records"},indent=2),flush=True)
    print("summary",out_dir/"summary.json",flush=True)
if __name__=="__main__": main()
