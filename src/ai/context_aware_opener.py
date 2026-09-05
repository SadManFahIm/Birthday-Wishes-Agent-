"""
Context-Aware Opening Line — Birthday Wishes Agent v8.0
Scans a contact's recent LinkedIn activity (posts, job changes, achievements)
and generates a hyper-specific opening line for their birthday wish —
so it never starts with generic openers like "Wishing you a great birthday!"

Flow:
  1. Fetch recent LinkedIn activity for the contact (browser_use / API)
  2. Extract the most wish-worthy signal (post, milestone, achievement)
  3. Generate a natural opening line referencing that signal
  4. Return the line + full context for injection into the AI wish prompt

Integrates with: agent.py, wish_preview.py, wish_style_memory.py
"""

import sqlite3
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = Path("agent_history.db")

# Signal priority order — higher index = more wish-worthy
SIGNAL_PRIORITY = [
    "new_job",
    "promotion",
    "work_anniversary",
    "graduation",
    "award",
    "product_launch",
    "funding",
    "viral_post",
    "recent_post",
    "recent_comment",
]

SIGNAL_LABELS = {
    "new_job":          "Started a new job",
    "promotion":        "Got promoted",
    "work_anniversary": "Work anniversary milestone",
    "graduation":       "Graduated",
    "award":            "Won an award or recognition",
    "product_launch":   "Launched a product or feature",
    "funding":          "Announced funding or investment",
    "viral_post":       "Posted something that got a lot of engagement",
    "recent_post":      "Posted recently on LinkedIn",
    "recent_comment":   "Was active on LinkedIn recently",
}

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_context_table():
    """Create contact_context_cache table for storing fetched activity signals."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_context_cache (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id     TEXT NOT NULL,
            contact_name   TEXT NOT NULL,
            signal_type    TEXT NOT NULL,
            signal_text    TEXT NOT NULL,
            signal_date    TEXT,
            opening_line   TEXT,
            used           INTEGER DEFAULT 0,
            fetched_at     TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Activity signal extraction ────────────────────────────────────────────────

def extract_signal_from_activity(activity_items: list[dict]) -> Optional[dict]:
    """
    Given a list of raw activity items from LinkedIn scrape, pick the
    most wish-worthy signal based on SIGNAL_PRIORITY.

    Each activity_item should be a dict with keys:
        type (str), text (str), date (str, ISO format optional)

    Returns the best signal dict or None if nothing found.
    """
    if not activity_items:
        return None

    best = None
    best_priority = -1

    for item in activity_items:
        signal_type = item.get("type", "recent_post")
        priority    = SIGNAL_PRIORITY.index(signal_type) if signal_type in SIGNAL_PRIORITY else 0
        if priority > best_priority:
            best_priority = priority
            best = item

    return best


def detect_signal_type_from_text(text: str) -> str:
    """
    Heuristic: infer the signal type from raw post/notification text
    when structured type is not available from the scraper.
    """
    text_lower = text.lower()

    patterns = {
        "new_job":          [r"excited to (join|announce|start)", r"joining .+ as", r"new role", r"first day at"],
        "promotion":        [r"promoted to", r"new title", r"stepping up", r"taking on the role"],
        "work_anniversary": [r"\d+ year[s]? at", r"work anniversary", r"years with the team"],
        "graduation":       [r"graduated", r"degree in", r"proud to have completed"],
        "award":            [r"honored to", r"award", r"recognition", r"winner", r"nominated"],
        "product_launch":   [r"launched", r"shipped", r"releasing", r"introducing", r"new product", r"new feature"],
        "funding":          [r"raised", r"funding", r"series [a-z]", r"investment", r"backed by"],
        "viral_post":       [],  # detected via engagement count, not text
    }

    for signal_type, regexes in patterns.items():
        for pattern in regexes:
            if re.search(pattern, text_lower):
                return signal_type

    return "recent_post"


# ── Opening line generation ───────────────────────────────────────────────────

def build_opening_line_prompt(contact_name: str, signal: dict) -> str:
    """
    Build the prompt fragment to send to the AI for generating a
    context-aware opening line from the extracted signal.
    """
    first_name   = contact_name.split()[0]
    signal_type  = signal.get("type", "recent_post")
    signal_text  = signal.get("text", "")
    signal_label = SIGNAL_LABELS.get(signal_type, "recent activity")

    prompt = f"""
You are writing the opening line of a birthday wish for {first_name}.

Recent LinkedIn activity ({signal_label}):
\"\"\"{signal_text}\"\"\"

Write ONE opening sentence (max 25 words) that:
- Naturally references this specific activity WITHOUT quoting it verbatim
- Feels conversational and genuine, not like an AI wrote it
- Connects the activity to the birthday occasion
- Does NOT start with "Happy Birthday" (that comes later in the wish)

Examples of good openers:
- "Saw your post about the product launch — what a year to have a birthday!"
- "Between leading that new initiative and hitting this milestone, you deserve a proper celebration."
- "Couldn't let your birthday pass without mentioning how impressive that recent announcement was."

Return ONLY the opening line, nothing else.
""".strip()

    return prompt


def generate_opening_line_mock(contact_name: str, signal: dict) -> str:
    """
    Mock generator — returns a realistic opening line without calling the AI.
    Replace with real LangChain / Gemini call in production using
    build_opening_line_prompt() as the prompt.
    """
    first_name  = contact_name.split()[0]
    signal_type = signal.get("type", "recent_post")
    signal_text = signal.get("text", "")

    # Trim signal text to a short reference phrase
    words       = signal_text.split()
    short_ref   = " ".join(words[:6]) + ("…" if len(words) > 6 else "")

    templates = {
        "new_job": [
            f"Seeing you step into this new role just as your birthday arrives — what perfect timing, {first_name}!",
            f"A new chapter at a new company, and now a birthday on top of it — you're on a roll, {first_name}.",
        ],
        "promotion": [
            f"A promotion and a birthday in the same season — you're clearly making {datetime.now().year} count, {first_name}.",
            f"Couldn't let your birthday pass without acknowledging that impressive step up you just made.",
        ],
        "work_anniversary": [
            f"A work milestone and a birthday — clearly {first_name} runs on big moments.",
            f"Between the work anniversary and today, you've given everyone around you a lot to celebrate lately.",
        ],
        "graduation": [
            f"Graduating and having a birthday so close together — the universe really stacked the celebrations for you, {first_name}.",
            f"Huge week: degree earned, birthday incoming — you deserve every bit of it.",
        ],
        "award": [
            f"Saw the recognition you received recently — well deserved, and now your birthday too? Great timing.",
            f"Between that award and today, it feels like the world is finally catching up to what people around you already knew.",
        ],
        "product_launch": [
            f"Saw the launch — impressive work. And now a birthday right after? Celebrate both properly, {first_name}.",
            f"Shipping something meaningful and then having a birthday feels on-brand for someone like you.",
        ],
        "funding": [
            f"The announcement was exciting to see — and now a birthday on top of it. Big month, {first_name}.",
            f"Between closing that round and celebrating today, you've earned a proper break.",
        ],
        "viral_post": [
            f"That post got a lot of people talking — and now your birthday? You know how to make an entrance.",
            f"Saw your recent post make the rounds — and now a birthday. You're having quite a run, {first_name}.",
        ],
        "recent_post": [
            f"Was just reading what you shared recently — good stuff. And now I see it's your birthday too!",
            f"Your post about '{short_ref}' caught my eye, and then I realized — it's your birthday. Perfect excuse to reach out.",
        ],
        "recent_comment": [
            f"You've been active on LinkedIn lately, which made it even easier to notice this important day, {first_name}.",
            f"Glad the feed reminded me — {first_name}, today's a day worth celebrating properly.",
        ],
    }

    options = templates.get(signal_type, templates["recent_post"])
    import random
    return random.choice(options)


# ── Cache helpers ─────────────────────────────────────────────────────────────

def cache_opening_line(
    contact_id:   str,
    contact_name: str,
    signal:       dict,
    opening_line: str,
):
    """Save generated opening line to DB cache for audit and timeline display."""
    init_context_table()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO contact_context_cache
            (contact_id, contact_name, signal_type, signal_text, signal_date, opening_line, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contact_id,
            contact_name,
            signal.get("type", "recent_post"),
            signal.get("text", ""),
            signal.get("date", ""),
            opening_line,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_cached_opening_line(contact_id: str, max_age_hours: int = 24) -> Optional[str]:
    """
    Return a recently cached opening line if available and fresh enough.
    Avoids re-fetching LinkedIn activity for the same contact on the same day.
    """
    if not DB_PATH.exists():
        return None
    cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    row    = conn.execute(
        """
        SELECT opening_line FROM contact_context_cache
        WHERE contact_id = ? AND fetched_at > ?
        ORDER BY fetched_at DESC LIMIT 1
        """,
        (contact_id, cutoff),
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ── Main entry point ──────────────────────────────────────────────────────────

def get_context_aware_opening(
    contact_id:      str,
    contact_name:    str,
    activity_items:  Optional[list[dict]] = None,
    use_cache:       bool = True,
    verbose:         bool = True,
) -> dict:
    """
    Main entry point called from agent.py before generating a birthday wish.

    Args:
        contact_id:     Unique contact identifier.
        contact_name:   Human-readable name.
        activity_items: List of activity dicts scraped from LinkedIn.
                        If None, returns a fallback generic opener.
        use_cache:      Check DB cache first before regenerating.
        verbose:        Print progress to console.

    Returns:
        {
          "opening_line":   str  — the context-aware opening sentence,
          "signal_type":    str  — what kind of activity was detected,
          "signal_text":    str  — raw activity text used as context,
          "prompt_snippet": str  — ready-to-inject prompt fragment for AI,
          "from_cache":     bool — whether this came from the DB cache,
        }
    """
    init_context_table()

    # 1. Check cache
    if use_cache:
        cached = get_cached_opening_line(contact_id)
        if cached:
            if verbose:
                print(f"[ContextOpener] Using cached opening line for {contact_name}")
            return {
                "opening_line":   cached,
                "signal_type":    "cached",
                "signal_text":    "",
                "prompt_snippet": f'Start the wish with this opening line: "{cached}"',
                "from_cache":     True,
            }

    # 2. Extract best signal from activity
    signal = None
    if activity_items:
        # Auto-detect signal type if not provided
        for item in activity_items:
            if "type" not in item and "text" in item:
                item["type"] = detect_signal_type_from_text(item["text"])
        signal = extract_signal_from_activity(activity_items)

    # 3. Fallback signal if no activity
    if not signal:
        if verbose:
            print(f"[ContextOpener] No activity found for {contact_name} — using warm fallback")
        first_name   = contact_name.split()[0]
        opening_line = f"Couldn't let today pass without reaching out, {first_name} — hope it's a brilliant one."
        return {
            "opening_line":   opening_line,
            "signal_type":    "fallback",
            "signal_text":    "",
            "prompt_snippet": f'Start the wish with this opening line: "{opening_line}"',
            "from_cache":     False,
        }

    # 4. Generate opening line
    opening_line = generate_opening_line_mock(contact_name, signal)

    if verbose:
        print(f"[ContextOpener] Contact:     {contact_name}")
        print(f"  Signal type: {signal['type']} — {SIGNAL_LABELS.get(signal['type'], '')}")
        print(f"  Signal text: {signal.get('text', '')[:80]}...")
        print(f"  Opening line: {opening_line}")

    # 5. Cache result
    cache_opening_line(contact_id, contact_name, signal, opening_line)

    return {
        "opening_line":   opening_line,
        "signal_type":    signal.get("type", "recent_post"),
        "signal_text":    signal.get("text", ""),
        "prompt_snippet": f'Start the wish with this opening line: "{opening_line}"',
        "from_cache":     False,
    }


# ── Streamlit panel (embed in wish_preview.py) ───────────────────────────────

def render_context_opener_panel(contact_id: str, contact_name: str, activity_items: Optional[list] = None):
    """
    Drop into wish_preview.py to show the detected signal and opening line
    alongside the live wish editor.

    Usage:
        from context_aware_opener import render_context_opener_panel
        render_context_opener_panel(contact_id, contact_name, activity_items)
    """
    try:
        import streamlit as st
    except ImportError:
        return

    result = get_context_aware_opening(contact_id, contact_name, activity_items, verbose=False)

    st.markdown("**🔍 Context-Aware Opening Line**")
    if result["signal_type"] not in ("fallback", "cached"):
        st.caption(f"Signal detected: `{result['signal_type']}` — {SIGNAL_LABELS.get(result['signal_type'], '')}")
    st.info(f'"{result["opening_line"]}"')
    if result["from_cache"]:
        st.caption("⚡ From cache — fetched earlier today")


# ── CLI self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_context_table()

    print("=== Context-Aware Opening Line — self test ===\n")

    TEST_ACTIVITIES = [
        {
            "type": "product_launch",
            "text": "Thrilled to announce we just shipped v2.0 of our core platform — 6 months of work and the team absolutely crushed it.",
            "date": (datetime.now() - timedelta(days=3)).isoformat(),
        },
        {
            "type": "recent_post",
            "text": "Reflecting on what it means to build in public — the good, the hard, and everything in between.",
            "date": (datetime.now() - timedelta(days=10)).isoformat(),
        },
    ]

    contacts = [
        ("linkedin_urn_rakib_001", "Rakib Hossain",  TEST_ACTIVITIES),
        ("linkedin_urn_nadia_002", "Nadia Islam",     [{"text": "Excited to join bKash as Head of Design!", "date": datetime.now().isoformat()}]),
        ("linkedin_urn_tanvir_003","Tanvir Ahmed",    []),  # no activity — fallback test
    ]

    for cid, name, activity in contacts:
        print(f"\n--- {name} ---")
        result = get_context_aware_opening(cid, name, activity)
        print(f"  ✅ Opening: {result['opening_line']}")
        print(f"  Signal:   {result['signal_type']}")
