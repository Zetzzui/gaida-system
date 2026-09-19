# Acoustic / Voice-Scoring Validation Kit

GAIDA's voice pipeline (`backend/app/analytics/acoustic_features.py`) extracts
librosa prosody features (pitch, energy, jitter, shimmer, speech rate, pauses)
and maps them to an emotion (anxious / sad / angry / calm / neutral) and a
severity (Normal / Low / Moderate / High). It runs technically, but **its
real-world accuracy has never been measured** against human-labeled audio.
This kit is the instrument to close that gap before defense.

## Why this exists
The defense brief asks: "Voice/acoustic scoring is still unvalidated against
real labeled data." The fix is data + a reproducible harness — this folder is
that harness. Fill in the clips, run one command, and you get an accuracy
report you can put in the paper/talk.

## What to do
1. **Collect clips.** Have volunteers (same consent you already use) read a
   small script while intentionally calm / anxious / sad / angry / neutral —
   same words, different delivery — so the *only* difference is prosody.
   A phone recording is fine (the pipeline normalizes to 16 kHz mono).
2. **Name + label them.** Put each file under `audio_samples/` and add one row
   to `sample_labeled_acoustic.csv`:
   `filename,emotion,severity,note`
   - `emotion` ∈ {anxious, sad, angry, calm, neutral}
   - `severity` ∈ {Normal, Low, Moderate, High} (acoustic alone can never reach Crisis)
3. **Run the harness** (from `backend/`, with deps installed):
   ```
   python training/acoustic_validation/evaluate_acoustic.py
   ```
   Add `--audio-dir ...`, `--csv ...`, and `--out ...` to point at your data.

## Target
At least 10 clips per emotion (50 total). Report the accuracy numbers however
they land — the goal is honest measurement, not a cherry-picked score.

## Files
- `sample_labeled_acoustic.csv` — label template (1 row per clip)
- `evaluate_acoustic.py` — the evaluation harness (librosa features → report)
- `acoustic_eval_results.csv` — written by the harness (per-clip predictions)