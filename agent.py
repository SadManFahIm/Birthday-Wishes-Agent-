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
from platforms import (run_whatsapp_task, run_facebook_task,
                        run_instagram_task, run_linkedin_birthday_with_custom_wish)
from wish_generator import generate_custom_wish
from followup import (init_followup_table, schedule_followup,
                       get_pending_followups, mark_followup_sent,
                       build_followup_task)
from calendar_export import export_birthday_calendar
from smart_timing import should_send_now, build_timing_instructions
from sentiment import analyze_sentiment, get_sentiment_reply, build_sentiment_instructions
from auto_connect import (init_connections_table, get_connects_today,
                           log_connection_request, build_auto_connect_task)
from memory import (init_memory_table, save_contact_memory,
                    get_contact_memory, build_memory_context,
                    generate_memory_aware_wish, build_memory_instructions)
from post_engagement import (init_engagement_table, log_engagement,
                              run_post_engagement)
from birthday_reminder import (init_reminder_table, run_birthday_reminder)
from contact_notes import (init_notes_table, add_note, get_notes, build_notes_context)
from wish_scorer import score_wish, generate_scored_wish, build_scorer_instructions
from group_birthday import (init_group_birthday_table, run_group_birthday_detection)
from connection_tracker import (init_tracker_table, log_interaction,
                                calculate_strength, get_top_connections,
                                get_fading_connections, sync_from_history)
from auto_reply_followup import (init_auto_reply_table, run_auto_reply_followup)
from tone_matching import detect_tone, get_tone_matched_reply, build_tone_matching_instructions
from occasion_detection import run_occasion_detection
from multilang_reply import detect_language, get_multilang_reply, build_multilang_instructions
from relationship_health import (init_health_table, run_relationship_health_report)
from best_time_connect import (init_activity_table, get_best_send_time,
                               run_best_time_analysis, build_timing_notice)
from dm_campaign import (init_campaign_table, run_dm_campaign, get_campaign_stats)
from contact_categorizer import (init_categorizer_table, run_contact_categorizer,
                                  get_contacts_by_category, get_category_stats)
from voice import generate_voice

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

DRY_RUN = True

SCHEDULE_HOUR   = 9
SCHEDULE_MINUTE = 0

WHITELIST: list[str] = []
BLACKLIST: list[str] = []
COOLDOWN_DAYS = 30

# ── PLATFORM TOGGLES ─────────────────────────
ENABLE_LINKEDIN  = True
ENABLE_WHATSAPP  = True
ENABLE_FACEBOOK  = True
ENABLE_INSTAGRAM = True

# ── VOICE MESSAGE SETTINGS ────────────────────
VOICE_ENABLED = True
VOICE_ENGINE  = "gtts"

# ── SENTIMENT ANALYSIS ────────────────────────
SENTIMENT_ANALYSIS_ENABLED = True

# ── AUTO-CONNECT ──────────────────────────────
AUTO_CONNECT_ENABLED = True
MAX_CONNECTS_PER_DAY = 10

if not USERNAME or not PASSWORD:
    raise EnvironmentError("❌ USERNAME or PASSWORD missing in .env")


# ──────────────────────────────────────────────
# 3. SQLITE LOGGING
# ──────────────────────────────────────────────
DB_FILE = Path("agent_history.db")


def init_db():
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
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO history (date, task, contact, message, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date.today().isoformat(), task, contact, message,
             int(dry_run), datetime.now().isoformat()),
        )
        conn.commit()
    logger.info("🗄️  Logged: [%s] → %s", task, contact)


def get_recent_contacts(task: str, days: int) -> set[str]:
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
# 4. WHITELIST / BLACKLIST / COOLDOWN HELPERS
# ──────────────────────────────────────────────
def is_allowed(name: str) -> bool:
    name_lower = name.lower()
    if BLACKLIST and name_lower in [b.lower() for b in BLACKLIST]:
        return False
    if WHITELIST and name_lower not in [w.lower() for w in WHITELIST]:
        return False
    return True


def filter_notice(task: str) -> str:
    recent        = get_recent_contacts(task, COOLDOWN_DAYS)
    cooldown_str  = ", ".join(recent) if recent else "None"
    whitelist_str = ", ".join(WHITELIST) if WHITELIST else "Everyone (no whitelist set)"
    blacklist_str = ", ".join(BLACKLIST) if BLACKLIST else "None"
    return f"""
  CONTACT FILTERS (follow strictly):
  🚫 BLACKLIST — always skip: {blacklist_str}
  ✅ WHITELIST — only process: {whitelist_str}
  ❄️  COOLDOWN  — skip (contacted in last {COOLDOWN_DAYS} days): {cooldown_str}
"""


# ──────────────────────────────────────────────
# 5. SESSION MANAGEMENT
# ──────────────────────────────────────────────
SESSION_FILE = Path("linkedin_session.json")
SESSION_MAX_AGE_HOURS = 12


def session_is_valid() -> bool:
    if not SESSION_FILE.exists():
        return False
    try:
        data = json.loads(SESSION_FILE.read_text())
        age_hours = (time.time() - data.get("saved_at", 0)) / 3600
        if age_hours > SESSION_MAX_AGE_HOURS:
            logger.info("⏰ Session expired. Will re-login.")
            return False
        logger.info("✅ Valid session (%.1f h old).", age_hours)
        return True
    except Exception as e:
        logger.warning("⚠️  Session read error: %s", e)
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
    logger.info("💾 Session saved.")


# ──────────────────────────────────────────────
# 6. BROWSER
# ──────────────────────────────────────────────
BROWSER_PROFILE_DIR = str(Path.cwd() / "browser_profile")

browser = Browser(
    config=BrowserConfig(user_data_dir=BROWSER_PROFILE_DIR)
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
    "Many happy returns of the day, {name}! 🎈 Hope this year brings great success!",
    "Happy Birthday {name}! 🎁 May your day be filled with happiness and laughter!",
]


# ──────────────────────────────────────────────
# 9. SHARED DETECTION RULES
# ──────────────────────────────────────────────
WISH_DETECTION_RULES = """
  A message IS a birthday wish if it contains ANY of the following —

  ✅ Direct English: "Happy birthday", "HBD", "Happy bday", "Many happy returns",
     "Wishing you a wonderful birthday", "Congrats on your special day",
     "Hope you have a great day", "Birthday greetings"

  ✅ Indirect English: "Another year older", "Another trip around the sun",
     "Hope your day is as special as you are", "Celebrate you today",
     "May this year bring you", "Here's to another year"

  ✅ Bengali:    "শুভ জন্মদিন", "জন্মদিনের শুভেচ্ছা", "অনেক শুভকামনা"
  ✅ Arabic:     "عيد ميلاد سعيد", "كل عام وأنت بخير"
  ✅ Hindi:      "जन्मदिन मुबारक", "जन्मदिन की शुभकामनाएं"
  ✅ Spanish:    "Feliz cumpleaños", "Feliz cumple"
  ✅ French:     "Joyeux anniversaire"
  ✅ German:     "Alles Gute zum Geburtstag"
  ✅ Turkish:    "İyi ki doğdun"
  ✅ Indonesian: "Selamat ulang tahun", "Met ultah"
  ✅ Emoji:      🎂 🎉 🎈 🥳 🎁 (combined with name or greeting)

  ❌ NOT a birthday wish: job offers, "Hi/Hello", business messages,
     group announcements, replies to your own message.

  When in doubt → SKIP.
"""


# ──────────────────────────────────────────────
# 10. DRY RUN NOTICE
# ──────────────────────────────────────────────
def dry_run_notice() -> str:
    if DRY_RUN:
        return """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT send any messages.
  For each message you WOULD send, print:
    [DRY RUN] Would send to <n>: "<message>"
  Then move on without clicking Send.
"""
    return ""


# ──────────────────────────────────────────────
# 11. LINKEDIN TASK BUILDERS
# ──────────────────────────────────────────────
def build_linkedin_reply_task(already_logged_in: bool) -> str:
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in else
        f"Go to https://linkedin.com and log in:\n"
        f"  Email: {USERNAME}\n  Password: {PASSWORD}\n"
        "Handle MFA if prompted.\n"
    )
    templates_str = "\n".join(f'  {i+1}. "{t}"' for i, t in enumerate(PERSONALIZED_REPLY_TEMPLATES))
    return f"""
  Open the browser. {login}
  {dry_run_notice()}
  {filter_notice("LinkedIn-Reply")}

  Go to https://www.linkedin.com/messaging/
  Check up to 15 UNREAD threads.

  For each thread:
    STEP 1 — Get sender's FIRST NAME.
    STEP 2 — Apply filters (blacklist, whitelist, cooldown).
    STEP 3 — Detect birthday wish: {WISH_DETECTION_RULES}
    STEP 4 — If yes → choose ONE template randomly, fill {{name}}, send:
{templates_str}
    If no → skip.

  Summary at the end: replied to (names), skipped (count+reason).
"""


def build_birthday_detection_task(already_logged_in: bool) -> str:
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in else
        f"Go to https://linkedin.com and log in:\n"
        f"  Email: {USERNAME}\n  Password: {PASSWORD}\n"
        "Handle MFA if prompted.\n"
    )
    templates_str = "\n".join(f'  {i+1}. "{t}"' for i, t in enumerate(BIRTHDAY_WISH_TEMPLATES))
    return f"""
  Open the browser. {login}
  {dry_run_notice()}
  {filter_notice("LinkedIn-BirthdayDetection")}

  Go to https://www.linkedin.com/mynetwork/
  Find contacts with birthdays TODAY (check Birthdays section + 🔔).

  For each birthday contact:
    a) Get FIRST NAME only.
    b) Apply filters.
    c) Choose ONE wish randomly, fill {{name}}, send (or log if DRY RUN):
{templates_str}

  Stop after 20 contacts. TODAY only. No duplicates.
  Summary: wished (names), skipped (count+reason).
"""


# ──────────────────────────────────────────────
# 12. RETRY HELPER
# ──────────────────────────────────────────────
async def run_with_retry(coro_factory, task_name: str, retries: int = 3, delay: int = 5):
    for attempt in range(1, retries + 1):
        try:
            logger.info("🚀 [%s] Attempt %d/%d", task_name, attempt, retries)
            result = await coro_factory()
            logger.info("✅ [%s] Done.", task_name)
            return result
        except Exception as e:
            logger.error("❌ [%s] Attempt %d failed: %s", task_name, attempt, e)
            if attempt < retries:
                await asyncio.sleep(delay)
            else:
                logger.critical("💀 [%s] All attempts failed.", task_name)
                raise


# ──────────────────────────────────────────────
# 13. TASK RUNNERS
# ──────────────────────────────────────────────
task_github = f"Open browser, go to {GITHUB_URL} and tell me how many followers they have."


async def run_github_task():
    logger.info("=== GitHub Follower Check ===")
    async def _run():
        return await Agent(task=task_github, llm=llm, browser=browser).run()
    result = await run_with_retry(_run, "GitHub")
    logger.info("GitHub: %s", result)
    return result


async def run_linkedin_reply_task():
    logger.info("=== LinkedIn Reply === [DRY RUN: %s]", DRY_RUN)
    task = build_linkedin_reply_task(session_is_valid())
    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()
    result = await run_with_retry(_run, "LinkedIn-Reply")
    save_session_timestamp()
    send_summary("LinkedIn - Reply to Wishes", [], 0, DRY_RUN)
    return result


async def run_birthday_detection_task():
    logger.info("=== LinkedIn Birthday Detection === [DRY RUN: %s]", DRY_RUN)
    task = build_birthday_detection_task(session_is_valid())
    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()
    result = await run_with_retry(_run, "LinkedIn-BirthdayDetection")
    save_session_timestamp()
    send_summary("LinkedIn - Birthday Detection", [], 0, DRY_RUN)
    return result


async def run_ai_custom_wish_task():
    """Birthday detection with AI-generated personalized wishes."""
    logger.info("=== LinkedIn: AI Custom Wishes === [DRY RUN: %s]", DRY_RUN)
    async def _run():
        return await run_linkedin_birthday_with_custom_wish(
            llm=llm,
            browser=browser,
            dry_run=DRY_RUN,
            username=USERNAME,
            password=PASSWORD,
            already_logged_in=session_is_valid(),
            filter_notice=filter_notice("LinkedIn-BirthdayDetection"),
            wish_detection_rules=WISH_DETECTION_RULES,
        )
    result = await run_with_retry(_run, "LinkedIn-AIWish")
    save_session_timestamp()
    send_summary("LinkedIn - AI Custom Wishes", [], 0, DRY_RUN)
    return result


async def run_sentiment_reply_task():
    """Reply to LinkedIn wishes with sentiment-aware messages + auto connect."""
    logger.info("=== LinkedIn: Sentiment-Aware Reply === [DRY RUN: %s]", DRY_RUN)
    logged_in = session_is_valid()

    sentiment_instructions = build_sentiment_instructions() if SENTIMENT_ANALYSIS_ENABLED else ""
    connect_instructions   = build_auto_connect_task(
        username=USERNAME,
        password=PASSWORD,
        already_logged_in=logged_in,
        dry_run=DRY_RUN,
    ) if AUTO_CONNECT_ENABLED else ""

    task = build_linkedin_reply_task(logged_in)
    task = task + f"""
  ADDITIONAL INSTRUCTIONS:
  {sentiment_instructions}
  {connect_instructions}
"""
    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "LinkedIn-SentimentReply")
    save_session_timestamp()
    send_summary("LinkedIn - Sentiment Reply + Auto Connect", [], 0, DRY_RUN)
    return result


async def run_whatsapp_reply_task():
    logger.info("=== WhatsApp Reply === [DRY RUN: %s | VOICE: %s]", DRY_RUN, VOICE_ENABLED)
    async def _run():
        return await run_whatsapp_task(
            llm=llm, browser=browser, dry_run=DRY_RUN,
            wish_detection_rules=WISH_DETECTION_RULES,
            reply_templates=PERSONALIZED_REPLY_TEMPLATES,
            filter_notice=filter_notice("WhatsApp-Reply"),
            voice_enabled=VOICE_ENABLED,
            voice_engine=VOICE_ENGINE,
        )
    result = await run_with_retry(_run, "WhatsApp-Reply")
    send_summary("WhatsApp - Reply to Wishes", [], 0, DRY_RUN)
    return result


async def run_facebook_reply_task():
    logger.info("=== Facebook Messenger Reply === [DRY RUN: %s]", DRY_RUN)
    async def _run():
        return await run_facebook_task(
            llm=llm, browser=browser, dry_run=DRY_RUN,
            wish_detection_rules=WISH_DETECTION_RULES,
            reply_templates=PERSONALIZED_REPLY_TEMPLATES,
            filter_notice=filter_notice("Facebook-Reply"),
        )
    result = await run_with_retry(_run, "Facebook-Reply")
    send_summary("Facebook - Reply to Wishes", [], 0, DRY_RUN)
    return result


async def run_instagram_reply_task():
    logger.info("=== Instagram DM Reply === [DRY RUN: %s]", DRY_RUN)
    async def _run():
        return await run_instagram_task(
            llm=llm, browser=browser, dry_run=DRY_RUN,
            wish_detection_rules=WISH_DETECTION_RULES,
            reply_templates=PERSONALIZED_REPLY_TEMPLATES,
            filter_notice=filter_notice("Instagram-Reply"),
        )
    result = await run_with_retry(_run, "Instagram-Reply")
    send_summary("Instagram - Reply to Wishes", [], 0, DRY_RUN)
    return result


async def run_calendar_export():
    """Scrape LinkedIn birthdays and export to .ics file."""
    logger.info("=== Birthday Calendar Export ===")
    path = await export_birthday_calendar(
        llm=llm,
        browser=browser,
        username=USERNAME,
        password=PASSWORD,
        already_logged_in=session_is_valid(),
    )
    if path:
        logger.info("✅ Calendar exported to: %s", path)
    return path


async def run_followup_task():
    """Send follow-up messages to contacts whose birthday was 2-3 days ago."""
    logger.info("=== Follow-up Messages === [DRY RUN: %s]", DRY_RUN)

    pending = get_pending_followups()
    if not pending:
        logger.info("📭 No follow-ups due today.")
        return

    task = build_followup_task(
        pending=pending,
        dry_run=DRY_RUN,
        username=USERNAME,
        password=PASSWORD,
        already_logged_in=session_is_valid(),
    )

    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "FollowUp")
    save_session_timestamp()

    if not DRY_RUN:
        for item in pending:
            mark_followup_sent(item["id"])

    send_summary("Follow-up Messages", [p["contact"] for p in pending], 0, DRY_RUN)
    logger.info("Follow-up Result: %s", result)
    return result


async def run_memory_wish_task():
    """Send birthday wishes that reference last year's context."""
    logger.info("=== LinkedIn: Memory-Aware Wishes === [DRY RUN: %s]", DRY_RUN)
    logged_in = session_is_valid()

    task = f"""
  Open the browser.
  {"You are already logged into LinkedIn. Skip login." if True else ""}
  {dry_run_notice()}
  {filter_notice("LinkedIn-BirthdayDetection")}

  GOAL: Find contacts with birthdays TODAY and send memory-aware wishes.

  For each birthday contact:
    a) Apply contact filters.
    b) Visit their LinkedIn profile and note:
       - First name, job title, company, recent posts or achievements
    c) Check memory context (will be provided below per contact).
    d) Generate a wish that references last year's context if available.
    e) Send the wish (or log if DRY RUN).

  MEMORY SYSTEM:
  Before wishing each contact, their last year's memory context
  will be injected. Use it to make the wish feel personal and continuous.
  If no memory → write a warm first-time wish and note their profile details
  so they can be remembered next year.

  After sending each wish, save these details for next year:
    - Their current job title
    - Their current company
    - Any notable life events or achievements mentioned in their profile
    - The wish message you sent

  Stop after 20 contacts. TODAY only.
  Summary: wished (names + memory used Y/N), skipped (count+reason).
"""

    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "LinkedIn-MemoryWish")
    save_session_timestamp()
    send_summary("LinkedIn - Memory-Aware Wishes", [], 0, DRY_RUN)
    return result


async def run_categorizer_task():
    """Auto-categorize LinkedIn contacts by industry, seniority, location."""
    logger.info("=== Contact Categorizer === [MAX: %d]", CATEGORIZER_MAX_CONTACTS)
    count = await run_contact_categorizer(
        llm=llm,
        browser=browser,
        username=USERNAME,
        password=PASSWORD,
        already_logged_in=session_is_valid(),
        max_contacts=CATEGORIZER_MAX_CONTACTS,
    )
    stats = get_category_stats()
    logger.info(
        "🏷️  Categorized %d contacts | Industries: %s",
        count, list(stats.get("by_industry", {}).keys())[:3],
    )
    return count


async def run_dm_campaign_task():
    """Run a LinkedIn DM campaign for new or existing connections."""
    logger.info("=== LinkedIn DM Campaign: %s === [DRY RUN: %s]",
                CAMPAIGN_TYPE.upper(), DRY_RUN)
    result = await run_dm_campaign(
        llm=llm,
        browser=browser,
        campaign_type=CAMPAIGN_TYPE,
        username=USERNAME,
        password=PASSWORD,
        already_logged_in=session_is_valid(),
        dry_run=DRY_RUN,
        max_dms=MAX_DM_PER_DAY,
        cooldown_days=DM_COOLDOWN_DAYS,
        variant=CAMPAIGN_VARIANT,
    )
    stats = get_campaign_stats()
    logger.info(
        "📊 Campaign stats: %d sent | %.1f%% reply rate",
        stats.get("total_sent", 0), stats.get("reply_rate", 0),
    )
    return result


async def run_best_time_task(contacts: list[dict] = None):
    """Analyze activity patterns and find best time to connect."""
    logger.info("=== Best Time to Connect Analysis ===")
    if not contacts:
        logger.info("📭 No contacts provided for activity analysis.")
        return []
    results = await run_best_time_analysis(
        llm=llm,
        browser=browser,
        contacts=contacts,
        already_logged_in=session_is_valid(),
        username=USERNAME,
        password=PASSWORD,
    )
    for r in results:
        logger.info(
            "⏰ Best time for %s: %s at %d:00",
            r["contact"], r.get("best_day"), r.get("best_hour", 9),
        )
    return results


async def run_health_report_task():
    """Generate and send weekly relationship health report."""
    logger.info("=== Weekly Health Report === [DRY RUN: %s]", DRY_RUN)
    report = await run_relationship_health_report(dry_run=DRY_RUN)
    logger.info(
        "📊 Health report: %d contacts | Avg: %.1f",
        report.get("total_contacts", 0),
        report.get("average_score", 0),
    )
    return report


async def run_occasion_detection_task():
    """Scan LinkedIn for life events and send congratulations."""
    logger.info("=== Occasion Detection === [DRY RUN: %s]", DRY_RUN)
    await run_occasion_detection(
        llm=llm,
        browser=browser,
        username=USERNAME,
        password=PASSWORD,
        already_logged_in=session_is_valid(),
        dry_run=DRY_RUN,
    )


async def run_auto_reply_task():
    """Reply to responses to our birthday wishes and follow-ups."""
    logger.info("=== Auto Reply to Follow-up === [DRY RUN: %s]", DRY_RUN)
    await run_auto_reply_followup(
        llm=llm,
        browser=browser,
        username=USERNAME,
        password=PASSWORD,
        already_logged_in=session_is_valid(),
        dry_run=DRY_RUN,
        max_replies=MAX_AUTO_REPLIES_PER_DAY,
    )


async def run_group_birthday_task():
    """Detect and engage with birthday posts in LinkedIn Groups."""
    logger.info("=== Group Birthday Detection === [DRY RUN: %s]", DRY_RUN)
    await run_group_birthday_detection(
        llm=llm,
        browser=browser,
        username=USERNAME,
        password=PASSWORD,
        already_logged_in=session_is_valid(),
        dry_run=DRY_RUN,
        max_engagements=MAX_GROUP_ENGAGEMENTS,
        comment_enabled=GROUP_COMMENT_ENABLED,
        dm_enabled=GROUP_DM_ENABLED,
    )


async def run_birthday_reminder_task():
    """Send reminder emails for tomorrow's birthdays."""
    logger.info("=== Birthday Reminder Email === [DRY RUN: %s]", DRY_RUN)
    await run_birthday_reminder(
        llm=llm,
        browser=browser,
        username=USERNAME,
        password=PASSWORD,
        already_logged_in=session_is_valid(),
        dry_run=DRY_RUN,
    )


async def run_post_engagement_task():
    """Like and comment on birthday contacts' latest LinkedIn posts."""
    logger.info("=== LinkedIn Post Engagement === [DRY RUN: %s | MODE: %s]",
                DRY_RUN, ENGAGEMENT_MODE)

    # Sample contacts — in production these come from birthday detection result
    sample_contacts = [
        {"name": "Birthday Contact", "profile_url": "", "relationship": "colleague"}
    ]

    result = await run_post_engagement(
        llm=llm,
        browser=browser,
        birthday_contacts=sample_contacts,
        dry_run=DRY_RUN,
        engagement_mode=ENGAGEMENT_MODE,
        max_engagements=MAX_ENGAGEMENTS_PER_DAY,
    )
    send_summary("LinkedIn - Post Engagement", [], 0, DRY_RUN)
    return result


# ──────────────────────────────────────────────
# 14. DAILY JOB (all platforms)
# ──────────────────────────────────────────────
async def daily_job():
    logger.info("⏰ Daily job started.")
    try:
        if ENABLE_LINKEDIN:
            await run_birthday_detection_task()
            await run_linkedin_reply_task()

        if ENABLE_WHATSAPP:
            await run_whatsapp_reply_task()

        if ENABLE_FACEBOOK:
            await run_facebook_reply_task()

        if ENABLE_INSTAGRAM:
            await run_instagram_reply_task()

        await run_followup_task()

        if SENTIMENT_ANALYSIS_ENABLED or AUTO_CONNECT_ENABLED:
            await run_sentiment_reply_task()

        # Memory-aware birthday wishes
        if MEMORY_ENABLED:
            await run_memory_wish_task()

        # Post engagement (like + comment on birthday contacts' posts)
        if POST_ENGAGEMENT_ENABLED:
            await run_post_engagement_task()

        # Birthday reminder email for tomorrow's birthdays
        if BIRTHDAY_REMINDER_ENABLED:
            await run_birthday_reminder_task()

        # Group birthday detection
        if GROUP_BIRTHDAY_ENABLED:
            await run_group_birthday_task()

        # Auto reply to follow-up responses
        if AUTO_REPLY_FOLLOWUP_ENABLED:
            await run_auto_reply_task()

        # Occasion detection (promotion, new job, graduation, etc.)
        if OCCASION_DETECTION_ENABLED:
            await run_occasion_detection_task()

        # LinkedIn DM Campaign
        if DM_CAMPAIGN_ENABLED:
            await run_dm_campaign_task()

        # Contact categorizer (runs weekly on Sunday)
        if CONTACT_CATEGORIZER_ENABLED:
            from datetime import date
            if date.today().strftime("%A") == "Sunday":
                await run_categorizer_task()

        # Weekly relationship health report (Mondays only)
        if HEALTH_REPORT_ENABLED:
            from datetime import date
            if date.today().strftime("%A").lower() == HEALTH_REPORT_DAY.lower():
                await run_health_report_task()

    except Exception as e:
        logger.error("❌ Daily job error: %s", e)


async def run_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(daily_job, trigger="cron",
                      hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE)
    scheduler.start()
    logger.info("📅 Scheduler running. Daily at %02d:%02d. DRY_RUN=%s",
                SCHEDULE_HOUR, SCHEDULE_MINUTE, DRY_RUN)
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("🛑 Scheduler stopped.")


# ──────────────────────────────────────────────
# 15. CLEANUP
# ──────────────────────────────────────────────
async def close_browser():
    try:
        await browser.close()
        logger.info("🔒 Browser closed.")
    except Exception as e:
        logger.warning("⚠️  Browser close error: %s", e)


# ──────────────────────────────────────────────
# 16. ENTRYPOINT
# ──────────────────────────────────────────────
async def main():
    init_db()
    init_followup_table()
    init_connections_table()
    init_memory_table()
    init_engagement_table()
    init_reminder_table()
    init_notes_table()
    init_group_birthday_table()
    init_tracker_table()
    init_auto_reply_table()
    init_health_table()
    init_activity_table()
    init_campaign_table()
    init_categorizer_table()
    if CONNECTION_TRACKER_ENABLED:
        sync_from_history()  # Sync existing history into tracker
    try:
        # Run a single task immediately (uncomment to use):
        # await run_github_task()
        # await run_linkedin_reply_task()
        # await run_birthday_detection_task()
        # await run_ai_custom_wish_task()
        # await run_sentiment_reply_task()
        # await run_followup_task()
        # await run_calendar_export()
        # await run_whatsapp_reply_task()
        # await run_facebook_reply_task()
        # await run_instagram_reply_task()
        # await run_memory_wish_task()         # Memory-aware wishes
        # await run_post_engagement_task()    # Like + comment on posts
        # await run_birthday_reminder_task()  # Reminder email for tomorrow's birthdays
        # await run_group_birthday_task()      # Group birthday detection
        # await run_auto_reply_task()           # Auto reply to follow-up responses
        # await run_occasion_detection_task()  # Occasion detection & congratulations
        # await run_health_report_task()        # Weekly relationship health report
        # await run_best_time_task()            # Analyze best time to connect
        # await run_dm_campaign_task()          # LinkedIn DM campaign
        # await run_categorizer_task()          # Auto-categorize contacts

        # Run ALL platforms on daily schedule:
        await run_scheduler()

    finally:
        await close_browser()


if __name__ == "__main__":
    asyncio.run(main())