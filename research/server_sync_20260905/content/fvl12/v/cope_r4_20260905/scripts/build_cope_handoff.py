#!/usr/bin/env python3
"""Assemble `cope_fsrpc_交接_v1/` and verify it byte-for-byte.

Every code file in the handoff is copied, never re-typed, and its SHA-256 is
compared against the source. A mismatch is a hard failure.

    python3 scripts/build_cope_handoff.py
"""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cope_fsrpc_交接_v1"

# (source, destination) — sources are copied verbatim
CODE_DIRS = [("cope", "code/cope")]
# Mirrored at its real import path so the package is self-contained: the pilot
# script imports `rekep_repair.benchmark.statistics` unmodified.
CODE_FILES = [
    ("rekep_repair/benchmark/statistics.py",
     "code/rekep_repair/benchmark/statistics.py"),
]

# Generated (not copied) so the delivered tree runs standalone.
STUB = ('"""Namespace stub for the handoff package.\n\n'
        'Only `statistics.py` is delivered here; the full `rekep_repair` package\n'
        'lives in the main repository and is reused unchanged.\n"""\n')
BOOTSTRAP = (
    '"""Puts `code/` on sys.path so `cope` and `rekep_repair.benchmark.\n'
    'statistics` import without installation. Collected automatically by\n'
    'pytest; imported explicitly by the scripts."""\n'
    "import sys\n"
    "from pathlib import Path\n\n"
    "CODE = Path(__file__).resolve().parent / 'code'\n"
    "if str(CODE) not in sys.path:\n"
    "    sys.path.insert(0, str(CODE))\n")
SCRIPTS = ["run_cope_pilot.py", "cope_dry_run.py", "build_cope_handoff.py",
           "check_gpu_environment.py"]
TESTS = ["test_cope_semantics.py", "test_cope_fairness.py"]
CONFIGS = ["benchmark.yaml", "pilot.yaml", "machine.yaml"]
DOCS = [
    ("docs/COPE_METHOD.md", "COPE_METHOD.md"),
    ("docs/FSRPC_BASELINE_SPEC.md", "FSRPC_BASELINE_SPEC.md"),
    ("docs/BENCHMARK_TASK.md", "BENCHMARK_TASK.md"),
    ("docs/FAIR_COMPARISON_PROTOCOL.md", "FAIR_COMPARISON_PROTOCOL.md"),
    ("docs/METRICS.md", "METRICS.md"),
    ("docs/PILOT_EXPERIMENT.md", "PILOT_EXPERIMENT.md"),
    ("docs/COPE_GPU_RUNBOOK.md", "GPU_RUNBOOK.md"),
    ("docs/COPE_COLLABORATION_NOTES.md", "COLLABORATION_NOTES.md"),
    ("docs/CHANGELOG_FROM_REKEP_V2.md", "CHANGELOG_FROM_REKEP_V2.md"),
    ("README_FIRST_COPE.md", "README_FIRST.md"),
    ("docs/COPE_PROJECT_STATUS.md", "PROJECT_STATUS.md"),
    ("docs/COPE_VALIDATION_REPORT.md", "VALIDATION_REPORT.md"),
]
RESULTS = ["stage_a_reliability.json", "stage_b_paired.json",
           "stage_c_ablations.json", "dry_run_nominal.txt", "dry_run_I1.txt",
           "dry_run_I2.txt", "dry_run_I3.txt", "dry_run_I4.txt"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy(src: Path, dst: Path) -> Tuple[str, str]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return sha256(src), sha256(dst)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    pairs: List[Tuple[Path, Path]] = []

    for s, d in CODE_DIRS:
        for f in sorted((ROOT / s).rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            pairs.append((f, OUT / d / f.relative_to(ROOT / s)))
    for s, d in CODE_FILES:
        pairs.append((ROOT / s, OUT / d))
    for n in SCRIPTS:
        pairs.append((ROOT / "scripts" / n, OUT / "scripts" / n))
    for n in TESTS:
        pairs.append((ROOT / "tests" / n, OUT / "tests" / n))
    for n in CONFIGS:
        pairs.append((ROOT / "configs_cope_gpu" / n, OUT / "configs_gpu" / n))
    for s, d in DOCS:
        pairs.append((ROOT / s, OUT / d))
    for n in RESULTS:
        pairs.append((ROOT / "results" / "cope_pilot" / n,
                      OUT / "results_cpu" / n))
    for n in ("episode_record.schema.json", "example_episode.json"):
        pairs.append((ROOT / "results_schema" / n, OUT / "results_schema" / n))
    for n in ("cope_fsrpc_experiment_design.tex",
              "cope_fsrpc_experiment_design.pdf"):
        pairs.append((ROOT / "report" / n, OUT / "report" / n))

    # generated files (documented as generated in the manifest)
    (OUT / "conftest.py").write_text(BOOTSTRAP)
    for d in ("code/rekep_repair", "code/rekep_repair/benchmark"):
        (OUT / d).mkdir(parents=True, exist_ok=True)
        (OUT / d / "__init__.py").write_text(STUB)
    (OUT / "run_all.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# Reproduce every CPU result in this package. No GPU software involved.\n"
        "set -euo pipefail\n"
        'cd "$(dirname "$0")"\n'
        "python3 -m pytest tests/ -q\n"
        "python3 scripts/run_cope_pilot.py --seeds 5 --out results_cpu_rerun\n"
        "for c in nominal I1 I2 I3 I4; do\n"
        "  python3 scripts/cope_dry_run.py --condition $c --seed 0 \\\n"
        "    --out results_cpu_rerun/dry_run_$c.txt > /dev/null\n"
        "done\n"
        'echo "OK -- compare results_cpu_rerun/ against results_cpu/"\n')
    (OUT / "run_all.sh").chmod(0o755)

    missing = [str(s.relative_to(ROOT)) for s, _ in pairs if not s.exists()]
    if missing:
        print("MISSING SOURCES:\n  " + "\n  ".join(missing))
        return 1

    checks: List[Dict[str, str]] = []
    mismatched = []
    for s, d in pairs:
        a, b = copy(s, d)
        checks.append({"source": str(s.relative_to(ROOT)),
                       "dest": str(d.relative_to(OUT)),
                       "sha256": a, "identical": a == b})
        if a != b:
            mismatched.append(str(s))

    if mismatched:
        print("BYTE-IDENTITY FAILURE:\n  " + "\n  ".join(mismatched))
        return 1

    try:
        rev = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                      text=True).strip()
        branch = subprocess.check_output(["git", "branch", "--show-current"],
                                         cwd=ROOT, text=True).strip()
    except Exception:
        rev, branch = "unknown", "unknown"

    manifest = {
        "package": "cope_fsrpc_交接_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_branch": branch, "git_rev": rev,
        "python": sys.version.split()[0], "platform": platform.platform(),
        "gpu_software_installed": False,
        "gpu_commands_executed": False,
        "n_files": sum(1 for f in OUT.rglob("*") if f.is_file()) + 1,  # + SHA256SUMS
        "byte_identity_checked": len(checks),
        "byte_identity_failures": 0,
        "generated_not_copied": ["conftest.py", "run_all.sh",
                                 "code/rekep_repair/__init__.py",
                                 "code/rekep_repair/benchmark/__init__.py"],
        "immutable_folders_not_modified": [
            "rekep_gpu_execution", "rekep_gpu_analysis",
            "rekep_repair_交接", "rekep_repair_交接_v2"],
        "file_checks": checks,
    }
    (OUT / "handoff_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False))

    # SHA256SUMS.txt last, so it covers every delivered file including the
    # manifest. It cannot cover itself.
    lines = [f"{sha256(f)}  {f.relative_to(OUT)}"
             for f in sorted(OUT.rglob("*"))
             if f.is_file() and f.name != "SHA256SUMS.txt"]
    (OUT / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n")

    print(f"Built {OUT.name}: {len(lines) + 1} files "
          f"({len(lines)} covered by SHA256SUMS.txt), "
          f"{len(checks)} byte-identity checks, 0 failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
