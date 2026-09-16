import json
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "anxiety_training.jsonl"
SAMPLE_PER_CLASS = 24
SEED = 42


def main():
    with open(DATA, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    by_label = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)

    print("Distribution:", {k: len(v) for k, v in sorted(by_label.items())})

    rng = random.Random(SEED)
    sample_rows = []
    for label in sorted(by_label):
        pool = by_label[label]
        picked = rng.sample(pool, min(SAMPLE_PER_CLASS, len(pool)))
        for r in picked:
            sample_rows.append(r)

    rng.shuffle(sample_rows)

    with open(BASE / "sample_for_experts.csv", "w", encoding="utf-8-sig", newline="") as f:
        f.write("sample_id,text,counselor_A_label,counselor_B_label\n")
        for i, r in enumerate(sample_rows, start=1):
            f.write(f"{i},\"{r['text'].replace('\"', '\"\"')}\",,,\n")

    with open(BASE / "gold_key.csv", "w", encoding="utf-8-sig", newline="") as f:
        f.write("sample_id,text,gold_label\n")
        for i, r in enumerate(sample_rows, start=1):
            f.write(f"{i},\"{r['text'].replace('\"', '\"\"')}\",{r['label']}\n")

    print(f"Exported {len(sample_rows)} sample rows -> expert_validation/sample_for_experts.csv")
    print(f"Gold key -> expert_validation/gold_key.csv")


if __name__ == "__main__":
    main()