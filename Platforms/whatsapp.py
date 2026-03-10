"""
platforms/whatsapp.py
─────────────────────
Birthday wish detection and reply for WhatsApp Web.

How it works:
  - Opens WhatsApp Web (web.whatsapp.com)
  - Scans unread chats for birthday wishes
  - Replies with a personalized thank-you message
  - Skips non-birthday messages

Note:
  WhatsApp Web requires QR code scan on first use.
  After scanning, the session is saved in the browser profile.
"""

import logging
from browser_use import Agent, Browser

logger = logging.getLogger(__name__)


async def run_whatsapp_task(
    llm,
    browser: Browser,
    dry_run: bool,
    wish_detection_rules: str,
    reply_templates: list[str],
    filter_notice: str,
) -> str:
    """
    Scan WhatsApp Web unread messages and reply to birthday wishes.

    Returns the agent's result summary string.
    """
    logger.info("=== WhatsApp: Birthday Wish Reply === [DRY RUN: %s]", dry_run)

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

    task = f"""
  Open the browser and go to https://web.whatsapp.com

  Wait for the page to fully load.
  If a QR code is shown, wait for the user to scan it with their phone.
  Once logged in, proceed.

  {dry_run_notice}
  {filter_notice}

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
    If IS a birthday wish AND contact is allowed (check filters):
      Choose ONE reply template randomly, fill in {{name}} with sender's first name,
      then send it (or log it if DRY RUN):
{reply_templates_str}

    If NOT a birthday wish → close chat and move on.

  At the end, provide a summary:
    - Replied to: (names + messages sent)
    - Skipped: (count + reason)
    - Any errors
"""

    agent = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("WhatsApp Result: %s", result)
    return str(result)
