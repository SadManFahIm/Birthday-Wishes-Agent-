"""
Wish Style Memory — Birthday Wishes Agent v8.0
Tracks which wish style was used for each contact in previous years and ensures
the agent always picks a fresh angle — never repeating the same style twice in a row.

Styles: funny | formal | poetic | warm | motivational | nostalgic | short_punchy
"""

import sqlite3
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = Path("agent_history.db")

ALL_STYLES = [
    "funny",
    "formal",
    "poetic",
    "warm",
    "motivational",
    "nostalgic",
    "short_punchy",
]

STYLE_DESCRIPTIONS = {
    "funny":        "Light-hearted, playful, includes a gentle joke or pun",
    "formal":       "Professional, polished, no emoji, suitable for senior contacts",
    "poetic":       "Lyrical, metaphorical, reads like a short verse",
    "warm":         "Heartfelt and personal, feels like a close friend wrote it",
    "motivational": "Energetic and forward-looking, focuses on the year ahead",
    "nostalgic":    "References shared history, memories, or how far they've come",
    "short_punchy": "Brief, punchy, confident — no filler, maximum impact",
}

# ── DB Setup ──────────────────────────────────────────────────────────────────

def init_style_memory_table():
    """Create wish_style_memory table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wish_style_memory (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id    TEXT    NOT NULL,
            contact_name  TEXT    NOT NULL,
            platform      TEXT    NOT NULL,
            style_used    TEXT    NOT NULL,
            wish_snippet  TEXT,
            year          INTEGER NOT NULL,
            timestamp     TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Core logic ────────────────────────────────────────────────────────────────

def get_used_styles(contact_id: str) -> list[dict]:
    """
    Return all previously used styles for a contact, ordered newest first.
    Each entry: { year, style_used, wish_snippet }
    """
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT year, style_used, wish_snippet
        FROM wish_style_memory
        WHERE contact_id = ?
        ORDER BY year DESC
        """,
        (contact_id,),
    ).fetchall()
    conn.close()
    return [{"year": r[0], "style_used": r[1], "wish_snippet": r[2]} for r in rows]


def pick_fresh_style(contact_id: str, avoid_last_n: int = 2) -> str:
    """
    Choose a style that hasn't been used in the last `avoid_last_n` years.
    Falls back to a random style if all styles have been recently used.

    Args:
        contact_id:   Unique identifier for the contact (LinkedIn URN, phone, etc.)
        avoid_last_n: How many recent years to avoid repeating. Default 2.

    Returns:
        Style name string.
    """
    history = get_used_styles(contact_id)
    recently_used = {entry["style_used"] for entry in history[:avoid_last_n]}
    available = [s for s in ALL_STYLES if s not in recently_used]

    if not available:
        # All styles used recently — pick least-recently-used
        used_ordered = [entry["style_used"] for entry in history]
        for style in reversed(used_ordered):
            if style in ALL_STYLES:
                available = [style]
                break
        if not available:
            available = ALL_STYLES

    chosen = random.choice(available)
    return chosen


def record_style_used(
    contact_id: str,
    contact_name: str,
    platform: str,
    style_used: str,
    wish_snippet: Optional[str] = None,
    year: Optional[int] = None,
):
    """
    Save the style used for a contact this year so future runs can avoid it.

    Args:
        contact_id:   Unique contact identifier.
        contact_name: Human-readable name (for dashboard display).
        platform:     Platform the wish was sent on (LinkedIn, WhatsApp, etc.).
        style_used:   The style name that was used.
        wish_snippet: First 120 chars of the wish (optional, for timeline display).
        year:         Override year (defaults to current year).
    """
    init_style_memory_table()
    year = year or datetime.now().year
    snippet = (wish_snippet or "")[:120]
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO wish_style_memory
            (contact_id, contact_name, platform, style_used, wish_snippet, year, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (contact_id, contact_name, platform, style_used, snippet, year, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_style_prompt_instruction(style: str) -> str:
    """
    Return the prompt instruction to inject into the AI wish generation call
    so the model writes in the chosen style.
    """
    instructions = {
        "funny": (
            "Write the birthday wish in a light-hearted, playful tone. "
            "Include a gentle joke or a clever pun related to their job or industry. "
            "Keep it fun but never offensive."
        ),
        "formal": (
            "Write the birthday wish in a professional, polished tone. "
            "Use full sentences, no emoji, no slang. "
            "Suitable for a senior executive or someone you respect professionally."
        ),
        "poetic": (
            "Write the birthday wish in a lyrical, slightly poetic style. "
            "Use a metaphor or a short verse-like structure. "
            "It should feel artistic and thoughtful, not generic."
        ),
        "warm": (
            "Write the birthday wish in a genuinely warm, heartfelt tone — "
            "as if written by a close friend who truly knows and cares about the person. "
            "Personal, sincere, and uplifting."
        ),
        "motivational": (
            "Write the birthday wish in an energetic, forward-looking tone. "
            "Focus on the exciting year ahead, their potential, and what they can achieve. "
            "Inspiring without being preachy."
        ),
        "nostalgic": (
            "Write the birthday wish with a touch of nostalgia. "
            "Reference shared history, how far they've come, or a meaningful memory. "
            "Reflective and meaningful."
        ),
        "short_punchy": (
            "Write the birthday wish in a brief, punchy, confident style. "
            "No filler words. Maximum impact in minimum words. "
            "2-3 sentences at most. Bold and memorable."
        ),
    }
    return instructions.get(style, instructions["warm"])


def get_style_history_summary(contact_id: str) -> str:
    """
    Return a human-readable summary of past wish styles for dashboard display.
    """
    history = get_used_styles(contact_id)
    if not history:
        return "No wish history — all styles available."
    lines = [f"  {entry['year']}: {entry['style_used']}" for entry in history]
    return "Past styles used:\n" + "\n".join(lines)


# ── Integration helper (called from agent.py) ─────────────────────────────────

def get_wish_style_for_contact(
    contact_id: str,
    contact_name: str,
    avoid_last_n: int = 2,
    verbose: bool = True,
) -> dict:
    """
    Main entry point. Returns everything agent.py needs to generate a fresh wish.

    Returns:
        {
          "style":       str   — chosen style name,
          "description": str   — one-line style description,
          "prompt":      str   — instruction to inject into AI prompt,
          "history":     list  — past style records for this contact,
        }
    """
    init_style_memory_table()
    style   = pick_fresh_style(contact_id, avoid_last_n=avoid_last_n)
    history = get_used_styles(contact_id)

    if verbose:
        recently = [h["style_used"] for h in history[:avoid_last_n]]
        print(f"[WishStyleMemory] Contact: {contact_name}")
        print(f"  Recently used styles: {recently or 'none'}")
        print(f"  Chosen fresh style:   {style} — {STYLE_DESCRIPTIONS[style]}")

    return {
        "style":       style,
        "description": STYLE_DESCRIPTIONS[style],
        "prompt":      get_style_prompt_instruction(style),
        "history":     history,
    }


# ── Streamlit dashboard panel ─────────────────────────────────────────────────

def render_style_memory_panel(contact_id: str, contact_name: str):
    """
    Embed this in wish_preview.py or command_center.py to show a contact's
    wish style history and the recommended fresh style for this year.

    Usage:
        from wish_style_memory import render_style_memory_panel
        render_style_memory_panel(contact_id, contact_name)
    """
    try:
        import streamlit as st
    except ImportError:
        print("Streamlit not available — skipping dashboard render.")
        return

    result  = get_wish_style_for_contact(contact_id, contact_name, verbose=False)
    history = result["history"]

    st.markdown("**🎨 Wish Style Memory**")
    st.markdown(
        f"Chosen style for {datetime.now().year}: "
        f"`{result['style']}` — _{result['description']}_"
    )

    if history:
        st.markdown("Past styles used:")
        for entry in history:
            snippet_display = f'"{entry["wish_snippet"][:60]}…"' if entry.get("wish_snippet") else ""
            st.markdown(
                f"- **{entry['year']}** → `{entry['style_used']}` {snippet_display}"
            )
    else:
        st.caption("No history yet — all styles available for this contact.")


# ── Quick CLI test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_style_memory_table()

    # Simulate 3 years of history for a test contact
    TEST_ID   = "linkedin_urn_rakib_001"
    TEST_NAME = "Rakib Hossain"

    print("=== Wish Style Memory — self test ===\n")

    # Year 1
    record_style_used(TEST_ID, TEST_NAME, "LinkedIn", "funny",
                      "Happy Birthday Rakib! Hope your servers are as stable as your good mood today 🎂", year=2022)
    # Year 2
    record_style_used(TEST_ID, TEST_NAME, "LinkedIn", "formal",
                      "Dear Rakib, wishing you a wonderful birthday and continued success.", year=2023)
    # Year 3 — what should we pick?
    result = get_wish_style_for_contact(TEST_ID, TEST_NAME, avoid_last_n=2)
    print(f"\nFresh style selected: {result['style']}")
    print(f"Prompt instruction:\n  {result['prompt']}")
    print(f"\nHistory summary:\n{get_style_history_summary(TEST_ID)}")
