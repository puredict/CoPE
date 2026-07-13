import json
import os
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from transformers import AutoModelForVision2Seq, AutoProcessor

ROOT = Path("/home/lijingsu/vla")
OUT = ROOT / "disturbance_probe_out"
OUT.mkdir(exist_ok=True)
MODEL = ROOT / "models" / "openvla-7b"
DEVICE = "cuda:0"
UNNORM_KEY = "bridge_orig"

os.environ.setdefault("HF_HOME", str(ROOT / "cache" / "huggingface"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(ROOT / "cache" / "transformers"))

def draw_scene(kind: str, path: Path):
    img = Image.new("RGB", (224, 224), (235, 235, 225))
    d = ImageDraw.Draw(img)
    # table
    d.rectangle([0, 155, 224, 224], fill=(185, 165, 130))
    # kettle body/spout on left
    d.ellipse([18, 72, 92, 146], fill=(130, 130, 135), outline=(70, 70, 70), width=3)
    d.rectangle([80, 96, 132, 112], fill=(110, 110, 115), outline=(60, 60, 60))
    d.arc([30, 50, 78, 95], 180, 360, fill=(60, 60, 60), width=4)
    cup_box = [145, 105, 190, 158]
    if kind == "cup_moved":
        cup_box = [170, 117, 215, 170]
    if kind != "cup_removed":
        d.rectangle(cup_box, fill=(245, 245, 255), outline=(40, 80, 180), width=3)
        d.ellipse([cup_box[0], cup_box[1]-8, cup_box[2], cup_box[1]+8], fill=(245,245,255), outline=(40,80,180), width=3)
        # water level marker
        d.rectangle([cup_box[0]+4, cup_box[3]-18, cup_box[2]-4, cup_box[3]-7], fill=(70, 150, 225))
    if kind == "hand_intrusion":
        d.ellipse([130, 70, 205, 125], fill=(226, 177, 132), outline=(125, 85, 55), width=2)
        d.rectangle([118, 82, 160, 112], fill=(226, 177, 132), outline=(125, 85, 55), width=2)
    if kind == "water_high" and kind != "cup_removed":
        d.rectangle([cup_box[0]+4, cup_box[1]+12, cup_box[2]-4, cup_box[3]-7], fill=(70, 150, 225))
    d.text((8, 8), kind, fill=(20, 20, 20))
    img.save(path)

scenarios = ["normal", "hand_intrusion", "cup_moved", "cup_removed", "water_high"]
for s in scenarios:
    draw_scene(s, OUT / f"{s}.png")

print("loading processor/model", flush=True)
processor = AutoProcessor.from_pretrained(str(MODEL), trust_remote_code=True)
model = AutoModelForVision2Seq.from_pretrained(
    str(MODEL),
    torch_dtype=torch.float16,
    low_cpu_mem_usage=True,
    trust_remote_code=True,
    attn_implementation="sdpa",
).to(DEVICE)
model.eval()

instructions = [
    "pour water into the cup until the target level",
    "continue pouring water into the cup",
    "stop pouring and keep the kettle stable",
    "realign the kettle spout to the cup before pouring",
]

rows = []
with torch.no_grad():
    for s in scenarios:
        image = Image.open(OUT / f"{s}.png").convert("RGB")
        for instr in instructions:
            prompt = f"In: What action should the robot take to {instr}?\nOut:"
            inputs = processor(prompt, image).to(DEVICE, dtype=torch.float16)
            action = model.predict_action(**inputs, do_sample=False, unnorm_key=UNNORM_KEY)
            arr = np.asarray(action, dtype=float).round(6).tolist()
            rows.append({"scenario": s, "instruction": instr, "action": arr})
            print(json.dumps(rows[-1]), flush=True)

# Simple pairwise distances for original instruction across scenarios.
base = None
summary = []
for r in rows:
    if r["instruction"] == instructions[0] and r["scenario"] == "normal":
        base = np.asarray(r["action"], dtype=float)
for r in rows:
    if r["instruction"] == instructions[0]:
        a = np.asarray(r["action"], dtype=float)
        summary.append({"scenario": r["scenario"], "l2_from_normal": float(np.linalg.norm(a - base))})

(OUT / "results.json").write_text(json.dumps({"rows": rows, "summary": summary}, indent=2), encoding="utf-8")
print("SUMMARY", json.dumps(summary), flush=True)
print("wrote", OUT / "results.json", flush=True)
