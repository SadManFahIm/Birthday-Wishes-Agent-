"""
best_time_connect.py
────────────────────
Best Time to Connect module for Birthday Wishes Agent.

Analyzes LinkedIn activity patterns to determine when a contact
is most active and schedules messages to be sent at that time.

How it works:
  1. Scans the contact's recent LinkedIn posts and activity
  2. Notes the timestamps of their posts, comments, and likes
  3. Identifies peak activity hours and days
  4. Schedules the wish/message for their most active time

Activity Signals:
  - Post publishing time
  - Comment timestamps
  - Like/reaction timestamps
  - Profile update times

Usage:
    from best_time_connect import (
        analyze_activity_pattern,
        get_best_send_time,
        build_activity_task
    )
"""

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger  = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_activity_table():
    """Create the contact activity pattern table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_activity (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact       TEXT    NOT NULL,
                active_hours  TEXT,
                active_days   TEXT,
                best_hour     INTEGER,
                best_day      TEXT,
                timezone      TEXT,
                confidence    REAL    DEFAULT 0.0,
                last_analyzed TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                UNIQUE(contact)
            )
        """)
        conn.commit()
    logger.info("🗄️  Contact activity table ready.")


def save_activity_pattern(
    contact: str,
    active_hours: list[int],
    active_days: list[str],
    best_hour: int,
    best_day: str,
    timezone: str = "UTC",
    confidence: float = 0.0,
):
    """Save a contact's activity pattern to the database."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO contact_activity
                (contact, active_hours, active_days, best_hour,
                 best_day, timezone, confidence, last_analyzed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact) DO UPDATE SET
                active_hours  = excluded.active_hours,
                active_days   = excluded.active_days,
                best_hour     = excluded.best_hour,
                best_day      = excluded.best_day,
                timezone      = excluded.timezone,
                confidence    = excluded.confidence,
                last_analyzed = excluded.last_analyzed
        """, (
            contact,
            json.dumps(active_hours),
            json.dumps(active_days),
            best_hour,
            best_day,
            timezone,
            confidence,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
        ))
        conn.commit()
    logger.info("🗄️  Activity pattern saved for %s", contact)


def get_activity_pattern(contact: str) -> dict | None:
    """Retrieve stored activity pattern for a contact."""
    if not DB_FILE.exists():
        return None
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT active_hours, active_days, best_hour, best_day, "
            "timezone, confidence, last_analyzed "
            "FROM contact_activity WHERE LOWER(contact) = LOWER(?)",
            (contact,),
        ).fetchone()
    if not row:
        return None
    return {
        "active_hours":  json.loads(row[0]) if row[0] else [],
        "active_days":   json.loads(row[1]) if row[1] else [],
        "best_hour":     row[2],
        "best_day":      row[3],
        "timezone":      row[4] or "UTC",
        "confidence":    row[5] or 0.0,
        "last_analyzed": row[6],
    }


def is_pattern_fresh(contact: str, max_age_days: int = 7) -> bool:
    """Check if the stored pattern is recent enough."""
    pattern = get_activity_pattern(contact)
    if not pattern:
        return False
    try:
        analyzed = datetime.fromisoformat(pattern["last_analyzed"])
        age_days = (datetime.now() - analyzed).days
        return age_days <= max_age_days
    except Exception:
        return False


# ──────────────────────────────────────────────
# ACTIVITY ANALYSIS
# ──────────────────────────────────────────────
def analyze_activity_pattern(raw_timestamps: list[str]) -> dict:
    """
    Analyze a list of activity timestamps to find peak hours and days.

    Args:
        raw_timestamps : List of ISO datetime strings

    Returns:
        Dict with active_hours, active_days, best_hour, best_day, confidence
    """
    if not raw_timestamps:
        return {
            "active_hours": [9, 10, 11, 17, 18, 19],
            "active_days":  ["Monday", "Tuesday", "Wednesday",
                             "Thursday", "Friday"],
            "best_hour":    9,
            "best_day":     "Tuesday",
            "confidence":   0.0,
        }

    hour_counts = {}
    day_counts  = {}

    for ts in raw_timestamps:
        try:
            dt   = datetime.fromisoformat(ts)
            hour = dt.hour
            day  = dt.strftime("%A")
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
            day_counts[day]   = day_counts.get(day, 0) + 1
        except Exception:
            continue

    if not hour_counts:
        return {
            "active_hours": [9, 10, 17, 18],
            "active_days":  ["Monday", "Tuesday", "Wednesday"],
            "best_hour":    9,
            "best_day":     "Tuesday",
            "confidence":   0.0,
        }

    # Sort by activity count
    sorted_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)
    sorted_days  = sorted(day_counts.items(),  key=lambda x: x[1], reverse=True)

    best_hour    = sorted_hours[0][0] if sorted_hours else 9
    best_day     = sorted_days[0][0]  if sorted_days  else "Tuesday"
    active_hours = [h for h, _ in sorted_hours[:5]]
    active_days  = [d for d, _ in sorted_days[:3]]

    # Confidence based on data points
    confidence = min(1.0, len(raw_timestamps) / 20)

    logger.info(
        "📊 Activity pattern: Best time is %s at %d:00 (confidence: %.0f%%)",
        best_day, best_hour, confidence * 100,
    )

    return {
        "active_hours": active_hours,
        "active_days":  active_days,
        "best_hour":    best_hour,
        "best_day":     best_day,
        "confidence":   confidence,
    }


# ──────────────────────────────────────────────
# GET BEST SEND TIME
# ──────────────────────────────────────────────
def get_best_send_time(contact: str) -> dict:
    """
    Get the best time to send a message to a contact.

    Returns:
        Dict with best_hour, best_day, next_window, confidence
    """
    pattern = get_activity_pattern(contact)

    if not pattern or pattern["confidence"] < 0.3:
        # Default to morning if no data
        logger.info(
            "📅 No activity pattern for %s — defaulting to 9 AM Tuesday", contact
        )
        return {
            "best_hour":   9,
            "best_day":    "Tuesday",
            "next_window": _get_next_occurrence("Tuesday", 9),
            "confidence":  0.0,
            "note":        "Default timing — no activity data available yet.",
        }

    best_hour = pattern["best_hour"]
    best_day  = pattern["best_day"]

    return {
        "best_hour":   best_hour,
        "best_day":    best_day,
        "next_window": _get_next_occurrence(best_day, best_hour),
        "confidence":  pattern["confidence"],
        "note": (
            f"Based on activity analysis — "
            f"{contact} is most active on {best_day}s around {best_hour}:00."
        ),
    }


def _get_next_occurrence(day_name: str, hour: int) -> str:
    """Get the next occurrence of a specific day and hour."""
    days = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]
    today     = datetime.now()
    today_idx = today.weekday()

    try:
        target_idx = days.index(day_name)
    except ValueError:
        target_idx = 1  # Default Tuesday

    days_ahead = (target_idx - today_idx) % 7
    if days_ahead == 0 and today.hour >= hour:
        days_ahead = 7

    target_date = today + timedelta(days=days_ahead)
    target_dt   = target_date.replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return target_dt.strftime("%A, %B %d at %I:%M %p")


# ──────────────────────────────────────────────
# BROWSER TASK BUILDER
# ──────────────────────────────────────────────
def build_activity_scan_task(
    contact: str,
    profile_url: str,
    already_logged_in: bool,
    username: str = "",
    password: str = "",
) -> str:
    """
    Build a browser agent task to scan a contact's LinkedIn
    activity and extract timestamps.
    """
    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {username}\n"
            f"  Password: {password}\n"
        )
    )

    profile_instruction = (
        f"Go to this profile: {profile_url}"
        if profile_url
        else f"Search for '{contact}' on LinkedIn and open their profile."
    )

    return f"""
  Open the browser.
  {login_instructions}

  GOAL: Analyze {contact}'s LinkedIn activity to find their most
  active times — so we can send messages when they are online.

  STEP 1 — {profile_instruction}

  STEP 2 — Scroll through their Activity section.
    Click "Show all activity" if available.
    Look at the timestamps of their:
    - Posts (when did they publish?)
    - Comments (when did they comment?)
    - Likes/reactions (when did they react?)
    - Profile updates

  STEP 3 — Collect up to 20 recent activity timestamps.
    Note the date AND time of each activity.

  STEP 4 — Return the data as JSON:
  {{
    "contact": "{contact}",
    "timestamps": [
      "2025-03-15T09:30:00",
      "2025-03-12T18:45:00",
      "2025-03-10T08:15:00"
    ],
    "timezone_hint": "appears to be in UTC+6 based on posting times",
    "notes": "Most posts around 9-10 AM and 6-8 PM"
  }}

  If no activity found → return {{"contact": "{contact}", "timestamps": [], "notes": "No activity found"}}
  Return ONLY the JSON. No extra text.
"""


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_best_time_analysis(
    llm,
    browser,
    contacts: list[dict],
    already_logged_in: bool,
    username: str = "",
    password: str = "",
) -> list[dict]:
    """
    Analyze activity patterns for a list of contacts.

    Args:
        llm               : LangChain LLM instance
        browser           : browser_use Browser instance
        contacts          : List of dicts with "name" and "profile_url"
        already_logged_in : Whether session is valid
        username          : LinkedIn email
        password          : LinkedIn password

    Returns:
        List of dicts with contact name and best send time.
    """
    import json
    from browser_use import Agent

    results = []

    for contact_info in contacts:
        name        = contact_info.get("name", "")
        profile_url = contact_info.get("profile_url", "")

        # Skip if fresh pattern exists
        if is_pattern_fresh(name):
            logger.info("⏭️  Fresh pattern exists for %s — skipping scan.", name)
            best_time = get_best_send_time(name)
            results.append({"contact": name, **best_time})
            continue

        logger.info("🔍 Scanning activity for %s...", name)

        task  = build_activity_scan_task(
            contact=name,
            profile_url=profile_url,
            already_logged_in=already_logged_in,
            username=username,
            password=password,
        )
        agent  = Agent(task=task, llm=llm, browser=browser)
        result = await agent.run()

        # Parse timestamps from result
        try:
            result_str = str(result)
            start      = result_str.find("{")
            end        = result_str.rfind("}") + 1
            if start != -1 and end > start:
                data       = json.loads(result_str[start:end])
                timestamps = data.get("timestamps", [])
                timezone   = data.get("timezone_hint", "UTC")

                pattern = analyze_activity_pattern(timestamps)
                save_activity_pattern(
                    contact=name,
                    active_hours=pattern["active_hours"],
                    active_days=pattern["active_days"],
                    best_hour=pattern["best_hour"],
                    best_day=pattern["best_day"],
                    timezone=timezone,
                    confidence=pattern["confidence"],
                )

                best_time = get_best_send_time(name)
                results.append({"contact": name, **best_time})
        except Exception as e:
            logger.warning("⚠️  Could not parse activity for %s: %s", name, e)
            results.append({
                "contact":   name,
                "best_hour": 9,
                "best_day":  "Tuesday",
                "note":      "Could not analyze — using default timing.",
            })

    return results


# ──────────────────────────────────────────────
# TIMING NOTICE FOR AGENT
# ──────────────────────────────────────────────
def build_timing_notice(contact: str) -> str:
    """
    Build a timing notice for the browser agent
    based on the contact's activity pattern.
    """
    best_time = get_best_send_time(contact)
    confidence = best_time.get("confidence", 0)

    if confidence < 0.3:
        return f"""
  BEST TIME TO CONNECT ({contact}):
  No activity data available yet — sending at default morning time.
"""

    return f"""
  BEST TIME TO CONNECT ({contact}):
  Based on their LinkedIn activity pattern:
  - Best day  : {best_time['best_day']}
  - Best hour : {best_time['best_hour']}:00
  - Next window: {best_time['next_window']}
  - Confidence : {int(confidence * 100)}%

  If sending now is not within 2 hours of their peak time,
  consider scheduling for their next active window instead.
"""