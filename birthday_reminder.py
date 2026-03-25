"""
birthday_reminder.py
────────────────────
Birthday Reminder Email module for Birthday Wishes Agent.

Sends a reminder email to yourself (or someone else) the day before
a contact's birthday so you never forget to wish them.

Examples:
  "🎂 Tomorrow is Rahul's birthday — don't forget to wish!"
  "🎈 Reminder: Priya's birthday is tomorrow. She works at Google."

Features:
  - Scrapes upcoming birthdays from LinkedIn
  - Sends reminder emails for tomorrow's birthdays
  - Includes contact's job title and company in the email
  - Supports multiple recipients
  - Tracks sent reminders in SQLite to avoid duplicates

Setup:
  Add to .env:
    EMAIL_SENDER=your_gmail@gmail.com
    EMAIL_PASSWORD=your_app_password
    REMINDER_RECIPIENTS=you@gmail.com,spouse@gmail.com

Usage:
    from birthday_reminder import run_birthday_reminder
    await run_birthday_reminder(llm, browser)
"""

import logging
import smtplib
import sqlite3
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)
config  = Path(".env")
DB_FILE = Path("agent_history.db")

_env = dotenv_values(".env")
EMAIL_SENDER         = _env.get("EMAIL_SENDER", "")
EMAIL_PASSWORD       = _env.get("EMAIL_PASSWORD", "")
REMINDER_RECIPIENTS  = _env.get("REMINDER_RECIPIENTS", EMAIL_SENDER)


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_reminder_table():
    """Create the reminder tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS birthday_reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                contact     TEXT    NOT NULL,
                birthday    TEXT    NOT NULL,
                reminded_on TEXT    NOT NULL,
                recipients  TEXT,
                created_at  TEXT    NOT NULL,
                UNIQUE(contact, reminded_on)
            )
        """)
        conn.commit()
    logger.info("🗄️  Birthday reminder table ready.")


def already_reminded(contact: str, reminded_on: str) -> bool:
    """Check if a reminder was already sent for this contact today."""
    if not DB_FILE.exists():
        return False
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT id FROM birthday_reminders "
            "WHERE LOWER(contact) = LOWER(?) AND reminded_on = ?",
            (contact, reminded_on),
        ).fetchone()
    return row is not None


def log_reminder(contact: str, birthday: str, recipients: str):
    """Save a sent reminder to the database."""
    today = date.today().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO birthday_reminders "
            "(contact, birthday, reminded_on, recipients, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (contact, birthday, today, recipients, datetime.now().isoformat()),
        )
        conn.commit()
    logger.info("🗄️  Reminder logged for %s", contact)


# ──────────────────────────────────────────────
# EMAIL BUILDER
# ──────────────────────────────────────────────
def build_reminder_email(contacts_tomorrow: list[dict]) -> tuple[str, str]:
    """
    Build the reminder email subject and body.

    Args:
        contacts_tomorrow: List of dicts with name, job_title, company, birthday

    Returns:
        Tuple of (subject, html_body)
    """
    tomorrow = (date.today() + timedelta(days=1)).strftime("%B %d")
    count    = len(contacts_tomorrow)

    if count == 1:
        contact  = contacts_tomorrow[0]
        name     = contact.get("name", "Someone")
        subject  = f"🎂 Tomorrow is {name}'s Birthday — Don't Forget to Wish!"
    else:
        subject = f"🎂 {count} Birthdays Tomorrow — Don't Forget to Wish!"

    # Build contact cards for email body
    cards_html = ""
    cards_text = ""
    for c in contacts_tomorrow:
        name      = c.get("name", "Unknown")
        job_title = c.get("job_title", "")
        company   = c.get("company", "")
        profile   = c.get("linkedin_url", "")

        job_line = ""
        if job_title and company:
            job_line = f"{job_title} at {company}"
        elif job_title:
            job_line = job_title
        elif company:
            job_line = company

        profile_link = f'<a href="{profile}">View Profile</a>' if profile else ""

        cards_html += f"""
        <div style="background:#f8f9fa;border-left:4px solid #4CAF50;
                    padding:16px;margin:12px 0;border-radius:8px;">
            <h3 style="margin:0;color:#1a1a2e;">🎂 {name}</h3>
            {"<p style='margin:4px 0;color:#555;'>💼 " + job_line + "</p>" if job_line else ""}
            {"<p style='margin:4px 0;'>" + profile_link + "</p>" if profile_link else ""}
        </div>
"""
        cards_text += f"\n  🎂 {name}"
        if job_line:
            cards_text += f"\n     💼 {job_line}"
        if profile:
            cards_text += f"\n     🔗 {profile}"
        cards_text += "\n"

    html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;">

  <div style="background:linear-gradient(135deg,#667eea,#764ba2);
              padding:30px;border-radius:12px;text-align:center;color:white;">
    <h1 style="margin:0;font-size:2rem;">🎂 Birthday Reminder</h1>
    <p style="margin:8px 0 0;opacity:0.9;">
      {"Tomorrow is" if count == 1 else f"{count} birthdays are"} on <strong>{tomorrow}</strong>
    </p>
  </div>

  <div style="padding:20px 0;">
    <p style="color:#333;font-size:1rem;">
      Hey! Just a friendly reminder that the following
      {"person has" if count == 1 else "people have"} a birthday tomorrow.
      Don't forget to send them a warm wish! 😊
    </p>

    {cards_html}

    <div style="background:#e8f5e9;padding:16px;border-radius:8px;margin-top:20px;">
      <p style="margin:0;color:#2e7d32;font-weight:bold;">💡 Quick Tips</p>
      <ul style="color:#555;margin:8px 0;">
        <li>Send the wish in the morning for maximum impact</li>
        <li>A personalized message goes a long way</li>
        <li>Consider liking their latest post too!</li>
      </ul>
    </div>
  </div>

  <p style="color:#999;font-size:0.8rem;text-align:center;margin-top:20px;">
    Sent by Birthday Wishes Agent 🤖 | This is an automated reminder.
  </p>

</body>
</html>
"""

    return subject, html_body


# ──────────────────────────────────────────────
# SEND REMINDER EMAIL
# ──────────────────────────────────────────────
def send_reminder_email(contacts_tomorrow: list[dict]) -> bool:
    """
    Send birthday reminder email for tomorrow's birthdays.

    Args:
        contacts_tomorrow: List of contact dicts with name, job, company

    Returns:
        True if sent successfully.
    """
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        logger.warning("⚠️  Email not configured. Skipping reminder.")
        return False

    if not contacts_tomorrow:
        logger.info("📭 No birthdays tomorrow. No reminder needed.")
        return True

    recipients = [r.strip() for r in REMINDER_RECIPIENTS.split(",") if r.strip()]
    if not recipients:
        recipients = [EMAIL_SENDER]

    subject, html_body = build_reminder_email(contacts_tomorrow)

    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, recipients, msg.as_string())

        logger.info(
            "📧 Birthday reminder sent to %s for %d contact(s).",
            ", ".join(recipients), len(contacts_tomorrow),
        )

        # Log to DB
        for c in contacts_tomorrow:
            log_reminder(
                contact=c.get("name", "Unknown"),
                birthday=c.get("birthday", ""),
                recipients=", ".join(recipients),
            )

        return True

    except Exception as e:
        logger.error("❌ Reminder email failed: %s", e)
        return False


# ──────────────────────────────────────────────
# BROWSER TASK — Find tomorrow's birthdays
# ──────────────────────────────────────────────
def build_reminder_scrape_task(
    username: str,
    password: str,
    already_logged_in: bool,
) -> str:
    """Build a browser agent task to find tomorrow's LinkedIn birthdays."""
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%B %d")

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

    return f"""
  Open the browser.
  {login_instructions}

  GOAL: Find LinkedIn contacts whose birthday is TOMORROW ({tomorrow_str}).

  STEP 1 — Go to https://www.linkedin.com/mynetwork/
    Look for the "Birthdays" section.
    Check for any contacts listed as having a birthday tomorrow.

  STEP 2 — Also check the notification bell 🔔
    Look for upcoming birthday notifications for tomorrow.

  STEP 3 — For each contact with a birthday tomorrow:
    Visit their profile and note:
    - Full name and first name
    - Current job title
    - Current company
    - LinkedIn profile URL

  STEP 4 — Return results as a JSON array:
  [
    {{
      "name": "Full Name",
      "first_name": "First Name",
      "birthday": "{tomorrow_str}",
      "job_title": "Software Engineer",
      "company": "Google",
      "linkedin_url": "https://linkedin.com/in/username"
    }}
  ]

  If no birthdays tomorrow → return empty array: []
  Return ONLY the JSON array. No extra text.
"""


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_birthday_reminder(
    llm,
    browser,
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool = True,
) -> bool:
    """
    Scrape tomorrow's LinkedIn birthdays and send reminder emails.

    Returns:
        True if reminders were sent successfully.
    """
    import json
    from browser_use import Agent

    logger.info("=== Birthday Reminder Email === [DRY RUN: %s]", dry_run)

    task   = build_reminder_scrape_task(username, password, already_logged_in)
    agent  = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()

    # Parse contacts from result
    contacts_tomorrow = []
    try:
        result_str = str(result)
        start      = result_str.find("[")
        end        = result_str.rfind("]") + 1
        if start != -1 and end > start:
            contacts_tomorrow = json.loads(result_str[start:end])
            logger.info("📋 Found %d birthday(s) tomorrow.", len(contacts_tomorrow))
    except Exception as e:
        logger.error("❌ Could not parse birthday data: %s", e)

    if dry_run:
        logger.info(
            "[DRY RUN] Would send reminder for: %s",
            [c.get("name") for c in contacts_tomorrow],
        )
        return True

    return send_reminder_email(contacts_tomorrow)