"""
diagnose_suicidal_misses.py
---------------------------
Reproduce the exact train/split used in production (seed 42, stratify),
then print every SUICIDAL test message with each model's vote so we can
see exactly how the ensemble misses 4/27.

Usage (from backend/):
    venv\\Scripts\\python.exe training\\diagnose_suicidal_misses.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter
from sklearn.model_selection import train_test_split
from app.services.ml_classifier import (
    load_dataset, load_anger_augmentation, build_pipelines,
)

texts, labels = load_dataset()
aug_texts, aug_labels = load_anger_augmentation()

X_train, X_test, y_train, y_test = train_test_split(
    texts, labels, test_size=0.2, random_state=42, stratify=labels
)
if aug_texts:
    X_train = X_train + aug_texts
    y_train = y_train + aug_labels

models = build_pipelines()
for name, pipe in models.items():
    print(f"Training {name}...")
    pipe.fit(X_train, y_train)

suic_rows = [(t, y) for t, y in zip(X_test, y_test) if y == "suicidal"]
print(f"\nTest set: {len(y_test)} rows | suicidal rows: {len(suic_rows)}\n")

missed = []
for text, true in suic_rows:
    preds = {name: pipe.predict([text])[0] for name, pipe in models.items()}
    votes = Counter(preds.values())
    majority = votes.most_common(1)[0][0]
    if votes.most_common(1)[0][1] == 1:
        majority = preds["Logistic Regression"]
    avg_conf = {}
    for name, pipe in models.items():
        p = pipe.predict_proba([text])[0]
        prob = dict(zip(pipe.classes_, p))
        avg_conf[name] = round(max(p), 3)
        avg_conf[name + "_suic"] = round(prob.get("suicidal", 0.0), 3)
    correct = majority == true
    tag = "OK " if correct else "MISS"
    if not correct:
        missed.append(text)
    print(f"[{tag}] true=suicidal | ensemble={majority}")
    print(f"     text: {text!r}")
    for name in models:
        print(f"        {name:<20} pred={preds[name]:<10} "
              f"p(suic)={avg_conf[name + '_suic']:.3f} p(max)={avg_conf[name]:.3f}")
    print()

print(f"\n=== {len(missed)} suicidal messages MISSED by majority ensemble ===")
for t in missed:
    print("  -", t)

# ---- Probe alternative fusion rules -----------------------------------------
print("\n=== ANALYZE ALTERNATIVE RECALL RULES (on the 27 suicidal rows) ===")
n = len(suic_rows)

# Rule A: any model votes suicidal -> suicidal
caught_a = sum(1 for text, true in suic_rows
               if any(pipe.predict([text])[0] == "suicidal" for pipe in models.values()))
print(f"A. ANY-model-votes-suicidal    caught {caught_a}/{n}")

# Rule B: any model p(suic) >= 0.45 -> suicidal
caught_b = 0
for text, true in suic_rows:
    probs = []
    for pipe in models.values():
        p = dict(zip(pipe.classes_, pipe.predict_proba([text])[0]))
        probs.append(p.get("suicidal", 0.0))
    if max(probs) >= 0.45:
        caught_b += 1
print(f"B. any p(suic)>=0.45           caught {caught_b}/{n}")

# Rule C: sec0.40
for thresh in (0.30, 0.40, 0.50):
    caught = 0
    for text, true in suic_rows:
        maxp = max(dict(zip(p.classes_, p.predict_proba([text])[0])).get("suicidal", 0.0)
                   for p in models.values())
        if maxp >= thresh:
            caught += 1
    print(f"C. any p(suic)>={thresh:.2f}              caught {caught}/{n}")

# False-positive cost of each rule across the whole test set
def rule_fp(rulelambda, name):
    rows = [(t, y) for t, y in zip(X_test, y_test) if y != "suicidal"]
    fp = sum(1 for text, true in rows if rulelambda(text))
    return fp

print()
for thresh in (0.30, 0.40, 0.45, 0.50):
    def rl(t, th=thresh):
        return max(dict(zip(p.classes_, p.predict_proba([t])[0])).get("suicidal", 0.0)
                   for p in models.values()) >= th
    fp = rule_fp(rl, thresh)
    print(f"   any p(suic)>={thresh:.2f} -> false-positive suicidal alerts on "
          f"{fp}/{len(y_test) - n} non-suicidal test rows")