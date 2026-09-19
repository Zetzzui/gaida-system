import tempfile
import os
import traceback
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from fastapi.responses import Response
from app.utils.auth import get_current_user
from app.services.tts import text_to_speech_bytes
from app.analytics.acoustic_features import (
    extract_features,
    map_acoustic_to_severity,
    fuse_with_text_severity,
    log_to_supabase,
)
from app.services.session_manager import get_session, start_session

router = APIRouter(prefix="/audio", tags=["audio"])

# ── Lazy load Whisper — loads on first voice request, not at startup ──
_whisper_model = None


def _ensure_ffmpeg_on_path():
    """Whisper shells out to the `ffmpeg` command. If it isn't on the system,
    expose the bundled static ffmpeg from imageio-ffmpeg through PATH so
    transcription works on hosts with no apt (e.g. Render)."""
    import shutil
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        _dir = os.path.dirname(exe)
        os.environ["PATH"] = _dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        _ensure_ffmpeg_on_path()
        import whisper
        print("[GAIDA] Loading Whisper model (first voice request)...")
        _whisper_model = whisper.load_model("medium")
        print("[GAIDA] Whisper model loaded.")
    return _whisper_model

@router.post("/speech-to-text")
async def speech_to_text(
    audio: UploadFile = File(...),
    session_id: str = Form(None),
    user: dict = Depends(get_current_user),
):
    try:
        if session_id:
            session = get_session(session_id)
            if session and session.get("user_id") and session["user_id"] != user["user_id"]:
                raise HTTPException(status_code=403, detail="Session does not belong to this user")

        # Accept any audio content type — browser sends various formats
        content_type = audio.content_type or ""
        if content_type and not content_type.startswith("audio/") and not content_type.startswith("video/webm"):
            print(f"DEBUG: Rejected content type: {content_type}")
            raise HTTPException(status_code=400, detail=f"File must be audio type. Got: {content_type}")

        audio_bytes = await audio.read()
        print(f"DEBUG: Audio bytes received: {len(audio_bytes)}")

        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file.")

        # --- Step 1: Acoustic feature extraction ---
        acoustic_features_dict = {}
        acoustic_severity = "Normal"
        acoustic_confidence = 0.0
        acoustic_emotion = "neutral"

        try:
            acoustic_features_dict = extract_features(audio_bytes)
            acoustic_severity = map_acoustic_to_severity(
                acoustic_features_dict.get("acoustic_anxiety_score", 0.0)
            )
            acoustic_confidence = acoustic_features_dict.get("acoustic_confidence", 1.0)
            acoustic_emotion = acoustic_features_dict.get("acoustic_emotion", "neutral")
            print(f"DEBUG: Acoustic features extracted - severity={acoustic_severity}, emotion={acoustic_emotion}")

            # ── Log to Supabase ──────────────────────────────────────────────
            log_to_supabase(session_id=session_id or "unknown", features=acoustic_features_dict)

        except Exception as e:
            print(f"DEBUG: Acoustic extraction failed (non-fatal): {e}")
        # --- Step 2: Save acoustic features to session ---
        if session_id:
            session = get_session(session_id)
            if session is None:
                session_id = start_session()
                session = get_session(session_id)
        else:
            session_id = start_session()
            session = get_session(session_id)

        if session:
            if "meta" not in session:
                session["meta"] = {}
            session["meta"]["pending_acoustic"] = {
                "severity": acoustic_severity,
                "emotion": acoustic_emotion,
                "confidence": acoustic_confidence,
                "anxiety_score": acoustic_features_dict.get("acoustic_anxiety_score", 0.0),
                "pitch_mean": acoustic_features_dict.get("pitch_mean", 0.0),
                "speech_rate": acoustic_features_dict.get("speech_rate", 0.0),
                "pause_ratio": acoustic_features_dict.get("pause_ratio", 0.0),
                "jitter": acoustic_features_dict.get("jitter", 0.0),
                "shimmer": acoustic_features_dict.get("shimmer", 0.0),
                "energy_mean": acoustic_features_dict.get("energy_mean", 0.0),
            }
            print(f"DEBUG: Acoustic features saved to session {session_id}")

        # --- Step 3: Whisper transcription ---
        # Always use .webm suffix so Whisper/ffmpeg handles it correctly
        suffix = ".webm"
        tmp_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            print(f"DEBUG: Temp file created: {tmp_path}")

            print(f"DEBUG: Starting Whisper transcription...")
            result = _get_whisper_model().transcribe(tmp_path)
            transcript = result.get("text", "").strip()
            print(f"DEBUG: Transcription complete: '{transcript}'")

        except Exception as e:
            print(f"DEBUG: Transcription error: {e}")
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        return {
            "transcript": transcript,
            "session_id": session_id,
            "acoustic": {
                "severity": acoustic_severity,
                "emotion": acoustic_emotion,
                "confidence": acoustic_confidence,
                "anxiety_score": acoustic_features_dict.get("acoustic_anxiety_score", 0.0),
                "pitch_mean": acoustic_features_dict.get("pitch_mean", 0.0),
                "speech_rate": acoustic_features_dict.get("speech_rate", 0.0),
                "pause_ratio": acoustic_features_dict.get("pause_ratio", 0.0),
                "jitter": acoustic_features_dict.get("jitter", 0.0),
                "shimmer": acoustic_features_dict.get("shimmer", 0.0),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"DEBUG: Unhandled error in speech-to-text: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tts")
def tts(text: str, user: dict = Depends(get_current_user)):
    if not text:
        raise HTTPException(status_code=400, detail="text param is required.")
    try:
        audio_bytes = text_to_speech_bytes(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")
    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=response.mp3"},
    )


@router.post("/analyze")
async def analyze_audio(audio: UploadFile = File(...), user: dict = Depends(get_current_user)):
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    features = extract_features(audio_bytes)
    severity = map_acoustic_to_severity(features.get("acoustic_anxiety_score", 0.0))

    # ── Log to Supabase ──────────────────────────────────────────────────────
    log_to_supabase(session_id="analyze", features=features)
    return {
        "acoustic_severity": severity,
        "acoustic_anxiety_score": features.get("acoustic_anxiety_score"),
        "acoustic_emotion": features.get("acoustic_emotion"),
        "features": features,
    }