"""
build_training_audit.py
-----------------------
VALIDATES THE ACTUAL TRAINING DATA (label audit).

Samples rows from the REAL training set (anxiety_training.jsonl) and asks a
licensed counselor to CONFIRM or CORRECT the team's label on each row.

This is different from build_expert_sample.py:
  * build_expert_sample  = 120 NEW messages, blank labels -> measures
    INTER-EXPERT AGREEMENT (kappa) on the label scheme.
  * build_training_audit = 90 REAL training rows, current label SHOWN ->
    verifies the dataset annotations are correct (label integrity).

Outputs:
  * training_audit.csv      -- sent to counselors (sample_id, text, current_label, counselor_verdict)
  * training_audit_form.html -- printable version
"""

import csv
import html
import json
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "anxiety_training.jsonl"
PER_CLASS = 18
SEED = 7


def load_rows():
    rows = []
    with open(DATA, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _sample_stratified(rows):
    by_label = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)
    rng = random.Random(SEED)
    picked = []
    for label in sorted(by_label):
        pool = by_label[label]
        picked += rng.sample(pool, min(PER_CLASS, len(pool)))
    rng.shuffle(picked)
    return picked


def _write_csv(picked):
    with open(BASE / "training_audit.csv", "w", encoding="utf-8-sig", newline="") as f:
        f.write("sample_id,text,current_label,counselor_verdict\n")
        for i, r in enumerate(picked, start=1):
            text = r["text"].replace('"', '""')
            f.write(f'{i},"{text}",{r["label"]},\n')


def _write_form(picked):
    rows_html = "".join(
        "<tr><td class=\"num\">{num}</td><td>{msg}</td>"
        "<td class=\"cur\">{cur}</td><td class=\"opt\"></td>"
        "<td class=\"fix\"></td></tr>".format(
            num=i, msg=html.escape(r["text"]), cur=r["label"]
        )
        for i, r in enumerate(picked, start=1)
    )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GAIDA - Training Data Label Audit</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; margin: 20px 28px; }}
  h1 {{ font-size: 20px; margin: 0 0 2px; }}
  h2 {{ font-size: 15px; margin: 22px 0 8px; border-bottom: 1px solid #999; padding-bottom: 3px; }}
  p, li {{ font-size: 12px; line-height: 1.5; }}
  .muted {{ color: #555; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  th, td {{ border: 1px solid #bbb; padding: 4px 6px; vertical-align: middle; }}
  th {{ background: #eee; font-weight: bold; text-align: left; }}
  tr {{ page-break-inside: avoid; }}
  .num {{ width: 30px; text-align: center; }}
  .msg {{ width: 46%; }}
  .cur {{ width: 12%; text-align: center; font-weight: bold; }}
  .opt {{ width: 14%; text-align: center; }}
  .fix {{ width: 22%; }}
  .sig {{ margin-top: 28px; font-size: 12px; }}
  .sig td {{ border: none; padding: 10px 0; }}
  @media print {{
    body {{ margin: 10mm; }}
    thead {{ display: table-header-group; }}
  }}
</style>
</head>
<body>

<h1>GAIDA - Training Data Label Audit</h1>
<p class="muted">AI-based Anxiety Detection System &middot; College Guidance &middot; University of the East</p>

<p><b>Purpose.</b> GAIDA's model is trained on student-like messages that our team labeled across
5 categories. We ask a licensed mental health professional to AUDIT the correctness of these labels:
for each message, our current label is shown. Please check <b>Agree</b> if the label is correct, or
write the corrected label in the last column if it is not.</p>

<p><b>Time required:</b> approximately 10&ndash;15 minutes.</p>

<h2>Label Definitions (with examples)</h2>
<ul>
  <li><b>anxiety</b> &mdash; nervousness, worry, tension, dread, panic-like feelings, overthinking.</li>
  <li><b>sadness</b> &mdash; low mood, grief, loneliness, emptiness, crying.</li>
  <li><b>neutral</b> &mdash; casual or everyday statements with no significant distress.</li>
  <li><b>suicidal</b> &mdash; death wishes, wanting to end one&rsquo;s life, self-harm &mdash; even when phrased indirectly.</li>
  <li><b>anger</b> &mdash; irritation, frustration, hostility.</li>
</ul>

<h2>Audit Sheet</h2>
<table>
  <thead>
    <tr>
      <th class="num">#</th>
      <th class="msg">Student Message (from our training data)</th>
      <th class="cur">Current Label</th>
      <th class="opt">Agree &radic;</th>
      <th class="fix">If NOT agree, corrected label:</th>
    </tr>
  </thead>
  <tbody>
{rows_html}
  </tbody>
</table>

<table class="sig">
  <tr>
    <td><b>Counselor Name:</b> ______________________________</td>
    <td><b>Date:</b> ___________________</td>
  </tr>
  <tr>
    <td><b>Signature:</b> ___________________________________</td>
    <td><b>List name (A or B):</b> ________</td>
  </tr>
</table>

<p class="muted">For research use only. Responses will be compared anonymously to measure agreement with
the team's annotations.</p>

</body>
</html>
"""
    with open(BASE / "training_audit_form.html", "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    rows = _sample_stratified(load_rows())
    dist = {}
    for r in rows:
        dist[r["label"]] = dist.get(r["label"], 0) + 1
    print("Sample:", dist, "| total:", len(rows))
    _write_csv(rows)
    _write_form(rows)
    print("Wrote training_audit.csv and training_audit_form.html")


if __name__ == "__main__":
    main()