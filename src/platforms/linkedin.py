"""
platforms/linkedin.py
─────────────────────
LinkedIn birthday detection with:
  - AI-generated custom wishes (v3.1)
  - Contact Relationship Score (v3.2)

The agent now:
  1. Finds today's birthday contacts
  2. Visits each profile
  3. Assesses the relationship (close friend / colleague / acquaintance)
  4. Picks the appropriate wish style
  5. Generates a unique personalized wish using the LLM
  6. Sends it
"""

import logging
from browser_use import Agent, Browser
from relationship import build_relationship_detection_instructions
from smart_timing import build_timing_instructions

logger = logging.getLogger(__name__)


async def run_linkedin_birthday_with_custom_wish(
    llm,
    browser: Browser,
    dry_run: bool,
    username: str,
    password: str,
    already_logged_in: bool,
    filter_notice: str,
    wish_detection_rules: str,
    contacts_with_locations: list[dict] = None,
) -> str:
    """
    Detect LinkedIn birthday contacts, score the relationship,
    and send a personalized AI-generated wish.
    """
    logger.info(
        "=== LinkedIn: AI Custom Birthday Wishes + Relationship Score === [DRY RUN: %s]",
        dry_run,
    )

    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any messages.
  For each wish you WOULD send, print:
    [DRY RUN] Would send to <n> (<relationship>): "<wish>"
  Then move on without clicking Send.
""" if dry_run else ""

    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {username}\n"
            f"  Password: {password}\n"
            "Handle MFA if prompted.\n"
        )
    )

    relationship_instructions = build_relationship_detection_instructions()

    timing_instructions = ""
    if contacts_with_locations:
        timing_instructions = build_timing_instructions(contacts_with_locations)

    task = f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice}
  {filter_notice}
  {timing_instructions}

  GOAL: Find contacts with birthdays TODAY, understand your relationship
  with each one, and send a personalized birthday wish that matches
  the relationship style.

  ═══════════════════════════════════════════
  STEP 1 — Find today's birthdays.
  ═══════════════════════════════════════════
    Go to https://www.linkedin.com/mynetwork/
    Find the "Birthdays" section or "Say happy birthday" buttons.
    Also check the notification bell 🔔.
    Collect up to 20 contacts with birthdays today.

  ═══════════════════════════════════════════
  STEP 2 — For each birthday contact:
  ═══════════════════════════════════════════

    a) Apply contact filters (blacklist, whitelist, cooldown). Skip if needed.

    b) Visit their LinkedIn profile.

    c) Assess the relationship:
{relationship_instructions}

    d) Collect profile details for personalization:
       - First name
       - Current job title
       - Current company
       - Any recent posts, achievements, or shared interests

    e) Compose a UNIQUE birthday wish that:
       - Matches the relationship style (see below)
       - Mentions their job/company naturally if relevant
       - Feels genuine, not template-like
       - Is 2-3 sentences max
       - Has 1-2 relevant emojis

       WISH STYLES BY RELATIONSHIP:

       🟢 close_friend → Casual, warm, funny, personal:
          Example: "Hey Rahul! 🥳 Can't believe another year has gone by —
          hope today is as incredible as you always make everything around you.
          Let's catch up soon! 🎉"

       🔵 colleague → Professional but friendly:
          Example: "Happy Birthday Priya! 💼 It's been such a pleasure
          collaborating with you this year. Wishing you continued success
          and a day as brilliant as your work! 🌟"

       ⚪ acquaintance → Polite, brief, warm:
          Example: "Happy Birthday Ahmed! 🎂 Hope you have a wonderful
          day and a fantastic year ahead!"

    f) Send the wish via LinkedIn messaging.
       (Or log it if DRY RUN)

  ═══════════════════════════════════════════
  STEP 3 — Summary
  ═══════════════════════════════════════════
  At the end, provide a detailed summary table:

  | Name | Relationship | Job | Wish Sent |
  |------|-------------|-----|-----------|
  | ...  | ...         | ... | ...       |

  Total wished: X
  Breakdown: X close friends, X colleagues, X acquaintances
  Skipped: X (reason)
"""

    agent = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("LinkedIn AI Wish Result: %s", result)
    return str(result)