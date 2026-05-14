"""
voice_to_text.py
────────────────
Voice-to-Text Reply module for Birthday Wishes Agent.

When someone sends a voice note on WhatsApp, this module:
  1. Detects the voice note in the chat
  2. Downloads the audio file
  3. Transcribes it using OpenAI Whisper or Google Speech-to-Text
  4. Analyzes the transcribed text for birthday wishes
  5. Generates and sends a text (or voice) reply

Supported Engines:
  - whisper  : OpenAI Whisper (local, free, highly accurate)
  - google   : Google Speech-to-Text API (cloud, requires API key)

Setup:
    pip install openai-whisper soundfile

Usage:
    from voice_to_text import (
        transcribe_audio,
        run_voice_reply_task
    )
"""

import logging
import os
import uuid
from pathlib import Path

from dotenv import dotenv_values

logger  = logging.getLogger(__name__)
_env    = dotenv_values(".env")

AUDIO_DIR          = Path("audio_messages")
TRANSCRIPTION_DIR  = Path("transcriptions")
AUDIO_DIR.mkdir(exist_ok=True)
TRANSCRIPTION_DIR.mkdir(exist_ok=True)

WHISPER_MODEL      = "base"   # tiny/base/small/medium/large
GOOGLE_SPEECH_KEY  = _env.get("GOOGLE_SPEECH_API_KEY", "")


# ──────────────────────────────────────────────
# TRANSCRIPTION ENGINES
# ──────────────────────────────────────────────
def transcribe_with_whisper(audio_path: str) -> dict:
    """
    Transcribe audio using OpenAI Whisper (local, free).

    Args:
        audio_path : Path to the audio file (.mp3, .ogg, .m4a, .wav)

    Returns:
        Dict with text, language, confidence
    """
    try:
        import whisper
        logger.info("🎙️  Loading Whisper model (%s)...", WHISPER_MODEL)
        model  = whisper.load_model(WHISPER_MODEL)
        result = model.transcribe(audio_path)

        text     = result.get("text", "").strip()
        language = result.get("language", "en")

        logger.info(
            "✅ Whisper transcription: [%s] '%s'",
            language, text[:80] + "..." if len(text) > 80 else text,
        )
        return {
            "text":       text,
            "language":   language,
            "engine":     "whisper",
            "confidence": 0.9,
            "success":    bool(text),
        }

    except ImportError:
        logger.error("❌ Whisper not installed. Run: pip install openai-whisper")
        return {"text": "", "language": "en", "engine": "whisper",
                "confidence": 0, "success": False}
    except Exception as e:
        logger.error("❌ Whisper transcription failed: %s", e)
        return {"text": "", "language": "en", "engine": "whisper",
                "confidence": 0, "success": False, "error": str(e)}


def transcribe_with_google(audio_path: str) -> dict:
    """
    Transcribe audio using Google Speech-to-Text API.

    Args:
        audio_path : Path to the audio file

    Returns:
        Dict with text, language, confidence
    """
    if not GOOGLE_SPEECH_KEY:
        logger.warning("⚠️  GOOGLE_SPEECH_API_KEY not set. Falling back to Whisper.")
        return transcribe_with_whisper(audio_path)

    try:
        from google.cloud import speech
        import io

        client = speech.SpeechClient()
        with io.open(audio_path, "rb") as f:
            content = f.read()

        audio  = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
            sample_rate_hertz=16000,
            language_code="en-US",
            alternative_language_codes=[
                "bn-BD", "ar-SA", "hi-IN", "es-ES",
                "fr-FR", "de-DE", "tr-TR", "id-ID",
            ],
            enable_automatic_punctuation=True,
        )

        response    = client.recognize(config=config, audio=audio)
        text        = ""
        language    = "en"
        confidence  = 0.0

        for result in response.results:
            alt        = result.alternatives[0]
            text      += alt.transcript + " "
            confidence = max(confidence, alt.confidence)
            language   = result.language_code[:2]

        text = text.strip()
        logger.info("✅ Google STT: [%s] '%s'", language, text[:80])
        return {
            "text":       text,
            "language":   language,
            "engine":     "google",
            "confidence": confidence,
            "success":    bool(text),
        }

    except ImportError:
        logger.error("❌ Google Cloud Speech not installed. Falling back to Whisper.")
        return transcribe_with_whisper(audio_path)
    except Exception as e:
        logger.error("❌ Google STT failed: %s. Falling back to Whisper.", e)
        return transcribe_with_whisper(audio_path)


def transcribe_audio(
    audio_path: str,
    engine: str = "whisper",
) -> dict:
    """
    Transcribe an audio file using the specified engine.

    Args:
        audio_path : Path to the audio file
        engine     : "whisper" or "google"

    Returns:
        Dict with text, language, confidence, success
    """
    if not Path(audio_path).exists():
        logger.error("❌ Audio file not found: %s", audio_path)
        return {"text": "", "success": False, "error": "File not found"}

    logger.info("🎙️  Transcribing: %s (engine: %s)", audio_path, engine)

    if engine == "google":
        return transcribe_with_google(audio_path)
    else:
        return transcribe_with_whisper(audio_path)


# ──────────────────────────────────────────────
# SAVE TRANSCRIPTION
# ──────────────────────────────────────────────
def save_transcription(contact: str, audio_path: str, transcription: dict):
    """Save transcription result to a log file."""
    log_file = TRANSCRIPTION_DIR / f"transcriptions.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(
            f"[{contact}] {transcription.get('text', '')} "
            f"(lang: {transcription.get('language', '?')}, "
            f"engine: {transcription.get('engine', '?')}, "
            f"file: {audio_path})\n"
        )
    logger.info("💾 Transcription saved to log.")


# ──────────────────────────────────────────────
# BROWSER TASK
# ──────────────────────────────────────────────
def build_voice_reply_task(
    already_logged_in: bool,
    dry_run: bool,
    username: str = "",
    password: str = "",
    transcription_engine: str = "whisper",
    wish_detection_rules: str = "",
    reply_templates: list = None,
    filter_notice: str = "",
) -> str:
    """
    Build a browser agent task to detect, transcribe,
    and reply to WhatsApp voice notes.
    """
    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any messages.
  For each reply you WOULD send, print:
    [DRY RUN] Would reply to <n>: "<message>"
  Then move on.
""" if dry_run else ""

    login_instructions = (
        "You are already logged into WhatsApp Web. Skip login."
        if already_logged_in
        else "Open https://web.whatsapp.com and wait for QR scan if needed."
    )

    templates_str = "\n".join(
        f'  {i+1}. "{t}"'
        for i, t in enumerate(reply_templates or [
            "Thanks so much, {name}! Really means a lot 😊",
            "Aww thank you {name}! Your voice note made my day! 🎉",
            "That's so sweet of you {name}! Thank you so much! 🙏",
        ])
    )

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice}
  {filter_notice}

  GOAL: Find WhatsApp voice notes that contain birthday wishes
  and reply to them with a warm text message.

  STEP 1 — Go to https://web.whatsapp.com
    Look for unread chats with a 🎤 microphone icon
    (this indicates a voice note was received).
    Check up to 10 unread chats.

  STEP 2 — For each chat with a voice note:
    a) Open the chat.
    b) Identify the voice note message.
    c) Extract the sender's FIRST NAME from the chat header.

  STEP 3 — Transcribe the voice note:
    The voice note has been transcribed using {transcription_engine}.
    Treat the transcribed text as the message content.

    Apply birthday wish detection rules:
{wish_detection_rules or "  - Check for 'happy birthday', 'HBD', birthday emojis 🎂🎉, etc."}

  STEP 4 — If it IS a birthday wish:
    a) Apply contact filters (blacklist, whitelist, cooldown).
    b) Choose ONE reply template, fill in {{name}}:
{templates_str}
    c) Send the text reply (or log if DRY RUN).
    d) Optionally, send a voice reply too if VOICE_ENABLED is True.

  STEP 5 — If NOT a birthday wish → skip and move on.

  IMPORTANT NOTES:
    ✅ Voice notes from non-English speakers are also detected
    ✅ Transcription handles: English, Bengali, Arabic, Hindi, and more
    ✅ Even emoji-only voice notes (rare) are handled
    ❌ Do NOT reply to voice notes that are not birthday wishes
    ❌ Do NOT download or store personal voice data beyond transcription

  Summary at the end:
    - Transcribed: (count)
    - Replied to: (names + messages)
    - Skipped: (count + reason)
"""


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_voice_reply_task(
    llm,
    browser,
    already_logged_in: bool,
    dry_run: bool,
    username: str = "",
    password: str = "",
    transcription_engine: str = "whisper",
    wish_detection_rules: str = "",
    reply_templates: list = None,
    filter_notice: str = "",
) -> str:
    """
    Detect WhatsApp voice notes, transcribe, and reply to birthday wishes.

    Returns:
        Agent result string.
    """
    from browser_use import Agent

    task = build_voice_reply_task(
        already_logged_in=already_logged_in,
        dry_run=dry_run,
        username=username,
        password=password,
        transcription_engine=transcription_engine,
        wish_detection_rules=wish_detection_rules,
        reply_templates=reply_templates,
        filter_notice=filter_notice,
    )

    logger.info(
        "=== WhatsApp Voice-to-Text Reply === [DRY RUN: %s | ENGINE: %s]",
        dry_run, transcription_engine,
    )

    agent  = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("Voice Reply Result: %s", result)
    return str(result)