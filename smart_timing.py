"""
smart_timing.py
───────────────
Smart Timing module for Birthday Wishes Agent.

Instead of sending wishes at a fixed time (e.g. midnight),
this module detects the contact's timezone and schedules
the wish to be sent in the MORNING of their local time.

Features:
  - Detects timezone from LinkedIn profile location
  - Maps city/country to timezone
  - Calculates optimal send time (9:00 AM contact's local time)
  - Integrates with the scheduler

Dependencies:
    pip install pytz timezonefinder geopy

Usage:
    from smart_timing import get_optimal_send_time, build_timing_schedule

    send_time = get_optimal_send_time("Dhaka, Bangladesh")
    # Returns: datetime of 9:00 AM Bangladesh time in UTC
"""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# Default send time (hour in contact's local timezone)
OPTIMAL_HOUR = 9   # 9:00 AM


# ──────────────────────────────────────────────
# TIMEZONE MAPPING
# ──────────────────────────────────────────────
# Maps common city/country names to IANA timezone strings
TIMEZONE_MAP: dict[str, str] = {
    # South Asia
    "bangladesh":       "Asia/Dhaka",
    "dhaka":            "Asia/Dhaka",
    "india":            "Asia/Kolkata",
    "mumbai":           "Asia/Kolkata",
    "delhi":            "Asia/Kolkata",
    "bangalore":        "Asia/Kolkata",
    "pakistan":         "Asia/Karachi",
    "karachi":          "Asia/Karachi",
    "sri lanka":        "Asia/Colombo",
    "nepal":            "Asia/Kathmandu",

    # Southeast Asia
    "singapore":        "Asia/Singapore",
    "malaysia":         "Asia/Kuala_Lumpur",
    "kuala lumpur":     "Asia/Kuala_Lumpur",
    "indonesia":        "Asia/Jakarta",
    "jakarta":          "Asia/Jakarta",
    "philippines":      "Asia/Manila",
    "manila":           "Asia/Manila",
    "thailand":         "Asia/Bangkok",
    "bangkok":          "Asia/Bangkok",
    "vietnam":          "Asia/Ho_Chi_Minh",

    # East Asia
    "china":            "Asia/Shanghai",
    "shanghai":         "Asia/Shanghai",
    "beijing":          "Asia/Shanghai",
    "japan":            "Asia/Tokyo",
    "tokyo":            "Asia/Tokyo",
    "korea":            "Asia/Seoul",
    "seoul":            "Asia/Seoul",

    # Middle East
    "uae":              "Asia/Dubai",
    "dubai":            "Asia/Dubai",
    "saudi arabia":     "Asia/Riyadh",
    "riyadh":           "Asia/Riyadh",
    "qatar":            "Asia/Qatar",
    "doha":             "Asia/Qatar",
    "turkey":           "Europe/Istanbul",
    "istanbul":         "Europe/Istanbul",

    # Europe
    "uk":               "Europe/London",
    "london":           "Europe/London",
    "germany":          "Europe/Berlin",
    "berlin":           "Europe/Berlin",
    "france":           "Europe/Paris",
    "paris":            "Europe/Paris",
    "netherlands":      "Europe/Amsterdam",
    "spain":            "Europe/Madrid",
    "italy":            "Europe/Rome",
    "sweden":           "Europe/Stockholm",

    # North America
    "usa":              "America/New_York",
    "new york":         "America/New_York",
    "los angeles":      "America/Los_Angeles",
    "chicago":          "America/Chicago",
    "canada":           "America/Toronto",
    "toronto":          "America/Toronto",
    "vancouver":        "America/Vancouver",

    # Others
    "australia":        "Australia/Sydney",
    "sydney":           "Australia/Sydney",
    "brazil":           "America/Sao_Paulo",
    "nigeria":          "Africa/Lagos",
    "south africa":     "Africa/Johannesburg",
    "egypt":            "Africa/Cairo",
}


# ──────────────────────────────────────────────
# TIMEZONE DETECTION
# ──────────────────────────────────────────────
def detect_timezone(location: str) -> str:
    """
    Detect IANA timezone from a location string.

    Args:
        location: e.g. "Dhaka, Bangladesh", "London, UK", "New York, USA"

    Returns:
        IANA timezone string, e.g. "Asia/Dhaka"
        Falls back to "UTC" if not found.
    """
    if not location:
        return "UTC"

    location_lower = location.lower()

    # Check each key in the map
    for key, tz in TIMEZONE_MAP.items():
        if key in location_lower:
            logger.info("🌍 Detected timezone: %s → %s", location, tz)
            return tz

    logger.warning("⚠️  Unknown location '%s', defaulting to UTC", location)
    return "UTC"


# ──────────────────────────────────────────────
# OPTIMAL SEND TIME CALCULATOR
# ──────────────────────────────────────────────
def get_optimal_send_time(location: str) -> datetime:
    """
    Calculate the optimal time to send a birthday wish.
    Targets 9:00 AM in the contact's local timezone.

    Args:
        location: Contact's location string from LinkedIn profile

    Returns:
        datetime object in UTC representing 9:00 AM contact's local time today.
    """
    tz_name = detect_timezone(location)

    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("⚠️  Invalid timezone %s, using UTC", tz_name)
        tz = ZoneInfo("UTC")

    # 9:00 AM in contact's timezone today
    today = datetime.now(tz).date()
    local_9am = datetime(
        today.year, today.month, today.day,
        OPTIMAL_HOUR, 0, 0,
        tzinfo=tz,
    )

    # Convert to UTC
    utc_time = local_9am.astimezone(ZoneInfo("UTC"))
    logger.info(
        "⏰ Optimal send time for %s: %s local → %s UTC",
        location, local_9am.strftime("%H:%M"), utc_time.strftime("%H:%M UTC"),
    )
    return utc_time


def should_send_now(location: str, window_minutes: int = 30) -> bool:
    """
    Check if now is within the optimal send window for a contact.

    Args:
        location       : Contact's location
        window_minutes : How many minutes around 9 AM to consider valid

    Returns:
        True if current time is within the send window.
    """
    optimal = get_optimal_send_time(location)
    now_utc = datetime.now(ZoneInfo("UTC"))
    diff    = abs((now_utc - optimal).total_seconds() / 60)

    if diff <= window_minutes:
        logger.info("✅ Now is within send window for %s (diff: %.1f min)", location, diff)
        return True

    logger.info(
        "⏳ Not yet time to send for %s. Optimal: %s, Now: %s (diff: %.1f min)",
        location,
        optimal.strftime("%H:%M UTC"),
        now_utc.strftime("%H:%M UTC"),
        diff,
    )
    return False


# ──────────────────────────────────────────────
# TIMING NOTICE (for browser agent tasks)
# ──────────────────────────────────────────────
def build_timing_instructions(contacts_with_locations: list[dict]) -> str:
    """
    Build timing instructions for the agent based on contact locations.

    Args:
        contacts_with_locations: List of dicts with "name" and "location"

    Returns:
        Instruction string for the browser agent.
    """
    if not contacts_with_locations:
        return ""

    timing_lines = []
    for contact in contacts_with_locations:
        name     = contact.get("name", "Unknown")
        location = contact.get("location", "")
        tz_name  = detect_timezone(location)
        send_ok  = should_send_now(location)
        status   = "✅ Send now" if send_ok else "⏳ Wait — not morning yet in their timezone"

        timing_lines.append(
            f"  - {name} ({location or 'Unknown location'}) "
            f"[{tz_name}] → {status}"
        )

    timing_str = "\n".join(timing_lines)

    return f"""
  SMART TIMING RULES:
  Only send wishes to contacts for whom it is currently MORNING
  (around 9:00 AM in their local timezone).
  This ensures they receive the wish at a pleasant time of day.

  Contact timing status:
{timing_str}

  For contacts marked "⏳ Wait" → skip them NOW.
  They will be retried in the next scheduler run.
"""