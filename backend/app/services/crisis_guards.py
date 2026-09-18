"""
crisis_guards.py
----------------
Context guards that decide whether a matched suicidal keyword is REAL risk or is
being diluted by surrounding context. Used by both rule_intent.py (rule fallback)
and virtual_agent.py (hard crisis path) so the whole pipeline agrees.

Guards:
    1. SOFT_VENTING_PHRASES  — colloquial "I give up" phrases. These are only
       treated as suicidal when NO school/work context surrounds them. With
       school/work context they are venting → reclassified as stress.
    2. FICTION_CONTEXT       — essays, movies, songs, stories, poems. The death
       talk is about content, not the speaker → tone down, no auto-alert.
    3. HYPOTHETICAL_CONTEXT  — hedged/conditional musing ("what if", "kung").
       Still concerning, but not yet an active plan → keep alert at HIGH.
"""

import re

# Colloquial "give up" phrases. Normalized keys; compare via is_soft_venting_phrase.
SOFT_VENTING_PHRASES = {
    "i can't do this anymore",
    "cant do this anymore",
    "i give up on everything",
    "i'm done with everything",
    "im done with everything",
    "i just want it to stop",
    "no point in trying anymore",
    "tired of it all",
    "make everything stop",
    "make it all stop",
    "ayoko na ng lahat",
    "ayoko na sa lahat",
    "nagpaalam na ako",
}

_APOS_TRANSLATE = str.maketrans({"’": "'", "‘": "'"})


def is_soft_venting_phrase(keyword: str) -> bool:
    """True if the matched keyword is a colloquial give-up phrase (not an
    explicit self-harm statement). Fuzzy-match tags are stripped first."""
    norm = keyword.lower().replace(" (fuzzy)", "").translate(_APOS_TRANSLATE).strip()
    return norm in SOFT_VENTING_PHRASES


TONING_CONTEXTS = (
    "school", "classes", "class", "exams", "exam", "tests", "test", "quiz",
    "finals", "thesis", "assignments", "assignment", "projects", "project",
    "homework", "requirements", "deadlines", "deadline", "grades", "grade",
    "professor", "teacher", "subjects", "subject", "classmate", "classmates",
    "aral", "pag aaral", "mag aral", "magaral", "pumasok", "pasok", "studying",
    "studies", "study", "semester", "sem", "curriculum", "syllabus",
    "recitation", "plates", "defense", "groupwork", "activity", "activities",
    "utang", "tuition", "work", "job", "workload", "overtime", "shift", "boss",
    "client", "meeting",
)

TONING_CONTEXT_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in TONING_CONTEXTS) + r")\b",
    re.IGNORECASE,
)


def has_venting_context(text: str) -> bool:
    """True when the message is clearly about school/work (a known FP vector
    for colloquial give-up phrases)."""
    return bool(TONING_CONTEXT_RE.search(text or ""))


FICTION_CONTEXTS = (
    "movie", "film", "show", "series", "episode", "character", "scene", "story",
    "novel", "book", "anime", "manga", "fiction", "fantasy", "song", "lyrics",
    "lyric", "poem", "poetry", "essay", "quote", "kwento", "pelikula",
)

FICTION_CONTEXT_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in FICTION_CONTEXTS) + r")\b",
    re.IGNORECASE,
)


def has_fiction_context(text: str) -> bool:
    """True when the message is about media/creative content rather than the
    speaker's own life (essay, movie, story, song...)."""
    return bool(FICTION_CONTEXT_RE.search(text or ""))


HYPOTHETICAL_CONTEXTS = (
    "what if", "if i", "hypothetically", "suppose", "supposedly", "imagine",
    "if someone", "if you", "kunwari", "parang", "kung",
)

HYPOTHETICAL_CONTEXT_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in HYPOTHETICAL_CONTEXTS) + r")\b",
    re.IGNORECASE,
)


def has_hypothetical_context(text: str) -> bool:
    """True when the death-talk is hedged/conditional. Risk is still real, so
    callers should keep the alert but avoid the full crisis protocol."""
    return bool(HYPOTHETICAL_CONTEXT_RE.search(text or ""))


def resolve_crisis_level(matched_keywords, text: str) -> dict:
    """Decide the crisis verdict from the matched suicidal keywords + message
    context. This is the ONE place that converts a suicidal-string match into a
    0.30–0.99 verdict + intent, shared by the hard path and the rule fallback.

    Order of precedence (safety first):
      1. explicit-self-harm keyword → full crisis
      2. soft give-up phrase + venting context → stress (false-positive guard)
      3. fiction context → angry fiction (no alert; low risk)
      4. hypothetical/hedged, or any give-up phrase with no vent → MODERATE alert
      5. explicit keyword in hypothetical → HIGH (still real, but not plan)
    """
    text = text or ""
    if any(not is_soft_venting_phrase(k) for k in matched_keywords):
        if has_hypothetical_context(text):
            return {"intent": "suicidal", "confidence": 0.88}
        return {"intent": "suicidal", "confidence": 0.99}

    if has_venting_context(text):
        return {"intent": "stress", "confidence": 0.60}

    if has_fiction_context(text):
        return {"intent": "anger", "confidence": 0.55}

    if has_hypothetical_context(text):
        return {"intent": "suicidal", "confidence": 0.88}

    return {"intent": "suicidal", "confidence": 0.99}