from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path
from types import SimpleNamespace
import imageio, numpy as np

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
    p.add_argument("--dx", type=float, default=0.10)
    p.add_argument("--dy", type=float, default=0.05)
    p.add_argument("--out-dir", default="/home/lijingsu/vla/second_necessity_outputs/intervention")
    p.add_argument("--seed", type=int, default=7)
    return p.parse_args()


def make_cfg(args):
    return SimpleNamespace(model_family="openvla", pretrained_checkpoint=args.checkpoint, load_in_8bit=False, load_in_4bit=False, center_crop=True, unnorm_key=args.task_suite)


def sim_from_env(env): return env.env.sim if hasattr(env, "env") else env.sim

def toks(text): return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t)>1}

def choose_target_joint(env, task_description):
    sim=sim_from_env(env); task_tokens=toks(task_description); cands=[]
    for jid in range(sim.model.njnt):
        name=sim.model.joint_id2name(jid)
        if not name or name.startswith("robot") or name.startswith("gripper"): continue
        if int(sim.model.jnt_type[jid]) != 0: continue
        obj=name.replace("_joint0", "")
        score=len(task_tokens & toks(obj))
        cands.append((score, -jid, name))
    cands.sort(reverse=True)
    return cands[0][2]

def object_phrase_from_joint(joint):
    s=joint.replace("_joint0", "")
    # Remove common LIBERO asset prefixes/suffixes when making a language prompt.
    s=s.replace("akita_", "").replace("_1", "")
    return s.replace("_", " ")

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

def structured_prompt(original_task, joint):
    obj=object_phrase_from_joint(joint)
    # The intervention is intentionally minimal: it does not provide coordinates or hidden state.
    # It only supplies the recovery semantics that a verifier-only policy lacks.
    return f"relocalize the {obj} at its current position, then complete the original task: {original_task}"

def rollout(cfg, model, processor, task_suite, task_id, mode, args, out_dir):
    task=task_suite.get_task(task_id); init_states=task_suite.get_task_init_states(task_id)
    env, task_desc=get_libero_env(task, cfg.model_family, resolution=256)
    resize_size=get_image_resize_size(cfg)
    env.reset(); obs=env.set_init_state(init_states[0])
    target_joint=choose_target_joint(env, task_desc)
    replay=[]; actions=[]; disturbance=None; recovery_state=None; done=False; reward=0.0
    current_task_desc=task_desc
    stopped_by_verifier=False
    for t in range(args.max_steps + args.num_steps_wait):
        if t < args.num_steps_wait:
            obs,reward,done,info=env.step(get_libero_dummy_action(cfg.model_family)); continue
        pt=t-args.num_steps_wait
        if pt == args.disturbance_step:
            disturbance=move_free_joint_xy(env, target_joint, args.dx, args.dy)
            if mode == "verifier_stop":
                stopped_by_verifier=True
                recovery_state={"verifier":"invalid_continuation", "decision":"stop_or_full_replan", "has_selective_recovery_state":False}
                break
            if mode == "structured_reprompt_recovery":
                current_task_desc=structured_prompt(task_desc, target_joint)
                recovery_state={
                    "verifier":"invalid_continuation",
                    "affected_joint": target_joint,
                    "affected_object": object_phrase_from_joint(target_joint),
                    "invalid_state":["affected_object_pose", "grasp_validity"],
                    "decision":"relocalize_affected_object_then_continue",
                    "prompt_after_recovery": current_task_desc,
                    "has_selective_recovery_state": True,
                }
        img=get_libero_image(obs, resize_size); replay.append(img)
        observation={"full_image":img,"state":np.concatenate((obs["robot0_eef_pos"], quat2axisangle(obs["robot0_eef_quat"]), obs["robot0_gripper_qpos"]))}
        action=get_action(cfg, model, observation, current_task_desc, processor=processor)
        raw=action.astype(float).tolist(); action=normalize_gripper_action(action,binarize=True)
        if cfg.model_family == "openvla": action=invert_gripper_action(action)
        obs,reward,done,info=env.step(action.tolist())
        actions.append({"t":pt,"task_prompt":current_task_desc,"raw_action":raw,"env_action":np.asarray(action,dtype=float).tolist(),"reward":float(reward),"done":bool(done)})
        if done: break
    video=out_dir / f"{mode}_task{task_id}_success{bool(done)}.mp4"
    save_video(replay, video)
    env.close()
    return {"mode":mode,"task_id":task_id,"task_description":task_desc,"target_joint":target_joint,"success":bool(done),"stopped_by_verifier":stopped_by_verifier,"final_reward":float(reward),"num_policy_steps":len(actions),"disturbance":disturbance,"recovery_state":recovery_state,"video_path":str(video),"actions":actions}

def main():
    args=parse_args(); set_seed_everywhere(args.seed)
    out_dir=Path(args.out_dir)/time.strftime("%Y_%m_%d-%H_%M_%S"); out_dir.mkdir(parents=True, exist_ok=True)
    cfg=make_cfg(args); model=get_model(cfg)
    if cfg.unnorm_key not in model.norm_stats and f"{cfg.unnorm_key}_no_noops" in model.norm_stats: cfg.unnorm_key=f"{cfg.unnorm_key}_no_noops"
    processor=get_processor(cfg); suite=benchmark.get_benchmark_dict()[args.task_suite]()
    task_ids=[int(x) for x in args.tasks.split(",") if x.strip()]
    modes=["reactive_disturbed", "verifier_stop", "structured_reprompt_recovery"]
    rows=[]; jsonl=out_dir/"episodes.jsonl"
    for tid in task_ids:
        for mode in modes:
            rec=rollout(cfg,model,processor,suite,tid,mode,args,out_dir)
            rows.append(rec); jsonl.open("a",encoding="utf-8").write(json.dumps(rec)+"\n")
            print(mode,"task",tid,"success",rec["success"],"steps",rec["num_policy_steps"],"video",rec["video_path"],flush=True)
    summary={"args":vars(args),"records":rows,"success_by_mode":{m:float(np.mean([r["success"] for r in rows if r["mode"]==m])) for m in modes},"selective_recovery_state_rate":{m:float(np.mean([bool((r.get("recovery_state") or {}).get("has_selective_recovery_state")) for r in rows if r["mode"]==m])) for m in modes},"jsonl_path":str(jsonl)}
    (out_dir/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k!="records"},indent=2),flush=True)
    print("summary",out_dir/"summary.json",flush=True)
if __name__ == "__main__": main()
