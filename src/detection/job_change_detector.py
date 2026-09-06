"""
job_change_detector.py
----------------------
Job Change Detector for Birthday Wishes Agent.

Monitors LinkedIn connections for job changes and automatically
sends personalized congratulation messages.

How it works:
  1. Scans LinkedIn connections' profiles periodically
  2. Compares current job/company with last stored data
  3. Detects: new job, promotion, company change
  4. Sends a personalized congratulation message
  5. Updates stored profile data for next comparison

Detects:
  - New job at a different company
  - Promotion (same company, different title)
  - Started own business / freelance
  - Left a company (no longer shows job)

Integrates with:
  - memory.py     : reads/writes contact profile data
  - agent.py      : runs as a scheduled weekly task
  - notifications : sends alert when job change detected

Usage:
    from job_change_detector import (
        init_job_change_table,
        run_job_change_detector,
        get_recent_job_changes,
        build_job_change_report,
    )

    await run_job_change_detector(dry_run=True)
"""

import logging
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# How many days between scans per contact
SCAN_INTERVAL_DAYS = 7

# Max contacts to scan per run (to avoid rate limits)
MAX_SCANS_PER_RUN = 20

# Congratulation message templates
CONGRATS_TEMPLATES = {
    "new_job": [
        "Hi {name}! Just saw that you have joined {company} as {title}. "
        "Congratulations! That is a fantastic move. Wishing you all the best!",

        "Congratulations {name}! Starting a new role as {title} at {company} "
        "is exciting news. Hope it is everything you hoped for!",

        "Hi {name}! Big congratulations on your new role at {company}! "
        "Wishing you a great start and lots of success ahead.",
    ],
    "promotion": [
        "Hi {name}! Congratulations on your promotion to {title}! "
        "That is a well-deserved recognition. Keep up the amazing work!",

        "Congrats {name}! Moving up to {title} is fantastic news. "
        "Your hard work is clearly paying off!",

        "Hi {name}! I just saw you became {title} — congratulations! "
        "Wishing you continued success in the new role.",
    ],
    "new_company": [
        "Hi {name}! Exciting to see you have moved to {company}. "
        "Congratulations on the new chapter! Hope it goes brilliantly.",

        "Congratulations {name}! Joining {company} sounds like a great opportunity. "
        "Wishing you all the best in your new journey!",

        "Hi {name}! Big congrats on the move to {company}! "
        "A new company means new adventures — excited for you!",
    ],
    "started_business": [
        "Hi {name}! Starting your own venture is incredibly exciting. "
        "Congratulations and wishing you massive success!",

        "Congrats {name}! Taking the entrepreneurial leap takes courage. "
        "Rooting for you all the way!",
    ],
}


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_job_change_table():
    """Create job change tracking tables."""
    with sqlite3.connect(DB_FILE) as conn:
        # Store last known job per contact
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_jobs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL UNIQUE,
                job_title    TEXT,
                company      TEXT,
                last_scanned TEXT,
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            )
        """)
        # Log detected job changes
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_changes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                contact        TEXT    NOT NULL,
                change_type    TEXT    NOT NULL,
                old_title      TEXT,
                old_company    TEXT,
                new_title      TEXT,
                new_company    TEXT,
                congrats_sent  INTEGER DEFAULT 0,
                congrats_text  TEXT,
                dry_run        INTEGER DEFAULT 1,
                detected_date  TEXT    NOT NULL,
                created_at     TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Job change tables ready.")


# ------------------------------------------------------------
# JOB STORAGE
# ------------------------------------------------------------

def get_stored_job(contact: str) -> dict | None:
    """Get last known job info for a contact."""
    if not DB_FILE.exists():
        return None

    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT job_title, company, last_scanned
            FROM   contact_jobs
            WHERE  LOWER(contact) = LOWER(?)
        """, (contact,)).fetchone()

    if not row:
        return None

    return {
        "job_title":    row[0],
        "company":      row[1],
        "last_scanned": row[2],
    }


def save_job(contact: str, job_title: str, company: str):
    """Save or update a contact's current job."""
    now = datetime.now().isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO contact_jobs
                (contact, job_title, company, last_scanned, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact) DO UPDATE SET
                job_title    = excluded.job_title,
                company      = excluded.company,
                last_scanned = excluded.last_scanned,
                updated_at   = excluded.updated_at
        """, (contact, job_title, company,
              date.today().isoformat(), now, now))
        conn.commit()
    logger.info("Job saved for %s: %s at %s", contact, job_title, company)


def needs_scan(contact: str) -> bool:
    """Check if a contact is due for a job scan."""
    stored = get_stored_job(contact)
    if not stored or not stored["last_scanned"]:
        return True

    try:
        last = date.fromisoformat(stored["last_scanned"])
        return (date.today() - last).days >= SCAN_INTERVAL_DAYS
    except ValueError:
        return True


# ------------------------------------------------------------
# CHANGE DETECTION
# ------------------------------------------------------------

def detect_change(
    contact: str,
    new_title: str,
    new_company: str,
) -> dict | None:
    """
    Compare new job info with stored data.

    Returns:
        Dict with change_type, old/new title/company, or None if no change.
    """
    stored = get_stored_job(contact)

    # First time seeing this contact — save and skip
    if not stored:
        save_job(contact, new_title, new_company)
        logger.info("First scan for %s — saved job data.", contact)
        return None

    old_title   = (stored.get("job_title") or "").strip().lower()
    old_company = (stored.get("company") or "").strip().lower()
    cur_title   = (new_title or "").strip().lower()
    cur_company = (new_company or "").strip().lower()

    # No change
    if old_title == cur_title and old_company == cur_company:
        logger.info("No job change for %s.", contact)
        save_job(contact, new_title, new_company)
        return None

    # Determine change type
    if not old_company and cur_company:
        change_type = "new_job"
    elif old_company != cur_company and cur_company:
        # Check if it looks like own business
        own_biz_keywords = ["self", "freelance", "founder", "co-founder",
                            "owner", "entrepreneur", "independent"]
        if any(k in cur_title.lower() for k in own_biz_keywords):
            change_type = "started_business"
        else:
            change_type = "new_company"
    elif old_company == cur_company and old_title != cur_title:
        change_type = "promotion"
    else:
        change_type = "new_job"

    logger.info(
        "Job change detected for %s: [%s] %s @ %s -> %s @ %s",
        contact, change_type,
        stored["job_title"], stored["company"],
        new_title, new_company,
    )

    return {
        "contact":     contact,
        "change_type": change_type,
        "old_title":   stored["job_title"],
        "old_company": stored["company"],
        "new_title":   new_title,
        "new_company": new_company,
    }


def log_job_change(change: dict, dry_run: bool = True) -> int:
    """Log a detected job change to DB."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("""
            INSERT INTO job_changes
            (contact, change_type, old_title, old_company,
             new_title, new_company, dry_run, detected_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            change["contact"], change["change_type"],
            change["old_title"], change["old_company"],
            change["new_title"], change["new_company"],
            int(dry_run), date.today().isoformat(),
            datetime.now().isoformat(),
        ))
        change_id = cursor.lastrowid
        conn.commit()
    return change_id


def mark_congrats_sent(change_id: int, congrats_text: str):
    """Mark congratulations as sent."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE job_changes
            SET    congrats_sent = 1, congrats_text = ?
            WHERE  id = ?
        """, (congrats_text, change_id))
        conn.commit()
    logger.info("Congrats marked sent (ID: %d)", change_id)


# ------------------------------------------------------------
# MESSAGE GENERATION
# ------------------------------------------------------------

def get_congrats_message(
    contact_name: str,
    change_type: str,
    new_title: str = "",
    new_company: str = "",
) -> str:
    """Get a personalized congratulation message."""
    first_name = contact_name.split()[0].capitalize()
    templates  = CONGRATS_TEMPLATES.get(change_type, CONGRATS_TEMPLATES["new_job"])
    template   = random.choice(templates)

    return template.format(
        name=first_name,
        title=new_title or "your new role",
        company=new_company or "your new company",
    )


# ------------------------------------------------------------
# AGENT TASKS
# ------------------------------------------------------------

def build_scan_task(
    contacts: list[str],
    username: str,
    password: str,
    already_logged_in: bool = False,
) -> str:
    """Build agent task to scan LinkedIn profiles for job changes."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    contacts_str = "\n".join(f"  - {c}" for c in contacts)

    return f"""
Open browser. {login}

GOAL: Check current job title and company for each contact below.

Contacts to check:
{contacts_str}

For each contact:
  1. Search for them on LinkedIn
  2. Open their profile
  3. Read their CURRENT job title and company (the most recent one)
  4. Report in this exact format:
     JOB: <contact_name> | <job_title> | <company_name>

  If no job listed, report:
     JOB: <contact_name> | none | none

Check all contacts. Do not send any messages.
"""


def build_congrats_task(
    job_changes: list[dict],
    username: str,
    password: str,
    already_logged_in: bool = False,
    dry_run: bool = True,
) -> str:
    """Build agent task to send congratulation messages."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    dry = "[DRY RUN] Do NOT send. Print what you would send." if dry_run else ""

    messages_str = "\n".join(
        f"  {c['contact']}: \"{get_congrats_message(c['contact'], c['change_type'], c['new_title'], c['new_company'])}\""
        for c in job_changes
    )

    return f"""
Open browser. {login}
{dry}

GOAL: Send congratulation messages for job changes detected.

Messages to send:
{messages_str}

For each contact:
  1. Go to https://www.linkedin.com/messaging/
  2. Find their conversation or start a new one
  3. Send the congratulation message
  4. Report: CONGRATS SENT: <name> or CONGRATS FAILED: <name>
"""


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def get_recent_job_changes(days: int = 30) -> list[dict]:
    """Get recently detected job changes."""
    if not DB_FILE.exists():
        return []

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT contact, change_type, old_title, old_company,
                   new_title, new_company, congrats_sent, detected_date
            FROM   job_changes
            WHERE  detected_date >= ?
            ORDER  BY detected_date DESC
        """, (cutoff,)).fetchall()

    return [
        {
            "contact":      row[0],
            "change_type":  row[1],
            "old_title":    row[2],
            "old_company":  row[3],
            "new_title":    row[4],
            "new_company":  row[5],
            "congrats_sent": bool(row[6]),
            "detected_date": row[7],
        }
        for row in rows
    ]


def build_job_change_report(changes: list[dict] | None = None) -> str:
    """Build human-readable job change report."""
    if changes is None:
        changes = get_recent_job_changes()

    if not changes:
        return "No job changes detected recently."

    type_labels = {
        "new_job":          "New Job",
        "promotion":        "Promotion",
        "new_company":      "Changed Company",
        "started_business": "Started Own Business",
    }

    lines = [
        "Job Change Detector Report",
        "-" * 55,
        f"  Total detected : {len(changes)}",
        f"  Congrats sent  : {sum(1 for c in changes if c['congrats_sent'])}",
        "-" * 55,
        "",
    ]

    for c in changes:
        label  = type_labels.get(c["change_type"], c["change_type"])
        status = "SENT" if c["congrats_sent"] else "PENDING"

        lines.append(f"  [{status}] {c['contact']} — {label}")
        lines.append(f"    Before : {c['old_title']} at {c['old_company']}")
        lines.append(f"    After  : {c['new_title']} at {c['new_company']}")
        lines.append(f"    Date   : {c['detected_date']}")
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_job_change_detector(
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
    dry_run: bool = True,
    contacts: list[str] | None = None,
    max_scans: int = MAX_SCANS_PER_RUN,
    send_congrats: bool = True,
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
        contacts          : List of contact names to scan.
                            If None, reads from history table.
        max_scans         : Max contacts to scan per run
        send_congrats     : If True, send congratulation messages

    Returns:
        Dict with summary stats.
    """
    from browser_use import Agent

    logger.info("=== Job Change Detector === [DRY RUN: %s]", dry_run)

    # Get contacts to scan
    if not contacts:
        contacts = _get_contacts_to_scan(max_scans)

    if not contacts:
        logger.info("No contacts due for job scan.")
        return {"scanned": 0, "changes": 0, "congrats_sent": 0}

    logger.info("Scanning %d contacts for job changes...", len(contacts))

    # Step 1: Scan profiles
    scan_task = build_scan_task(
        contacts=contacts,
        username=username,
        password=password,
        already_logged_in=already_logged_in,
    )

    job_data = {}
    try:
        agent  = Agent(task=scan_task, llm=llm, browser=browser)
        result = await agent.run()

        # Parse result: "JOB: <name> | <title> | <company>"
        job_data = _parse_scan_result(str(result))
        logger.info("Parsed job data for %d contacts.", len(job_data))

    except Exception as e:
        logger.error("Scan task failed: %s", e)
        return {"scanned": 0, "changes": 0, "congrats_sent": 0}

    # Step 2: Detect changes
    detected_changes = []
    for contact, info in job_data.items():
        change = detect_change(
            contact=contact,
            new_title=info.get("title", ""),
            new_company=info.get("company", ""),
        )
        if change:
            change_id = log_job_change(change, dry_run=dry_run)
            change["id"] = change_id
            detected_changes.append(change)
            # Update stored job
            save_job(contact, info.get("title", ""), info.get("company", ""))

    logger.info("Detected %d job changes.", len(detected_changes))

    # Step 3: Send congratulations
    congrats_sent = 0
    if send_congrats and detected_changes:
        congrats_task = build_congrats_task(
            job_changes=detected_changes,
            username=username,
            password=password,
            already_logged_in=True,
            dry_run=dry_run,
        )

        try:
            agent  = Agent(task=congrats_task, llm=llm, browser=browser)
            await agent.run()

            if not dry_run:
                for c in detected_changes:
                    msg = get_congrats_message(
                        c["contact"], c["change_type"],
                        c["new_title"], c["new_company"],
                    )
                    mark_congrats_sent(c["id"], msg)
                    congrats_sent += 1

        except Exception as e:
            logger.error("Congrats task failed: %s", e)

    report = build_job_change_report(detected_changes)
    logger.info("Job change scan done: %d scanned | %d changes | %d congrats",
                len(contacts), len(detected_changes), congrats_sent)

    return {
        "scanned":       len(contacts),
        "changes":       len(detected_changes),
        "congrats_sent": congrats_sent,
        "report":        report,
    }


def _get_contacts_to_scan(limit: int) -> list[str]:
    """Get contacts that are due for a job scan."""
    if not DB_FILE.exists():
        return []

    cutoff = (date.today() - timedelta(days=SCAN_INTERVAL_DAYS)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        # Contacts not scanned recently
        scanned_recently = conn.execute("""
            SELECT contact FROM contact_jobs
            WHERE last_scanned >= ?
        """, (cutoff,)).fetchall()
        scanned_set = {row[0].lower() for row in scanned_recently}

        # Get contacts from history
        rows = conn.execute("""
            SELECT DISTINCT LOWER(contact) FROM history
            WHERE dry_run = 0
            LIMIT 200
        """).fetchall()

    all_contacts = [row[0] for row in rows if row[0]]
    due = [c for c in all_contacts if c not in scanned_set]

    return due[:limit]


def _parse_scan_result(result_text: str) -> dict:
    """
    Parse agent scan result into contact -> {title, company} dict.

    Expected format: "JOB: <name> | <title> | <company>"
    """
    job_data = {}
    for line in result_text.splitlines():
        line = line.strip()
        if not line.upper().startswith("JOB:"):
            continue
        try:
            parts = line[4:].split("|")
            if len(parts) >= 3:
                name    = parts[0].strip()
                title   = parts[1].strip()
                company = parts[2].strip()
                if name and name.lower() != "none":
                    job_data[name] = {
                        "title":   "" if title.lower() == "none" else title,
                        "company": "" if company.lower() == "none" else company,
                    }
        except Exception:
            continue
    return job_data


# ------------------------------------------------------------
# AGENT INSTRUCTIONS
# ------------------------------------------------------------

def build_job_detector_instructions() -> str:
    """Build job detector instructions for the browser agent."""
    recent = get_recent_job_changes(days=7)

    if not recent:
        return "No job changes detected in the last 7 days."

    lines = ["JOB CHANGES DETECTED (last 7 days):"]
    for c in recent[:5]:
        lines.append(
            f"  - {c['contact']}: {c['change_type']} -> "
            f"{c['new_title']} at {c['new_company']}"
        )
    return "\n".join(lines)
