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
    p.add_argument("--tasks", default="0,1,3")
    p.add_argument("--max-steps", type=int, default=220)
    p.add_argument("--num-steps-wait", type=int, default=10)
    p.add_argument("--disturbance-step", type=int, default=70)
    p.add_argument("--target-joint", default="auto")
    p.add_argument("--dx", type=float, default=0.10)
    p.add_argument("--dy", type=float, default=0.05)
    p.add_argument("--out-dir", default="/home/lijingsu/vla/baseline_outputs/reset_rollback")
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

def move_free_joint_xy(env, joint_name, dx, dy):
    sim=sim_from_env(env); jid=sim.model.joint_name2id(joint_name); qaddr=int(sim.model.jnt_qposadr[jid])
    before=sim.data.qpos[qaddr:qaddr+7].copy()
    sim.data.qpos[qaddr]+=dx; sim.data.qpos[qaddr+1]+=dy; sim.forward()
    after=sim.data.qpos[qaddr:qaddr+7].copy()
    return {"joint":joint_name,"before_qpos":before.astype(float).tolist(),"after_qpos":after.astype(float).tolist(),"delta_xy":[dx,dy]}

def save_video(images, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    w=imageio.get_writer(path, fps=30)
    for im in images: w.append_data(im)
    w.close()

def policy_step(cfg, model, processor, obs, task_desc, resize_size):
    img=get_libero_image(obs, resize_size)
    observation={"full_image":img,"state":np.concatenate((obs["robot0_eef_pos"], quat2axisangle(obs["robot0_eef_quat"]), obs["robot0_gripper_qpos"]))}
    action=get_action(cfg, model, observation, task_desc, processor=processor)
    raw=action.astype(float).tolist(); action=normalize_gripper_action(action,binarize=True)
    if cfg.model_family == "openvla": action=invert_gripper_action(action)
    return img, raw, np.asarray(action, dtype=float)

def rollout(cfg, model, processor, task_suite, task_id, mode, args, out_dir):
    task=task_suite.get_task(task_id); init_states=task_suite.get_task_init_states(task_id)
    env, task_desc=get_libero_env(task, cfg.model_family, resolution=256)
    resize_size=get_image_resize_size(cfg)
    env.reset(); obs=env.set_init_state(init_states[0])
    target_selection=select_target_joint(env, task_desc, args.target_joint)
    target_joint=target_selection.selected_joint
    if target_joint is None:
        raise ValueError(f"target selection did not produce a joint: {target_selection.reason}")
    replay=[]; actions=[]; disturbance=None; done=False; reward=0.0; recovery=None
    info={}
    saved_state_for_rollback=None
    disturbance_done=False
    policy_t=0
    total_policy_steps=0
    reset_count=0
    rollback_count=0
    warmup_steps=0
    extra_env_steps=0
    initial_stabilized=False
    while total_policy_steps < args.max_steps:
        # Initial stabilization only once at episode start; full_reset does its own stabilization after reset.
        if not initial_stabilized:
            for _ in range(args.num_steps_wait):
                obs,reward,done,info=env.step(get_libero_dummy_action(cfg.model_family))
            warmup_steps += args.num_steps_wait
            initial_stabilized=True
        if (not disturbance_done) and policy_t == args.disturbance_step:
            if mode == "oracle_rollback":
                saved_state_for_rollback=sim_from_env(env).get_state().flatten().copy()
            disturbance=audited_move_free_joint_xy(env, target_joint, args.dx, args.dy)
            obs,refresh=refresh_observation_after_sim_change(env,cfg)
            disturbance["refresh"]=refresh
            extra_env_steps += int(bool(refresh.get("consumed_noop_env_step")))
            disturbance_done=True
            if mode == "full_reset_replan":
                # This is full replanning as full task restart. It can recover success but loses all progress.
                env.reset(); obs=env.set_init_state(init_states[0])
                for _ in range(args.num_steps_wait):
                    obs,reward,done,info=env.step(get_libero_dummy_action(cfg.model_family))
                warmup_steps += args.num_steps_wait
                reset_count += 1
                recovery={
                    "type":"full_reset_replan",
                    "baseline_property":"restart_baseline_not_current_world_recovery",
                    "progress_preserved":False,
                    "extra_wait_steps":args.num_steps_wait,
                    "policy_step_budget_after_reset":"remaining_original_budget_only",
                }
                policy_t = 0
                continue
            if mode == "oracle_rollback":
                sim=sim_from_env(env); sim.set_state_from_flattened(saved_state_for_rollback); sim.forward()
                obs,refresh=refresh_observation_after_sim_change(env,cfg)
                rollback_count += 1
                extra_env_steps += int(bool(refresh.get("consumed_noop_env_step")))
                recovery={
                    "type":"oracle_rollback_to_pre_disturbance_state",
                    "baseline_property":"oracle_upper_bound_state_undo",
                    "progress_preserved":"sim_state_restored_but_external_disturbance_undone",
                    "refresh":refresh,
                }
                continue
        img, raw, action = policy_step(cfg, model, processor, obs, task_desc, resize_size)
        replay.append(img)
        obs,reward,done,info=env.step(action.tolist())
        actions.append({"t":policy_t,"total_policy_step":total_policy_steps,"raw_action":raw,"env_action":action.tolist(),"reward":float(reward),"done":bool(done)})
        total_policy_steps += 1
        if done: break
        policy_t += 1
    episode_status=extract_episode_status(reward,done,info,total_policy_steps,args.max_steps)
    pre_steps=min(total_policy_steps,args.disturbance_step) if disturbance else total_policy_steps
    budget=make_budget_report(
        policy_step_budget=args.max_steps,
        warmup_simulator_steps=warmup_steps,
        policy_inference_steps=total_policy_steps,
        extra_environment_steps=extra_env_steps,
        pre_disturbance_policy_steps=pre_steps,
        reset_count=reset_count,
        rollback_count=rollback_count,
        success=episode_status.success,
    )
    video=out_dir / f"{mode}_task{task_id}_success{episode_status.success}.mp4"
    save_video(replay, video)
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
    out_dir=Path(args.out_dir)/time.strftime("%Y_%m_%d-%H_%M_%S"); out_dir.mkdir(parents=True, exist_ok=True)
    cfg=make_cfg(args); model=get_model(cfg)
    if cfg.unnorm_key not in model.norm_stats and f"{cfg.unnorm_key}_no_noops" in model.norm_stats: cfg.unnorm_key=f"{cfg.unnorm_key}_no_noops"
    processor=get_processor(cfg); suite=benchmark.get_benchmark_dict()[args.task_suite]()
    task_ids=[int(x) for x in args.tasks.split(",") if x.strip()]
    modes=["reactive_disturbed", "full_reset_replan", "oracle_rollback"]
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
if __name__ == "__main__": main()
