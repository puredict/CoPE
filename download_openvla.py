from huggingface_hub import snapshot_download
p = snapshot_download(
    "openvla/openvla-7b",
    local_dir="/home/lijingsu/vla/models/openvla-7b",
    resume_download=True,
    max_workers=1,
)
print("downloaded", p)
