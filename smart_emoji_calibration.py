"""
Smart Emoji Calibration — Birthday Wishes Agent v8.0
Learns each contact's emoji usage pattern from their reply history,
then calibrates the birthday wish to match — never over-emojifying
a formal contact or sending a plain text wish to someone who replies with 🎉🔥💯.

Levels: none | minimal | moderate | heavy | very_heavy
Integrates with: agent.py, wish_variant_generator.py, wish_preview.py
"""

import sqlite3
import re
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = Path("agent_history.db")

# Emoji density levels and their rules
DENSITY_LEVELS = {
    "none":       {"label": "No emoji",     "emoji_per_100_words": 0,   "max_in_wish": 0},
    "minimal":    {"label": "1–2 emoji",    "emoji_per_100_words": 1,   "max_in_wish": 2},
    "moderate":   {"label": "2–4 emoji",    "emoji_per_100_words": 3,   "max_in_wish": 4},
    "heavy":      {"label": "4–7 emoji",    "emoji_per_100_words": 6,   "max_in_wish": 7},
    "very_heavy": {"label": "7+ emoji",     "emoji_per_100_words": 10,  "max_in_wish": 12},
}

# Emoji pools by category — used when injecting emoji into wishes
EMOJI_POOLS = {
    "celebration": ["🎉", "🎊", "🥳", "🎈", "🎂", "🎁"],
    "warm":        ["😊", "🤗", "💛", "🌟", "✨", "💫"],
    "motivational":["🚀", "💪", "🔥", "⚡", "🌟", "🏆"],
    "love":        ["❤️", "💙", "💚", "💜", "🧡", "💖"],
    "tech":        ["💻", "🛠️", "⚙️", "🔧", "🖥️", "📱"],
    "nature":      ["🌸", "🌿", "🌈", "🌻", "🍀", "🌺"],
}

# ── DB helpers ─────────────────────────────────────────────────────────────────

def init_emoji_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_emoji_profile (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL UNIQUE,
            contact_name    TEXT NOT NULL,
            density_level   TEXT NOT NULL,
            avg_emoji_count REAL NOT NULL DEFAULT 0,
            sample_size     INTEGER NOT NULL DEFAULT 0,
            top_emoji       TEXT,
            last_updated    TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reply_emoji_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id   TEXT NOT NULL,
            reply_text   TEXT NOT NULL,
            emoji_found  TEXT,
            emoji_count  INTEGER NOT NULL DEFAULT 0,
            word_count   INTEGER NOT NULL DEFAULT 0,
            logged_at    TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Emoji extraction ───────────────────────────────────────────────────────────

# Broad unicode emoji regex (covers most common ranges)
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols etc.
    "\U0001FA70-\U0001FAFF"  # extended symbols
    "\U00002300-\U000023FF"  # misc technical
    "]+",
    flags=re.UNICODE,
)

def extract_emoji(text: str) -> list[str]:
    """Return a flat list of all emoji found in text."""
    matches = EMOJI_PATTERN.findall(text)
    # Split multi-char emoji clusters into individual
    result = []
    for m in matches:
        result.extend(list(m))
    return result

def count_words(text: str) -> int:
    return len(re.findall(r'\w+', text))

def emoji_density_per_100(emoji_count: int, word_count: int) -> float:
    if word_count == 0:
        return 0.0
    return round((emoji_count / word_count) * 100, 2)


# ── Density classification ─────────────────────────────────────────────────────

def classify_density(avg_emoji_per_100: float) -> str:
    """Map average emoji-per-100-words to a density level name."""
    if avg_emoji_per_100 == 0:
        return "none"
    elif avg_emoji_per_100 <= 1.5:
        return "minimal"
    elif avg_emoji_per_100 <= 4:
        return "moderate"
    elif avg_emoji_per_100 <= 8:
        return "heavy"
    else:
        return "very_heavy"


# ── Reply history analysis ─────────────────────────────────────────────────────

def analyze_reply_history(replies: list[str]) -> dict:
    """
    Analyze a list of reply texts to build an emoji profile.

    Args:
        replies: List of raw reply strings from the contact.

    Returns:
        {
          density_level, avg_emoji_count, avg_emoji_per_100,
          top_emoji, sample_size, all_emoji_found
        }
    """
    if not replies:
        return {
            "density_level":    "minimal",
            "avg_emoji_count":  0,
            "avg_emoji_per_100": 0,
            "top_emoji":        [],
            "sample_size":      0,
            "all_emoji_found":  [],
        }

    total_emoji  = 0
    total_words  = 0
    all_emoji    = []

    for reply in replies:
        emoji_list  = extract_emoji(reply)
        word_count  = count_words(reply)
        total_emoji += len(emoji_list)
        total_words += word_count
        all_emoji.extend(emoji_list)

    avg_per_reply   = total_emoji / len(replies)
    avg_per_100     = emoji_density_per_100(total_emoji, total_words)
    density_level   = classify_density(avg_per_100)

    # Top 5 most-used emoji
    freq = {}
    for e in all_emoji:
        freq[e] = freq.get(e, 0) + 1
    top_emoji = sorted(freq, key=freq.get, reverse=True)[:5]

    return {
        "density_level":     density_level,
        "avg_emoji_count":   round(avg_per_reply, 2),
        "avg_emoji_per_100": avg_per_100,
        "top_emoji":         top_emoji,
        "sample_size":       len(replies),
        "all_emoji_found":   all_emoji,
    }


# ── Profile persistence ───────────────────────────────────────────────────────

def save_emoji_profile(contact_id: str, contact_name: str, profile: dict):
    init_emoji_table()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO contact_emoji_profile
            (contact_id, contact_name, density_level, avg_emoji_count,
             sample_size, top_emoji, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id) DO UPDATE SET
            density_level   = excluded.density_level,
            avg_emoji_count = excluded.avg_emoji_count,
            sample_size     = excluded.sample_size,
            top_emoji       = excluded.top_emoji,
            last_updated    = excluded.last_updated
    """, (
        contact_id,
        contact_name,
        profile["density_level"],
        profile["avg_emoji_count"],
        profile["sample_size"],
        " ".join(profile["top_emoji"]),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


def load_emoji_profile(contact_id: str) -> Optional[dict]:
    """Load saved emoji profile from DB. Returns None if not found."""
    if not DB_PATH.exists():
        return None
    init_emoji_table()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute(
        "SELECT density_level, avg_emoji_count, sample_size, top_emoji "
        "FROM contact_emoji_profile WHERE contact_id = ?",
        (contact_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "density_level":   row[0],
        "avg_emoji_count": row[1],
        "sample_size":     row[2],
        "top_emoji":       row[3].split() if row[3] else [],
    }


def log_reply(contact_id: str, reply_text: str):
    """Append a new reply to the raw log table for future re-analysis."""
    init_emoji_table()
    emoji_list = extract_emoji(reply_text)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO reply_emoji_log
            (contact_id, reply_text, emoji_found, emoji_count, word_count, logged_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        contact_id,
        reply_text,
        " ".join(emoji_list),
        len(emoji_list),
        count_words(reply_text),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


# ── Wish calibration ──────────────────────────────────────────────────────────

def calibrate_wish(
    wish_text: str,
    density_level: str,
    top_emoji: Optional[list[str]] = None,
    industry: str = "general",
) -> str:
    """
    Adjust emoji count in a wish to match the contact's calibrated density level.

    Strategy:
    - "none"      → strip all emoji
    - "minimal"   → keep at most 2, prefer contact's top emoji
    - "moderate"  → keep/add up to 4
    - "heavy"     → keep/add up to 7
    - "very_heavy"→ keep/add up to 12, use contact's favourites prominently

    Args:
        wish_text:     The AI-generated wish text.
        density_level: Target density level (from contact profile).
        top_emoji:     Contact's most-used emoji (preferred for injection).
        industry:      Used to pick thematically relevant emoji if needed.

    Returns:
        Calibrated wish string.
    """
    max_emoji   = DENSITY_LEVELS[density_level]["max_in_wish"]
    current_emoji = extract_emoji(wish_text)
    current_count = len(current_emoji)

    # ── Strip all emoji for "none" ─────────────────────────────────────────
    if density_level == "none":
        return EMOJI_PATTERN.sub("", wish_text).strip()

    # ── Already within target range ────────────────────────────────────────
    if current_count <= max_emoji:
        if current_count == 0 and max_emoji > 0:
            # Need to inject emoji — wish has none but contact uses them
            wish_text = _inject_emoji(wish_text, max_emoji, top_emoji, industry)
        return wish_text

    # ── Too many emoji — trim from end of wish ─────────────────────────────
    if current_count > max_emoji:
        wish_text = _trim_emoji(wish_text, max_emoji)

    return wish_text


def _pick_emoji(count: int, top_emoji: Optional[list], industry: str) -> list[str]:
    """Pick `count` emoji to inject, preferring contact's top emoji."""
    pool = list(top_emoji) if top_emoji else []
    # Fill remainder from themed pools
    industry_map = {"tech": "tech", "design": "warm", "startup": "motivational"}
    themed_pool  = EMOJI_POOLS.get(industry_map.get(industry, "warm"), EMOJI_POOLS["warm"])
    fallback     = EMOJI_POOLS["celebration"] + themed_pool
    combined     = pool + [e for e in fallback if e not in pool]
    # Cycle if needed
    result = []
    for i in range(count):
        result.append(combined[i % len(combined)])
    return result


def _inject_emoji(wish_text: str, target_count: int, top_emoji: Optional[list], industry: str) -> str:
    """Inject emoji naturally into a wish that currently has none."""
    emojis  = _pick_emoji(target_count, top_emoji, industry)
    sentences = re.split(r'(?<=[.!?])\s+', wish_text.strip())

    if not sentences:
        return wish_text + " " + " ".join(emojis)

    # Distribute: put 1 emoji after first sentence, rest after last
    result = []
    per_sentence = max(1, target_count // len(sentences))
    emoji_idx    = 0

    for i, sentence in enumerate(sentences):
        result.append(sentence)
        if emoji_idx < len(emojis):
            to_add = emojis[emoji_idx:emoji_idx + per_sentence]
            result[-1] = result[-1].rstrip() + " " + "".join(to_add)
            emoji_idx += per_sentence

    return " ".join(result)


def _trim_emoji(wish_text: str, max_keep: int) -> str:
    """Remove excess emoji from a wish, keeping only `max_keep`."""
    found   = []
    removed = 0

    def replacer(match):
        nonlocal removed
        if len(found) < max_keep:
            found.append(match.group())
            return match.group()
        else:
            removed += 1
            return ""

    result = EMOJI_PATTERN.sub(replacer, wish_text)
    return result.strip()


# ── Prompt instruction ────────────────────────────────────────────────────────

def get_emoji_prompt_instruction(density_level: str, top_emoji: Optional[list] = None) -> str:
    """
    Return a prompt fragment to inject into the AI wish generation call
    so the model uses the right emoji density from the start.
    """
    level   = DENSITY_LEVELS[density_level]
    top_str = " ".join(top_emoji[:3]) if top_emoji else ""
    fav_str = f" Their favourite emoji are: {top_str}." if top_str else ""

    instructions = {
        "none":       f"Use NO emoji whatsoever. Plain text only, professional.",
        "minimal":    f"Use at most 1–2 emoji total, placed at natural pause points.{fav_str}",
        "moderate":   f"Use 2–4 emoji naturally spread through the message.{fav_str}",
        "heavy":      f"Use 4–7 emoji — this contact loves emoji. Mirror their style.{fav_str}",
        "very_heavy": f"Use 7+ emoji throughout — this contact communicates primarily with emoji. Match their energy.{fav_str}",
    }
    return instructions.get(density_level, instructions["moderate"])


# ── Main entry point ──────────────────────────────────────────────────────────

def get_emoji_calibration(
    contact_id:   str,
    contact_name: str,
    replies:      Optional[list[str]] = None,
    verbose:      bool = True,
) -> dict:
    """
    Main entry point. Analyzes reply history (or loads cached profile) and
    returns everything needed to calibrate the wish emoji density.

    Args:
        contact_id:   Unique contact identifier.
        contact_name: Human-readable name.
        replies:      List of reply strings. If None, loads from DB cache.
        verbose:      Print analysis to console.

    Returns:
        {
          density_level, label, max_in_wish,
          top_emoji, avg_emoji_count, sample_size,
          prompt_instruction, from_cache
        }
    """
    init_emoji_table()

    # Try to load from cache first
    if replies is None:
        cached = load_emoji_profile(contact_id)
        if cached:
            if verbose:
                print(f"[EmojiCalibration] Loaded cached profile for {contact_name}: "
                      f"{cached['density_level']} (n={cached['sample_size']})")
            level = cached["density_level"]
            return {
                "density_level":      level,
                "label":              DENSITY_LEVELS[level]["label"],
                "max_in_wish":        DENSITY_LEVELS[level]["max_in_wish"],
                "top_emoji":          cached["top_emoji"],
                "avg_emoji_count":    cached["avg_emoji_count"],
                "sample_size":        cached["sample_size"],
                "prompt_instruction": get_emoji_prompt_instruction(level, cached["top_emoji"]),
                "from_cache":         True,
            }
        else:
            # No data at all — default to moderate
            if verbose:
                print(f"[EmojiCalibration] No history for {contact_name} — defaulting to moderate")
            level = "moderate"
            return {
                "density_level":      level,
                "label":              DENSITY_LEVELS[level]["label"],
                "max_in_wish":        DENSITY_LEVELS[level]["max_in_wish"],
                "top_emoji":          [],
                "avg_emoji_count":    0,
                "sample_size":        0,
                "prompt_instruction": get_emoji_prompt_instruction(level),
                "from_cache":         False,
            }

    # Analyze fresh reply list
    profile = analyze_reply_history(replies)
    save_emoji_profile(contact_id, contact_name, profile)

    level = profile["density_level"]

    if verbose:
        print(f"[EmojiCalibration] Contact: {contact_name}")
        print(f"  Sample size:      {profile['sample_size']} replies")
        print(f"  Avg emoji/reply:  {profile['avg_emoji_count']}")
        print(f"  Avg per 100 words:{profile['avg_emoji_per_100']}")
        print(f"  Density level:    {level} ({DENSITY_LEVELS[level]['label']})")
        print(f"  Top emoji:        {''.join(profile['top_emoji']) or 'none'}")

    return {
        "density_level":      level,
        "label":              DENSITY_LEVELS[level]["label"],
        "max_in_wish":        DENSITY_LEVELS[level]["max_in_wish"],
        "top_emoji":          profile["top_emoji"],
        "avg_emoji_count":    profile["avg_emoji_count"],
        "sample_size":        profile["sample_size"],
        "prompt_instruction": get_emoji_prompt_instruction(level, profile["top_emoji"]),
        "from_cache":         False,
    }


# ── Streamlit panel ───────────────────────────────────────────────────────────

def render_emoji_calibration_panel(contact_id: str, contact_name: str, replies: Optional[list] = None):
    """
    Drop into wish_preview.py or wish_variant_generator.py to show the
    contact's emoji profile and let the user see/override the density level.

    Usage:
        from smart_emoji_calibration import render_emoji_calibration_panel
        render_emoji_calibration_panel(contact_id, contact_name, replies)
    """
    try:
        import streamlit as st
    except ImportError:
        return

    result = get_emoji_calibration(contact_id, contact_name, replies, verbose=False)
    level  = result["density_level"]
    color  = {"none": "#8b949e", "minimal": "#58a6ff", "moderate": "#3fb950",
               "heavy": "#d29922", "very_heavy": "#f78166"}.get(level, "#3fb950")

    st.markdown("**😊 Emoji Calibration**")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(
            f'Detected level: <span style="color:{color};font-weight:700">'
            f'{result["label"]}</span> '
            f'(max {result["max_in_wish"]} per wish)',
            unsafe_allow_html=True,
        )
        if result["top_emoji"]:
            st.caption(f"Contact's favourites: {'  '.join(result['top_emoji'])}")
        st.caption(f"Based on {result['sample_size']} replies · "
                   f"avg {result['avg_emoji_count']:.1f} emoji/reply")
    with col2:
        override = st.selectbox(
            "Override",
            list(DENSITY_LEVELS.keys()),
            index=list(DENSITY_LEVELS.keys()).index(level),
            key=f"emoji_override_{contact_id}",
            label_visibility="collapsed",
        )
        if override != level:
            st.caption(f"Override: {DENSITY_LEVELS[override]['label']}")


# ── CLI self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_emoji_table()
    print("=== Smart Emoji Calibration — self test ===\n")

    # Simulate reply histories for 4 contacts with very different emoji styles
    contacts = [
        {
            "id":      "urn_rakib_001",
            "name":    "Rakib Hossain",
            "replies": [
                "Thank you so much! Really appreciate it.",
                "Appreciate it, means a lot.",
                "Thanks! Hope to catch up soon.",
            ],
            "industry": "tech",
        },
        {
            "id":      "urn_nadia_002",
            "name":    "Nadia Islam",
            "replies": [
                "Aww thank you! 😊🙏",
                "Haha appreciate it! 😄",
                "Thanks so much!! 😍✨",
            ],
            "industry": "design",
        },
        {
            "id":      "urn_tanvir_003",
            "name":    "Tanvir Ahmed",
            "replies": [
                "Thank you brother! 🚀🔥💯",
                "🙌🔥🎉 appreciate it so much bro!!",
                "Thanks!! 💪🏆🔥🎊🎉",
            ],
            "industry": "startup",
        },
        {
            "id":      "urn_mim_004",
            "name":    "Mim Chowdhury",
            "replies": [],   # no history
            "industry": "tech",
        },
    ]

    sample_wish = (
        "Happy Birthday! Hope your day is as amazing as the work you do. "
        "Wishing you a brilliant year ahead, filled with success and happiness."
    )

    for c in contacts:
        print(f"\n--- {c['name']} ---")
        calibration = get_emoji_calibration(c["id"], c["name"], c["replies"] or None)
        calibrated_wish = calibrate_wish(
            sample_wish,
            calibration["density_level"],
            calibration["top_emoji"],
            c["industry"],
        )
        print(f"  Wish (calibrated): {calibrated_wish}")
        print(f"  Emoji in result:   {''.join(extract_emoji(calibrated_wish)) or '(none)'}")
        print(f"  Prompt instruction: {calibration['prompt_instruction'][:80]}...")
