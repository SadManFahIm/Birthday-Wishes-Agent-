"""
platforms/whatsapp.py
─────────────────────
Birthday wish detection and reply for WhatsApp Web.

v3.1 — Voice Message Support:
  - Generates a voice message (.mp3) from the reply text
  - Attaches and sends it via WhatsApp Web's file attachment
  - Falls back to text reply if voice generation fails

Config in agent.py:
  VOICE_ENABLED = True   → send voice messages
  VOICE_ENGINE  = "gtts" → "gtts" (free) or "elevenlabs" (premium)
"""

import logging
from pathlib import Path

from browser_use import Agent, Browser
from voice import generate_voice, delete_audio

logger = logging.getLogger(__name__)


async def run_whatsapp_task(
    llm,
    browser: Browser,
    dry_run: bool,
    wish_detection_rules: str,
    reply_templates: list[str],
    filter_notice: str,
    voice_enabled: bool = True,
    voice_engine: str = "gtts",
) -> str:
    """
    Scan WhatsApp Web unread chats and reply to birthday wishes.
    If voice_enabled=True, sends a voice message instead of text.

    Returns the agent's result summary string.
    """
    logger.info(
        "=== WhatsApp: Birthday Wish Reply === [DRY RUN: %s | VOICE: %s (%s)]",
        dry_run, voice_enabled, voice_engine,
    )

    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any messages.
  For each message you WOULD send, print:
    [DRY RUN] Would send to <name>: "<message>"
  Then move on without clicking Send.
""" if dry_run else ""

    reply_templates_str = "\n".join(
        f'  {i+1}. "{t}"' for i, t in enumerate(reply_templates)
    )

    # ── Pre-generate voice files for each template ────────────────
    # We generate voice files ahead of time so the agent can attach them.
    voice_files: dict[int, Path] = {}

    if voice_enabled and not dry_run:
        logger.info("🎙️  Pre-generating voice files...")
        for i, template in enumerate(reply_templates):
            # Use a placeholder name for pre-generation
            sample_text = template.replace("{name}", "friend")
            try:
                audio_path = generate_voice(sample_text, engine=voice_engine)
                voice_files[i] = audio_path
                logger.info("✅ Voice file %d ready: %s", i + 1, audio_path)
            except Exception as e:
                logger.warning("⚠️  Voice generation failed for template %d: %s", i + 1, e)

    # Build voice attachment instructions for the agent
    if voice_enabled and voice_files and not dry_run:
        voice_paths_str = "\n".join(
            f'  Template {i+1}: {path.resolve()}'
            for i, path in voice_files.items()
        )
        voice_instructions = f"""
  VOICE MESSAGE MODE IS ON:
  Instead of typing a text reply, send a VOICE MESSAGE using the pre-generated audio files.

  To send a voice message on WhatsApp Web:
    1. Click the attachment icon (📎) in the chat input area.
    2. Select "Document" or "Audio" option.
    3. Upload the audio file corresponding to the template you chose.
    4. Click Send.

  Pre-generated audio files (choose the one matching your selected template):
{voice_paths_str}

  If attaching audio fails for any reason → fall back to sending the text reply instead.
"""
    else:
        voice_instructions = ""
        if voice_enabled and dry_run:
            voice_instructions = "\n  (Voice messages would be sent in live mode)\n"

    task = f"""
  Open the browser and go to https://web.whatsapp.com

  Wait for the page to fully load.
  If a QR code is shown, wait for the user to scan it with their phone.
  Once logged in, proceed.

  {dry_run_notice}
  {filter_notice}
  {voice_instructions}

  STEP 1 — Find unread chats.
    Look for chats with an unread message badge (green circle with number).
    Check up to 15 unread chats.

  STEP 2 — For each unread chat:
    a) Open the chat.
    b) Read the latest message(s).
    c) Extract the sender's FIRST NAME from the chat name.

  STEP 3 — Detect if it's a birthday wish:
{wish_detection_rules}

  STEP 4 — Reply or Skip.
    If IS a birthday wish AND contact is allowed:
      a) Choose ONE reply template randomly, fill in {{name}} with sender's first name:
{reply_templates_str}

      b) If VOICE MESSAGE MODE is on → attach and send the audio file.
         If voice fails or mode is off → send as text.
         If DRY RUN → just log what you would send.

    If NOT a birthday wish → close chat and move on.

  At the end, provide a summary:
    - Replied to: (names + method used: voice/text)
    - Skipped: (count + reason)
    - Any errors
"""

    agent = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("WhatsApp Result: %s", result)

    # Cleanup generated audio files
    for path in voice_files.values():
        delete_audio(path)

    return str(result)