"""
Contact Loader — Birthday Wishes Agent v10.0
=============================================
Contact loading, whitelist/blacklist filtering, cooldown checks,
session management, and browser configuration.

Extracted from agent.py god file for cleaner separation of concerns.

Author : Fahim (SadManFahIm)
Branch : feature/agent-decompose (→ 10.0)
"""

import json
import logging
import sqlite3
import time
from datetime import date
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

config = dotenv_values(".env")

USERNAME = config.get("USERNAME")
PASSWORD = config.get("PASSWORD")
GITHUB_URL = config.get("GITHUB_URL")

DRY_RUN = True

WHITELIST: list[str] = []
BLACKLIST: list[str] = []
COOLDOWN_DAYS = 30

# ──────────────────────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────────────────────

DB_FILE = Path("agent_history.db")


def init_db():
    """Create the core history table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT    NOT NULL,
                task        TEXT    NOT NULL,
                contact     TEXT    NOT NULL,
                message     TEXT    NOT NULL,
                dry_run     INTEGER NOT NULL,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("  Database ready: %s", DB_FILE)


def log_action(task: str, contact: str, message: str, dry_run: bool):
    """Log an agent action to the history table."""
    from datetime import datetime
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO history (date, task, contact, message, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date.today().isoformat(), task, contact, message,
             int(dry_run), datetime.now().isoformat()),
        )
        conn.commit()
    logger.info("  Logged: [%s] -> %s", task, contact)


def get_recent_contacts(task: str, days: int) -> set[str]:
    """Get contacts contacted within the last N days for a given task."""
    if not DB_FILE.exists():
        return set()
    cutoff = date.fromordinal(date.today().toordinal() - days).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT LOWER(contact) FROM history "
            "WHERE task = ? AND date >= ? AND dry_run = 0",
            (task, cutoff),
        ).fetchall()
    return {row[0] for row in rows}


# ──────────────────────────────────────────────────────────────
# Whitelist / Blacklist / Cooldown
# ──────────────────────────────────────────────────────────────


def is_allowed(name: str) -> bool:
    """Check if a contact passes whitelist/blacklist filters."""
    name_lower = name.lower()
    if BLACKLIST and name_lower in [b.lower() for b in BLACKLIST]:
        return False
    if WHITELIST and name_lower not in [w.lower() for w in WHITELIST]:
        return False
    return True


def filter_notice(task: str) -> str:
    """Build a filter notice string for agent prompts."""
    recent = get_recent_contacts(task, COOLDOWN_DAYS)
    cooldown_str = ", ".join(recent) if recent else "None"
    whitelist_str = ", ".join(WHITELIST) if WHITELIST else "Everyone (no whitelist set)"
    blacklist_str = ", ".join(BLACKLIST) if BLACKLIST else "None"
    return f"""
  CONTACT FILTERS (follow strictly):
   BLACKLIST - always skip: {blacklist_str}
   WHITELIST - only process: {whitelist_str}
    COOLDOWN  - skip (contacted in last {COOLDOWN_DAYS} days): {cooldown_str}
"""


# ──────────────────────────────────────────────────────────────
# Session Management
# ──────────────────────────────────────────────────────────────

SESSION_FILE = Path("linkedin_session.json")
SESSION_MAX_AGE_HOURS = 12


def session_is_valid() -> bool:
    """Check if the LinkedIn session cookie is still valid."""
    if not SESSION_FILE.exists():
        return False
    try:
        data = json.loads(SESSION_FILE.read_text())
        age_hours = (time.time() - data.get("saved_at", 0)) / 3600
        if age_hours > SESSION_MAX_AGE_HOURS:
            logger.info(" Session expired. Will re-login.")
            return False
        logger.info(" Valid session (%.1f h old).", age_hours)
        return True
    except Exception as e:
        logger.warning("  Session read error: %s", e)
        return False


def save_session_timestamp():
    """Persist the session timestamp to disk."""
    existing = {}
    if SESSION_FILE.exists():
        try:
            existing = json.loads(SESSION_FILE.read_text())
        except Exception:
            pass
    existing["saved_at"] = time.time()
    SESSION_FILE.write_text(json.dumps(existing, indent=2))
    logger.info(" Session saved.")


# ──────────────────────────────────────────────────────────────
# Browser
# ──────────────────────────────────────────────────────────────

BROWSER_PROFILE_DIR = str(Path.cwd() / "browser_profile")


def get_browser():
    """Create and return a Browser instance."""
    try:
        from browser_use import Browser, BrowserConfig
        return Browser(
            config=BrowserConfig(user_data_dir=BROWSER_PROFILE_DIR)
        )
    except ImportError:
        logger.warning("browser_use not installed — returning None")
        return None


# ──────────────────────────────────────────────────────────────
# AI Model Builder
# ──────────────────────────────────────────────────────────────

AI_MODEL = config.get("AI_MODEL", "gemini").strip().lower()

SUPPORTED_MODELS = {
    "gemini": "Google Gemini 2.5 Pro",
    "gpt-4o": "OpenAI GPT-4o",
}

if AI_MODEL not in SUPPORTED_MODELS:
    logger.warning(
        "  Unknown AI_MODEL '%s'. Falling back to 'gemini'. "
        "Supported: %s", AI_MODEL, list(SUPPORTED_MODELS.keys())
    )
    AI_MODEL = "gemini"


def build_llm():
    """Build and return the configured LLM instance."""
    if AI_MODEL == "gpt-4o":
        api_key = config.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                " OPENAI_API_KEY missing in .env - required for AI_MODEL=gpt-4o"
            )
        from langchain_openai import ChatOpenAI
        logger.info(" Using OpenAI API key.")
        return ChatOpenAI(model="gpt-4o", api_key=api_key)
    else:
        api_key = config.get("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                " GOOGLE_API_KEY missing in .env - required for AI_MODEL=gemini"
            )
        from langchain_google_genai import ChatGoogleGenerativeAI
        logger.info(" Using Google API key.")
        return ChatGoogleGenerativeAI(
            model="models/gemini-2.5-pro-preview-05-06",
            google_api_key=api_key,
        )


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    print("=" * 50)
    print("Contact Loader — Self-Test")
    print("=" * 50)

    # 1. Filter tests
    print("\n[1/4] Whitelist/Blacklist ...")
    assert is_allowed("Alice") is True
    BLACKLIST.append("Bob")
    assert is_allowed("Bob") is False
    BLACKLIST.clear()
    print("      ✅ Filters OK")

    # 2. Filter notice
    print("[2/4] Filter notice ...")
    init_db()  # ensure table exists
    notice = filter_notice("test-task")
    assert "BLACKLIST" in notice
    assert "COOLDOWN" in notice
    print("      ✅ Notice generated")

    # 3. Session
    print("[3/4] Session check ...")
    result = session_is_valid()
    print(f"      ✅ Session valid: {result}")

    # 4. DB init
    print("[4/4] DB init ...")
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    import os
    old_db = DB_FILE
    DB_FILE = Path(tmp.name)
    init_db()
    log_action("test", "Alice", "Hello", True)
    recent = get_recent_contacts("test", 7)
    DB_FILE = old_db
    os.unlink(tmp.name)
    print("      ✅ DB init + log + query OK")

    print("\n" + "=" * 50)
    print("✅ ALL CONTACT LOADER TESTS PASSED")
    print("=" * 50)
