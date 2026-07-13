import argparse
import os

import torch
from PIL import Image
from transformers import AutoModelForVision2Seq, AutoProcessor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="openvla/openvla-7b")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--instruction", default="move the end effector forward")
    parser.add_argument("--unnorm-key", default=None)
    parser.add_argument("--image", default=None)
    args = parser.parse_args()

    os.environ.setdefault("HF_HOME", os.path.expanduser("~/vla/cache/huggingface"))
    os.environ.setdefault("TRANSFORMERS_CACHE", os.path.expanduser("~/vla/cache/transformers"))

    processor = AutoProcessor.from_pretrained(
        args.model,
        trust_remote_code=True,
    )
    model = AutoModelForVision2Seq.from_pretrained(
        args.model,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
        attn_implementation="sdpa",
    ).to(args.device)

    if args.image:
        image = Image.open(args.image).convert("RGB")
    else:
        image = Image.new("RGB", (224, 224), color=(128, 128, 128))

    prompt = f"In: What action should the robot take to {args.instruction}?\nOut:"
    inputs = processor(prompt, image).to(args.device, dtype=torch.float16)

    kwargs = {"do_sample": False}
    if args.unnorm_key:
        kwargs["unnorm_key"] = args.unnorm_key
    action = model.predict_action(**inputs, **kwargs)
    print("action:", action)


if __name__ == "__main__":
    main()

