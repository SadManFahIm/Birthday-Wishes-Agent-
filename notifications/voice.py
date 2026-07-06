"""
voice.py
--------
AI-Generated Voice Wish Module - Birthday Wishes Agent

Converts birthday wish text into a realistic voice note
and sends it via WhatsApp or saves it for LinkedIn sharing.

Supported engines:
  - gtts      : Google Text-to-Speech (free, no API key needed)
  - elevenlabs: ElevenLabs realistic voice (API key required)

Usage:
    from voice import generate_voice, send_voice_wish

    # Generate voice file
    path = await generate_voice(
        text="Happy Birthday Rahul! Wishing you an amazing day!",
        engine="gtts",         # or "elevenlabs"
        language="en",
        contact_name="Rahul",
    )

    # Send via WhatsApp
    await send_voice_wish(
        llm=llm,
        browser=browser,
        contact_name="Rahul",
        wish_text="Happy Birthday Rahul!",
        engine="gtts",
        dry_run=True,
    )
"""

import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

AUDIO_DIR = Path("audio_messages")
AUDIO_DIR.mkdir(exist_ok=True)

SUPPORTED_ENGINES = ["gtts", "elevenlabs"]

# Language code map for gTTS
GTTS_LANG_MAP = {
    "english":    "en",
    "bengali":    "bn",
    "arabic":     "ar",
    "hindi":      "hi",
    "urdu":       "ur",
    "spanish":    "es",
    "french":     "fr",
    "german":     "de",
    "turkish":    "tr",
    "indonesian": "id",
    "malay":      "ms",
    "chinese":    "zh",
    "japanese":   "ja",
    "korean":     "ko",
    "portuguese": "pt",
    "italian":    "it",
    "russian":    "ru",
}


# ------------------------------------------------------------
# CORE: Generate voice file
# ------------------------------------------------------------

async def generate_voice(
    text: str,
    engine: str = "gtts",
    language: str = "en",
    contact_name: str = "contact",
    voice_id: str = "",
) -> str | None:
    """
    Convert wish text to a voice note file.

    Args:
        text         : The birthday wish text to convert
        engine       : "gtts" or "elevenlabs"
        language     : Language code (e.g. "en", "bn", "ar")
                       or full name (e.g. "bengali", "arabic")
        contact_name : Used for output filename
        voice_id     : ElevenLabs voice ID (optional, uses default if not set)

    Returns:
        Path to the generated .mp3 file, or None on failure.
    """
    engine = engine.lower().strip()

    if engine not in SUPPORTED_ENGINES:
        logger.warning("Unknown voice engine '%s'. Falling back to gtts.", engine)
        engine = "gtts"

    # Normalize language
    lang_code = _resolve_language(language, engine)

    # Build output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() else "_" for c in contact_name)
    filename = AUDIO_DIR / f"wish_{safe_name}_{timestamp}.mp3"

    logger.info("Generating voice wish for '%s' using %s (%s)...",
                contact_name, engine, lang_code)

    if engine == "gtts":
        return await _generate_gtts(text, lang_code, filename)
    elif engine == "elevenlabs":
        return await _generate_elevenlabs(text, voice_id, filename)

    return None


def _resolve_language(language: str, engine: str) -> str:
    """Resolve language name or code to the correct format."""
    lang = language.lower().strip()

    # Already a short code like "en", "bn"
    if len(lang) <= 3 and lang.isalpha():
        return lang

    # Full name like "bengali" -> "bn"
    if lang in GTTS_LANG_MAP:
        return GTTS_LANG_MAP[lang]

    logger.warning("Unknown language '%s'. Defaulting to English.", language)
    return "en"


async def _generate_gtts(text: str, lang: str, output_path: Path) -> str | None:
    """Generate voice using Google Text-to-Speech (free)."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(str(output_path))
        logger.info("gTTS voice saved: %s", output_path)
        return str(output_path)
    except Exception as e:
        logger.error("gTTS failed: %s", e)
        return None


async def _generate_elevenlabs(
    text: str,
    voice_id: str,
    output_path: Path,
) -> str | None:
    """Generate voice using ElevenLabs realistic TTS."""
    try:
        from elevenlabs.client import ElevenLabs
        from dotenv import dotenv_values

        config = dotenv_values(".env")
        api_key = config.get("ELEVENLABS_API_KEY", "")
        if not api_key:
            logger.error("ELEVENLABS_API_KEY missing in .env")
            return None

        # Use voice_id from arg, then .env, then default
        if not voice_id:
            voice_id = config.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

        client = ElevenLabs(api_key=api_key)
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )

        with open(output_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        logger.info("ElevenLabs voice saved: %s", output_path)
        return str(output_path)

    except Exception as e:
        logger.error("ElevenLabs failed: %s", e)
        return None


# ------------------------------------------------------------
# WHATSAPP: Send voice wish
# ------------------------------------------------------------

async def send_voice_wish(
    llm,
    browser,
    contact_name: str,
    wish_text: str,
    engine: str = "gtts",
    language: str = "en",
    voice_id: str = "",
    dry_run: bool = True,
) -> bool:
    """
    Generate a voice wish and send it via WhatsApp Web.

    Args:
        llm          : LangChain LLM instance
        browser      : browser_use Browser instance
        contact_name : WhatsApp contact name
        wish_text    : Birthday wish text to convert to voice
        engine       : "gtts" or "elevenlabs"
        language     : Language code or name
        voice_id     : ElevenLabs voice ID (optional)
        dry_run      : If True, generate file but do not send

    Returns:
        True if sent (or would send in dry run), False on failure.
    """
    from browser_use import Agent

    # Step 1: Generate voice file
    audio_path = await generate_voice(
        text=wish_text,
        engine=engine,
        language=language,
        contact_name=contact_name,
        voice_id=voice_id,
    )

    if not audio_path:
        logger.error("Voice generation failed for %s.", contact_name)
        return False

    abs_path = str(Path(audio_path).resolve())
    logger.info("Voice file ready: %s", abs_path)

    if dry_run:
        logger.info("[DRY RUN] Would send voice note to %s: %s",
                    contact_name, abs_path)
        return True

    # Step 2: Send via WhatsApp Web
    task = f"""
Open WhatsApp Web at https://web.whatsapp.com/

Search for contact: "{contact_name}"
Open their chat.

Send the audio file as a voice message:
  File path: {abs_path}

Steps:
  1. Click the attachment (paperclip) icon
  2. Select "Document" or "Audio" option
  3. Upload the file: {abs_path}
  4. Click Send

Confirm the file was sent successfully.
If the contact is not found, report: CONTACT NOT FOUND: {contact_name}
"""

    try:
        agent = Agent(task=task, llm=llm, browser=browser)
        result = await agent.run()
        logger.info("Voice wish sent to %s: %s", contact_name, result)
        return True
    except Exception as e:
        logger.error("Failed to send voice wish to %s: %s", contact_name, e)
        return False


# ------------------------------------------------------------
# LINKEDIN: Save voice note for manual sharing
# ------------------------------------------------------------

async def prepare_linkedin_voice_wish(
    contact_name: str,
    wish_text: str,
    engine: str = "gtts",
    language: str = "en",
    voice_id: str = "",
) -> str | None:
    """
    Generate a voice wish file ready for LinkedIn sharing.

    LinkedIn does not support automated voice DM sending via browser,
    so this generates the file and returns the path for manual upload
    or future automation.

    Returns:
        Path to the generated audio file.
    """
    audio_path = await generate_voice(
        text=wish_text,
        engine=engine,
        language=language,
        contact_name=contact_name,
        voice_id=voice_id,
    )

    if audio_path:
        logger.info(
            "LinkedIn voice wish ready for %s: %s",
            contact_name, audio_path
        )
        logger.info(
            "Manual step: Upload this file as a LinkedIn voice message to %s",
            contact_name
        )

    return audio_path


# ------------------------------------------------------------
# BATCH: Generate voice wishes for multiple contacts
# ------------------------------------------------------------

async def generate_batch_voice_wishes(
    contacts: list[dict],
    engine: str = "gtts",
    dry_run: bool = True,
) -> list[dict]:
    """
    Generate voice wishes for a list of contacts.

    Args:
        contacts : List of dicts with keys:
                     - name       (str) contact name
                     - wish_text  (str) wish message
                     - language   (str, optional) language code
                     - voice_id   (str, optional) ElevenLabs voice ID
        engine   : "gtts" or "elevenlabs"
        dry_run  : If True, generate files but log only

    Returns:
        List of dicts with name, audio_path, status.
    """
    results = []

    for contact in contacts:
        name      = contact.get("name", "Friend")
        wish_text = contact.get("wish_text", f"Happy Birthday {name}!")
        language  = contact.get("language", "en")
        voice_id  = contact.get("voice_id", "")

        audio_path = await generate_voice(
            text=wish_text,
            engine=engine,
            language=language,
            contact_name=name,
            voice_id=voice_id,
        )

        status = "generated" if audio_path else "failed"

        if dry_run and audio_path:
            logger.info("[DRY RUN] Voice wish for %s ready at: %s", name, audio_path)
            status = "dry_run"

        results.append({
            "name":       name,
            "audio_path": audio_path,
            "status":     status,
        })

    success = sum(1 for r in results if r["status"] != "failed")
    logger.info("Batch voice generation: %d/%d successful.", success, len(results))
    return results


# ------------------------------------------------------------
# UTILS
# ------------------------------------------------------------

def list_voice_files() -> list[str]:
    """List all generated voice files in the audio directory."""
    files = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime, reverse=True)
    return [str(f) for f in files]


def cleanup_old_voice_files(keep_last: int = 50):
    """Delete old voice files, keeping only the most recent ones."""
    files = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime, reverse=True)
    to_delete = files[keep_last:]
    for f in to_delete:
        try:
            f.unlink()
            logger.info("Deleted old voice file: %s", f)
        except Exception as e:
            logger.warning("Could not delete %s: %s", f, e)
    logger.info("Cleanup done. Kept %d files, deleted %d.",
                min(len(files), keep_last), len(to_delete))


def build_voice_instructions(
    contact_name: str,
    audio_path: str,
    platform: str = "whatsapp",
) -> str:
    """Build agent instructions for sending a voice file."""
    abs_path = str(Path(audio_path).resolve())

    if platform == "whatsapp":
        return f"""
  VOICE MESSAGE INSTRUCTIONS:
  Send a voice note to {contact_name} on WhatsApp Web.

  Audio file: {abs_path}

  Steps:
    1. Open https://web.whatsapp.com/
    2. Search for "{contact_name}" and open their chat
    3. Click the attachment (paperclip) icon
    4. Select Audio or Document
    5. Upload: {abs_path}
    6. Click Send

  Report: VOICE SENT: {contact_name} or VOICE FAILED: {contact_name}
"""
    elif platform == "linkedin":
        return f"""
  VOICE MESSAGE - LINKEDIN:
  LinkedIn does not support automated voice DM upload.
  The voice file has been generated and is ready for manual upload.

  Contact : {contact_name}
  File    : {abs_path}

  Manual steps:
    1. Open LinkedIn -> Messages -> {contact_name}
    2. Click the attachment icon
    3. Upload: {abs_path}
    4. Send

  Report: VOICE READY: {contact_name} - {abs_path}
"""
    return f"Voice file for {contact_name}: {abs_path}"