import json, os, sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, "/home/lijingsu/vla/src/openvla")
sys.path.insert(0, "/home/lijingsu/vla/src/LIBERO")
os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("HF_HOME", "/home/lijingsu/vla/cache/huggingface")
os.environ.setdefault("TRANSFORMERS_CACHE", "/home/lijingsu/vla/cache/transformers")

from libero.libero import benchmark
from experiments.robot.libero.libero_utils import get_libero_env, get_libero_dummy_action, get_libero_image, quat2axisangle
from experiments.robot.openvla_utils import get_processor, get_vla_action
from experiments.robot.robot_utils import normalize_gripper_action, invert_gripper_action
from dataclasses import dataclass
from transformers import AutoModelForVision2Seq, AutoProcessor
import torch

@dataclass
class Cfg:
    pretrained_checkpoint: str = "/home/lijingsu/vla/models/openvla-7b"
    load_in_8bit: bool = False
    load_in_4bit: bool = False
    center_crop: bool = False
    unnorm_key: str = "bridge_orig"

out = Path("/home/lijingsu/vla/smoke_outputs")
out.mkdir(exist_ok=True)

cfg = Cfg()
print("loading model", flush=True)
processor = AutoProcessor.from_pretrained(cfg.pretrained_checkpoint, trust_remote_code=True)
model = AutoModelForVision2Seq.from_pretrained(
    cfg.pretrained_checkpoint,
    attn_implementation="sdpa",
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=True,
    trust_remote_code=True,
).to("cuda:0")
model.eval()
print("model loaded", flush=True)

ts = benchmark.get_benchmark_dict()["libero_10"]()
task = ts.get_task(0)
init_states = ts.get_task_init_states(0)
env, task_description = get_libero_env(task, "openvla", resolution=128)
env.reset()
obs = env.set_init_state(init_states[0])
rows = []
for t in range(10):
    if t < 3:
        action = np.array(get_libero_dummy_action("openvla"), dtype=float)
        phase = "wait"
    else:
        img = get_libero_image(obs, 224)
        Image.fromarray(img).save(out / f"frame_t{t}.png")
        observation = {
            "full_image": img,
            "state": np.concatenate((obs["robot0_eef_pos"], quat2axisangle(obs["robot0_eef_quat"]), obs["robot0_gripper_qpos"])),
        }
        action = get_vla_action(model, processor, cfg.pretrained_checkpoint, observation, task_description, cfg.unnorm_key, center_crop=False)
        action = normalize_gripper_action(action, binarize=True)
        action = invert_gripper_action(action)
        phase = "vla"
    obs, reward, done, info = env.step(action.tolist())
    row = {"t": t, "phase": phase, "reward": float(reward), "done": bool(done), "action": np.asarray(action, dtype=float).round(6).tolist()}
    rows.append(row)
    print(json.dumps(row), flush=True)
    if done:
        break
env.close()
(out / "base_closed_loop_smoke.json").write_text(json.dumps({"task": task_description, "rows": rows}, indent=2), encoding="utf-8")
print("wrote", out / "base_closed_loop_smoke.json", flush=True)
