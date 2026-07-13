import argparse, json, os
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from transformers import AutoModelForVision2Seq, AutoProcessor
p=argparse.ArgumentParser(); p.add_argument("--scenario", required=True); p.add_argument("--instruction", default="pour water into the cup until the target level"); args=p.parse_args()
root=Path("/home/lijingsu/vla"); out=root/"disturbance_probe_out"; model_path=root/"models"/"openvla-7b"
os.environ.setdefault("HF_HOME", str(root/"cache"/"huggingface")); os.environ.setdefault("TRANSFORMERS_CACHE", str(root/"cache"/"transformers"))
processor=AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True)
model=AutoModelForVision2Seq.from_pretrained(str(model_path), torch_dtype=torch.float16, low_cpu_mem_usage=True, trust_remote_code=True, attn_implementation="sdpa").to("cuda:0")
image=Image.open(out/f"{args.scenario}.png").convert("RGB")
prompt=f"In: What action should the robot take to {args.instruction}?\nOut:"
inputs=processor(prompt, image).to("cuda:0", dtype=torch.float16)
with torch.no_grad():
    action=model.predict_action(**inputs, do_sample=False, unnorm_key="bridge_orig")
row={"scenario": args.scenario, "instruction": args.instruction, "action": np.asarray(action, dtype=float).tolist()}
(out/f"result_{args.scenario}.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
print(json.dumps(row))
