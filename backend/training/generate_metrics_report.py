"""
generate_metrics_report.py
--------------------------
Retrains GAIDA's 3 ML models and writes a defense-ready report to
backend/training/metrics_report.txt, including:

  * per-model accuracy / macro-F1 / CV / suicidal recall
  * the ENSEMBLE's macro-F1 + confusion matrix + per-class table
  * class-balance of the training data

Usage (from backend/):
    venv\\Scripts\\python.exe training\\generate_metrics_report.py

Healthy targets to defend in front of a panel:
  * ensemble suitability >= 95% (never miss a crisis phrase)
  * macro-F1 clearly above the no-skill baseline (20% for 5 classes)
"""

import sys
import pickle
import json
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_fscore_support,
    confusion_matrix,
)

from app.services import ml_classifier as mc
from app.services.text_prep import preprocess
from app.services.virtual_agent import detect_intent_and_level

REPORT_PATH = Path(__file__).resolve().parent / "metrics_report.txt"
SEED = 42


def _fmt_pct(x) -> str:
    return f"{x * 100:.2f}%"


def _model_suite():
    return {
        "Logistic Regression": mc.LR_MODEL_PATH,
        "Random Forest": mc.RF_MODEL_PATH,
        "Neural Network": mc.NN_MODEL_PATH,
    }


def _ensemble_predict(models, texts):
    """Same fusion as classify_intent -- majority vote, LR tiebreak, no threshold."""
    preds = []
    for t in texts:
        votes = Counter(m.predict([t])[0] for m in models.values())
        intent, count = votes.most_common(1)[0]
        if count == 1:
            intent = models["Logistic Regression"].predict([t])[0]
        preds.append(intent)
    return preds


def _evaluate(y_true, y_pred, labels):
    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    per_class = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    details = {}
    for i, label in enumerate(labels):
        details[label] = {
            "precision": per_class[0][i],
            "recall": per_class[1][i],
            "f1": per_class[2][i],
        }
    return acc, macro_f1, details, cm


def main():
    texts, labels = mc.load_dataset()
    aug_texts, aug_labels = mc.load_anger_augmentation()
    sui_texts, sui_labels = mc.load_suicidal_augmentation()
    classes = dict(Counter(labels))
    class_names = sorted(classes)

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=SEED, stratify=labels
    )

    # Retrain + save all models (this is what production loads)
    mc.train_and_compare()

    models = {
        name: pickle.load(open(path, "rb"))
        for name, path in _model_suite().items()
    }

    lines = []
    def out(s=""):
        lines.append(s)

    out("=" * 78)
    out("GAIDA SCRIBBLE-DETECTION MODEL REPORT")
    out("=" * 78)
    out(f"Dataset: {len(texts)} REAL labeled messages, {len(class_names)} classes")
    out(f"Real class distribution: {', '.join(f'{k}={v}' for k, v in sorted(classes.items()))}")
    if aug_texts:
        aug_counts = Counter(aug_labels)
        out(f"Augmentation: +{len(aug_texts)} curated anger examples "
            f"({', '.join(f'{k}={v}' for k, v in sorted(aug_counts.items()))}) - TRAIN ONLY")
    if sui_texts:
        sui_counts = Counter(sui_labels)
        out(f"Augmentation: +{len(sui_texts)} curated suicidal examples "
            f"({', '.join(f'{k}={v}' for k, v in sorted(sui_counts.items()))}) - TRAIN ONLY")
    out(f"Split: stratified 80/20 (train/test), seed {SEED}; "
        f"test set = {len(X_test)} real messages, NEVER augmented")
    out(f"Features: TF-IDF (1-2 grams, max 5000) + Taglish-aware preprocessing")
    out(f"Preprocessing: lower, collapse repeats, expand contractions, "
        f"drop {len(mc.STOPWORDS) if hasattr(mc, 'STOPWORDS') else 'curated'} stopwords")
    out("")

    out(f"{'Model':<25} {'Test Acc':>9} {'Macro-F1':>10} {'Suicidal Recall':>16}")
    out("-" * 62)
    per_model = {}
    for name, model in models.items():
        y_pred = model.predict(X_test)
        acc, macro_f1, details, _ = _evaluate(y_test, y_pred, class_names)
        sui_recall = details["suicidal"]["recall"]
        per_model[name] = (acc, macro_f1, details)
        out(f"{name:<25} {_fmt_pct(acc):>9} {_fmt_pct(macro_f1):>10} "
            f"{_fmt_pct(sui_recall):>16}")
    out("")

    # Ensemble (what the live system uses)
    y_ens = _ensemble_predict(models, X_test)
    ens_acc, ens_f1, ens_details, ens_cm = _evaluate(y_test, y_ens, class_names)

    out("=" * 78)
    out("ENSEMBLE (majority vote, LR tiebreak) - what production runs")
    out("=" * 78)
    out(f"Accuracy : {_fmt_pct(ens_acc)}")
    out(f"Macro-F1 : {_fmt_pct(ens_f1)}   (no-skill baseline for 5 classes = 20%)")
    out(f"Suicidal recall: {_fmt_pct(ens_details['suicidal']['recall'])}  "
        f"[target >= 95% - never miss a crisis phrase]")
    out("")
    out("PER-CLASS (ensemble):")
    out(f"{'class':<12} {'precision':>11} {'recall':>8} {'f1':>8}")
    out("-" * 42)
    for label in class_names:
        d = ens_details[label]
        out(f"{label:<12} {_fmt_pct(d['precision']):>11} {_fmt_pct(d['recall']):>8} "
            f"{_fmt_pct(d['f1']):>8}")
    out("")

    out("CONFUSION MATRIX (rows=true, cols=predicted):")
    out(f"{'':<12}" + "".join(f"{c:>12}" for c in class_names))
    for i, row in enumerate(ens_cm):
        out(f"{class_names[i]:<12}" + "".join(f"{v:>12}" for v in row))
    out("")

    out("BEST SINGLE MODEL: " + max(per_model, key=lambda n: per_model[n][1]))
    out("")

    # End-to-end: full detection pipeline (keywords -> safe phrases -> ML -> rules)
    out("=" * 78)
    out("END-TO-END PIPELINE on the same real test set (what the student chats with)")
    out("=" * 78)
    total_sui = sum(1 for y in y_test if y == "suicidal")
    e2e_caught = 0
    e2e_fp = 0
    e2e_fp_examples = []
    for t, y in zip(X_test, y_test):
        verdict = detect_intent_and_level(t)
        if verdict["intent"] == "suicidal":
            if y == "suicidal":
                e2e_caught += 1
            else:
                e2e_fp += 1
                if len(e2e_fp_examples) < 8:
                    e2e_fp_examples.append(t)
    e2e_recall = (e2e_caught / total_sui) if total_sui else 0.0
    out(f"Real suicidal messages in test set       : {total_sui}")
    out(f"Flagged suicidal by the live pipeline    : {e2e_caught}"
        f"   -> suicidal recall = {_fmt_pct(e2e_recall)}  [target >= 95%]")
    out(f"False-positive suicidal flags on other labels: {e2e_fp}")
    if e2e_fp_examples:
        out("FP examples (first " + str(len(e2e_fp_examples)) + "):")
        for ex in e2e_fp_examples:
            out("  - " + ex[:70])
    out("")

    out("FINALIST NOTE: confidence < 0.55 (threshold) -> 'uncertain', delegated")
    out("to the rule engine + context guards; this is a feature, not a gap.")
    out("=" * 78)

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[saved -> {REPORT_PATH} ]")


if __name__ == "__main__":
    main()