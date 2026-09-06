# VLA Remote Setup

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

