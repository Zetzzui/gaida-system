import re
from difflib import SequenceMatcher

PHRASE_FUZZY_THRESHOLD = 0.85
TOKEN_FUZZY_THRESHOLD = 0.82
FUZZY_WEIGHT_MULTIPLIER = 0.9

from app.services.crisis_guards import (
    has_fiction_context,
    has_hypothetical_context,
    has_venting_context,
    is_soft_venting_phrase,
    resolve_crisis_level,
)

# ---------------------------------------------------------------------------
# COUNSELOR FIRST AID PROTOCOLS
# ---------------------------------------------------------------------------

COUNSELOR_PROTOCOLS = {
        "low": """
    Respond with warmth and gentle acknowledgment.
    - Validate their feeling without alarming them
    - Normalize what they are experiencing
    - Offer one simple practical suggestion if appropriate
    - End with one open question to keep them talking
    - Do NOT mention the counselor or escalate
    """,
        "moderate": """
    Respond with stronger empathy and grounded support.
    - Validate clearly that what they feel is real and matters
    - Reflect back what they shared to show you heard them
    - Offer one specific coping suggestion relevant to what they described
    - Keep the tone calm and present
    - Do NOT invent grounding techniques involving specific objects or rooms
    - End with one focused question about how they are feeling right now
    """,
        "high": """
    Respond with calm urgency. You are a steady grounding presence.
    - Lead with strong validation — acknowledge the intensity directly
    - Inform them calmly that the counselor has been notified
    - Offer ONE simple immediate action: sit down, breathe slowly, stay where they are
    - Do NOT suggest specific objects, rooms, or actions you cannot verify they have access to
    - Do NOT mix languages mid-sentence — respond in the same language the student used
    - End with one simple present-moment question: "Are you sitting down?" or "Is anyone nearby?"
    """,
        "crisis": """
    Respond with full presence and deep human care.
    - Open with immediate acknowledgment — do not jump to resources first
    - Make them feel heard before anything else
    - Never minimize what they are feeling
    - Provide crisis resources warmly: National Crisis Hotline 1553 (24/7), In Touch (02) 893-7603
    - Encourage them to reach out to someone nearby
    - End with reassurance and presence — not a question
    """,
}
# ---------------------------------------------------------------------------
# CRISIS SAFETY RESOURCES
# ---------------------------------------------------------------------------

CRISIS_RESOURCES = """
Please reach out for immediate help:
- National Crisis Hotline: 1553 (available 24/7)
- In Touch Crisis Line: (02) 893-7603
- School Guidance Office: please visit or call them now
- If in immediate danger, call 911
"""

# ---------------------------------------------------------------------------
# SAFE PHRASES — known frustration phrases that must never trigger crisis
# Checked before anything else — hard override to neutral
# ---------------------------------------------------------------------------

SAFE_PHRASES = [
    "ayoko na mag aral", "ayoko na magaral",
    "ayoko na pumasok", "ayoko na umattend",
    "pagod na ako", "pagod sa pag aaral",
    "pagod mag aral", "tired of studying",
    "tired of school", "don't want to study",
    "dont want to study", "ayoko na ng requirements",
    "pagod na pagod na ako sa school",
    "ayoko na mag trabaho ngayon",
    "i give up on this assignment",
    "i quit studying",
    "i don't want to go to class",
    "ayoko na lumabas",
    "ayoko na kumain",
    "ayoko na sa mga tao",
    "goodbye",
    "good bye",
    "checking lang",
    "testing lang",
    "test lang",
    "kung active ka",
    "active ka ba",
    "active kaba",
    "pasensya na nag check lang",
]

def _is_safe_phrase(text: str) -> bool:
    txt = text.lower().strip()
    return any(safe in txt for safe in SAFE_PHRASES)

# ---------------------------------------------------------------------------
# SUICIDAL KEYWORDS — deduplicated, ordered by specificity
# ---------------------------------------------------------------------------

KEYWORDS = {
    "suicidal": [
        # Direct English
        ("i want to die", 3.5),
        ("kill myself", 3.5),
        ("end my life", 3.5),
        ("take my own life", 3.5),
        ("suicide", 3.5),
        ("suicidal", 3.5),
        ("i want to kill myself", 3.5),

        # Indirect English
        ("no point of living", 4.0),
        ("point of living anymore", 4.0),
        ("no point in living", 4.0),
        ("no point to life", 3.5),
        ("what's the point of living", 4.0),
        ("no reason to keep going", 3.5),
        ("no reason to continue", 3.5),
        ("why bother living", 3.5),
        ("end it all", 4.0),
        ("i should end it", 4.0),
        ("let it all end", 4.0),
        ("make it all stop", 3.5),
        ("want it all to end", 4.0),
        ("end everything", 3.5),
        ("done with life", 4.0),
        ("i just want it to stop", 3.5),
        ("no point in trying anymore", 3.0),
        ("tired of it all", 3.0),
        ("make everything stop", 3.0),
        ("let it crumble", 3.0),
        ("there is no point anymore", 3.5),
        ("there's no point anymore", 3.5),
        ("i can't go on", 3.5),
        ("i don't want to exist", 3.5),
        ("i want to disappear forever", 3.5),
        ("better off dead", 3.5),

        # Direct Filipino
        ("gusto ko na mamatay", 3.5),
        ("ayoko na mabuhay", 3.5),
        ("ayoko nang mabuhay", 3.5),
        ("magpapakamatay", 3.5),
        ("papatayin ko sarili ko", 3.5),
        ("tapusin ko na ang buhay ko", 3.5),
        ("tapusin ko na ang lahat", 3.0),
        ("sana wala na lang ako", 3.5),
        ("sana hindi na ako nagising", 3.5),
        ("pagod na ako mabuhay", 3.5),
        ("wala na akong dahilan para mabuhay", 3.5),
        ("wala na akong dahilan", 3.0),
        ("gusto ko nang mawala sa mundo", 3.5),
        ("gusto ko nang mawala sa lahat", 3.5),
        ("papatayin ko na ang sarili ko", 3.5),
        ("papatayin ko ang sarili ko", 3.5),
        ("patayin ko na ang sarili ko", 3.5),
        ("patayin ko ang sarili ko", 3.5),
        ("nag isip ng kamatayan", 3.5),
        ("nag iisip ng kamatayan", 3.5),
        ("nagiisip ng kamatayan", 3.5),
        ("iniisip ko ang kamatayan", 3.5),

        # Indirect Filipino
        ("bakit pa mabuhay", 4.0),
        ("wala nang saysay mabuhay", 4.0),
        ("para saan pa mabuhay", 4.0),
        ("wala na kong dahilan magpatuloy", 4.0),
        ("suko na ako sa buhay", 4.0),
        ("wala na kong pakialam sa buhay", 3.5),
        ("di ko na kaya ang buhay", 4.0),
        ("para saan pa ako", 3.5),
        ("bakit pa ako nagtatagal", 3.5),
        ("wala nang dahilan magpatuloy", 4.0),
        ("hindi ko alam kung may dahilan pa", 3.5),
        ("huling liham", 4.0),
        ("nagpaalam na ako", 3.5),
        ("wish i was never born", 3.5),
        ("never born", 3.0),
    ],
}


def _normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    txt = text.lower()
    txt = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", txt)
    txt = re.sub(r"[^\w\s']+", ' ', txt)
    txt = re.sub(r'(.)\1{2,}', r'\1', txt)
    txt = re.sub(r"\s+", ' ', txt).strip()
    return txt


def _tokenize(text: str):
    return re.findall(r"\w+'?\w*|\w+", text)


# ---------------------------------------------------------------------------
# NEGATIVE CONTEXT PATTERNS
# ---------------------------------------------------------------------------

NEGATIVE_CONTEXTS = [
    (re.compile(r"\b(used to|before|last time|yesterday|last week|last month|dati|noon|noong)\b"), 0.3),
    (re.compile(r"\b(but (im|i'm|i am) (better|okay|fine|good)|better now|okay na|ayos na)\b"), 0.2),
    (re.compile(r"\b(not|no longer|never|wala|hindi|hindi na|di na|wala na)\b"), 0.4),
    (re.compile(r"\b(dying of (laughter|boredom|cuteness)|dead (tired|serious)|i('m| am) dead|lol|haha|hehe|joke|kidding|char)\b"), 0.1),
    (re.compile(r"\b(killed it|crushing it|nailed it|aced it|passed|pumasa|pumasa ako)\b"), 0.1),
    (re.compile(r"\b(my (friend|classmate|roommate|sister|brother|mom|dad|kaibigan|kaklase))\b"), 0.3),
    (re.compile(r"^(do you|are you|can you|have you|did you|would you|will you|should i|could you)\b"), 0.2),
    (re.compile(r"\b(if (i|you) (were|was|feel|felt|am|have|had|get|got)|hypothetically|parang kung|what if)\b"), 0.3),
    (re.compile(r"\b(movie|film|show|series|character|scene|story|novel|book|anime|episode|fiction|sa pelikula|sa kwento)\b"), 0.1),
]


def _get_negative_context_multiplier(txt: str) -> float:
    multiplier = 1.0
    for pattern, reduction in NEGATIVE_CONTEXTS:
        if pattern.search(txt):
            multiplier = min(multiplier, reduction)
    return multiplier


def _context_override_for_suicidal(text: str):
    """When ML flags suicidal language but no explicit self-harm keyword matched
    (the rule hard-path already caught those), decide whether context actually
    makes this fiction/venting rather than a real crisis.

    Explicit self-referential phrases are never downgraded here — they would
    have been caught by the hard path already.
    """
    if has_fiction_context(text):
        return {"intent": "anger", "confidence": 0.55}
    if has_venting_context(text):
        return {"intent": "stress", "confidence": 0.60}
    if has_hypothetical_context(text):
        return {"intent": "suicidal", "confidence": 0.88}
    return None


def _windowed_fuzzy(kw: str, txt: str) -> bool:
    """Match a multiword keyword against sliding windows of the text so a long
    message can't dilute the similarity score below the threshold."""
    kw_tokens = kw.split()
    n = len(kw_tokens)
    if n == 0:
        return False
    txt_tokens = _tokenize(txt)
    for i in range(len(txt_tokens) - n + 1):
        window = " ".join(txt_tokens[i:i + n])
        if SequenceMatcher(None, kw, window).ratio() >= PHRASE_FUZZY_THRESHOLD:
            return True
    return False


def _match_suicidal_keyword(txt: str, tokens: set):
    """Return the matched suicidal keyword, preferring an explicit (hard)
    self-harm phrase over a colloquial give-up phrase when both are present."""
    found_soft = None
    for kw, _weight in KEYWORDS.get("suicidal", []):
        if ' ' in kw:
            if re.search(r"\b" + re.escape(kw) + r"\b", txt) or \
               _windowed_fuzzy(kw, txt):
                if not is_soft_venting_phrase(kw):
                    return kw
                if found_soft is None:
                    found_soft = kw
        else:
            if kw in tokens:
                if not is_soft_venting_phrase(kw):
                    return kw
                if found_soft is None:
                    found_soft = kw
                continue
            for t in tokens:
                if SequenceMatcher(None, kw, t).ratio() >= TOKEN_FUZZY_THRESHOLD:
                    if not is_soft_venting_phrase(kw):
                        return kw
                    if found_soft is None:
                        found_soft = kw
                    break
    return found_soft


def detect_intent_and_level(text: str) -> dict:
    txt = _normalize_text(text)
    tokens = set(_tokenize(txt))

    # ── Step 1: Suicidal keyword check — run BEFORE the safe-phrase mask so a
    #    real crisis is never hidden (e.g. "ayoko na mag aral... gusto ko na
    #    mamatay" must still be caught). Context guards below tune the level. ──
    crisis_kw = _match_suicidal_keyword(txt, tokens)

    if crisis_kw:
        verdict = resolve_crisis_level([crisis_kw], txt)
        return _build_result(verdict["intent"], verdict["confidence"])

    # ── Step 3: Safe phrase check — masks venting, never masks a real crisis ──
    if _is_safe_phrase(txt):
        return _build_result("neutral", 0.3)

    # ── Step 2: ML classifier ─────────────────────────────────────────────────
    try:
        from app.services.ml_classifier import classify_intent
        ml_result = classify_intent(text)
        ml_intent = ml_result["intent"]
        ml_confidence = ml_result["confidence"]

        if ml_intent == "neutral":
            return _build_result("neutral", 0.3)

        if ml_intent == "uncertain":
            raise Exception("ML uncertain — trying rule_intent fallback")

        # Guard ML-reported suicidal when no explicit self-harm keyword matched
        # (rule path already checks explicit keywords). If ML votes suicidal but
        # the message is fiction/venting, downgrade instead of alerting.
        if ml_intent == "suicidal":
            override = _context_override_for_suicidal(text)
            if override:
                return _build_result(override["intent"], override["confidence"])

        neg_multiplier = _get_negative_context_multiplier(txt)
        ml_confidence = round(ml_confidence * neg_multiplier, 3)
        scaled_confidence = 0.3 + 0.7 * ml_confidence
        scaled_confidence = round(min(0.98, scaled_confidence), 3)

        return _build_result(ml_intent, scaled_confidence)

    except Exception:
        pass

    # ── Step 4: rule_intent.py fallback ──────────────────────────────────────
    try:
        from app.services.rule_intent import analyze_with_rules
        rule_result = analyze_with_rules(text)

        rule_intent = rule_result.get("intent", "neutral")
        rule_confidence = rule_result.get("confidence", 0.3)
        rule_intensity = rule_result.get("intensity", 0.0)
        escalate = rule_result.get("escalate", False)

        # rule_intent already applied the same context guards when it detected
        # suicidal language — trust its verdict instead of re-scaling.
        if rule_result.get("guarded"):
            return _build_result(rule_result["intent"], rule_result["confidence"])

        if escalate or rule_intent == "suicidal":
            return _build_result("suicidal", 0.99)

        if rule_intent == "neutral":
            return _build_result("neutral", 0.3)

        neg_multiplier = _get_negative_context_multiplier(txt)
        rule_confidence = round(rule_confidence * neg_multiplier, 3)

        if rule_intensity > 0.5:
            rule_confidence = min(0.98, rule_confidence + (rule_intensity * 0.1))
            rule_confidence = round(rule_confidence, 3)

        scaled_confidence = 0.3 + 0.7 * rule_confidence
        scaled_confidence = round(min(0.98, scaled_confidence), 3)

        return _build_result(rule_intent, scaled_confidence)

    except Exception:
        pass

    return _build_result("neutral", 0.3)


def _build_result(intent: str, confidence: float, post_crisis: bool = False) -> dict:
    # Anger is a valid emotion but an angry rant is not inherently an anxiety
    # crisis — cap its severity so it can never reach "high"/alert level.
    if intent == "anger":
        confidence = min(confidence, 0.55)

    if confidence >= 0.99:
        return {
            "intent": intent,
            "confidence": confidence,
            "anxiety_level": "Crisis",
            "severity": "Crisis",
            "counselor_protocol": COUNSELOR_PROTOCOLS["crisis"],
            "crisis_resources": CRISIS_RESOURCES,
            "anxiety_score": 5,
        }

    if confidence >= 0.75:
        anxiety_level = "high"
        severity = "High"
        anxiety_score = 5
        protocol = COUNSELOR_PROTOCOLS["high"]
    elif confidence >= 0.60:
        anxiety_level = "moderate"
        severity = "Moderate"
        anxiety_score = 3
        protocol = COUNSELOR_PROTOCOLS["moderate"]
    elif confidence >= 0.45:
        anxiety_level = "low"
        severity = "Low"
        anxiety_score = 1
        protocol = COUNSELOR_PROTOCOLS["low"]
    else:
        anxiety_level = None
        anxiety_score = 0
        protocol = None

        if post_crisis:
            severity = "Low"
            anxiety_level = "low"
            anxiety_score = 1
            protocol = COUNSELOR_PROTOCOLS["low"]
        else:
            severity = "Normal"

    return {
        "intent": intent,
        "confidence": confidence,
        "anxiety_level": anxiety_level,
        "severity": severity,
        "counselor_protocol": protocol,
        "crisis_resources": None,
        "anxiety_score": anxiety_score,
    }