"""
Exports anonymously-collected research sessions into the format the
existing expert_validation/ review flow expects.

This deliberately does NOT write directly into anxiety_training.jsonl.
A GAD-7 band is a provisional signal, not a confirmed label — per Bibera
and Bechayda's own answers, borderline scores and the label itself should
be reviewed by a counselor/psych faculty member before anything is trusted
as ground truth. This script produces the *candidate* file for that review
step (matching expert_validation/sample_for_experts.csv's shape), not a
finished training file.

Usage:
    python export_research_data.py --out expert_validation/sample_for_experts.csv
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
from app.database.database import supabase  # noqa: E402

GAD7_BAND_TO_CANDIDATE_LABEL = {
    "minimal": "neutral",
    "mild": "anxiety",
    "moderate": "anxiety",
    "severe": "suicidal",  # flagged for priority review, not auto-accepted
}


def fetch_research_sessions() -> list[dict]:
    result = (
        supabase.table("sessions")
        .select("session_token, student_id, is_anonymous, year_level, program, gender, region")
        .eq("is_research", True)
        .execute()
    )
    return result.data or []


def fetch_gad7(session_id: str) -> dict | None:
    result = (
        supabase.table("gad7_responses")
        .select("total_score, severity_band")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def fetch_messages(session_id: str) -> list[dict]:
    result = (
        supabase.table("interactions")
        .select("message, intent, confidence, severity, timestamp")
        .eq("session_id", session_id)
        .order("timestamp")
        .execute()
    )
    return result.data or []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="research_export_for_review.csv",
        help="Separate from expert_validation/sample_for_experts.csv on purpose — "
             "that file is a fixed sample checked against gold_key.csv for inter-rater "
             "agreement, a different exercise from labeling newly-collected data.",
    )
    args = parser.parse_args()

    sessions = fetch_research_sessions()
    if not sessions:
        print("No research sessions found (sessions.is_research = true). Nothing to export.")
        return

    rows = []
    sample_id = 0
    for s in sessions:
        session_id = s["session_token"]
        gad7 = fetch_gad7(session_id)
        if not gad7:
            continue  # skip sessions where the participant never completed GAD-7

        candidate_label = GAD7_BAND_TO_CANDIDATE_LABEL[gad7["severity_band"]]

        for msg in fetch_messages(session_id):
            text = (msg.get("message") or "").strip()
            if not text:
                continue
            sample_id += 1
            rows.append({
                "sample_id": sample_id,
                "session_id": session_id,
                # Only populated for identified (non-anonymous) sessions —
                # lets the counselor follow up on a specific case if needed.
                "student_id": "" if s.get("is_anonymous") else (s.get("student_id") or ""),
                "is_anonymous": bool(s.get("is_anonymous")),
                "text": text,
                "gad7_total_score": gad7["total_score"],
                "gad7_band": gad7["severity_band"],
                "candidate_label": candidate_label,
                "model_detected_intent": msg.get("intent") or "",
                "model_severity": msg.get("severity") or "",
                "year_level": s.get("year_level") or "",
                "program": s.get("program") or "",
                "gender": s.get("gender") or "",
                "region": s.get("region") or "",
                # Same column names compute_agreement.py already expects, so this
                # file can be run through the same review workflow if desired.
                "counselor_A_label": "",
                "counselor_B_label": "",
            })

    if not rows:
        print("Found research sessions, but none had both a completed GAD-7 and messages.")
        return

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} candidate rows from {len(sessions)} research sessions to {out_path}")
    print("Next step: have a counselor/psych faculty member fill in counselor_A_label "
          "(and counselor_B_label for a second rater) before treating candidate_label as ground truth.")


if __name__ == "__main__":
    main()
