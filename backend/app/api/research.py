"""
Research-data-collection endpoints.

Default path is identified: a real student number is captured (same as a
normal login) so returning-student features, follow-up, and counselor
review all work exactly as they do for real sessions. A participant may
instead choose to participate anonymously — in that case no student number
is ever collected, and a random participant_code is generated and shown to
them once, so they have something to reference later (to withdraw, or to
resume as "the same" pseudonymous person) without it identifying them to
anyone else.

Demographics (year level, program, gender, region) are captured once per
participant, in research_participants, keyed by participant_id — not once
per session. A returning participant (same student number, or the same
anonymous code entered again) is never asked again; whatever is on file
for them is reused automatically. GAD-7, by contrast, is deliberately
asked every session, since anxiety is expected to vary over time.

Either way, this issues a normal bearer token (see utils/auth.py), so it
works against the existing /virtual-agent and /virtual-agent/stream
endpoints unmodified — no changes needed to the chat pipeline,
session_manager, or the frontend dashboard component.
"""
import re
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.database.database import supabase
from app.services.rate_limiter import check_rate_limit
from app.services.session_manager import start_session
from app.utils.auth import create_session_token

router = APIRouter(prefix="/api/research", tags=["research"])


# ---------------------------------------------------------------------------
# GAD-7 scoring — standard clinical cut-offs (Spitzer et al., 2006)
# ---------------------------------------------------------------------------
def _severity_band(total: int) -> str:
    if total >= 15:
        return "severe"
    if total >= 10:
        return "moderate"
    if total >= 5:
        return "mild"
    return "minimal"


# UE student numbers observed as 4-digit enrollment year + 7-digit sequence
# (11 digits total). Format check only, not verification.
_STUDENT_NUMBER_RE = re.compile(r"^\d{11}$")


def _validate_student_number(value: str) -> None:
    if not _STUDENT_NUMBER_RE.match(value):
        raise HTTPException(
            status_code=400,
            detail="Student number should be 11 digits (e.g. 20240001234).",
        )


def _resolve_participant_id(anonymous: bool, student_number: str | None, participant_code: str | None) -> tuple[str, str | None]:
    """Returns (participant_id, code_used). code_used is only non-None for
    the anonymous path — either the code the participant supplied, or a
    freshly generated one if this is their first time."""
    if anonymous:
        code_used = participant_code or uuid.uuid4().hex[:10]
        return f"anon_{code_used}", code_used

    if not student_number or not student_number.strip():
        raise HTTPException(
            status_code=400,
            detail="student_number is required unless participating anonymously",
        )
    student_number = student_number.strip()
    _validate_student_number(student_number)
    return student_number, None


def _fetch_participant(participant_id: str) -> dict | None:
    result = (
        supabase.table("research_participants")
        .select("year_level, program, gender, region")
        .eq("participant_id", participant_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ---------------------------------------------------------------------------
# Check whether a participant is already known, before showing demographics
# ---------------------------------------------------------------------------
class ParticipantCheckRequest(BaseModel):
    anonymous: bool = False
    student_number: str | None = Field(default=None, max_length=50)
    participant_code: str | None = Field(default=None, max_length=32)


class ParticipantCheckResponse(BaseModel):
    is_returning: bool


@router.post("/participant-check", response_model=ParticipantCheckResponse)
def check_participant(payload: ParticipantCheckRequest):
    """
    Called right after the identification step, before deciding whether to
    show the demographics form. Anonymous participants only get a
    meaningful answer here if they entered a previous code — a brand-new
    anonymous participant has no code yet, so is always "not returning."
    """
    if payload.anonymous and not payload.participant_code:
        return ParticipantCheckResponse(is_returning=False)

    participant_id, _ = _resolve_participant_id(
        payload.anonymous, payload.student_number, payload.participant_code
    )
    existing = _fetch_participant(participant_id)
    return ParticipantCheckResponse(is_returning=existing is not None)


# ---------------------------------------------------------------------------
# Start a session
# ---------------------------------------------------------------------------
class StartResearchRequest(BaseModel):
    anonymous: bool = False
    student_number: str | None = Field(default=None, max_length=50)
    participant_code: str | None = Field(default=None, max_length=32)

    # Only used the *first* time a given participant is seen — ignored (not
    # overwritten) for a returning participant, whose stored values are
    # used instead. See _resolve_participant_id / _fetch_participant.
    year_level: str | None = Field(default=None, max_length=50)
    program: str | None = Field(default=None, max_length=100)
    gender: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=100)


class StartResearchResponse(BaseModel):
    session_token: str
    session_id: str
    participant_id: str
    anonymous: bool
    participant_code: str | None = None  # only set (and shown once) for a brand-new anonymous participant


@router.post("/start", response_model=StartResearchResponse)
def start_research_session(payload: StartResearchRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(f"research_start:{client_ip}")

    participant_id, code_used = _resolve_participant_id(
        payload.anonymous, payload.student_number, payload.participant_code
    )

    existing = _fetch_participant(participant_id)
    if existing:
        # Returning participant — always use what's already on file,
        # regardless of what (if anything) this request sent.
        demographics = existing
    else:
        demographics = {
            "year_level": payload.year_level,
            "program": payload.program,
            "gender": payload.gender,
            "region": payload.region,
        }
        try:
            supabase.table("research_participants").insert({
                "participant_id": participant_id,
                "is_anonymous": payload.anonymous,
                **demographics,
            }).execute()
        except Exception as e:
            print(f"[research] participant record creation failed: {e}")

    session_id = str(uuid.uuid4())

    # Reuses the exact same session-creation path real logins use, so the
    # chat pipeline (running confidence, acoustic fusion, returning-student
    # check-ins, etc.) behaves identically for research participants.
    start_session(user_id=participant_id, session_id=session_id)

    try:
        supabase.table("sessions").update({
            "is_research": True,
            "is_anonymous": payload.anonymous,
            "participant_code": code_used,  # None for identified participants
            **demographics,
        }).eq("session_token", session_id).execute()
    except Exception as e:
        # Non-fatal — the session still works for chat even if this tagging
        # update fails; it just won't be picked up by the export script.
        print(f"[research] session tagging failed: {e}")

    token = create_session_token(participant_id, role="research")

    return StartResearchResponse(
        session_token=token,
        session_id=session_id,
        participant_id=participant_id,
        anonymous=payload.anonymous,
        # Only show a code to a *brand-new* anonymous participant — a
        # returning one already has theirs and doesn't need it shown again.
        participant_code=code_used if (payload.anonymous and not existing) else None,
    )


# ---------------------------------------------------------------------------
# GAD-7 — deliberately asked every session, not gated by participant history
# ---------------------------------------------------------------------------
class Gad7Request(BaseModel):
    session_id: str
    answers: list[int] = Field(min_length=7, max_length=7)


class Gad7Response(BaseModel):
    total_score: int
    severity_band: str


@router.post("/gad7", response_model=Gad7Response)
def submit_gad7(payload: Gad7Request):
    if any(a < 0 or a > 3 for a in payload.answers):
        raise HTTPException(status_code=400, detail="Each answer must be between 0 and 3")

    total = sum(payload.answers)
    band = _severity_band(total)

    try:
        supabase.table("gad7_responses").insert({
            "session_id": payload.session_id,
            "q1": payload.answers[0], "q2": payload.answers[1],
            "q3": payload.answers[2], "q4": payload.answers[3],
            "q5": payload.answers[4], "q6": payload.answers[5],
            "q7": payload.answers[6],
            "total_score": total,
            "severity_band": band,
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store GAD-7 response: {e}")

    return Gad7Response(total_score=total, severity_band=band)