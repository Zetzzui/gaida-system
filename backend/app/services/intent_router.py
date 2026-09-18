from typing import Dict, Any
import logging
from app.services.session_manager import get_session, start_session, record_interaction
from app.services.virtual_agent import detect_intent_and_level, _build_result
from app.services.gpt_agent import generate_response_with_gpt, stream_gpt_response
from app.api.counselor import process_alert

logger = logging.getLogger(__name__)

HISTORY_WEIGHT = 0.7
CURRENT_WEIGHT = 0.3
REPETITION_BOOST = 1.3

CALMING_KEYWORDS = [
    "salamat", "thank you", "thanks", "walang anuman",
    "wala kang anuman", "sige", "sige salamat",
    "take care", "okay sige", "sige po",
    "maraming salamat", "pasensya na",
    "better", "okay", "ok", "fine", "calm", "good", "thanks", "thank you",
    "relieved", "relaxed", "happy", "magaan na", "okay na", "ayos na",
    "mas okay na", "feel better", "feeling better", "nakakagaan",
    "panatag na", "hindi na", "wala na", "okay na ko", "okay na ako",
    "want to continue", "continue this conversation", "keep talking",
    "more in the future", "hope we can", "looking forward",
    "i want to continue", "i want this to continue",
]

URGENT_PHYSICAL_KEYWORDS = [
    "cant breathe", "can't breathe", "cannot breathe",
    "chest is tight", "tight chest", "chest tightness", "chest pain",
    "shaking uncontrollably", "trembling uncontrollably", "nanginginig na grabe",
    "hyperventilating", "hyperventilation",
    "panic attack", "panicattack",
    "cant control my breathing", "cant control breathing",
    "palpitations", "heart racing",
    "sikip sa puso", "hirap huminga",
    "di makahininga",
]


def _detect_calming(text: str) -> bool:
    txt = text.lower()
    return any(kw in txt for kw in CALMING_KEYWORDS)


def _detect_urgent(text: str) -> bool:
    txt = text.lower()
    return any(kw in txt for kw in URGENT_PHYSICAL_KEYWORDS)

def _scaled_boost(raw_confidence: float, base_multiplier: float, threshold: float = 0.5) -> float:
    """Scales the boost so confidence just above threshold gets minimal boost,
    while confidence well above threshold gets close to the full multiplier."""
    if raw_confidence <= threshold:
        return raw_confidence
    excess = (raw_confidence - threshold) / (1.0 - threshold)
    scaled_multiplier = 1.0 + (base_multiplier - 1.0) * excess
    return min(0.98, raw_confidence * scaled_multiplier)


def _prepare_turn(user_message: str, session_id: str | None = None, user_id: str | None = None, vent_mode: bool = False) -> Dict[str, Any]:
    """Steps 1–6 of a chat turn: session handling, detection, confidence
    running, severity mapping, acoustic fusion, counselor check.

    Shared by the sync path (analyze_intent) and the streaming path
    (stream_analyze_intent) so both behave identically.
    """
    # --- Step 1: Ensure session exists ---
    if session_id and get_session(session_id):
        session = get_session(session_id)
    else:
        session_id = start_session(user_id, session_id=session_id)
        session = get_session(session_id)

    # --- Step 2: Detect intent (always — even in vent mode for safety) ---
    detection = detect_intent_and_level(user_message)
    detected_intent = detection["intent"]
    raw_confidence = detection["confidence"]
    crisis_resources = detection["crisis_resources"]

    if vent_mode and (detected_intent == "suicidal" or raw_confidence >= 0.99):
        logger.warning("VENT MODE OVERRIDE: crisis detected in vent session %s", session_id)

    is_venting = vent_mode and detected_intent != "suicidal" and raw_confidence < 0.99

    if is_venting:
        # VENT MODE: track analysis silently, respond with listening prompt only.
        intent = detected_intent
        running_confidence = raw_confidence

        final_detection = _build_result(detected_intent, raw_confidence)
        severity = final_detection["severity"]
        anxiety_level = "venting"
        anxiety_score = final_detection["anxiety_score"]

        session.setdefault("meta", {})
        session["meta"]["running_confidence"] = running_confidence
        session["meta"]["running_intent"] = intent

        return {
            "session": session,
            "session_id": session_id,
            "intent": intent,
            "running_confidence": running_confidence,
            "anxiety_level": anxiety_level,
            "severity": severity,
            "anxiety_score": anxiety_score,
            "counselor_protocol": None,
            "crisis_resources": crisis_resources,
            "is_venting": is_venting,
            "counselor_active": False,
        }

    # --- Normal path: crisis bypass / running confidence / priority ---
    intent = detected_intent

    if intent == "suicidal" or raw_confidence >= 0.99:
        running_confidence = 0.99
        if "meta" not in session:
            session["meta"] = {}
        session["meta"]["running_confidence"] = running_confidence
        session["meta"]["running_intent"] = "suicidal"
        session["meta"]["post_crisis"] = True
        post_crisis = True
    else:
        previous_confidence = session.get("meta", {}).get("running_confidence", 0.3)
        previous_intent = session.get("meta", {}).get("running_intent", "neutral")
        post_crisis = session.get("meta", {}).get("post_crisis", False)

        # --- Step 4: Calming signals ---
        if _detect_calming(user_message):
            if post_crisis:
                running_confidence = (previous_confidence * 0.5) + (0.3 * 0.5)
            else:
                running_confidence = (previous_confidence * 0.4) + (0.3 * 0.6)
            running_confidence = max(0.3, round(running_confidence, 3))
        else:
            boosted_raw = raw_confidence
            if (
                intent == previous_intent
                and intent not in ("neutral", "academic")
                and raw_confidence > 0.5
            ):
                boosted_raw = _scaled_boost(raw_confidence, REPETITION_BOOST)

            RELATED_INTENTS = {
                "anxiety":    ("stress", "sadness", "academic"),
                "sadness":    ("anxiety", "loneliness", "stress"),
                "stress":     ("anxiety", "academic", "sadness"),
                "academic":   ("anxiety", "stress"),
                "loneliness": ("sadness", "anxiety"),
                "anger":      ("stress", "sadness"),
            }
            related = RELATED_INTENTS.get(intent, ())
            if (
                previous_intent in related
                and raw_confidence > 0.5
                and boosted_raw == raw_confidence
            ):
                boosted_raw = _scaled_boost(raw_confidence, 1.15)

            if _detect_urgent(user_message):
                running_confidence = (previous_confidence * 0.4) + (boosted_raw * 0.6)
                running_confidence = max(running_confidence, 0.60)
            else:
                running_confidence = (previous_confidence * HISTORY_WEIGHT) + (boosted_raw * CURRENT_WEIGHT)

            max_drop = previous_confidence * 0.50
            running_confidence = max(max_drop, running_confidence)
            running_confidence = round(running_confidence, 3)

            if intent == "neutral" and not _detect_urgent(user_message):
                running_confidence = min(running_confidence, 0.55)
                running_confidence = round(running_confidence, 3)

        intent_priority = ["neutral", "academic", "loneliness", "anger", "stress", "sadness", "anxiety", "suicidal"]
        prev_priority = intent_priority.index(previous_intent) if previous_intent in intent_priority else 0
        curr_priority = intent_priority.index(intent) if intent in intent_priority else 0

        if post_crisis and _detect_calming(user_message):
            pass
        else:
            intent = intent if curr_priority >= prev_priority else previous_intent

        if "meta" not in session:
            session["meta"] = {}
        session["meta"]["running_confidence"] = running_confidence
        session["meta"]["running_intent"] = intent
        session["meta"]["post_crisis"] = post_crisis

    # --- Step 5: Map confidence to anxiety level ---
    post_crisis = session.get("meta", {}).get("post_crisis", False)
    final_detection = _build_result(intent, running_confidence, post_crisis=post_crisis)
    anxiety_level = final_detection["anxiety_level"]
    severity = final_detection["severity"]
    counselor_protocol = final_detection["counselor_protocol"]
    anxiety_score = final_detection["anxiety_score"]

    # --- Step 5b: Fuse with acoustic features if available ---
    pending_acoustic = session.get("meta", {}).get("pending_acoustic")
    if pending_acoustic:
        try:
            from app.analytics.acoustic_features import fuse_with_text_severity
            acoustic_severity = pending_acoustic.get("severity", "Normal")
            acoustic_emotion = pending_acoustic.get("emotion", "neutral")
            acoustic_confidence = pending_acoustic.get("confidence", 0.0)

            fused_severity = fuse_with_text_severity(
                acoustic_severity=acoustic_severity,
                text_severity=severity,
                acoustic_emotion=acoustic_emotion,
            )

            severity_order = {"Normal": 0, "Low": 1, "Moderate": 2, "High": 3}
            if severity_order.get(fused_severity, 0) > severity_order.get(severity, 0):
                severity = fused_severity
                severity_to_level = {
                    "Low": ("low", 1),
                    "Moderate": ("moderate", 3),
                    "High": ("high", 5),
                }
                if fused_severity in severity_to_level:
                    anxiety_level, anxiety_score = severity_to_level[fused_severity]
                    counselor_protocol = final_detection.get("counselor_protocol")

            session["meta"]["pending_acoustic"] = None
            logger.info(f"Acoustic fusion: text={final_detection['severity']} acoustic={acoustic_severity} fused={severity}")
        except Exception as e:
            logger.error(f"Acoustic fusion error: {e}")

    # --- Step 6: Is a human counselor active? ---
    counselor_active = bool(session.get("meta", {}).get("counselor_active"))

    return {
        "session": session,
        "session_id": session_id,
        "intent": intent,
        "running_confidence": running_confidence,
        "anxiety_level": anxiety_level,
        "severity": severity,
        "anxiety_score": anxiety_score,
        "counselor_protocol": counselor_protocol,
        "crisis_resources": crisis_resources,
        "is_venting": is_venting,
        "counselor_active": counselor_active,
    }


def _finalize_turn(turn: Dict[str, Any], user_message: str, response_text: str, method: str, escalate: bool, fire_alert: bool = True) -> Dict[str, Any]:
    """Steps 8–9 shared by both paths: record interactions, fire alerts,
    track covered themes, and return the canonical result dict."""
    session = turn["session"]
    session_id = turn["session_id"]
    intent = turn["intent"]
    running_confidence = turn["running_confidence"]
    anxiety_level = turn["anxiety_level"]
    severity = turn["severity"]
    anxiety_score = turn["anxiety_score"]

    # --- Step 9: Record interaction (user) ---
    try:
        record_interaction(
            session_id=session_id,
            sender="user",
            text=user_message,
            analysis={
                "intent": intent,
                "confidence": running_confidence,
                "intensity": anxiety_score,
                "severity": severity,
                "escalate": escalate,
            },
            response=response_text if method != "counselor" else None,
        )
    except Exception as e:
        logger.error(f"Failed to record interaction: {e}")

    # --- Step 9a: Record GAIDA's bot reply as its own visible message ---
    if response_text:
        try:
            record_interaction(
                session_id=session_id,
                sender="bot",
                text=response_text,
                analysis={},
                response=None,
            )
        except Exception as e:
            logger.error(f"Failed to record bot interaction: {e}")

        # --- Step 9b: Track question themes to prevent repetition ---
        if "meta" not in session:
            session["meta"] = {}
        if "covered_themes" not in session["meta"]:
            session["meta"]["covered_themes"] = []

        sentences = [s.strip() for s in response_text.split('.') if s.strip()]
        if sentences:
            closing_line = sentences[-1]
            session["meta"]["covered_themes"].append(closing_line)
            session["meta"]["covered_themes"] = session["meta"]["covered_themes"][-5:]

    # --- Step 8: Fire counselor alert for HIGH and CRISIS ---
    if escalate and fire_alert:
        try:
            process_alert(
                session_id=session_id,
                user_id=session.get("user_id") if session else None,
                intent=intent,
                anxiety_score=anxiety_score,
                message=user_message,
            )
        except Exception as e:
            logger.error(f"Failed to fire counselor alert: {e}")

    return {
        "session_id": session_id,
        "intent": intent,
        "confidence": running_confidence,
        "anxiety_level": anxiety_level,
        "severity": severity,
        "anxiety_score": anxiety_score,
        "response": response_text if method != "counselor" else None,
        "counselor_active": method == "counselor",
        "method": method,
    }


def analyze_intent(user_message: str, session_id: str | None = None, user_id: str | None = None, vent_mode: bool = False) -> Dict[str, Any]:
    turn = _prepare_turn(user_message, session_id, user_id, vent_mode)

    # --- Step 6: If counselor is active — skip GPT, still return full analysis ---
    if turn["counselor_active"]:
        escalate = turn["anxiety_level"] in ("high", "crisis") or turn["running_confidence"] >= 0.99
        return _finalize_turn(turn, user_message, "", "counselor", escalate, fire_alert=False)

    # --- Step 7: GPT response (only when counselor is NOT active) ---
    gpt_protocol = turn["counselor_protocol"]
    if turn["crisis_resources"]:
        gpt_protocol = f"{turn['crisis_resources']}\n\n{turn['counselor_protocol'] or ''}"

    gpt_result = generate_response_with_gpt(
        user_message=user_message,
        session_context=turn["session"],
        anxiety_level=turn["anxiety_level"],
        counselor_protocol=gpt_protocol,
    )

    if gpt_result.get("used") and gpt_result.get("response"):
        response_text = gpt_result["response"]
        method = "gpt"
    else:
        logger.warning("GPT unavailable, using safe fallback response")
        response_text = "I'm here with you. Can you tell me more about how you're feeling?"
        method = "fallback"

    escalate = turn["anxiety_level"] in ("high", "crisis") or turn["running_confidence"] >= 0.99

    return _finalize_turn(turn, user_message, response_text, method, escalate)


def stream_analyze_intent(user_message: str, session_id: str | None = None, user_id: str | None = None, vent_mode: bool = False):
    """Streaming variant of analyze_intent.

    Yields event dicts:
      {"type": "delta", "text": str}   — each GPT token chunk
      {"type": "done",  "result": {...}} — final result dict (the same shape
                                            analyze_intent returns)
    """
    turn = _prepare_turn(user_message, session_id, user_id, vent_mode)

    # --- Step 6: Counselor active — no GPT, immediately done ---
    if turn["counselor_active"]:
        escalate = turn["anxiety_level"] in ("high", "crisis") or turn["running_confidence"] >= 0.99
        yield {"type": "done", "result": _finalize_turn(turn, user_message, "", "counselor", escalate, fire_alert=False)}
        return

    # --- Step 7: Stream GPT response ---
    gpt_protocol = turn["counselor_protocol"]
    if turn["crisis_resources"]:
        gpt_protocol = f"{turn['crisis_resources']}\n\n{turn['counselor_protocol'] or ''}"

    response_text = ""
    got_tokens = False
    for delta, full in stream_gpt_response(
        user_message=user_message,
        session_context=turn["session"],
        anxiety_level=turn["anxiety_level"],
        counselor_protocol=gpt_protocol,
    ):
        got_tokens = True
        response_text = full
        yield {"type": "delta", "text": delta}

    if not got_tokens:
        logger.warning("GPT stream unavailable, using safe fallback response")
        response_text = "I'm here with you. Can you tell me more about how you're feeling?"
        yield {"type": "delta", "text": response_text}

    method = "gpt" if got_tokens else "fallback"
    escalate = turn["anxiety_level"] in ("high", "crisis") or turn["running_confidence"] >= 0.99

    result = _finalize_turn(turn, user_message, response_text, method, escalate)
    yield {"type": "done", "result": result}