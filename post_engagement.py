"""
post_engagement.py
──────────────────
LinkedIn Post Engagement module for Birthday Wishes Agent.

On someone's birthday, instead of just sending a message,
the agent also:
  1. Visits their LinkedIn profile
  2. Finds their latest post
  3. Likes the post
  4. Leaves a thoughtful, birthday-themed comment

This makes the interaction feel more genuine and increases
profile visibility and engagement.

Config in agent.py:
  POST_ENGAGEMENT_ENABLED = True
  ENGAGEMENT_MODE = "both"   # "like", "comment", or "both"
  MAX_ENGAGEMENTS_PER_DAY = 15

Usage:
    from post_engagement import build_post_engagement_task
"""

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_engagement_table():
    """Create the post engagement tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS post_engagements (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                post_url     TEXT,
                action       TEXT    NOT NULL,
                comment_text TEXT,
                date         TEXT    NOT NULL,
                dry_run      INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  Post engagement table ready.")


def log_engagement(
    contact: str,
    action: str,
    post_url: str = "",
    comment_text: str = "",
    dry_run: bool = True,
):
    """Save a post engagement action to the database."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO post_engagements "
            "(contact, post_url, action, comment_text, date, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (contact, post_url, action, comment_text,
             date.today().isoformat(), int(dry_run),
             datetime.now().isoformat()),
        )
        conn.commit()
    logger.info("👍 Engagement logged: [%s] %s → %s", action, contact, post_url[:50] if post_url else "")


def already_engaged_today(contact: str) -> bool:
    """Check if we already engaged with this contact's post today."""
    if not DB_FILE.exists():
        return False
    today = date.today().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT id FROM post_engagements "
            "WHERE contact = ? AND date = ? AND dry_run = 0",
            (contact, today),
        ).fetchone()
    return row is not None


def get_engagements_today() -> int:
    """Return how many post engagements were done today."""
    if not DB_FILE.exists():
        return 0
    today = date.today().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM post_engagements WHERE date = ? AND dry_run = 0",
            (today,),
        ).fetchone()[0]
    return count


# ──────────────────────────────────────────────
# COMMENT TEMPLATES
# ──────────────────────────────────────────────
BIRTHDAY_COMMENT_TEMPLATES = {
    "close_friend": [
        "Amazing post! 🎉 Also — Happy Birthday! Hope your special day is as incredible as you are! 🎂",
        "Love this! 🙌 By the way, wishing you the happiest birthday today! Hope it's a great one! 🥳",
        "Great content as always! 😊 And Happy Birthday! Hope you're celebrating in style today! 🎈",
    ],
    "colleague": [
        "Insightful post! 🌟 Also wishing you a very Happy Birthday today — hope it's a wonderful one! 🎂",
        "Great perspective! 👏 Happy Birthday! Wishing you continued success and a fantastic celebration! 🎉",
        "Really valuable content! Thank you for sharing. Also — Happy Birthday! Hope your day is special! 🎈",
    ],
    "acquaintance": [
        "Great post! 🌟 Happy Birthday by the way — hope you have a wonderful day! 🎂",
        "Thanks for sharing this! Also wishing you a Happy Birthday today! 🎉",
        "Interesting read! Happy Birthday — hope your day is filled with joy! 🥳",
    ],
}


# ──────────────────────────────────────────────
# TASK BUILDER
# ──────────────────────────────────────────────
def build_post_engagement_task(
    birthday_contacts: list[dict],
    dry_run: bool,
    engagement_mode: str = "both",
    max_engagements: int = 15,
) -> str:
    """
    Build a browser agent task to like and/or comment on
    birthday contacts' latest LinkedIn posts.

    Args:
        birthday_contacts : List of dicts with "name", "profile_url", "relationship"
        dry_run           : Whether to simulate or actually engage
        engagement_mode   : "like", "comment", or "both"
        max_engagements   : Maximum engagements per day

    Returns:
        Task string for the browser agent.
    """
    engagements_today = get_engagements_today()
    remaining         = max_engagements - engagements_today

    if remaining <= 0:
        logger.info("📊 Daily engagement limit reached (%d).", max_engagements)
        return ""

    if not birthday_contacts:
        return ""

    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually like or comment on any posts.
  For each action you WOULD take, print:
    [DRY RUN] Would like post of <name>: <post_url>
    [DRY RUN] Would comment on post of <name>: "<comment>"
  Then move on.
""" if dry_run else ""

    # Build contact list
    contact_lines = []
    for c in birthday_contacts[:remaining]:
        name         = c.get("name", "Unknown")
        profile_url  = c.get("profile_url", "")
        relationship = c.get("relationship", "acquaintance")
        templates    = BIRTHDAY_COMMENT_TEMPLATES.get(
            relationship, BIRTHDAY_COMMENT_TEMPLATES["acquaintance"]
        )
        suggested_comment = templates[0]

        contact_lines.append(
            f"  - Name: {name} | Relationship: {relationship}\n"
            f"    Profile: {profile_url or 'Search by name on LinkedIn'}\n"
            f"    Suggested comment: \"{suggested_comment}\""
        )

    contacts_str = "\n".join(contact_lines)

    # Build action instructions based on mode
    if engagement_mode == "like":
        action_instructions = """
    b) Find their most recent post on their profile.
    c) Click the Like button (👍) on the post.
    d) Do NOT leave a comment.
"""
    elif engagement_mode == "comment":
        action_instructions = """
    b) Find their most recent post on their profile.
    c) Click "Comment" on the post.
    d) Write a warm, birthday-themed comment based on the post content.
       Use the suggested comment as a base, but adapt it to fit the post topic naturally.
       Keep it genuine — max 2 sentences.
    e) Post the comment.
    f) Do NOT like the post separately (commenting already shows engagement).
"""
    else:  # both
        action_instructions = """
    b) Find their most recent post on their profile.
    c) Click the Like button (👍) on the post.
    d) Click "Comment" on the post.
    e) Write a warm, birthday-themed comment based on the post content.
       Use the suggested comment as a base, but adapt it to fit the post topic.
       Keep it genuine — max 2 sentences.
    f) Post the comment.
"""

    return f"""
  {dry_run_notice}

  GOAL: Engage with birthday contacts' latest LinkedIn posts.
  This makes the birthday interaction more meaningful and visible.

  Today's birthday contacts to engage with (up to {remaining}):
{contacts_str}

  For each contact:
    a) Go to their LinkedIn profile URL (or search their name).
{action_instructions}
    g) If they have NO recent posts (last 30 days) → skip engagement, just note it.
    h) If already liked/commented today → skip.

  IMPORTANT RULES:
    ✅ Adapt comments to the post topic — don't paste generic text
    ✅ Keep comments warm, positive, and professional
    ❌ Do NOT comment anything negative or controversial
    ❌ Do NOT engage with posts older than 30 days
    ❌ Do NOT spam multiple comments on the same post
    ❌ Stop after {remaining} engagement(s) today

  At the end, provide a summary:
    - Engaged with: (name | action | post topic)
    - Skipped: (name | reason)
    - Any errors
"""


# ──────────────────────────────────────────────
# STANDALONE ENGAGEMENT RUNNER
# ──────────────────────────────────────────────
async def run_post_engagement(
    llm,
    browser,
    birthday_contacts: list[dict],
    dry_run: bool,
    engagement_mode: str = "both",
    max_engagements: int = 15,
) -> str:
    """
    Run the post engagement task for birthday contacts.

    Args:
        llm               : LangChain LLM instance
        browser           : browser_use Browser instance
        birthday_contacts : List of contact dicts
        dry_run           : Simulate or actually engage
        engagement_mode   : "like", "comment", or "both"
        max_engagements   : Daily limit

    Returns:
        Agent result string.
    """
    from browser_use import Agent

    task = build_post_engagement_task(
        birthday_contacts=birthday_contacts,
        dry_run=dry_run,
        engagement_mode=engagement_mode,
        max_engagements=max_engagements,
    )

    if not task:
        logger.info("📭 No post engagements to perform.")
        return "No engagements performed."

    logger.info(
        "=== LinkedIn Post Engagement === [DRY RUN: %s | MODE: %s]",
        dry_run, engagement_mode,
    )

    agent  = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("Post Engagement Result: %s", result)
    return str(result)