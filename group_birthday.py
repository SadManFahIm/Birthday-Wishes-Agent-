"""
group_birthday.py
─────────────────
LinkedIn Group Birthday Detection module.

Detects birthday wishes posted in LinkedIn Groups and
responds with a congratulatory group post or comment.

How it works:
  1. Scans LinkedIn Groups the user is a member of
  2. Finds posts where members are wishing someone a birthday
  3. Likes the post and/or adds a warm comment
  4. Optionally sends a direct message to the birthday person

Features:
  - Auto-detects birthday posts in groups
  - Likes and comments on group birthday posts
  - Sends direct wish to the birthday person
  - Tracks all actions in SQLite
  - Daily limit to avoid spam

Config in agent.py:
  GROUP_BIRTHDAY_ENABLED   = True
  MAX_GROUP_ENGAGEMENTS    = 10
  GROUP_COMMENT_ENABLED    = True
  GROUP_DM_ENABLED         = True
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
def init_group_birthday_table():
    """Create group birthday tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS group_birthdays (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name    TEXT    NOT NULL,
                contact       TEXT    NOT NULL,
                post_url      TEXT,
                action        TEXT    NOT NULL,
                comment_text  TEXT,
                date          TEXT    NOT NULL,
                dry_run       INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  Group birthday table ready.")


def log_group_action(
    group_name: str,
    contact: str,
    action: str,
    post_url: str = "",
    comment_text: str = "",
    dry_run: bool = True,
):
    """Log a group birthday action to the database."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO group_birthdays "
            "(group_name, contact, post_url, action, comment_text, date, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (group_name, contact, post_url, action, comment_text,
             date.today().isoformat(), int(dry_run), datetime.now().isoformat()),
        )
        conn.commit()
    logger.info("🗄️  Group action logged: [%s] %s in %s", action, contact, group_name)


def get_group_engagements_today() -> int:
    """Return how many group engagements were done today."""
    if not DB_FILE.exists():
        return 0
    today = date.today().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM group_birthdays WHERE date = ? AND dry_run = 0",
            (today,),
        ).fetchone()[0]
    return count


def already_engaged_in_group(contact: str, group_name: str) -> bool:
    """Check if we already engaged with this contact in this group today."""
    if not DB_FILE.exists():
        return False
    today = date.today().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT id FROM group_birthdays "
            "WHERE LOWER(contact) = LOWER(?) AND LOWER(group_name) = LOWER(?) "
            "AND date = ? AND dry_run = 0",
            (contact, group_name, today),
        ).fetchone()
    return row is not None


# ──────────────────────────────────────────────
# COMMENT TEMPLATES
# ──────────────────────────────────────────────
GROUP_COMMENT_TEMPLATES = [
    "Happy Birthday {name}! 🎂 Hope you have an absolutely wonderful day! 🎉",
    "Wishing {name} a very Happy Birthday! 🥳 Hope it's filled with joy and celebration!",
    "Happy Birthday {name}! 🎈 May this year bring you great success and happiness!",
    "Many happy returns {name}! 🎂 Hope your special day is everything you wished for! 🌟",
    "Happy Birthday {name}! 🎁 Wishing you all the best on your special day! 🎉",
]

GROUP_DM_TEMPLATES = [
    "Hi {name}! Saw the birthday wishes in the group — Happy Birthday! 🎂 Hope you're having a fantastic day!",
    "Hey {name}! Happy Birthday! 🎉 Saw everyone wishing you in the group — hope it's been an amazing day!",
    "Happy Birthday {name}! 🥳 The group is celebrating you today — hope you're enjoying every moment!",
]


# ──────────────────────────────────────────────
# TASK BUILDER
# ──────────────────────────────────────────────
def build_group_birthday_task(
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool,
    max_engagements: int = 10,
    comment_enabled: bool = True,
    dm_enabled: bool = True,
) -> str:
    """
    Build a browser agent task to find and engage with
    birthday posts in LinkedIn Groups.
    """
    engagements_today = get_group_engagements_today()
    remaining         = max_engagements - engagements_today

    if remaining <= 0:
        logger.info("📊 Daily group engagement limit reached.")
        return ""

    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually like, comment, or send messages.
  For each action you WOULD take, print:
    [DRY RUN] Would <action> for <name> in <group>: "<text>"
  Then move on.
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

    comment_instruction = """
    c) COMMENT on the post:
       Write a warm, birthday-themed comment (1-2 sentences).
       Address the birthday person by name.
       Example: "Happy Birthday {name}! 🎂 Hope you have a wonderful day!"
       Keep it genuine — adapt to the group's tone.
""" if comment_enabled else ""

    dm_instruction = """
    e) DIRECT MESSAGE the birthday person:
       Go to their profile and send a short personal DM.
       Example: "Hi {name}! Saw the birthday wishes in the group —
                 Happy Birthday! 🎂 Hope you're having a fantastic day!"
       Only send if they are a 1st or 2nd degree connection.
""" if dm_enabled else ""

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice}

  GOAL: Find birthday posts in LinkedIn Groups and engage with them.

  STEP 1 — Go to LinkedIn Groups.
    Visit https://www.linkedin.com/groups/
    You will see a list of groups you are a member of.

  STEP 2 — For each group (check up to 5 groups):
    a) Open the group feed.
    b) Look for posts from TODAY that mention a birthday:
       - Posts with "Happy Birthday", "HBD", "🎂", "🎉", "🥳"
       - Posts wishing a specific member
       - Posts with many birthday-related comments

  STEP 3 — For each birthday post found:
    a) Extract the birthday person's name.
    b) Check: have we already engaged with this person in this group today?
       If yes → skip.

    c) LIKE the post (👍).
{comment_instruction}
    d) Note the birthday person's name and group for logging.
{dm_instruction}

  STEP 4 — Stop after {remaining} engagement(s) today.

  RULES:
    ✅ Only engage with posts from TODAY
    ✅ Keep comments warm and group-appropriate
    ❌ Do NOT comment on old posts
    ❌ Do NOT send DMs to 3rd degree connections
    ❌ Do NOT engage with the same person twice today

  At the end, provide a summary:
    | Group | Birthday Person | Actions Taken |
    |-------|----------------|---------------|
    | ...   | ...            | like, comment, DM |

  Total engagements: X
  Skipped: X (reason)
"""


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_group_birthday_detection(
    llm,
    browser,
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool,
    max_engagements: int = 10,
    comment_enabled: bool = True,
    dm_enabled: bool = True,
) -> str:
    """
    Detect and engage with birthday posts in LinkedIn Groups.

    Returns:
        Agent result string.
    """
    from browser_use import Agent

    task = build_group_birthday_task(
        username=username,
        password=password,
        already_logged_in=already_logged_in,
        dry_run=dry_run,
        max_engagements=max_engagements,
        comment_enabled=comment_enabled,
        dm_enabled=dm_enabled,
    )

    if not task:
        logger.info("📭 No group engagements to perform.")
        return "No group engagements performed."

    logger.info(
        "=== LinkedIn Group Birthday Detection === [DRY RUN: %s]", dry_run
    )

    agent  = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("Group Birthday Result: %s", result)
    return str(result)