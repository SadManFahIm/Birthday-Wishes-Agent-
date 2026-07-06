"""
decay_alert.py
--------------
Relationship Decay Alert module for Birthday Wishes Agent.

Monitors how long it has been since the agent last interacted
with each contact and sends alerts when relationships are fading.

How it works:
  1. Reads interaction history from connection_tracker (SQLite)
  2. Calculates days since last interaction per contact
  3. Classifies contacts into decay levels:
       - Green  (0-30 days)  : Active, no action needed
       - Yellow (31-60 days) : Warming up recommended
       - Orange (61-90 days) : At risk - send a check-in
       - Red    (90+ days)   : Fading - urgent re-engagement
  4. Sends email/Telegram alert with the fading contacts list
  5. Optionally triggers an automated check-in message

Integrates with:
  - connection_tracker.py  : reads last interaction dates
  - relationship_health.py : reads health scores
  - notifications.py       : sends email/Telegram alerts
  - agent.py               : runs as a scheduled daily task

Usage:
    from decay_alert import (
        init_decay_table,
        run_decay_alert,
        get_fading_contacts,
        build_decay_report,
    )

    await run_decay_alert(dry_run=True)
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_FILE = Path("agent_history.db")

# Decay thresholds (days since last interaction)
DECAY_LEVELS = {
    "green":  (0,  30),
    "yellow": (31, 60),
    "orange": (61, 90),
    "red":    (91, 9999),
}

DECAY_LABELS = {
    "green":  "Active",
    "yellow": "Warm up recommended",
    "orange": "At risk - send check-in",
    "red":    "Fading - urgent re-engagement",
}

# Only alert for these levels
ALERT_LEVELS = ["yellow", "orange", "red"]

# Default check-in message templates per decay level
CHECKIN_TEMPLATES = {
    "yellow": [
        "Hey {name}! Hope you are doing well. Been a while since we connected!",
        "Hi {name}! Just wanted to check in and see how things are going.",
    ],
    "orange": [
        "Hi {name}! It has been some time since we last spoke. Hope all is well!",
        "Hey {name}! I realized we haven't connected in a while. How have you been?",
    ],
    "red": [
        "Hi {name}! I noticed we haven't been in touch for a while. "
        "Would love to reconnect and hear how you are doing!",
        "Hey {name}! It has been too long. Hope everything is going great for you. "
        "Would love to catch up!",
    ],
}


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_decay_table():
    """Create decay alert tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS decay_alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                decay_level  TEXT    NOT NULL,
                days_since   INTEGER NOT NULL,
                alerted      INTEGER DEFAULT 0,
                checkin_sent INTEGER DEFAULT 0,
                alert_date   TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Decay alert table ready.")


# ------------------------------------------------------------
# CORE: Get last interaction per contact
# ------------------------------------------------------------

def get_last_interactions() -> dict:
    """
    Read last interaction date per contact from history table.

    Returns:
        Dict[contact_name] -> last interaction date (date object)
    """
    if not DB_FILE.exists():
        return {}

    with sqlite3.connect(DB_FILE) as conn:
        # Try connection_tracker first (most accurate)
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
                logger.info("Loaded %d contacts from interaction_log.", len(result))
                return result
        except sqlite3.OperationalError:
            pass

        # Fallback: use history table
        try:
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
            logger.info("Loaded %d contacts from history table.", len(result))
            return result
        except sqlite3.OperationalError:
            logger.warning("No interaction data found.")
            return {}


def get_days_since(last_date: date) -> int:
    """Calculate days since last interaction."""
    return (date.today() - last_date).days


def classify_decay(days: int) -> str:
    """Classify a contact into a decay level based on days since contact."""
    for level, (low, high) in DECAY_LEVELS.items():
        if low <= days <= high:
            return level
    return "red"


# ------------------------------------------------------------
# CORE: Get fading contacts
# ------------------------------------------------------------

def get_fading_contacts(
    min_level: str = "yellow",
    limit: int = 50,
) -> list[dict]:
    """
    Get contacts that are fading based on decay level.

    Args:
        min_level : Minimum decay level to include
                    ("yellow", "orange", or "red")
        limit     : Max contacts to return

    Returns:
        List of dicts sorted by days_since (most faded first):
          - contact, days_since, decay_level, last_interaction
    """
    levels_order = ["green", "yellow", "orange", "red"]
    min_idx = levels_order.index(min_level) if min_level in levels_order else 1

    interactions = get_last_interactions()
    fading = []

    for contact, last_date in interactions.items():
        days = get_days_since(last_date)
        level = classify_decay(days)
        level_idx = levels_order.index(level)

        if level_idx >= min_idx:
            fading.append({
                "contact":          contact,
                "days_since":       days,
                "decay_level":      level,
                "decay_label":      DECAY_LABELS[level],
                "last_interaction": last_date.isoformat(),
            })

    fading.sort(key=lambda x: x["days_since"], reverse=True)
    logger.info("Found %d fading contacts (min level: %s).", len(fading), min_level)
    return fading[:limit]


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_decay_report(fading: list[dict] | None = None) -> str:
    """
    Build a human-readable decay report.
    Used in email digest, Telegram notification, or dashboard.
    """
    if fading is None:
        fading = get_fading_contacts(min_level="yellow")

    if not fading:
        return "All relationships are active! No fading contacts found."

    # Count per level
    counts = {"yellow": 0, "orange": 0, "red": 0}
    for c in fading:
        level = c["decay_level"]
        if level in counts:
            counts[level] += 1

    lines = [
        "Relationship Decay Alert Report",
        "-" * 50,
        f"  Active (0-30d)       : (not shown)",
        f"  Warm up (31-60d)     : {counts['yellow']} contacts",
        f"  At risk (61-90d)     : {counts['orange']} contacts",
        f"  Fading (90d+)        : {counts['red']} contacts",
        "-" * 50,
        "",
    ]

    # Red contacts first
    for level in ["red", "orange", "yellow"]:
        level_contacts = [c for c in fading if c["decay_level"] == level]
        if not level_contacts:
            continue

        label = DECAY_LABELS[level]
        marker = "!!!" if level == "red" else "!!" if level == "orange" else "!"
        lines.append(f"{marker} {label.upper()}")
        lines.append("-" * 40)

        for c in level_contacts:
            lines.append(
                f"  {c['contact']:<30} "
                f"{c['days_since']:>4} days ago"
            )
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# LOG ALERT
# ------------------------------------------------------------

def log_decay_alert(contact: str, decay_level: str, days_since: int):
    """Log that an alert was sent for a contact."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO decay_alerts
            (contact, decay_level, days_since, alerted, alert_date, created_at)
            VALUES (?, ?, ?, 1, ?, ?)
        """, (contact, decay_level, days_since,
              date.today().isoformat(), datetime.now().isoformat()))
        conn.commit()
    logger.info("Decay alert logged: %s (%s, %d days)", contact, decay_level, days_since)


def mark_checkin_sent(contact: str):
    """Mark that a check-in message was sent to a contact."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE decay_alerts
            SET    checkin_sent = 1
            WHERE  LOWER(contact) = LOWER(?)
              AND  id = (
                  SELECT id FROM decay_alerts
                  WHERE  LOWER(contact) = LOWER(?)
                  ORDER  BY id DESC LIMIT 1
              )
        """, (contact, contact))
        conn.commit()
    logger.info("Check-in marked sent: %s", contact)


def already_alerted_today(contact: str) -> bool:
    """Check if we already sent a decay alert for this contact today."""
    if not DB_FILE.exists():
        return False
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM decay_alerts
            WHERE  LOWER(contact) = LOWER(?)
              AND  alert_date = ?
        """, (contact, date.today().isoformat())).fetchone()
    return (row[0] or 0) > 0


# ------------------------------------------------------------
# CHECK-IN MESSAGE
# ------------------------------------------------------------

def get_checkin_message(contact_name: str, decay_level: str) -> str:
    """Get a check-in message template for the given decay level."""
    import random
    templates = CHECKIN_TEMPLATES.get(decay_level, CHECKIN_TEMPLATES["yellow"])
    template = random.choice(templates)
    # Capitalize first name
    first_name = contact_name.split()[0].capitalize()
    return template.format(name=first_name)


def build_checkin_task(
    fading_contacts: list[dict],
    username: str,
    password: str,
    already_logged_in: bool = False,
    dry_run: bool = True,
) -> str:
    """Build agent task for sending check-in messages to fading contacts."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    dry = "[DRY RUN] Do NOT send. Print what you would send." if dry_run else ""

    contacts_str = "\n".join(
        f"  - {c['contact']} ({c['days_since']} days since last contact, "
        f"level: {c['decay_level']})"
        for c in fading_contacts
    )

    messages_str = "\n".join(
        f"  {c['contact']}: \"{get_checkin_message(c['contact'], c['decay_level'])}\""
        for c in fading_contacts
    )

    return f"""
Open browser. {login}
{dry}

GOAL: Send check-in messages to fading contacts on LinkedIn.

Fading contacts:
{contacts_str}

Messages to send:
{messages_str}

For each contact:
  1. Go to https://www.linkedin.com/messaging/
  2. Search for the contact
  3. Send their check-in message
  4. Report: CHECKIN SENT: <contact_name> or CHECKIN FAILED: <contact_name>

Stop after all contacts are processed.
"""


# ------------------------------------------------------------
# NOTIFICATION
# ------------------------------------------------------------

def send_decay_notification(report: str, dry_run: bool = True):
    """Send decay alert via email and/or Telegram."""
    if dry_run:
        logger.info("[DRY RUN] Would send decay alert:\n%s", report)
        return

    try:
        from notifications import send_email, send_telegram

        subject = "Relationship Decay Alert - Fading Contacts"

        try:
            send_email(subject=subject, body=report)
            logger.info("Decay alert sent via email.")
        except Exception as e:
            logger.warning("Email notification failed: %s", e)

        try:
            send_telegram(message=f"*{subject}*\n\n```\n{report[:3000]}\n```")
            logger.info("Decay alert sent via Telegram.")
        except Exception as e:
            logger.warning("Telegram notification failed: %s", e)

    except ImportError:
        logger.warning("notifications.py not available.")


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_decay_alert(
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
    dry_run: bool = True,
    send_checkin: bool = False,
    alert_levels: list[str] | None = None,
    max_checkins: int = 10,
) -> dict:
    """
    Main decay alert runner. Call this from agent.py daily.

    Args:
        llm               : LangChain LLM (needed if send_checkin=True)
        browser           : browser_use Browser (needed if send_checkin=True)
        username          : LinkedIn email
        password          : LinkedIn password
        already_logged_in : Skip login if True
        dry_run           : If True, log only - do not send
        send_checkin      : If True, send check-in messages to fading contacts
        alert_levels      : List of levels to alert on (default: yellow+orange+red)
        max_checkins      : Max check-in messages to send per run

    Returns:
        Dict with summary stats.
    """
    if alert_levels is None:
        alert_levels = ALERT_LEVELS

    logger.info("=== Relationship Decay Alert === [DRY RUN: %s]", dry_run)

    # Get fading contacts
    fading = get_fading_contacts(min_level=min(alert_levels, key=ALERT_LEVELS.index))

    if not fading:
        logger.info("No fading contacts found. All relationships are active!")
        return {
            "total_fading": 0,
            "alerted": 0,
            "checkins_sent": 0,
            "report": "All relationships are active!",
        }

    # Build report
    report = build_decay_report(fading)
    logger.info("\n%s", report)

    # Send notification
    send_decay_notification(report, dry_run=dry_run)

    # Log alerts
    alerted = 0
    for contact in fading:
        if not already_alerted_today(contact["contact"]):
            log_decay_alert(
                contact=contact["contact"],
                decay_level=contact["decay_level"],
                days_since=contact["days_since"],
            )
            alerted += 1

    # Send check-in messages
    checkins_sent = 0
    if send_checkin and llm and browser:
        from browser_use import Agent

        # Only send to orange and red contacts
        urgent = [c for c in fading
                  if c["decay_level"] in ("orange", "red")][:max_checkins]

        if urgent:
            task = build_checkin_task(
                fading_contacts=urgent,
                username=username,
                password=password,
                already_logged_in=already_logged_in,
                dry_run=dry_run,
            )
            try:
                agent = Agent(task=task, llm=llm, browser=browser)
                result = await agent.run()
                logger.info("Check-in result: %s", result)

                if not dry_run:
                    for c in urgent:
                        mark_checkin_sent(c["contact"])
                        checkins_sent += 1
            except Exception as e:
                logger.error("Check-in task failed: %s", e)

    summary = {
        "total_fading": len(fading),
        "alerted":      alerted,
        "checkins_sent": checkins_sent,
        "report":       report,
        "breakdown": {
            "yellow": len([c for c in fading if c["decay_level"] == "yellow"]),
            "orange": len([c for c in fading if c["decay_level"] == "orange"]),
            "red":    len([c for c in fading if c["decay_level"] == "red"]),
        },
    }

    logger.info(
        "Decay alert done: %d fading | %d alerted | %d checkins sent",
        summary["total_fading"], summary["alerted"], summary["checkins_sent"],
    )
    return summary


# ------------------------------------------------------------
# AGENT INSTRUCTIONS
# ------------------------------------------------------------

def build_decay_alert_instructions() -> str:
    """Build decay alert instructions for the browser agent."""
    fading = get_fading_contacts(min_level="orange")

    if not fading:
        return "No fading contacts found. All relationships are active."

    contacts_str = "\n".join(
        f"  - {c['contact']} (last contact: {c['days_since']} days ago)"
        for c in fading[:10]
    )

    return f"""
  RELATIONSHIP DECAY ALERT:
  The following contacts have not been interacted with recently.
  Consider sending a warm check-in message.

{contacts_str}

  For each contact above:
    - Send a brief, friendly check-in message on LinkedIn
    - Do NOT mention that you noticed they were inactive
    - Keep it natural and warm
"""