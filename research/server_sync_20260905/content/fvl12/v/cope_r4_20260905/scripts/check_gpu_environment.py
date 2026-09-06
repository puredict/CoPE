"""Environment validation for the ReKep + OmniGibson GPU host.

STATUS:
  --dry-run : locally dry-run validated (no GPU imports, safe on macOS/CPU)
  full mode : NOT EXECUTED -- REMOTE GPU SERVER ONLY, requires remote GPU
              verification

Full mode imports GPU-only packages and queries the driver.  It is guarded so it
can never run by accident on the CPU development machine: it refuses to proceed
on Darwin, and every risky import is inside a try/except that degrades to FAIL
rather than raising.

Usage:
  python scripts/check_gpu_environment.py --dry-run     # anywhere
  python scripts/check_gpu_environment.py               # REMOTE GPU SERVER ONLY
"""

from __future__ import annotations

import argparse
import importlib
import platform
from pathlib import Path as _Path

import sys as _sys
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

# Proposed pins -- see docs/GPU_SETUP.md.  NOT yet confirmed on hardware.
REQUIRED_PY = (3, 10)
MIN_DRIVER = (525, 60)
EXPECT_TORCH = "2.2"
EXPECT_CUDA = "12.1"
EXPECT_GPUS = 8
EXPECT_GPU_NAME = "3090"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    hard: bool = True          # hard failures make the script exit non-zero


def _v(mod: str) -> Optional[str]:
    try:
        m = importlib.import_module(mod)
        return getattr(m, "__version__", "unknown")
    except Exception:
        return None


# --------------------------------------------------------------------------
# checks that are safe anywhere
# --------------------------------------------------------------------------
def check_python() -> Check:
    got = sys.version_info[:2]
    if got == REQUIRED_PY:
        return Check("python", PASS, f"{got[0]}.{got[1]}")
    return Check("python", FAIL,
                 f"found {got[0]}.{got[1]}, OmniGibson/IsaacSim pin "
                 f"{REQUIRED_PY[0]}.{REQUIRED_PY[1]}")


def check_os() -> Check:
    s = platform.system()
    if s == "Linux":
        return Check("os", PASS, platform.platform())
    return Check("os", FAIL,
                 f"{s}: Isaac Sim/OmniGibson are Linux-only "
                 f"(this is expected on the CPU dev machine)")


def check_repair_layer() -> Check:
    try:
        import rekep_repair
        from rekep_repair.adapter import RepairEnvironmentAdapter  # noqa: F401
        return Check("rekep_repair (repair layer)", PASS,
                     f"v{rekep_repair.__version__}")
    except Exception as e:                                    # pragma: no cover
        return Check("rekep_repair (repair layer)", FAIL, repr(e))


def check_cpu_stack() -> List[Check]:
    out = []
    for mod, hard in (("numpy", True), ("scipy", True), ("matplotlib", False)):
        v = _v(mod)
        out.append(Check(mod, PASS if v else (FAIL if hard else WARN),
                         v or "not importable", hard=hard))
    if (nv := _v("numpy")) and nv.startswith("2."):
        out.append(Check("numpy<2 constraint", WARN,
                         f"found {nv}; OmniGibson toolchains often require <2",
                         hard=False))
    return out


# --------------------------------------------------------------------------
# GPU-only checks (never run under --dry-run)
# --------------------------------------------------------------------------
def check_driver() -> Check:
    if shutil.which("nvidia-smi") is None:
        return Check("nvidia driver", FAIL, "nvidia-smi not found")
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,name,driver_version,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=60, check=True).stdout
    except Exception as e:
        return Check("nvidia driver", FAIL, repr(e))
    rows = [r for r in out.strip().splitlines() if r.strip()]
    if not rows:
        return Check("nvidia driver", FAIL, "no GPUs reported")
    drv = rows[0].split(",")[2].strip()
    try:
        parts = tuple(int(x) for x in drv.split(".")[:2])
    except Exception:
        parts = (0, 0)
    ok_drv = parts >= MIN_DRIVER
    names_ok = all(EXPECT_GPU_NAME in r.split(",")[1] for r in rows)
    detail = f"{len(rows)} GPU(s), driver {drv}"
    if not ok_drv:
        return Check("nvidia driver", FAIL,
                     f"{detail}; need >= {MIN_DRIVER[0]}.{MIN_DRIVER[1]}")
    if len(rows) != EXPECT_GPUS or not names_ok:
        return Check("nvidia driver", WARN,
                     f"{detail}; expected {EXPECT_GPUS}x RTX {EXPECT_GPU_NAME}",
                     hard=False)
    return Check("nvidia driver", PASS, detail)


def check_torch() -> List[Check]:
    out: List[Check] = []
    try:
        import torch
    except Exception as e:
        return [Check("torch", FAIL, f"not importable: {e!r}")]
    out.append(Check("torch", PASS if torch.__version__.startswith(EXPECT_TORCH)
                     else WARN, torch.__version__, hard=False))
    if not torch.cuda.is_available():
        out.append(Check("torch.cuda", FAIL,
                         "CUDA unavailable -- likely a CPU-only wheel; "
                         "reinstall from the cu121 index"))
        return out
    cv = torch.version.cuda or "?"
    out.append(Check("torch CUDA build", PASS if cv.startswith(EXPECT_CUDA) else WARN,
                     f"cuda {cv}", hard=False))
    out.append(Check("torch device count",
                     PASS if torch.cuda.device_count() == EXPECT_GPUS else WARN,
                     str(torch.cuda.device_count()), hard=False))
    try:
        cap = torch.cuda.get_device_capability(0)
        out.append(Check("compute capability",
                         PASS if cap >= (8, 6) else WARN, f"sm_{cap[0]}{cap[1]}",
                         hard=False))
        (torch.zeros(8, device="cuda") + 1).sum().item()
        out.append(Check("cuda smoke (alloc+add)", PASS, "ok"))
    except Exception as e:
        out.append(Check("cuda smoke (alloc+add)", FAIL, repr(e)))
    return out


def check_sim_stack() -> List[Check]:
    out = []
    for mod, hard in (("omnigibson", True), ("omni", True), ("open3d", False),
                      ("cv2", False), ("transforms3d", False)):
        v = _v(mod)
        out.append(Check(mod, PASS if v else (FAIL if hard else WARN),
                         v or "not importable", hard=hard))
    return out


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="config validation only; no GPU imports (safe on CPU)")
    args = ap.parse_args()

    checks: List[Check] = [check_python(), check_os(), check_repair_layer()]
    checks += check_cpu_stack()

    if args.dry_run:
        print("MODE: --dry-run (configuration validation only; no GPU imports)\n")
        for c in (check_driver, check_torch, check_sim_stack):
            checks.append(Check(f"{c.__name__} (GPU)", SKIP,
                                "skipped in dry-run", hard=False))
    else:
        if platform.system() == "Darwin":
            print("REFUSING: full mode is REMOTE GPU SERVER ONLY and this is "
                  "macOS.\nRun with --dry-run here.", file=sys.stderr)
            sys.exit(2)
        print("MODE: full (REMOTE GPU SERVER ONLY)\n")
        checks.append(check_driver())
        checks += check_torch()
        checks += check_sim_stack()

    width = max(len(c.name) for c in checks) + 2
    hard_fail = False
    for c in checks:
        print(f"  [{c.status:4}] {c.name:<{width}} {c.detail}")
        if c.status == FAIL and c.hard:
            hard_fail = True

    print()
    if args.dry_run:
        print("Dry-run complete. GPU checks were SKIPPED and remain "
              "'requires remote GPU verification'.")
        sys.exit(0)
    print("FAIL: environment not ready." if hard_fail else "OK: environment ready.")
    sys.exit(1 if hard_fail else 0)


if __name__ == "__main__":
    main()
