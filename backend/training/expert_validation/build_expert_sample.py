"""
build_expert_sample.py
----------------------
Builds a 120-message expert-validation sample (24 per class) using
CONTEXT-FREE, unambiguously-labelable student phrases -- NOT sampled from
the training data.

Each message must be classifiable from the words alone (no backstory, no
context). These are deliberately "obvious" examples so a licensed counselor
can label each one confidently and we can measure inter-expert agreement.

Outputs:
  * sample_for_experts.csv   -- what gets sent to counselors (blank labels)
  * gold_key.csv             -- answer key (keep PRIVATE)
  * validation_form.html     -- printable PDF-style form (same 120 messages)
"""

import csv
import html
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent
SEED = 42

SAMPLES = {
    "neutral": [
        "I ate lunch with my classmates today",
        "May klase ako sa alas-diyes mamaya",
        "I'm just watching Netflix right now",
        "chill lang ang weekend ko",
        "I passed my math exam",
        "kakain na ako kasi gutom na ako",
        "I'm scrolling through social media",
        "Gumising ako ng maaga at nag-ayos ng kama",
        "I bought new shoes today and I like them",
        "mamaya na ako matutulog, may gagawin pa",
        "My friends and I played basketball yesterday",
        "Napanood ko na ang movie na sinabi mo",
        "I'm doing my homework right now",
        "Naalala ko lang na may meeting tayo bukas",
        "I'll go to the mall this weekend",
        "Nilinis ko ang kwarto ko kanina",
        "good morning, ang sarap ng tulog ko",
        "I'm looking forward to the upcoming holiday",
        "Umuulan ngayon, dala ko ang payong ko",
        "I finished my project earlier than expected",
        "Nagtext ako sa kaibigan ko kagabi",
        "The weather is nice today",
        "May concert daw sa November, excited ako",
        "I'm just taking a break from studying",
    ],
    "anxiety": [
        "my heart is racing and I can't calm down",
        "sobrang kaba ko, para akong masusuka sa exam",
        "I keep overthinking every little thing until I can't sleep",
        "hindi ako makahinga sa sobrang pag-aalala ko",
        "I'm so nervous I feel like I'm shaking",
        "parang nasasakal ako sa kaba",
        "I can't stop worrying about what might happen tomorrow",
        "hindi ko mapigilan ang takot na nararamdaman ko",
        "my palms are sweating and my mind is racing right now",
        "paulit-ulit kong iniisip ang mga pangyayari at di ako kumalma",
        "I feel a lump in my throat every time I think about it",
        "parang may nagbagsak ng dingding sa dibdib ko sa sobrang kaba",
        "I'm terrified I'll fail everything and I can't turn my mind off",
        "nanginginig ang kamay ko sa kaba",
        "I can't stop my heart from pounding, it's scaring me",
        "ang daming nasa isip ko, sabog na sabog na ako",
        "I keep imagining the worst happening over and over",
        "nahihilo na ako sa kakaisip",
        "I feel panicky and I don't know why",
        "pinagpapawisan ako kahit hindi naman mainit, ang kaba ko",
        "I'm worried sick about my health and I can't stop checking it",
        "hanggang ngayon kinakabahan pa rin ako sa nangyari",
        "I keep getting a knot in my stomach from worrying",
        "hindi ako makatulog sa kaba sa quiz bukas",
    ],
    "sadness": [
        "sobrang lungkot ko ngayon, gusto kong umiyak",
        "I've been crying all day and I can't stop",
        "walang nakakaintindi sa nararamdaman ko",
        "I feel so alone in this world",
        "parang ang bigat at walang laman ang dibdib ko",
        "I lost my best friend and I just feel empty",
        "wala akong lakas gawin ang kahit ano, lungkot lang",
        "I feel like nobody loves me",
        "umiiyak ako mag-isa sa kwarto",
        "it hurts so much and I don't know how to move on",
        "malungkot na malungkot na talaga ako araw-araw",
        "I just want to be alone because I feel so down",
        "nawalan na ako ng gana sa mga dati kong hilig",
        "I feel empty inside, like nothing matters anymore",
        "ang sakit na lagi na lang akong naiwan",
        "I feel so sad that I can't even eat properly",
        "parang wala nang kulay ang mundo ko",
        "I miss them so much it hurts to breathe",
        "paulit-ulit kong inaalala ang masasakit na alaala",
        "I feel unwanted and excluded everywhere I go",
        "hindi na ako masaya kahit sa anong gawin ko",
        "I feel like I'm carrying all this sadness alone",
        "ang lungkot ng araw ko, wala akong makausap",
        "I feel rejected and heartbroken right now",
    ],
    "anger": [
        "nagngangalit ako ngayon, para akong sasabog",
        "I am so pissed off right now, I could break something",
        "bwisit na bwisit na talaga ako",
        "I hate you, don't ever talk to me again",
        "nakakainis na nakakainis ka, gusto kitang harapin",
        "galit na galit ako at gusto kong sumigaw",
        "I'm so angry my blood is boiling",
        "putang ina, ang tagal niyong mag-reply",
        "I want to punch someone right now",
        "grabe ang inis ko, kalmado lang ang iba",
        "I'm fuming mad and I can't even explain it",
        "nararamdaman kong umaapaw ang galit ko",
        "sobrang inis ko sa ginawa niyo",
        "I could actually scream at the top of my lungs",
        "nakakagalit talaga ang mga ginagawa nila, walang hiya",
        "I am seriously mad and I don't care who knows it",
        "gustong-gusto kong itapon lahat dahil sobrang galit ako",
        "I'm raging right now, stay away from me",
        "ang init ng ulo ko, ayoko munang kausapin kahit sino",
        "I feel like I'm about to explode in anger",
        "nakakaasar ka at nakakainis yang ugali mo",
        "I am furious and I want them to know it",
        "sakit sa ulo ang mga ginagawa nila, nabuwisit ako",
        "don't test me right now, I am really angry",
    ],
    "suicidal": [
        "I want to kill myself",
        "gusto ko nang mamatay",
        "I have already planned how to end my life",
        "hindi ko na kaya, magpapakamatay na ako",
        "I'm going to take all these pills tonight",
        "wala na akong rason para mabuhay",
        "I've already written my goodbye letters",
        "maghihigpit lang ako ng tali ngayong gabi",
        "I am about to end my life, goodbye",
        "I don't want to wake up anymore",
        "Gumuho na lahat, gusto ko nang tapusin ang lahat",
        "I've been thinking of jumping off the bridge",
        "tapos ko na lahat ng dapat kong gawin, hihinto na ako",
        "I swallowed some pills because I give up",
        "I already bought what I need to end myself",
        "hindi na ako magtatagal sa mundong to",
        "I want to die so the pain stops forever",
        "sa gabing ito, aalis na ako sa mundo",
        "I'm going to end my life, please forgive me",
        "wala nang pag-asa, mamamatay na lang ako",
        "I've decided, wala nang makakapigil sa akin",
        "Ayoko na, lulunukin ko lahat ng gamot",
        "I'm ready to die tonight",
        "tinitignan ko na ang pinakamataas na building dito para tumalon",
    ],
}


def _build_rows():
    rows = []
    for label, phrases in SAMPLES.items():
        for text in phrases:
            rows.append({"text": text, "label": label})
    if any(len(v) != 24 for v in SAMPLES.values()):
        raise SystemExit("Each class must have exactly 24 samples.")
    rng = random.Random(SEED)
    rng.shuffle(rows)
    return rows


def _write_csvs(rows):
    with open(BASE / "sample_for_experts.csv", "w", encoding="utf-8-sig", newline="") as f:
        f.write("sample_id,text,counselor_A_label,counselor_B_label\n")
        for i, r in enumerate(rows, start=1):
            f.write(f"{i},\"{r['text'].replace('\"', '\"\"')}\",,\n")

    with open(BASE / "gold_key.csv", "w", encoding="utf-8-sig", newline="") as f:
        f.write("sample_id,text,gold_label\n")
        for i, r in enumerate(rows, start=1):
            f.write(f"{i},\"{r['text'].replace('\"', '\"\"')}\",{r['label']}\n")


def _write_form(rows):
    label_cols = ("anxiety", "sadness", "neutral", "suicidal", "anger")
    body_rows = "".join(
        "<tr><td class=\"num\">{num}</td><td>{msg}</td>"
        "<td></td><td></td><td></td><td></td><td></td></tr>".format(
            num=i, msg=html.escape(r["text"])
        )
        for i, r in enumerate(rows, start=1)
    )

    doc = (
    f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GAIDA - Expert Validation of Training Data</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; margin: 20px 28px; }}
  h1 {{ font-size: 20px; margin: 0 0 2px; }}
  h2 {{ font-size: 15px; margin: 22px 0 8px; border-bottom: 1px solid #999; padding-bottom: 3px; }}
  p, li {{ font-size: 12px; line-height: 1.5; }}
  .muted {{ color: #555; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  th, td {{ border: 1px solid #bbb; padding: 4px 6px; vertical-align: top; }}
  th {{ background: #eee; font-weight: bold; text-align: left; }}
  tr {{ page-break-inside: avoid; }}
  .num {{ width: 30px; text-align: center; }}
  .msg {{ width: 42%; }}
  .label-col {{ width: {100 / (len(label_cols) + 2):.1f}%; text-align: center; }}
  .sig {{ margin-top: 28px; font-size: 12px; }}
  .sig td {{ border: none; padding: 10px 0; }}
  @media print {{
    body {{ margin: 10mm; }}
    thead {{ display: table-header-group; }}
  }}
</style>
</head>
<body>

<h1>GAIDA - Expert Validation of Training Data</h1>
<p class="muted">AI-based Anxiety Detection System &middot; College Guidance &middot; University of the East</p>

<p><b>Purpose.</b> GAIDA detects anxiety in student text messages using a model trained on labeled
student-like phrases. We ask a licensed mental health professional to independently label this sample
to confirm our dataset is clinically sound and to measure inter-expert agreement.</p>

<p><b>Time required:</b> approximately 10&ndash;15 minutes. <b>How to answer:</b> read each message and put a
check (&radic;) in the box of the ONE label you judge as the closest match.</p>

<h2>Label Definitions (with examples)</h2>
<ul>
  <li><b>anxiety</b> &mdash; nervousness, worry, tension, dread, panic-like feelings, overthinking. <i>e.g. "my heart is racing and I can't calm down"</i></li>
  <li><b>sadness</b> &mdash; low mood, grief, loneliness, emptiness, crying. <i>e.g. "I've been crying all day and I can't stop"</i></li>
  <li><b>neutral</b> &mdash; casual or everyday statements with no significant distress. <i>e.g. "I passed my math exam"</i></li>
  <li><b>suicidal</b> &mdash; death wishes, wanting to end one&rsquo;s life, self-harm &mdash; even when phrased indirectly. <i>e.g. "I want to kill myself"</i></li>
  <li><b>anger</b> &mdash; irritation, frustration, hostility. <i>e.g. "I'm so angry my blood is boiling"</i></li>
</ul>

<h2>Rating Sheet</h2>
<table>
  <thead>
    <tr>
      <th class="num">#</th>
      <th class="msg">Student Message</th>"""
    + "".join(f'      <th class="label-col">{c}</th>' for c in label_cols)
    + f"""
    </tr>
  </thead>
  <tbody>
{body_rows}
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

<p class="muted">For research use only. Responses will be compared anonymously to measure inter-rater agreement.</p>

</body>
</html>
"""
    )
    with open(BASE / "validation_form.html", "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    rows = _build_rows()
    dist = {}
    for r in rows:
        dist[r["label"]] = dist.get(r["label"], 0) + 1
    print("Distribution:", dist, "| total:", len(rows))

    _write_csvs(rows)
    _write_form(rows)
    print("Wrote sample_for_experts.csv, gold_key.csv, validation_form.html")
    print(f"HEADS UP: gold_key.csv is the answer key - do NOT send it to counselors.")


if __name__ == "__main__":
    main()