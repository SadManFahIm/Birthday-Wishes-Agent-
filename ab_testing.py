"""
ab_testing.py
─────────────
<<<<<<< HEAD
Wish A/B Testing module for Birthday Wishes Agent.

Generates two different wish styles (Variant A and Variant B),
sends each to different contacts, tracks which one gets more replies,
and automatically uses the winning variant going forward.

How it works:
  1. For each birthday contact, randomly assigns Variant A or B
  2. Variant A: Warm and personal style
     Variant B: Enthusiastic and fun style
  3. Tracks if the contact replied to the wish
  4. After enough data, determines the winning variant
  5. Agent automatically uses the winner for future wishes

Metrics tracked:
  - Send count per variant
  - Reply count per variant
  - Reply rate per variant
  - Win/loss determination

Usage:
    from ab_testing import (
        get_ab_variant,
        log_ab_send,
        log_ab_reply,
        get_ab_results,
        get_winning_variant
    )
"""

import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
import random
=======
Wish A/B Testing with Auto-Learning — Birthday Wishes Agent 🆕

Upgraded from 2-variant (A/B) to 5-style testing with full auto-learning.

How it works:
  1. 5 wish styles are tested: Warm & Personal, Enthusiastic & Fun,
     Professional, Funny & Playful, Inspirational
  2. Each contact gets the current best-performing style
     (or a random one during the exploration phase)
  3. Reply rate per style is tracked in SQLite
  4. Auto-learning activates after MIN_SENDS_FOR_WINNER sends per style
  5. The winning style is used automatically going forward
  6. Recent sends are weighted more heavily (decay factor) so the agent
     adapts to changing trends over time

Backward compatible:
  - Old variant "A" / "B" records in ab_tests table are preserved
  - All original functions still work exactly as before
  - New style keys: "A", "B", "C", "D", "E"

New additions (🆕):
  - get_best_style()           → best style key via decay-weighted reply rate
  - get_all_style_stats()      → full stats for all 5 styles
  - log_ab_reply_by_style()    → mark reply for a specific style key
  - get_full_ab_report()       → human-readable report for dashboard / digest
  - build_ab_instructions()    → updated to show 5-style status
  - generate_ab_wish()         → supports all 5 style keys (A–E)
"""

import logging
import random
import sqlite3
from datetime import date, datetime
from pathlib import Path
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)

logger  = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

<<<<<<< HEAD
# Minimum sends before declaring a winner
MIN_SENDS_FOR_WINNER = 20


# ──────────────────────────────────────────────
# VARIANT DEFINITIONS
# ──────────────────────────────────────────────
=======
# Minimum sends per style before auto-learning activates
MIN_SENDS_FOR_WINNER = 20

# Decay weighting: sends in last RECENT_DAYS_WINDOW days count RECENT_WEIGHT× more
RECENT_DAYS_WINDOW = 30
RECENT_WEIGHT      = 2.0


# ──────────────────────────────────────────────
# STYLE DEFINITIONS
# ──────────────────────────────────────────────

# Original 2 variants — kept for backward compatibility
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
AB_VARIANTS = {
    "A": {
        "name":        "Warm & Personal",
        "description": "Heartfelt, mentions their name and job/context naturally",
        "style":       "warm, personal, genuine, 2-3 sentences, 1-2 emoji",
        "example":     "Happy Birthday Rahul! 🎂 Hope your journey at Google "
                       "keeps inspiring the engineer in you. "
                       "Wishing you an incredible year ahead!",
    },
    "B": {
        "name":        "Enthusiastic & Fun",
        "description": "Upbeat, energetic, celebratory tone",
        "style":       "enthusiastic, fun, celebratory, 1-2 sentences, 2-3 emoji",
        "example":     "Happy Birthday Rahul!! 🎉🥳 Hope today is absolutely "
                       "AMAZING — you deserve all the celebrations! 🎂",
    },
}

<<<<<<< HEAD
=======
# Extended 5-style definitions (A and B match AB_VARIANTS above)
WISH_STYLES = {
    "A": {
        "name":        "Warm & Personal",
        "description": "Heartfelt, mentions their name and job/context naturally",
        "style":       "warm, personal, genuine, 2-3 sentences, 1-2 emoji",
        "example":     "Happy Birthday Rahul! 🎂 Hope your journey at Google "
                       "keeps inspiring the engineer in you. "
                       "Wishing you an incredible year ahead!",
    },
    "B": {
        "name":        "Enthusiastic & Fun",
        "description": "Upbeat, energetic, celebratory tone",
        "style":       "enthusiastic, fun, celebratory, 1-2 sentences, 2-3 emoji",
        "example":     "Happy Birthday Rahul!! 🎉🥳 Hope today is absolutely "
                       "AMAZING — you deserve all the celebrations! 🎂",
    },
    "C": {
        "name":        "Professional",
        "description": "Formal, polished, suitable for senior or professional contacts",
        "style":       "professional, respectful, concise, no slang, 1-2 emoji max",
        "example":     "Wishing you a wonderful birthday, Rahul. "
                       "Hope this year brings continued success and new milestones. 🎂",
    },
    "D": {
        "name":        "Funny & Playful",
        "description": "Light humour, witty, casual — best for close connections",
        "style":       "playful, witty, light humour, casual, 2-3 emoji",
        "example":     "Another trip around the sun, Rahul! 🌍🎂 "
                       "You're getting better with age — like a fine app update! 😄",
    },
    "E": {
        "name":        "Inspirational",
        "description": "Motivating, forward-looking, aspirational tone",
        "style":       "inspirational, uplifting, forward-looking, 2-3 sentences, 1-2 emoji",
        "example":     "Happy Birthday Rahul! 🚀 May this year unlock doors "
                       "you haven't even knocked on yet. "
                       "Here's to your best chapter yet! ✨",
    },
}

>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)

# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
<<<<<<< HEAD
def init_ab_table():
    """Create the A/B testing tracking table."""
=======

def init_ab_table():
    """Create the A/B testing tracking table (backward compatible)."""
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ab_tests (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                variant      TEXT    NOT NULL,
                wish_text    TEXT,
                replied      INTEGER DEFAULT 0,
                reply_text   TEXT,
                date         TEXT    NOT NULL,
                dry_run      INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  A/B testing table ready.")


# ──────────────────────────────────────────────
<<<<<<< HEAD
# VARIANT ASSIGNMENT
# ──────────────────────────────────────────────
def get_ab_variant(contact: str) -> str:
    """
    Get the A/B variant for a contact.
    Uses the winning variant if enough data exists,
    otherwise assigns randomly for fair testing.

    Returns:
        "A" or "B"
    """
    winner = get_winning_variant()

=======
# AUTO-LEARNING — STYLE SELECTION  🆕
# ──────────────────────────────────────────────

def get_all_style_stats() -> dict:
    """
    Returns per-style stats with decay weighting.

    Recent sends (last RECENT_DAYS_WINDOW days) count RECENT_WEIGHT×
    more than older sends — so the agent adapts to recent trends.

    Returns:
        Dict[style_key] → {sent, replies, weighted_sent,
                           weighted_replies, reply_rate}
    """
    if not DB_FILE.exists():
        return {k: {"sent": 0, "replies": 0, "weighted_sent": 0.0,
                    "weighted_replies": 0.0, "reply_rate": 0.0}
                for k in WISH_STYLES}

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT variant, replied, date FROM ab_tests WHERE dry_run = 0"
        ).fetchall()

    today = date.today()
    stats = {k: {"sent": 0, "replies": 0, "weighted_sent": 0.0,
                 "weighted_replies": 0.0, "reply_rate": 0.0}
             for k in WISH_STYLES}

    for variant, replied, sent_date_str in rows:
        if variant not in stats:
            continue
        try:
            sent_date = date.fromisoformat(sent_date_str)
        except ValueError:
            sent_date = today

        age_days = (today - sent_date).days
        weight   = RECENT_WEIGHT if age_days <= RECENT_DAYS_WINDOW else 1.0

        stats[variant]["sent"]          += 1
        stats[variant]["weighted_sent"] += weight
        if replied:
            stats[variant]["replies"]          += 1
            stats[variant]["weighted_replies"] += weight

    for s in stats.values():
        ws = s["weighted_sent"]
        s["reply_rate"] = round(s["weighted_replies"] / ws, 4) if ws else 0.0

    return stats


def get_best_style() -> str:
    """
    Auto-learning style picker.

    Exploration phase (any style < MIN_SENDS_FOR_WINNER sends):
      → pick randomly so all styles get tested fairly.

    Exploitation phase (all styles tested enough):
      → pick the style with the highest weighted reply rate.

    Returns: "A", "B", "C", "D", or "E"
    """
    stats      = get_all_style_stats()
    all_styles = list(WISH_STYLES.keys())

    # Exploration
    for key in all_styles:
        if stats.get(key, {}).get("sent", 0) < MIN_SENDS_FOR_WINNER:
            chosen = random.choice(all_styles)
            logger.info(
                "🎲 A/B Explore: Style '%s' only %d/%d sends. Random → %s (%s)",
                key, stats.get(key, {}).get("sent", 0), MIN_SENDS_FOR_WINNER,
                chosen, WISH_STYLES[chosen]["name"],
            )
            return chosen

    # Exploitation: highest weighted reply rate
    best = max(all_styles, key=lambda k: stats.get(k, {}).get("reply_rate", 0.0))
    rate = stats.get(best, {}).get("reply_rate", 0.0)
    logger.info(
        "🏆 A/B Auto-Learn: Best style → %s (%s) | Weighted reply rate: %.1f%%",
        best, WISH_STYLES[best]["name"], rate * 100,
    )
    return best


# ──────────────────────────────────────────────
# ORIGINAL FUNCTIONS — BACKWARD COMPATIBLE
# ──────────────────────────────────────────────

def get_ab_variant(contact: str) -> str:
    """
    Backward-compatible: returns "A" or "B".
    Uses get_best_style() internally; maps C/D/E → A or B
    so old callers still receive a valid variant.
    """
    winner = get_winning_variant()
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
    if winner:
        logger.info("🏆 Using winning variant %s for %s", winner, contact)
        return winner

<<<<<<< HEAD
    # Random assignment for fair testing
    variant = random.choice(["A", "B"])
    logger.info("🎲 Randomly assigned variant %s to %s", variant, contact)
    return variant


# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
=======
    best   = get_best_style()
    mapped = best if best in ("A", "B") else random.choice(["A", "B"])
    logger.info("🎲 A/B variant for %s → %s (best style: %s)", contact, mapped, best)
    return mapped


>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
def log_ab_send(
    contact: str,
    variant: str,
    wish_text: str,
    dry_run: bool = True,
) -> int:
<<<<<<< HEAD
    """
    Log that a wish was sent with a specific variant.

    Returns:
        The ID of the new record.
    """
=======
    """Log a sent wish. Accepts any style key A–E."""
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute(
            "INSERT INTO ab_tests "
            "(contact, variant, wish_text, date, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (contact, variant, wish_text,
             date.today().isoformat(), int(dry_run),
             datetime.now().isoformat()),
        )
        record_id = cursor.lastrowid
        conn.commit()
<<<<<<< HEAD
    logger.info("📊 A/B send logged: Variant %s → %s (ID: %d)",
                variant, contact, record_id)
=======
    logger.info("📊 A/B logged: Style %s → %s (ID: %d)", variant, contact, record_id)
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
    return record_id


def log_ab_reply(contact: str, reply_text: str = ""):
<<<<<<< HEAD
    """
    Log that a contact replied to our wish.
    Marks the most recent send to this contact as replied.
    """
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE ab_tests SET replied = 1, reply_text = ? "
            "WHERE LOWER(contact) = LOWER(?) AND replied = 0 AND dry_run = 0 "
            "ORDER BY created_at DESC LIMIT 1",
            (reply_text, contact),
        )
        conn.commit()
    logger.info("💬 A/B reply logged for %s", contact)
=======
    """Mark most recent wish to a contact as replied (backward compat)."""
    log_ab_reply_by_style(contact, reply_text=reply_text)


def log_ab_reply_by_style(contact: str, style_key: str = "", reply_text: str = ""):
    """🆕 Mark reply for a contact. Optionally filter by style_key."""
    with sqlite3.connect(DB_FILE) as conn:
        if style_key:
            conn.execute("""
                UPDATE ab_tests SET replied = 1, reply_text = ?
                WHERE  LOWER(contact) = LOWER(?) AND variant = ?
                  AND  replied = 0 AND dry_run = 0
                  AND  id = (
                      SELECT id FROM ab_tests
                      WHERE  LOWER(contact) = LOWER(?) AND variant = ?
                        AND  replied = 0 AND dry_run = 0
                      ORDER BY created_at DESC LIMIT 1
                  )
            """, (reply_text, contact, style_key, contact, style_key))
        else:
            conn.execute("""
                UPDATE ab_tests SET replied = 1, reply_text = ?
                WHERE  LOWER(contact) = LOWER(?)
                  AND  replied = 0 AND dry_run = 0
                  AND  id = (
                      SELECT id FROM ab_tests
                      WHERE  LOWER(contact) = LOWER(?)
                        AND  replied = 0 AND dry_run = 0
                      ORDER BY created_at DESC LIMIT 1
                  )
            """, (reply_text, contact, contact))
        conn.commit()
    logger.info("💬 A/B reply marked: %s (style: %s)", contact, style_key or "any")
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)


# ──────────────────────────────────────────────
# RESULTS & ANALYTICS
# ──────────────────────────────────────────────
<<<<<<< HEAD
def get_ab_results() -> dict:
    """
    Get full A/B test results with reply rates for each variant.

    Returns:
        Dict with stats for variant A, variant B, and winner.
=======

def get_ab_results() -> dict:
    """
    Backward-compatible A vs B results + winner.
    Also includes 'all_styles' key with extended 5-style stats.
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
    """
    if not DB_FILE.exists():
        return _empty_results()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT variant, COUNT(*) as sends, SUM(replied) as replies "
<<<<<<< HEAD
            "FROM ab_tests WHERE dry_run = 0 "
            "GROUP BY variant",
        ).fetchall()

    stats = {}
    for row in rows:
        variant = row[0]
        sends   = row[1] or 0
        replies = row[2] or 0
        rate    = round((replies / sends * 100), 1) if sends > 0 else 0.0
        stats[variant] = {
            "variant":    variant,
            "name":       AB_VARIANTS.get(variant, {}).get("name", variant),
            "sends":      sends,
            "replies":    replies,
            "reply_rate": rate,
        }

    # Fill missing variants
    for v in ["A", "B"]:
        if v not in stats:
            stats[v] = {
                "variant":    v,
                "name":       AB_VARIANTS[v]["name"],
                "sends":      0,
                "replies":    0,
                "reply_rate": 0.0,
            }

    # Determine winner
    winner = None
    a_rate = stats.get("A", {}).get("reply_rate", 0)
    b_rate = stats.get("B", {}).get("reply_rate", 0)
    a_sends = stats.get("A", {}).get("sends", 0)
    b_sends = stats.get("B", {}).get("sends", 0)

    if a_sends >= MIN_SENDS_FOR_WINNER and b_sends >= MIN_SENDS_FOR_WINNER:
        if a_rate > b_rate + 5:   # A wins by more than 5%
            winner = "A"
        elif b_rate > a_rate + 5: # B wins by more than 5%
            winner = "B"
        else:
            winner = None  # Too close to call

    logger.info(
        "📊 A/B Results — A: %.1f%% (%d sends) | B: %.1f%% (%d sends) | Winner: %s",
        a_rate, a_sends, b_rate, b_sends, winner or "Too close",
    )

    return {
        "variant_a":        stats.get("A", {}),
        "variant_b":        stats.get("B", {}),
        "winner":           winner,
        "total_sends":      a_sends + b_sends,
        "min_for_winner":   MIN_SENDS_FOR_WINNER,
        "test_concluded":   winner is not None,
        "conclusion_note":  _get_conclusion_note(winner, a_rate, b_rate,
                                                  a_sends, b_sends),
=======
            "FROM ab_tests WHERE dry_run = 0 GROUP BY variant",
        ).fetchall()

    stats = {}
    for variant, sends, replies in rows:
        sends   = sends or 0
        replies = replies or 0
        rate    = round((replies / sends * 100), 1) if sends > 0 else 0.0
        name    = WISH_STYLES.get(variant, AB_VARIANTS.get(variant, {})).get("name", variant)
        stats[variant] = {
            "variant": variant, "name": name,
            "sends": sends, "replies": replies, "reply_rate": rate,
        }

    for v in ["A", "B"]:
        if v not in stats:
            stats[v] = {"variant": v, "name": AB_VARIANTS[v]["name"],
                        "sends": 0, "replies": 0, "reply_rate": 0.0}

    a_rate  = stats.get("A", {}).get("reply_rate", 0)
    b_rate  = stats.get("B", {}).get("reply_rate", 0)
    a_sends = stats.get("A", {}).get("sends", 0)
    b_sends = stats.get("B", {}).get("sends", 0)

    winner = None
    if a_sends >= MIN_SENDS_FOR_WINNER and b_sends >= MIN_SENDS_FOR_WINNER:
        if a_rate > b_rate + 5:
            winner = "A"
        elif b_rate > a_rate + 5:
            winner = "B"

    return {
        "variant_a":      stats.get("A", {}),
        "variant_b":      stats.get("B", {}),
        "winner":         winner,
        "total_sends":    a_sends + b_sends,
        "min_for_winner": MIN_SENDS_FOR_WINNER,
        "test_concluded": winner is not None,
        "conclusion_note": _get_conclusion_note(winner, a_rate, b_rate, a_sends, b_sends),
        "all_styles":     get_all_style_stats(),  # 🆕
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
    }


def _empty_results() -> dict:
    return {
        "variant_a":      {"variant": "A", "name": AB_VARIANTS["A"]["name"],
                           "sends": 0, "replies": 0, "reply_rate": 0.0},
        "variant_b":      {"variant": "B", "name": AB_VARIANTS["B"]["name"],
                           "sends": 0, "replies": 0, "reply_rate": 0.0},
        "winner":         None,
        "total_sends":    0,
        "min_for_winner": MIN_SENDS_FOR_WINNER,
        "test_concluded": False,
<<<<<<< HEAD
        "conclusion_note": f"Need at least {MIN_SENDS_FOR_WINNER} sends per variant to declare a winner.",
    }


def _get_conclusion_note(
    winner: str | None,
    a_rate: float,
    b_rate: float,
    a_sends: int,
    b_sends: int,
) -> str:
    if winner == "A":
        return (
            f"✅ Variant A wins! '{AB_VARIANTS['A']['name']}' style gets "
            f"{a_rate:.1f}% reply rate vs {b_rate:.1f}% for Variant B. "
            f"Agent will now use Variant A for all wishes."
        )
    elif winner == "B":
        return (
            f"✅ Variant B wins! '{AB_VARIANTS['B']['name']}' style gets "
            f"{b_rate:.1f}% reply rate vs {a_rate:.1f}% for Variant A. "
            f"Agent will now use Variant B for all wishes."
        )
    elif a_sends >= MIN_SENDS_FOR_WINNER and b_sends >= MIN_SENDS_FOR_WINNER:
        return (
            f"🟡 Too close to call! A: {a_rate:.1f}% vs B: {b_rate:.1f}%. "
            f"Continuing to test both variants equally."
        )
    else:
        remaining = MIN_SENDS_FOR_WINNER - min(a_sends, b_sends)
        return f"⏳ Still testing — need {remaining} more sends to declare a winner."


def get_winning_variant() -> str | None:
    """
    Return the winning variant if test has concluded, else None.
    Returns None if test is still running.
    """
    results = get_ab_results()
    return results.get("winner")


def get_recent_ab_sends(limit: int = 20) -> list[dict]:
    """Get the most recent A/B test sends."""
=======
        "conclusion_note": f"Need {MIN_SENDS_FOR_WINNER} sends per style to declare a winner.",
        "all_styles":     {},
    }


def _get_conclusion_note(winner, a_rate, b_rate, a_sends, b_sends) -> str:
    if winner == "A":
        return (f"✅ Style A wins! {a_rate:.1f}% vs {b_rate:.1f}%. "
                f"Using '{AB_VARIANTS['A']['name']}' going forward.")
    if winner == "B":
        return (f"✅ Style B wins! {b_rate:.1f}% vs {a_rate:.1f}%. "
                f"Using '{AB_VARIANTS['B']['name']}' going forward.")
    if a_sends >= MIN_SENDS_FOR_WINNER and b_sends >= MIN_SENDS_FOR_WINNER:
        return f"🟡 Too close! A: {a_rate:.1f}% vs B: {b_rate:.1f}%. Continuing."
    remaining = MIN_SENDS_FOR_WINNER - min(a_sends, b_sends)
    return f"⏳ Need {remaining} more sends to declare a winner."


def get_winning_variant() -> str | None:
    """Return winning variant (A/B) if concluded, else None."""
    return get_ab_results().get("winner")


def get_recent_ab_sends(limit: int = 20) -> list[dict]:
    """Get most recent A/B sends."""
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
    if not DB_FILE.exists():
        return []
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT contact, variant, wish_text, replied, date "
            "FROM ab_tests WHERE dry_run = 0 "
<<<<<<< HEAD
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"contact": r[0], "variant": r[1], "wish_text": r[2],
         "replied": bool(r[3]), "date": r[4]}
        for r in rows
    ]


# ──────────────────────────────────────────────
# WISH GENERATOR FOR A/B
# ──────────────────────────────────────────────
=======
            "ORDER BY created_at DESC LIMIT ?", (limit,),
        ).fetchall()
    return [{"contact": r[0], "variant": r[1], "wish_text": r[2],
             "replied": bool(r[3]), "date": r[4]} for r in rows]


# ──────────────────────────────────────────────
# FULL REPORT  🆕
# ──────────────────────────────────────────────

def get_full_ab_report() -> str:
    """
    Human-readable report for all 5 styles.
    Used in dashboard or weekly digest email.
    """
    stats = get_all_style_stats()
    if not any(s["sent"] for s in stats.values()):
        return "📊 No A/B data yet — send some wishes first!"

    best = get_best_style()
    lines = [
        "📊 A/B Auto-Learning Report — Wish Style Performance",
        "─" * 58,
        f"  {'Key':<4} {'Style':<22} {'Sent':>5} {'Replies':>8} {'Rate':>8}  {'Weighted':>8}",
        "  " + "─" * 54,
    ]

    sorted_keys = sorted(
        WISH_STYLES.keys(),
        key=lambda k: stats.get(k, {}).get("reply_rate", 0.0),
        reverse=True,
    )

    for key in sorted_keys:
        s     = stats.get(key, {"sent": 0, "replies": 0, "reply_rate": 0.0, "weighted_sent": 0.0})
        name  = WISH_STYLES[key]["name"]
        medal = "🏆" if key == best else "  "
        rate  = s["reply_rate"] * 100
        lines.append(
            f"{medal} {key:<4} {name:<22} {s['sent']:>5} "
            f"{s['replies']:>8} {rate:>7.1f}%  {s.get('weighted_sent', 0.0):>7.1f}w"
        )

    lines += [
        "  " + "─" * 54,
        f"  🏆 Best style now: {best} — {WISH_STYLES[best]['name']}",
        f"  ⚖️  Sends in last {RECENT_DAYS_WINDOW} days weighted {RECENT_WEIGHT}× (adapts to trends).",
        f"  🔬 Auto-learning activates after {MIN_SENDS_FOR_WINNER} sends per style.",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────
# WISH GENERATOR — supports A–E  🆕
# ──────────────────────────────────────────────

>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
async def generate_ab_wish(
    llm,
    name: str,
    profile_info: dict,
    variant: str,
) -> str:
    """
<<<<<<< HEAD
    Generate a wish in the style of the given variant.

    Args:
        llm          : LangChain LLM instance
        name         : Contact's first name
        profile_info : Profile details
        variant      : "A" or "B"

    Returns:
        Generated wish string.
    """
    from langchain_core.messages import HumanMessage

    v         = AB_VARIANTS.get(variant, AB_VARIANTS["A"])
    style     = v["style"]
    example   = v["example"]
    job_title = profile_info.get("job_title", "")
    company   = profile_info.get("company", "")

    context = f"They work as {job_title} at {company}." if job_title and company \
              else f"They work as {job_title}." if job_title \
              else ""
=======
    Generate a wish in the style of the given variant (A–E).
    Falls back to Style A if unknown variant given.
    """
    from langchain_core.messages import HumanMessage

    v         = WISH_STYLES.get(variant, WISH_STYLES["A"])
    job_title = profile_info.get("job_title", "")
    company   = profile_info.get("company", "")
    context   = (
        f"They work as {job_title} at {company}." if job_title and company
        else f"They work as {job_title}." if job_title
        else ""
    )
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)

    prompt = f"""
Write a birthday wish for {name}.

<<<<<<< HEAD
Style: {style}
{context}

Example of this style:
"{example}"

Rules:
  ✅ Start with "Happy Birthday {name}!"
  ✅ Follow the style exactly
  ✅ Keep it genuine and personal
  ❌ Don't copy the example — write a fresh wish
=======
Style: {v['style']}
{context}

Example of this style:
"{v['example']}"

Rules:
  ✅ Start with "Happy Birthday {name}!"
  ✅ Match the style exactly — tone, length, emoji count
  ✅ Keep it genuine and personal
  ❌ Do not copy the example word for word
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)

Reply with ONLY the wish text.
"""
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
<<<<<<< HEAD
        wish     = response.content.strip().strip('"').strip("'")
        logger.info("✨ A/B Variant %s wish for %s: %s",
                    variant, name, wish[:60] + "...")
=======
        wish = response.content.strip().strip('"').strip("'")
        logger.info("✨ A/B Style %s wish for %s: %s", variant, name, wish[:60] + "...")
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
        return wish
    except Exception as e:
        logger.error("❌ A/B wish generation failed: %s", e)
        return f"Happy Birthday {name}! 🎂 Wishing you an amazing day!"


# ──────────────────────────────────────────────
<<<<<<< HEAD
# AGENT INSTRUCTIONS
# ──────────────────────────────────────────────
def build_ab_instructions(variant: str) -> str:
    """Build A/B testing instructions for the browser agent."""
    v = AB_VARIANTS.get(variant, AB_VARIANTS["A"])
    results = get_ab_results()

    status_line = ""
    if results["test_concluded"] and results["winner"]:
        status_line = f"\n  🏆 TEST CONCLUDED: Variant {results['winner']} is the winner!"
    else:
        a_rate = results["variant_a"]["reply_rate"]
        b_rate = results["variant_b"]["reply_rate"]
        status_line = f"\n  📊 Current: A={a_rate:.1f}% reply rate | B={b_rate:.1f}% reply rate"

    return f"""
  A/B TESTING INSTRUCTIONS:
  Using Variant {variant} — "{v['name']}"
  Style: {v['style']}
  {status_line}

  Write all birthday wishes in this style:
  Example: "{v['example']}"

  After sending, note if they reply — this helps determine
  which wish style gets more engagement.
=======
# AGENT INSTRUCTIONS  🆕
# ──────────────────────────────────────────────

def build_ab_instructions(variant: str = "") -> str:
    """
    Build A/B testing instructions for the browser agent.
    If no variant given, auto-picks the best style.
    """
    if not variant:
        variant = get_best_style()

    v       = WISH_STYLES.get(variant, WISH_STYLES["A"])
    results = get_ab_results()
    stats   = get_all_style_stats()

    if results["test_concluded"] and results["winner"]:
        status = (f"🏆 Winner: Style {results['winner']} — "
                  f"{WISH_STYLES[results['winner']]['name']}")
    else:
        top3   = sorted(WISH_STYLES.keys(),
                        key=lambda k: stats.get(k, {}).get("reply_rate", 0.0),
                        reverse=True)[:3]
        status = "📊 Top styles: " + " | ".join(
            f"{k}={stats.get(k,{}).get('reply_rate',0)*100:.1f}%"
            for k in top3
        )

    return f"""
  A/B TESTING — AUTO-LEARNING WISH STYLE:
  Using Style {variant} — "{v['name']}"
  Guide: {v['style']}
  {status}

  Write all birthday wishes in this style today.
  Example: "{v['example']}"

  After sending, report replies as:
    REPLIED: <contact_name>
  This trains the auto-learning system to improve over time.
>>>>>>> c6eea7e (feat: upgrade A/B testing with auto-learning — 5 styles + decay weighting)
"""