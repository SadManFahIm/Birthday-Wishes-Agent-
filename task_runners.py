"""
Task Runners — Birthday Wishes Agent v10.0
============================================
All async task runner functions for every platform and feature.

Each function is a self-contained task that can be triggered
from the scheduler, CLI, or command center.

Extracted from agent.py god file.

Author : Fahim (SadManFahIm)
Branch : feature/agent-decompose (→ 10.0)
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Retry helper
# ──────────────────────────────────────────────────────────────


async def run_with_retry(coro_factory, task_name: str,
                         retries: int = 3, delay: int = 5):
    """Run an async coroutine with retry logic."""
    for attempt in range(1, retries + 1):
        try:
            logger.info(" [%s] Attempt %d/%d", task_name, attempt, retries)
            result = await coro_factory()
            logger.info(" [%s] Done.", task_name)
            return result
        except Exception as e:
            logger.error(" [%s] Attempt %d failed: %s",
                         task_name, attempt, e)
            if attempt < retries:
                await asyncio.sleep(delay)
            else:
                logger.critical(" [%s] All attempts failed.", task_name)
                raise


# ──────────────────────────────────────────────────────────────
# GitHub
# ──────────────────────────────────────────────────────────────


async def run_github_task(llm, browser, github_url: str):
    """Check GitHub follower count."""
    logger.info("=== GitHub Follower Check ===")
    from browser_use import Agent
    task = f"Open browser, go to {github_url} and tell me how many followers they have."

    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "GitHub")
    logger.info("GitHub: %s", result)
    return result


# ──────────────────────────────────────────────────────────────
# LinkedIn
# ──────────────────────────────────────────────────────────────


async def run_linkedin_reply_task(llm, browser, dry_run: bool,
                                  session_valid: bool,
                                  filter_notice_str: str,
                                  save_session_fn, send_summary_fn):
    """Reply to LinkedIn birthday wishes."""
    from browser_use import Agent
    from wish_templates import build_linkedin_reply_task
    from security.two_factor_auth import get_2fa_instructions

    logger.info("=== LinkedIn Reply === [DRY RUN: %s]", dry_run)
    login_instr = get_2fa_instructions(session_valid)
    task = build_linkedin_reply_task(
        session_valid, dry_run, filter_notice_str, login_instr)

    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "LinkedIn-Reply")
    save_session_fn()
    send_summary_fn("LinkedIn - Reply to Wishes", [], 0, dry_run)
    return result


async def run_birthday_detection_task(llm, browser, dry_run: bool,
                                      session_valid: bool,
                                      filter_notice_str: str,
                                      save_session_fn, send_summary_fn):
    """Detect LinkedIn birthdays and send wishes."""
    from browser_use import Agent
    from wish_templates import build_birthday_detection_task
    from security.two_factor_auth import get_2fa_instructions

    logger.info("=== LinkedIn Birthday Detection === [DRY RUN: %s]", dry_run)
    login_instr = get_2fa_instructions(session_valid)
    task = build_birthday_detection_task(
        session_valid, dry_run, filter_notice_str, login_instr)

    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "LinkedIn-BirthdayDetection")
    save_session_fn()
    send_summary_fn("LinkedIn - Birthday Detection", [], 0, dry_run)
    return result


async def run_ai_custom_wish_task(llm, browser, dry_run: bool,
                                  username: str, password: str,
                                  session_valid: bool,
                                  filter_notice_str: str,
                                  save_session_fn, send_summary_fn):
    """Send AI-generated custom wishes on LinkedIn."""
    from platforms import run_linkedin_birthday_with_custom_wish
    from wish_templates import WISH_DETECTION_RULES

    logger.info("=== LinkedIn: AI Custom Wishes === [DRY RUN: %s]", dry_run)

    async def _run():
        return await run_linkedin_birthday_with_custom_wish(
            llm=llm, browser=browser, dry_run=dry_run,
            username=username, password=password,
            already_logged_in=session_valid,
            filter_notice=filter_notice_str,
            wish_detection_rules=WISH_DETECTION_RULES,
        )

    result = await run_with_retry(_run, "LinkedIn-AIWish")
    save_session_fn()
    send_summary_fn("LinkedIn - AI Custom Wishes", [], 0, dry_run)
    return result


async def run_memory_wish_task(llm, browser, dry_run: bool,
                               session_valid: bool,
                               filter_notice_str: str,
                               save_session_fn, send_summary_fn):
    """Send memory-aware wishes on LinkedIn."""
    from browser_use import Agent
    from wish_templates import dry_run_notice

    logger.info("=== LinkedIn: Memory-Aware Wishes === [DRY RUN: %s]", dry_run)
    task = f"""
  Open the browser.
  You are already logged into LinkedIn. Skip login.
  {dry_run_notice(dry_run)}
  {filter_notice_str}

  GOAL: Find contacts with birthdays TODAY and send memory-aware wishes.

  For each birthday contact:
    a) Apply contact filters.
    b) Visit their LinkedIn profile and note:
       - First name, job title, company, recent posts or achievements
    c) Generate a wish that references last year's context if available.
    d) Send the wish (or log if DRY RUN).

  Stop after 20 contacts. TODAY only.
  Summary: wished (names + memory used Y/N), skipped (count+reason).
"""

    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "LinkedIn-MemoryWish")
    save_session_fn()
    send_summary_fn("LinkedIn - Memory-Aware Wishes", [], 0, dry_run)
    return result


async def run_sentiment_reply_task(llm, browser, dry_run: bool,
                                   username: str, password: str,
                                   session_valid: bool,
                                   filter_notice_str: str,
                                   sentiment_enabled: bool,
                                   auto_connect_enabled: bool,
                                   save_session_fn, send_summary_fn):
    """Sentiment-aware reply with optional auto-connect."""
    from browser_use import Agent
    from wish_templates import build_linkedin_reply_task
    from security.two_factor_auth import get_2fa_instructions

    logger.info("=== LinkedIn: Sentiment-Aware Reply === [DRY RUN: %s]", dry_run)
    login_instr = get_2fa_instructions(session_valid)
    task = build_linkedin_reply_task(
        session_valid, dry_run, filter_notice_str, login_instr)

    additions = ""
    if sentiment_enabled:
        from ai.sentiment import build_sentiment_instructions
        additions += build_sentiment_instructions()
    if auto_connect_enabled:
        from automation.auto_connect import build_auto_connect_task
        additions += build_auto_connect_task(
            username=username, password=password,
            already_logged_in=session_valid, dry_run=dry_run)

    if additions:
        task += f"\n  ADDITIONAL INSTRUCTIONS:\n  {additions}\n"

    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "LinkedIn-SentimentReply")
    save_session_fn()
    send_summary_fn("LinkedIn - Sentiment Reply + Auto Connect", [], 0, dry_run)
    return result


# ──────────────────────────────────────────────────────────────
# Other Platforms
# ──────────────────────────────────────────────────────────────


async def run_whatsapp_reply_task(llm, browser, dry_run: bool,
                                  filter_notice_str: str,
                                  voice_enabled: bool,
                                  voice_engine: str,
                                  send_summary_fn):
    """Reply to WhatsApp birthday wishes."""
    from platforms import run_whatsapp_task
    from wish_templates import (WISH_DETECTION_RULES,
                                PERSONALIZED_REPLY_TEMPLATES)

    logger.info("=== WhatsApp Reply === [DRY RUN: %s | VOICE: %s]",
                dry_run, voice_enabled)

    async def _run():
        return await run_whatsapp_task(
            llm=llm, browser=browser, dry_run=dry_run,
            wish_detection_rules=WISH_DETECTION_RULES,
            reply_templates=PERSONALIZED_REPLY_TEMPLATES,
            filter_notice=filter_notice_str,
            voice_enabled=voice_enabled, voice_engine=voice_engine,
        )

    result = await run_with_retry(_run, "WhatsApp-Reply")
    send_summary_fn("WhatsApp - Reply to Wishes", [], 0, dry_run)
    return result


async def run_facebook_reply_task(llm, browser, dry_run: bool,
                                  filter_notice_str: str,
                                  send_summary_fn):
    """Reply to Facebook birthday wishes."""
    from platforms import run_facebook_task
    from wish_templates import (WISH_DETECTION_RULES,
                                PERSONALIZED_REPLY_TEMPLATES)

    logger.info("=== Facebook Messenger Reply === [DRY RUN: %s]", dry_run)

    async def _run():
        return await run_facebook_task(
            llm=llm, browser=browser, dry_run=dry_run,
            wish_detection_rules=WISH_DETECTION_RULES,
            reply_templates=PERSONALIZED_REPLY_TEMPLATES,
            filter_notice=filter_notice_str,
        )

    result = await run_with_retry(_run, "Facebook-Reply")
    send_summary_fn("Facebook - Reply to Wishes", [], 0, dry_run)
    return result


async def run_instagram_reply_task(llm, browser, dry_run: bool,
                                   filter_notice_str: str,
                                   send_summary_fn):
    """Reply to Instagram DM birthday wishes."""
    from platforms import run_instagram_task
    from wish_templates import (WISH_DETECTION_RULES,
                                PERSONALIZED_REPLY_TEMPLATES)

    logger.info("=== Instagram DM Reply === [DRY RUN: %s]", dry_run)

    async def _run():
        return await run_instagram_task(
            llm=llm, browser=browser, dry_run=dry_run,
            wish_detection_rules=WISH_DETECTION_RULES,
            reply_templates=PERSONALIZED_REPLY_TEMPLATES,
            filter_notice=filter_notice_str,
        )

    result = await run_with_retry(_run, "Instagram-Reply")
    send_summary_fn("Instagram - Reply to Wishes", [], 0, dry_run)
    return result


async def run_instagram_birthday_detection_task(username: str):
    """Detect birthdays from Instagram posts."""
    from platforms.instagram_birthday_detector import InstagramBirthdayDetector
    from platforms.instagram_birthdays import save_detected_birthday

    logger.info("=== Instagram Birthday Detection ===")
    detector = InstagramBirthdayDetector(username)
    detector.load_session(username)
    target_accounts = ["instagram"]
    total_detected = 0

    for account in target_accounts:
        logger.info("Scanning account: %s", account)
        results = detector.detect_birthday_posts(
            target_username=account, limit=10)
        for post in results:
            save_detected_birthday(post)
            total_detected += 1
            logger.info("Birthday detected: %s", post["post_url"])

    logger.info("Instagram birthday detection completed. Total: %d",
                total_detected)
    return total_detected


# ──────────────────────────────────────────────────────────────
# Automation Tasks
# ──────────────────────────────────────────────────────────────


async def run_followup_task(llm, browser, dry_run: bool,
                            username: str, password: str,
                            session_valid: bool,
                            save_session_fn, send_summary_fn):
    """Send follow-up messages for pending items."""
    from followup import (get_pending_followups, build_followup_task,
                          mark_followup_sent)
    from browser_use import Agent

    logger.info("=== Follow-up Messages === [DRY RUN: %s]", dry_run)
    pending = get_pending_followups()
    if not pending:
        logger.info(" No follow-ups due today.")
        return
    task = build_followup_task(
        pending=pending, dry_run=dry_run,
        username=username, password=password,
        already_logged_in=session_valid,
    )

    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "FollowUp")
    save_session_fn()
    if not dry_run:
        for item in pending:
            mark_followup_sent(item["id"])
    send_summary_fn("Follow-up Messages",
                     [p["contact"] for p in pending], 0, dry_run)
    return result


async def run_calendar_export(llm, browser, username: str,
                              password: str, session_valid: bool):
    """Export birthday calendar to .ics file."""
    from calendar_export import export_birthday_calendar

    logger.info("=== Birthday Calendar Export ===")
    path = await export_birthday_calendar(
        llm=llm, browser=browser, username=username,
        password=password, already_logged_in=session_valid,
    )
    if path:
        logger.info(" Calendar exported to: %s", path)
    return path


async def run_email_digest_task(dry_run: bool):
    """Send weekly email digest."""
    from notifications.email_digest import send_weekly_digest

    logger.info("=== Weekly Email Digest === [DRY RUN: %s]", dry_run)
    data = await send_weekly_digest(dry_run=dry_run)
    logger.info(
        " Digest: %d actions | %d upcoming | %d fading",
        data["wishes"]["total"],
        len(data["upcoming_birthdays"]),
        len(data["fading_connections"]),
    )
    return data


async def run_post_engagement_task(llm, browser, dry_run: bool,
                                   engagement_mode: str,
                                   max_engagements: int,
                                   send_summary_fn):
    """Engage with LinkedIn posts of birthday contacts."""
    from automation.post_engagement import run_post_engagement

    logger.info("=== LinkedIn Post Engagement === [DRY RUN: %s | MODE: %s]",
                dry_run, engagement_mode)
    sample_contacts = [
        {"name": "Birthday Contact", "profile_url": "",
         "relationship": "colleague"}
    ]
    result = await run_post_engagement(
        llm=llm, browser=browser, birthday_contacts=sample_contacts,
        dry_run=dry_run, engagement_mode=engagement_mode,
        max_engagements=max_engagements,
    )
    send_summary_fn("LinkedIn - Post Engagement", [], 0, dry_run)
    return result


async def run_birthday_reminder_task(llm, browser, dry_run: bool,
                                     username: str, password: str,
                                     session_valid: bool):
    """Send birthday reminder emails."""
    from automation.birthday_reminder import run_birthday_reminder

    logger.info("=== Birthday Reminder Email === [DRY RUN: %s]", dry_run)
    await run_birthday_reminder(
        llm=llm, browser=browser, username=username,
        password=password, already_logged_in=session_valid,
        dry_run=dry_run,
    )


async def run_group_birthday_task(llm, browser, dry_run: bool,
                                  username: str, password: str,
                                  session_valid: bool,
                                  max_engagements: int,
                                  comment_enabled: bool,
                                  dm_enabled: bool):
    """Detect and engage with group birthdays."""
    from automation.group_birthday import run_group_birthday_detection

    logger.info("=== Group Birthday Detection === [DRY RUN: %s]", dry_run)
    await run_group_birthday_detection(
        llm=llm, browser=browser, username=username,
        password=password, already_logged_in=session_valid,
        dry_run=dry_run, max_engagements=max_engagements,
        comment_enabled=comment_enabled, dm_enabled=dm_enabled,
    )


async def run_auto_reply_task(llm, browser, dry_run: bool,
                              username: str, password: str,
                              session_valid: bool,
                              max_replies: int):
    """Auto-reply to follow-up responses."""
    from automation.auto_reply_followup import run_auto_reply_followup

    logger.info("=== Auto Reply to Follow-up === [DRY RUN: %s]", dry_run)
    await run_auto_reply_followup(
        llm=llm, browser=browser, username=username,
        password=password, already_logged_in=session_valid,
        dry_run=dry_run, max_replies=max_replies,
    )


async def run_occasion_detection_task(llm, browser, dry_run: bool,
                                      username: str, password: str,
                                      session_valid: bool):
    """Detect and congratulate life events."""
    from ai.occasion_detection import run_occasion_detection

    logger.info("=== Occasion Detection === [DRY RUN: %s]", dry_run)
    await run_occasion_detection(
        llm=llm, browser=browser, username=username,
        password=password, already_logged_in=session_valid,
        dry_run=dry_run,
    )


async def run_health_report_task(dry_run: bool):
    """Generate weekly health report."""
    from contacts.relationship_health import run_relationship_health_report

    logger.info("=== Weekly Health Report === [DRY RUN: %s]", dry_run)
    report = await run_relationship_health_report(dry_run=dry_run)
    logger.info(" Health report: %d contacts | Avg: %.1f",
                report.get("total_contacts", 0),
                report.get("average_score", 0))
    return report


async def run_voice_to_text_reply_task(llm, browser, dry_run: bool,
                                       username: str, password: str,
                                       session_valid: bool,
                                       transcription_engine: str,
                                       filter_notice_str: str,
                                       send_summary_fn):
    """Transcribe and reply to voice messages."""
    from notifications.voice_to_text import run_voice_reply_task
    from wish_templates import (WISH_DETECTION_RULES,
                                PERSONALIZED_REPLY_TEMPLATES)

    logger.info("=== Voice-to-Text Reply === [DRY RUN: %s | ENGINE: %s]",
                dry_run, transcription_engine)
    result = await run_voice_reply_task(
        llm=llm, browser=browser, already_logged_in=session_valid,
        dry_run=dry_run, username=username, password=password,
        transcription_engine=transcription_engine,
        wish_detection_rules=WISH_DETECTION_RULES,
        reply_templates=PERSONALIZED_REPLY_TEMPLATES,
        filter_notice=filter_notice_str,
    )
    send_summary_fn("WhatsApp - Voice-to-Text Reply", [], 0, dry_run)
    return result


async def run_rag_wish_task(llm, browser, session_valid: bool,
                            filter_notice_str: str,
                            save_session_fn, send_summary_fn,
                            dry_run: bool):
    """Send RAG-enhanced birthday wishes."""
    from browser_use import Agent
    from wish_templates import build_birthday_detection_task

    logger.info("=== RAG Birthday Wishes === [DRY RUN: %s]", dry_run)
    task = build_birthday_detection_task(session_valid) + """
  ADDITIONAL: Use the RAG memory system to enrich each wish.
"""

    async def _run():
        return await Agent(task=task, llm=llm, browser=browser).run()

    result = await run_with_retry(_run, "RAG-BirthdayWish")
    save_session_fn()
    send_summary_fn("RAG Birthday Wishes", [], 0, dry_run)
    return result


async def run_dm_campaign_task(llm, browser, dry_run: bool,
                               username: str, password: str,
                               session_valid: bool,
                               campaign_type: str, max_dms: int,
                               cooldown_days: int, variant: str):
    """Run LinkedIn DM campaign."""
    from automation.dm_campaign import run_dm_campaign, get_campaign_stats

    logger.info("=== LinkedIn DM Campaign: %s === [DRY RUN: %s]",
                campaign_type.upper(), dry_run)
    result = await run_dm_campaign(
        llm=llm, browser=browser, campaign_type=campaign_type,
        username=username, password=password,
        already_logged_in=session_valid, dry_run=dry_run,
        max_dms=max_dms, cooldown_days=cooldown_days, variant=variant,
    )
    stats = get_campaign_stats()
    logger.info(" Campaign stats: %d sent | %.1f%% reply rate",
                stats.get("total_sent", 0), stats.get("reply_rate", 0))
    return result


async def run_categorizer_task(llm, browser, username: str,
                               password: str, session_valid: bool,
                               max_contacts: int):
    """Categorize contacts by industry and seniority."""
    from contacts.contact_categorizer import (run_contact_categorizer,
                                              get_category_stats)

    logger.info("=== Contact Categorizer === [MAX: %d]", max_contacts)
    count = await run_contact_categorizer(
        llm=llm, browser=browser, username=username,
        password=password, already_logged_in=session_valid,
        max_contacts=max_contacts,
    )
    stats = get_category_stats()
    logger.info("  Categorized %d contacts | Industries: %s",
                count, list(stats.get("by_industry", {}).keys())[:3])
    return count


async def run_personality_task(llm, browser, username: str,
                               password: str, session_valid: bool,
                               contacts: list = None):
    """Analyze contact personalities."""
    from ai.personality_profiling import analyze_personality

    logger.info("=== Personality Profiling ===")
    if not contacts:
        logger.info(" No contacts provided for personality analysis.")
        return []
    results = []
    for c in contacts:
        profile = await analyze_personality(
            llm=llm, browser=browser,
            contact=c.get("name", ""),
            profile_url=c.get("profile_url", ""),
            already_logged_in=session_valid,
            username=username, password=password,
        )
        if profile:
            results.append({"contact": c.get("name"), "profile": profile})
            logger.info(" %s -> %s (%s)",
                        c.get("name"),
                        profile.get("mbti_type", "?"),
                        profile.get("communication_style", "?"))
    return results


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Task Runners — Self-Test")
    print("=" * 50)

    # 1. run_with_retry
    print("\n[1/2] run_with_retry ...")
    call_count = 0

    async def _test_retry():
        global call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("Simulated failure")
        return "success"

    result = asyncio.run(
        run_with_retry(lambda: _test_retry(), "test", retries=3, delay=0))
    assert result == "success"
    assert call_count == 2
    print("      ✅ Retry succeeded on attempt 2")

    # 2. All task functions are callable
    print("[2/2] Task functions exist ...")
    task_fns = [
        run_github_task, run_linkedin_reply_task,
        run_birthday_detection_task, run_ai_custom_wish_task,
        run_whatsapp_reply_task, run_facebook_reply_task,
        run_instagram_reply_task, run_followup_task,
        run_email_digest_task, run_post_engagement_task,
        run_birthday_reminder_task, run_group_birthday_task,
        run_auto_reply_task, run_occasion_detection_task,
        run_health_report_task, run_dm_campaign_task,
        run_categorizer_task, run_memory_wish_task,
        run_sentiment_reply_task, run_rag_wish_task,
        run_voice_to_text_reply_task, run_personality_task,
        run_instagram_birthday_detection_task,
        run_calendar_export,
    ]
    for fn in task_fns:
        assert callable(fn), f"{fn.__name__} not callable"
    print(f"      ✅ {len(task_fns)} task functions verified")

    print("\n" + "=" * 50)
    print("✅ ALL TASK RUNNER TESTS PASSED")
    print("=" * 50)
