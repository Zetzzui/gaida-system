import re
from typing import Dict, List
from difflib import SequenceMatcher

# Fuzzy match thresholds
PHRASE_FUZZY_THRESHOLD = 0.72
TOKEN_FUZZY_THRESHOLD = 0.84

from app.services.crisis_guards import (
    has_venting_context,
    resolve_crisis_level,
)

STOPWORDS = {
    "ang", "ng", "sa", "ako", "ikaw", "siya",
    "ko", "mo", "niya", "na", "pa", "lang",
    "yung", "ito", "yan", "din", "rin", "mga",
    "at", "ay", "kung", "hindi", "naman", "talaga"
}

# Each keyword maps to a weight (signal strength).
# Higher weight = stronger indicator for that intent.
KEYWORDS: Dict[str, List[tuple]] = {

    "suicidal": [
        # English
        ("no point of living", 4.0),
        ("point of living anymore", 4.0),
        ("no point in living", 4.0),
        ("don't know if there's a point", 3.5),
        ("is there a point anymore", 3.5),
        ("point of life anymore", 3.5),
        ("no point to life", 3.5),
        ("no reason to keep going", 3.5),
        ("no reason to continue", 3.5),
        ("why keep going", 3.0),
        ("why bother living", 3.5),
        ("what's the point of living", 4.0),
        ("bakit pa mabuhay", 4.0),
        ("wala nang saysay mabuhay", 4.0),
        ("hindi ko alam kung may dahilan pa", 3.5),
        ("wala na kong dahilan magpatuloy", 4.0),
        ("para saan pa mabuhay", 4.0),

        # Indirect "end it" expressions
        ("end it all", 4.0),
        ("i should end it", 4.0),
        ("let it all end", 4.0),
        ("make it all stop", 3.5),
        ("want it all to end", 4.0),
        ("end everything", 3.5),
        ("i'm done with everything", 3.5),
        ("done with life", 4.0),
        ("i just want it to stop", 3.5),
        ("i can't do this anymore", 3.0),
        ("i give up on everything", 3.5),
        ("no point in trying anymore", 3.0),

        # Filipino indirect expressions
        ("suko na ako sa buhay", 4.0),
        ("wala na kong pakialam sa buhay", 3.5),
        ("ayoko na ng lahat", 3.0),
        ("di ko na kaya ang buhay", 4.0),
        ("para saan pa ako", 3.5),
        ("bakit pa ako nagtatagal", 3.5),
        ("wala nang dahilan magpatuloy", 4.0),
        ("end it all", 4.0),
        ("i should end it", 4.0),
        ("let it all end", 4.0),
        ("make it all stop", 3.5),
        ("want it all to end", 4.0),
        ("end everything", 3.5),
        ("tired of it all", 3.0),
        ("can't do this anymore", 3.0),
        ("i want to die", 4.0),
        ("i want to kill myself", 4.0),
        ("kill myself", 4.0),
        ("kill my self", 4.0),
        ("killing myself", 4.0),
        ("killed myself", 4.0),
        ("wanna kill myself", 4.0),
        ("gonna kill myself", 4.0),
        ("going to kill myself", 4.0),
        ("planning to kill myself", 4.0),
        ("thinking of killing myself", 4.0),
        ("im gonna kill myself", 4.0),
        ("i will kill myself", 4.0),
        ("kms", 4.0),
        ("i will kms", 4.0),
        ("wanna kms", 4.0),
        ("off myself", 4.0),
        ("off my self", 4.0),
        ("end myself", 4.0),
        ("end my self", 4.0),
        ("end my own life", 4.0),
        ("take my life", 4.0),
        ("hurt myself", 4.0),
        ("harm myself", 4.0),
        ("cut myself", 4.0),
        ("want to hurt myself", 4.0),
        ("want to harm myself", 4.0),
        ("let me just die", 4.0),
        ("let me die", 4.0),
        ("just let me die", 4.0),
        ("i should just die", 4.0),
        ("wish i was dead", 3.5),
        ("wish i were dead", 3.5),
        ("feel like dying", 3.5),
        ("feel like ending everything", 3.5),
        ("dying inside", 3.5),
        ("end my life", 4.0),
        ("take my own life", 4.0),
        ("suicide", 4.0),
        ("suicidal", 4.0),
        ("i don't want to live", 3.8),
        ("i don't want to exist", 3.8),
        ("no reason to live", 3.8),
        ("no reason to stay alive", 3.8),
        ("thinking about suicide", 3.8),
        ("planning to end it", 3.8),
        ("want to disappear forever", 3.5),
        ("nobody would miss me", 3.5),
        ("better off dead", 3.5),
        ("i want to hurt myself", 3.5),
        ("i want to harm myself", 3.5),
        ("feel like ending everything", 3.5),
        ("don't want to wake up", 3.5),
        # Filipino / Taglish
        ("gusto ko na mamatay", 4.0),
        ("ayoko na mabuhay", 4.0),
        ("magpapakamatay", 4.0),
        ("magpapakamatay na ako", 4.0),
        ("tapusin ko na buhay ko", 4.0),
        ("tapusin ko na lahat", 4.0),
        ("tapusin ko na ang buhay ko", 4.0),
        ("tapusin ko na ang lahat", 4.0),
        ("wawakasan ko na ang buhay ko", 4.0),
        ("tatapusin ko na ang lahat", 4.0),
        ("tatapusin ko na ang buhay ko", 4.0),
        ("mawala na lang ako", 3.5),
        ("sana mawala na ako", 3.5),
        ("sana hindi na ako gumising", 3.8),
        ("mas mabuti pang mawala na ako", 3.5),
        ("wala nang dahilan para mabuhay", 3.8),
        ("ayoko na magising", 3.8),
        ("gusto ko nang mawala", 3.8),
        ("sana di na lang ako ipinanganak", 3.5),
        ("pabigat lang ako", 3.5),
        ("wala na akong silbi", 3.5),
        ("mas tahimik kung wala ako", 3.5),
        ("gusto ko na sumuko sa buhay", 3.5),
        ("pagod na ako sa existence", 3.5),
        ("ayoko na sa lahat", 3.0),
        ("parang wala nang saysay mabuhay", 3.8),
        ("papatayin ko na ang sarili ko", 4.0),
        ("papatayin ko ang sarili ko", 4.0),
        ("patayin ko na ang sarili ko", 4.0),
        ("patayin ko ang sarili ko", 4.0),
        ("nag isip ng kamatayan", 3.8),
        ("nag iisip ng kamatayan", 3.8),
        ("nagiisip ng kamatayan", 3.8),
        ("iniisip ko ang kamatayan", 3.8),
        ("huling liham", 4.0),
        ("nagpaalam na ako", 3.5),
        ("wish i was never born", 3.5),
        ("never born", 3.0),
    ],

    "anxiety": [
        # English
        ("anxiety", 2.0),
        ("anxious", 2.0),
        ("panic attack", 2.5),
        ("panic", 1.8),
        ("nervous", 1.5),
        ("worried", 1.5),
        ("overthinking", 2.0),
        ("overthink", 1.8),
        ("restless", 1.5),
        ("uneasy", 1.5),
        ("on edge", 1.8),
        ("heart racing", 2.0),
        ("can't breathe", 1.8),
        ("shaking from fear", 1.8),
        ("scared of failing", 1.8),
        ("constantly worried", 2.0),
        ("social anxiety", 2.2),
        ("fear of judgment", 1.8),
        ("freeze up", 1.5),
        ("impending doom", 2.0),
        # Filipino / Taglish
        ("kinakabahan", 2.0),
        ("kabado", 1.8),
        ("natatakot", 1.5),
        ("natataranta", 1.8),
        ("balisa", 1.8),
        ("nag aalala", 1.8),
        ("hindi mapanatag", 1.8),
        ("hindi mapakali", 1.8),
        ("takot mabigo", 1.8),
        ("hindi makatulog sa pagaalala", 2.0),
        ("parang may mangyayaring masama", 1.8),
        ("nanginginig sa kaba", 2.0),
        ("nahihirapan huminga pag stressed", 2.0),
    ],

    "sadness": [
        # English
        ("sad", 1.5),
        ("sadness", 1.5),
        ("depressed", 2.0),
        ("depression", 2.0),
        ("hopeless", 2.2),
        ("hopelessness", 2.2),
        ("lonely", 1.8),
        ("alone", 1.5),
        ("empty inside", 2.2),
        ("worthless", 2.2),
        ("burden to everyone", 2.5),
        ("nobody cares", 2.0),
        ("nobody understands", 2.0),
        ("crying for no reason", 2.0),
        ("lost interest", 2.0),
        ("no motivation", 1.8),
        ("feel broken", 2.2),
        ("feel abandoned", 2.0),
        ("feel ignored", 1.8),
        ("feel unwanted", 2.0),
        # Filipino / Taglish
        ("malungkot", 2.0),
        ("lungkot", 1.8),
        ("wala nang gana", 2.2),
        ("wala na akong gana", 2.2),
        ("walang halaga", 2.2),
        ("parang wala akong silbi", 2.2),
        ("di ko na kaya", 2.0),
        ("ayoko na umalis sa kwarto", 2.0),
        ("parang wala akong halaga", 2.2),
        ("hindi mahanap motivation", 1.8),
        ("iyak gabi gabi", 2.2),
        ("parang ako lang palagi", 2.0),
    ],

    "stress": [
        # English
        ("stressed", 2.0),
        ("stress", 1.8),
        ("overwhelmed", 2.0),
        ("pressure", 1.8),
        ("burnout", 2.2),
        ("burned out", 2.2),
        ("burnt out", 2.2),
        ("drained", 1.8),
        ("exhausted", 1.8),
        ("too many deadlines", 2.2),
        ("can't cope", 2.0),
        ("workload is killing me", 2.5),
        ("no time to sleep", 2.0),
        ("no time to rest", 2.0),
        ("too much work", 2.0),
        ("stretched too thin", 2.0),
        ("drowning in tasks", 2.2),
        ("can't manage", 1.8),
        ("academic pressure", 2.0),
        ("financial stress", 2.0),
        # Filipino / Taglish
        ("pagod", 1.8),
        ("pagod na pagod", 2.2),
        ("napapagod", 1.8),
        ("nakakapagod", 1.8),
        ("naiistress", 2.0),
        ("hindi ko na kaya ang pressure", 2.5),
        ("ubos na energy", 2.2),
        ("wala nang oras matulog", 2.2),
        ("sobrang daming requirements", 2.0),
        ("hindi matapos gawain", 1.8),
        ("andaming expectations", 1.8),
        ("sabay sabay problema", 2.0),
    ],
}

INTENSIFIERS = {
    # Filipino
    "sobrang", "sobra", "grabe", "super", "napaka", "talagang",
    # English
    "extremely", "very", "too", "so much", "unbearable", "terrible",
    "completely", "absolutely", "totally"
}

ESCALATION_MESSAGE = (
    "You are not alone. If you or someone you know is in danger, "
    "please contact local emergency services or a trusted person immediately. "
    "You can also reach a crisis line or mental health professional for support."
)


def normalize_text(text: str) -> str:
    text = text.lower()
    # collapse repeated characters (e.g., "soooo" -> "so")
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    # normalize unicode quotes
    text = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", text)
    # strip excessive punctuation but keep apostrophes
    text = re.sub(r"[^\w\s']", " ", text)
    # merge look-alike word splits so "kill my self" matches "kill myself"
    text = re.sub(r"\bmy self\b", "myself", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def remove_stopwords(text: str) -> str:
    tokens = text.split()
    return " ".join(t for t in tokens if t not in STOPWORDS)


def _phrase_match(keyword: str, text: str) -> bool:
    if re.search(r"\b" + re.escape(keyword) + r"\b", text):
        return True
    return SequenceMatcher(None, keyword, text).ratio() >= PHRASE_FUZZY_THRESHOLD


def _token_match(keyword: str, tokens: set) -> bool:
    if keyword in tokens:
        return True
    return any(
        SequenceMatcher(None, keyword, t).ratio() >= TOKEN_FUZZY_THRESHOLD
        for t in tokens
    )


def _count_intensifiers(text: str) -> int:
    return sum(1 for i in INTENSIFIERS if i in text)


def analyze_with_rules(user_input: str) -> Dict[str, object]:
    raw_text = user_input or ""
    text = normalize_text(raw_text)
    clean_text = remove_stopwords(text)
    tokens = set(clean_text.split())

    scores: Dict[str, float] = {label: 0.0 for label in KEYWORDS}
    matched: Dict[str, List[str]] = {label: [] for label in KEYWORDS}

    for label, kw_list in KEYWORDS.items():
        for kw, weight in kw_list:
            hit = False
            tag = kw

            if " " in kw:
                if _phrase_match(kw, clean_text):
                    hit = True
                elif _phrase_match(kw, text):
                    hit = True
                    tag = kw + " (fuzzy)"
            else:
                if _token_match(kw, tokens):
                    hit = True

            if hit:
                scores[label] += weight
                matched[label].append(tag)

    # Hard escalation: suicidal always wins if any keyword matched
    if matched["suicidal"]:
        verdict = resolve_crisis_level(matched["suicidal"], text)
        return {
            "intent": verdict["intent"],
            "confidence": verdict["confidence"],
            "intensity": 1.0 if verdict["intent"] == "suicidal" else 0.5,
            "matched_keywords": {"suicidal": matched["suicidal"]},
            "escalate": verdict["intent"] == "suicidal",
            "guarded": True,
            "escalation_message": ESCALATION_MESSAGE if verdict["intent"] == "suicidal" else None,
        }

    total_score = sum(scores.values())

    if total_score == 0.0:
        return {
            "intent": "neutral",
            "confidence": 0.5,
            "intensity": 0.0,
            "matched_keywords": {},
        }

    best_label = max(scores, key=scores.get)
    best_score = scores[best_label]

    # Confidence: share of total weighted score belonging to best label
    confidence = round(best_score / total_score, 3)

    # Intensity: normalized score boosted by intensifier count
    intensifier_boost = _count_intensifiers(text) * 0.15
    raw_intensity = (best_score / 10.0) + intensifier_boost
    intensity = round(min(1.0, raw_intensity), 3)

    return {
        "intent": best_label,
        "confidence": confidence,
        "intensity": intensity,
        "matched_keywords": {best_label: matched[best_label]},
    }