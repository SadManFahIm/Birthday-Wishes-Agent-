"""
ab_testing.py
─────────────
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

logger  = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Minimum sends before declaring a winner
MIN_SENDS_FOR_WINNER = 20


# ──────────────────────────────────────────────
# VARIANT DEFINITIONS
# ──────────────────────────────────────────────
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


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_ab_table():
    """Create the A/B testing tracking table."""
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

    if winner:
        logger.info("🏆 Using winning variant %s for %s", winner, contact)
        return winner

    # Random assignment for fair testing
    variant = random.choice(["A", "B"])
    logger.info("🎲 Randomly assigned variant %s to %s", variant, contact)
    return variant


# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────
def log_ab_send(
    contact: str,
    variant: str,
    wish_text: str,
    dry_run: bool = True,
) -> int:
    """
    Log that a wish was sent with a specific variant.

    Returns:
        The ID of the new record.
    """
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
    logger.info("📊 A/B send logged: Variant %s → %s (ID: %d)",
                variant, contact, record_id)
    return record_id


def log_ab_reply(contact: str, reply_text: str = ""):
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


# ──────────────────────────────────────────────
# RESULTS & ANALYTICS
# ──────────────────────────────────────────────
def get_ab_results() -> dict:
    """
    Get full A/B test results with reply rates for each variant.

    Returns:
        Dict with stats for variant A, variant B, and winner.
    """
    if not DB_FILE.exists():
        return _empty_results()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT variant, COUNT(*) as sends, SUM(replied) as replies "
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
    if not DB_FILE.exists():
        return []
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT contact, variant, wish_text, replied, date "
            "FROM ab_tests WHERE dry_run = 0 "
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
async def generate_ab_wish(
    llm,
    name: str,
    profile_info: dict,
    variant: str,
) -> str:
    """
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

    prompt = f"""
Write a birthday wish for {name}.

Style: {style}
{context}

Example of this style:
"{example}"

Rules:
  ✅ Start with "Happy Birthday {name}!"
  ✅ Follow the style exactly
  ✅ Keep it genuine and personal
  ❌ Don't copy the example — write a fresh wish

Reply with ONLY the wish text.
"""
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        wish     = response.content.strip().strip('"').strip("'")
        logger.info("✨ A/B Variant %s wish for %s: %s",
                    variant, name, wish[:60] + "...")
        return wish
    except Exception as e:
        logger.error("❌ A/B wish generation failed: %s", e)
        return f"Happy Birthday {name}! 🎂 Wishing you an amazing day!"


# ──────────────────────────────────────────────
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
"""