"""
Acoustic / voice-prosody scoring harness.

Measures how well GAIDA's voice pipeline (app.analytics.acoustic_features)
judges real voice clips against hand-labeled ground truth. The formula runs
(librosa + ffmpeg) but its real-world accuracy has never been scored — this
script is the validation instrument for closing that gap before defense.

Ground truth: a CSV (see sample_labeled_acoustic.csv) with one row per audio
file:

    filename,emotion,severity,note
    audio_samples/calm_01.wav,calm,Normal,optional free-text note

emotion  : one of anxious, sad, angry, calm, neutral
severity : one of Normal, Low, Moderate, High   (acoustic can never be Crisis)

Usage (from backend/):
    python training/acoustic_validation/evaluate_acoustic.py \
        --csv training/acoustic_validation/sample_labeled_acoustic.csv \
        --audio-dir training/acoustic_validation \
        --out training/acoustic_validation/results.csv

Recommendation: at least 10 files per emotion class, ideally from student
volunteers reading scripted scripts (same wording, contrasting delivery) so
the only difference is the prosody itself. Keep consent on file — the clips
are personal data.
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.analytics.acoustic_features import extract_features, map_acoustic_to_severity  # noqa: E402

SEVERITY_MAP = {"Normal": 0, "Low": 1, "Moderate": 2, "High": 3}


def evaluate(csv_path: Path, audio_dir: Path):
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row["_filename"] = row["filename"].strip()
            row["_emotion_gold"] = (row["emotion"] or "").strip().lower()
            row["_severity_gold"] = (row["severity"] or "").strip().title()
            rows.append(row)

    per_emotion = defaultdict(lambda: {"correct": 0, "total": 0})
    severity_conf = defaultdict(lambda: defaultdict(int))
    detail = []
    skipped = 0

    for row in rows:
        path = audio_dir / row["_filename"]
        if not path.exists():
            print(f"  ! missing audio file: {path}")
            skipped += 1
            continue

        with open(path, "rb") as fh:
            audio_bytes = fh.read()

        try:
            feats = extract_features(audio_bytes)
        except Exception as e:
            print(f"  ! extract failed for {row['_filename']}: {e}")
            skipped += 1
            continue

        pred_emotion = feats.get("acoustic_emotion") or "neutral"
        pred_severity = map_acoustic_to_severity(feats.get("acoustic_anxiety_score", 0.0))

        e_gold = row["_emotion_gold"]
        s_gold = row["_severity_gold"]

        per_emotion[e_gold]["total"] += 1
        if pred_emotion == e_gold:
            per_emotion[e_gold]["correct"] += 1
        severity_conf[s_gold][pred_severity] += 1

        detail.append({
            "filename": row["_filename"],
            "emotion_gold": e_gold,
            "emotion_pred": pred_emotion,
            "emotion_correct": "Y" if pred_emotion == e_gold else "N",
            "severity_gold": s_gold,
            "severity_pred": pred_severity,
            "anxiety_score": round(float(feats.get("acoustic_anxiety_score", 0.0)), 3),
            "note": row.get("note", ""),
        })

    return per_emotion, severity_conf, detail, skipped


def report(per_emotion, severity_conf, detail, skipped) -> None:
    total = len(detail)
    print("=" * 70)
    print("ACOUSTIC SCORING VALIDATION REPORT")
    print("=" * 70)

    if total == 0:
        print("No labeled clips evaluated (all skipped or missing).")
        return

    correct_emotion = sum(1 for d in detail if d["emotion_correct"] == "Y")
    print(f"\nClips evaluated : {total}   (skipped: {skipped})")
    print(f"EMOTION accuracy: {correct_emotion}/{total} = {correct_emotion/total:.1%}")

    print("\nPer-gold-emotion accuracy (support | correct | accuracy):")
    for gold in sorted(per_emotion):
        st = per_emotion[gold]
        acc = st["correct"] / st["total"] if st["total"] else 0
        print(f"  {gold:<10}: {st['total']:>3} clips | {st['correct']:>3} | {acc:>6.1%}")

    print("\nSeverity confusion matrix (rows = gold, cols = predicted):")
    labels = ["Normal", "Low", "Moderate", "High"]
    header = "".join(f"{l:>9}" for l in labels)
    print(f"{'gold':<9}" + header)
    exact = 0
    for gold in labels:
        cells = "".join(f"{severity_conf[gold][p]:>9}" for p in labels)
        print(f"{gold:<9}" + cells)
        exact += severity_conf[gold][gold]
    print(f"\nSEVERITY exact-match: {exact}/{total} = {exact/total:.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=str(Path(__file__).parent / "sample_labeled_acoustic.csv"))
    parser.add_argument("--audio-dir", default=str(Path(__file__).parent))
    parser.add_argument("--out", default=str(Path(__file__).parent / "acoustic_eval_results.csv"))
    args = parser.parse_args()

    csv_path = Path(args.csv)
    audio_dir = Path(args.audio_dir)
    per_emotion, severity_conf, detail, skipped = evaluate(csv_path, audio_dir)

    report(per_emotion, severity_conf, detail, skipped)

    out = Path(args.out)
    if detail and out:
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(detail[0].keys()))
            writer.writeheader()
            writer.writerows(detail)
        print(f"\nPer-clip results written to: {out}")


if __name__ == "__main__":
    main()