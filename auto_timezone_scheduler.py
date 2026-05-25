"""
auto_timezone_scheduler.py
--------------------------
Auto-Schedule by Contact Timezone for Birthday Wishes Agent.

Fully automatic timezone detection and wish scheduling.
No manual configuration needed - the agent detects each
contact's timezone from their LinkedIn profile and schedules
wishes to arrive at 9:00 AM their local time.

How it works:
  1. Reads contact's location from LinkedIn profile
  2. Maps location to timezone automatically
  3. Calculates what UTC time = 9:00 AM in their timezone
  4. Schedules the wish to send at that exact UTC time
  5. Falls back to immediate send if timezone unknown

Integrates with:
  - best_time_connect.py : activity pattern data
  - agent.py             : runs as scheduled task
  - apscheduler          : job scheduling

Usage:
    from auto_timezone_scheduler import (
        init_scheduler_table,
        schedule_wish_for_contact,
        run_auto_timezone_scheduler,
        get_pending_scheduled_wishes,
    )

    await run_auto_timezone_scheduler(dry_run=True)
"""

import logging
import sqlite3
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Target send time in contact's local timezone
TARGET_HOUR   = 9
TARGET_MINUTE = 0

# Fallback timezone if detection fails
FALLBACK_TZ = "UTC"

# Location to timezone mapping (common cities/countries)
LOCATION_TZ_MAP = {
    # Bangladesh
    "dhaka":        "Asia/Dhaka",
    "bangladesh":   "Asia/Dhaka",
    "chittagong":   "Asia/Dhaka",
    "sylhet":       "Asia/Dhaka",

    # India
    "india":        "Asia/Kolkata",
    "mumbai":       "Asia/Kolkata",
    "delhi":        "Asia/Kolkata",
    "bangalore":    "Asia/Kolkata",
    "hyderabad":    "Asia/Kolkata",
    "chennai":      "Asia/Kolkata",
    "kolkata":      "Asia/Kolkata",
    "pune":         "Asia/Kolkata",

    # USA
    "new york":     "America/New_York",
    "boston":       "America/New_York",
    "washington":   "America/New_York",
    "chicago":      "America/Chicago",
    "dallas":       "America/Chicago",
    "houston":      "America/Chicago",
    "denver":       "America/Denver",
    "los angeles":  "America/Los_Angeles",
    "san francisco":"America/Los_Angeles",
    "seattle":      "America/Los_Angeles",
    "united states":"America/New_York",
    "usa":          "America/New_York",

    # UK
    "london":       "Europe/London",
    "united kingdom":"Europe/London",
    "uk":           "Europe/London",

    # Europe
    "paris":        "Europe/Paris",
    "france":       "Europe/Paris",
    "berlin":       "Europe/Berlin",
    "germany":      "Europe/Berlin",
    "amsterdam":    "Europe/Amsterdam",
    "netherlands":  "Europe/Amsterdam",
    "dubai":        "Asia/Dubai",
    "uae":          "Asia/Dubai",

    # Canada
    "toronto":      "America/Toronto",
    "vancouver":    "America/Vancouver",
    "canada":       "America/Toronto",

    # Australia
    "sydney":       "Australia/Sydney",
    "melbourne":    "Australia/Melbourne",
    "australia":    "Australia/Sydney",

    # Singapore / Malaysia
    "singapore":    "Asia/Singapore",
    "malaysia":     "Asia/Kuala_Lumpur",
    "kuala lumpur": "Asia/Kuala_Lumpur",

    # Pakistan
    "pakistan":     "Asia/Karachi",
    "karachi":      "Asia/Karachi",
    "lahore":       "Asia/Karachi",

    # Others
    "japan":        "Asia/Tokyo",
    "tokyo":        "Asia/Tokyo",
    "china":        "Asia/Shanghai",
    "beijing":      "Asia/Shanghai",
    "shanghai":     "Asia/Shanghai",
    "korea":        "Asia/Seoul",
    "seoul":        "Asia/Seoul",
    "brazil":       "America/Sao_Paulo",
    "nigeria":      "Africa/Lagos",
    "kenya":        "Africa/Nairobi",
    "egypt":        "Africa/Cairo",
    "turkey":       "Europe/Istanbul",
    "istanbul":     "Europe/Istanbul",
    "indonesia":    "Asia/Jakarta",
    "jakarta":      "Asia/Jakarta",
    "philippines":  "Asia/Manila",
    "manila":       "Asia/Manila",
    "vietnam":      "Asia/Ho_Chi_Minh",
    "thailand":     "Asia/Bangkok",
    "bangkok":      "Asia/Bangkok",
    "saudi arabia": "Asia/Riyadh",
    "riyadh":       "Asia/Riyadh",
    "iran":         "Asia/Tehran",
    "israel":       "Asia/Jerusalem",
    "south africa": "Africa/Johannesburg",
    "mexico":       "America/Mexico_City",
    "argentina":    "America/Argentina/Buenos_Aires",
}


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_scheduler_table():
    """Create auto-scheduler tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_wishes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                contact        TEXT    NOT NULL,
                timezone       TEXT    NOT NULL,
                location       TEXT,
                scheduled_utc  TEXT    NOT NULL,
                local_time     TEXT    NOT NULL,
                wish_text      TEXT,
                platform       TEXT    DEFAULT 'linkedin',
                status         TEXT    DEFAULT 'pending',
                sent_at        TEXT,
                dry_run        INTEGER DEFAULT 1,
                created_at     TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Auto-scheduler table ready.")


# ------------------------------------------------------------
# TIMEZONE DETECTION
# ------------------------------------------------------------

def detect_timezone(location: str) -> str:
    """
    Detect timezone from a location string.

    Args:
        location: Location string from LinkedIn profile
                  e.g. "Dhaka, Bangladesh" or "New York, USA"

    Returns:
        Timezone string e.g. "Asia/Dhaka" or "UTC" as fallback.
    """
    if not location:
        return FALLBACK_TZ

    location_lower = location.lower().strip()

    # Direct match
    for key, tz in LOCATION_TZ_MAP.items():
        if key in location_lower:
            logger.info("Timezone detected: %s -> %s", location, tz)
            return tz

    # Try to validate as direct timezone string
    try:
        ZoneInfo(location)
        return location
    except (ZoneInfoNotFoundError, KeyError):
        pass

    logger.warning("Could not detect timezone for '%s'. Using %s.", location, FALLBACK_TZ)
    return FALLBACK_TZ


def get_send_time_utc(
    contact_timezone: str,
    target_hour: int = TARGET_HOUR,
    target_minute: int = TARGET_MINUTE,
) -> datetime:
    """
    Calculate UTC datetime for sending at target_hour:target_minute
    in the contact's local timezone.

    Args:
        contact_timezone : Timezone string e.g. "Asia/Dhaka"
        target_hour      : Hour in contact's local time (default 9)
        target_minute    : Minute in contact's local time (default 0)

    Returns:
        UTC datetime to send the wish.
    """
    try:
        tz = ZoneInfo(contact_timezone)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo(FALLBACK_TZ)

    today = date.today()

    # Target time in contact's timezone
    local_target = datetime(
        today.year, today.month, today.day,
        target_hour, target_minute, 0,
        tzinfo=tz,
    )

    # Convert to UTC
    utc_time = local_target.astimezone(ZoneInfo("UTC"))

    # If already past, schedule for tomorrow
    now_utc = datetime.now(ZoneInfo("UTC"))
    if utc_time < now_utc:
        utc_time += timedelta(days=1)
        logger.info("Target time passed for today. Scheduling for tomorrow.")

    logger.info(
        "Send time: %s local (%s) = %s UTC",
        local_target.strftime("%H:%M"),
        contact_timezone,
        utc_time.strftime("%Y-%m-%d %H:%M UTC"),
    )
    return utc_time


def get_local_time_str(contact_timezone: str, utc_time: datetime) -> str:
    """Convert UTC time to local time string for display."""
    try:
        tz = ZoneInfo(contact_timezone)
        local_time = utc_time.astimezone(tz)
        return local_time.strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return utc_time.strftime("%Y-%m-%d %H:%M UTC")


# ------------------------------------------------------------
# SCHEDULING
# ------------------------------------------------------------

def schedule_wish_for_contact(
    contact: str,
    location: str,
    wish_text: str = "",
    platform: str = "linkedin",
    dry_run: bool = True,
) -> dict:
    """
    Schedule a birthday wish for a contact based on their timezone.

    Args:
        contact   : Contact name
        location  : Location from LinkedIn profile
        wish_text : The wish message to send
        platform  : Platform to send on (linkedin/whatsapp/slack)
        dry_run   : If True, log only

    Returns:
        Dict with schedule info.
    """
    tz_str    = detect_timezone(location)
    send_utc  = get_send_time_utc(tz_str)
    local_str = get_local_time_str(tz_str, send_utc)

    if not wish_text:
        first_name = contact.split()[0].capitalize()
        wish_text  = f"Happy Birthday {first_name}! Hope your day is amazing!"

    with sqlite3.connect(DB_FILE) as conn:
        # Avoid duplicate scheduling for same contact today
        existing = conn.execute("""
            SELECT id FROM scheduled_wishes
            WHERE LOWER(contact) = LOWER(?) AND DATE(created_at) = ?
        """, (contact, date.today().isoformat())).fetchone()

        if existing:
            logger.info("Already scheduled wish for %s today.", contact)
            return {"contact": contact, "status": "already_scheduled"}

        conn.execute("""
            INSERT INTO scheduled_wishes
            (contact, timezone, location, scheduled_utc, local_time,
             wish_text, platform, status, dry_run, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (contact, tz_str, location,
              send_utc.isoformat(), local_str,
              wish_text, platform, int(dry_run),
              datetime.now().isoformat()))
        conn.commit()

    logger.info(
        "Scheduled wish for %s | TZ: %s | Send at: %s (local) | %s (UTC)",
        contact, tz_str, local_str, send_utc.strftime("%H:%M UTC"),
    )

    return {
        "contact":       contact,
        "timezone":      tz_str,
        "location":      location,
        "send_utc":      send_utc.isoformat(),
        "local_time":    local_str,
        "status":        "scheduled",
    }


def get_pending_scheduled_wishes() -> list[dict]:
    """Get wishes that are due to be sent now (within 5 min window)."""
    if not DB_FILE.exists():
        return []

    now_utc   = datetime.now(ZoneInfo("UTC"))
    window    = timedelta(minutes=5)
    from_time = (now_utc - window).isoformat()
    to_time   = (now_utc + window).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT id, contact, timezone, wish_text, platform, scheduled_utc
            FROM   scheduled_wishes
            WHERE  status = 'pending'
              AND  scheduled_utc BETWEEN ? AND ?
        """, (from_time, to_time)).fetchall()

    return [
        {
            "id":            row[0],
            "contact":       row[1],
            "timezone":      row[2],
            "wish_text":     row[3],
            "platform":      row[4],
            "scheduled_utc": row[5],
        }
        for row in rows
    ]


def mark_wish_sent(wish_id: int):
    """Mark a scheduled wish as sent."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE scheduled_wishes
            SET status = 'sent', sent_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), wish_id))
        conn.commit()
    logger.info("Scheduled wish %d marked as sent.", wish_id)


def mark_wish_failed(wish_id: int):
    """Mark a scheduled wish as failed."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE scheduled_wishes
            SET status = 'failed'
            WHERE id = ?
        """, (wish_id,))
        conn.commit()


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_scheduler_report(scheduled: list[dict]) -> str:
    """Build a human-readable scheduler report."""
    if not scheduled:
        return "No wishes scheduled today."

    lines = [
        "Auto Timezone Scheduler Report",
        "-" * 55,
        f"  Total scheduled: {len(scheduled)}",
        f"  Target send time : {TARGET_HOUR:02d}:{TARGET_MINUTE:02d} (contact local time)",
        "-" * 55,
        f"  {'Contact':<25} {'Timezone':<20} {'Local Send Time'}",
        "  " + "-" * 53,
    ]

    for s in scheduled:
        lines.append(
            f"  {s['contact']:<25} {s['timezone']:<20} {s['local_time']}"
        )

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_auto_timezone_scheduler(
    birthday_contacts: list[dict] | None = None,
    dry_run: bool = True,
    target_hour: int = TARGET_HOUR,
) -> dict:
    """
    Main runner. Call from agent.py after birthday detection.

    Args:
        birthday_contacts : List of dicts with 'name' and 'location'
                            If None, reads from history table.
        dry_run           : If True, schedule but do not send
        target_hour       : Hour to send in contact's local time

    Returns:
        Dict with summary stats.
    """
    logger.info("=== Auto Timezone Scheduler === [DRY RUN: %s]", dry_run)

    if not birthday_contacts:
        birthday_contacts = _get_birthday_contacts_from_history()

    if not birthday_contacts:
        logger.info("No birthday contacts to schedule.")
        return {"total_scheduled": 0, "report": "No contacts to schedule."}

    scheduled = []

    for contact in birthday_contacts:
        name     = contact.get("name", "")
        location = contact.get("location", "")

        if not name:
            continue

        result = schedule_wish_for_contact(
            contact=name,
            location=location,
            wish_text=contact.get("wish_text", ""),
            platform=contact.get("platform", "linkedin"),
            dry_run=dry_run,
        )

        if result.get("status") == "scheduled":
            scheduled.append(result)

    report = build_scheduler_report(scheduled)
    logger.info("Auto-scheduler done: %d wishes scheduled.", len(scheduled))

    return {
        "total_scheduled": len(scheduled),
        "scheduled":       scheduled,
        "report":          report,
    }


async def run_pending_wishes(
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
    dry_run: bool = True,
) -> dict:
    """
    Send wishes that are due now based on scheduled UTC time.
    Run this every 5 minutes via scheduler for best accuracy.
    """
    pending = get_pending_scheduled_wishes()

    if not pending:
        logger.info("No pending scheduled wishes at this time.")
        return {"sent": 0, "failed": 0}

    logger.info("Found %d pending wishes to send now.", len(pending))

    sent   = 0
    failed = 0

    for wish in pending:
        if dry_run:
            logger.info(
                "[DRY RUN] Would send to %s (%s): %s",
                wish["contact"], wish["timezone"], wish["wish_text"][:50],
            )
            mark_wish_sent(wish["id"])
            sent += 1
            continue

        if llm and browser:
            from browser_use import Agent

            task = build_scheduler_agent_task(
                contact=wish["contact"],
                wish_text=wish["wish_text"],
                platform=wish["platform"],
                username=username,
                password=password,
                already_logged_in=already_logged_in,
            )

            try:
                agent = Agent(task=task, llm=llm, browser=browser)
                await agent.run()
                mark_wish_sent(wish["id"])
                sent += 1
                logger.info("Sent scheduled wish to %s.", wish["contact"])
            except Exception as e:
                logger.error("Failed to send wish to %s: %s", wish["contact"], e)
                mark_wish_failed(wish["id"])
                failed += 1

    return {"sent": sent, "failed": failed}


def _get_birthday_contacts_from_history() -> list[dict]:
    """Get today's birthday contacts from history table."""
    if not DB_FILE.exists():
        return []

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT DISTINCT contact FROM history
            WHERE task LIKE '%BirthdayDetection%'
              AND date = ?
              AND dry_run = 0
        """, (date.today().isoformat(),)).fetchall()

    return [{"name": row[0], "location": ""} for row in rows if row[0]]


# ------------------------------------------------------------
# AGENT TASK
# ------------------------------------------------------------

def build_scheduler_agent_task(
    contact: str,
    wish_text: str,
    platform: str = "linkedin",
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
) -> str:
    """Build agent task for sending a scheduled wish."""
    login = (
        "You are already logged in. Skip login."
        if already_logged_in
        else f"Log in with Email: {username} Password: {password}"
    )

    if platform == "linkedin":
        return f"""
Open browser. {login}

Send a birthday wish on LinkedIn:
  Contact  : {contact}
  Message  : {wish_text}

Steps:
  1. Go to https://www.linkedin.com/messaging/
  2. Search for {contact}
  3. Send the message
  4. Report: SENT: {contact} or FAILED: {contact}
"""
    elif platform == "whatsapp":
        return f"""
Open WhatsApp Web at https://web.whatsapp.com/

Send birthday wish to {contact}:
  Message: {wish_text}

Report: SENT: {contact} or FAILED: {contact}
"""
    return f"Send birthday wish to {contact}: {wish_text}"


def build_timezone_instructions(contact: str, location: str) -> str:
    """Build timezone scheduling instructions for the agent."""
    tz_str   = detect_timezone(location)
    send_utc = get_send_time_utc(tz_str)
    local    = get_local_time_str(tz_str, send_utc)

    return f"""
  AUTO TIMEZONE SCHEDULER:
  Contact  : {contact}
  Location : {location}
  Timezone : {tz_str}
  Send at  : {local} ({TARGET_HOUR:02d}:{TARGET_MINUTE:02d} local time)
  UTC time : {send_utc.strftime('%H:%M UTC')}

  Schedule this wish to be sent at the time above.
"""