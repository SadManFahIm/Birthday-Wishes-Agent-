"""
emotional_intelligence.py
─────────────────────────
Emotional Intelligence (EQ) module for Birthday Wishes Agent.

Scores replies for empathy, warmth, and personalization.
Tracks performance over time and provides feedback for continuous improvement.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# ──────────────────────────────────────────────
# 1. DB SETUP
# ──────────────────────────────────────────────

def init_eq_table():
    """Create the EQ scores tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eq_scores (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                contact           TEXT    NOT NULL,
                reply_text        TEXT    NOT NULL,
                eq_score          INTEGER NOT NULL,
                empathy           INTEGER,
                tone_match        INTEGER,
                personalization   INTEGER,
                warmth            INTEGER,
                authenticity      INTEGER,
                improvement_tips  TEXT,
                created_at        TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  EQ scores table ready.")


# ──────────────────────────────────────────────
# 2. SCORING LOGIC
# ──────────────────────────────────────────────

async def score_reply(reply_text: str, context: str, llm) -> dict:
    """
    Use LLM to score a reply on various EQ dimensions.
    Returns a dict with scores and improvement tips.
    """
    prompt = f"""
    Evaluate the Emotional Intelligence (EQ) of the following birthday wish reply.
    
    REPLY TEXT: "{reply_text}"
    CONTEXT: "{context}"

    Score each category from 0 to 100:
    1. Empathy: Does it acknowledge the sender's feelings or effort?
    2. Tone Match: Does it match the closeness of the relationship?
    3. Personalization: Does it feel specific to the sender?
    4. Warmth: Is the tone friendly and welcoming?
    5. Authenticity: Does it feel like a human wrote it, not a bot?

    Return the result ONLY as a JSON object with this structure:
    {{
        "eq_score": (average of all scores),
        "breakdown": {{
            "empathy": (0-100),
            "tone_match": (0-100),
            "personalization": (0-100),
            "warmth": (0-100),
            "authenticity": (0-100)
        }},
        "improvement_tips": ["tip1", "tip2"]
    }}
    """
    try:
        response = await llm.ainvoke(prompt)
        # Handle different LLM response formats (string or object)
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Strip markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        result = json.loads(content)
        return result
    except Exception as e:
        logger.error("❌ EQ Scoring error: %s", e)
        return {
            "eq_score": 0,
            "breakdown": {"empathy": 0, "tone_match": 0, "personalization": 0, "warmth": 0, "authenticity": 0},
            "improvement_tips": ["Error in scoring system."]
        }


# ──────────────────────────────────────────────
# 3. DB OPERATIONS
# ──────────────────────────────────────────────

def save_eq_score(contact, reply_text, eq_score, breakdown, tips):
    """Save an EQ score record to SQLite."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO eq_scores (
                contact, reply_text, eq_score, 
                empathy, tone_match, personalization, warmth, authenticity,
                improvement_tips, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            contact, reply_text, eq_score,
            breakdown.get("empathy"), breakdown.get("tone_match"),
            breakdown.get("personalization"), breakdown.get("warmth"),
            breakdown.get("authenticity"),
            json.dumps(tips),
            datetime.now().isoformat()
        ))
        conn.commit()


def get_avg_eq_score() -> float:
    """Return the average EQ score across all records."""
    if not DB_FILE.exists():
        return 0.0
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("SELECT AVG(eq_score) FROM eq_scores").fetchone()
        return row[0] if row and row[0] else 0.0


def get_improvement_context() -> str:
    """Return the last 5 scores + tips as context string for LLM prompts."""
    if not DB_FILE.exists():
        return "No past data available."
    
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT eq_score, improvement_tips FROM eq_scores 
            ORDER BY created_at DESC LIMIT 5
        """).fetchall()
    
    if not rows:
        return "No past performance data."

    context = "Past Performance Feedback:\n"
    for score, tips_json in rows:
        tips = json.loads(tips_json)
        context += f"- Score: {score}/100. Tips: {', '.join(tips)}\n"
    return context


def build_eq_instructions() -> str:
    """Return prompt instructions to make replies more emotionally intelligent."""
    avg = get_avg_eq_score()
    improvement_context = get_improvement_context()
    
    return f"""
    EMOTIONAL INTELLIGENCE GUIDELINES:
    Current average performance: {avg:.1f}/100.
    
    Goal: Every reply must feel deeply personal, warm, and authentic.
    {improvement_context}
    
    Apply these rules:
    - Never sound like a template.
    - Reference specific context from the message.
    - Use natural language and varied emoji.
    - Match the emotional intensity of the sender.
    """


def get_eq_stats() -> dict:
    """Return EQ statistics for the dashboard."""
    if not DB_FILE.exists():
        return {"total": 0, "avg": 0}
        
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM eq_scores").fetchone()[0]
        avg = conn.execute("SELECT AVG(eq_score) FROM eq_scores").fetchone()[0] or 0
        
        breakdown_avg = conn.execute("""
            SELECT 
                AVG(empathy) as empathy, 
                AVG(tone_match) as tone_match, 
                AVG(personalization) as personalization, 
                AVG(warmth) as warmth, 
                AVG(authenticity) as authenticity 
            FROM eq_scores
        """).fetchone()
        
    return {
        "total": total,
        "avg_score": round(avg, 1),
        "breakdown": dict(breakdown_avg) if breakdown_avg else {}
    }
