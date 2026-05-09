"""
multi_account.py
━━━━━━━━━━━━━━━━
Multiple LinkedIn accounts একসাথে manage করে।
প্রতিটা account আলাদা browser profile-এ run হয়।

Tables:
  accounts — registered accounts + status
  account_history — per-account action log
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from browser_use import Browser, BrowserConfig

logger = logging.getLogger(__name__)

DB_FILE = Path("agent_history.db")


# ─────────────────────────────────────────────
# 1. DATA MODEL
# ─────────────────────────────────────────────

@dataclass
class LinkedInAccount:
    id:       int
    label:    str    # e.g. "personal", "work", "recruiter"
    username: str
    password: str
    enabled:  bool   = True
    priority: int    = 1    # lower = runs first

    @property
    def profile_dir(self) -> str:
        """Each account gets its own browser profile directory."""
        safe_label = self.label.replace(" ", "_").lower()
        return str(Path.cwd() / "browser_profiles" / safe_label)

    @property
    def session_file(self) -> Path:
        safe_label = self.label.replace(" ", "_").lower()
        return Path(f"session_{safe_label}.json")


# ─────────────────────────────────────────────
# 2. DB SETUP
# ─────────────────────────────────────────────

def init_accounts_table():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                label      TEXT    NOT NULL UNIQUE,
                username   TEXT    NOT NULL,
                password   TEXT    NOT NULL,
                enabled    INTEGER NOT NULL DEFAULT 1,
                priority   INTEGER NOT NULL DEFAULT 1,
                created_at TEXT    NOT NULL,
                last_run   TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS account_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                label      TEXT    NOT NULL,
                date       TEXT    NOT NULL,
                task       TEXT    NOT NULL,
                contact    TEXT    NOT NULL,
                message    TEXT,
                dry_run    INTEGER NOT NULL,
                created_at TEXT    NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(id)
            )
        """)
        conn.commit()
    logger.info("🗄️  accounts + account_history tables ready.")


def register_account(label: str, username: str, password: str,
                     enabled: bool = True, priority: int = 1):
    """Add or update an account."""
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO accounts (label, username, password, enabled, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(label) DO UPDATE SET
                username  = excluded.username,
                password  = excluded.password,
                enabled   = excluded.enabled,
                priority  = excluded.priority
        """, (label, username, password, int(enabled), priority, now))
        conn.commit()
    logger.info("✅ Account registered: [%s] %s", label, username)


def get_enabled_accounts() -> list[LinkedInAccount]:
    """Return all enabled accounts ordered by priority."""
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT id, label, username, password, enabled, priority
            FROM accounts
            WHERE enabled = 1
            ORDER BY priority ASC
        """).fetchall()
    return [
        LinkedInAccount(
            id=r[0], label=r[1], username=r[2],
            password=r[3], enabled=bool(r[4]), priority=r[5]
        )
        for r in rows
    ]


def log_account_action(account: LinkedInAccount, task: str,
                       contact: str, message: str, dry_run: bool):
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO account_history
                (account_id, label, date, task, contact, message, dry_run, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (account.id, account.label, date.today().isoformat(),
              task, contact, message, int(dry_run), now))
        conn.execute("""
            UPDATE accounts SET last_run = ? WHERE id = ?
        """, (now, account.id))
        conn.commit()


def get_account_stats() -> list[dict]:
    """Per-account stats for dashboard."""
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT a.label, a.username, a.enabled, a.last_run,
                   COUNT(h.id) as total_actions,
                   SUM(CASE WHEN h.dry_run = 0 THEN 1 ELSE 0 END) as real_actions
            FROM accounts a
            LEFT JOIN account_history h ON a.id = h.account_id
            GROUP BY a.id
            ORDER BY a.priority
        """).fetchall()
    return [
        {
            "label"       : r[0],
            "username"    : r[1],
            "enabled"     : bool(r[2]),
            "last_run"    : r[3],
            "total_actions": r[4],
            "real_actions" : r[5],
        }
        for r in rows
    ]


# ─────────────────────────────────────────────
# 3. SESSION MANAGEMENT (per account)
# ─────────────────────────────────────────────

SESSION_MAX_AGE_HOURS = 12


def account_session_is_valid(account: LinkedInAccount) -> bool:
    f = account.session_file
    if not f.exists():
        return False
    try:
        import time
        data = json.loads(f.read_text())
        age  = (time.time() - data.get("saved_at", 0)) / 3600
        if age > SESSION_MAX_AGE_HOURS:
            logger.info("⏰ Session expired for [%s].", account.label)
            return False
        logger.info("✅ Valid session for [%s] (%.1f h old).", account.label, age)
        return True
    except Exception as e:
        logger.warning("⚠️ Session read error [%s]: %s", account.label, e)
        return False


def save_account_session(account: LinkedInAccount):
    import time
    existing = {}
    if account.session_file.exists():
        try:
            existing = json.loads(account.session_file.read_text())
        except Exception:
            pass
    existing["saved_at"] = time.time()
    account.session_file.write_text(json.dumps(existing, indent=2))
    logger.info("💾 Session saved for [%s].", account.label)


# ─────────────────────────────────────────────
# 4. BROWSER FACTORY (per account)
# ─────────────────────────────────────────────

def make_browser_for_account(account: LinkedInAccount) -> Browser:
    """Each account gets its own isolated browser profile."""
    profile_path = Path(account.profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)
    return Browser(config=BrowserConfig(user_data_dir=str(profile_path)))


# ─────────────────────────────────────────────
# 5. TASK PROMPT BUILDERS (per account)
# ─────────────────────────────────────────────

def build_account_login_block(account: LinkedInAccount) -> str:
    if account_session_is_valid(account):
        return f"You are already logged into LinkedIn as {account.username}. Skip login."
    return (
        f"Go to https://linkedin.com and log in:\n"
        f"  Email   : {account.username}\n"
        f"  Password: {account.password}\n"
        "Handle MFA if prompted.\n"
    )


def build_account_birthday_detection_task(
    account: LinkedInAccount,
    dry_run: bool,
    wish_templates: list[str],
    filter_block: str,
) -> str:
    login       = build_account_login_block(account)
    dry         = _dry_run_notice(dry_run)
    templates_s = "\n".join(f'  {i+1}. "{t}"' for i, t in enumerate(wish_templates))
    return f"""
Open the browser. {login}
{dry}
{filter_block}

ACCOUNT: [{account.label}] ({account.username})

Go to https://www.linkedin.com/mynetwork/
Find contacts with birthdays TODAY.

For each birthday contact:
  a) Get FIRST NAME only.
  b) Apply filters.
  c) Choose ONE wish randomly and send (or log if DRY RUN):
{templates_s}

Stop after 20. TODAY only. No duplicates.
Summary: wished (names), skipped (count+reason).
"""


def build_account_reply_task(
    account: LinkedInAccount,
    dry_run: bool,
    reply_templates: list[str],
    wish_detection_rules: str,
    filter_block: str,
) -> str:
    login       = build_account_login_block(account)
    dry         = _dry_run_notice(dry_run)
    templates_s = "\n".join(f'  {i+1}. "{t}"' for i, t in enumerate(reply_templates))
    return f"""
Open the browser. {login}
{dry}
{filter_block}

ACCOUNT: [{account.label}] ({account.username})

Go to https://www.linkedin.com/messaging/
Check up to 15 UNREAD threads.

For each thread:
  STEP 1 — Get sender's FIRST NAME.
  STEP 2 — Apply filters.
  STEP 3 — Detect birthday wish: {wish_detection_rules}
  STEP 4 — If yes → pick ONE template, fill {{name}}, send:
{templates_s}
  If no → skip.

Summary: replied (names), skipped (count+reason).
"""


def _dry_run_notice(dry_run: bool) -> str:
    if dry_run:
        return """
⚠️  DRY RUN MODE IS ON ⚠️
Do NOT send any messages.
For each message you WOULD send, print:
  [DRY RUN] Would send to <name>: "<message>"
Then move on without clicking Send.
"""
    return ""


# ─────────────────────────────────────────────
# 6. MULTI-ACCOUNT RUNNER
# ─────────────────────────────────────────────

async def run_task_for_account(
    account: LinkedInAccount,
    task_str: str,
    task_name: str,
    llm,
    dry_run: bool,
    retries: int = 2,
) -> dict:
    """Run a single browser task for one account with retry."""
    from browser_use import Agent
    import asyncio

    browser = make_browser_for_account(account)
    last_error = ""

    for attempt in range(1, retries + 1):
        try:
            logger.info("🤖 [%s][%s] Attempt %d/%d",
                        account.label, task_name, attempt, retries)
            result = await Agent(task=task_str, llm=llm, browser=browser).run()
            save_account_session(account)
            log_account_action(account, task_name, "multiple", str(result)[:200], dry_run)
            logger.info("✅ [%s][%s] Done.", account.label, task_name)
            await browser.close()
            return {"account": account.label, "task": task_name,
                    "status": "success", "result": str(result)}
        except Exception as e:
            last_error = str(e)
            logger.warning("⚠️ [%s][%s] Attempt %d failed: %s",
                           account.label, task_name, attempt, e)
            if attempt < retries:
                await asyncio.sleep(5)

    try:
        await browser.close()
    except Exception:
        pass

    logger.error("💀 [%s][%s] All attempts failed.", account.label, task_name)
    return {"account": account.label, "task": task_name,
            "status": "failed", "error": last_error}


async def run_multi_account_birthday_detection(
    llm,
    dry_run: bool,
    wish_templates: list[str],
    filter_notice_fn,
    wish_detection_rules: str,
) -> list[dict]:
    """
    All enabled accounts-এর জন্য birthday detection চালায়।
    Parallel — সব accounts একসাথে।
    """
    import asyncio
    accounts = get_enabled_accounts()

    if not accounts:
        logger.warning("⚠️ No enabled accounts found. Register accounts first.")
        return []

    logger.info("👥 Running birthday detection for %d accounts...", len(accounts))

    coros = []
    for acc in accounts:
        task_str = build_account_birthday_detection_task(
            account        = acc,
            dry_run        = dry_run,
            wish_templates = wish_templates,
            filter_block   = filter_notice_fn(f"LinkedIn-BirthdayDetection-{acc.label}"),
        )
        coros.append(
            run_task_for_account(acc, task_str, "BirthdayDetection", llm, dry_run)
        )

    results = await asyncio.gather(*coros, return_exceptions=False)
    return list(results)


async def run_multi_account_reply(
    llm,
    dry_run: bool,
    reply_templates: list[str],
    wish_detection_rules: str,
    filter_notice_fn,
) -> list[dict]:
    """
    All enabled accounts-এর inbox check করে birthday wish replies পাঠায়।
    Parallel — সব accounts একসাথে।
    """
    import asyncio
    accounts = get_enabled_accounts()

    if not accounts:
        logger.warning("⚠️ No enabled accounts found.")
        return []

    logger.info("👥 Running reply task for %d accounts...", len(accounts))

    coros = []
    for acc in accounts:
        task_str = build_account_reply_task(
            account              = acc,
            dry_run              = dry_run,
            reply_templates      = reply_templates,
            wish_detection_rules = wish_detection_rules,
            filter_block         = filter_notice_fn(f"LinkedIn-Reply-{acc.label}"),
        )
        coros.append(
            run_task_for_account(acc, task_str, "ReplyToWishes", llm, dry_run)
        )

    results = await asyncio.gather(*coros, return_exceptions=False)
    return list(results)
