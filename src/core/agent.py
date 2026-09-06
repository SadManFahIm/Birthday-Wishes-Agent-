"""
Birthday Wishes Agent — Main Orchestrator v10.0
=================================================
Thin entry point that wires together the decomposed modules:
  - contact_loader.py   → config, DB, session, browser, LLM
  - wish_templates.py   → templates, detection rules, prompts
  - task_runners.py     → all async task functions
  - scheduler.py        → daily job, cron scheduler, cleanup

Run:
  python agent.py                    # start scheduler
  python agent.py --self-test        # run module self-tests

Author : Fahim (SadManFahIm)
Branch : feature/agent-decompose (→ 10.0)
"""

import asyncio
import logging
import sys

# ──────────────────────────────────────────────────────────────
# 1. Logging
# ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 2. Core imports from decomposed modules
# ──────────────────────────────────────────────────────────────

from contact_loader import (                                     # noqa: E402
    config, USERNAME, PASSWORD, GITHUB_URL, DRY_RUN,
    WHITELIST, BLACKLIST, COOLDOWN_DAYS,
    DB_FILE, init_db, log_action, get_recent_contacts,
    is_allowed, filter_notice,
    SESSION_FILE, session_is_valid, save_session_timestamp,
    BROWSER_PROFILE_DIR, get_browser,
    AI_MODEL, SUPPORTED_MODELS, build_llm,
)

from wish_templates import (                                     # noqa: E402
    PERSONALIZED_REPLY_TEMPLATES, BIRTHDAY_WISH_TEMPLATES,
    WISH_DETECTION_RULES, dry_run_notice,
    build_linkedin_reply_task, build_birthday_detection_task,
)

from task_runners import run_with_retry                          # noqa: E402

# ──────────────────────────────────────────────────────────────
# 3. Notification stub
# ──────────────────────────────────────────────────────────────

try:
    from notifications import send_summary
except ImportError:
    def send_summary(*args, **kwargs):
        pass

# ──────────────────────────────────────────────────────────────
# 4. Table initialisation imports (same as original agent.py)
# ──────────────────────────────────────────────────────────────

from followup import init_followup_table                         # noqa: E402
from automation.auto_connect import init_connections_table       # noqa: E402
from ai.memory import init_memory_table                          # noqa: E402
from automation.post_engagement import init_engagement_table     # noqa: E402
from automation.birthday_reminder import init_reminder_table     # noqa: E402
from contacts.contact_notes import init_notes_table              # noqa: E402
from automation.group_birthday import init_group_birthday_table  # noqa: E402
from contacts.connection_tracker import (                        # noqa: E402
    init_tracker_table, sync_from_history,
)
from automation.auto_reply_followup import init_auto_reply_table  # noqa: E402
from contacts.relationship_health import init_health_table       # noqa: E402
from security.proxy_rotation import init_proxy_table             # noqa: E402
from detection.best_time_connect import init_activity_table      # noqa: E402
from automation.dm_campaign import init_campaign_table           # noqa: E402
from contacts.contact_categorizer import init_categorizer_table  # noqa: E402
from automation.personalized_connect import init_connect_request_table  # noqa: E402
from ai.ab_testing import init_ab_table                          # noqa: E402
from automation.auto_timezone_scheduler import init_scheduler_table  # noqa: E402
from ai.personality_profiling import init_personality_table       # noqa: E402
from ai.predictive_birthday import init_predicted_birthday_table  # noqa: E402
from ai.emotional_intelligence import init_eq_table              # noqa: E402
from automation.birthday_miss_tracker import init_miss_table     # noqa: E402
from automation.smart_followup import init_smart_followup_table  # noqa: E402
from contacts.decay_alert import init_decay_table                # noqa: E402
from platforms.twitter_birthday import init_twitter_table        # noqa: E402
from platforms.slack_birthday_bot import init_slack_table         # noqa: E402
from telegram_birthday_bot import init_telegram_birthday_table   # noqa: E402
from security.vpn_switch import init_vpn_table                   # noqa: E402
from notifications.discord_birthday_bot import init_discord_birthday_table  # noqa: E402
from multi_account.multi_account import (                        # noqa: E402
    init_accounts_table, register_account,
)
from ai.rag_memory import init_rag_memory, migrate_from_sqlite_memory  # noqa: E402

# ──────────────────────────────────────────────────────────────
# 5. Re-exports for backward compatibility
#    (any future module importing from agent.py still works)
# ──────────────────────────────────────────────────────────────

__all__ = [
    "config", "USERNAME", "PASSWORD", "GITHUB_URL", "DRY_RUN",
    "WHITELIST", "BLACKLIST", "COOLDOWN_DAYS",
    "DB_FILE", "init_db", "log_action", "get_recent_contacts",
    "is_allowed", "filter_notice",
    "session_is_valid", "save_session_timestamp",
    "AI_MODEL", "SUPPORTED_MODELS", "build_llm",
    "PERSONALIZED_REPLY_TEMPLATES", "BIRTHDAY_WISH_TEMPLATES",
    "WISH_DETECTION_RULES", "dry_run_notice",
    "build_linkedin_reply_task", "build_birthday_detection_task",
    "run_with_retry", "send_summary",
]

# ──────────────────────────────────────────────────────────────
# 6. Credential validation
# ──────────────────────────────────────────────────────────────

if not USERNAME or not PASSWORD:
    raise EnvironmentError(" USERNAME or PASSWORD missing in .env")

logger.info(" AI Model: %s (%s)", AI_MODEL, SUPPORTED_MODELS[AI_MODEL])

# ──────────────────────────────────────────────────────────────
# 7. Build LLM & Browser
# ──────────────────────────────────────────────────────────────

llm = build_llm()
browser = get_browser()

# ──────────────────────────────────────────────────────────────
# 8. Multi-account loader
# ──────────────────────────────────────────────────────────────

MAX_EXTRA_ACCOUNTS = 9
RAG_MEMORY_ENABLED = False
CONNECTION_TRACKER_ENABLED = True
MULTI_ACCOUNT_ENABLED = True


def _load_extra_accounts_from_env():
    """Load extra accounts from .env (ACCOUNT_2..ACCOUNT_10)."""
    for i in range(2, 2 + MAX_EXTRA_ACCOUNTS):
        label = config.get(f"ACCOUNT_{i}_LABEL")
        username = config.get(f"ACCOUNT_{i}_USERNAME")
        password = config.get(f"ACCOUNT_{i}_PASSWORD")
        if label and username and password:
            register_account(
                label=label, username=username,
                password=password, enabled=True, priority=i,
            )
            logger.info(" Loaded account from .env: [%s] %s",
                        label, username)


# ──────────────────────────────────────────────────────────────
# 9. Init & Main
# ──────────────────────────────────────────────────────────────


def _init_all_tables():
    """Initialise all database tables."""
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
    init_proxy_table()
    init_activity_table()
    init_campaign_table()
    init_categorizer_table()
    init_connect_request_table()
    init_ab_table()
    init_scheduler_table()
    init_personality_table()
    init_predicted_birthday_table()
    init_eq_table()
    init_miss_table()
    init_smart_followup_table()
    init_decay_table()
    init_twitter_table()
    init_slack_table()
    init_telegram_birthday_table()
    init_vpn_table()
    init_discord_birthday_table()
    init_accounts_table()

    if RAG_MEMORY_ENABLED:
        init_rag_memory()
        migrate_from_sqlite_memory()
    if CONNECTION_TRACKER_ENABLED:
        sync_from_history()
    if MULTI_ACCOUNT_ENABLED:
        _load_extra_accounts_from_env()


async def main():
    """Main entry point — init tables, start scheduler."""
    from scheduler import run_scheduler, close_browser

    _init_all_tables()

    try:
        await run_scheduler(
            llm, browser, DRY_RUN,
            USERNAME, PASSWORD,
            session_is_valid, filter_notice,
            save_session_timestamp, send_summary,
        )
    finally:
        await close_browser(browser)


# ──────────────────────────────────────────────────────────────
# 10. Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        print("Running decomposed module self-tests...")
        import subprocess
        modules = [
            "contact_loader.py", "wish_templates.py",
            "task_runners.py", "scheduler.py",
        ]
        for m in modules:
            print(f"\n{'='*50}")
            print(f"Testing: {m}")
            print("=" * 50)
            subprocess.run([sys.executable, m])
    else:
        asyncio.run(main())
