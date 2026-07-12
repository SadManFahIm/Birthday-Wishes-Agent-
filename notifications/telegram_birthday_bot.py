"""
telegram_birthday_bot.py
------------------------
Telegram Birthday Wishes Bot for Birthday Wishes Agent.

Sends personalized birthday wishes directly via Telegram
to contacts who are on Telegram.

Features:
  - Send birthday wishes to individual Telegram users
  - Post birthday announcements in Telegram groups/channels
  - AI-generated personalized wishes
  - Supports text, emoji, and formatted messages
  - Logs all wishes to SQLite

.env setup:
  TELEGRAM_BOT_TOKEN=xxxxxxxxxxx
  TELEGRAM_CHAT_ID=your_chat_id        (for personal notifications)
  TELEGRAM_GROUP_ID=-100xxxxxxxxx      (for group announcements)
  TELEGRAM_BIRTHDAY_ENABLED=true

Usage:
    from telegram_birthday_bot import (
        init_telegram_birthday_table,
        send_telegram_birthday_wish,
        run_telegram_birthday_bot,
    )

    await run_telegram_birthday_bot(contacts=["John Smith"], dry_run=True)
"""

import logging
import random
import sqlite3
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Birthday wish templates for Telegram
WISH_TEMPLATES = [
    "Happy Birthday {name}! Hope your day is absolutely amazing!",
    "Wishing you a fantastic birthday {name}! Hope this year brings great things!",
    "Happy Birthday {name}! You deserve all the celebrations today!",
    "Many happy returns {name}! Hope your special day is filled with joy!",
    "Happy Birthday {name}! Another year wiser and better. Enjoy your day!",
]

# Group announcement templates
GROUP_TEMPLATES = [
    "Hey everyone! Let us wish {name} a very Happy Birthday today! "
    "Hope your day is amazing {name}!",
    "It is {name}'s birthday today! Wishing you all the best! "
    "Have a wonderful day!",
    "Happy Birthday to {name}! Hope this year brings great success and happiness!",
]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_telegram_birthday_table():
    """Create Telegram birthday wish tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telegram_birthday_wishes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                chat_id      TEXT    NOT NULL,
                message      TEXT    NOT NULL,
                wish_type    TEXT    DEFAULT 'direct',
                sent         INTEGER DEFAULT 0,
                dry_run      INTEGER DEFAULT 1,
                wish_date    TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Telegram birthday table ready.")


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def load_config() -> dict:
    """Load Telegram config from .env."""
    from dotenv import dotenv_values
    config = dotenv_values(".env")
    return {
        "bot_token": config.get("TELEGRAM_BOT_TOKEN", ""),
        "chat_id":   config.get("TELEGRAM_CHAT_ID", ""),
        "group_id":  config.get("TELEGRAM_GROUP_ID", ""),
        "enabled":   config.get("TELEGRAM_BIRTHDAY_ENABLED", "false").lower() == "true",
    }


def already_wished_today(contact: str) -> bool:
    """Check if already sent a Telegram wish today."""
    if not DB_FILE.exists():
        return False
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM telegram_birthday_wishes
            WHERE LOWER(contact) = LOWER(?) AND wish_date = ? AND dry_run = 0
        """, (contact, date.today().isoformat())).fetchone()
    return (row[0] or 0) > 0


def get_wish_message(contact_name: str) -> str:
    """Get a personalized birthday wish."""
    first_name = contact_name.split()[0].capitalize()
    return random.choice(WISH_TEMPLATES).format(name=first_name)


def get_group_message(contact_name: str) -> str:
    """Get a group birthday announcement."""
    first_name = contact_name.split()[0].capitalize()
    return random.choice(GROUP_TEMPLATES).format(name=first_name)


def log_wish(
    contact: str,
    chat_id: str,
    message: str,
    wish_type: str = "direct",
    dry_run: bool = True,
):
    """Log a Telegram birthday wish."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO telegram_birthday_wishes
            (contact, chat_id, message, wish_type, sent, dry_run, wish_date, created_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """, (contact, chat_id, message, wish_type, int(dry_run),
              date.today().isoformat(), datetime.now().isoformat()))
        conn.commit()
    logger.info("Telegram wish logged: %s (%s)", contact, wish_type)


# ------------------------------------------------------------
# SEND FUNCTIONS
# ------------------------------------------------------------

async def send_telegram_message(
    chat_id: str,
    message: str,
    bot_token: str,
    dry_run: bool = True,
    parse_mode: str = "HTML",
) -> bool:
    """
    Send a message via Telegram Bot API.

    Args:
        chat_id   : Telegram chat/user/group ID
        message   : Message text
        bot_token : Bot token from BotFather
        dry_run   : If True, log only
        parse_mode: HTML or Markdown

    Returns:
        True if sent successfully.
    """
    if dry_run:
        logger.info("[DRY RUN] Would send to %s: %s", chat_id, message[:60])
        return True

    try:
        import requests
        url      = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = requests.post(url, json={
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": parse_mode,
        }, timeout=10)

        if response.status_code == 200:
            logger.info("Telegram message sent to %s.", chat_id)
            return True
        else:
            logger.error("Telegram API error: %s", response.text[:100])
            return False

    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return False


async def send_telegram_birthday_wish(
    contact_name: str,
    chat_id: str,
    bot_token: str,
    wish_text: str = "",
    dry_run: bool = True,
) -> bool:
    """
    Send a birthday wish to a specific Telegram user/chat.

    Args:
        contact_name : Contact's name
        chat_id      : Their Telegram chat ID
        bot_token    : Bot token
        wish_text    : Custom wish (auto-generated if empty)
        dry_run      : If True, log only

    Returns:
        True if sent successfully.
    """
    if already_wished_today(contact_name) and not dry_run:
        logger.info("Already wished %s on Telegram today.", contact_name)
        return False

    if not wish_text:
        wish_text = get_wish_message(contact_name)

    # Format with HTML for Telegram
    formatted = f"<b>{wish_text}</b>"

    success = await send_telegram_message(
        chat_id=chat_id,
        message=formatted,
        bot_token=bot_token,
        dry_run=dry_run,
    )

    if success:
        log_wish(contact_name, chat_id, wish_text, "direct", dry_run)

    return success


async def send_group_birthday_announcement(
    contact_name: str,
    group_id: str,
    bot_token: str,
    dry_run: bool = True,
) -> bool:
    """
    Post a birthday announcement in a Telegram group/channel.

    Args:
        contact_name : Birthday person's name
        group_id     : Telegram group/channel ID
        bot_token    : Bot token
        dry_run      : If True, log only

    Returns:
        True if posted successfully.
    """
    message = get_group_message(contact_name)

    success = await send_telegram_message(
        chat_id=group_id,
        message=message,
        bot_token=bot_token,
        dry_run=dry_run,
    )

    if success:
        log_wish(contact_name, group_id, message, "group", dry_run)

    return success


# ------------------------------------------------------------
# AI-GENERATED WISH
# ------------------------------------------------------------

async def send_ai_telegram_wish(
    llm,
    contact_name: str,
    chat_id: str,
    bot_token: str,
    profile_info: dict | None = None,
    dry_run: bool = True,
) -> bool:
    """
    Generate an AI-personalized wish and send via Telegram.

    Args:
        llm          : LangChain LLM instance
        contact_name : Contact's name
        chat_id      : Telegram chat ID
        bot_token    : Bot token
        profile_info : Contact profile (job, company etc.)
        dry_run      : If True, log only
    """
    from langchain_core.messages import HumanMessage

    profile   = profile_info or {}
    job_title = profile.get("job_title", "")
    company   = profile.get("company", "")
    first     = contact_name.split()[0].capitalize()

    context = ""
    if job_title and company:
        context = f"They work as {job_title} at {company}."
    elif job_title:
        context = f"They work as {job_title}."

    prompt = f"""Write a birthday wish for {first}.

{context}
Style: warm, personal, 2 sentences, 1-2 emoji
Start with: Happy Birthday {first}!
Reply with ONLY the wish text.
"""

    try:
        response  = await llm.ainvoke([HumanMessage(content=prompt)])
        wish_text = response.content.strip().strip('"').strip("'")
        logger.info("AI Telegram wish for %s: %s", first, wish_text[:60])

        return await send_telegram_birthday_wish(
            contact_name=contact_name,
            chat_id=chat_id,
            bot_token=bot_token,
            wish_text=wish_text,
            dry_run=dry_run,
        )

    except Exception as e:
        logger.error("AI Telegram wish failed: %s", e)
        # Fallback to template
        return await send_telegram_birthday_wish(
            contact_name=contact_name,
            chat_id=chat_id,
            bot_token=bot_token,
            dry_run=dry_run,
        )


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_telegram_report() -> str:
    """Build Telegram birthday wish report."""
    if not DB_FILE.exists():
        return "No Telegram wish data yet."

    cutoff = (date.today().replace(day=1)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT contact, wish_type, message, wish_date, dry_run
            FROM   telegram_birthday_wishes
            WHERE  wish_date >= ?
            ORDER  BY wish_date DESC
        """, (cutoff,)).fetchall()

    if not rows:
        return "No Telegram wishes sent this month."

    direct = [r for r in rows if r[1] == "direct" and not r[4]]
    group  = [r for r in rows if r[1] == "group"  and not r[4]]

    lines = [
        "Telegram Birthday Wishes Report",
        "-" * 50,
        f"  Direct wishes : {len(direct)}",
        f"  Group posts   : {len(group)}",
        "-" * 50,
        "",
    ]

    for r in rows[:10]:
        dry  = "[DRY]" if r[4] else ""
        lines.append(f"  {dry} {r[0]} ({r[1]}) — {r[3]}")
        lines.append(f"    {r[2][:60]}...")
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_telegram_birthday_bot(
    contacts: list[str],
    llm=None,
    chat_ids: dict | None = None,
    dry_run: bool = True,
    use_ai: bool = False,
    announce_in_group: bool = False,
) -> dict:
    """
    Main runner. Call from agent.py daily.

    Args:
        contacts         : List of contact names with birthdays today
        llm              : LangChain LLM (for AI wishes)
        chat_ids         : Dict mapping contact name -> Telegram chat_id
                           If not provided, sends to TELEGRAM_CHAT_ID as notification
        dry_run          : If True, log only
        use_ai           : Use AI to generate personalized wishes
        announce_in_group: Also post in group/channel

    Returns:
        Dict with summary stats.
    """
    logger.info("=== Telegram Birthday Bot === [DRY RUN: %s]", dry_run)

    config = load_config()
    if not config["bot_token"]:
        logger.error("TELEGRAM_BOT_TOKEN missing in .env")
        return {"error": "No bot token", "sent": 0}

    chat_ids  = chat_ids or {}
    sent      = 0
    announced = 0

    for contact in contacts:
        # Get chat_id for this contact
        chat_id = chat_ids.get(contact, config["chat_id"])

        if not chat_id:
            logger.warning("No chat_id for %s. Skipping.", contact)
            continue

        # Send direct wish
        if use_ai and llm:
            success = await send_ai_telegram_wish(
                llm=llm,
                contact_name=contact,
                chat_id=chat_id,
                bot_token=config["bot_token"],
                dry_run=dry_run,
            )
        else:
            success = await send_telegram_birthday_wish(
                contact_name=contact,
                chat_id=chat_id,
                bot_token=config["bot_token"],
                dry_run=dry_run,
            )

        if success:
            sent += 1

        # Group announcement
        if announce_in_group and config["group_id"]:
            ok = await send_group_birthday_announcement(
                contact_name=contact,
                group_id=config["group_id"],
                bot_token=config["bot_token"],
                dry_run=dry_run,
            )
            if ok:
                announced += 1

    report = build_telegram_report()
    logger.info("Telegram bot done: %d sent | %d announced.", sent, announced)

    return {
        "sent":      sent,
        "announced": announced,
        "report":    report,
    }
