"""
smart_followup.py
-----------------
Smart Follow-up Timing for Birthday Wishes Agent.

Automatically sends a follow-up message if the contact
did not reply to the original birthday wish within N days.

How it works:
  1. Tracks every birthday wish sent (contact + date)
  2. Checks if the contact replied within FOLLOWUP_DAYS days
  3. If no reply -> sends a warm follow-up message
  4. If they replied -> skips follow-up (no need)
  5. Maximum 1 follow-up per contact per year

Integrates with:
  - agent.py             : runs as daily task
  - auto_reply_followup  : detects incoming replies
  - notifications.py     : alert on follow-up sent

Usage:
    from smart_followup import (
        init_smart_followup_table,
        log_wish_for_followup,
        mark_reply_received,
        run_smart_followup,
        get_pending_followups,
    )

    await run_smart_followup(dry_run=True)
"""

import logging
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Days to wait before sending follow-up
FOLLOWUP_DAYS = 3

# Max follow-ups per contact per year
MAX_FOLLOWUPS_PER_YEAR = 1

# Follow-up message templates
FOLLOWUP_TEMPLATES = [
    "Hey {name}! Just wanted to check in - hope you had a wonderful birthday! "
    "How are things going?",

    "Hi {name}! Hope your birthday was amazing! "
    "Would love to hear how you celebrated.",

    "Hey {name}! Just thinking of you - hope your special day was everything you wanted! "
    "How have you been?",

    "Hi {name}! Hope you had a great birthday celebration! "
    "It would be great to catch up sometime.",
]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_smart_followup_table():
    """Create smart follow-up tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS smart_followups (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                contact         TEXT    NOT NULL,
                wish_date       TEXT    NOT NULL,
                platform        TEXT    DEFAULT 'linkedin',
                reply_received  INTEGER DEFAULT 0,
                reply_date      TEXT,
                followup_sent   INTEGER DEFAULT 0,
                followup_date   TEXT,
                followup_text   TEXT,
                dry_run         INTEGER DEFAULT 1,
                created_at      TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Smart followup table ready.")


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def log_wish_for_followup(
    contact: str,
    platform: str = "linkedin",
    dry_run: bool = True,
):
    """
    Log a sent birthday wish for follow-up tracking.
    Call this right after sending a birthday wish.
    """
    with sqlite3.connect(DB_FILE) as conn:
        # Avoid duplicate for same contact + date
        existing = conn.execute("""
            SELECT id FROM smart_followups
            WHERE LOWER(contact) = LOWER(?) AND wish_date = ?
        """, (contact, date.today().isoformat())).fetchone()

        if existing:
            return

        conn.execute("""
            INSERT INTO smart_followups
            (contact, wish_date, platform, dry_run, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (contact, date.today().isoformat(),
              platform, int(dry_run), datetime.now().isoformat()))
        conn.commit()
    logger.info("Wish logged for follow-up tracking: %s", contact)


def mark_reply_received(contact: str):
    """
    Mark that a contact replied to our wish.
    Call this from auto_reply_followup when a reply is detected.
    No follow-up will be sent to contacts who replied.
    """
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE smart_followups
            SET    reply_received = 1,
                   reply_date     = ?
            WHERE  LOWER(contact) = LOWER(?)
              AND  reply_received  = 0
              AND  id = (
                  SELECT id FROM smart_followups
                  WHERE  LOWER(contact) = LOWER(?)
                    AND  reply_received  = 0
                  ORDER  BY id DESC LIMIT 1
              )
        """, (datetime.now().isoformat(), contact, contact))
        conn.commit()
    logger.info("Reply received marked for: %s (no follow-up needed)", contact)


def mark_followup_sent(followup_id: int, followup_text: str):
    """Mark that a follow-up was sent."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE smart_followups
            SET    followup_sent = 1,
                   followup_date = ?,
                   followup_text = ?
            WHERE  id = ?
        """, (date.today().isoformat(), followup_text, followup_id))
        conn.commit()
    logger.info("Follow-up marked sent (ID: %d)", followup_id)


# ------------------------------------------------------------
# CORE: Get pending follow-ups
# ------------------------------------------------------------

def get_pending_followups(followup_days: int = FOLLOWUP_DAYS) -> list[dict]:
    """
    Get contacts who:
      - Received a birthday wish N+ days ago
      - Have NOT replied
      - Have NOT received a follow-up yet

    Args:
        followup_days: Days to wait before follow-up (default 3)

    Returns:
        List of dicts: id, contact, wish_date, platform, days_since_wish
    """
    if not DB_FILE.exists():
        return []

    cutoff = (date.today() - timedelta(days=followup_days)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT id, contact, wish_date, platform
            FROM   smart_followups
            WHERE  wish_date    <= ?
              AND  reply_received = 0
              AND  followup_sent  = 0
              AND  dry_run        = 0
            ORDER  BY wish_date ASC
        """, (cutoff,)).fetchall()

    result = []
    for row in rows:
        wish_date  = date.fromisoformat(row[2])
        days_since = (date.today() - wish_date).days
        result.append({
            "id":              row[0],
            "contact":         row[1],
            "wish_date":       row[2],
            "platform":        row[3],
            "days_since_wish": days_since,
        })

    logger.info("Found %d contacts pending follow-up.", len(result))
    return result


def already_followed_up_this_year(contact: str) -> bool:
    """Check if we already sent a follow-up to this contact this year."""
    if not DB_FILE.exists():
        return False

    year_start = date(date.today().year, 1, 1).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM smart_followups
            WHERE  LOWER(contact) = LOWER(?)
              AND  followup_sent   = 1
              AND  followup_date  >= ?
        """, (contact, year_start)).fetchone()

    return (row[0] or 0) >= MAX_FOLLOWUPS_PER_YEAR


# ------------------------------------------------------------
# MESSAGE
# ------------------------------------------------------------

def get_followup_message(contact_name: str) -> str:
    """Get a warm follow-up message."""
    first_name = contact_name.split()[0].capitalize()
    template   = random.choice(FOLLOWUP_TEMPLATES)
    return template.format(name=first_name)


# ------------------------------------------------------------
# AGENT TASK
# ------------------------------------------------------------

def build_smart_followup_task(
    pending: list[dict],
    username: str,
    password: str,
    already_logged_in: bool = False,
    dry_run: bool = True,
) -> str:
    """Build agent task for sending follow-up messages."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    dry = "[DRY RUN] Do NOT send. Print what you would send." if dry_run else ""

    messages_str = "\n".join(
        f"  {p['contact']} (wished {p['days_since_wish']} days ago, no reply): "
        f"\"{get_followup_message(p['contact'])}\""
        for p in pending
    )

    return f"""
Open browser. {login}
{dry}

GOAL: Send follow-up messages to contacts who did not reply to birthday wishes.

These contacts received a birthday wish but have not replied:
{messages_str}

For each contact:
  1. Go to https://www.linkedin.com/messaging/
  2. Find their existing conversation
  3. Send the follow-up message
  4. Report: FOLLOWUP SENT: <name> or FOLLOWUP FAILED: <name>

Do NOT start a new conversation - reply in the existing thread.
"""


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_followup_report(pending: list[dict], sent: list[str]) -> str:
    """Build a human-readable follow-up report."""
    lines = [
        "Smart Follow-up Report",
        "-" * 50,
        f"  Pending follow-ups : {len(pending)}",
        f"  Sent today         : {len(sent)}",
        f"  Wait period        : {FOLLOWUP_DAYS} days after wish",
        "-" * 50,
        "",
    ]

    if pending:
        lines.append("Contacts pending follow-up:")
        for p in pending:
            status = "SENT" if p["contact"] in sent else "PENDING"
            lines.append(
                f"  [{status}] {p['contact']:<25} "
                f"Wished {p['days_since_wish']} days ago"
            )

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_smart_followup(
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
    dry_run: bool = True,
    followup_days: int = FOLLOWUP_DAYS,
    max_followups: int = 20,
) -> dict:
    """
    Main runner. Call from agent.py daily.

    Args:
        llm               : LangChain LLM instance
        browser           : browser_use Browser instance
        username          : LinkedIn email
        password          : LinkedIn password
        already_logged_in : Skip login if True
        dry_run           : If True, log only - do not send
        followup_days     : Days to wait before follow-up (default 3)
        max_followups     : Max follow-ups to send per run

    Returns:
        Dict with summary stats.
    """
    logger.info("=== Smart Follow-up === [DRY RUN: %s | WAIT: %d days]",
                dry_run, followup_days)

    # Get contacts needing follow-up
    pending = get_pending_followups(followup_days=followup_days)

    if not pending:
        logger.info("No follow-ups due today.")
        return {
            "total_pending": 0,
            "sent":          0,
            "report":        "No follow-ups due today.",
        }

    # Filter out already followed up this year
    pending = [
        p for p in pending
        if not already_followed_up_this_year(p["contact"])
    ][:max_followups]

    if not pending:
        logger.info("All pending contacts already followed up this year.")
        return {"total_pending": 0, "sent": 0}

    logger.info("Sending follow-ups to %d contacts.", len(pending))

    sent_names = []

    if dry_run:
        for p in pending:
            msg = get_followup_message(p["contact"])
            logger.info("[DRY RUN] Would follow up with %s: %s",
                        p["contact"], msg)
            sent_names.append(p["contact"])

    elif llm and browser:
        from browser_use import Agent

        task = build_smart_followup_task(
            pending=pending,
            username=username,
            password=password,
            already_logged_in=already_logged_in,
            dry_run=False,
        )

        try:
            agent  = Agent(task=task, llm=llm, browser=browser)
            result = await agent.run()
            logger.info("Follow-up agent result: %s", result)

            # Mark sent
            for p in pending:
                msg = get_followup_message(p["contact"])
                mark_followup_sent(p["id"], msg)
                sent_names.append(p["contact"])

        except Exception as e:
            logger.error("Follow-up task failed: %s", e)

    report = build_followup_report(pending, sent_names)
    logger.info("Smart follow-up done: %d sent.", len(sent_names))

    return {
        "total_pending": len(pending),
        "sent":          len(sent_names),
        "report":        report,
    }


# ------------------------------------------------------------
# AGENT INSTRUCTIONS
# ------------------------------------------------------------

def build_smart_followup_instructions() -> str:
    """Build follow-up instructions for the browser agent."""
    pending = get_pending_followups()

    if not pending:
        return "No follow-ups needed. All contacts replied or are within the wait period."

    lines = [
        f"SMART FOLLOW-UP ({len(pending)} contacts, no reply in {FOLLOWUP_DAYS}+ days):",
    ]

    for p in pending[:10]:
        msg = get_followup_message(p["contact"])
        lines.append(
            f"  - {p['contact']} (wished {p['days_since_wish']} days ago): \"{msg}\""
        )

    return "\n".join(lines)