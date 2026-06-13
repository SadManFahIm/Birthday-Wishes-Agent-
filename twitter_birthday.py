"""
twitter_birthday.py
-------------------
Twitter/X Birthday Mention Detection for Birthday Wishes Agent.

Monitors Twitter/X for birthday mentions of your LinkedIn contacts
and optionally replies with a birthday wish.

How it works:
  1. Searches Twitter/X for birthday mentions of known contacts
  2. Detects birthday-related tweets (HBD, Happy Birthday, etc.)
  3. Logs detected mentions to SQLite
  4. Optionally replies with a personalized birthday wish
  5. Sends alert via email/Telegram

Requirements:
  - Twitter Developer Account (free tier works)
  - API Key, API Secret, Access Token, Access Token Secret
  - Bearer Token (for search)

.env setup:
  TWITTER_API_KEY=...
  TWITTER_API_SECRET=...
  TWITTER_ACCESS_TOKEN=...
  TWITTER_ACCESS_SECRET=...
  TWITTER_BEARER_TOKEN=...

Usage:
    from twitter_birthday import (
        init_twitter_table,
        run_twitter_birthday_detection,
        get_twitter_mentions,
    )

    await run_twitter_birthday_detection(dry_run=True)
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Birthday keywords to search for
BIRTHDAY_KEYWORDS = [
    "Happy Birthday",
    "HBD",
    "Happy Bday",
    "Many happy returns",
    "Birthday wishes",
    "birthday",
]

# Birthday reply templates
REPLY_TEMPLATES = [
    "Happy Birthday {name}! Hope your day is amazing!",
    "Wishing you a fantastic birthday {name}! Have a great one!",
    "Happy Birthday {name}! Hope this year brings you great things!",
]

# Max tweets to fetch per search
MAX_RESULTS = 50

# How many days back to search
LOOKBACK_HOURS = 24


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_twitter_table():
    """Create Twitter birthday mention tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS twitter_birthday_mentions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                twitter_user TEXT,
                tweet_id     TEXT,
                tweet_text   TEXT,
                replied      INTEGER DEFAULT 0,
                reply_text   TEXT,
                detected_date TEXT   NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Twitter birthday mention table ready.")


# ------------------------------------------------------------
# TWITTER CLIENT
# ------------------------------------------------------------

def get_twitter_client():
    """Build and return a Tweepy client using .env credentials."""
    try:
        import tweepy
        from dotenv import dotenv_values

        config = dotenv_values(".env")

        bearer_token    = config.get("TWITTER_BEARER_TOKEN", "")
        api_key         = config.get("TWITTER_API_KEY", "")
        api_secret      = config.get("TWITTER_API_SECRET", "")
        access_token    = config.get("TWITTER_ACCESS_TOKEN", "")
        access_secret   = config.get("TWITTER_ACCESS_SECRET", "")

        if not bearer_token:
            logger.error("TWITTER_BEARER_TOKEN missing in .env")
            return None, None

        # v2 client for search
        client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
            wait_on_rate_limit=True,
        )

        logger.info("Twitter client initialized.")
        return client, tweepy

    except ImportError:
        logger.error("tweepy not installed. Run: pip install tweepy")
        return None, None
    except Exception as e:
        logger.error("Twitter client error: %s", e)
        return None, None


# ------------------------------------------------------------
# SEARCH
# ------------------------------------------------------------

def search_birthday_tweets(
    contact_name: str,
    client,
    tweepy,
    lookback_hours: int = LOOKBACK_HOURS,
) -> list[dict]:
    """
    Search Twitter/X for birthday mentions of a contact.

    Args:
        contact_name  : Full name or username to search
        client        : Tweepy v2 Client
        tweepy        : Tweepy module
        lookback_hours: How many hours back to search

    Returns:
        List of dicts: tweet_id, tweet_text, author_id
    """
    first_name = contact_name.split()[0]
    results = []

    for keyword in ["Happy Birthday", "HBD", "birthday"]:
        query = f'"{first_name}" {keyword} -is:retweet lang:en'

        try:
            start_time = datetime.utcnow() - timedelta(hours=lookback_hours)

            response = client.search_recent_tweets(
                query=query,
                max_results=min(MAX_RESULTS, 100),
                start_time=start_time.isoformat() + "Z",
                tweet_fields=["text", "author_id", "created_at"],
            )

            if response.data:
                for tweet in response.data:
                    results.append({
                        "tweet_id":   str(tweet.id),
                        "tweet_text": tweet.text,
                        "author_id":  str(tweet.author_id),
                    })

            logger.info("Found %d tweets for '%s' with keyword '%s'.",
                        len(response.data or []), contact_name, keyword)

        except Exception as e:
            logger.warning("Search failed for '%s' ('%s'): %s",
                           contact_name, keyword, e)

    # Deduplicate by tweet_id
    seen = set()
    unique = []
    for t in results:
        if t["tweet_id"] not in seen:
            seen.add(t["tweet_id"])
            unique.append(t)

    return unique


def is_birthday_tweet(tweet_text: str) -> bool:
    """Check if a tweet text contains birthday keywords."""
    text_lower = tweet_text.lower()
    return any(kw.lower() in text_lower for kw in BIRTHDAY_KEYWORDS)


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def log_twitter_mention(
    contact: str,
    tweet_id: str,
    tweet_text: str,
    twitter_user: str = "",
):
    """Log a detected Twitter birthday mention."""
    with sqlite3.connect(DB_FILE) as conn:
        # Avoid duplicates
        existing = conn.execute("""
            SELECT id FROM twitter_birthday_mentions
            WHERE tweet_id = ?
        """, (tweet_id,)).fetchone()

        if existing:
            return

        conn.execute("""
            INSERT INTO twitter_birthday_mentions
            (contact, twitter_user, tweet_id, tweet_text,
             detected_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (contact, twitter_user, tweet_id, tweet_text,
              date.today().isoformat(), datetime.now().isoformat()))
        conn.commit()
    logger.info("Twitter mention logged: %s (tweet: %s)", contact, tweet_id)


def mark_replied(tweet_id: str, reply_text: str):
    """Mark a tweet as replied."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE twitter_birthday_mentions
            SET    replied = 1, reply_text = ?
            WHERE  tweet_id = ?
        """, (reply_text, tweet_id))
        conn.commit()
    logger.info("Tweet reply marked: %s", tweet_id)


def get_twitter_mentions(lookback_days: int = 7) -> list[dict]:
    """Get recent Twitter birthday mentions from DB."""
    if not DB_FILE.exists():
        return []

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT contact, twitter_user, tweet_id, tweet_text,
                   replied, detected_date
            FROM   twitter_birthday_mentions
            WHERE  detected_date >= ?
            ORDER  BY detected_date DESC
        """, (cutoff,)).fetchall()

    return [
        {
            "contact":      row[0],
            "twitter_user": row[1],
            "tweet_id":     row[2],
            "tweet_text":   row[3],
            "replied":      bool(row[4]),
            "date":         row[5],
        }
        for row in rows
    ]


# ------------------------------------------------------------
# REPLY
# ------------------------------------------------------------

import random

def get_reply_message(contact_name: str) -> str:
    """Get a birthday reply message."""
    first_name = contact_name.split()[0].capitalize()
    template = random.choice(REPLY_TEMPLATES)
    return template.format(name=first_name)


def send_twitter_reply(
    client,
    tweet_id: str,
    reply_text: str,
    dry_run: bool = True,
) -> bool:
    """Send a reply to a birthday tweet."""
    if dry_run:
        logger.info("[DRY RUN] Would reply to tweet %s: %s", tweet_id, reply_text)
        return True

    try:
        client.create_tweet(
            text=reply_text,
            in_reply_to_tweet_id=tweet_id,
        )
        logger.info("Replied to tweet %s: %s", tweet_id, reply_text)
        return True
    except Exception as e:
        logger.error("Failed to reply to tweet %s: %s", tweet_id, e)
        return False


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_twitter_report(mentions: list[dict] | None = None) -> str:
    """Build a human-readable Twitter mention report."""
    if mentions is None:
        mentions = get_twitter_mentions()

    if not mentions:
        return "No Twitter birthday mentions found."

    lines = [
        "Twitter/X Birthday Mention Report",
        "-" * 50,
        f"  Total mentions : {len(mentions)}",
        f"  Replied        : {sum(1 for m in mentions if m['replied'])}",
        "-" * 50,
        "",
    ]

    for m in mentions:
        status = "REPLIED" if m["replied"] else "PENDING"
        lines.append(f"  [{status}] {m['contact']} — {m['date']}")
        lines.append(f"    {m['tweet_text'][:80]}...")
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_twitter_birthday_detection(
    contacts: list[str] | None = None,
    dry_run: bool = True,
    auto_reply: bool = False,
    lookback_hours: int = LOOKBACK_HOURS,
) -> dict:
    """
    Main runner. Call from agent.py daily.

    Args:
        contacts      : List of contact names to check.
                        If None, reads from history table.
        dry_run       : If True, log only - do not reply
        auto_reply    : If True, auto-reply to birthday tweets
        lookback_hours: Hours back to search Twitter

    Returns:
        Dict with summary stats.
    """
    logger.info("=== Twitter Birthday Detection === [DRY RUN: %s]", dry_run)

    client, tweepy = get_twitter_client()
    if not client:
        logger.error("Twitter client unavailable. Check .env credentials.")
        return {"error": "Twitter client unavailable.", "total_found": 0}

    # Get contacts from history if not provided
    if not contacts:
        contacts = _get_contacts_from_history()

    if not contacts:
        logger.info("No contacts to check.")
        return {"total_found": 0, "replied": 0}

    total_found = 0
    replied     = 0

    for contact in contacts:
        tweets = search_birthday_tweets(
            contact_name=contact,
            client=client,
            tweepy=tweepy,
            lookback_hours=lookback_hours,
        )

        for tweet in tweets:
            if not is_birthday_tweet(tweet["tweet_text"]):
                continue

            log_twitter_mention(
                contact=contact,
                tweet_id=tweet["tweet_id"],
                tweet_text=tweet["tweet_text"],
            )
            total_found += 1
            logger.info("Birthday mention found for %s: %s",
                        contact, tweet["tweet_text"][:60])

            if auto_reply:
                reply_text = get_reply_message(contact)
                success = send_twitter_reply(
                    client=client,
                    tweet_id=tweet["tweet_id"],
                    reply_text=reply_text,
                    dry_run=dry_run,
                )
                if success and not dry_run:
                    mark_replied(tweet["tweet_id"], reply_text)
                    replied += 1

    report = build_twitter_report()
    logger.info("Twitter detection done: %d found | %d replied",
                total_found, replied)

    return {
        "total_found": total_found,
        "replied":     replied,
        "report":      report,
    }


def _get_contacts_from_history() -> list[str]:
    """Get contact names from agent history table."""
    if not DB_FILE.exists():
        return []

    cutoff = (date.today() - timedelta(days=30)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT DISTINCT contact FROM history
            WHERE date >= ? AND dry_run = 0
            LIMIT 100
        """, (cutoff,)).fetchall()

    return [row[0] for row in rows if row[0]]


# ------------------------------------------------------------
# AGENT INSTRUCTIONS
# ------------------------------------------------------------

def build_twitter_instructions(contact_name: str, tweet_text: str) -> str:
    """Build instructions for agent to handle a Twitter birthday mention."""
    reply = get_reply_message(contact_name)
    return f"""
  TWITTER BIRTHDAY MENTION DETECTED:
  Contact    : {contact_name}
  Tweet      : {tweet_text[:100]}

  Suggested reply:
    "{reply}"

  Action: Reply to this tweet with the message above.
  Report: TWITTER REPLIED: {contact_name} or TWITTER FAILED: {contact_name}
"""