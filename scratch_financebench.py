from datasets import load_dataset

ds = load_dataset("PatronusAI/financebench", split="train")
print(ds[0].keys())
print("First item sample:")
for k, v in ds[0].items():
    print(f"{k}: {str(v)[:100]}")
