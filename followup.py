"""
followup.py
───────────
Follow-up Message module for Birthday Wishes Agent.

After sending a birthday wish, this module:
  1. Saves the contact + wish date to SQLite DB
  2. Checks daily for contacts whose birthday was 2-3 days ago
  3. Sends a warm follow-up message via LinkedIn/WhatsApp

Follow-up styles by relationship:
  - close_friend  : Casual check-in
  - colleague     : Professional follow-up
  - acquaintance  : Brief, polite check-in

Setup:
  - Runs automatically via the daily scheduler
  - No extra configuration needed
  - FOLLOWUP_DAYS controls when to send (default: 2 days after birthday)
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_FILE      = Path("agent_history.db")
FOLLOWUP_DAYS = 2   # Send follow-up X days after birthday wish


# ──────────────────────────────────────────────
# FOLLOW-UP TEMPLATES BY RELATIONSHIP
# ──────────────────────────────────────────────
FOLLOWUP_TEMPLATES = {
    "close_friend": [
        "Hey {name}! Hope your birthday was absolutely amazing! 🎉 Did you celebrate? Would love to hear all about it!",
        "Hey {name}! Just checking in — hope the birthday celebrations were epic! 🥳 You deserve all the fun!",
        "Hi {name}! Hope you had the most incredible birthday! 🎂 Thinking of you and hope everything was just perfect!",
    ],
    "colleague": [
        "Hi {name}! Hope you had a wonderful birthday celebration! 🎉 Wishing you continued success in the days ahead!",
        "Hello {name}! Just wanted to check in and hope your birthday was fantastic! 🌟 Looking forward to more great work together!",
        "Hi {name}! Hope your special day was everything you wished for! 🎂 Wishing you all the best going forward!",
    ],
    "acquaintance": [
        "Hi {name}! Hope you had a lovely birthday! 🎂 Wishing you all the best!",
        "Hello {name}! Just wanted to check in — hope your birthday was wonderful! 🎉",
        "Hi {name}! Hope the birthday celebrations were great! 🥳 Wishing you a fantastic year ahead!",
    ],
}


# ──────────────────────────────────────────────
# DB HELPERS
# ──────────────────────────────────────────────
def init_followup_table():
    """Create the followup tracking table if it doesn't exist."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS followups (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                contact         TEXT    NOT NULL,
                platform        TEXT    NOT NULL,
                relationship    TEXT    NOT NULL DEFAULT 'acquaintance',
                wish_date       TEXT    NOT NULL,
                followup_date   TEXT,
                followup_sent   INTEGER NOT NULL DEFAULT 0,
                dry_run         INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  Follow-up table ready.")


def schedule_followup(
    contact: str,
    platform: str,
    relationship: str = "acquaintance",
    dry_run: bool = True,
):
    """
    Schedule a follow-up message for a contact.
    Called right after a birthday wish is sent.

    Args:
        contact      : Contact's first name
        platform     : "linkedin", "whatsapp", "facebook", "instagram"
        relationship : "close_friend", "colleague", "acquaintance"
        dry_run      : Whether this was a dry run
    """
    wish_date     = date.today().isoformat()
    followup_date = (date.today() + timedelta(days=FOLLOWUP_DAYS)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        # Check if already scheduled
        existing = conn.execute(
            "SELECT id FROM followups WHERE contact = ? AND wish_date = ?",
            (contact, wish_date),
        ).fetchone()

        if existing:
            logger.info("⏭️  Follow-up already scheduled for %s", contact)
            return

        conn.execute(
            "INSERT INTO followups "
            "(contact, platform, relationship, wish_date, followup_date, followup_sent, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
            (contact, platform, relationship, wish_date,
             followup_date, int(dry_run), datetime.now().isoformat()),
        )
        conn.commit()

    logger.info(
        "📅 Follow-up scheduled for %s on %s (platform: %s)",
        contact, followup_date, platform,
    )


def get_pending_followups() -> list[dict]:
    """
    Get all follow-ups that are due today (not yet sent).

    Returns:
        List of dicts with contact info.
    """
    if not DB_FILE.exists():
        return []

    today = date.today().isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT id, contact, platform, relationship, wish_date, followup_date "
            "FROM followups "
            "WHERE followup_date <= ? AND followup_sent = 0",
            (today,),
        ).fetchall()

    pending = [
        {
            "id":           row[0],
            "contact":      row[1],
            "platform":     row[2],
            "relationship": row[3],
            "wish_date":    row[4],
            "followup_date": row[5],
        }
        for row in rows
    ]

    if pending:
        logger.info("📬 %d follow-up(s) due today.", len(pending))
    return pending


def mark_followup_sent(followup_id: int):
    """Mark a follow-up as sent in the database."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE followups SET followup_sent = 1 WHERE id = ?",
            (followup_id,),
        )
        conn.commit()
    logger.info("✅ Follow-up #%d marked as sent.", followup_id)


# ──────────────────────────────────────────────
# FOLLOW-UP TASK BUILDER
# ──────────────────────────────────────────────
def build_followup_task(
    pending: list[dict],
    dry_run: bool,
    username: str,
    password: str,
    already_logged_in: bool,
) -> str:
    """
    Build a browser agent task to send all pending follow-ups.

    Args:
        pending          : List of pending follow-up dicts
        dry_run          : Whether to simulate or actually send
        username         : LinkedIn email
        password         : LinkedIn password
        already_logged_in: Whether session is still valid
    """
    if not pending:
        return ""

    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any messages.
  For each follow-up you WOULD send, print:
    [DRY RUN] Would send follow-up to <n>: "<message>"
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

    # Build contact list with their relationship and suggested message
    contact_lines = []
    for item in pending:
        name         = item["contact"]
        relationship = item["relationship"]
        platform     = item["platform"]
        wish_date    = item["wish_date"]
        templates    = FOLLOWUP_TEMPLATES.get(
            relationship, FOLLOWUP_TEMPLATES["acquaintance"]
        )
        # Pick first template as suggestion (agent can vary)
        suggested = templates[0].replace("{name}", name)

        contact_lines.append(
            f"  - Name: {name} | Platform: {platform} | "
            f"Relationship: {relationship} | Birthday was: {wish_date}\n"
            f"    Suggested message: \"{suggested}\""
        )

    contacts_str = "\n".join(contact_lines)

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice}

  GOAL: Send follow-up messages to contacts whose birthday was {FOLLOWUP_DAYS} days ago.

  These contacts need a follow-up today:
{contacts_str}

  For each contact:
    a) Go to LinkedIn messaging and find their conversation.
       (Or WhatsApp/Facebook/Instagram based on the platform field)

    b) Send the follow-up message. You can use the suggested message
       or a slightly varied version — keep it warm and genuine.

    c) Do NOT send if you already replied to them today.

  After sending all follow-ups, provide a summary:
    - Sent to: (names + messages)
    - Skipped: (reason)
    - Any errors
"""