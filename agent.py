import asyncio
import json
import logging
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
# 4. BROWSER (user-data-dir keeps cookies on disk)
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
# 6. PERSONALIZED REPLY TEMPLATES
#    Used when someone sends YOU a birthday wish.
#    {name} = sender's first name
# ──────────────────────────────────────────────
PERSONALIZED_REPLY_TEMPLATES = [
    "Thanks so much, {name}! Really means a lot 😊",
    "Appreciate it, {name}! Thank you for thinking of me 🙏",
    "Thank you, {name}! Hope you're having a great day too 😄",
    "That's so kind of you, {name}! Thanks a lot 🎂",
    "Aww, thanks {name}! Really appreciate the birthday wishes 🎉",
]

# ──────────────────────────────────────────────
# 7. BIRTHDAY WISH TEMPLATES
#    Used when YOU wish someone on their birthday.
#    {name} = recipient's first name
# ──────────────────────────────────────────────
BIRTHDAY_WISH_TEMPLATES = [
    "Happy Birthday, {name}! 🎂 Hope your day is as amazing as you are!",
    "Wishing you a fantastic birthday, {name}! 🎉 Hope it's full of joy!",
    "Happy Birthday {name}! 🥳 Wishing you all the best on your special day!",
    "Many happy returns of the day, {name}! 🎈 Hope this year brings you great success!",
    "Happy Birthday {name}! 🎁 May your day be filled with happiness and laughter!",
]


# ──────────────────────────────────────────────
# 8. TASK DEFINITIONS
# ──────────────────────────────────────────────
task_github = f"""
  Open browser, then go to {GITHUB_URL} and tell me how many followers they have.
"""


def build_linkedin_reply_task(already_logged_in: bool) -> str:
    """Task: Reply to birthday wishes people sent YOU."""
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

  Once on LinkedIn:
  - Navigate to the main messaging page (https://www.linkedin.com/messaging/).
  - Examine each UNREAD message thread one by one (up to 15 threads).

  For each thread, follow these steps:

  STEP 1 — Identify the sender's FIRST NAME.
    Look at the name shown on the message thread header or profile.
    Extract only the first name (e.g. if the name is "Rahul Ahmed", use "Rahul").

  STEP 2 — Check if it's a birthday wish.
    It IS a birthday wish if the message contains phrases like:
       "Happy birthday", "HBD", "Many happy returns", "Hope your day is great",
       "Congrats on your special day", "Wishing you a wonderful birthday", etc.

    It is NOT a birthday wish if it contains anything else — questions,
    business topics, job offers, or general greetings unrelated to birthday.

  STEP 3 — Reply or Skip.
    If it IS a birthday wish:
       Choose ONE reply from the templates below and fill in {{name}} with
       the sender's actual first name:

{reply_templates_str}

       Example: if sender is "Rahul" and you pick template 1,
       send: "Thanks so much, Rahul! Really means a lot 😊"

       Pick templates randomly — do NOT always use template 1.

    If it is NOT a birthday wish:
       Do NOT reply. Just open the thread (mark as read) and move on.

  Accuracy first — it is better to skip a birthday wish than to
  accidentally reply to an unrelated message.

  At the end, provide a summary:
    - How many birthday wishes were replied to (list sender names)
    - How many threads were skipped
    - Any errors encountered
"""


def build_birthday_detection_task(already_logged_in: bool) -> str:
    """Task: Detect contacts with birthdays TODAY and send them wishes."""
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

  Once on LinkedIn, your goal is to find contacts with birthdays TODAY
  and send them a birthday wish message.

  STEP 1 — Find today's birthdays.
    Go to: https://www.linkedin.com/mynetwork/
    Look for a "Birthdays" section or notification that shows contacts
    celebrating their birthday today.
    Also check the top notification bell (🔔) for any birthday alerts.
    If LinkedIn shows a birthday card or "Say happy birthday" button
    for any contact, note their name.

  STEP 2 — For each contact with a birthday today:
    a) Extract their FIRST NAME only
       (e.g. "Rahul Ahmed" → use "Rahul").

    b) Click on their profile or the "Message" button to open a chat.

    c) Choose ONE wish from the templates below, fill in {{name}}
       with their actual first name, and send it:

{wish_templates_str}

       Example: if the contact is "Priya Sharma" and you pick template 2,
       send: "Wishing you a fantastic birthday, Priya! 🎉 Hope it's full of joy!"

       Pick templates randomly — do NOT always pick template 1.

    d) After sending, move to the next birthday contact.

  STEP 3 — Stop conditions.
    Stop after wishing up to 20 contacts, or when there are no more
    birthday contacts to wish today.

  Important rules:
    - Only wish people whose birthday is TODAY — not yesterday, not tomorrow.
    - Do NOT send duplicate wishes to the same person.
    - If you are unsure whether it is their birthday, SKIP them.

  At the end, provide a summary:
    - Names of contacts you wished happy birthday
    - Total count of wishes sent
    - Any contacts skipped and why
"""


# ──────────────────────────────────────────────
# 9. RETRY HELPER
# ──────────────────────────────────────────────
async def run_with_retry(coro_factory, task_name: str, retries: int = 3, delay: int = 5):
    """Run an async coroutine, retrying up to `retries` times on failure."""
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
    """Reply to birthday wishes that people sent you."""
    logger.info("=== LinkedIn: Replying to Birthday Wishes ===")

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
    """Detect contacts with birthdays today and send them wishes."""
    logger.info("=== LinkedIn: Sending Birthday Wishes to Contacts ===")

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
# 11. CLEANUP
# ──────────────────────────────────────────────
async def close_browser():
    try:
        await browser.close()
        logger.info("🔒 Browser closed.")
    except Exception as e:
        logger.warning("⚠️  Error closing browser: %s", e)


# ──────────────────────────────────────────────
# 12. ENTRYPOINT
# ──────────────────────────────────────────────
async def main():
    try:
        # ── Choose which task(s) to run ───────────────
        # Comment/uncomment as needed:

        await run_github_task()
        # await run_linkedin_reply_task()       # Reply to wishes sent to YOU
        # await run_birthday_detection_task()   # Wish YOUR contacts on their birthday

    finally:
        await close_browser()


if __name__ == "__main__":
    asyncio.run(main())