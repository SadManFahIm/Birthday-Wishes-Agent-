"""
platforms/instagram.py
──────────────────────
Birthday wish detection and reply for Instagram DMs.

How it works:
  - Opens Instagram (instagram.com)
  - Logs in with credentials from .env
  - Scans unread DMs for birthday wishes
  - Replies with a personalized thank-you message

Setup:
  Add to your .env file:
    IG_USERNAME=your_instagram_username
    IG_PASSWORD=your_instagram_password
"""

import logging
from browser_use import Agent, Browser
from dotenv import dotenv_values

config = dotenv_values(".env")
logger = logging.getLogger(__name__)

IG_USERNAME = config.get("IG_USERNAME", "")
IG_PASSWORD = config.get("IG_PASSWORD", "")


async def run_instagram_task(
    llm,
    browser: Browser,
    dry_run: bool,
    wish_detection_rules: str,
    reply_templates: list[str],
    filter_notice: str,
) -> str:
    """
    Scan Instagram DMs and reply to birthday wishes.

    Returns the agent's result summary string.
    """
    logger.info("=== Instagram DM: Birthday Wish Reply === [DRY RUN: %s]", dry_run)

    if not IG_USERNAME or not IG_PASSWORD:
        logger.warning("⚠️  IG_USERNAME or IG_PASSWORD not set in .env. Skipping Instagram task.")
        return "Skipped: Instagram credentials not configured."

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
  Open the browser and go to https://www.instagram.com

  Log in with:
    Username: {IG_USERNAME}
    Password: {IG_PASSWORD}

  Handle any 2FA, "Save login info", or "Turn on notifications" popups
  by dismissing them. Wait for the home feed to load.

  Then navigate to Direct Messages:
    Click the paper plane icon (✈️) or go to https://www.instagram.com/direct/inbox/

  {dry_run_notice}
  {filter_notice}

  STEP 1 — Find unread DM threads.
    Look for threads with a bold name or blue unread dot.
    Check up to 15 unread threads.

  STEP 2 — For each unread thread:
    a) Open the thread.
    b) Read the latest message(s).
    c) Extract the sender's FIRST NAME or username from the thread header.
       If it's a username (e.g. "rahul_ahmed99"), use the display name if visible,
       otherwise use the first part before underscore or numbers.

  STEP 3 — Detect if it's a birthday wish:
{wish_detection_rules}

  STEP 4 — Reply or Skip.
    If IS a birthday wish AND contact is allowed (check filters):
      Choose ONE reply template randomly, fill in {{name}} with sender's first name,
      then send it (or log it if DRY RUN):
{reply_templates_str}

    If NOT a birthday wish → go back to inbox and move on.

  At the end, provide a summary:
    - Replied to: (names + messages sent)
    - Skipped: (count + reason)
    - Any errors
"""

    agent = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("Instagram Result: %s", result)
    return str(result)
