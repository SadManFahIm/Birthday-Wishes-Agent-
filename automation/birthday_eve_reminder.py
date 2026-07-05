"""
birthday_eve_reminder.py
------------------------
Birthday Eve Reminder for Birthday Wishes Agent.

Sends a personal reminder notification the night before
a contact's birthday so you never miss one.

Reminder channels:
  - Telegram message
  - Email
  - Desktop notification (Windows/Mac/Linux)

How it works:
  1. Runs daily at a configured evening time (default 9 PM)
  2. Checks who has a birthday TOMORROW
  3. Sends reminder via Telegram and/or email
  4. Logs sent reminders to SQLite

Usage:
    from birthday_eve_reminder import (
        init_eve_reminder_table,
        run_birthday_eve_reminder,
        get_tomorrows_birthdays,
    )

    await run_birthday_eve_reminder(dry_run=True)
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_eve_reminder_table():
    """Create birthday eve reminder tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eve_reminders (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact       TEXT    NOT NULL,
                birthday_date TEXT    NOT NULL,
                channel       TEXT    NOT NULL,
                dry_run       INTEGER DEFAULT 1,
                sent_date     TEXT    NOT NULL,
                created_at    TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Birthday eve reminder table ready.")


# ------------------------------------------------------------
# GET TOMORROW'S BIRTHDAYS
# ------------------------------------------------------------

def get_tomorrows_birthdays() -> list[dict]:
    """
    Get contacts whose birthday is tomorrow.
    Reads from birthday detection history and predictive_birthday table.

    Returns:
        List of dicts: contact, birthday_date
    """
    if not DB_FILE.exists():
        return []

    tomorrow = date.today() + timedelta(days=1)
    results  = []

    with sqlite3.connect(DB_FILE) as conn:
        # From predictive_birthday table
        try:
            rows = conn.execute("""
                SELECT contact, predicted_date
                FROM   predicted_birthdays
                WHERE  strftime('%m-%d', predicted_date) = ?
                  AND  predicted_date >= ?
            """, (tomorrow.strftime("%m-%d"), tomorrow.isoformat())).fetchall()

            for contact, bday in rows:
                results.append({
                    "contact":       contact,
                    "birthday_date": bday,
                    "source":        "predicted",
                })
        except sqlite3.OperationalError:
            pass

        # From history (past birthday detections on same month/day)
        try:
            rows = conn.execute("""
                SELECT DISTINCT contact
                FROM   history
                WHERE  task LIKE '%BirthdayDetection%'
                  AND  strftime('%m-%d', date) = ?
                  AND  dry_run = 0
            """, (tomorrow.strftime("%m-%d"),)).fetchall()

            existing = {r["contact"] for r in results}
            for row in rows:
                if row[0] not in existing:
                    results.append({
                        "contact":       row[0],
                        "birthday_date": tomorrow.isoformat(),
                        "source":        "history",
                    })
        except sqlite3.OperationalError:
            pass

    logger.info("Found %d birthdays tomorrow (%s).",
                len(results), tomorrow.isoformat())
    return results


def already_reminded_today(contact: str) -> bool:
    """Check if we already sent an eve reminder for this contact today."""
    if not DB_FILE.exists():
        return False
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM eve_reminders
            WHERE LOWER(contact) = LOWER(?)
              AND sent_date = ? AND dry_run = 0
        """, (contact, date.today().isoformat())).fetchone()
    return (row[0] or 0) > 0


def log_eve_reminder(contact: str, birthday_date: str,
                     channel: str, dry_run: bool = True):
    """Log a sent eve reminder."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO eve_reminders
            (contact, birthday_date, channel, dry_run, sent_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (contact, birthday_date, channel, int(dry_run),
              date.today().isoformat(), datetime.now().isoformat()))
        conn.commit()
    logger.info("Eve reminder logged: %s via %s", contact, channel)


# ------------------------------------------------------------
# SEND REMINDER
# ------------------------------------------------------------

def build_reminder_message(contacts: list[dict]) -> str:
    """Build reminder message text."""
    tomorrow = date.today() + timedelta(days=1)
    names    = ", ".join(c["contact"].capitalize() for c in contacts)

    if len(contacts) == 1:
        c = contacts[0]
        return (
            f"Birthday Reminder!\n\n"
            f"{c['contact'].capitalize()} has a birthday tomorrow "
            f"({tomorrow.strftime('%B %d')}).\n\n"
            f"Don't forget to send them a wish!"
        )
    else:
        return (
            f"Birthday Reminder!\n\n"
            f"{len(contacts)} contacts have birthdays tomorrow "
            f"({tomorrow.strftime('%B %d')}):\n"
            f"{names}\n\n"
            f"Don't forget to send them wishes!"
        )


def send_telegram_reminder(message: str, dry_run: bool = True) -> bool:
    """Send reminder via Telegram."""
    if dry_run:
        logger.info("[DRY RUN] Telegram reminder: %s", message[:80])
        return True

    try:
        from dotenv import dotenv_values
        import requests

        config    = dotenv_values(".env")
        bot_token = config.get("TELEGRAM_BOT_TOKEN", "")
        chat_id   = config.get("TELEGRAM_CHAT_ID", "")

        if not bot_token or not chat_id:
            logger.warning("Telegram credentials missing in .env")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text":    message,
        }, timeout=10)

        if response.status_code == 200:
            logger.info("Telegram reminder sent.")
            return True
        else:
            logger.error("Telegram failed: %s", response.text[:100])
            return False

    except Exception as e:
        logger.error("Telegram reminder error: %s", e)
        return False


def send_email_reminder(message: str, dry_run: bool = True) -> bool:
    """Send reminder via email."""
    if dry_run:
        logger.info("[DRY RUN] Email reminder: %s", message[:80])
        return True

    try:
        import smtplib
        from email.mime.text import MIMEText
        from dotenv import dotenv_values

        config   = dotenv_values(".env")
        sender   = config.get("EMAIL_SENDER", "")
        password = config.get("EMAIL_PASSWORD", "")
        receiver = config.get("REMINDER_RECIPIENTS", sender)

        if not sender or not password:
            logger.warning("Email credentials missing in .env")
            return False

        tomorrow = date.today() + timedelta(days=1)
        subject  = f"Birthday Eve Reminder — {tomorrow.strftime('%B %d')}"

        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"]    = sender
        msg["To"]      = receiver

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)

        logger.info("Email reminder sent to %s.", receiver)
        return True

    except Exception as e:
        logger.error("Email reminder error: %s", e)
        return False


def send_desktop_notification(message: str, dry_run: bool = True) -> bool:
    """Send desktop notification (Windows/Mac/Linux)."""
    if dry_run:
        logger.info("[DRY RUN] Desktop notification: %s", message[:60])
        return True

    try:
        import platform
        system = platform.system()
        title  = "Birthday Wishes Agent"

        if system == "Windows":
            from win10toast import ToastNotifier
            toast = ToastNotifier()
            toast.show_toast(title, message[:200], duration=10)
            return True

        elif system == "Darwin":
            import subprocess
            subprocess.run([
                "osascript", "-e",
                f'display notification "{message[:100]}" with title "{title}"'
            ])
            return True

        elif system == "Linux":
            import subprocess
            subprocess.run(["notify-send", title, message[:100]])
            return True

    except ImportError:
        logger.warning("Desktop notification library not available.")
    except Exception as e:
        logger.error("Desktop notification error: %s", e)

    return False


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_eve_report(contacts: list[dict], channels_used: list[str]) -> str:
    """Build eve reminder report."""
    tomorrow = date.today() + timedelta(days=1)

    if not contacts:
        return f"No birthdays tomorrow ({tomorrow.strftime('%B %d')})."

    lines = [
        "Birthday Eve Reminder Report",
        "-" * 50,
        f"  Tomorrow      : {tomorrow.strftime('%B %d, %Y')}",
        f"  Birthdays     : {len(contacts)}",
        f"  Channels used : {', '.join(channels_used) or 'none'}",
        "-" * 50,
        "",
        "Contacts with birthday tomorrow:",
    ]
    for c in contacts:
        lines.append(f"  - {c['contact'].capitalize()}")

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_birthday_eve_reminder(
    dry_run: bool = True,
    send_telegram: bool = True,
    send_email: bool = True,
    send_desktop: bool = False,
) -> dict:
    """
    Main runner. Call from agent.py every evening (e.g. 9 PM).

    Args:
        dry_run        : If True, log only - do not send
        send_telegram  : Send via Telegram
        send_email     : Send via email
        send_desktop   : Send desktop notification

    Returns:
        Dict with summary stats.
    """
    logger.info("=== Birthday Eve Reminder === [DRY RUN: %s]", dry_run)

    contacts = get_tomorrows_birthdays()

    if not contacts:
        logger.info("No birthdays tomorrow. No reminder needed.")
        return {
            "birthdays_tomorrow": 0,
            "reminders_sent":     0,
            "report": "No birthdays tomorrow.",
        }

    # Filter already reminded today
    contacts = [c for c in contacts if not already_reminded_today(c["contact"])]

    if not contacts:
        logger.info("Eve reminders already sent today.")
        return {"birthdays_tomorrow": 0, "reminders_sent": 0}

    message       = build_reminder_message(contacts)
    channels_used = []
    reminders_sent = 0

    if send_telegram:
        success = send_telegram_reminder(message, dry_run=dry_run)
        if success:
            channels_used.append("telegram")
            reminders_sent += 1
            for c in contacts:
                log_eve_reminder(c["contact"], c["birthday_date"],
                                 "telegram", dry_run=dry_run)

    if send_email:
        success = send_email_reminder(message, dry_run=dry_run)
        if success:
            channels_used.append("email")
            if "telegram" not in channels_used:
                reminders_sent += 1
            for c in contacts:
                log_eve_reminder(c["contact"], c["birthday_date"],
                                 "email", dry_run=dry_run)

    if send_desktop:
        success = send_desktop_notification(message, dry_run=dry_run)
        if success:
            channels_used.append("desktop")

    report = build_eve_report(contacts, channels_used)
    logger.info("Eve reminder done: %d birthdays | channels: %s",
                len(contacts), channels_used)

    return {
        "birthdays_tomorrow": len(contacts),
        "reminders_sent":     reminders_sent,
        "channels":           channels_used,
        "report":             report,
    }
