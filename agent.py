import asyncio
import json
import logging
import time
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from browser_use import Agent, Browser, BrowserConfig
from dotenv import dotenv_values
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

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

# ── DRY RUN MODE ─────────────────────────────
# Set to True  → agent will SHOW what it would do, but NOT actually send messages
# Set to False → agent will actually send messages
DRY_RUN = True

# ── SCHEDULER TIME ────────────────────────────
# Agent will run automatically every day at this time (24h format)
SCHEDULE_HOUR   = 9   # 9 AM
SCHEDULE_MINUTE = 0   # :00

if not USERNAME or not PASSWORD:
    raise EnvironmentError(
        "❌ USERNAME or PASSWORD is missing in .env file. "
        "Please fill in your credentials."
    )


# ──────────────────────────────────────────────
# 3. SESSION / COOKIE MANAGEMENT
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
# 4. BROWSER
# ──────────────────────────────────────────────
BROWSER_PROFILE_DIR = str(Path.cwd() / "browser_profile")

browser = Browser(
    config=BrowserConfig(
        user_data_dir=BROWSER_PROFILE_DIR,
    )
)


# ──────────────────────────────────────────────
# 5. LLM
# ──────────────────────────────────────────────
# llm = ChatOpenAI(model="gpt-4o")
llm = ChatGoogleGenerativeAI(model="models/gemini-2.5-flash-preview-04-17")


# ──────────────────────────────────────────────
# 6. TEMPLATES
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
# 7. DRY RUN HELPER
# ──────────────────────────────────────────────
def dry_run_notice() -> str:
    """Returns extra instructions for the agent when DRY_RUN is enabled."""
    if DRY_RUN:
        return """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any messages.
  Instead, for each message you WOULD send, print:
    [DRY RUN] Would send to <name>: "<message>"
  Then move on without clicking Send.
  At the end, summarize everything you would have done.
"""
    return ""  # Normal mode — no extra instructions


# ──────────────────────────────────────────────
# 8. TASK BUILDERS
# ──────────────────────────────────────────────
def build_linkedin_reply_task(already_logged_in: bool) -> str:
    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {USERNAME}\n"
            f"  Password: {PASSWORD}\n"
            "Handle MFA if prompted (wait for user if needed).\n"
        )
    )

    reply_templates_str = "\n".join(
        f'  {i+1}. "{t}"'
        for i, t in enumerate(PERSONALIZED_REPLY_TEMPLATES)
    )

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice()}

  Once on LinkedIn:
  - Navigate to the main messaging page (https://www.linkedin.com/messaging/).
  - Examine each UNREAD message thread one by one (up to 15 threads).

  STEP 1 — Identify the sender's FIRST NAME.
  STEP 2 — Check if it's a birthday wish.
    YES: "Happy birthday", "HBD", "Many happy returns", "Hope your day is great", etc.
    NO:  Anything else — questions, business, job offers, unrelated greetings.

  STEP 3 — Reply or Skip.
    If YES → choose ONE template, fill in {{name}}, send (or log if DRY RUN):
{reply_templates_str}

    If NO → open thread (mark as read) and move on.

  At the end, provide a summary of actions taken.
"""


def build_birthday_detection_task(already_logged_in: bool) -> str:
    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {USERNAME}\n"
            f"  Password: {PASSWORD}\n"
            "Handle MFA if prompted (wait for user if needed).\n"
        )
    )

    wish_templates_str = "\n".join(
        f'  {i+1}. "{t}"'
        for i, t in enumerate(BIRTHDAY_WISH_TEMPLATES)
    )

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice()}

  Goal: Find contacts with birthdays TODAY and send them a wish.

  STEP 1 — Go to https://www.linkedin.com/mynetwork/
    Look for a "Birthdays" section or "Say happy birthday" button.
    Also check the notification bell 🔔 for birthday alerts.

  STEP 2 — For each contact with a birthday today:
    a) Extract their FIRST NAME only.
    b) Open their chat / Message button.
    c) Choose ONE wish template, fill in {{name}}, send (or log if DRY RUN):

{wish_templates_str}

  STEP 3 — Stop after 20 contacts or when no more birthdays remain.

  Rules:
    - Only wish people whose birthday is TODAY.
    - No duplicate wishes.
    - If unsure, SKIP.

  At the end, provide a summary of actions taken.
"""


# ──────────────────────────────────────────────
# 9. RETRY HELPER
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
                logger.critical("💀 [%s] All %d attempts failed. Giving up.", task_name, retries)
                raise


# ──────────────────────────────────────────────
# 10. TASK RUNNERS
# ──────────────────────────────────────────────
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
    logger.info("Birthday Detection Result: %s", result)
    return result


# ──────────────────────────────────────────────
# 11. DAILY SCHEDULED JOB
# ──────────────────────────────────────────────
async def daily_job():
    """
    This runs automatically every day at SCHEDULE_HOUR:SCHEDULE_MINUTE.
    Adjust DRY_RUN at the top to test before going live.
    """
    logger.info("⏰ Scheduler triggered daily job.")
    try:
        await run_birthday_detection_task()   # Wish contacts on their birthday
        await run_linkedin_reply_task()        # Reply to wishes sent to you
    except Exception as e:
        logger.error("❌ Daily job failed: %s", e)


async def run_scheduler():
    """Start the scheduler and keep it running."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        daily_job,
        trigger="cron",
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
    )
    scheduler.start()
    logger.info(
        "📅 Scheduler started. Agent will run every day at %02d:%02d.",
        SCHEDULE_HOUR, SCHEDULE_MINUTE,
    )
    logger.info("   DRY RUN mode: %s", DRY_RUN)
    logger.info("   Press Ctrl+C to stop.")

    try:
        while True:
            await asyncio.sleep(60)  # Keep alive
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("🛑 Scheduler stopped.")


# ──────────────────────────────────────────────
# 12. CLEANUP
# ──────────────────────────────────────────────
async def close_browser():
    try:
        await browser.close()
        logger.info("🔒 Browser closed.")
    except Exception as e:
        logger.warning("⚠️  Error closing browser: %s", e)


# ──────────────────────────────────────────────
# 13. ENTRYPOINT
# ──────────────────────────────────────────────
task_github = f"""
  Open browser, then go to {GITHUB_URL} and tell me how many followers they have.
"""

async def main():
    try:
        # ── Pick ONE mode to run ──────────────────────

        # MODE 1: Run once immediately (good for testing)
        # await run_github_task()
        # await run_linkedin_reply_task()
        # await run_birthday_detection_task()

        # MODE 2: Run on a daily schedule (keep terminal open)
        await run_scheduler()

    finally:
        await close_browser()


if __name__ == "__main__":
    asyncio.run(main())