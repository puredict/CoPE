from __future__ import annotations

import argparse
from pathlib import Path

try:
    from tools.video_io import annotate_video, print_warnings, sidecar_default
except ImportError:  # Allows `python tools/annotate_rollout_video.py` from repo root.
    from video_io import annotate_video, print_warnings, sidecar_default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate a LIBERO rollout video with episode metadata.")
    parser.add_argument("--episode-dir", type=Path, default=None, help="Directory containing raw.mp4 and sidecar logs.")
    parser.add_argument("--video", type=Path, default=None, help="Input raw mp4. Overrides episode-dir discovery.")
    parser.add_argument("--run-config", type=Path, default=None)
    parser.add_argument("--events", type=Path, default=None)
    parser.add_argument("--actions", type=Path, default=None)
    parser.add_argument("--episode-summary", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sidecar-json", type=Path, default=None)
    parser.add_argument("--fps", type=float, default=None, help="Output render FPS. This is not policy frequency.")
    parser.add_argument("--mode", default=None, help="Override mode label.")
    parser.add_argument("--title", default=None, help="Override panel title.")
    parser.add_argument("--camera", choices=["policy", "observer"], default="policy")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sidecar = annotate_video(
        source=args.episode_dir,
        video=args.video,
        run_config=args.run_config,
        events=args.events,
        actions=args.actions,
        episode_summary=args.episode_summary,
        output=args.output,
        fps=args.fps,
        sidecar_json=args.sidecar_json or sidecar_default(args.output),
        mode=args.mode,
        title=args.title,
        camera=args.camera,
    )
    print_warnings(sidecar.get("warnings", []))
    print(sidecar["output_path"])


if __name__ == "__main__":
    main()
