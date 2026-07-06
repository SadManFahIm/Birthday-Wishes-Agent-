"""
auto_learning_reply.py
----------------------
Auto-Learning Reply Style for Birthday Wishes Agent.

Tracks how contacts engage with different reply styles
and automatically improves the style over time.

How it works:
  1. Tracks every reply sent with its style (formal/casual/warm/funny)
  2. Monitors if the contact engaged further (replied back, liked, etc.)
  3. Calculates engagement rate per style
  4. Auto-selects the best-performing style for future replies
  5. Adapts per contact relationship type (VIP/Key/Regular)

Reply styles:
  - warm     : Friendly, personal, 2-3 sentences
  - casual   : Relaxed, short, conversational
  - formal   : Professional, respectful, concise
  - funny    : Light humor, playful, fun
  - brief    : Ultra short, 1 sentence

Usage:
    from auto_learning_reply import (
        init_reply_learning_table,
        log_reply_sent,
        log_reply_engaged,
        get_best_reply_style,
        build_reply_learning_report,
    )

    style = get_best_reply_style(contact="John", relationship="Key")
"""

import logging
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

MIN_SAMPLES   = 10   # Min sends before auto-learning activates
RECENT_DAYS   = 60   # Weight recent data more
RECENT_WEIGHT = 2.0  # Recent sends count 2x

REPLY_STYLES = {
    "warm": {
        "name":        "Warm & Personal",
        "description": "Friendly, personal, mentions their name",
        "templates": [
            "Thanks so much {name}! That really means a lot to me. Hope you are doing great!",
            "Aww thank you {name}! You are so kind. Hope life is treating you well!",
            "That is so sweet of you {name}! Really appreciate it. Hope all is well with you!",
        ],
    },
    "casual": {
        "name":        "Casual & Relaxed",
        "description": "Relaxed, conversational, like texting a friend",
        "templates": [
            "Thanks {name}! Really appreciate it!",
            "Haha thanks {name}! Made my day!",
            "Thanks so much {name}! You are the best!",
        ],
    },
    "formal": {
        "name":        "Professional & Formal",
        "description": "Respectful, professional tone",
        "templates": [
            "Thank you very much {name}. I truly appreciate your kind wishes.",
            "Many thanks {name}. Your thoughtfulness is greatly appreciated.",
            "Thank you {name}. It means a great deal to receive your warm wishes.",
        ],
    },
    "funny": {
        "name":        "Funny & Playful",
        "description": "Light humor, witty response",
        "templates": [
            "Thanks {name}! Getting older but at least I am getting better right?",
            "Haha thanks {name}! Another year wiser they say!",
            "Thanks {name}! You remembered! You are officially my favorite person today!",
        ],
    },
    "brief": {
        "name":        "Brief & Sweet",
        "description": "Ultra short, one line",
        "templates": [
            "Thanks {name}!",
            "Really appreciate it {name}!",
            "Thank you {name}! Means a lot!",
        ],
    },
}

# Default style per relationship tier
DEFAULT_STYLES = {
    "VIP":     "warm",
    "Key":     "warm",
    "Regular": "casual",
    "Casual":  "brief",
    "unknown": "casual",
}


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_reply_learning_table():
    """Create reply learning tracking tables."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reply_learning (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                relationship TEXT    DEFAULT 'unknown',
                style        TEXT    NOT NULL,
                reply_text   TEXT,
                engaged      INTEGER DEFAULT 0,
                engaged_at   TEXT,
                platform     TEXT    DEFAULT 'linkedin',
                dry_run      INTEGER DEFAULT 1,
                sent_date    TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Reply learning table ready.")


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def log_reply_sent(
    contact: str,
    style: str,
    reply_text: str,
    relationship: str = "unknown",
    platform: str = "linkedin",
    dry_run: bool = True,
) -> int:
    """Log a sent reply for learning tracking."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("""
            INSERT INTO reply_learning
            (contact, relationship, style, reply_text, platform,
             dry_run, sent_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (contact, relationship, style, reply_text, platform,
              int(dry_run), date.today().isoformat(),
              datetime.now().isoformat()))
        record_id = cursor.lastrowid
        conn.commit()
    logger.info("Reply logged: %s | style=%s", contact, style)
    return record_id


def log_reply_engaged(contact: str, platform: str = "linkedin"):
    """
    Mark that a contact engaged with our reply (replied back, liked etc.)
    Call this when engagement is detected.
    """
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE reply_learning
            SET    engaged = 1, engaged_at = ?
            WHERE  LOWER(contact) = LOWER(?)
              AND  platform = ?
              AND  engaged  = 0
              AND  dry_run  = 0
              AND  id = (
                  SELECT id FROM reply_learning
                  WHERE  LOWER(contact) = LOWER(?)
                    AND  platform = ?
                    AND  engaged  = 0
                    AND  dry_run  = 0
                  ORDER BY id DESC LIMIT 1
              )
        """, (datetime.now().isoformat(), contact, platform,
              contact, platform))
        conn.commit()
    logger.info("Engagement logged for: %s", contact)


# ------------------------------------------------------------
# STYLE STATS
# ------------------------------------------------------------

def get_style_stats(relationship: str = "") -> dict:
    """
    Get per-style engagement stats with decay weighting.

    Args:
        relationship: Filter by relationship tier (VIP/Key/Regular/Casual)

    Returns:
        Dict[style] -> {sent, engaged, weighted_sent, weighted_engaged, rate}
    """
    if not DB_FILE.exists():
        return {}

    today  = date.today()
    query  = """
        SELECT style, engaged, sent_date
        FROM   reply_learning
        WHERE  dry_run = 0
    """
    params = []

    if relationship:
        query  += " AND relationship = ?"
        params.append(relationship)

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(query, params).fetchall()

    stats = {k: {"sent": 0, "engaged": 0, "weighted_sent": 0.0,
                 "weighted_engaged": 0.0, "rate": 0.0}
             for k in REPLY_STYLES}

    for style, engaged, sent_date_str in rows:
        if style not in stats:
            continue
        try:
            sent_date = date.fromisoformat(sent_date_str)
        except ValueError:
            sent_date = today

        age_days = (today - sent_date).days
        weight   = RECENT_WEIGHT if age_days <= RECENT_DAYS else 1.0

        stats[style]["sent"]             += 1
        stats[style]["weighted_sent"]    += weight
        if engaged:
            stats[style]["engaged"]          += 1
            stats[style]["weighted_engaged"] += weight

    for s in stats.values():
        ws = s["weighted_sent"]
        s["rate"] = round(s["weighted_engaged"] / ws, 4) if ws else 0.0

    return stats


# ------------------------------------------------------------
# BEST STYLE SELECTION
# ------------------------------------------------------------

def get_best_reply_style(
    contact: str = "",
    relationship: str = "unknown",
) -> str:
    """
    Get the best reply style using auto-learning.

    Exploration phase (any style < MIN_SAMPLES):
      -> random style from suitable defaults
    Exploitation phase (enough data):
      -> highest weighted engagement rate

    Args:
        contact      : Contact name (for per-contact learning)
        relationship : Relationship tier (VIP/Key/Regular/Casual)

    Returns:
        Style key string.
    """
    stats    = get_style_stats(relationship)
    all_keys = list(REPLY_STYLES.keys())

    # Exploration: any style not tested enough?
    for key in all_keys:
        if stats.get(key, {}).get("sent", 0) < MIN_SAMPLES:
            # Pick from default styles for this relationship
            default = DEFAULT_STYLES.get(relationship, "casual")
            chosen  = random.choice([default, key])
            logger.info(
                "Reply learning [explore]: style '%s' only %d/%d samples. "
                "Picking -> %s",
                key, stats.get(key, {}).get("sent", 0), MIN_SAMPLES, chosen,
            )
            return chosen

    # Exploitation: pick highest engagement rate
    best = max(all_keys, key=lambda k: stats.get(k, {}).get("rate", 0.0))
    rate = stats.get(best, {}).get("rate", 0.0)
    logger.info(
        "Reply learning [exploit]: best style -> %s (%s) | rate: %.1f%%",
        best, REPLY_STYLES[best]["name"], rate * 100,
    )
    return best


def get_reply_message(
    contact_name: str,
    style: str = "",
    relationship: str = "unknown",
) -> str:
    """Get a reply message in the selected style."""
    if not style:
        style = get_best_reply_style(contact_name, relationship)

    first_name = contact_name.split()[0].capitalize() if contact_name else "there"
    style_data = REPLY_STYLES.get(style, REPLY_STYLES["casual"])
    template   = random.choice(style_data["templates"])
    return template.format(name=first_name)


# ------------------------------------------------------------
# AGENT INSTRUCTIONS
# ------------------------------------------------------------

def build_reply_learning_instructions(
    contact: str,
    relationship: str = "unknown",
) -> str:
    """Build reply style instructions for the browser agent."""
    style   = get_best_reply_style(contact, relationship)
    message = get_reply_message(contact, style, relationship)
    stats   = get_style_stats(relationship)
    rate    = stats.get(style, {}).get("rate", 0.0)

    return f"""
  AUTO-LEARNING REPLY STYLE:
  Contact      : {contact}
  Relationship : {relationship}
  Best style   : {style} — {REPLY_STYLES[style]['name']}
  Engagement   : {rate * 100:.1f}% (weighted)

  Use this reply message:
  "{message}"

  After sending, note if they engage (reply back, like etc.).
  Report: ENGAGED: {contact} or NO_ENGAGE: {contact}
"""


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_reply_learning_report() -> str:
    """Build human-readable auto-learning reply report."""
    stats = get_style_stats()
    best  = get_best_reply_style()

    total_sent    = sum(s["sent"] for s in stats.values())
    total_engaged = sum(s["engaged"] for s in stats.values())
    overall_rate  = round(total_engaged / total_sent * 100, 1) if total_sent else 0

    lines = [
        "Auto-Learning Reply Style Report",
        "-" * 55,
        f"  Total replies  : {total_sent}",
        f"  Total engaged  : {total_engaged}",
        f"  Overall rate   : {overall_rate:.1f}%",
        f"  Best style now : {best} — {REPLY_STYLES[best]['name']}",
        "-" * 55,
        "",
        f"  {'Style':<10} {'Name':<22} {'Sent':>5} {'Engaged':>8} {'Rate':>7}",
        "  " + "-" * 56,
    ]

    sorted_styles = sorted(
        REPLY_STYLES.keys(),
        key=lambda k: stats.get(k, {}).get("rate", 0.0),
        reverse=True,
    )

    for key in sorted_styles:
        s      = stats.get(key, {"sent": 0, "engaged": 0, "rate": 0.0})
        name   = REPLY_STYLES[key]["name"]
        medal  = "* " if key == best else "  "
        rate   = s["rate"] * 100
        lines.append(
            f"  {medal}{key:<10} {name:<22} {s['sent']:>5} "
            f"{s['engaged']:>8} {rate:>6.1f}%"
        )

    lines += [
        "",
        f"  Weighted window : last {RECENT_DAYS} days = {RECENT_WEIGHT}x weight",
        f"  Min samples     : {MIN_SAMPLES} per style before auto-select",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    return "\n".join(lines)
