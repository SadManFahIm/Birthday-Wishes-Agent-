"""
connection_tracker.py
─────────────────────
Connection Strength Tracker module for Birthday Wishes Agent.

Tracks interaction history with each LinkedIn contact over time
and calculates a dynamic "connection strength" score.

How it works:
  1. Every time the agent interacts with a contact (wish, reply,
     comment, follow-up, connect), it logs the interaction
  2. Connection strength is calculated based on:
     - Frequency of interactions
     - Recency of last interaction
     - Types of interactions (DM > comment > like)
  3. Strength score is used to:
     - Determine wish style (close_friend vs colleague vs acquaintance)
     - Prioritize who to engage with
     - Show trending connections in the dashboard

Strength Levels:
  🔴 Fading     (0-20)  : No recent interaction
  🟡 Weak       (21-40) : Occasional interaction
  🟢 Moderate   (41-60) : Regular interaction
  💙 Strong     (61-80) : Frequent interaction
  ⭐ Very Strong (81-100): Highly engaged connection
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Interaction weights
INTERACTION_WEIGHTS = {
    "birthday_wish":    10,
    "reply":            8,
    "follow_up":        7,
    "dm":               9,
    "comment":          5,
    "like":             3,
    "connect":          6,
    "group_engagement": 4,
}

# Recency decay — interactions older than this lose weight
RECENCY_DAYS = 365


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_tracker_table():
    """Create connection strength tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connection_interactions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                contact         TEXT    NOT NULL,
                interaction_type TEXT   NOT NULL,
                platform        TEXT    NOT NULL DEFAULT 'linkedin',
                notes           TEXT,
                date            TEXT    NOT NULL,
                created_at      TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  Connection tracker table ready.")


# ──────────────────────────────────────────────
# LOG INTERACTION
# ──────────────────────────────────────────────
def log_interaction(
    contact: str,
    interaction_type: str,
    platform: str = "linkedin",
    notes: str = "",
):
    """
    Log an interaction with a contact.

    Args:
        contact          : Contact's name
        interaction_type : One of INTERACTION_WEIGHTS keys
        platform         : "linkedin", "whatsapp", "facebook", "instagram"
        notes            : Optional notes about the interaction
    """
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO connection_interactions "
            "(contact, interaction_type, platform, notes, date, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (contact, interaction_type, platform, notes,
             date.today().isoformat(), datetime.now().isoformat()),
        )
        conn.commit()
    logger.info("📊 Interaction logged: [%s] %s on %s", interaction_type, contact, platform)


# ──────────────────────────────────────────────
# CALCULATE STRENGTH SCORE
# ──────────────────────────────────────────────
def calculate_strength(contact: str) -> dict:
    """
    Calculate connection strength score for a contact.

    Args:
        contact : Contact's name

    Returns:
        Dict with score, level, interactions, last_interaction, trend
    """
    if not DB_FILE.exists():
        return _empty_strength(contact)

    cutoff = (date.today() - timedelta(days=RECENCY_DAYS)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT interaction_type, date FROM connection_interactions "
            "WHERE LOWER(contact) = LOWER(?) AND date >= ? "
            "ORDER BY date DESC",
            (contact, cutoff),
        ).fetchall()

    if not rows:
        return _empty_strength(contact)

    # Calculate weighted score with recency decay
    today      = date.today()
    raw_score  = 0
    total_count = len(rows)

    for interaction_type, interaction_date in rows:
        weight = INTERACTION_WEIGHTS.get(interaction_type, 3)

        # Recency decay: interactions lose 50% weight every 180 days
        try:
            days_ago = (today - date.fromisoformat(interaction_date)).days
        except Exception:
            days_ago = 365
        decay  = max(0.1, 1 - (days_ago / RECENCY_DAYS) * 0.9)
        raw_score += weight * decay

    # Normalize to 0-100
    score = min(100, int(raw_score * 2))

    # Get last interaction date
    last_date = rows[0][1] if rows else None

    # Calculate trend (compare last 90 days vs previous 90 days)
    trend = _calculate_trend(contact)

    # Determine level
    level = _get_level(score)

    logger.info(
        "📊 Connection strength for %s: %d/100 (%s) | Trend: %s",
        contact, score, level["name"], trend,
    )

    return {
        "contact":          contact,
        "score":            score,
        "level":            level,
        "total_interactions": total_count,
        "last_interaction": last_date,
        "trend":            trend,
    }


def _empty_strength(contact: str) -> dict:
    return {
        "contact":            contact,
        "score":              0,
        "level":              _get_level(0),
        "total_interactions": 0,
        "last_interaction":   None,
        "trend":              "neutral",
    }


def _get_level(score: int) -> dict:
    """Return level info based on score."""
    if score >= 81:
        return {"name": "Very Strong", "emoji": "⭐", "color": "#FFD700",
                "relationship": "close_friend"}
    elif score >= 61:
        return {"name": "Strong",      "emoji": "💙", "color": "#2196F3",
                "relationship": "close_friend"}
    elif score >= 41:
        return {"name": "Moderate",    "emoji": "🟢", "color": "#4CAF50",
                "relationship": "colleague"}
    elif score >= 21:
        return {"name": "Weak",        "emoji": "🟡", "color": "#FFC107",
                "relationship": "acquaintance"}
    else:
        return {"name": "Fading",      "emoji": "🔴", "color": "#F44336",
                "relationship": "acquaintance"}


def _calculate_trend(contact: str) -> str:
    """Calculate if connection is growing, stable, or fading."""
    if not DB_FILE.exists():
        return "neutral"

    today       = date.today()
    recent_cut  = (today - timedelta(days=90)).isoformat()
    prev_cut    = (today - timedelta(days=180)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        recent_count = conn.execute(
            "SELECT COUNT(*) FROM connection_interactions "
            "WHERE LOWER(contact) = LOWER(?) AND date >= ?",
            (contact, recent_cut),
        ).fetchone()[0]

        prev_count = conn.execute(
            "SELECT COUNT(*) FROM connection_interactions "
            "WHERE LOWER(contact) = LOWER(?) AND date >= ? AND date < ?",
            (contact, prev_cut, recent_cut),
        ).fetchone()[0]

    if recent_count > prev_count * 1.2:
        return "growing 📈"
    elif recent_count < prev_count * 0.8:
        return "fading 📉"
    else:
        return "stable ➡️"


# ──────────────────────────────────────────────
# GET ALL CONNECTIONS RANKED
# ──────────────────────────────────────────────
def get_top_connections(limit: int = 20) -> list[dict]:
    """
    Get top connections ranked by strength score.

    Returns:
        List of connection strength dicts, sorted by score descending.
    """
    if not DB_FILE.exists():
        return []

    with sqlite3.connect(DB_FILE) as conn:
        contacts = conn.execute(
            "SELECT DISTINCT contact FROM connection_interactions "
            "ORDER BY contact"
        ).fetchall()

    results = [calculate_strength(row[0]) for row in contacts]
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def get_fading_connections(threshold: int = 20) -> list[dict]:
    """
    Get connections whose strength is fading (score below threshold).
    These are contacts worth re-engaging with.
    """
    all_connections = get_top_connections(limit=100)
    return [c for c in all_connections if c["score"] <= threshold]


# ──────────────────────────────────────────────
# AUTO-LOG FROM HISTORY
# ──────────────────────────────────────────────
def sync_from_history():
    """
    Sync interaction data from the existing history table
    into connection_interactions for retroactive tracking.
    """
    if not DB_FILE.exists():
        return

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT contact, task, date FROM history WHERE dry_run = 0"
        ).fetchall()

    for contact, task, interaction_date in rows:
        # Map task names to interaction types
        if "Birthday" in task or "Wish" in task:
            itype = "birthday_wish"
        elif "Reply" in task:
            itype = "reply"
        elif "Follow" in task:
            itype = "follow_up"
        else:
            itype = "like"

        # Check if already logged
        with sqlite3.connect(DB_FILE) as conn:
            existing = conn.execute(
                "SELECT id FROM connection_interactions "
                "WHERE LOWER(contact) = LOWER(?) AND date = ? AND interaction_type = ?",
                (contact, interaction_date, itype),
            ).fetchone()

            if not existing:
                conn.execute(
                    "INSERT INTO connection_interactions "
                    "(contact, interaction_type, platform, notes, date, created_at) "
                    "VALUES (?, ?, 'linkedin', 'synced from history', ?, ?)",
                    (contact, itype, interaction_date, datetime.now().isoformat()),
                )
                conn.commit()

    logger.info("🔄 Synced interaction history for connection tracking.")