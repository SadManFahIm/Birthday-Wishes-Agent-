"""
work_anniversary_detector.py
----------------------------
Work Anniversary Detector for Birthday Wishes Agent.

Monitors LinkedIn connections for work anniversaries and
automatically sends personalized congratulation messages.

How it works:
  1. Reads contact job start dates from LinkedIn profiles
  2. Checks if today matches their work anniversary
  3. Calculates years at company (1 year, 5 years, 10 years etc.)
  4. Sends a personalized anniversary message
  5. Stores anniversary data for future reference

Special milestones:
  - 1 year  : First anniversary
  - 3 years : Growing milestone
  - 5 years : Major milestone
  - 10 years: Decade milestone
  - Any year: Regular anniversary

Integrates with:
  - agent.py : runs as a daily task
  - memory.py: reads/writes contact profile data

Usage:
    from work_anniversary_detector import (
        init_anniversary_table,
        run_anniversary_detector,
        get_todays_anniversaries,
        build_anniversary_report,
    )

    await run_anniversary_detector(dry_run=True)
"""

import logging
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

MAX_SCANS_PER_RUN = 20
SCAN_INTERVAL_DAYS = 30

# Milestone years that get special messages
MILESTONE_YEARS = [1, 3, 5, 10, 15, 20, 25]

# Message templates per milestone type
ANNIVERSARY_TEMPLATES = {
    "milestone_1": [
        "Hi {name}! Happy 1-year work anniversary at {company}! "
        "What an exciting first year it must have been. Here's to many more!",

        "Congratulations {name} on your 1-year anniversary at {company}! "
        "Hope the first year has been everything you hoped for!",
    ],
    "milestone_5": [
        "Hi {name}! A huge congratulations on your 5-year work anniversary at {company}! "
        "5 years is a real milestone — your dedication is truly inspiring.",

        "Wow, {name}! 5 years at {company} — that is seriously impressive. "
        "Congratulations on this milestone!",
    ],
    "milestone_10": [
        "Hi {name}! A decade at {company} — that is incredible! "
        "Congratulations on your 10-year work anniversary. "
        "What an amazing journey it must have been!",

        "10 years, {name}! Congratulations on this massive milestone at {company}. "
        "Your loyalty and dedication are truly admirable!",
    ],
    "milestone_other": [
        "Hi {name}! Congratulations on your {years}-year work anniversary at {company}! "
        "That is a wonderful achievement. Keep up the great work!",

        "Happy {years}-year work anniversary {name}! "
        "What a journey at {company} it has been. Wishing you continued success!",
    ],
    "regular": [
        "Hi {name}! Just noticed it is your work anniversary at {company}. "
        "Congratulations on another great year!",

        "Happy work anniversary {name}! Another year at {company} — "
        "hope it has been a great one!",

        "Congratulations on your work anniversary {name}! "
        "Hope {company} continues to be an amazing place to grow.",
    ],
}


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_anniversary_table():
    """Create work anniversary tracking tables."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_anniversaries (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL UNIQUE,
                company      TEXT,
                job_title    TEXT,
                start_date   TEXT,
                last_scanned TEXT,
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS anniversary_wishes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                contact        TEXT    NOT NULL,
                company        TEXT,
                years          INTEGER,
                milestone      INTEGER DEFAULT 0,
                wish_text      TEXT,
                wish_sent      INTEGER DEFAULT 0,
                dry_run        INTEGER DEFAULT 1,
                wish_date      TEXT    NOT NULL,
                created_at     TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Anniversary tables ready.")


# ------------------------------------------------------------
# STORAGE
# ------------------------------------------------------------

def save_anniversary_data(
    contact: str,
    company: str,
    job_title: str,
    start_date: str,
):
    """Save or update a contact's work start date."""
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO contact_anniversaries
                (contact, company, job_title, start_date,
                 last_scanned, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact) DO UPDATE SET
                company      = excluded.company,
                job_title    = excluded.job_title,
                start_date   = excluded.start_date,
                last_scanned = excluded.last_scanned,
                updated_at   = excluded.updated_at
        """, (contact, company, job_title, start_date,
              date.today().isoformat(), now, now))
        conn.commit()
    logger.info("Anniversary data saved: %s at %s since %s",
                contact, company, start_date)


def get_stored_anniversary(contact: str) -> dict | None:
    """Get stored anniversary data for a contact."""
    if not DB_FILE.exists():
        return None

    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT company, job_title, start_date, last_scanned
            FROM   contact_anniversaries
            WHERE  LOWER(contact) = LOWER(?)
        """, (contact,)).fetchone()

    if not row:
        return None

    return {
        "company":      row[0],
        "job_title":    row[1],
        "start_date":   row[2],
        "last_scanned": row[3],
    }


def already_wished_this_year(contact: str) -> bool:
    """Check if we already sent an anniversary wish this year."""
    if not DB_FILE.exists():
        return False

    year_start = date(date.today().year, 1, 1).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM anniversary_wishes
            WHERE LOWER(contact) = LOWER(?)
              AND wish_date >= ?
              AND dry_run = 0
        """, (contact, year_start)).fetchone()
    return (row[0] or 0) > 0


# ------------------------------------------------------------
# ANNIVERSARY DETECTION
# ------------------------------------------------------------

def get_todays_anniversaries() -> list[dict]:
    """
    Find contacts whose work anniversary is today.

    Returns:
        List of dicts: contact, company, job_title, years, is_milestone
    """
    if not DB_FILE.exists():
        return []

    today = date.today()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT contact, company, job_title, start_date
            FROM   contact_anniversaries
            WHERE  start_date IS NOT NULL
        """).fetchall()

    anniversaries = []
    for contact, company, job_title, start_date_str in rows:
        if not start_date_str:
            continue

        try:
            start = date.fromisoformat(start_date_str)
        except ValueError:
            # Try parsing partial dates like "2020-01" or "2020"
            start = _parse_partial_date(start_date_str)
            if not start:
                continue

        # Check if today is the anniversary (same month and day)
        if start.month == today.month and start.day == today.day:
            years = today.year - start.year
            if years <= 0:
                continue

            is_milestone = years in MILESTONE_YEARS
            anniversaries.append({
                "contact":     contact,
                "company":     company or "",
                "job_title":   job_title or "",
                "years":       years,
                "is_milestone": is_milestone,
                "start_date":  start_date_str,
            })
            logger.info(
                "Anniversary today: %s — %d years at %s (milestone: %s)",
                contact, years, company, is_milestone,
            )

    logger.info("Found %d work anniversaries today.", len(anniversaries))
    return anniversaries


def _parse_partial_date(date_str: str) -> date | None:
    """Parse partial date strings like '2020-01' or '2020'."""
    try:
        if len(date_str) == 4:
            return date(int(date_str), 1, 1)
        if len(date_str) == 7:
            parts = date_str.split("-")
            return date(int(parts[0]), int(parts[1]), 1)
        return None
    except (ValueError, IndexError):
        return None


# ------------------------------------------------------------
# MESSAGE GENERATION
# ------------------------------------------------------------

def get_anniversary_message(
    contact_name: str,
    company: str,
    years: int,
    is_milestone: bool,
) -> str:
    """Get a personalized work anniversary message."""
    first_name = contact_name.split()[0].capitalize()
    company    = company or "your company"

    if years == 1:
        templates = ANNIVERSARY_TEMPLATES["milestone_1"]
    elif years == 5:
        templates = ANNIVERSARY_TEMPLATES["milestone_5"]
    elif years == 10:
        templates = ANNIVERSARY_TEMPLATES["milestone_10"]
    elif is_milestone:
        templates = ANNIVERSARY_TEMPLATES["milestone_other"]
    else:
        templates = ANNIVERSARY_TEMPLATES["regular"]

    template = random.choice(templates)
    return template.format(name=first_name, company=company, years=years)


# ------------------------------------------------------------
# AGENT TASKS
# ------------------------------------------------------------

def build_scan_task(
    contacts: list[str],
    username: str,
    password: str,
    already_logged_in: bool = False,
) -> str:
    """Build agent task to scan LinkedIn profiles for work start dates."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    contacts_str = "\n".join(f"  - {c}" for c in contacts)

    return f"""
Open browser. {login}

GOAL: Find work start dates for each contact below.

Contacts to check:
{contacts_str}

For each contact:
  1. Search for them on LinkedIn
  2. Open their profile
  3. Look at their Experience section
  4. Find their CURRENT job start date (month and year)
  5. Also note their current company and job title

Report in this EXACT format for each contact:
  ANNIVERSARY: <contact_name> | <company> | <job_title> | <start_date>

  start_date format: YYYY-MM (e.g. 2021-03) or YYYY if only year shown

If no current job found:
  ANNIVERSARY: <contact_name> | none | none | none

Check all contacts. Do not send any messages.
"""


def build_wish_task(
    anniversaries: list[dict],
    username: str,
    password: str,
    already_logged_in: bool = False,
    dry_run: bool = True,
) -> str:
    """Build agent task to send anniversary wishes."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    dry = "[DRY RUN] Do NOT send. Print what you would send." if dry_run else ""

    messages_str = "\n".join(
        f"  {a['contact']} ({a['years']} years at {a['company']}): "
        f"\"{get_anniversary_message(a['contact'], a['company'], a['years'], a['is_milestone'])}\""
        for a in anniversaries
    )

    return f"""
Open browser. {login}
{dry}

GOAL: Send work anniversary wishes to contacts.

Messages to send:
{messages_str}

For each contact:
  1. Go to https://www.linkedin.com/messaging/
  2. Find or start their conversation
  3. Send the anniversary message
  4. Report: ANNIVERSARY SENT: <name> or ANNIVERSARY FAILED: <name>
"""


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def log_anniversary_wish(
    contact: str,
    company: str,
    years: int,
    is_milestone: bool,
    wish_text: str,
    dry_run: bool = True,
):
    """Log a sent anniversary wish."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO anniversary_wishes
            (contact, company, years, milestone, wish_text,
             wish_sent, dry_run, wish_date, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
        """, (contact, company, years, int(is_milestone),
              wish_text, int(dry_run),
              date.today().isoformat(), datetime.now().isoformat()))
        conn.commit()
    logger.info("Anniversary wish logged: %s (%d years)", contact, years)


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_anniversary_report(anniversaries: list[dict]) -> str:
    """Build human-readable anniversary report."""
    if not anniversaries:
        return "No work anniversaries today."

    milestones = [a for a in anniversaries if a["is_milestone"]]
    regular    = [a for a in anniversaries if not a["is_milestone"]]

    lines = [
        "Work Anniversary Report",
        "-" * 50,
        f"  Total today : {len(anniversaries)}",
        f"  Milestones  : {len(milestones)}",
        f"  Regular     : {len(regular)}",
        "-" * 50,
        "",
    ]

    if milestones:
        lines.append("MILESTONE ANNIVERSARIES:")
        for a in milestones:
            lines.append(
                f"  * {a['contact']} — {a['years']} years at {a['company']}"
            )
        lines.append("")

    if regular:
        lines.append("REGULAR ANNIVERSARIES:")
        for a in regular:
            lines.append(
                f"  - {a['contact']} — {a['years']} years at {a['company']}"
            )
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_anniversary_detector(
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
    dry_run: bool = True,
    scan_new_contacts: bool = True,
    max_scans: int = MAX_SCANS_PER_RUN,
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
        scan_new_contacts : If True, scan new contacts for start dates
        max_scans         : Max new contacts to scan per run

    Returns:
        Dict with summary stats.
    """
    from browser_use import Agent

    logger.info("=== Work Anniversary Detector === [DRY RUN: %s]", dry_run)

    # Step 1: Scan new contacts for start dates (weekly)
    if scan_new_contacts:
        contacts_to_scan = _get_contacts_to_scan(max_scans)
        if contacts_to_scan:
            scan_task = build_scan_task(
                contacts=contacts_to_scan,
                username=username,
                password=password,
                already_logged_in=already_logged_in,
            )
            try:
                agent  = Agent(task=scan_task, llm=llm, browser=browser)
                result = await agent.run()
                _parse_and_save_scan_result(str(result))
                already_logged_in = True
            except Exception as e:
                logger.error("Scan task failed: %s", e)

    # Step 2: Find today's anniversaries
    anniversaries = get_todays_anniversaries()

    if not anniversaries:
        logger.info("No work anniversaries today.")
        return {"anniversaries": 0, "wishes_sent": 0,
                "report": "No work anniversaries today."}

    # Filter already wished
    anniversaries = [
        a for a in anniversaries
        if not already_wished_this_year(a["contact"])
    ]

    if not anniversaries:
        logger.info("All anniversaries already wished this year.")
        return {"anniversaries": 0, "wishes_sent": 0}

    # Step 3: Send wishes
    wishes_sent = 0

    if dry_run:
        for a in anniversaries:
            msg = get_anniversary_message(
                a["contact"], a["company"], a["years"], a["is_milestone"]
            )
            logger.info("[DRY RUN] Would wish %s: %s", a["contact"], msg)
            log_anniversary_wish(
                a["contact"], a["company"], a["years"],
                a["is_milestone"], msg, dry_run=True,
            )
            wishes_sent += 1

    elif llm and browser:
        wish_task = build_wish_task(
            anniversaries=anniversaries,
            username=username,
            password=password,
            already_logged_in=already_logged_in,
            dry_run=False,
        )
        try:
            agent = Agent(task=wish_task, llm=llm, browser=browser)
            await agent.run()

            for a in anniversaries:
                msg = get_anniversary_message(
                    a["contact"], a["company"], a["years"], a["is_milestone"]
                )
                log_anniversary_wish(
                    a["contact"], a["company"], a["years"],
                    a["is_milestone"], msg, dry_run=False,
                )
                wishes_sent += 1

        except Exception as e:
            logger.error("Wish task failed: %s", e)

    report = build_anniversary_report(anniversaries)
    logger.info("Anniversary done: %d found | %d wished.",
                len(anniversaries), wishes_sent)

    return {
        "anniversaries": len(anniversaries),
        "wishes_sent":   wishes_sent,
        "report":        report,
    }


def _get_contacts_to_scan(limit: int) -> list[str]:
    """Get contacts not yet scanned for anniversary data."""
    if not DB_FILE.exists():
        return []

    cutoff = (date.today() - timedelta(days=SCAN_INTERVAL_DAYS)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        scanned = conn.execute("""
            SELECT LOWER(contact) FROM contact_anniversaries
            WHERE last_scanned >= ?
        """, (cutoff,)).fetchall()
        scanned_set = {row[0] for row in scanned}

        rows = conn.execute("""
            SELECT DISTINCT LOWER(contact) FROM history
            WHERE dry_run = 0 LIMIT 200
        """).fetchall()

    all_contacts = [row[0] for row in rows if row[0]]
    due = [c for c in all_contacts if c not in scanned_set]
    return due[:limit]


def _parse_and_save_scan_result(result_text: str):
    """Parse scan result and save anniversary data."""
    for line in result_text.splitlines():
        line = line.strip()
        if not line.upper().startswith("ANNIVERSARY:"):
            continue
        try:
            parts = line[12:].split("|")
            if len(parts) >= 4:
                contact    = parts[0].strip()
                company    = parts[1].strip()
                job_title  = parts[2].strip()
                start_date = parts[3].strip()

                if contact and start_date.lower() != "none":
                    save_anniversary_data(
                        contact=contact,
                        company="" if company.lower() == "none" else company,
                        job_title="" if job_title.lower() == "none" else job_title,
                        start_date=start_date,
                    )
        except Exception:
            continue
