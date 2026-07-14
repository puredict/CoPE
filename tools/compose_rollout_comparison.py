from __future__ import annotations

import argparse
from pathlib import Path

try:
    from tools.video_io import compose_comparison, print_warnings, sidecar_default
except ImportError:  # Allows `python tools/compose_rollout_comparison.py` from repo root.
    from video_io import compose_comparison, print_warnings, sidecar_default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compose side-by-side LIBERO rollout comparison videos.")
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Mode-labeled source, e.g. clean=/path/to/episode_dir or reactive_disturbed=/path/raw.mp4.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sidecar-json", type=Path, default=None)
    parser.add_argument("--align", choices=["policy-step", "disturbance-step"], default="policy-step")
    parser.add_argument("--padding", choices=["freeze-last", "black"], default="freeze-last")
    parser.add_argument("--fps", type=float, default=None, help="Output render FPS. This is not policy frequency.")
    parser.add_argument("--cell-width", type=int, default=None)
    parser.add_argument("--cell-height", type=int, default=None)
    parser.add_argument("--camera", choices=["policy", "observer"], default="policy")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sidecar = compose_comparison(
        inputs=args.input,
        output=args.output,
        sidecar_json=args.sidecar_json or sidecar_default(args.output),
        alignment=args.align,
        padding=args.padding,
        fps=args.fps,
        cell_width=args.cell_width,
        cell_height=args.cell_height,
        camera=args.camera,
    )
    for item in sidecar.get("inputs", []):
        print_warnings(item.get("warnings", []))
    print(sidecar["output_path"])


if __name__ == "__main__":
    main()
