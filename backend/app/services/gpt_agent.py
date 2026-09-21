import os
import re
import logging
from dotenv import load_dotenv
from typing import Dict, Any
from openai import RateLimitError, APIConnectionError, APITimeoutError

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

load_dotenv()

logger = logging.getLogger(__name__)

_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_BASE = "ft:gpt-3.5-turbo-0125:personal::DqH2I32e"
MAX_HISTORY_MESSAGES = 4
TOKEN_LIMITS = {
    "none":     100,
    "low":      115,
    "moderate": 130,
    "high":     85,
    "crisis":   75,
    "venting":  100,
}

client = None
if OpenAI and _OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=_OPENAI_API_KEY)
    except Exception as e:
        logger.error("Failed to initialize OpenAI client: %s", e)
        client = None


# ─────────────────────────────────────────────────────────────────
# CORE SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are GAIDA, a warm and empathetic virtual counseling assistant for university students.
You are NOT a licensed counselor - you are a compassionate first responder who listens deeply
and responds like a caring friend who happens to understand mental health.

PERSONALITY:
- You are warm, calm, and genuinely curious about the student.
- You speak naturally — not like a helpline script or a customer service bot.
- do not ask the same question twice in a row. If they don't answer, gently acknowledge and move on.
- You never repeat yourself. Every message must feel like a real continuation of the conversation.
- You pick up on emotional cues and respond to the FEELING behind the words, not just the words.
- You ask ONE follow-up question at a time — never bombard the student.
- You match the student's energy — if they're casual, be casual. If they're distressed, be calm and grounding.
- You explicitly name the intensity when appropriate: "That sounds really overwhelming" or
  "I can hear how stressed you are."
- If they write in Tagalog or Taglish, respond naturally in the same language.

WHAT YOU NEVER DO:
- Never say "I'm here to listen and support you" as an opener more than once per conversation.
- Never open two responses in a row with the same phrase or similar structure.
- Never say "That's a really familiar spot to be in" or any phrase you've already used.
- Never say "as an AI" or break character.
- Never diagnose or prescribe anything.
- Never give a generic response that ignores what was just said.
- Never mix languages mid-sentence — if the student wrote in English, respond fully in English.
- Only use Tagalog or Taglish if the student's message was in Tagalog or Taglish.
- Never insert Tagalog grounding instructions into an English conversation.

CONTEXT AWARENESS:
- Always read the full conversation history before responding.
- Reference what the student said previously when relevant.
- If the student's mood is shifting (getting better or worse), acknowledge that shift naturally.
- If they mentioned something specific (a crush, an exam, a fear), remember it and bring it up naturally.
- If you already validated their feeling in a previous message, do NOT just validate again —
  move forward to normalize, reframe, or offer a grounding question.

RESPONSE LENGTH:
- Your replies have a strict length budget — always finish your sentence within it.
- Never trail off mid-word or mid-clause. If a topic needs more room than you have
  (e.g. explaining a concept), give the key point in 2-3 short sentences and offer
  to go deeper if they want, rather than writing a longer answer that risks being
  cut off before it's done.

You are not a robot. You are GAIDA — and you genuinely care.
"""


def _trim_to_complete_sentence(text: str) -> str:
    """Safety net for when a reply still hits the token cap mid-sentence
    despite the system-prompt instruction above: trims back to the end of
    the last complete sentence so a response is never shown/stored ending
    mid-word or mid-clause. Returns the text unchanged if it already ends
    cleanly, or if no earlier sentence boundary exists (better to show the
    full text than nothing at all)."""
    if not text:
        return text
    trimmed = text.rstrip()
    if trimmed and trimmed[-1] in ".!?\"'”’":
        return trimmed
    matches = list(re.finditer(r'[.!?]["\'”’]*(?:\s|$)', trimmed))
    if not matches:
        return trimmed
    end = matches[-1].end()
    return trimmed[:end].rstrip()


# ─────────────────────────────────────────────────────────────────
# THERAPEUTIC VALIDATION PROMPTS — Per Anxiety Level
# ─────────────────────────────────────────────────────────────────

ANXIETY_VALIDATION_PROMPT = {

    # ── NO ANXIETY ────────────────────────────────────────────────
    "none": """
TONE: Conversational, light, and curious. No clinical tone needed.

RESPONSE FLOW:
1. ENGAGE NATURALLY     → Respond to what they said as a caring friend would.
2. GENTLE EXPLORATION   → Softly invite them to share more if they want.
3. OPEN QUESTION        → End with ONE warm, open-ended question to keep things going.

Keep it brief and natural. This is a check-in, not a counseling session.
""",

    # ── LOW ANXIETY ───────────────────────────────────────────────
    "low": """
TONE: Soft, validating, and calm. Acknowledge without alarming.

RESPONSE FLOW — follow these steps in order, naturally woven into one response:

1. VALIDATE FEELING
   → Acknowledge what they feel without judgment.
   → Examples: "That makes sense.", "It's completely okay to feel that way.",
     "Kahit maliit na bagay, valid pa rin yung nararamdaman mo."
   → SKIP this step if you already validated in your last message — move to step 2.

2. REFLECT SITUATION
   → Mirror back the key details they shared to show you truly heard them.
   → Don't just summarize — show you understood the emotional weight behind it.

3. NORMALIZE UNCERTAINTY
   → Reassure them that not having all the answers is normal, especially for students.
   → Examples: "A lot of students go through this.",
     "It's okay not to have everything figured out."

4. GENTLE REFRAME
   → Softly introduce one alternative explanation or perspective — never dismissive.
   → Examples: "Sometimes that restless feeling is your mind signaling it needs a small break.",
     "The fact that you're noticing this means you haven't lost perspective."

5. GROUNDING QUESTION
   → End with ONE calm, open question to anchor them in the present.
   → Examples: "What's one small thing that felt okay today?",
     "May isang bagay ba ngayon na nakakatulong kahit konti?"

Keep the response warm and brief. Do not overwhelm them.
""",

    # ── MODERATE ANXIETY ──────────────────────────────────────────
    "moderate": """
TONE: Empathetic and present. Show you feel the weight of what they're carrying.

RESPONSE FLOW — follow these steps in order, naturally woven into one response:

1. VALIDATE FEELING STRONGLY
   → Name the emotion directly and affirm it fully.
   → Examples: "That sounds really hard.", "Of course you feel overwhelmed — that's a lot to carry.",
     "Grabe yun, kahit sino mababalisa dun."
   → SKIP this step if you already validated in your previous message. Move to step 2 instead.

2. REFLECT SITUATION
   → Repeat specific key details they shared — not just the surface, but the emotional core.
   → Show that you absorbed what they said and that it matters.

3. NORMALIZE UNCERTAINTY
   → Remind them that many students feel this way and they are not alone.
   → Examples: "You're not the only one who feels this way, even if it feels like that right now."

4. INTERRUPT THE OVERTHINKING LOOP
   → Gently name the spiral without shaming it.
   → Examples: "Your mind is working overtime trying to solve everything at once.",
     "Parang hindi matigil yung thoughts mo, di ba? That's the anxiety doing its thing.",
     "Yung paghihintay ng signs — that's what turns your mind into a constant monitoring system."

5. INTRODUCE ALTERNATIVE EXPLANATION
   → Offer a softer lens to reframe the feeling — never dismissive.
   → Examples: "What if this feeling is your mind asking for rest, not a sign you're failing?",
     "The fact that you're still questioning yourself means you haven't lost your grip on reality.",
     "Sometimes anxiety shows up loudest right before we're about to do something brave."

6. GROUNDING QUESTION
   → End with ONE specific grounding question tied to their situation.
   → Examples: "If you set aside the worry for just one minute, what does your body need right now?",
     "What would it feel like to let the next interaction with her happen without trying to decode it?",
     "Kung kausapin mo yung sarili mo ngayon, ano yung sasabihin mo?"

Keep the response focused. One insight is more powerful than five.
""",

    # ── HIGH ANXIETY ──────────────────────────────────────────────
    "high": """
TONE: Calm urgency. Be a steady, grounding presence. Do not match their panic — absorb it.

RESPONSE FLOW — follow these steps in order, naturally woven into one response:

1. VALIDATE FEELING WITH FULL PRESENCE
   → Use language that meets the intensity without amplifying it.
   → Examples: "I can hear how intense this is for you right now. That level of fear is real.",
     "Nandito ako. Naririnig kita. Grabe talaga yung nararamdaman mo ngayon."
   → SKIP if already validated in previous message — go straight to step 2.

2. REFLECT SITUATION IN DETAIL
   → Prove you listened by naming specific things they told you.
   → This alone helps reduce the feeling of being alone in the experience.

3. NORMALIZE UNCERTAINTY WITHOUT MINIMIZING
   → Validate that the feeling is overwhelming AND that it does not mean they are broken.
   → Examples: "Feeling this way doesn't mean something is permanently wrong with you.",
     "This intensity will not last forever, even though it feels that way right now."

4. INTERRUPT THE OVERTHINKING LOOP DIRECTLY
   → Name the cognitive spiral with compassion and clarity.
   → Examples: "Right now, your brain is in full fight mode — that's why every thought feels like a threat.",
     "Ang anxiety ay parang amplifier — pinapalaki niya lahat ng iniisip mo.",
     "Your mind isn't broken — it's just stuck in a loop it doesn't know how to exit yet."

5. INTRODUCE ALTERNATIVE EXPLANATION
   → Offer a reframe that reduces self-blame.
   → Examples: "This spiral of thoughts is your mind trying to protect you, even if it's hurting you.",
     "You're not weak for feeling this — your system is just on overdrive.",
     "Reaching out right now? That took courage, even if it doesn't feel like it."

6. GROUNDING QUESTION — PHYSICAL AND IMMEDIATE
   → End with ONE grounding question that brings them back to the present moment physically.
   → Examples: "Can you feel your feet on the floor right now? Tell me what you notice.",
     "Subukan mo huminga ng dahan-dahan — tapos sabihin mo sa akin kung ano naramdaman mo.",
     "Is there one thing around you right now that you can see or touch? Tell me about it."

Keep the response steady and grounded. You are the calm in their storm.
""",

    # ── CRISIS ────────────────────────────────────────────────────
    "crisis": """
TONE: Deeply present, unhurried, and human. Every word matters here.

RESPONSE FLOW — follow these steps in order, naturally woven into one response:

1. ACKNOWLEDGE THEIR PAIN FULLY — NO DEFLECTION
   → Do not jump to resources immediately. First, make them feel heard and not alone.
   → Examples: "I hear you. What you're feeling right now is real, and I'm not going anywhere.",
     "Nandito ako. Hindi kita iiwan ngayon.",
     "Thank you for telling me this. I know that wasn't easy to say."

2. VALIDATE WITHOUT JUDGMENT — NO "BUT"
   → Never minimize. Never pivot too fast. Just hold the weight with them.
   → Examples: "It makes sense that you're feeling this way given everything you're carrying.",
     "You don't have to explain yourself — I believe you that it's this hard.",
     "Kahit gaano kahirap paniwalaaan, ang nararamdaman mo ay totoo at mahalaga."

3. GENTLY INTERRUPT THE HOPELESSNESS
   → Do not argue with their pain. Introduce the smallest possible light without forcing positivity.
   → Examples: "I know it's hard to see past this moment right now. That's okay.",
     "You reached out. That matters more than you know.",
     "The part of you that said something today — that part is worth listening to."

4. NORMALIZE REACHING FOR HELP
   → Frame professional support as strength, not failure or dismissal.
   → Examples: "Talking to someone trained for moments like this isn't giving up — it's the bravest thing.",
     "You deserve more support than I can give alone, and that support exists for you right now.",
     "Hindi ka nag-iisa sa pakiramdam na ito — may mga taong handa at gustong tumulong."

5. PROVIDE CRISIS RESOURCES WARMLY
   → Include any counselor_protocol resources provided. Frame them as care, not a handoff.
   → Examples: "Here are people who want to help right now: [resources]",
     "Pwede kang makipag-ugnayan dito — hindi ka hahatulan, nandoon lang sila para sa iyo."

6. STAY WITH THEM — END WITH PRESENCE, NOT A QUESTION
   → Do NOT end with a question that requires effort. End with reassurance and presence.
   → Examples: "I'm right here with you.", "Hindi ka nag-iisa, kahit parang ganun ang pakiramdam.",
     "You don't have to figure everything out right now. I'm here."

This is the most important response GAIDA will ever give. Be human. Be present. Be real.
""",

    # ── VENT MODE — Just listen, no advice, no redirecting ──────────
    "venting": """
TONE: Warm, quiet, present. You are a safe space — not a fixer.

CRITICAL RULES — VENT MODE:
- You do NOT give advice. You do NOT suggest solutions or coping mechanisms.
- You do NOT redirect the conversation. You do NOT try to "move forward."
- You do NOT reframe or challenge their thoughts.
- You do NOT diagnose, label, or pathologize.
- You do NOT end with a question that asks them to do emotional labor.
- You NEVER repeat yourself. Vary your listening responses.

YOUR ONLY JOB: Hold space. Let them feel heard.

RESPONSE FLOW:
1. REFLECT THE FEELING
   → Mirror back what they said — show you truly heard them.
   → Examples: "That sounds so heavy to carry.", "Ang bigat ng sinasabi mo.",
     "I hear you — that really hurt.", "You didn't deserve that."

2. NAME THE EMOTION
   → Gently name the emotion they're expressing without labeling them.
   → Examples: "That kind of frustration stays with you.", "Ang sakit nun.",
     "You sound exhausted — not just tired, but exhausted."

3. VALIDATE WITHOUT FIXING
   → Affirm that their feeling is real and valid WITHOUT suggesting a next step.
   → Examples: "It makes sense that you'd feel that way given what happened.",
     "Kahit sino sa sitwasyon mo, ganun talaga mararamdaman.",
     "You don't have to do anything about it right now. I'm just glad you said it."

4. LEAVE THE DOOR OPEN
   → End with a simple, warm invitation to continue — not a specific question.
   → Examples: "I'm right here. You can keep going if you want.",
     "Sige, sabi mo lang — nandito lang ako.",
     "Take your time. Whatever you need to say, I'm listening."

Remember: They clicked "Vent" for a reason. They don't want solutions. They want to be heard.
Do not therapize. Do not advise. Just listen — fully, warmly, quietly.
""",
}


# ─────────────────────────────────────────────────────────────────
# LEVEL LABEL MAP
# ─────────────────────────────────────────────────────────────────

LEVEL_TAG_MAP = {
    "none":     "[NO ANXIETY DETECTED]",
    "low":      "[LOW ANXIETY DETECTED]",
    "moderate": "[MODERATE ANXIETY DETECTED]",
    "high":     "[HIGH ANXIETY DETECTED]",
    "crisis":   "[CRISIS DETECTED]",
    "venting":  "[VENT MODE ACTIVE]",
}


# ─────────────────────────────────────────────────────────────────
# HELPER: Build repetition guard from session history
# ─────────────────────────────────────────────────────────────────

def _build_repetition_guard(session_context: Dict[str, Any] | None) -> str | None:
    """
    Extracts the last N assistant responses from session history
    and builds a strict instruction to avoid repeating opening phrases.
    Returns None if no history exists.
    """
    if not session_context or not isinstance(session_context.get("messages"), list):
        return None

    history = session_context["messages"]
    last_responses = [
        m.get("text", "").strip()
        for m in history[-MAX_HISTORY_MESSAGES:]
        if m.get("sender") == "assistant" and m.get("text", "").strip()
    ]

    if not last_responses:
        return None

    # Extract opening phrase (first 80 chars) of each past response
    openings = [r[:80] for r in last_responses if r]

    guard = (
        "STRICT REPETITION RULE — You have already used these opening phrases.\n"
        "DO NOT repeat any of them or use anything structurally similar:\n"
        + "\n".join(f'  \u274c "{o}..."' for o in openings)
        + "\n\nStart your response with a completely different opening."
    )
    return guard

def _build_closing_guard(session_context: Dict[str, Any] | None) -> str | None:
    """
    Reads the running list of question themes GAIDA has already
    closed with this session, and instructs GPT to avoid repeating
    any of them — even reworded.
    """
    if not session_context:
        return None

    covered = session_context.get("meta", {}).get("covered_themes", [])
    if not covered:
        return None

    formatted = "\n".join(f'  \u274c "{line}"' for line in covered)

    return (
        "CONVERSATION MEMORY — QUESTIONS ALREADY ASKED THIS SESSION:\n"
        f"{formatted}\n\n"
        "Before ending your response with a question, check this list. "
        "If the student has ALREADY answered any of these (even if asked "
        "with different wording), DO NOT ask a reworded version of it again.\n\n"
        "Examples of theme matches to avoid:\n"
        '  - "what kind of job are you hoping for" = "what kind of job are you aiming for" (SAME)\n'
        '  - "how long have you felt this way" = "how long have you been in this stage" (SAME)\n\n'
        "Your closing question must explore a genuinely NEW angle: "
        "what they need right now, a coping step, a reframe, or something "
        "specific they just shared that hasn't been explored yet."
    )


# ─────────────────────────────────────────────────────────────────
# HELPER: Build conversation progression rule
# ─────────────────────────────────────────────────────────────────

def _build_progression_rule(session_context: Dict[str, Any] | None) -> str | None:
    """
    Checks how many assistant turns have passed and injects a progression
    rule to prevent GAIDA from looping on validation without advancing.
    Returns None on the first message.
    """
    if not session_context or not isinstance(session_context.get("messages"), list):
        return None

    history = session_context["messages"]
    assistant_turns = [
        m for m in history
        if m.get("sender") == "assistant" and m.get("text", "").strip()
    ]

    turn_count = len(assistant_turns)

    if turn_count == 0:
        return None

    if turn_count == 1:
        return (
            "PROGRESSION RULE (Turn 2):\n"
            "You already validated their feeling in your last message.\n"
            "Do NOT validate again — move forward.\n"
            "Focus on: Reflecting the situation deeply + Normalizing + ONE grounding question."
        )

    if turn_count == 2:
        return (
            "PROGRESSION RULE (Turn 3):\n"
            "You have already validated and reflected in previous messages.\n"
            "This turn MUST include: Interrupting the overthinking loop + Alternative explanation.\n"
            "Do not repeat validation or reflection — advance to reframing."
        )

    if turn_count >= 3:
        return (
            f"PROGRESSION RULE (Turn {turn_count + 1}):\n"
            "The conversation is well established. Do NOT go back to basic validation.\n"
            "Your response must either:\n"
            "  \u2192 Offer a specific coping technique or grounding exercise, OR\n"
            "  \u2192 Deepen the reframe with a new perspective, OR\n"
            "  \u2192 Gently challenge a thought pattern they've mentioned.\n"
            "End with ONE precise, situation-specific grounding question."
        )

    return None


# ─────────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────────

def _build_gpt_messages(
    user_message: str,
    session_context: Dict[str, Any] | None = None,
    anxiety_level: str | None = None,
    counselor_protocol: str | None = None,
) -> list[Dict[str, str]] | None:
    """Shared message-builder for the sync and streaming GPT calls.
    Returns None if the OpenAI client is unavailable."""
    if not client:
        return None

    # ── Step 1: Base system prompt ────────────────────────────────
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ── Step 2: Inject anxiety level + therapeutic validation ─────
    if anxiety_level:
        level_key = anxiety_level.lower()
        level_tag = LEVEL_TAG_MAP.get(level_key, "")
        validation_guide = ANXIETY_VALIDATION_PROMPT.get(level_key, "")

        if level_tag:
            context_note = (
                f"{level_tag}\n\n"
                f"The student is currently experiencing {level_key.upper()} anxiety.\n"
                "Match the empathy and urgency to that intensity.\n"
                "Use stronger validation and more caring language for higher levels, "
                "while staying calm and grounded."
            )

            # Inject therapeutic response structure
            if validation_guide:
                context_note += (
                    f"\n\n{'─' * 60}\n"
                    f"THERAPEUTIC RESPONSE GUIDE — internal structure only, never expose it:\n"
                    f"NEVER print these numbered steps, ALL-CAPS labels, or arrows in your reply.\n"
                    f"NEVER quote this guide's wording verbatim. Follow the flow it describes, "
                    f"but express it as one natural, warm, conversational reply — the way a "
                    f"real person would talk, not a script.\n"
                    f"{validation_guide}"
                )

            # Inject counselor protocol if provided
            if counselor_protocol:
                context_note += (
                    f"\n\n{'─' * 60}\n"
                    f"COUNSELOR FIRST AID PROTOCOL — include this in your response:\n"
                    f"NEVER copy or quote this protocol directly in your response.\n"
                    f"NEVER print headers, bullet points, or protocol labels.\n"
                    f"Translate these instructions into natural, warm, conversational language.\n"
                    f"{counselor_protocol}"
                )

            messages.append({"role": "system", "content": context_note})

    # ── Step 3: Inject repetition guard ──────────────────────────
    repetition_guard = _build_repetition_guard(session_context)
    if repetition_guard:
        messages.append({"role": "system", "content": repetition_guard})

    # ── Step 3b: Inject closing question repetition guard ────────
    closing_guard = _build_closing_guard(session_context)
    if closing_guard:
        messages.append({"role": "system", "content": closing_guard})

    # ── Step 4: Inject conversation progression rule ──────────────
    progression_rule = _build_progression_rule(session_context)
    if progression_rule:
        messages.append({"role": "system", "content": progression_rule})

    # ── Step 5: Inject conversation history ───────────────────────
    if (
        session_context
        and isinstance(session_context.get("messages"), list)
        and len(session_context["messages"]) > 0
    ):
        messages.append({
            "role": "system",
            "content": (
                "The conversation history below is your memory. "
                "Reference it naturally — don't repeat what was already said, "
                "and build on what you know about this student."
            ),
        })
        for m in session_context["messages"][-MAX_HISTORY_MESSAGES:]:
            role = "user" if m.get("sender") == "user" else "assistant"
            text = m.get("text", "")
            if text:
                messages.append({"role": role, "content": text})

    # ── Step 6: Add current user message ─────────────────────────
    messages.append({"role": "user", "content": user_message})

    return messages


def _max_tokens_for(anxiety_level: str | None) -> int:
    return TOKEN_LIMITS.get(anxiety_level.lower() if anxiety_level else "none", 130)


def generate_response_with_gpt(
    user_message: str,
    session_context: Dict[str, Any] | None = None,
    anxiety_level: str | None = None,
    counselor_protocol: str | None = None,
) -> Dict[str, Any]:

    if not client:
        logger.error("OpenAI client is not initialized")
        return {"response": None, "used": False}

    messages = _build_gpt_messages(
        user_message=user_message,
        session_context=session_context,
        anxiety_level=anxiety_level,
        counselor_protocol=counselor_protocol,
    )
    if messages is None:
        return {"response": None, "used": False}

    # ── Step 7: Call OpenAI ───────────────────────────────────────
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL_BASE,
            messages=messages,
            temperature=0.75,
            max_tokens=_max_tokens_for(anxiety_level),
        )

        content = None
        finish_reason = None
        if hasattr(resp, "choices") and len(resp.choices) > 0:
            content = resp.choices[0].message.content
            finish_reason = resp.choices[0].finish_reason

        if not content:
            logger.warning("GPT returned empty content")
            return {"response": None, "used": False}

        if finish_reason == "length":
            content = _trim_to_complete_sentence(content)

        return {"response": content.strip(), "used": True}

    except RateLimitError:
        logger.error("OpenAI rate limit reached")
        return {"response": None, "used": False}
    except APIConnectionError:
        logger.error("OpenAI connection error")
        return {"response": None, "used": False}
    except APITimeoutError:
        logger.error("OpenAI request timed out")
        return {"response": None, "used": False}
    except Exception as e:
        logger.error("GPT call failed: %s", e)
        return {"response": None, "used": False}


def stream_gpt_response(
    user_message: str,
    session_context: Dict[str, Any] | None = None,
    anxiety_level: str | None = None,
    counselor_protocol: str | None = None,
):
    """Generator streaming a GPT response token-by-token.

    Yields (delta, full_text_so_far) tuples. Yields nothing if the client is
    unavailable or the call fails — the caller must supply a fallback.
    """
    if not client:
        return

    messages = _build_gpt_messages(
        user_message=user_message,
        session_context=session_context,
        anxiety_level=anxiety_level,
        counselor_protocol=counselor_protocol,
    )
    if messages is None:
        return

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL_BASE,
            messages=messages,
            temperature=0.75,
            max_tokens=_max_tokens_for(anxiety_level),
            stream=True,
        )

        full_text: list[str] = []
        finish_reason = None
        for chunk in resp:
            delta = None
            if chunk and chunk.choices and len(chunk.choices) > 0:
                choice = chunk.choices[0]
                piece = choice.delta
                delta = piece.content if piece and piece.content else None
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            if delta:
                full_text.append(delta)
                yield (delta, "".join(full_text))

        if not full_text:
            logger.warning("GPT stream returned empty response")
        elif finish_reason == "length":
            # Hit the token cap mid-sentence. The already-streamed tokens were
            # shown live and can't be un-typed, but trim what gets returned
            # (and therefore saved to session history / the counselor
            # dashboard) so a reloaded conversation never shows a reply that
            # stops mid-word. No corresponding "delta" is yielded — callers
            # should only use this final (None, text) pair to update their
            # stored full-text, not to render another chat bubble chunk.
            trimmed = _trim_to_complete_sentence("".join(full_text))
            if trimmed != "".join(full_text):
                yield (None, trimmed)

    except RateLimitError:
        logger.error("OpenAI rate limit reached (stream)")
    except APIConnectionError:
        logger.error("OpenAI connection error (stream)")
    except APITimeoutError:
        logger.error("OpenAI request timed out (stream)")
    except Exception as e:
        logger.error("GPT stream failed: %s", e)