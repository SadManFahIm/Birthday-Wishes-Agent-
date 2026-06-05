"""
smart_reengagement.py
---------------------
Smart Re-engagement for Birthday Wishes Agent.

Detects contacts with whom there has been no interaction
for 6+ months and sends a personalized re-engagement message.

How it works:
  1. Reads last interaction date per contact from history
  2. Finds contacts with 6+ months of silence
  3. Generates a personalized, natural re-engagement message
  4. Sends via LinkedIn DM
  5. Logs all re-engagements to SQLite

Re-engagement levels:
  - 6-9 months  : Warm check-in
  - 9-12 months : Stronger outreach
  - 12+ months  : Full reconnect message

Rules:
  - Max 1 re-engagement per contact per year
  - Max 10 messages per run
  - Skips contacts already re-engaged this year

Usage:
    from smart_reengagement import (
        init_reengagement_table,
        run_smart_reengagement,
        get_dormant_contacts,
        build_reengagement_report,
    )

    await run_smart_reengagement(dry_run=True)
"""

import logging
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

MAX_MESSAGES_PER_RUN = 10
MAX_MESSAGES_PER_YEAR = 1

# Thresholds in days
WARM_THRESHOLD   = 180   # 6 months
STRONG_THRESHOLD = 270   # 9 months
FULL_THRESHOLD   = 365   # 12 months

# Message templates per level
REENGAGEMENT_TEMPLATES = {
    "warm": [
        "Hi {name}! It has been a while since we last connected. "
        "Hope everything is going well with you. "
        "Would love to catch up sometime!",

        "Hey {name}! Just thinking about our past conversations and "
        "wanted to check in. Hope life is treating you well!",

        "Hi {name}! I realized it has been some time since we last spoke. "
        "Hope you are doing great. Would love to reconnect!",
    ],
    "strong": [
        "Hi {name}! It has been quite a while and I wanted to reach out. "
        "I hope everything is going well in your personal and professional life. "
        "Would love to hear what you have been up to!",

        "Hey {name}! Time really flies — it feels like ages since we connected. "
        "I would love to catch up and hear about what you have been working on recently.",

        "Hi {name}! I was reflecting on some of my valuable connections "
        "and thought of you. Hope you are doing well. "
        "It would be great to reconnect!",
    ],
    "full": [
        "Hi {name}! I know it has been a long time since we last connected, "
        "but I wanted to reach out and see how you are doing. "
        "I hope life has been treating you well. "
        "It would be wonderful to catch up!",

        "Hey {name}! I hope this message finds you well. "
        "It has been a while since we last spoke and I wanted to reconnect. "
        "I would love to hear about the exciting things you have been working on!",

        "Hi {name}! I came across your profile and realized "
        "we have not been in touch for a while. "
        "Hope everything is fantastic. "
        "Would love to catch up and reconnect!",
    ],
}


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_reengagement_table():
    """Create re-engagement tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reengagements (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                contact         TEXT    NOT NULL,
                days_dormant    INTEGER NOT NULL,
                level           TEXT    NOT NULL,
                message_text    TEXT,
                sent            INTEGER DEFAULT 0,
                dry_run         INTEGER DEFAULT 1,
                sent_date       TEXT    NOT NULL,
                created_at      TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Re-engagement table ready.")


# ------------------------------------------------------------
# DORMANT CONTACT DETECTION
# ------------------------------------------------------------

def get_last_interactions() -> dict:
    """Get last interaction date per contact from history."""
    if not DB_FILE.exists():
        return {}

    with sqlite3.connect(DB_FILE) as conn:
        # Try interaction_log first
        try:
            rows = conn.execute("""
                SELECT LOWER(contact), MAX(interaction_date)
                FROM   interaction_log
                GROUP  BY LOWER(contact)
            """).fetchall()
            if rows:
                result = {}
                for contact, last_date in rows:
                    try:
                        result[contact] = date.fromisoformat(last_date)
                    except (ValueError, TypeError):
                        pass
                return result
        except sqlite3.OperationalError:
            pass

        # Fallback: history table
        rows = conn.execute("""
            SELECT LOWER(contact), MAX(date)
            FROM   history
            WHERE  dry_run = 0
            GROUP  BY LOWER(contact)
        """).fetchall()

    result = {}
    for contact, last_date in rows:
        try:
            result[contact] = date.fromisoformat(last_date)
        except (ValueError, TypeError):
            pass
    return result


def get_dormant_contacts(
    min_days: int = WARM_THRESHOLD,
    limit: int = 50,
) -> list[dict]:
    """
    Get contacts with no interaction for min_days or more.

    Returns:
        List of dicts sorted by days_dormant (most dormant first).
    """
    interactions = get_last_interactions()
    today        = date.today()
    dormant      = []

    for contact, last_date in interactions.items():
        days = (today - last_date).days
        if days >= min_days:
            level = _get_level(days)
            dormant.append({
                "contact":      contact,
                "days_dormant": days,
                "last_contact": last_date.isoformat(),
                "level":        level,
            })

    dormant.sort(key=lambda x: x["days_dormant"], reverse=True)
    logger.info("Found %d dormant contacts (min %d days).",
                len(dormant), min_days)
    return dormant[:limit]


def _get_level(days: int) -> str:
    """Get re-engagement level based on days dormant."""
    if days >= FULL_THRESHOLD:
        return "full"
    if days >= STRONG_THRESHOLD:
        return "strong"
    return "warm"


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def already_reengaged_this_year(contact: str) -> bool:
    """Check if already sent re-engagement this year."""
    if not DB_FILE.exists():
        return False
    year_start = date(date.today().year, 1, 1).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM reengagements
            WHERE LOWER(contact) = LOWER(?)
              AND sent_date >= ?
              AND dry_run = 0
        """, (contact, year_start)).fetchone()
    return (row[0] or 0) >= MAX_MESSAGES_PER_YEAR


def log_reengagement(
    contact: str,
    days_dormant: int,
    level: str,
    message_text: str,
    dry_run: bool = True,
):
    """Log a re-engagement message."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO reengagements
            (contact, days_dormant, level, message_text,
             sent, dry_run, sent_date, created_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """, (contact, days_dormant, level, message_text,
              int(dry_run), date.today().isoformat(),
              datetime.now().isoformat()))
        conn.commit()
    logger.info("Re-engagement logged: %s (%s, %d days)",
                contact, level, days_dormant)


# ------------------------------------------------------------
# MESSAGE GENERATION
# ------------------------------------------------------------

def get_reengagement_message(contact_name: str, level: str) -> str:
    """Get a personalized re-engagement message."""
    first_name = contact_name.split()[0].capitalize()
    templates  = REENGAGEMENT_TEMPLATES.get(level, REENGAGEMENT_TEMPLATES["warm"])
    template   = random.choice(templates)
    return template.format(name=first_name)


# ------------------------------------------------------------
# AGENT TASK
# ------------------------------------------------------------

def build_reengagement_task(
    dormant_contacts: list[dict],
    username: str,
    password: str,
    already_logged_in: bool = False,
    dry_run: bool = True,
) -> str:
    """Build agent task for sending re-engagement messages."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    dry = "[DRY RUN] Do NOT send. Print what you would send." if dry_run else ""

    messages_str = "\n".join(
        f"  {c['contact']} ({c['days_dormant']} days, level: {c['level']}): "
        f"\"{get_reengagement_message(c['contact'], c['level'])}\""
        for c in dormant_contacts
    )

    return f"""
Open browser. {login}
{dry}

GOAL: Send re-engagement messages to dormant contacts.

Contacts and messages:
{messages_str}

For each contact:
  1. Go to https://www.linkedin.com/messaging/
  2. Search for the contact
  3. Send the message
  4. Report: REENGAGED: <name> or FAILED: <name>

Keep tone warm and natural. Do not mention how long it has been
since you last spoke — just reach out naturally.
"""


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_reengagement_report(
    dormant: list[dict],
    sent: list[str],
) -> str:
    """Build human-readable re-engagement report."""
    warm   = [c for c in dormant if c["level"] == "warm"]
    strong = [c for c in dormant if c["level"] == "strong"]
    full   = [c for c in dormant if c["level"] == "full"]

    lines = [
        "Smart Re-engagement Report",
        "-" * 55,
        f"  Total dormant  : {len(dormant)}",
        f"  Messages sent  : {len(sent)}",
        f"  Warm (6-9m)    : {len(warm)}",
        f"  Strong (9-12m) : {len(strong)}",
        f"  Full (12m+)    : {len(full)}",
        "-" * 55,
        "",
    ]

    for level, contacts, label in [
        ("full",   full,   "FULL RECONNECT (12+ months)"),
        ("strong", strong, "STRONG OUTREACH (9-12 months)"),
        ("warm",   warm,   "WARM CHECK-IN (6-9 months)"),
    ]:
        if not contacts:
            continue
        lines.append(f"{label}:")
        for c in contacts:
            status = "SENT" if c["contact"] in sent else "PENDING"
            months = round(c["days_dormant"] / 30)
            lines.append(
                f"  [{status}] {c['contact']:<25} "
                f"({months} months ago)"
            )
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_smart_reengagement(
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
    dry_run: bool = True,
    min_days: int = WARM_THRESHOLD,
    max_messages: int = MAX_MESSAGES_PER_RUN,
) -> dict:
    """
    Main runner. Call from agent.py weekly.

    Args:
        llm               : LangChain LLM instance
        browser           : browser_use Browser instance
        username          : LinkedIn email
        password          : LinkedIn password
        already_logged_in : Skip login if True
        dry_run           : If True, log only - do not send
        min_days          : Minimum days of inactivity (default 180 = 6 months)
        max_messages      : Max re-engagement messages per run

    Returns:
        Dict with summary stats.
    """
    from browser_use import Agent

    logger.info("=== Smart Re-engagement === [DRY RUN: %s | MIN: %d days]",
                dry_run, min_days)

    # Get dormant contacts
    dormant = get_dormant_contacts(min_days=min_days)

    if not dormant:
        logger.info("No dormant contacts found.")
        return {"dormant": 0, "sent": 0,
                "report": "No dormant contacts found."}

    # Filter already re-engaged this year
    eligible = [
        c for c in dormant
        if not already_reengaged_this_year(c["contact"])
    ][:max_messages]

    if not eligible:
        logger.info("All dormant contacts already re-engaged this year.")
        return {"dormant": len(dormant), "sent": 0}

    logger.info("Sending re-engagement to %d contacts.", len(eligible))

    sent_names = []

    if dry_run:
        for c in eligible:
            msg = get_reengagement_message(c["contact"], c["level"])
            logger.info("[DRY RUN] Would re-engage %s: %s",
                        c["contact"], msg)
            log_reengagement(
                c["contact"], c["days_dormant"], c["level"], msg, dry_run=True
            )
            sent_names.append(c["contact"])

    elif llm and browser:
        task = build_reengagement_task(
            dormant_contacts=eligible,
            username=username,
            password=password,
            already_logged_in=already_logged_in,
            dry_run=False,
        )
        try:
            agent  = Agent(task=task, llm=llm, browser=browser)
            await agent.run()

            for c in eligible:
                msg = get_reengagement_message(c["contact"], c["level"])
                log_reengagement(
                    c["contact"], c["days_dormant"],
                    c["level"], msg, dry_run=False,
                )
                sent_names.append(c["contact"])

        except Exception as e:
            logger.error("Re-engagement task failed: %s", e)

    report = build_reengagement_report(dormant, sent_names)
    logger.info("Re-engagement done: %d dormant | %d sent.",
                len(dormant), len(sent_names))

    return {
        "dormant": len(dormant),
        "sent":    len(sent_names),
        "report":  report,
    }


# ------------------------------------------------------------
# AGENT INSTRUCTIONS
# ------------------------------------------------------------

def build_reengagement_instructions() -> str:
    """Build re-engagement instructions for the browser agent."""
    dormant = get_dormant_contacts()

    if not dormant:
        return "No dormant contacts found."

    lines = [f"SMART RE-ENGAGEMENT ({len(dormant)} dormant contacts):"]
    for c in dormant[:5]:
        months = round(c["days_dormant"] / 30)
        msg    = get_reengagement_message(c["contact"], c["level"])
        lines.append(
            f"  - {c['contact']} ({months}m silent, {c['level']}): \"{msg}\""
        )
    return "\n".join(lines)
