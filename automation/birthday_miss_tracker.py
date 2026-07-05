"""
birthday_miss_tracker.py
------------------------
Birthday Miss Tracker for Birthday Wishes Agent.

Tracks which contacts had birthdays but did NOT receive a wish,
and sends alerts so you can follow up manually or automatically.

How it works:
  1. Reads all contacts whose birthday was detected (from history table)
  2. Checks which ones actually received a wish
  3. Marks the difference as "missed"
  4. Sends alert via email/Telegram
  5. Optionally sends a late wish automatically

Usage:
    from birthday_miss_tracker import (
        init_miss_table,
        run_miss_tracker,
        get_missed_contacts,
        build_miss_report,
    )

    await run_miss_tracker(dry_run=True)
"""

import logging
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# How many days back to check for missed birthdays
LOOKBACK_DAYS = 7

# Late wish templates
LATE_WISH_TEMPLATES = [
    "Happy Belated Birthday {name}! Sorry for the late wishes - "
    "hope you had a wonderful day!",
    "Belated Happy Birthday {name}! Wishing you all the best - "
    "hope your celebration was amazing!",
    "A little late but heartfelt - Happy Belated Birthday {name}! "
    "Hope your special day was fantastic!",
]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_miss_table():
    """Create birthday miss tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS birthday_misses (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact       TEXT    NOT NULL,
                birthday_date TEXT    NOT NULL,
                reason        TEXT,
                late_wish_sent INTEGER DEFAULT 0,
                alerted       INTEGER DEFAULT 0,
                created_at    TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Birthday miss table ready.")


# ------------------------------------------------------------
# CORE LOGIC
# ------------------------------------------------------------

def get_detected_birthdays(lookback_days: int = LOOKBACK_DAYS) -> set:
    """
    Get contacts whose birthday was detected in the last N days.
    Reads from history table where task = LinkedIn-BirthdayDetection.
    """
    if not DB_FILE.exists():
        return set()

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT LOWER(contact), date
            FROM   history
            WHERE  task LIKE '%BirthdayDetection%'
              AND  date >= ?
        """, (cutoff,)).fetchall()

    detected = {(row[0], row[1]) for row in rows}
    logger.info("Found %d detected birthdays in last %d days.", len(detected), lookback_days)
    return detected


def get_wished_contacts(lookback_days: int = LOOKBACK_DAYS) -> set:
    """
    Get contacts who actually received a wish in the last N days.
    Reads from history where task contains Wish or Reply.
    """
    if not DB_FILE.exists():
        return set()

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT LOWER(contact), date
            FROM   history
            WHERE  (task LIKE '%Wish%' OR task LIKE '%wish%')
              AND  dry_run = 0
              AND  date >= ?
        """, (cutoff,)).fetchall()

    wished = {(row[0], row[1]) for row in rows}
    logger.info("Found %d wished contacts in last %d days.", len(wished), lookback_days)
    return wished


def get_missed_contacts(lookback_days: int = LOOKBACK_DAYS) -> list[dict]:
    """
    Find contacts whose birthday was detected but no wish was sent.

    Returns:
        List of dicts: contact, birthday_date, days_ago
    """
    detected = get_detected_birthdays(lookback_days)
    wished   = get_wished_contacts(lookback_days)

    # Wished contact names (ignore date for matching)
    wished_names = {name for name, _ in wished}

    missed = []
    for contact, bday_date in detected:
        if contact not in wished_names:
            try:
                bday = date.fromisoformat(bday_date)
                days_ago = (date.today() - bday).days
            except ValueError:
                days_ago = 0

            missed.append({
                "contact":       contact,
                "birthday_date": bday_date,
                "days_ago":      days_ago,
            })

    missed.sort(key=lambda x: x["days_ago"])
    logger.info("Found %d missed birthday contacts.", len(missed))
    return missed


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def log_missed(contact: str, birthday_date: str, reason: str = ""):
    """Log a missed birthday contact."""
    with sqlite3.connect(DB_FILE) as conn:
        # Avoid duplicate entries for same contact + date
        existing = conn.execute("""
            SELECT id FROM birthday_misses
            WHERE LOWER(contact) = LOWER(?) AND birthday_date = ?
        """, (contact, birthday_date)).fetchone()

        if existing:
            return

        conn.execute("""
            INSERT INTO birthday_misses
            (contact, birthday_date, reason, created_at)
            VALUES (?, ?, ?, ?)
        """, (contact, birthday_date, reason, datetime.now().isoformat()))
        conn.commit()
    logger.info("Missed birthday logged: %s (%s)", contact, birthday_date)


def mark_late_wish_sent(contact: str):
    """Mark that a late wish was sent."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE birthday_misses
            SET    late_wish_sent = 1
            WHERE  LOWER(contact) = LOWER(?)
              AND  id = (
                  SELECT id FROM birthday_misses
                  WHERE LOWER(contact) = LOWER(?)
                  ORDER BY id DESC LIMIT 1
              )
        """, (contact, contact))
        conn.commit()
    logger.info("Late wish marked sent: %s", contact)


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_miss_report(missed: list[dict] | None = None) -> str:
    """Build a human-readable missed birthday report."""
    if missed is None:
        missed = get_missed_contacts()

    if not missed:
        return "No missed birthdays found. All detected birthdays received wishes!"

    lines = [
        "Birthday Miss Tracker Report",
        "-" * 50,
        f"  Total missed: {len(missed)} contacts",
        f"  Lookback    : last {LOOKBACK_DAYS} days",
        "-" * 50,
        "",
    ]

    today    = [c for c in missed if c["days_ago"] == 0]
    recent   = [c for c in missed if 1 <= c["days_ago"] <= 3]
    older    = [c for c in missed if c["days_ago"] > 3]

    if today:
        lines.append("TODAY - Still time to wish!")
        lines.append("-" * 40)
        for c in today:
            lines.append(f"  {c['contact']}")
        lines.append("")

    if recent:
        lines.append("RECENT (1-3 days ago) - Send late wish")
        lines.append("-" * 40)
        for c in recent:
            lines.append(f"  {c['contact']:<30} {c['days_ago']} day(s) ago")
        lines.append("")

    if older:
        lines.append("OLDER (4+ days ago) - Consider reaching out")
        lines.append("-" * 40)
        for c in older:
            lines.append(f"  {c['contact']:<30} {c['days_ago']} days ago")
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# LATE WISH
# ------------------------------------------------------------

def get_late_wish(contact_name: str) -> str:
    """Get a late birthday wish message."""
    first_name = contact_name.split()[0].capitalize()
    template = random.choice(LATE_WISH_TEMPLATES)
    return template.format(name=first_name)


def build_late_wish_task(
    missed_contacts: list[dict],
    username: str,
    password: str,
    already_logged_in: bool = False,
    dry_run: bool = True,
) -> str:
    """Build agent task for sending late wishes."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    dry = "[DRY RUN] Do NOT send. Print what you would send." if dry_run else ""

    messages_str = "\n".join(
        f"  {c['contact']}: \"{get_late_wish(c['contact'])}\""
        for c in missed_contacts
    )

    return f"""
Open browser. {login}
{dry}

GOAL: Send late birthday wishes to contacts who were missed.

Messages to send:
{messages_str}

For each contact:
  1. Go to https://www.linkedin.com/messaging/
  2. Search for the contact name
  3. Send their late wish message
  4. Report: LATE WISH SENT: <name> or LATE WISH FAILED: <name>
"""


# ------------------------------------------------------------
# NOTIFICATION
# ------------------------------------------------------------

def send_miss_notification(report: str, dry_run: bool = True):
    """Send missed birthday alert via email and Telegram."""
    if dry_run:
        logger.info("[DRY RUN] Would send miss alert:\n%s", report)
        return

    try:
        from notifications import send_email, send_telegram

        subject = "Birthday Miss Alert - Contacts Who Were Not Wished"

        try:
            send_email(subject=subject, body=report)
            logger.info("Miss alert sent via email.")
        except Exception as e:
            logger.warning("Email failed: %s", e)

        try:
            send_telegram(message=f"*{subject}*\n\n```\n{report[:3000]}\n```")
            logger.info("Miss alert sent via Telegram.")
        except Exception as e:
            logger.warning("Telegram failed: %s", e)

    except ImportError:
        logger.warning("notifications.py not available.")


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_miss_tracker(
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
    dry_run: bool = True,
    send_late_wishes: bool = False,
    lookback_days: int = LOOKBACK_DAYS,
    max_late_wishes: int = 10,
) -> dict:
    """
    Main runner for birthday miss tracker. Call from agent.py daily.

    Args:
        llm               : LangChain LLM (needed if send_late_wishes=True)
        browser           : browser_use Browser (needed if send_late_wishes=True)
        username          : LinkedIn email
        password          : LinkedIn password
        already_logged_in : Skip login if True
        dry_run           : If True, log only - do not send
        send_late_wishes  : If True, auto-send late wishes
        lookback_days     : How many days back to check
        max_late_wishes   : Max late wishes to send per run

    Returns:
        Dict with summary stats.
    """
    logger.info("=== Birthday Miss Tracker === [DRY RUN: %s]", dry_run)

    missed = get_missed_contacts(lookback_days=lookback_days)

    if not missed:
        logger.info("No missed birthdays! All contacts received wishes.")
        return {
            "total_missed":     0,
            "late_wishes_sent": 0,
            "report":           "No missed birthdays found!",
        }

    # Log missed contacts to DB
    for c in missed:
        log_missed(
            contact=c["contact"],
            birthday_date=c["birthday_date"],
            reason="No wish found in history",
        )

    # Build and send report
    report = build_miss_report(missed)
    logger.info("\n%s", report)
    send_miss_notification(report, dry_run=dry_run)

    # Send late wishes
    late_wishes_sent = 0
    if send_late_wishes and llm and browser:
        from browser_use import Agent

        # Only send late wishes for contacts missed within 3 days
        sendable = [c for c in missed if c["days_ago"] <= 3][:max_late_wishes]

        if sendable:
            task = build_late_wish_task(
                missed_contacts=sendable,
                username=username,
                password=password,
                already_logged_in=already_logged_in,
                dry_run=dry_run,
            )
            try:
                agent = Agent(task=task, llm=llm, browser=browser)
                result = await agent.run()
                logger.info("Late wish result: %s", result)

                if not dry_run:
                    for c in sendable:
                        mark_late_wish_sent(c["contact"])
                        late_wishes_sent += 1
            except Exception as e:
                logger.error("Late wish task failed: %s", e)

    summary = {
        "total_missed":     len(missed),
        "late_wishes_sent": late_wishes_sent,
        "report":           report,
        "breakdown": {
            "today":  len([c for c in missed if c["days_ago"] == 0]),
            "recent": len([c for c in missed if 1 <= c["days_ago"] <= 3]),
            "older":  len([c for c in missed if c["days_ago"] > 3]),
        },
    }

    logger.info(
        "Miss tracker done: %d missed | %d late wishes sent",
        summary["total_missed"], summary["late_wishes_sent"],
    )
    return summary


# ------------------------------------------------------------
# AGENT INSTRUCTIONS
# ------------------------------------------------------------

def build_miss_tracker_instructions() -> str:
    """Build miss tracker instructions for the browser agent."""
    missed = get_missed_contacts()

    if not missed:
        return "No missed birthdays found. All contacts received wishes."

    today_missed  = [c for c in missed if c["days_ago"] == 0]
    recent_missed = [c for c in missed if 1 <= c["days_ago"] <= 3]

    lines = ["BIRTHDAY MISS TRACKER:"]

    if today_missed:
        lines.append("  Still time to wish TODAY:")
        for c in today_missed:
            lines.append(f"    - {c['contact']}")

    if recent_missed:
        lines.append("  Send LATE wishes (missed recently):")
        for c in recent_missed:
            lines.append(
                f"    - {c['contact']} ({c['days_ago']} day(s) ago): "
                f"\"{get_late_wish(c['contact'])}\""
            )

    return "\n".join(lines)
