import torch
import transformers

print("torch:", torch.__version__)
print("transformers:", transformers.__version__)
print("cuda_available:", torch.cuda.is_available())
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        print(f"gpu_{i}: {props.name}, {props.total_memory / 1024**3:.1f} GiB")

