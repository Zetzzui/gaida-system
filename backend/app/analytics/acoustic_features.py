import numpy as np
import librosa
import io
import tempfile
import os
import subprocess

def _convert_to_wav(audio_bytes: bytes) -> bytes:
    """
    Convert any audio format (webm, ogg, mp3, etc.) to WAV using ffmpeg.
    Uses CapCut's bundled ffmpeg if system ffmpeg not in PATH.
    """
    import os

    # Try to find ffmpeg — system PATH first, then bundled fallbacks
    ffmpeg_cmd = "ffmpeg"
    capcut_ffmpeg = os.path.expandvars(
        r"C:\Users\Rainier J. Burlasa\AppData\Local\CapCut\Apps\8.2.0.3462\ffmpeg.exe"
    )
    if _is_ffmpeg_available("ffmpeg"):
        ffmpeg_cmd = "ffmpeg"
    elif os.path.exists(capcut_ffmpeg):
        ffmpeg_cmd = capcut_ffmpeg
    else:
        try:
            import imageio_ffmpeg  # bundled static ffmpeg (no apt needed)
            ffmpeg_cmd = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
        tmp_in.write(audio_bytes)
        tmp_in_path = tmp_in.name

    tmp_out_path = tmp_in_path.replace(".webm", ".wav")

    try:
        subprocess.run(
            [
                ffmpeg_cmd, "-y",
                "-i", tmp_in_path,
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                tmp_out_path
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        with open(tmp_out_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_in_path):
            os.unlink(tmp_in_path)
        if os.path.exists(tmp_out_path):
            os.unlink(tmp_out_path)


def _is_ffmpeg_available(cmd: str) -> bool:
    """Check if ffmpeg is available in PATH."""
    try:
        subprocess.run([cmd, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def extract_features(audio_bytes: bytes, sample_rate: int = 16000) -> dict:
    try:
        # Try direct load first
        try:
            audio_buf = io.BytesIO(audio_bytes)
            y, sr = librosa.load(audio_buf, sr=sample_rate, mono=True)
        except Exception:
            # Direct load failed — convert via ffmpeg first
            wav_bytes = _convert_to_wav(audio_bytes)
            audio_buf = io.BytesIO(wav_bytes)
            y, sr = librosa.load(audio_buf, sr=sample_rate, mono=True)

        if len(y) == 0:
            return _empty_features()

        features = {}

        # ── Pitch (F0) ──────────────────────────────────────────────────────
        f0, voiced_flag, _ = librosa.pyin(
            y,
            fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C7'),
            sr=sr
        )
        voiced_f0 = f0[voiced_flag] if f0 is not None else np.array([])
        features['pitch_mean'] = float(np.mean(voiced_f0)) if len(voiced_f0) > 0 else 0.0
        features['pitch_std']  = float(np.std(voiced_f0))  if len(voiced_f0) > 0 else 0.0

        # ── Energy (RMS) ────────────────────────────────────────────────────
        rms = librosa.feature.rms(y=y)[0]
        features['energy_mean'] = float(np.mean(rms))
        features['energy_std']  = float(np.std(rms))

        # ── Pause Detection ─────────────────────────────────────────────────
        silence_threshold = 0.01
        silent_frames = np.sum(rms < silence_threshold)
        features['pause_ratio'] = float(silent_frames / len(rms)) if len(rms) > 0 else 0.0

        # ── Speech Rate ──────────────────────────────────────────────────────
        onsets = librosa.onset.onset_detect(y=y, sr=sr, units='time')
        duration = librosa.get_duration(y=y, sr=sr)
        features['speech_rate'] = float(len(onsets) / duration) if duration > 0 else 0.0
        features['duration'] = float(duration)

        # ── Jitter ──────────────────────────────────────────────────────────
        if len(voiced_f0) > 1:
            periods = 1.0 / (voiced_f0 + 1e-10)
            jitter = float(
                np.mean(np.abs(np.diff(periods))) / (np.mean(periods) + 1e-10)
            )
        else:
            jitter = 0.0
        features['jitter'] = jitter

        # ── Shimmer ──────────────────────────────────────────────────────────
        if len(rms) > 1:
            shimmer = float(
                np.mean(np.abs(np.diff(rms))) / (np.mean(rms) + 1e-10)
            )
        else:
            shimmer = 0.0
        features['shimmer'] = shimmer

        # ── Zero Crossing Rate ───────────────────────────────────────────────
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        features['zcr_mean'] = float(np.mean(zcr))

        # ── Spectral Features ────────────────────────────────────────────────
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        features['spectral_centroid_mean'] = float(np.mean(spectral_centroid))

        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        features['spectral_rolloff_mean'] = float(np.mean(rolloff))

        # ── MFCCs (13 coefficients) ──────────────────────────────────────────
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        for i, coef in enumerate(mfccs):
            features[f'mfcc_{i+1}_mean'] = float(np.mean(coef))
            features[f'mfcc_{i+1}_std']  = float(np.std(coef))

        # ── Scores ───────────────────────────────────────────────────────────
        features['acoustic_anxiety_score'] = _score_from_features(features)
        features['acoustic_emotion'] = _detect_emotion(features)
        features['acoustic_confidence'] = min(
            1.0,
            features['acoustic_anxiety_score'] + 0.3
        )

        return features

    except Exception as e:
        print(f"[acoustic_features] Extraction error: {e}")
        return _empty_features()


def _score_from_features(f: dict) -> float:
    score = 0.0
    weights = 0.0

    pitch_std = f.get('pitch_std', 0)
    if pitch_std > 0:
        pitch_score = min(pitch_std / 80.0, 1.0)
        score += pitch_score * 0.25
        weights += 0.25

    jitter = f.get('jitter', 0)
    if jitter > 0:
        jitter_score = min(jitter / 0.05, 1.0)
        score += jitter_score * 0.25
        weights += 0.25

    shimmer = f.get('shimmer', 0)
    if shimmer > 0:
        shimmer_score = min(shimmer / 0.30, 1.0)
        score += shimmer_score * 0.20
        weights += 0.20

    pause_ratio = f.get('pause_ratio', 0)
    pause_score = min(pause_ratio / 0.60, 1.0)
    score += pause_score * 0.15
    weights += 0.15

    rate = f.get('speech_rate', 3)
    if rate > 6:
        rate_score = min((rate - 6) / 4.0, 1.0)
    elif rate < 1.5:
        rate_score = min((1.5 - rate) / 1.5, 1.0)
    else:
        rate_score = 0.0
    score += rate_score * 0.15
    weights += 0.15

    if weights > 0:
        score = score / weights * (weights / 1.0)

    return round(min(score, 1.0), 3)


def _detect_emotion(f: dict) -> str:
    pitch_mean  = f.get('pitch_mean', 0)
    pitch_std   = f.get('pitch_std', 0)
    energy_mean = f.get('energy_mean', 0)
    speech_rate = f.get('speech_rate', 3)
    pause_ratio = f.get('pause_ratio', 0)
    jitter      = f.get('jitter', 0)
    shimmer     = f.get('shimmer', 0)

    scores = {'anxious': 0.0, 'sad': 0.0, 'angry': 0.0, 'calm': 0.0}

    if pitch_std > 30:       scores['anxious'] += 0.3
    if speech_rate > 5:      scores['anxious'] += 0.25
    if jitter > 0.02:        scores['anxious'] += 0.25
    if shimmer > 0.15:       scores['anxious'] += 0.20

    if pitch_mean < 150:     scores['sad'] += 0.3
    if speech_rate < 2:      scores['sad'] += 0.3
    if pause_ratio > 0.5:    scores['sad'] += 0.25
    if energy_mean < 0.02:   scores['sad'] += 0.15

    if energy_mean > 0.08:   scores['angry'] += 0.3
    if pitch_mean > 250:     scores['angry'] += 0.25
    if speech_rate > 6:      scores['angry'] += 0.25
    if pause_ratio < 0.1:    scores['angry'] += 0.20

    if 1.5 <= speech_rate <= 4.5: scores['calm'] += 0.3
    if pitch_std < 20:            scores['calm'] += 0.3
    if jitter < 0.01:             scores['calm'] += 0.2
    if 0.1 <= pause_ratio <= 0.3: scores['calm'] += 0.2

    best = max(scores, key=scores.get)
    if scores[best] < 0.2:
        return 'neutral'
    return best


def map_acoustic_to_severity(acoustic_score: float) -> str:
    if acoustic_score >= 0.65:
        return "High"
    if acoustic_score >= 0.35:
        return "Moderate"
    if acoustic_score >= 0.15:
        return "Low"
    return "Normal"


def fuse_with_text_severity(
    acoustic_severity: str,
    text_severity: str,
    acoustic_emotion: str = None,
    acoustic_confidence: float = 1.0,
) -> str:
    order = {'Normal': 0, 'Low': 1, 'Moderate': 2, 'High': 3}
    reverse = {0: 'Normal', 1: 'Low', 2: 'Moderate', 3: 'High'}

    a = order.get(acoustic_severity, 0)
    t = order.get(text_severity, 0)
    fused = max(a, t)

    if acoustic_emotion in ('sad', 'anxious') and fused == 0:
        fused = 1

    return reverse[fused]


def _empty_features() -> dict:
    features = {
        'pitch_mean': 0.0, 'pitch_std': 0.0,
        'energy_mean': 0.0, 'energy_std': 0.0,
        'pause_ratio': 0.0, 'speech_rate': 0.0,
        'duration': 0.0, 'jitter': 0.0, 'shimmer': 0.0,
        'zcr_mean': 0.0, 'spectral_centroid_mean': 0.0,
        'spectral_rolloff_mean': 0.0,
        'acoustic_anxiety_score': 0.0,
        'acoustic_emotion': 'neutral',
        'acoustic_confidence': 0.0,
    }
    for i in range(1, 14):
        features[f'mfcc_{i}_mean'] = 0.0
        features[f'mfcc_{i}_std']  = 0.0
    return features

def log_to_supabase(session_id: str, features: dict) -> bool:
    """
    Persist extracted acoustic features + severity to Supabase.
    Call this right after extract_features() in your voice route.

    Returns True on success, False on failure.
    """
    try:
        from app.database.database import supabase
        from datetime import datetime, timezone

        severity = map_acoustic_to_severity(
            features.get("acoustic_anxiety_score", 0.0)
        )

        row = {
            "session_id":              session_id,
            "timestamp":               datetime.now(timezone.utc).isoformat(),
            "duration":                features.get("duration"),
            "pitch_mean":              features.get("pitch_mean"),
            "pitch_std":               features.get("pitch_std"),
            "energy_mean":             features.get("energy_mean"),
            "energy_std":              features.get("energy_std"),
            "pause_ratio":             features.get("pause_ratio"),
            "speech_rate":             features.get("speech_rate"),
            "jitter":                  features.get("jitter"),
            "shimmer":                 features.get("shimmer"),
            "zcr_mean":                features.get("zcr_mean"),
            "spectral_centroid_mean":  features.get("spectral_centroid_mean"),
            "spectral_rolloff_mean":   features.get("spectral_rolloff_mean"),
            "acoustic_anxiety_score":  features.get("acoustic_anxiety_score"),
            "acoustic_emotion":        features.get("acoustic_emotion"),
            "acoustic_confidence":     features.get("acoustic_confidence"),
            "severity":                severity,
        }

        # Add all 13 MFCCs
        for i in range(1, 14):
            row[f"mfcc_{i}_mean"] = features.get(f"mfcc_{i}_mean")
            row[f"mfcc_{i}_std"]  = features.get(f"mfcc_{i}_std")

        supabase.table("acoustic_logs").insert(row).execute()
        return True

    except Exception as e:
        print(f"[acoustic_features] Supabase log error: {e}")
        return False