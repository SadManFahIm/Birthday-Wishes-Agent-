import asyncio
import json
import logging
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from browser_use import Agent, Browser, BrowserConfig
from dotenv import dotenv_values
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from notifications import send_summary

# ──────────────────────────────────────────────
# 1. LOGGING SETUP
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 2. CONFIG & CREDENTIALS
# ──────────────────────────────────────────────
config = dotenv_values(".env")

USERNAME   = config.get("USERNAME")
PASSWORD   = config.get("PASSWORD")
GITHUB_URL = config.get("GITHUB_URL")

# Set to True  → simulate only, no messages sent
# Set to False → actually send messages
DRY_RUN = True

# Daily schedule time (24h format)
SCHEDULE_HOUR   = 9
SCHEDULE_MINUTE = 0

# ── WHITELIST / BLACKLIST ─────────────────────
# WHITELIST: if not empty, ONLY these contacts will be wished/replied to.
# BLACKLIST: these contacts will always be skipped.
# Use full names as they appear on LinkedIn (case-insensitive).
WHITELIST: list[str] = []   # e.g. ["Rahul Ahmed", "Priya Sharma"]
BLACKLIST: list[str] = []   # e.g. ["John Doe", "Spam Account"]

# ── REPLY COOLDOWN ────────────────────────────
# Minimum days before the agent will reply/wish the same contact again.
COOLDOWN_DAYS = 30

if not USERNAME or not PASSWORD:
    raise EnvironmentError(
        "❌ USERNAME or PASSWORD is missing in .env file."
    )


# ──────────────────────────────────────────────
# 3. SQLITE LOGGING
# ──────────────────────────────────────────────
DB_FILE = Path("agent_history.db")


def init_db():
    """Create the history table if it doesn't exist."""
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
    logger.info("🗄️  Database ready: %s", DB_FILE)


def log_action(task: str, contact: str, message: str, dry_run: bool):
    """Save a sent wish/reply to the SQLite history."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO history (date, task, contact, message, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                date.today().isoformat(),
                task,
                contact,
                message,
                int(dry_run),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    logger.info("🗄️  Logged action: [%s] → %s", task, contact)


def get_recent_contacts(task: str, days: int) -> set[str]:
    """
    Return a set of contact names that were already
    wished/replied to within the last `days` days.
    """
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


# ──────────────────────────────────────────────
# 4. WHITELIST / BLACKLIST HELPERS
# ──────────────────────────────────────────────
def is_allowed(name: str) -> bool:
    """Return True if this contact should be processed."""
    name_lower = name.lower()

    if BLACKLIST and name_lower in [b.lower() for b in BLACKLIST]:
        logger.info("🚫 Blacklisted contact skipped: %s", name)
        return False

    if WHITELIST and name_lower not in [w.lower() for w in WHITELIST]:
        logger.info("⏭️  Not in whitelist, skipping: %s", name)
        return False

    return True


def is_on_cooldown(name: str, task: str) -> bool:
    """Return True if this contact was already contacted within COOLDOWN_DAYS."""
    recent = get_recent_contacts(task, COOLDOWN_DAYS)
    if name.lower() in recent:
        logger.info("❄️  Cooldown active for: %s (task: %s)", name, task)
        return True
    return False


# ──────────────────────────────────────────────
# 5. SESSION / COOKIE MANAGEMENT
# ──────────────────────────────────────────────
SESSION_FILE = Path("linkedin_session.json")
SESSION_MAX_AGE_HOURS = 12


def session_is_valid() -> bool:
    if not SESSION_FILE.exists():
        return False
    try:
        data = json.loads(SESSION_FILE.read_text())
        saved_at = data.get("saved_at", 0)
        age_hours = (time.time() - saved_at) / 3600
        if age_hours > SESSION_MAX_AGE_HOURS:
            logger.info("⏰ Session expired (%.1f h old). Will re-login.", age_hours)
            return False
        logger.info("✅ Valid session found (%.1f h old). Skipping login.", age_hours)
        return True
    except Exception as e:
        logger.warning("⚠️  Could not read session file: %s", e)
        return False


def save_session_timestamp():
    existing = {}
    if SESSION_FILE.exists():
        try:
            existing = json.loads(SESSION_FILE.read_text())
        except Exception:
            pass
    existing["saved_at"] = time.time()
    SESSION_FILE.write_text(json.dumps(existing, indent=2))
    logger.info("💾 Session timestamp saved.")


# ──────────────────────────────────────────────
# 6. BROWSER
# ──────────────────────────────────────────────
BROWSER_PROFILE_DIR = str(Path.cwd() / "browser_profile")

browser = Browser(
    config=BrowserConfig(
        user_data_dir=BROWSER_PROFILE_DIR,
    )
)


# ──────────────────────────────────────────────
# 7. LLM
# ──────────────────────────────────────────────
# llm = ChatOpenAI(model="gpt-4o")
llm = ChatGoogleGenerativeAI(model="models/gemini-2.5-flash-preview-04-17")


# ──────────────────────────────────────────────
# 8. TEMPLATES
# ──────────────────────────────────────────────
PERSONALIZED_REPLY_TEMPLATES = [
    "Thanks so much, {name}! Really means a lot 😊",
    "Appreciate it, {name}! Thank you for thinking of me 🙏",
    "Thank you, {name}! Hope you're having a great day too 😄",
    "That's so kind of you, {name}! Thanks a lot 🎂",
    "Aww, thanks {name}! Really appreciate the birthday wishes 🎉",
]

BIRTHDAY_WISH_TEMPLATES = [
    "Happy Birthday, {name}! 🎂 Hope your day is as amazing as you are!",
    "Wishing you a fantastic birthday, {name}! 🎉 Hope it's full of joy!",
    "Happy Birthday {name}! 🥳 Wishing you all the best on your special day!",
    "Many happy returns of the day, {name}! 🎈 Hope this year brings you great success!",
    "Happy Birthday {name}! 🎁 May your day be filled with happiness and laughter!",
]


# ──────────────────────────────────────────────
# 9. DRY RUN HELPER
# ──────────────────────────────────────────────
def dry_run_notice() -> str:
    if DRY_RUN:
        return """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any messages.
  Instead, for each message you WOULD send, print:
    [DRY RUN] Would send to <name>: "<message>"
  Then move on without clicking Send.
  At the end, summarize everything you would have done.
"""
    return ""


# ──────────────────────────────────────────────
# 10. BETTER WISH DETECTION RULES
# ──────────────────────────────────────────────
WISH_DETECTION_RULES = """
  BIRTHDAY WISH DETECTION RULES (read carefully):

  A message IS a birthday wish if it contains ANY of the following —

  ✅ Direct English phrases:
     "Happy birthday", "HBD", "Happy bday", "Many happy returns",
     "Wishing you a wonderful birthday", "Hope your birthday is amazing",
     "Congrats on your special day", "Enjoy your special day",
     "Hope you have a great day", "Birthday greetings"

  ✅ Indirect / creative English phrases:
     "Another year older", "Another trip around the sun",
     "Hope your day is as special as you are",
     "Celebrate you today", "Your big day",
     "May this year bring you", "May your day be filled",
     "Thinking of you on your day", "Cheers to you",
     "Here's to another year", "Hope today treats you well"

  ✅ Bengali: "শুভ জন্মদিন", "জন্মদিনের শুভেচ্ছা", "অনেক শুভকামনা"
  ✅ Arabic:  "عيد ميلاد سعيد", "كل عام وأنت بخير"
  ✅ Hindi:   "जन्मदिन मुबारक", "जन्मदिन की शुभकामनाएं"
  ✅ Spanish: "Feliz cumpleaños", "Feliz cumple"
  ✅ French:  "Joyeux anniversaire", "Bon anniversaire"
  ✅ German:  "Alles Gute zum Geburtstag"
  ✅ Turkish: "İyi ki doğdun", "Doğum günün kutlu olsun"
  ✅ Indonesian/Malay: "Selamat ulang tahun", "Met ultah"
  ✅ Emoji-only hints: 🎂 🎉 🎈 🥳 🎁 combined with a name or greeting

  ❌ NOT a birthday wish: job offers, general "Hi/Hello", business messages,
     replies to your own message, group announcements.

  When in doubt → SKIP.
"""


# ──────────────────────────────────────────────
# 11. FILTER NOTICE (injected into task prompts)
# ──────────────────────────────────────────────
def filter_notice(task: str) -> str:
    """Build a dynamic notice about cooldown/whitelist/blacklist for the agent."""
    recent   = get_recent_contacts(task, COOLDOWN_DAYS)
    cooldown_str  = ", ".join(recent) if recent else "None"
    whitelist_str = ", ".join(WHITELIST) if WHITELIST else "Everyone (no whitelist set)"
    blacklist_str = ", ".join(BLACKLIST) if BLACKLIST else "None"

    return f"""
  CONTACT FILTERS (follow strictly):

  🚫 BLACKLIST — always skip these contacts: {blacklist_str}
  ✅ WHITELIST — only process these contacts: {whitelist_str}
  ❄️  COOLDOWN  — skip these (already contacted in last {COOLDOWN_DAYS} days): {cooldown_str}

  If a contact appears in blacklist or cooldown → do NOT send, just skip.
  If whitelist is set → only send to contacts IN the whitelist.
"""


# ──────────────────────────────────────────────
# 12. TASK BUILDERS
# ──────────────────────────────────────────────
def build_linkedin_reply_task(already_logged_in: bool) -> str:
    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {USERNAME}\n"
            f"  Password: {PASSWORD}\n"
            "Handle MFA if prompted.\n"
        )
    )

    reply_templates_str = "\n".join(
        f'  {i+1}. "{t}"' for i, t in enumerate(PERSONALIZED_REPLY_TEMPLATES)
    )

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice()}
  {filter_notice("LinkedIn-Reply")}

  Once on LinkedIn:
  - Navigate to https://www.linkedin.com/messaging/
  - Examine each UNREAD message thread one by one (up to 15 threads).

  STEP 1 — Identify the sender's FIRST NAME.
  STEP 2 — Apply contact filters above (blacklist, whitelist, cooldown).
  STEP 3 — Detect if it's a birthday wish:
{WISH_DETECTION_RULES}

  STEP 4 — Reply or Skip.
    If IS birthday wish AND contact is allowed:
       Choose ONE template randomly, fill {{name}}, send (or log if DRY RUN):
{reply_templates_str}

    Otherwise → skip.

  At the end, provide a summary:
    - Replied to: (names + messages)
    - Skipped: (count + reason)
"""


def build_birthday_detection_task(already_logged_in: bool) -> str:
    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {USERNAME}\n"
            f"  Password: {PASSWORD}\n"
            "Handle MFA if prompted.\n"
        )
    )

    wish_templates_str = "\n".join(
        f'  {i+1}. "{t}"' for i, t in enumerate(BIRTHDAY_WISH_TEMPLATES)
    )

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice()}
  {filter_notice("LinkedIn-BirthdayDetection")}

  Goal: Find contacts with birthdays TODAY and send them a wish.

  STEP 1 — Go to https://www.linkedin.com/mynetwork/
    Look for "Birthdays" section or "Say happy birthday" button.
    Also check the notification bell 🔔.

  STEP 2 — For each birthday contact:
    a) Extract FIRST NAME only.
    b) Apply contact filters (blacklist, whitelist, cooldown).
    c) If allowed → open chat, choose ONE wish randomly, send (or log if DRY RUN):

{wish_templates_str}

  STEP 3 — Stop after 20 contacts or no more birthdays.

  Rules: TODAY only. No duplicates. Skip if unsure.

  At the end, provide a summary:
    - Wished: (names + messages)
    - Skipped: (count + reason)
"""


# ──────────────────────────────────────────────
# 13. RETRY HELPER
# ──────────────────────────────────────────────
async def run_with_retry(coro_factory, task_name: str, retries: int = 3, delay: int = 5):
    for attempt in range(1, retries + 1):
        try:
            logger.info("🚀 [%s] Attempt %d/%d", task_name, attempt, retries)
            result = await coro_factory()
            logger.info("✅ [%s] Completed successfully.", task_name)
            return result
        except Exception as e:
            logger.error("❌ [%s] Attempt %d failed: %s", task_name, attempt, e)
            if attempt < retries:
                logger.info("⏳ Retrying in %d seconds…", delay)
                await asyncio.sleep(delay)
            else:
                logger.critical("💀 [%s] All %d attempts failed.", task_name, retries)
                raise


# ──────────────────────────────────────────────
# 14. TASK RUNNERS
# ──────────────────────────────────────────────
task_github = f"""
  Open browser, go to {GITHUB_URL} and tell me how many followers they have.
"""


async def run_github_task():
    logger.info("=== GitHub Follower Check ===")

    async def _run():
        agent = Agent(task=task_github, llm=llm, browser=browser)
        return await agent.run()

    result = await run_with_retry(_run, task_name="GitHub")
    logger.info("GitHub Result: %s", result)
    return result


async def run_linkedin_reply_task():
    logger.info("=== LinkedIn: Replying to Birthday Wishes === [DRY RUN: %s]", DRY_RUN)
    logged_in = session_is_valid()
    task = build_linkedin_reply_task(already_logged_in=logged_in)

    async def _run():
        agent = Agent(task=task, llm=llm, browser=browser)
        return await agent.run()

    result = await run_with_retry(_run, task_name="LinkedIn-Reply")
    save_session_timestamp()

    # Parse result to extract names (simplified)
    wished = []
    skipped = 0
    result_str = str(result)
    for line in result_str.splitlines():
        if "replied to" in line.lower() or "would send to" in line.lower():
            wished.append(line.strip())
        if "skipped" in line.lower():
            skipped += 1

    # Log to DB
    for name in wished:
        log_action("LinkedIn-Reply", name, "replied", DRY_RUN)

    # Send notification
    send_summary("Reply to Wishes", wished, skipped, DRY_RUN)

    logger.info("LinkedIn Reply Result: %s", result)
    return result


async def run_birthday_detection_task():
    logger.info("=== LinkedIn: Sending Birthday Wishes === [DRY RUN: %s]", DRY_RUN)
    logged_in = session_is_valid()
    task = build_birthday_detection_task(already_logged_in=logged_in)

    async def _run():
        agent = Agent(task=task, llm=llm, browser=browser)
        return await agent.run()

    result = await run_with_retry(_run, task_name="LinkedIn-BirthdayDetection")
    save_session_timestamp()

    # Parse result
    wished = []
    skipped = 0
    result_str = str(result)
    for line in result_str.splitlines():
        if "wished" in line.lower() or "would send to" in line.lower():
            wished.append(line.strip())
        if "skipped" in line.lower():
            skipped += 1

    # Log to DB
    for name in wished:
        log_action("LinkedIn-BirthdayDetection", name, "wished", DRY_RUN)

    # Send notification
    send_summary("Birthday Detection", wished, skipped, DRY_RUN)

    logger.info("Birthday Detection Result: %s", result)
    return result


# ──────────────────────────────────────────────
# 15. DAILY SCHEDULED JOB
# ──────────────────────────────────────────────
async def daily_job():
    logger.info("⏰ Scheduler triggered daily job.")
    try:
        await run_birthday_detection_task()
        await run_linkedin_reply_task()
    except Exception as e:
        logger.error("❌ Daily job failed: %s", e)


async def run_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        daily_job,
        trigger="cron",
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
    )
    scheduler.start()
    logger.info(
        "📅 Scheduler started. Runs daily at %02d:%02d. DRY_RUN=%s",
        SCHEDULE_HOUR, SCHEDULE_MINUTE, DRY_RUN,
    )
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("🛑 Scheduler stopped.")


# ──────────────────────────────────────────────
# 16. CLEANUP
# ──────────────────────────────────────────────
async def close_browser():
    try:
        await browser.close()
        logger.info("🔒 Browser closed.")
    except Exception as e:
        logger.warning("⚠️  Error closing browser: %s", e)


# ──────────────────────────────────────────────
# 17. ENTRYPOINT
# ──────────────────────────────────────────────
async def main():
    init_db()  # Ensure SQLite DB is ready

    try:
        # MODE 1: Run once immediately
        # await run_github_task()
        # await run_linkedin_reply_task()
        # await run_birthday_detection_task()

        # MODE 2: Daily scheduler (keep terminal open)
        await run_scheduler()

    finally:
        await close_browser()


if __name__ == "__main__":
    asyncio.run(main())