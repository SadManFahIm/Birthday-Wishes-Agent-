"""
voice.py
────────
Text-to-Speech module for the Birthday Wishes Agent.

Supports two TTS engines:
  1. gTTS  (free, Google Text-to-Speech)
  2. ElevenLabs (premium, very realistic voices)

Setup:
  gTTS:
    pip install gTTS
    No API key needed.

  ElevenLabs:
    pip install elevenlabs
    Add to .env:
      ELEVENLABS_API_KEY=your_api_key
      ELEVENLABS_VOICE_ID=your_voice_id  (optional, defaults to "Rachel")

Usage:
    from voice import generate_voice

    path = generate_voice("Happy Birthday Rahul!", engine="gtts")
    # returns Path to the generated .mp3 file
"""

import logging
import uuid
from pathlib import Path

from dotenv import dotenv_values

config = dotenv_values(".env")
logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = config.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = config.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Default: Rachel

# Folder where generated audio files are saved
AUDIO_DIR = Path("audio_messages")
AUDIO_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────
# gTTS ENGINE (Free)
# ──────────────────────────────────────────────
def generate_gtts(text: str, lang: str = "en") -> Path:
    """
    Generate a voice message using Google Text-to-Speech (gTTS).

    Args:
        text : The message to convert to speech.
        lang : Language code (e.g. "en", "bn", "ar", "hi"). Default: "en"

    Returns:
        Path to the generated .mp3 file.
    """
    try:
        from gtts import gTTS
    except ImportError:
        raise ImportError("gTTS not installed. Run: pip install gTTS")

    filename = AUDIO_DIR / f"voice_{uuid.uuid4().hex[:8]}.mp3"
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(str(filename))
    logger.info("🎙️  gTTS audio saved: %s", filename)
    return filename


# ──────────────────────────────────────────────
# ELEVENLABS ENGINE (Premium)
# ──────────────────────────────────────────────
def generate_elevenlabs(text: str) -> Path:
    """
    Generate a realistic voice message using ElevenLabs API.

    Args:
        text : The message to convert to speech.

    Returns:
        Path to the generated .mp3 file.
    """
    if not ELEVENLABS_API_KEY:
        raise ValueError(
            "ELEVENLABS_API_KEY not set in .env. "
            "Get your key from https://elevenlabs.io"
        )

    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import save
    except ImportError:
        raise ImportError("ElevenLabs not installed. Run: pip install elevenlabs")

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    audio = client.generate(
        text=text,
        voice=ELEVENLABS_VOICE_ID,
        model="eleven_multilingual_v2",  # Supports multiple languages
    )

    filename = AUDIO_DIR / f"voice_{uuid.uuid4().hex[:8]}.mp3"
    save(audio, str(filename))
    logger.info("🎙️  ElevenLabs audio saved: %s", filename)
    return filename


# ──────────────────────────────────────────────
# DETECT LANGUAGE FOR gTTS
# ──────────────────────────────────────────────
def detect_lang(text: str) -> str:
    """
    Simple language detection for gTTS.
    Checks for non-ASCII characters to guess the language.
    Falls back to English.
    """
    # Bengali
    if any("\u0980" <= c <= "\u09FF" for c in text):
        return "bn"
    # Arabic
    if any("\u0600" <= c <= "\u06FF" for c in text):
        return "ar"
    # Hindi / Devanagari
    if any("\u0900" <= c <= "\u097F" for c in text):
        return "hi"
    # Default English
    return "en"


# ──────────────────────────────────────────────
# MAIN FUNCTION
# ──────────────────────────────────────────────
def generate_voice(text: str, engine: str = "gtts") -> Path:
    """
    Generate a voice message from text.

    Args:
        text   : The message to convert to speech.
        engine : "gtts" (free) or "elevenlabs" (premium). Default: "gtts"

    Returns:
        Path to the generated audio file.

    Example:
        path = generate_voice("Happy Birthday Rahul!", engine="gtts")
        print(path)  # audio_messages/voice_a1b2c3d4.mp3
    """
    engine = engine.lower().strip()

    if engine == "elevenlabs":
        return generate_elevenlabs(text)
    elif engine == "gtts":
        lang = detect_lang(text)
        return generate_gtts(text, lang=lang)
    else:
        raise ValueError(f"Unknown engine: '{engine}'. Use 'gtts' or 'elevenlabs'.")


# ──────────────────────────────────────────────
# CLEANUP
# ──────────────────────────────────────────────
def delete_audio(path: Path):
    """Delete a generated audio file after it has been sent."""
    try:
        path.unlink()
        logger.info("🗑️  Deleted audio file: %s", path)
    except Exception as e:
        logger.warning("⚠️  Could not delete audio file: %s — %s", path, e)
