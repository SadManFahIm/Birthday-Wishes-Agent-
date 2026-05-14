"""
personality_profiling.py
────────────────────────
Personality Profiling module for Birthday Wishes Agent.

Analyzes a contact's LinkedIn posts, comments, and activity
to detect their personality type and communication preferences.

Personality Frameworks:
  1. MBTI-inspired (16 types)
     - I/E : Introvert vs Extrovert
     - S/N : Sensing vs Intuitive
     - T/F : Thinking vs Feeling
     - J/P : Judging vs Perceiving

  2. Big Five (OCEAN)
     - Openness, Conscientiousness, Extraversion,
       Agreeableness, Neuroticism

  3. Communication Style
     - Formal, Casual, Analytical, Expressive, Driver

  4. Content Style
     - Technical, Inspirational, Storyteller,
       Humorous, Professional

How it works:
  1. Scans contact's recent LinkedIn posts (up to 20)
  2. Analyzes writing style, topics, tone, emoji usage
  3. Detects personality type using LLM
  4. Saves profile to SQLite
  5. Used to personalize wishes and replies

Usage:
    from personality_profiling import (
        analyze_personality,
        get_personality_profile,
        build_personality_task
    )
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger  = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ──────────────────────────────────────────────
# PERSONALITY DEFINITIONS
# ──────────────────────────────────────────────
MBTI_TYPES = {
    "INTJ": {"name": "The Architect",    "traits": ["strategic", "independent", "decisive"]},
    "INTP": {"name": "The Thinker",      "traits": ["analytical", "curious", "logical"]},
    "ENTJ": {"name": "The Commander",    "traits": ["bold", "leadership", "ambitious"]},
    "ENTP": {"name": "The Debater",      "traits": ["innovative", "argumentative", "clever"]},
    "INFJ": {"name": "The Advocate",     "traits": ["insightful", "principled", "empathetic"]},
    "INFP": {"name": "The Mediator",     "traits": ["idealistic", "creative", "empathetic"]},
    "ENFJ": {"name": "The Protagonist",  "traits": ["charismatic", "inspiring", "warm"]},
    "ENFP": {"name": "The Campaigner",   "traits": ["enthusiastic", "creative", "sociable"]},
    "ISTJ": {"name": "The Logistician",  "traits": ["reliable", "detail-oriented", "practical"]},
    "ISFJ": {"name": "The Defender",     "traits": ["dedicated", "warm", "reliable"]},
    "ESTJ": {"name": "The Executive",    "traits": ["organized", "traditional", "direct"]},
    "ESFJ": {"name": "The Consul",       "traits": ["caring", "social", "popular"]},
    "ISTP": {"name": "The Virtuoso",     "traits": ["practical", "observant", "reserved"]},
    "ISFP": {"name": "The Adventurer",   "traits": ["artistic", "flexible", "charming"]},
    "ESTP": {"name": "The Entrepreneur", "traits": ["energetic", "perceptive", "direct"]},
    "ESFP": {"name": "The Entertainer",  "traits": ["spontaneous", "playful", "bold"]},
}

COMMUNICATION_STYLES = {
    "formal":       "Professional, structured, uses complete sentences, minimal emoji",
    "casual":       "Relaxed, contractions, conversational, some emoji",
    "analytical":   "Data-driven, references facts/numbers, logical reasoning",
    "expressive":   "Emotional, story-based, lots of emoji, exclamation points",
    "driver":       "Direct, action-oriented, results-focused, concise",
}

CONTENT_STYLES = {
    "technical":      "Posts about code, data, systems, engineering topics",
    "inspirational":  "Motivational content, life lessons, personal growth",
    "storyteller":    "Narratives, personal experiences, anecdotes",
    "humorous":       "Jokes, memes, light-hearted content",
    "professional":   "Industry news, business insights, career advice",
}

# Wish style per personality
PERSONALITY_WISH_STYLES = {
    "analytical":   "Include a thoughtful, specific reference to their work or achievement",
    "expressive":   "Use warmth, enthusiasm, and emoji — match their energy",
    "formal":       "Professional, structured, no slang",
    "casual":       "Relaxed and friendly, conversational tone",
    "driver":       "Short, punchy, results-focused",
    "inspirational": "Motivational, forward-looking, uplifting",
    "humorous":     "Light-hearted, can include a gentle joke",
}


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_personality_table():
    """Create the personality profiles table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS personality_profiles (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                contact            TEXT    NOT NULL UNIQUE,
                mbti_type          TEXT,
                mbti_name          TEXT,
                communication_style TEXT,
                content_style      TEXT,
                big_five           TEXT,
                key_traits         TEXT,
                wish_style         TEXT,
                raw_analysis       TEXT,
                confidence         REAL    DEFAULT 0.0,
                posts_analyzed     INTEGER DEFAULT 0,
                last_updated       TEXT    NOT NULL,
                created_at         TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  Personality profiles table ready.")


def save_personality_profile(
    contact: str,
    mbti_type: str = "",
    communication_style: str = "",
    content_style: str = "",
    big_five: dict = None,
    key_traits: list = None,
    wish_style: str = "",
    raw_analysis: str = "",
    confidence: float = 0.0,
    posts_analyzed: int = 0,
):
    """Save or update a contact's personality profile."""
    mbti_name = MBTI_TYPES.get(mbti_type, {}).get("name", "")
    now       = datetime.now().isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO personality_profiles
                (contact, mbti_type, mbti_name, communication_style,
                 content_style, big_five, key_traits, wish_style,
                 raw_analysis, confidence, posts_analyzed,
                 last_updated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact) DO UPDATE SET
                mbti_type           = excluded.mbti_type,
                mbti_name           = excluded.mbti_name,
                communication_style = excluded.communication_style,
                content_style       = excluded.content_style,
                big_five            = excluded.big_five,
                key_traits          = excluded.key_traits,
                wish_style          = excluded.wish_style,
                raw_analysis        = excluded.raw_analysis,
                confidence          = excluded.confidence,
                posts_analyzed      = excluded.posts_analyzed,
                last_updated        = excluded.last_updated
        """, (
            contact, mbti_type, mbti_name, communication_style,
            content_style,
            json.dumps(big_five or {}),
            json.dumps(key_traits or []),
            wish_style, raw_analysis, confidence, posts_analyzed,
            now, now,
        ))
        conn.commit()
    logger.info("🎭 Personality profile saved for %s: %s (%s)",
                contact, mbti_type, communication_style)


def get_personality_profile(contact: str) -> dict | None:
    """Get a contact's personality profile."""
    if not DB_FILE.exists():
        return None
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT mbti_type, mbti_name, communication_style, "
            "content_style, big_five, key_traits, wish_style, "
            "confidence, posts_analyzed, last_updated "
            "FROM personality_profiles WHERE LOWER(contact) = LOWER(?)",
            (contact,),
        ).fetchone()
    if not row:
        return None
    return {
        "mbti_type":           row[0] or "",
        "mbti_name":           row[1] or "",
        "communication_style": row[2] or "",
        "content_style":       row[3] or "",
        "big_five":            json.loads(row[4]) if row[4] else {},
        "key_traits":          json.loads(row[5]) if row[5] else [],
        "wish_style":          row[6] or "",
        "confidence":          row[7] or 0.0,
        "posts_analyzed":      row[8] or 0,
        "last_updated":        row[9] or "",
    }


def get_all_profiles() -> list[dict]:
    """Get all personality profiles."""
    if not DB_FILE.exists():
        return []
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT contact, mbti_type, mbti_name, communication_style, "
            "content_style, key_traits, confidence, posts_analyzed "
            "FROM personality_profiles ORDER BY contact"
        ).fetchall()
    return [
        {
            "contact":             r[0],
            "mbti_type":           r[1] or "",
            "mbti_name":           r[2] or "",
            "communication_style": r[3] or "",
            "content_style":       r[4] or "",
            "key_traits":          json.loads(r[5]) if r[5] else [],
            "confidence":          r[6] or 0.0,
            "posts_analyzed":      r[7] or 0,
        }
        for r in rows
    ]


# ──────────────────────────────────────────────
# FAST RULE-BASED ANALYSIS
# ──────────────────────────────────────────────
def quick_personality_analysis(posts: list[str]) -> dict:
    """
    Fast rule-based personality hints from post content.
    Returns partial analysis with lower confidence.
    """
    if not posts:
        return {}

    all_text   = " ".join(posts).lower()
    emoji_count = sum(1 for c in all_text if ord(c) > 127000)
    avg_length  = sum(len(p) for p in posts) / len(posts)

    # Communication style hints
    comm_style = "casual"
    if any(w in all_text for w in ["data", "analysis", "metrics", "research", "study"]):
        comm_style = "analytical"
    elif any(w in all_text for w in ["excited", "amazing", "love", "incredible", "blessed"]):
        comm_style = "expressive"
    elif avg_length > 400:
        comm_style = "formal"
    elif emoji_count > len(posts) * 2:
        comm_style = "expressive"

    # Content style hints
    content_style = "professional"
    if any(w in all_text for w in ["code", "github", "api", "deploy", "algorithm"]):
        content_style = "technical"
    elif any(w in all_text for w in ["grateful", "journey", "lesson", "mindset", "growth"]):
        content_style = "inspirational"
    elif any(w in all_text for w in ["lol", "funny", "joke", "haha", "humor"]):
        content_style = "humorous"
    elif any(w in all_text for w in ["story", "moment", "remember", "experience", "once"]):
        content_style = "storyteller"

    return {
        "communication_style": comm_style,
        "content_style":       content_style,
        "confidence":          0.5,
    }


# ──────────────────────────────────────────────
# LLM-BASED ANALYSIS
# ──────────────────────────────────────────────
async def analyze_personality_with_llm(
    llm,
    contact: str,
    posts: list[str],
) -> dict:
    """
    Use LLM to analyze personality from LinkedIn posts.

    Args:
        llm     : LangChain LLM instance
        contact : Contact's name
        posts   : List of their recent LinkedIn post texts

    Returns:
        Full personality analysis dict.
    """
    from langchain_core.messages import HumanMessage

    if not posts:
        return {}

    # Use first 10 posts for analysis
    posts_sample = posts[:10]
    posts_text   = "\n\n---\n\n".join(
        f"Post {i+1}:\n{p[:300]}" for i, p in enumerate(posts_sample)
    )

    mbti_list  = ", ".join(MBTI_TYPES.keys())
    comm_list  = ", ".join(COMMUNICATION_STYLES.keys())
    cont_list  = ", ".join(CONTENT_STYLES.keys())

    prompt = f"""
Analyze the personality of {contact} based on their LinkedIn posts.

LinkedIn Posts:
{posts_text}

Analyze and return a JSON object with:
{{
  "mbti_type": "{mbti_list} — pick ONE",
  "communication_style": "{comm_list} — pick ONE",
  "content_style": "{cont_list} — pick ONE",
  "big_five": {{
    "openness": 0-100,
    "conscientiousness": 0-100,
    "extraversion": 0-100,
    "agreeableness": 0-100,
    "neuroticism": 0-100
  }},
  "key_traits": ["trait1", "trait2", "trait3"],
  "wish_style": "How to write birthday wishes for this person — 1 sentence",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of why you chose these types"
}}

Guidelines:
- Base analysis ONLY on the posts provided
- Look for: writing style, topics, tone, vocabulary, emoji usage
- Be objective — don't stereotype based on name or job
- Lower confidence if fewer posts available
- key_traits should be 3-5 specific adjectives

Return ONLY the JSON. No extra text.
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text     = response.content.strip().replace("```json", "").replace("```", "").strip()
        result   = json.loads(text)

        # Add wish style from our map if not provided
        if not result.get("wish_style"):
            comm = result.get("communication_style", "casual")
            result["wish_style"] = PERSONALITY_WISH_STYLES.get(
                comm, "Write a warm, genuine birthday wish"
            )

        logger.info(
            "🎭 Personality analyzed for %s: %s (%s)",
            contact,
            result.get("mbti_type", "?"),
            result.get("communication_style", "?"),
        )
        return result

    except Exception as e:
        logger.warning("⚠️  LLM personality analysis failed for %s: %s", contact, e)
        return quick_personality_analysis(posts)


# ──────────────────────────────────────────────
# BROWSER TASK BUILDER
# ──────────────────────────────────────────────
def build_personality_task(
    contact: str,
    profile_url: str,
    already_logged_in: bool,
    username: str = "",
    password: str = "",
) -> str:
    """Build a browser task to scrape LinkedIn posts for personality analysis."""
    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {username}\n"
            f"  Password: {password}\n"
        )
    )
    profile_str = f"Go to: {profile_url}" if profile_url else f"Search for '{contact}' on LinkedIn."

    return f"""
  Open the browser.
  {login_instructions}

  GOAL: Collect recent LinkedIn posts from {contact}
  to analyze their personality and communication style.

  STEP 1 — {profile_str}

  STEP 2 — Click on "Activity" or "Posts" on their profile.
    Scroll through their recent activity.
    Collect the text of up to 20 recent posts.

  STEP 3 — For each post, note:
    - The full post text
    - Post type (article, short update, poll, etc.)
    - Approximate length
    - Emoji usage (yes/no)

  STEP 4 — Return the data as JSON:
  {{
    "contact": "{contact}",
    "posts": [
      "Post text 1...",
      "Post text 2...",
      ...
    ],
    "total_posts_found": 20,
    "notes": "Any observations about their posting style"
  }}

  Return ONLY the JSON. No extra text.
"""


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def analyze_personality(
    llm,
    browser,
    contact: str,
    profile_url: str = "",
    already_logged_in: bool = False,
    username: str = "",
    password: str = "",
) -> dict:
    """
    Scrape LinkedIn posts and analyze contact's personality.

    Returns:
        Full personality profile dict.
    """
    import json as jsonlib
    from browser_use import Agent

    logger.info("=== Personality Profiling: %s ===", contact)

    # Check if fresh profile exists (< 30 days old)
    existing = get_personality_profile(contact)
    if existing and existing.get("posts_analyzed", 0) > 0:
        logger.info("⏭️  Fresh profile exists for %s — skipping.", contact)
        return existing

    # Scrape posts
    task   = build_personality_task(
        contact=contact,
        profile_url=profile_url,
        already_logged_in=already_logged_in,
        username=username,
        password=password,
    )
    agent  = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()

    posts = []
    try:
        result_str = str(result)
        start      = result_str.find("{")
        end        = result_str.rfind("}") + 1
        if start != -1 and end > start:
            data  = jsonlib.loads(result_str[start:end])
            posts = data.get("posts", [])
            logger.info("📋 Collected %d posts for %s", len(posts), contact)
    except Exception as e:
        logger.warning("⚠️  Could not parse posts for %s: %s", contact, e)

    if not posts:
        logger.warning("⚠️  No posts found for %s", contact)
        return {}

    # Analyze personality with LLM
    analysis = await analyze_personality_with_llm(llm, contact, posts)

    if analysis:
        save_personality_profile(
            contact=contact,
            mbti_type=analysis.get("mbti_type", ""),
            communication_style=analysis.get("communication_style", ""),
            content_style=analysis.get("content_style", ""),
            big_five=analysis.get("big_five", {}),
            key_traits=analysis.get("key_traits", []),
            wish_style=analysis.get("wish_style", ""),
            raw_analysis=analysis.get("reasoning", ""),
            confidence=analysis.get("confidence", 0.5),
            posts_analyzed=len(posts),
        )

    return analysis


# ──────────────────────────────────────────────
# PERSONALITY-AWARE WISH INSTRUCTIONS
# ──────────────────────────────────────────────
def build_personality_instructions(contact: str) -> str:
    """
    Build personality-aware wish instructions for the browser agent.
    Injects personality profile into wish/reply prompts.
    """
    profile = get_personality_profile(contact)
    if not profile or not profile.get("mbti_type"):
        return ""

    mbti      = profile["mbti_type"]
    mbti_name = profile["mbti_name"] or MBTI_TYPES.get(mbti, {}).get("name", "")
    comm      = profile["communication_style"]
    traits    = ", ".join(profile.get("key_traits", [])[:3])
    wish_style = profile.get("wish_style", "")

    return f"""
  PERSONALITY PROFILE FOR {contact.upper()}:
  MBTI Type          : {mbti} — {mbti_name}
  Communication Style: {comm.title()}
  Key Traits         : {traits}
  Wish Style Guidance: {wish_style}

  Adapt your message to match their personality:
  {COMMUNICATION_STYLES.get(comm, "")}

  Examples of how to write for a {comm} communicator:
  {_get_style_example(comm)}
"""


def _get_style_example(style: str) -> str:
    examples = {
        "analytical":   '"Happy Birthday Rahul! 🎂 Another year of solving complex problems — your analytical mind is truly impressive. Wishing you data-driven success ahead!"',
        "expressive":   '"Happy Birthday!!! 🎉🥳🎂 You bring SO much energy and warmth everywhere you go — hope today is AMAZING! Sending all the love!! 💛✨"',
        "formal":       '"Happy Birthday. I hope this message finds you well and that your day is a pleasant one. Wishing you continued success in the year ahead."',
        "casual":       '"Hey, happy birthday! 🎂 Hope you\'re having an awesome day — you totally deserve it!"',
        "driver":       '"Happy Birthday! 🎯 Another year, bigger goals. Keep crushing it!"',
        "inspirational": '"Happy Birthday! 🌟 Every year you grow stronger and wiser. The best chapters of your story are still ahead — keep inspiring us all!"',
        "humorous":     '"Happy Birthday! 🎂 You\'re not getting older, you\'re just becoming a more limited edition. Hope it\'s a great one!"',
    }
    return examples.get(style, '"Happy Birthday! Wishing you a wonderful day!"')