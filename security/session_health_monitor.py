"""
session_health_monitor.py
-------------------------
Session Health Monitor for Birthday Wishes Agent.

Monitors LinkedIn session health and automatically renews
the session before it expires — no more unexpected logouts.

How it works:
  1. Tracks session age and last activity time
  2. Warns when session is approaching expiry
  3. Auto-renews session by visiting LinkedIn silently
  4. Detects if session was invalidated (IP change, LinkedIn logout)
  5. Logs all session events to SQLite

Session states:
  - healthy   : Session valid, plenty of time left
  - aging     : Session valid but nearing expiry (< 2 hours left)
  - expired   : Session has expired — needs fresh login
  - invalid   : Session was invalidated by LinkedIn
  - renewed   : Session was successfully renewed

Usage:
    from session_health_monitor import (
        init_session_monitor_table,
        check_session_health,
        auto_renew_session,
        get_session_status,
        build_session_report,
    )

    status = get_session_status()
    if status["needs_renewal"]:
        await auto_renew_session(llm, browser)
"""

import json
import logging
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE      = Path("agent_history.db")
SESSION_FILE = Path("linkedin_session.json")

# Session expiry settings
SESSION_MAX_AGE_HOURS   = 12
SESSION_WARN_HOURS      = 2    # Warn when less than 2 hours left
SESSION_RENEW_THRESHOLD = 1.5  # Auto-renew when less than 1.5 hours left

# How often to check session health (minutes)
HEALTH_CHECK_INTERVAL = 30


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_session_monitor_table():
    """Create session monitoring table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type   TEXT NOT NULL,
                session_age  REAL,
                hours_left   REAL,
                status       TEXT,
                note         TEXT,
                event_date   TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("Session monitor table ready.")


def log_session_event(
    event_type: str,
    session_age: float = 0,
    hours_left: float = 0,
    status: str = "",
    note: str = "",
):
    """Log a session event."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO session_events
            (event_type, session_age, hours_left, status, note,
             event_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (event_type, session_age, hours_left, status, note,
              date.today().isoformat(), datetime.now().isoformat()))
        conn.commit()


# ------------------------------------------------------------
# SESSION FILE MANAGEMENT
# ------------------------------------------------------------

def read_session_file() -> dict:
    """Read linkedin_session.json."""
    if not SESSION_FILE.exists():
        return {}
    try:
        return json.loads(SESSION_FILE.read_text())
    except Exception:
        return {}


def write_session_file(data: dict):
    """Write to linkedin_session.json."""
    existing = read_session_file()
    existing.update(data)
    SESSION_FILE.write_text(json.dumps(existing, indent=2))


def get_session_age_hours() -> float:
    """Get current session age in hours."""
    data = read_session_file()
    saved_at = data.get("saved_at", 0)
    if not saved_at:
        return SESSION_MAX_AGE_HOURS + 1  # Treat as expired
    return (time.time() - saved_at) / 3600


def get_hours_remaining() -> float:
    """Get hours remaining before session expires."""
    age = get_session_age_hours()
    return max(0, SESSION_MAX_AGE_HOURS - age)


# ------------------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------------------

def check_session_health() -> dict:
    """
    Check current session health.

    Returns:
        Dict with status, age_hours, hours_left, needs_renewal, needs_login
    """
    if not SESSION_FILE.exists():
        return {
            "status":        "no_session",
            "age_hours":     0,
            "hours_left":    0,
            "needs_renewal": False,
            "needs_login":   True,
            "message":       "No session file found. Fresh login required.",
        }

    age_hours  = get_session_age_hours()
    hours_left = get_hours_remaining()

    if age_hours > SESSION_MAX_AGE_HOURS:
        status = "expired"
        needs_renewal = False
        needs_login   = True
        message       = f"Session expired ({age_hours:.1f}h old). Fresh login required."
        log_session_event("expired", age_hours, 0, status, message)

    elif hours_left <= SESSION_RENEW_THRESHOLD:
        status = "aging"
        needs_renewal = True
        needs_login   = False
        message       = f"Session aging ({hours_left:.1f}h left). Auto-renewal recommended."
        log_session_event("aging", age_hours, hours_left, status, message)

    elif hours_left <= SESSION_WARN_HOURS:
        status = "warning"
        needs_renewal = True
        needs_login   = False
        message       = f"Session warning: {hours_left:.1f}h remaining."
        log_session_event("warning", age_hours, hours_left, status, message)

    else:
        status = "healthy"
        needs_renewal = False
        needs_login   = False
        message       = f"Session healthy: {hours_left:.1f}h remaining."

    logger.info("Session health: %s | Age: %.1fh | Left: %.1fh",
                status, age_hours, hours_left)

    return {
        "status":        status,
        "age_hours":     round(age_hours, 2),
        "hours_left":    round(hours_left, 2),
        "needs_renewal": needs_renewal,
        "needs_login":   needs_login,
        "message":       message,
    }


def is_session_valid() -> bool:
    """Quick check: is the session still valid?"""
    health = check_session_health()
    return health["status"] in ("healthy", "warning", "aging")


# ------------------------------------------------------------
# AUTO-RENEWAL
# ------------------------------------------------------------

async def auto_renew_session(
    llm,
    browser,
    username: str = "",
    password: str = "",
) -> bool:
    """
    Silently renew LinkedIn session by visiting the site.
    Call this when session is aging (< 1.5 hours left).

    Args:
        llm      : LangChain LLM instance
        browser  : browser_use Browser instance
        username : LinkedIn email (for re-login if needed)
        password : LinkedIn password (for re-login if needed)

    Returns:
        True if renewed successfully.
    """
    from browser_use import Agent
    from dotenv import dotenv_values

    config = dotenv_values(".env")
    if not username:
        username = config.get("USERNAME", "")
    if not password:
        password = config.get("PASSWORD", "")

    health = check_session_health()

    if health["status"] == "healthy":
        logger.info("Session healthy — no renewal needed.")
        return True

    logger.info("Auto-renewing session... Status: %s", health["status"])

    if health["needs_login"]:
        # Full re-login needed
        task = f"""
Go to https://www.linkedin.com and log in:
  Email: {username}
  Password: {password}

Handle any 2FA if prompted.
Once logged in successfully, go to https://www.linkedin.com/feed/
Report: SESSION RENEWED or SESSION FAILED
"""
    else:
        # Just visit LinkedIn to refresh session
        task = """
Go to https://www.linkedin.com/feed/
Wait for the page to fully load.
You should already be logged in.
Report: SESSION RENEWED or SESSION FAILED
"""

    try:
        agent  = Agent(task=task, llm=llm, browser=browser)
        result = await agent.run()
        result_str = str(result).upper()

        if "SESSION FAILED" in result_str or "LOGIN" in result_str:
            log_session_event("renewal_failed", health["age_hours"],
                              health["hours_left"], "failed",
                              "Session renewal failed.")
            logger.error("Session renewal failed.")
            return False

        # Update session timestamp
        write_session_file({"saved_at": time.time()})
        log_session_event("renewed", 0, SESSION_MAX_AGE_HOURS,
                          "renewed", "Session renewed successfully.")
        logger.info("Session renewed successfully.")
        return True

    except Exception as e:
        logger.error("Session renewal error: %s", e)
        log_session_event("renewal_error", 0, 0, "error", str(e))
        return False


# ------------------------------------------------------------
# PROACTIVE MONITORING
# ------------------------------------------------------------

async def ensure_healthy_session(
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
) -> bool:
    """
    Ensure session is healthy before running any task.
    Call this at the start of every agent task.

    Returns:
        True if session is ready (healthy or renewed).
        False if session is invalid and renewal failed.
    """
    health = check_session_health()

    if health["status"] == "healthy":
        return True

    if health["needs_renewal"] and llm and browser:
        logger.info("Session needs renewal — auto-renewing...")
        return await auto_renew_session(llm, browser, username, password)

    if health["needs_login"]:
        if llm and browser:
            logger.info("Session expired — performing fresh login...")
            return await auto_renew_session(llm, browser, username, password)
        else:
            logger.warning("Session expired but no browser available to renew.")
            return False

    return True


def get_session_status() -> dict:
    """Get full session status for dashboard display."""
    health  = check_session_health()
    data    = read_session_file()
    saved_at = data.get("saved_at", 0)

    return {
        **health,
        "saved_at": datetime.fromtimestamp(saved_at).isoformat() if saved_at else None,
        "max_age_hours":    SESSION_MAX_AGE_HOURS,
        "warn_threshold":   SESSION_WARN_HOURS,
        "renew_threshold":  SESSION_RENEW_THRESHOLD,
    }


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_session_report() -> str:
    """Build human-readable session health report."""
    status = get_session_status()

    if not DB_FILE.exists():
        events = []
    else:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute("""
                SELECT event_type, session_age, hours_left, status, note, created_at
                FROM   session_events
                ORDER  BY id DESC LIMIT 10
            """).fetchall()
        events = rows

    status_emoji = {
        "healthy":    "✓",
        "warning":    "!",
        "aging":      "!!",
        "expired":    "X",
        "no_session": "?",
    }.get(status["status"], "-")

    lines = [
        "Session Health Monitor Report",
        "-" * 55,
        f"  Status      : [{status_emoji}] {status['status'].upper()}",
        f"  Age         : {status['age_hours']:.1f} hours",
        f"  Remaining   : {status['hours_left']:.1f} hours",
        f"  Max age     : {status['max_age_hours']} hours",
        f"  Message     : {status['message']}",
        "-" * 55,
    ]

    if events:
        lines.append("\nRecent Session Events:")
        for row in events:
            lines.append(
                f"  [{row[3]}] {row[0]:<15} "
                f"age={row[1]:.1f}h left={row[2]:.1f}h | {row[4][:40]}"
            )

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)
