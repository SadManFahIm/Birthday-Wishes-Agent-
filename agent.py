import asyncio
import json
import logging
import os
import time
from pathlib import Path

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
        logging.FileHandler("agent.log"),   # saves to file
        logging.StreamHandler(),            # still prints to terminal
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

if not USERNAME or not PASSWORD:
    raise EnvironmentError(
        "❌ USERNAME or PASSWORD is missing in .env file. "
        "Please fill in your credentials."
    )

# ──────────────────────────────────────────────
# 3. SESSION / COOKIE MANAGEMENT
#    Instead of logging in with password every time,
#    we save the browser session (cookies) after the
#    first login and reuse them next time.
# ──────────────────────────────────────────────
SESSION_FILE = Path("linkedin_session.json")
SESSION_MAX_AGE_HOURS = 12   # re-login after 12 hours


def session_is_valid() -> bool:
    """Return True if a saved session exists and is still fresh."""
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
    """Write a timestamp so we know when the session was saved."""
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
# 4. BROWSER  (user-data-dir keeps cookies on disk)
# ──────────────────────────────────────────────
BROWSER_PROFILE_DIR = str(Path.cwd() / "browser_profile")

browser = Browser(
    config=BrowserConfig(
        # Storing the browser profile on disk means cookies/session
        # data persist between runs — no need to log in every time.
        user_data_dir=BROWSER_PROFILE_DIR,
    )
)


# ──────────────────────────────────────────────
# 5. LLM
# ──────────────────────────────────────────────
# llm = ChatOpenAI(model="gpt-4o")
llm = ChatGoogleGenerativeAI(model="models/gemini-2.5-flash-preview-04-17")


# ──────────────────────────────────────────────
# 6. TASK DEFINITIONS
# ──────────────────────────────────────────────
task_github = f"""
  Open browser, then go to {GITHUB_URL} and tell me how many followers they have.
"""

# LinkedIn task adapts based on whether we already have a session
def build_linkedin_task(already_logged_in: bool) -> str:
    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {USERNAME}\n"
            f"  Password: {PASSWORD}\n"
            "Handle MFA if prompted (wait for user if needed).\n"
            "After successful login, save the session by continuing."
        )
    )

    return f"""
  Open the browser.
  {login_instructions}

  Once on LinkedIn:
  - Navigate to the main messaging page (https://www.linkedin.com/messaging/).
  - Examine each UNREAD message thread one by one (up to 15 threads).

  For each thread:
    ✅ If the message is ONLY a simple birthday wish
       (e.g. "Happy birthday!", "HBD!", "Many happy returns!", "Hope your day is great!"):
       → Reply with a short, warm thank-you. Rotate randomly among:
         "Thanks so much! 😊", "Really appreciate the birthday wishes! 🎂",
         "Thank you, means a lot! 🙏", "Thanks for thinking of me! 😄"

    ❌ If the message contains anything more than a birthday wish,
       or is clearly NOT a birthday wish:
       → Do NOT reply. Just open it (mark as read) and move on.

  Accuracy first — it is better to skip a birthday wish than to
  accidentally reply to an unrelated message.

  At the end, provide a summary:
    - How many birthday wishes were replied to
    - How many threads were skipped
    - Any errors encountered
"""


# ──────────────────────────────────────────────
# 7. RETRY HELPER
# ──────────────────────────────────────────────
async def run_with_retry(coro_factory, task_name: str, retries: int = 3, delay: int = 5):
    """
    Run an async coroutine, retrying up to `retries` times on failure.

    coro_factory: a callable that returns a coroutine (so we can recreate it on retry)
    """
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
                logger.critical(
                    "💀 [%s] All %d attempts failed. Giving up.", task_name, retries
                )
                raise


# ──────────────────────────────────────────────
# 8. TASK RUNNERS
# ──────────────────────────────────────────────
async def run_github_task():
    logger.info("=== GitHub Follower Check ===")

    async def _run():
        agent = Agent(task=task_github, llm=llm, browser=browser)
        return await agent.run()

    result = await run_with_retry(_run, task_name="GitHub")
    logger.info("GitHub Result: %s", result)
    return result


async def run_linkedin_task():
    logger.info("=== LinkedIn Birthday Wishes ===")

    logged_in = session_is_valid()
    task = build_linkedin_task(already_logged_in=logged_in)

    async def _run():
        agent = Agent(task=task, llm=llm, browser=browser)
        return await agent.run()

    result = await run_with_retry(_run, task_name="LinkedIn")

    # After a successful run, mark session as fresh
    save_session_timestamp()

    logger.info("LinkedIn Result: %s", result)
    return result


# ──────────────────────────────────────────────
# 9. CLEANUP
# ──────────────────────────────────────────────
async def close_browser():
    try:
        await browser.close()
        logger.info("🔒 Browser closed.")
    except Exception as e:
        logger.warning("⚠️  Error closing browser: %s", e)


# ──────────────────────────────────────────────
# 10. ENTRYPOINT
# ──────────────────────────────────────────────
async def main():
    try:
        # ── Choose which task to run ──────────────────
        # Comment/uncomment as needed:

        await run_github_task()
        # await run_linkedin_task()

    finally:
        await close_browser()


if __name__ == "__main__":
    asyncio.run(main())