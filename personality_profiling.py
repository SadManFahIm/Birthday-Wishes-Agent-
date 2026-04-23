"""
personality_profiling.py
━━━━━━━━━━━━━━━━━━━━━━━━
Analyzes a LinkedIn contact's recent posts to detect their personality type
using the MBTI / Big Five framework, then stores results in SQLite and uses
them to generate a personality-aware birthday wish.

Tables created:
  personality_profiles  — one row per contact, stores type + traits + summary
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from browser_use import Agent, Browser
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

DB_FILE = Path("agent_history.db")

# ─────────────────────────────────────────────
# 1. DB SETUP
# ─────────────────────────────────────────────

def init_personality_table():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS personality_profiles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                contact         TEXT NOT NULL UNIQUE,
                profile_url     TEXT,
                mbti_type       TEXT,
                dominant_traits TEXT,
                tone            TEXT,
                interests       TEXT,
                communication_style TEXT,
                confidence_score    REAL,
                raw_summary     TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("🧠 personality_profiles table ready.")


def save_personality_profile(
    contact: str,
    profile_url: str,
    mbti_type: str,
    dominant_traits: list[str],
    tone: str,
    interests: list[str],
    communication_style: str,
    confidence_score: float,
    raw_summary: str,
):
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO personality_profiles
                (contact, profile_url, mbti_type, dominant_traits, tone,
                 interests, communication_style, confidence_score,
                 raw_summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact) DO UPDATE SET
                profile_url        = excluded.profile_url,
                mbti_type          = excluded.mbti_type,
                dominant_traits    = excluded.dominant_traits,
                tone               = excluded.tone,
                interests          = excluded.interests,
                communication_style= excluded.communication_style,
                confidence_score   = excluded.confidence_score,
                raw_summary        = excluded.raw_summary,
                updated_at         = excluded.updated_at
        """, (
            contact, profile_url, mbti_type,
            json.dumps(dominant_traits, ensure_ascii=False),
            tone,
            json.dumps(interests, ensure_ascii=False),
            communication_style,
            confidence_score,
            raw_summary,
            now, now,
        ))
        conn.commit()
    logger.info("💾 Personality saved for: %s → %s", contact, mbti_type)


def get_personality_profile(contact: str) -> dict | None:
    if not DB_FILE.exists():
        return None
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT * FROM personality_profiles WHERE LOWER(contact) = LOWER(?)",
            (contact,)
        ).fetchone()
    if not row:
        return None
    cols = [
        "id", "contact", "profile_url", "mbti_type", "dominant_traits",
        "tone", "interests", "communication_style", "confidence_score",
        "raw_summary", "created_at", "updated_at",
    ]
    data = dict(zip(cols, row))
    data["dominant_traits"] = json.loads(data["dominant_traits"] or "[]")
    data["interests"]       = json.loads(data["interests"]       or "[]")
    return data


def get_all_personality_profiles() -> list[dict]:
    if not DB_FILE.exists():
        return []
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT * FROM personality_profiles ORDER BY updated_at DESC"
        ).fetchall()
    cols = [
        "id", "contact", "profile_url", "mbti_type", "dominant_traits",
        "tone", "interests", "communication_style", "confidence_score",
        "raw_summary", "created_at", "updated_at",
    ]
    result = []
    for row in rows:
        data = dict(zip(cols, row))
        data["dominant_traits"] = json.loads(data["dominant_traits"] or "[]")
        data["interests"]       = json.loads(data["interests"]       or "[]")
        result.append(data)
    return result


# ─────────────────────────────────────────────
# 2. BROWSER TASK BUILDERS
# ─────────────────────────────────────────────

def build_profile_scrape_task(
    contact_name: str,
    profile_url: str,
    already_logged_in: bool,
    username: str,
    password: str,
) -> str:
    login_block = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in else
        f"Go to https://linkedin.com and log in:\n"
        f"  Email: {username}\n  Password: {password}\n"
        "Handle MFA if prompted.\n"
    )
    return f"""
Open the browser. {login_block}

GOAL: Collect the last 10 public LinkedIn posts from the contact below.

Contact name : {contact_name}
Profile URL  : {profile_url}

STEPS:
1. Open the profile URL.
2. Scroll to the "Activity" or "Posts" section.
3. Collect up to 10 recent posts (text only, skip pure image/video posts
   with no caption).
4. For each post record:
   - Post text (first 400 characters)
   - Approximate date (e.g. "2 days ago", "last week")
   - Number of likes / reactions (if visible)
   - Number of comments (if visible)

OUTPUT FORMAT — respond ONLY with a JSON object:
{{
  "contact": "{contact_name}",
  "profile_url": "{profile_url}",
  "posts": [
    {{
      "text": "...",
      "date": "...",
      "likes": 0,
      "comments": 0
    }}
  ]
}}

If the profile is private or has no posts, return:
{{"contact": "{contact_name}", "profile_url": "{profile_url}", "posts": []}}
"""


def build_personality_analysis_task(contact_name: str, posts_json: str) -> str:
    return f"""
You are an expert psychologist and communication analyst.

Analyze the LinkedIn posts below from '{contact_name}' and determine their
personality profile.

POSTS DATA:
{posts_json}

INSTRUCTIONS:
1. Detect their MBTI type (e.g. INTJ, ENFP, ISTJ …).
   — If posts are too few/neutral, make your best educated guess and set
     confidence_score below 0.5.

2. Identify the top 3–5 Big Five / personality TRAITS most evident
   (e.g. "analytical", "empathetic", "ambitious", "creative", "humorous").

3. Describe their TONE in one word
   (formal | casual | inspirational | technical | humorous | emotional | neutral).

4. List up to 5 INTERESTS inferred from the posts
   (e.g. "leadership", "AI/tech", "travel", "fitness", "entrepreneurship").

5. Describe their preferred COMMUNICATION STYLE in one sentence
   (e.g. "Direct and data-driven with occasional humor").

6. Assign a CONFIDENCE SCORE between 0.0 (no posts) and 1.0 (very clear pattern).

7. Write a 2–3 sentence RAW SUMMARY about their personality.

RESPOND ONLY with a valid JSON object — no markdown, no extra text:
{{
  "mbti_type": "INTJ",
  "dominant_traits": ["analytical", "strategic", "direct"],
  "tone": "formal",
  "interests": ["AI/tech", "leadership", "entrepreneurship"],
  "communication_style": "Data-driven and concise with a focus on results.",
  "confidence_score": 0.82,
  "raw_summary": "..."
}}
"""


# ─────────────────────────────────────────────
# 3. PERSONALITY-AWARE WISH BUILDER
# ─────────────────────────────────────────────

def build_personality_wish_prompt(contact_name: str, profile: dict) -> str:
    traits   = ", ".join(profile.get("dominant_traits", []))
    interests = ", ".join(profile.get("interests", []))
    return f"""
Write a LinkedIn birthday wish for {contact_name}.

Their personality profile:
- MBTI type         : {profile.get('mbti_type', 'Unknown')}
- Dominant traits   : {traits}
- Tone preference   : {profile.get('tone', 'neutral')}
- Interests         : {interests}
- Communication style: {profile.get('communication_style', '')}

RULES:
• Match their tone exactly (e.g. formal → no emojis; casual → warm and light).
• Reference 1–2 of their interests naturally (don't force it).
• Keep it under 60 words.
• Sound like a genuine human wrote it — not a template.
• End with exactly ONE relevant emoji.

Respond with ONLY the wish text, nothing else.
"""


# ─────────────────────────────────────────────
# 4. CORE RUNNER FUNCTIONS
# ─────────────────────────────────────────────

async def analyze_contact_personality(
    contact_name: str,
    profile_url: str,
    llm: BaseChatModel,
    browser: Browser,
    already_logged_in: bool,
    username: str,
    password: str,
) -> dict | None:
    """
    Scrapes a contact's LinkedIn posts, runs personality analysis via LLM,
    saves result to DB, and returns the profile dict.
    """
    logger.info("🔍 Analyzing personality for: %s", contact_name)

    # ── Step 1: Scrape posts via browser agent ──
    scrape_task = build_profile_scrape_task(
        contact_name, profile_url, already_logged_in, username, password
    )
    try:
        scrape_result = await Agent(task=scrape_task, llm=llm, browser=browser).run()
        # browser_use returns an AgentHistoryList — get the last text output
        raw_text = str(scrape_result)
        # Extract JSON substring from the result
        start = raw_text.find("{")
        end   = raw_text.rfind("}") + 1
        posts_data = json.loads(raw_text[start:end]) if start != -1 else {"posts": []}
    except Exception as e:
        logger.error("❌ Scrape failed for %s: %s", contact_name, e)
        return None

    posts = posts_data.get("posts", [])
    if not posts:
        logger.warning("⚠️ No posts found for %s — skipping analysis.", contact_name)
        return None

    # ── Step 2: Personality analysis via LLM (direct call, no browser) ──
    analysis_prompt = build_personality_analysis_task(
        contact_name, json.dumps(posts, ensure_ascii=False, indent=2)
    )
    try:
        analysis_result = await llm.ainvoke(analysis_prompt)
        raw_analysis = analysis_result.content if hasattr(analysis_result, "content") else str(analysis_result)

        start = raw_analysis.find("{")
        end   = raw_analysis.rfind("}") + 1
        profile_data = json.loads(raw_analysis[start:end])
    except Exception as e:
        logger.error("❌ Personality analysis LLM call failed for %s: %s", contact_name, e)
        return None

    # ── Step 3: Save to DB ──
    save_personality_profile(
        contact       = contact_name,
        profile_url   = profile_url,
        mbti_type     = profile_data.get("mbti_type", "Unknown"),
        dominant_traits = profile_data.get("dominant_traits", []),
        tone          = profile_data.get("tone", "neutral"),
        interests     = profile_data.get("interests", []),
        communication_style = profile_data.get("communication_style", ""),
        confidence_score    = profile_data.get("confidence_score", 0.0),
        raw_summary   = profile_data.get("raw_summary", ""),
    )

    return get_personality_profile(contact_name)


async def generate_personality_aware_wish(
    contact_name: str,
    llm: BaseChatModel,
    profile: dict | None = None,
) -> str:
    """
    Given a personality profile dict (or None), generate a personalized wish.
    Falls back to a generic warm wish if no profile available.
    """
    if not profile:
        profile = get_personality_profile(contact_name)

    if not profile or profile.get("confidence_score", 0) < 0.3:
        logger.info("📝 No strong profile for %s — using generic wish.", contact_name)
        return f"Happy Birthday, {contact_name}! 🎂 Wishing you an amazing day ahead!"

    prompt = build_personality_wish_prompt(contact_name, profile)
    try:
        result = await llm.ainvoke(prompt)
        wish = result.content if hasattr(result, "content") else str(result)
        wish = wish.strip().strip('"')
        logger.info("✅ Personality wish generated for %s [%s]",
                    contact_name, profile.get("mbti_type"))
        return wish
    except Exception as e:
        logger.error("❌ Wish generation failed for %s: %s", contact_name, e)
        return f"Happy Birthday, {contact_name}! 🎉 Hope your day is as brilliant as you are!"


# ─────────────────────────────────────────────
# 5. BATCH RUNNER (for daily_job integration)
# ─────────────────────────────────────────────

async def run_personality_profiling(
    contacts: list[dict],          # [{"name": "...", "profile_url": "..."}]
    llm: BaseChatModel,
    browser: Browser,
    already_logged_in: bool,
    username: str,
    password: str,
    dry_run: bool = True,
    max_profiles: int = 10,
) -> list[dict]:
    """
    Batch-analyze up to `max_profiles` contacts.
    Returns list of {contact, mbti_type, wish} dicts.

    Use this inside daily_job or as a standalone task.
    """
    results = []
    processed = 0

    for c in contacts[:max_profiles]:
        name        = c.get("name", "")
        profile_url = c.get("profile_url", "")

        if not name or not profile_url:
            continue

        # Use cached profile if fresh (updated today)
        cached = get_personality_profile(name)
        if cached and cached.get("updated_at", "")[:10] == datetime.now().date().isoformat():
            logger.info("⚡ Using cached profile for %s", name)
            profile = cached
        else:
            profile = await analyze_contact_personality(
                contact_name      = name,
                profile_url       = profile_url,
                llm               = llm,
                browser           = browser,
                already_logged_in = already_logged_in or processed > 0,
                username          = username,
                password          = password,
            )

        wish = await generate_personality_aware_wish(name, llm, profile)

        entry = {
            "contact"    : name,
            "profile_url": profile_url,
            "mbti_type"  : profile.get("mbti_type") if profile else "N/A",
            "tone"       : profile.get("tone")       if profile else "N/A",
            "traits"     : profile.get("dominant_traits", []) if profile else [],
            "wish"       : wish,
        }
        results.append(entry)
        processed += 1

        if dry_run:
            logger.info("[DRY RUN] Would send to %s (%s): \"%s\"",
                        name, entry["mbti_type"], wish)
        else:
            logger.info("✅ Ready to send to %s (%s): \"%s\"",
                        name, entry["mbti_type"], wish)

    logger.info("🧠 Personality profiling done: %d/%d contacts processed.",
                processed, len(contacts))
    return results


# ─────────────────────────────────────────────
# 6. DASHBOARD HELPERS
# ─────────────────────────────────────────────

def get_personality_stats() -> dict:
    """Return summary stats for the Streamlit dashboard."""
    profiles = get_all_personality_profiles()
    if not profiles:
        return {"total": 0, "by_mbti": {}, "by_tone": {}, "avg_confidence": 0.0}

    by_mbti: dict[str, int] = {}
    by_tone: dict[str, int] = {}
    total_conf = 0.0

    for p in profiles:
        mbti = p.get("mbti_type", "Unknown")
        tone = p.get("tone", "unknown")
        by_mbti[mbti] = by_mbti.get(mbti, 0) + 1
        by_tone[tone] = by_tone.get(tone, 0) + 1
        total_conf += p.get("confidence_score", 0.0)

    return {
        "total"          : len(profiles),
        "by_mbti"        : by_mbti,
        "by_tone"        : by_tone,
        "avg_confidence" : round(total_conf / len(profiles), 2),
    }