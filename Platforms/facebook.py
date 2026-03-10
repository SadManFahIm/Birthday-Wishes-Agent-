"""
platforms/facebook.py
─────────────────────
Birthday wish detection and reply for Facebook Messenger.

How it works:
  - Opens Facebook Messenger (messenger.com)
  - Logs in with credentials from .env
  - Scans unread message threads for birthday wishes
  - Replies with a personalized thank-you message

Setup:
  Add to your .env file:
    FB_USERNAME=your_facebook_email
    FB_PASSWORD=your_facebook_password
"""

import logging
from browser_use import Agent, Browser
from dotenv import dotenv_values

config = dotenv_values(".env")
logger = logging.getLogger(__name__)

FB_USERNAME = config.get("FB_USERNAME", "")
FB_PASSWORD = config.get("FB_PASSWORD", "")


async def run_facebook_task(
    llm,
    browser: Browser,
    dry_run: bool,
    wish_detection_rules: str,
    reply_templates: list[str],
    filter_notice: str,
) -> str:
    """
    Scan Facebook Messenger unread messages and reply to birthday wishes.

    Returns the agent's result summary string.
    """
    logger.info("=== Facebook Messenger: Birthday Wish Reply === [DRY RUN: %s]", dry_run)

    if not FB_USERNAME or not FB_PASSWORD:
        logger.warning("⚠️  FB_USERNAME or FB_PASSWORD not set in .env. Skipping Facebook task.")
        return "Skipped: Facebook credentials not configured."

    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any messages.
  For each message you WOULD send, print:
    [DRY RUN] Would send to <n>: "<message>"
  Then move on without clicking Send.
""" if dry_run else ""

    reply_templates_str = "\n".join(
        f'  {i+1}. "{t}"' for i, t in enumerate(reply_templates)
    )

    task = f"""
  Open the browser and go to https://www.messenger.com

  Log in with:
    Email:    {FB_USERNAME}
    Password: {FB_PASSWORD}

  Handle any 2FA or verification prompts if they appear (wait for user if needed).
  Once logged in, proceed.

  {dry_run_notice}
  {filter_notice}

  STEP 1 — Find unread message threads.
    Look for conversations with a bold name or unread indicator.
    Check up to 15 unread threads.

  STEP 2 — For each unread thread:
    a) Open the thread.
    b) Read the latest message(s).
    c) Extract the sender's FIRST NAME from the conversation header.

  STEP 3 — Detect if it's a birthday wish:
{wish_detection_rules}

  STEP 4 — Reply or Skip.
    If IS a birthday wish AND contact is allowed (check filters):
      Choose ONE reply template randomly, fill in {{name}} with sender's first name,
      then send it (or log it if DRY RUN):
{reply_templates_str}

    If NOT a birthday wish → close thread and move on.

  At the end, provide a summary:
    - Replied to: (names + messages sent)
    - Skipped: (count + reason)
    - Any errors
"""

    agent = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("Facebook Result: %s", result)
    return str(result)
