# CoPE Research Workspace

This private repository contains the CoPE implementation, experiment protocols,
audited result tables, negative results, and reproducibility checks.

中文阅读入口：
[实验地图（小学生版）](docs/EXPERIMENTS_INDEX_BEGINNER_CN.md)

Current scientific conclusion: CoPE is not more accurate than a fully
specified generic sparse patch in the held-out v3 comparison (40/40 versus
40/40), but it is substantially more compact and faster to generate. See
[the authoritative v3 decision](research/167_OCCURRENCE_CONFIRMATORY_V3_RESULT_AND_CLAIM_DECISION.md).

The repository intentionally retains failed and superseded experiments for
auditability. Do not treat every file named `RESULT` as current evidence; use
the experiment map and each report's supersession notes.

## VLA Remote Setup

Server:

```bash
ssh -i work/ssh/lijingsu_fvl10 -p 26575 lijingsu@10.176.53.120
```

Environment:

```bash
cd ~/vla
source .venv/bin/activate
python check_vla_env.py
```

OpenVLA smoke, after model access works:

```bash
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME=~/vla/cache/huggingface
python openvla_smoke.py --model openvla/openvla-7b --device cuda:0
```

If the model returns 403, accept the model license on HuggingFace and set:

```bash
export HF_TOKEN=...
```
