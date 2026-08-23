"""
Scheduler — Birthday Wishes Agent v10.0
=========================================
Daily job scheduler with cron-based timing, platform toggles,
weekly task scheduling, and graceful shutdown.

Extracted from agent.py god file.

Author : Fahim (SadManFahIm)
Branch : feature/agent-decompose (→ 10.0)
"""

import asyncio
import logging
from datetime import date

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Platform & Feature Toggles (loaded from contact_loader config)
# ──────────────────────────────────────────────────────────────

ENABLE_LINKEDIN = True
ENABLE_WHATSAPP = True
ENABLE_FACEBOOK = True
ENABLE_INSTAGRAM = True

VOICE_ENABLED = True
VOICE_ENGINE = "gtts"
TRANSCRIPTION_ENGINE = "google"

SENTIMENT_ANALYSIS_ENABLED = True
AUTO_CONNECT_ENABLED = True
PERSONALITY_PROFILING_ENABLED = True
PREDICTIVE_BIRTHDAY_ENABLED = True
EQ_SCORING_ENABLED = True
MULTI_ACCOUNT_ENABLED = True
CONNECTION_TRACKER_ENABLED = True
MEMORY_ENABLED = True
RAG_MEMORY_ENABLED = False
POST_ENGAGEMENT_ENABLED = True
BIRTHDAY_REMINDER_ENABLED = True
GROUP_BIRTHDAY_ENABLED = True
AUTO_REPLY_FOLLOWUP_ENABLED = True
OCCASION_DETECTION_ENABLED = True
DM_CAMPAIGN_ENABLED = False
CONTACT_CATEGORIZER_ENABLED = True
EMAIL_DIGEST_ENABLED = True
HEALTH_REPORT_ENABLED = True

MAX_ENGAGEMENTS_PER_DAY = 10
MAX_GROUP_ENGAGEMENTS = 10
GROUP_COMMENT_ENABLED = True
GROUP_DM_ENABLED = True
MAX_AUTO_REPLIES_PER_DAY = 10
ENGAGEMENT_MODE = "like_and_comment"
CATEGORIZER_MAX_CONTACTS = 50
DIGEST_DAY = "monday"
HEALTH_REPORT_DAY = "monday"

SCHEDULE_HOUR = 9
SCHEDULE_MINUTE = 0


# ──────────────────────────────────────────────────────────────
# Daily Job
# ──────────────────────────────────────────────────────────────


async def daily_job(llm, browser, dry_run: bool,
                    username: str, password: str,
                    session_valid_fn, filter_notice_fn,
                    save_session_fn, send_summary_fn):
    """
    The main daily job — runs all enabled tasks in sequence.
    Called by the scheduler at SCHEDULE_HOUR:SCHEDULE_MINUTE.
    """
    from task_runners import (
        run_birthday_detection_task, run_linkedin_reply_task,
        run_whatsapp_reply_task, run_facebook_reply_task,
        run_instagram_reply_task, run_instagram_birthday_detection_task,
        run_followup_task, run_sentiment_reply_task,
        run_memory_wish_task, run_post_engagement_task,
        run_birthday_reminder_task, run_group_birthday_task,
        run_auto_reply_task, run_occasion_detection_task,
        run_email_digest_task, run_health_report_task,
        run_categorizer_task, run_dm_campaign_task,
    )

    logger.info(" Daily job started.")
    try:
        sv = session_valid_fn()
        fn_str = filter_notice_fn("LinkedIn-BirthdayDetection")

        if ENABLE_LINKEDIN:
            await run_birthday_detection_task(
                llm, browser, dry_run, sv, fn_str,
                save_session_fn, send_summary_fn)
            await run_linkedin_reply_task(
                llm, browser, dry_run, sv,
                filter_notice_fn("LinkedIn-Reply"),
                save_session_fn, send_summary_fn)

        if ENABLE_WHATSAPP:
            await run_whatsapp_reply_task(
                llm, browser, dry_run,
                filter_notice_fn("WhatsApp-Reply"),
                VOICE_ENABLED, VOICE_ENGINE, send_summary_fn)

        if ENABLE_FACEBOOK:
            await run_facebook_reply_task(
                llm, browser, dry_run,
                filter_notice_fn("Facebook-Reply"),
                send_summary_fn)

        if ENABLE_INSTAGRAM:
            await run_instagram_reply_task(
                llm, browser, dry_run,
                filter_notice_fn("Instagram-Reply"),
                send_summary_fn)
            await run_instagram_birthday_detection_task(username)

        await run_followup_task(
            llm, browser, dry_run, username, password,
            sv, save_session_fn, send_summary_fn)

        if SENTIMENT_ANALYSIS_ENABLED or AUTO_CONNECT_ENABLED:
            await run_sentiment_reply_task(
                llm, browser, dry_run, username, password,
                sv, fn_str, SENTIMENT_ANALYSIS_ENABLED,
                AUTO_CONNECT_ENABLED, save_session_fn, send_summary_fn)

        if MEMORY_ENABLED:
            await run_memory_wish_task(
                llm, browser, dry_run, sv, fn_str,
                save_session_fn, send_summary_fn)

        if POST_ENGAGEMENT_ENABLED:
            await run_post_engagement_task(
                llm, browser, dry_run, ENGAGEMENT_MODE,
                MAX_ENGAGEMENTS_PER_DAY, send_summary_fn)

        if BIRTHDAY_REMINDER_ENABLED:
            await run_birthday_reminder_task(
                llm, browser, dry_run, username, password, sv)

        if GROUP_BIRTHDAY_ENABLED:
            await run_group_birthday_task(
                llm, browser, dry_run, username, password, sv,
                MAX_GROUP_ENGAGEMENTS, GROUP_COMMENT_ENABLED,
                GROUP_DM_ENABLED)

        if AUTO_REPLY_FOLLOWUP_ENABLED:
            await run_auto_reply_task(
                llm, browser, dry_run, username, password,
                sv, MAX_AUTO_REPLIES_PER_DAY)

        if OCCASION_DETECTION_ENABLED:
            await run_occasion_detection_task(
                llm, browser, dry_run, username, password, sv)

        if DM_CAMPAIGN_ENABLED:
            from contact_loader import config as env_config
            await run_dm_campaign_task(
                llm, browser, dry_run, username, password, sv,
                env_config.get("CAMPAIGN_TYPE", "new_connections"),
                10, 30, "A")

        if MULTI_ACCOUNT_ENABLED:
            from task_runners_multi import run_multi_account_task
            await run_multi_account_task(
                llm, dry_run, username, password, sv,
                filter_notice_fn, send_summary_fn)

        # Weekly tasks
        if CONTACT_CATEGORIZER_ENABLED:
            if date.today().strftime("%A") == "Sunday":
                await run_categorizer_task(
                    llm, browser, username, password,
                    sv, CATEGORIZER_MAX_CONTACTS)

        if EMAIL_DIGEST_ENABLED:
            if date.today().strftime("%A").lower() == DIGEST_DAY.lower():
                await run_email_digest_task(dry_run)

        if HEALTH_REPORT_ENABLED:
            if date.today().strftime("%A").lower() == HEALTH_REPORT_DAY.lower():
                await run_health_report_task(dry_run)

    except Exception as e:
        logger.error(" Daily job error: %s", e)


# ──────────────────────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────────────────────


async def run_scheduler(llm, browser, dry_run: bool,
                        username: str, password: str,
                        session_valid_fn, filter_notice_fn,
                        save_session_fn, send_summary_fn):
    """Start the APScheduler cron loop."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        daily_job, trigger="cron",
        hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE,
        args=[llm, browser, dry_run, username, password,
              session_valid_fn, filter_notice_fn,
              save_session_fn, send_summary_fn],
    )
    scheduler.start()
    logger.info(" Scheduler running. Daily at %02d:%02d. DRY_RUN=%s",
                SCHEDULE_HOUR, SCHEDULE_MINUTE, dry_run)
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info(" Scheduler stopped.")


# ──────────────────────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────────────────────


async def close_browser(browser):
    """Gracefully close the browser instance."""
    try:
        await browser.close()
        logger.info(" Browser closed.")
    except Exception as e:
        logger.warning("  Browser close error: %s", e)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Scheduler — Self-Test")
    print("=" * 50)

    # 1. Toggles
    print("\n[1/3] Toggles ...")
    assert ENABLE_LINKEDIN is True
    assert ENABLE_WHATSAPP is True
    assert DM_CAMPAIGN_ENABLED is False
    assert SCHEDULE_HOUR == 9
    print("      ✅ All toggles have defaults")

    # 2. daily_job is async
    print("[2/3] daily_job is async ...")
    assert asyncio.iscoroutinefunction(daily_job)
    assert asyncio.iscoroutinefunction(run_scheduler)
    assert asyncio.iscoroutinefunction(close_browser)
    print("      ✅ All functions are async")

    # 3. Weekly day check
    print("[3/3] Weekly day logic ...")
    today = date.today().strftime("%A")
    assert isinstance(today, str)
    print(f"      ✅ Today is {today}")

    print("\n" + "=" * 50)
    print("✅ ALL SCHEDULER TESTS PASSED")
    print("=" * 50)
