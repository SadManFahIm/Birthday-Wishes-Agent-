"""
calendar_export.py
──────────────────
Birthday Calendar Export module.

Exports LinkedIn contacts' birthdays to a .ics file
that can be imported into Google Calendar, Apple Calendar, or Outlook.

Features:
  - Scrapes birthday info from LinkedIn contacts
  - Creates recurring yearly birthday events
  - Adds 1-day reminder/alarm
  - Saves as birthdays.ics in the project folder

Usage:
    from calendar_export import export_birthday_calendar
    await export_birthday_calendar(llm, browser)

Import into Google Calendar:
    1. Go to calendar.google.com
    2. Settings → Import & Export → Import
    3. Upload birthdays.ics
"""

import logging
import uuid
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CALENDAR_FILE = Path("birthdays.ics")


# ──────────────────────────────────────────────
# ICS FILE BUILDER
# ──────────────────────────────────────────────
def build_ics(contacts: list[dict]) -> str:
    """
    Build an .ics calendar string from a list of contacts.

    Args:
        contacts: List of dicts with keys:
            - name       (str)  : Contact's full name
            - birthday   (str)  : "MM-DD" or "YYYY-MM-DD"
            - linkedin_url (str): Profile URL (optional)

    Returns:
        ICS file content as string.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Birthday Wishes Agent//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:LinkedIn Birthdays 🎂",
        "X-WR-TIMEZONE:UTC",
    ]

    for contact in contacts:
        name     = contact.get("name", "Unknown")
        birthday = contact.get("birthday", "")
        url      = contact.get("linkedin_url", "")

        if not birthday:
            continue

        # Parse birthday — support "MM-DD" and "YYYY-MM-DD"
        try:
            if len(birthday) == 5:  # MM-DD
                month, day = birthday.split("-")
                year = date.today().year
            else:  # YYYY-MM-DD
                parts = birthday.split("-")
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])

            # Use current year for recurring events
            dtstart = f"{date.today().year}{int(month):02d}{int(day):02d}"
        except Exception:
            logger.warning("⚠️  Could not parse birthday for %s: %s", name, birthday)
            continue

        uid        = str(uuid.uuid4())
        now_stamp  = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        description = f"Birthday of {name}"
        if url:
            description += f"\\nLinkedIn: {url}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtstart}",
            f"SUMMARY:🎂 {name}'s Birthday",
            f"DESCRIPTION:{description}",
            "RRULE:FREQ=YEARLY",       # Repeats every year
            "BEGIN:VALARM",
            "TRIGGER:-P1D",            # Remind 1 day before
            "ACTION:DISPLAY",
            f"DESCRIPTION:Reminder: {name}'s birthday is tomorrow! 🎂",
            "END:VALARM",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def save_ics(contacts: list[dict]) -> Path:
    """
    Generate and save the .ics file.

    Returns:
        Path to the saved .ics file.
    """
    content = build_ics(contacts)
    CALENDAR_FILE.write_text(content, encoding="utf-8")
    logger.info("📅 Calendar exported: %s (%d contacts)", CALENDAR_FILE, len(contacts))
    return CALENDAR_FILE


# ──────────────────────────────────────────────
# BROWSER TASK — Scrape birthdays from LinkedIn
# ──────────────────────────────────────────────
def build_birthday_scrape_task(
    username: str,
    password: str,
    already_logged_in: bool,
) -> str:
    """
    Build a browser agent task to scrape all LinkedIn
    contacts' birthdays and return them as JSON.
    """
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

  GOAL: Collect birthday information for as many LinkedIn contacts as possible.

  STEP 1 — Check upcoming birthdays section.
    Go to https://www.linkedin.com/mynetwork/
    Look for the "Birthdays" section.
    Note all contacts shown with their birthday dates.

  STEP 2 — Check notifications for birthday info.
    Click the notification bell 🔔.
    Look for past and upcoming birthday notifications.
    Note the names and dates.

  STEP 3 — Return results as a JSON array:
  [
    {{
      "name": "Full Name",
      "birthday": "MM-DD",
      "linkedin_url": "https://linkedin.com/in/username"
    }},
    ...
  ]

  Rules:
    - Include ONLY contacts where you know the birthday date.
    - If year is unknown, use "MM-DD" format.
    - If year is known, use "YYYY-MM-DD" format.
    - Return ONLY the JSON array. No extra text.
"""


# ──────────────────────────────────────────────
# MAIN EXPORT FUNCTION
# ──────────────────────────────────────────────
async def export_birthday_calendar(
    llm,
    browser,
    username: str,
    password: str,
    already_logged_in: bool,
) -> Path:
    """
    Scrape LinkedIn contacts' birthdays and export to .ics file.

    Returns:
        Path to the generated .ics file.
    """
    import json
    from browser_use import Agent

    logger.info("=== Birthday Calendar Export ===")

    task = build_birthday_scrape_task(username, password, already_logged_in)
    agent = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()

    # Parse JSON from result
    contacts = []
    try:
        result_str = str(result)
        # Find JSON array in result
        start = result_str.find("[")
        end   = result_str.rfind("]") + 1
        if start != -1 and end > start:
            contacts = json.loads(result_str[start:end])
            logger.info("📋 Found %d contacts with birthdays.", len(contacts))
    except Exception as e:
        logger.error("❌ Could not parse birthday data: %s", e)
        contacts = []

    if contacts:
        path = save_ics(contacts)
        logger.info("✅ Calendar saved to: %s", path)
        return path
    else:
        logger.warning("⚠️  No birthday data found.")
        return None