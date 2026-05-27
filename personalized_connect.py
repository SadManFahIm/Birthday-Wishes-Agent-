"""
personalized_connect.py
-----------------------
Personalized LinkedIn Connection Request After Birthday Wish.

After sending a birthday wish to a contact, if they are a
2nd-degree connection, automatically sends a personalized
connection request that references the birthday wish.

Difference from auto_connect.py:
  - auto_connect.py  : INBOUND  - someone wishes YOU -> you connect
  - personalized_connect.py : OUTBOUND - YOU wish someone -> then connect

How it works:
  1. After sending a birthday wish, checks if contact is 1st or 2nd degree
  2. If 2nd degree -> sends a personalized connection request
  3. Note references the birthday wish naturally
  4. Respects daily connection limits
  5. Logs all requests to SQLite

Usage:
    from personalized_connect import (
        init_connect_request_table,
        run_personalized_connect,
        log_connect_request,
        get_connect_stats,
    )

    await run_personalized_connect(
        birthday_contacts=["John Smith", "Jane Doe"],
        dry_run=True,
    )
"""

import logging
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Daily connection request limit (LinkedIn recommends max 20/day)
MAX_CONNECTS_PER_DAY = 15

# Cooldown: don't retry same contact within N days
COOLDOWN_DAYS = 30

# Personalized note templates (max 300 chars for LinkedIn)
NOTE_TEMPLATES = [
    "Hi {name}! Just wished you a happy birthday and wanted to connect. "
    "Would love to stay in touch and follow your journey!",

    "Hey {name}! Sent you birthday wishes and thought this would be "
    "a great opportunity to connect. Hope we can stay in touch!",

    "Hi {name}! Happy Birthday again! Would love to add you to my network "
    "and follow your work. Hope to connect!",

    "Hello {name}! Just reached out with birthday wishes - "
    "thought it would be great to connect and keep in touch!",

    "Hi {name}! Wishing you a wonderful birthday! "
    "Would love to connect and follow your professional journey.",
]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_connect_request_table():
    """Create personalized connection request tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS personalized_connect_requests (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                note         TEXT,
                status       TEXT    DEFAULT 'sent',
                wish_date    TEXT    NOT NULL,
                dry_run      INTEGER DEFAULT 1,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Personalized connect request table ready.")


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def get_connects_sent_today() -> int:
    """Count connection requests sent today."""
    if not DB_FILE.exists():
        return 0

    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM personalized_connect_requests
            WHERE wish_date = ? AND dry_run = 0
        """, (date.today().isoformat(),)).fetchone()

    return row[0] or 0


def already_requested(contact: str) -> bool:
    """Check if we already sent a connection request to this contact."""
    if not DB_FILE.exists():
        return False

    cutoff = (date.today() - timedelta(days=COOLDOWN_DAYS)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM personalized_connect_requests
            WHERE LOWER(contact) = LOWER(?) AND wish_date >= ? AND dry_run = 0
        """, (contact, cutoff)).fetchone()

    return (row[0] or 0) > 0


def get_note(contact_name: str) -> str:
    """Get a personalized connection request note."""
    first_name = contact_name.split()[0].capitalize()
    note = random.choice(NOTE_TEMPLATES).format(name=first_name)
    # Ensure within LinkedIn 300 char limit
    return note[:295]


def log_connect_request(
    contact: str,
    note: str,
    dry_run: bool = True,
    status: str = "sent",
):
    """Log a sent connection request."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO personalized_connect_requests
            (contact, note, status, wish_date, dry_run, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (contact, note, status,
              date.today().isoformat(), int(dry_run),
              datetime.now().isoformat()))
        conn.commit()
    logger.info("Connect request logged: %s [%s]", contact, status)


def get_connect_stats() -> dict:
    """Get connection request stats."""
    if not DB_FILE.exists():
        return {"total": 0, "today": 0, "accepted": 0}

    with sqlite3.connect(DB_FILE) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM personalized_connect_requests WHERE dry_run = 0"
        ).fetchone()[0]

        today = conn.execute(
            "SELECT COUNT(*) FROM personalized_connect_requests "
            "WHERE wish_date = ? AND dry_run = 0",
            (date.today().isoformat(),)
        ).fetchone()[0]

        accepted = conn.execute(
            "SELECT COUNT(*) FROM personalized_connect_requests "
            "WHERE status = 'accepted' AND dry_run = 0"
        ).fetchone()[0]

    return {"total": total, "today": today, "accepted": accepted}


# ------------------------------------------------------------
# AGENT TASK
# ------------------------------------------------------------

def build_connect_task(
    birthday_contacts: list[str],
    username: str,
    password: str,
    already_logged_in: bool = False,
    dry_run: bool = True,
) -> str:
    """Build agent task for sending connection requests."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    dry = "[DRY RUN] Do NOT send. Print what you would send." if dry_run else ""

    contacts_str = "\n".join(
        f"  - {c}: Note: \"{get_note(c)}\""
        for c in birthday_contacts
    )

    return f"""
Open browser. {login}
{dry}

GOAL: Send personalized LinkedIn connection requests to contacts
you just wished a happy birthday to.

Contacts to connect with:
{contacts_str}

For each contact:
  1. Go to their LinkedIn profile
  2. Check their connection degree:
     - 1st degree (already connected) -> SKIP, just reply normally
     - 2nd degree -> send connection request with the note above
     - 3rd degree or no degree -> SKIP (too distant)
  3. Click "Connect" -> "Add a note" -> paste the note -> Send

Rules:
  - Only connect with 2nd degree contacts
  - Max {MAX_CONNECTS_PER_DAY} connections today total
  - Never connect if already connected (1st degree)
  - Note must be under 300 characters

Report for each contact:
  CONNECTED: <name> or SKIPPED: <name> (reason) or FAILED: <name>
"""


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_connect_report(results: list[dict]) -> str:
    """Build a human-readable connection request report."""
    if not results:
        return "No connection requests sent."

    connected = [r for r in results if r["status"] == "connected"]
    skipped   = [r for r in results if r["status"] == "skipped"]
    failed    = [r for r in results if r["status"] == "failed"]

    lines = [
        "Personalized Connect Request Report",
        "-" * 50,
        f"  Connected : {len(connected)}",
        f"  Skipped   : {len(skipped)}",
        f"  Failed    : {len(failed)}",
        "-" * 50,
        "",
    ]

    if connected:
        lines.append("Connected:")
        for r in connected:
            lines.append(f"  + {r['contact']}")
        lines.append("")

    if skipped:
        lines.append("Skipped:")
        for r in skipped:
            lines.append(f"  - {r['contact']} ({r.get('reason', '')})")
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_personalized_connect(
    birthday_contacts: list[str],
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
    dry_run: bool = True,
) -> dict:
    """
    Main runner. Call from agent.py after birthday wishes are sent.

    Args:
        birthday_contacts : List of contact names who were wished today
        llm               : LangChain LLM instance
        browser           : browser_use Browser instance
        username          : LinkedIn email
        password          : LinkedIn password
        already_logged_in : Skip login if True
        dry_run           : If True, log only - do not send

    Returns:
        Dict with summary stats.
    """
    logger.info("=== Personalized Connect === [DRY RUN: %s]", dry_run)

    if not birthday_contacts:
        logger.info("No birthday contacts to connect with.")
        return {"total": 0, "connected": 0}

    # Check daily limit
    sent_today = get_connects_sent_today()
    if sent_today >= MAX_CONNECTS_PER_DAY:
        logger.info("Daily connection limit reached (%d/%d).",
                    sent_today, MAX_CONNECTS_PER_DAY)
        return {"total": 0, "connected": 0,
                "reason": "Daily limit reached"}

    # Filter already requested
    eligible = [
        c for c in birthday_contacts
        if not already_requested(c)
    ]

    # Respect daily limit
    remaining = MAX_CONNECTS_PER_DAY - sent_today
    eligible  = eligible[:remaining]

    if not eligible:
        logger.info("All contacts already received connection requests recently.")
        return {"total": 0, "connected": 0}

    logger.info("Sending connection requests to %d contacts.", len(eligible))

    results = []

    if dry_run:
        for contact in eligible:
            note = get_note(contact)
            logger.info("[DRY RUN] Would connect with %s: %s", contact, note)
            log_connect_request(contact, note, dry_run=True, status="dry_run")
            results.append({"contact": contact, "status": "connected", "note": note})

    elif llm and browser:
        from browser_use import Agent

        task = build_connect_task(
            birthday_contacts=eligible,
            username=username,
            password=password,
            already_logged_in=already_logged_in,
            dry_run=False,
        )

        try:
            agent  = Agent(task=task, llm=llm, browser=browser)
            result = await agent.run()
            logger.info("Connect agent result: %s", result)

            # Log all as sent
            for contact in eligible:
                note = get_note(contact)
                log_connect_request(contact, note, dry_run=False, status="sent")
                results.append({"contact": contact, "status": "connected", "note": note})

        except Exception as e:
            logger.error("Connect task failed: %s", e)
            for contact in eligible:
                results.append({"contact": contact, "status": "failed"})

    report = build_connect_report(results)
    connected = len([r for r in results if r["status"] == "connected"])

    logger.info("Personalized connect done: %d/%d connected.",
                connected, len(eligible))

    return {
        "total":     len(eligible),
        "connected": connected,
        "report":    report,
    }


# ------------------------------------------------------------
# AGENT INSTRUCTIONS
# ------------------------------------------------------------

def build_personalized_connect_instructions(
    contact_name: str,
) -> str:
    """Build connection request instructions for the browser agent."""
    note = get_note(contact_name)
    stats = get_connect_stats()

    return f"""
  PERSONALIZED CONNECTION REQUEST:
  Contact : {contact_name}
  Note    : "{note}"

  Steps:
    1. Go to {contact_name}'s LinkedIn profile
    2. If 2nd degree -> click Connect -> Add Note -> paste note -> Send
    3. If 1st degree -> SKIP (already connected)
    4. If 3rd degree -> SKIP (too distant)

  Daily limit: {stats['today']}/{MAX_CONNECTS_PER_DAY} sent today.
  Report: CONNECTED: {contact_name} or SKIPPED: {contact_name}
"""
