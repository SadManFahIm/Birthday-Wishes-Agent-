"""
discord_birthday_bot.py
-----------------------
Discord Server Member Birthday Bot for Birthday Wishes Agent.

Automatically detects and celebrates birthdays of Discord
server members with personalized messages.

Features:
  - Send birthday DM to member on their birthday
  - Post birthday announcement in a designated channel
  - Role-based birthday celebration (optional birthday role)
  - Tracks birthdays in SQLite
  - Supports multiple servers

.env setup:
  DISCORD_BOT_TOKEN=your_bot_token
  DISCORD_BIRTHDAY_CHANNEL=general        (channel name for announcements)
  DISCORD_BIRTHDAY_ROLE=Birthday Person   (optional role to assign)
  DISCORD_BIRTHDAY_ENABLED=true

Bot permissions needed:
  - Send Messages
  - Manage Roles (optional, for birthday role)
  - Read Message History

Usage:
    from discord_birthday_bot import (
        init_discord_birthday_table,
        run_discord_birthday_bot,
        register_member_birthday,
    )

    await run_discord_birthday_bot(dry_run=True)
"""

import logging
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Birthday wish templates for Discord
DM_TEMPLATES = [
    "Happy Birthday {name}! Hope your day is absolutely amazing!",
    "Wishing you a fantastic birthday {name}! Hope this year brings great things!",
    "Happy Birthday {name}! You deserve all the celebrations today!",
    "Many happy returns {name}! Hope your special day is filled with joy!",
    "Happy Birthday {name}! Another year wiser and better. Enjoy your day!",
]

CHANNEL_TEMPLATES = [
    "@everyone Let us celebrate {name}'s birthday today! "
    "Hope your day is amazing {mention}!",
    "It is {name}'s birthday today! Wishing you all the best {mention}! "
    "Have a wonderful day!",
    "Happy Birthday to our amazing member {mention}! "
    "Hope this year brings you great success and happiness!",
    "Everybody wish {mention} a Happy Birthday! "
    "Hope your special day is everything you dreamed of {name}!",
]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_discord_birthday_table():
    """Create Discord birthday tracking tables."""
    with sqlite3.connect(DB_FILE) as conn:
        # Store member birthdays
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discord_member_birthdays (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id    TEXT    NOT NULL,
                member_id    TEXT    NOT NULL,
                member_name  TEXT    NOT NULL,
                birthday     TEXT    NOT NULL,
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL,
                UNIQUE(server_id, member_id)
            )
        """)
        # Track sent wishes
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discord_birthday_wishes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id    TEXT    NOT NULL,
                member_id    TEXT    NOT NULL,
                member_name  TEXT    NOT NULL,
                wish_type    TEXT    DEFAULT 'dm',
                message      TEXT,
                dry_run      INTEGER DEFAULT 1,
                wish_date    TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Discord birthday tables ready.")


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

def load_config() -> dict:
    """Load Discord config from .env."""
    from dotenv import dotenv_values
    config = dotenv_values(".env")
    return {
        "bot_token":        config.get("DISCORD_BOT_TOKEN", ""),
        "birthday_channel": config.get("DISCORD_BIRTHDAY_CHANNEL", "general"),
        "birthday_role":    config.get("DISCORD_BIRTHDAY_ROLE", ""),
        "enabled":          config.get("DISCORD_BIRTHDAY_ENABLED", "false").lower() == "true",
    }


# ------------------------------------------------------------
# MEMBER BIRTHDAY REGISTRY
# ------------------------------------------------------------

def register_member_birthday(
    server_id: str,
    member_id: str,
    member_name: str,
    birthday: str,
):
    """
    Register a member's birthday.

    Args:
        server_id   : Discord server/guild ID
        member_id   : Discord user ID
        member_name : Display name
        birthday    : Birthday in MM-DD format (e.g. "03-15")
    """
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO discord_member_birthdays
                (server_id, member_id, member_name, birthday, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(server_id, member_id) DO UPDATE SET
                member_name = excluded.member_name,
                birthday    = excluded.birthday,
                updated_at  = excluded.updated_at
        """, (server_id, member_id, member_name, birthday, now, now))
        conn.commit()
    logger.info("Birthday registered: %s (%s) on %s", member_name, server_id, birthday)


def get_todays_birthdays(server_id: str = "") -> list[dict]:
    """Get members with birthdays today."""
    if not DB_FILE.exists():
        return []

    today_md = date.today().strftime("%m-%d")
    query    = "SELECT server_id, member_id, member_name, birthday FROM discord_member_birthdays WHERE birthday = ?"
    params   = [today_md]

    if server_id:
        query  += " AND server_id = ?"
        params.append(server_id)

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        {
            "server_id":   row[0],
            "member_id":   row[1],
            "member_name": row[2],
            "birthday":    row[3],
        }
        for row in rows
    ]


def already_wished_today(server_id: str, member_id: str) -> bool:
    """Check if already wished this member today."""
    if not DB_FILE.exists():
        return False
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM discord_birthday_wishes
            WHERE server_id = ? AND member_id = ?
              AND wish_date = ? AND dry_run = 0
        """, (server_id, member_id, date.today().isoformat())).fetchone()
    return (row[0] or 0) > 0


def log_wish(
    server_id: str,
    member_id: str,
    member_name: str,
    wish_type: str,
    message: str,
    dry_run: bool = True,
):
    """Log a sent birthday wish."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO discord_birthday_wishes
            (server_id, member_id, member_name, wish_type,
             message, dry_run, wish_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (server_id, member_id, member_name, wish_type,
              message, int(dry_run),
              date.today().isoformat(), datetime.now().isoformat()))
        conn.commit()
    logger.info("Discord wish logged: %s (%s)", member_name, wish_type)


# ------------------------------------------------------------
# MESSAGE HELPERS
# ------------------------------------------------------------

def get_dm_message(member_name: str) -> str:
    """Get a DM birthday wish."""
    first = member_name.split()[0].capitalize()
    return random.choice(DM_TEMPLATES).format(name=first)


def get_channel_message(member_name: str, member_id: str) -> str:
    """Get a channel birthday announcement with mention."""
    first   = member_name.split()[0].capitalize()
    mention = f"<@{member_id}>"
    return random.choice(CHANNEL_TEMPLATES).format(
        name=first, mention=mention
    )


# ------------------------------------------------------------
# DISCORD API HELPERS
# ------------------------------------------------------------

async def send_discord_dm(
    member_id: str,
    message: str,
    bot_token: str,
    dry_run: bool = True,
) -> bool:
    """Send a DM to a Discord member via REST API."""
    if dry_run:
        logger.info("[DRY RUN] Would DM %s: %s", member_id, message[:60])
        return True

    try:
        import requests

        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type":  "application/json",
        }

        # Create DM channel
        dm_resp = requests.post(
            "https://discord.com/api/v10/users/@me/channels",
            headers=headers,
            json={"recipient_id": member_id},
            timeout=10,
        )

        if dm_resp.status_code not in (200, 201):
            logger.error("Failed to create DM channel: %s", dm_resp.text[:100])
            return False

        channel_id = dm_resp.json()["id"]

        # Send message
        msg_resp = requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers=headers,
            json={"content": message},
            timeout=10,
        )

        if msg_resp.status_code == 200:
            logger.info("Discord DM sent to %s.", member_id)
            return True
        else:
            logger.error("Discord DM failed: %s", msg_resp.text[:100])
            return False

    except Exception as e:
        logger.error("Discord DM error: %s", e)
        return False


async def send_discord_channel_message(
    channel_id: str,
    message: str,
    bot_token: str,
    dry_run: bool = True,
) -> bool:
    """Post a message in a Discord channel."""
    if dry_run:
        logger.info("[DRY RUN] Would post in channel %s: %s",
                    channel_id, message[:60])
        return True

    try:
        import requests

        resp = requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={
                "Authorization": f"Bot {bot_token}",
                "Content-Type":  "application/json",
            },
            json={"content": message},
            timeout=10,
        )

        if resp.status_code == 200:
            logger.info("Discord channel message sent.")
            return True
        else:
            logger.error("Discord channel failed: %s", resp.text[:100])
            return False

    except Exception as e:
        logger.error("Discord channel error: %s", e)
        return False


async def get_guild_channels(guild_id: str, bot_token: str) -> dict:
    """Get channels in a guild, returns name->id mapping."""
    try:
        import requests
        resp = requests.get(
            f"https://discord.com/api/v10/guilds/{guild_id}/channels",
            headers={"Authorization": f"Bot {bot_token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return {ch["name"]: ch["id"] for ch in resp.json()
                    if ch.get("type") == 0}  # type 0 = text channel
    except Exception as e:
        logger.error("Could not fetch guild channels: %s", e)
    return {}


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_discord_report() -> str:
    """Build Discord birthday wish report."""
    if not DB_FILE.exists():
        return "No Discord wish data yet."

    month_start = date.today().replace(day=1).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT member_name, wish_type, wish_date, dry_run
            FROM   discord_birthday_wishes
            WHERE  wish_date >= ?
            ORDER  BY wish_date DESC
        """, (month_start,)).fetchall()

        registered = conn.execute(
            "SELECT COUNT(*) FROM discord_member_birthdays"
        ).fetchone()[0] or 0

    lines = [
        "Discord Birthday Bot Report",
        "-" * 50,
        f"  Registered members : {registered}",
        f"  Wishes this month  : {len([r for r in rows if not r[3]])}",
        "-" * 50,
        "",
    ]

    for r in rows[:10]:
        dry = "[DRY]" if r[3] else ""
        lines.append(f"  {dry} {r[0]} ({r[1]}) — {r[2]}")

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_discord_birthday_bot(
    guild_id: str = "",
    dry_run: bool = True,
    send_dm: bool = True,
    send_channel: bool = True,
) -> dict:
    """
    Main runner. Call from agent.py daily.

    Args:
        guild_id     : Discord server/guild ID
        dry_run      : If True, log only - do not send
        send_dm      : Send DM to birthday member
        send_channel : Post in birthday channel

    Returns:
        Dict with summary stats.
    """
    logger.info("=== Discord Birthday Bot === [DRY RUN: %s]", dry_run)

    config = load_config()
    if not config["bot_token"]:
        logger.error("DISCORD_BOT_TOKEN missing in .env")
        return {"error": "No bot token", "sent": 0}

    # Get today's birthdays
    members = get_todays_birthdays(guild_id)

    if not members:
        logger.info("No Discord birthdays today.")
        return {"sent": 0, "report": "No birthdays today."}

    # Get channel ID for announcements
    channel_map = {}
    if send_channel and guild_id and not dry_run:
        channel_map = await get_guild_channels(guild_id, config["bot_token"])

    birthday_channel_id = channel_map.get(config["birthday_channel"], "")

    sent = 0
    for member in members:
        if already_wished_today(member["server_id"], member["member_id"]) and not dry_run:
            logger.info("Already wished %s today.", member["member_name"])
            continue

        # Send DM
        if send_dm:
            dm_msg = get_dm_message(member["member_name"])
            ok     = await send_discord_dm(
                member_id=member["member_id"],
                message=dm_msg,
                bot_token=config["bot_token"],
                dry_run=dry_run,
            )
            if ok:
                log_wish(
                    member["server_id"], member["member_id"],
                    member["member_name"], "dm", dm_msg, dry_run,
                )
                sent += 1

        # Channel announcement
        if send_channel and (birthday_channel_id or dry_run):
            ch_msg = get_channel_message(
                member["member_name"], member["member_id"]
            )
            await send_discord_channel_message(
                channel_id=birthday_channel_id or "DRY_RUN_CHANNEL",
                message=ch_msg,
                bot_token=config["bot_token"],
                dry_run=dry_run,
            )
            log_wish(
                member["server_id"], member["member_id"],
                member["member_name"], "channel", ch_msg, dry_run,
            )

    report = build_discord_report()
    logger.info("Discord bot done: %d wished.", sent)

    return {"sent": sent, "total_birthdays": len(members), "report": report}
