"""
slack_birthday_bot.py
---------------------
Slack Workspace Birthday Bot for Birthday Wishes Agent.

Automatically detects birthdays of Slack workspace members
and sends personalized birthday wishes in DM or a birthday channel.

How it works:
  1. Connects to Slack workspace using Bot Token
  2. Reads user profiles to find birthdays (if set)
  3. Checks which users have birthdays today
  4. Sends personalized DM or posts in a birthday channel
  5. Logs all actions to SQLite

.env setup:
  SLACK_BOT_TOKEN=xoxb-...
  SLACK_BIRTHDAY_CHANNEL=#birthdays   (optional, for channel posts)

Usage:
    from slack_birthday_bot import (
        init_slack_table,
        run_slack_birthday_bot,
        get_slack_birthday_users,
    )

    await run_slack_birthday_bot(dry_run=True)
"""

import logging
import sqlite3
import random
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Birthday wish templates for Slack
DM_TEMPLATES = [
    "Happy Birthday {name}! Hope your day is absolutely amazing! ",
    "Wishing you a fantastic birthday {name}! Hope this year brings great things! ",
    "Happy Birthday {name}! You deserve all the celebrations today! ",
    "Many happy returns {name}! Hope your special day is filled with joy! ",
]

CHANNEL_TEMPLATES = [
    "Hey everyone! Let's wish {name} a very Happy Birthday today! "
    "Hope your day is amazing {mention}! ",
    "It's {name}'s birthday today! Wishing you all the best {mention}! "
    "Have a wonderful day! ",
    "Happy Birthday to our amazing {name} {mention}! "
    "Hope your day is as awesome as you are! ",
]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_slack_table():
    """Create Slack birthday tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS slack_birthday_wishes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                slack_user   TEXT    NOT NULL,
                display_name TEXT,
                wish_type    TEXT    NOT NULL,
                message      TEXT,
                channel      TEXT,
                dry_run      INTEGER DEFAULT 1,
                wish_date    TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Slack birthday table ready.")


# ------------------------------------------------------------
# SLACK CLIENT
# ------------------------------------------------------------

def get_slack_client():
    """Build Slack WebClient from .env credentials."""
    try:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError
        from dotenv import dotenv_values

        config = dotenv_values(".env")
        token = config.get("SLACK_BOT_TOKEN", "")

        if not token:
            logger.error("SLACK_BOT_TOKEN missing in .env")
            return None, None

        client = WebClient(token=token)
        logger.info("Slack client initialized.")
        return client, SlackApiError

    except ImportError:
        logger.error("slack-sdk not installed. Run: pip install slack-sdk")
        return None, None
    except Exception as e:
        logger.error("Slack client error: %s", e)
        return None, None


# ------------------------------------------------------------
# FETCH USERS
# ------------------------------------------------------------

def get_slack_users(client) -> list[dict]:
    """
    Fetch all users from Slack workspace.

    Returns:
        List of dicts: user_id, name, display_name, email, birthday
    """
    try:
        response = client.users_list()
        users = []

        for member in response["members"]:
            if member.get("is_bot") or member.get("deleted"):
                continue

            profile = member.get("profile", {})
            users.append({
                "user_id":      member["id"],
                "name":         profile.get("real_name", ""),
                "display_name": profile.get("display_name", ""),
                "email":        profile.get("email", ""),
                "birthday":     profile.get("fields", {}).get("birthday", {}).get("value", ""),
            })

        logger.info("Fetched %d Slack users.", len(users))
        return users

    except Exception as e:
        logger.error("Failed to fetch Slack users: %s", e)
        return []


def get_slack_birthday_users(client) -> list[dict]:
    """
    Find Slack users whose birthday is today.

    Returns:
        List of users with birthday today.
    """
    users = get_slack_users(client)
    today = date.today()
    birthday_users = []

    for user in users:
        bday = user.get("birthday", "")
        if not bday:
            continue

        try:
            # Try MM/DD or MM-DD or MM/DD/YYYY formats
            for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d", "%m-%d"):
                try:
                    parsed = datetime.strptime(bday, fmt)
                    if parsed.month == today.month and parsed.day == today.day:
                        birthday_users.append(user)
                    break
                except ValueError:
                    continue
        except Exception:
            continue

    logger.info("Found %d Slack users with birthday today.", len(birthday_users))
    return birthday_users


# ------------------------------------------------------------
# SEND WISHES
# ------------------------------------------------------------

def get_dm_message(name: str) -> str:
    """Get a personalized DM birthday message."""
    first_name = name.split()[0].capitalize() if name else "there"
    template = random.choice(DM_TEMPLATES)
    return template.format(name=first_name)


def get_channel_message(name: str, user_id: str) -> str:
    """Get a channel birthday announcement message."""
    first_name = name.split()[0].capitalize() if name else "our teammate"
    mention = f"<@{user_id}>"
    template = random.choice(CHANNEL_TEMPLATES)
    return template.format(name=first_name, mention=mention)


def send_slack_dm(
    client,
    user_id: str,
    message: str,
    dry_run: bool = True,
) -> bool:
    """Send a birthday DM to a Slack user."""
    if dry_run:
        logger.info("[DRY RUN] Would DM %s: %s", user_id, message)
        return True

    try:
        # Open DM channel
        response = client.conversations_open(users=user_id)
        channel_id = response["channel"]["id"]

        # Send message
        client.chat_postMessage(
            channel=channel_id,
            text=message,
        )
        logger.info("DM sent to %s.", user_id)
        return True

    except Exception as e:
        logger.error("Failed to DM %s: %s", user_id, e)
        return False


def send_slack_channel_message(
    client,
    channel: str,
    message: str,
    dry_run: bool = True,
) -> bool:
    """Post a birthday announcement in a Slack channel."""
    if dry_run:
        logger.info("[DRY RUN] Would post in %s: %s", channel, message)
        return True

    try:
        client.chat_postMessage(
            channel=channel,
            text=message,
        )
        logger.info("Channel message posted in %s.", channel)
        return True

    except Exception as e:
        logger.error("Failed to post in channel %s: %s", channel, e)
        return False


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def log_slack_wish(
    user_id: str,
    display_name: str,
    wish_type: str,
    message: str,
    channel: str = "",
    dry_run: bool = True,
):
    """Log a sent Slack birthday wish."""
    with sqlite3.connect(DB_FILE) as conn:
        # Avoid duplicate wishes on same day
        existing = conn.execute("""
            SELECT id FROM slack_birthday_wishes
            WHERE slack_user = ? AND wish_date = ?
        """, (user_id, date.today().isoformat())).fetchone()

        if existing:
            logger.info("Already wished %s today on Slack.", display_name)
            return

        conn.execute("""
            INSERT INTO slack_birthday_wishes
            (slack_user, display_name, wish_type, message,
             channel, dry_run, wish_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, display_name, wish_type, message,
              channel, int(dry_run),
              date.today().isoformat(), datetime.now().isoformat()))
        conn.commit()
    logger.info("Slack wish logged: %s (%s)", display_name, wish_type)


def already_wished_today(user_id: str) -> bool:
    """Check if we already wished this user today."""
    if not DB_FILE.exists():
        return False
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM slack_birthday_wishes
            WHERE slack_user = ? AND wish_date = ? AND dry_run = 0
        """, (user_id, date.today().isoformat())).fetchone()
    return (row[0] or 0) > 0


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_slack_report(wished: list[dict]) -> str:
    """Build a human-readable Slack birthday report."""
    if not wished:
        return "No Slack birthday wishes sent today."

    lines = [
        "Slack Birthday Bot Report",
        "-" * 50,
        f"  Total wished: {len(wished)}",
        f"  Date        : {date.today().isoformat()}",
        "-" * 50,
        "",
    ]

    for w in wished:
        lines.append(f"  {w['display_name'] or w['user_id']}")
        lines.append(f"    Type   : {w['wish_type']}")
        lines.append(f"    Message: {w['message'][:60]}...")
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_slack_birthday_bot(
    dry_run: bool = True,
    send_dm: bool = True,
    send_channel: bool = False,
    birthday_channel: str = "",
) -> dict:
    """
    Main runner. Call from agent.py daily.

    Args:
        dry_run          : If True, log only - do not send
        send_dm          : Send DM to birthday person
        send_channel     : Post in birthday channel
        birthday_channel : Slack channel name (e.g. #birthdays)

    Returns:
        Dict with summary stats.
    """
    from dotenv import dotenv_values
    config = dotenv_values(".env")

    logger.info("=== Slack Birthday Bot === [DRY RUN: %s]", dry_run)

    client, SlackApiError = get_slack_client()
    if not client:
        return {"error": "Slack client unavailable.", "total_wished": 0}

    # Get birthday channel from .env if not provided
    if not birthday_channel:
        birthday_channel = config.get("SLACK_BIRTHDAY_CHANNEL", "#general")

    # Find today's birthday users
    birthday_users = get_slack_birthday_users(client)

    if not birthday_users:
        logger.info("No Slack birthdays today.")
        return {"total_wished": 0, "report": "No birthdays today in Slack workspace."}

    wished = []

    for user in birthday_users:
        user_id      = user["user_id"]
        name         = user["name"] or user["display_name"] or "Friend"
        display_name = user["display_name"] or name

        if already_wished_today(user_id) and not dry_run:
            logger.info("Already wished %s today.", display_name)
            continue

        # Send DM
        if send_dm:
            message = get_dm_message(name)
            success = send_slack_dm(
                client=client,
                user_id=user_id,
                message=message,
                dry_run=dry_run,
            )
            if success:
                log_slack_wish(
                    user_id=user_id,
                    display_name=display_name,
                    wish_type="DM",
                    message=message,
                    dry_run=dry_run,
                )
                wished.append({
                    "user_id":      user_id,
                    "display_name": display_name,
                    "wish_type":    "DM",
                    "message":      message,
                })

        # Post in channel
        if send_channel and birthday_channel:
            channel_msg = get_channel_message(name, user_id)
            success = send_slack_channel_message(
                client=client,
                channel=birthday_channel,
                message=channel_msg,
                dry_run=dry_run,
            )
            if success:
                log_slack_wish(
                    user_id=user_id,
                    display_name=display_name,
                    wish_type="channel",
                    message=channel_msg,
                    channel=birthday_channel,
                    dry_run=dry_run,
                )
                wished.append({
                    "user_id":      user_id,
                    "display_name": display_name,
                    "wish_type":    "channel",
                    "message":      channel_msg,
                })

    report = build_slack_report(wished)
    logger.info("Slack bot done: %d wishes sent.", len(wished))

    return {
        "total_wished": len(wished),
        "report":       report,
        "users":        wished,
    }
