import sys
import csv
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

BASE = Path(__file__).resolve().parent

LABEL_VARIANTS = {
    "anxiety": ("anxiety", "anxious"),
    "sadness": ("sadness", "sad", "depressed"),
    "suicidal": ("suicidal", "selfharm", "self-harm", "crisis"),
    "neutral": ("neutral", "normal", "none", "no distress"),
    "anger": ("anger", "angry"),
}


def _norm(label):
    label = (label or "").strip().lower()
    for canonical, variants in LABEL_VARIANTS.items():
        if label == canonical or label in variants:
            return canonical
    return label


def load_csv(name):
    with open(BASE / name, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def agreement_report(counselor_col_a="counselor_A_label", counselor_col_b="counselor_B_label"):
    gold = {r["sample_id"]: r["gold_label"] for r in load_csv("gold_key.csv")}
    labels = load_csv("sample_for_experts.csv")

    def hits_for(col):
        rated = [(r["sample_id"], gold[r["sample_id"]], _norm(r[col])) for r in labels if r[col].strip()]
        rated = [(sid, g, s) for sid, g, s in rated if sid in gold and s]
        n = len(rated)
        matches = sum(1 for _, g, s in rated if _norm(g) == s)
        print(f"{col:<22} hits gold: {matches}/{n} = {matches / max(n, 1) * 100:.1f}%")
        return rated

    a = hits_for(counselor_col_a)
    b = hits_for(counselor_col_b)

    both = sorted(set(s for s, _, _ in a) & set(s for s, _, _ in b))
    if both:
        ya = [_norm(dict((s, x) for s, _, x in a)[s]) for s in both]
        yb = [_norm(dict((s, x) for s, _, x in b)[s]) for s in both]
        k = cohen_kappa_score(ya, yb)
        agree = sum(1 for x, y in zip(ya, yb) if x == y)
        print(f"Inter-expert agreement (A vs B): {agree}/{len(both)} = {agree / len(both) * 100:.1f}%")
        print(f"Cohen's kappa (A vs B)          : {k:.3f}")
        print("(kappa >= 0.61 = substantial agreement; >= 0.81 = almost perfect)")


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "counselor_A_label"
    b = sys.argv[2] if len(sys.argv) > 2 else "counselor_B_label"
    agreement_report(a, b)