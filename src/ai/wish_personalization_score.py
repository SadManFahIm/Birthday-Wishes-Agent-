"""
wish_personalization_score.py
------------------------------
Wish Personalization Scorer for Birthday Wishes Agent.

Scores every birthday wish on how personalized it is (1-10).
Auto-retries with a better prompt if score is below threshold.

Scoring criteria:
  - Mentions contact's name          (+2)
  - References their job/company     (+2)
  - References their industry        (+1)
  - References a past interaction    (+2)
  - Unique/non-generic language      (+1)
  - Appropriate length               (+1)
  - Warm and positive tone           (+1)
  Total max: 10

vs wish_scorer.py:
  - wish_scorer.py    : scores quality (grammar, tone, length)
  - this file         : scores PERSONALIZATION (how tailored to the contact)
  Both can be used together for maximum wish quality.

Usage:
    from wish_personalization_score import (
        score_personalization,
        generate_personalized_wish,
        build_personalization_report,
    )

    score = score_personalization(
        wish="Happy Birthday John! Hope your work at Google is going great!",
        contact_name="John",
        profile_info={"job_title": "Engineer", "company": "Google"},
    )
"""

import logging
import random
import sqlite3
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Retry if score below this
DEFAULT_THRESHOLD = 6

# Max retries
MAX_RETRIES = 3

# Generic phrases that lower personalization score
GENERIC_PHRASES = [
    "hope your day is great",
    "have a wonderful day",
    "wishing you all the best",
    "hope you enjoy",
    "many happy returns",
    "best wishes",
    "have a great one",
    "enjoy your special day",
]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_personalization_table():
    """Create personalization score tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS personalization_scores (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact       TEXT    NOT NULL,
                wish_text     TEXT    NOT NULL,
                score         REAL    NOT NULL,
                passed        INTEGER NOT NULL,
                name_score    REAL    DEFAULT 0,
                job_score     REAL    DEFAULT 0,
                memory_score  REAL    DEFAULT 0,
                unique_score  REAL    DEFAULT 0,
                tone_score    REAL    DEFAULT 0,
                threshold     REAL    DEFAULT 6,
                retries       INTEGER DEFAULT 0,
                scored_date   TEXT    NOT NULL,
                created_at    TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Personalization score table ready.")


# ------------------------------------------------------------
# SCORING
# ------------------------------------------------------------

def score_personalization(
    wish: str,
    contact_name: str,
    profile_info: dict | None = None,
    memory_context: str = "",
) -> dict:
    """
    Score a wish on personalization (0-10).

    Args:
        wish          : The wish text to score
        contact_name  : Contact's name
        profile_info  : Dict with job_title, company, industry etc.
        memory_context: Past interaction notes

    Returns:
        Dict with total score and component breakdown.
    """
    if not wish:
        return {"total": 0, "passed": False, "breakdown": {}}

    profile    = profile_info or {}
    wish_lower = wish.lower()
    breakdown  = {}

    # 1. Name mention (+2)
    first_name = contact_name.split()[0].lower() if contact_name else ""
    if first_name and first_name in wish_lower:
        breakdown["name"] = 2.0
    else:
        breakdown["name"] = 0.0

    # 2. Job/Company reference (+2)
    job_title = (profile.get("job_title") or "").lower()
    company   = (profile.get("company") or "").lower()
    job_score = 0.0

    if job_title:
        job_words = [w for w in job_title.split() if len(w) > 3]
        if any(w in wish_lower for w in job_words):
            job_score += 1.0
    if company:
        company_words = [w for w in company.split() if len(w) > 2]
        if any(w in wish_lower for w in company_words):
            job_score += 1.0

    breakdown["job_context"] = min(2.0, job_score)

    # 3. Industry reference (+1)
    industry = (profile.get("industry") or "").lower()
    if industry and any(w in wish_lower for w in industry.split() if len(w) > 3):
        breakdown["industry"] = 1.0
    else:
        breakdown["industry"] = 0.0

    # 4. Memory/past interaction reference (+2)
    if memory_context:
        memory_words = [
            w for w in memory_context.lower().split()
            if len(w) > 4
        ][:10]
        memory_matches = sum(1 for w in memory_words if w in wish_lower)
        breakdown["memory"] = min(2.0, memory_matches * 0.5)
    else:
        breakdown["memory"] = 0.0

    # 5. Unique language — penalize generic phrases (+1)
    generic_count = sum(
        1 for phrase in GENERIC_PHRASES
        if phrase in wish_lower
    )
    breakdown["unique"] = max(0.0, 1.0 - generic_count * 0.5)

    # 6. Length (+1)
    word_count = len(wish.split())
    if 15 <= word_count <= 60:
        breakdown["length"] = 1.0
    elif 8 <= word_count < 15 or 60 < word_count <= 80:
        breakdown["length"] = 0.5
    else:
        breakdown["length"] = 0.0

    # 7. Warm tone (+1)
    warm_words = ["amazing", "wonderful", "incredible", "fantastic",
                  "inspire", "proud", "admire", "brilliant", "great"]
    if any(w in wish_lower for w in warm_words):
        breakdown["tone"] = 1.0
    else:
        breakdown["tone"] = 0.5

    total  = round(sum(breakdown.values()), 1)
    total  = min(10.0, total)
    passed = total >= DEFAULT_THRESHOLD

    logger.info(
        "Personalization score for %s: %.1f/10 (%s) | %s",
        contact_name, total,
        "PASS" if passed else "FAIL",
        {k: v for k, v in breakdown.items() if v > 0},
    )

    return {
        "total":     total,
        "passed":    passed,
        "threshold": DEFAULT_THRESHOLD,
        "breakdown": breakdown,
    }


def log_score(
    contact: str,
    wish_text: str,
    score_result: dict,
    retries: int = 0,
):
    """Log a personalization score to DB."""
    b = score_result.get("breakdown", {})
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO personalization_scores
            (contact, wish_text, score, passed, name_score,
             job_score, memory_score, unique_score, tone_score,
             threshold, retries, scored_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            contact, wish_text[:500],
            score_result["total"], int(score_result["passed"]),
            b.get("name", 0), b.get("job_context", 0),
            b.get("memory", 0), b.get("unique", 0),
            b.get("tone", 0), score_result["threshold"],
            retries, date.today().isoformat(),
            datetime.now().isoformat(),
        ))
        conn.commit()


# ------------------------------------------------------------
# WISH GENERATION WITH AUTO-RETRY
# ------------------------------------------------------------

async def generate_personalized_wish(
    llm,
    contact_name: str,
    profile_info: dict | None = None,
    memory_context: str = "",
    threshold: int = DEFAULT_THRESHOLD,
    max_retries: int = MAX_RETRIES,
) -> dict:
    """
    Generate a wish and retry until personalization score >= threshold.

    Args:
        llm            : LangChain LLM instance
        contact_name   : Contact's name
        profile_info   : Profile details (job, company, industry)
        memory_context : Past interaction context
        threshold      : Min personalization score (default 6)
        max_retries    : Max generation attempts

    Returns:
        Dict with wish_text, score, attempts, passed.
    """
    from langchain_core.messages import HumanMessage

    profile   = profile_info or {}
    job_title = profile.get("job_title", "")
    company   = profile.get("company", "")
    industry  = profile.get("industry", "")

    best_wish  = None
    best_score = 0.0

    for attempt in range(1, max_retries + 1):
        # Build prompt with increasing specificity on retry
        specificity = "very" if attempt > 1 else ""
        prompt = f"""Write a birthday wish for {contact_name}.

{f"They work as {job_title} at {company}." if job_title and company else ""}
{f"Industry: {industry}" if industry else ""}
{f"Past context: {memory_context}" if memory_context and attempt > 1 else ""}

Requirements (attempt {attempt}/{max_retries}):
- MUST mention their name: {contact_name.split()[0]}
{f"- MUST reference their role ({job_title}) or company ({company})" if job_title or company else ""}
- Be {specificity} specific and personal — NOT generic
- 2-3 sentences, warm tone, 1-2 emoji
- Do NOT use: "hope your day is great", "all the best", "many happy returns"

Reply with ONLY the wish text.
"""
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            wish     = response.content.strip().strip('"').strip("'")

            score_result = score_personalization(
                wish, contact_name, profile_info, memory_context
            )

            logger.info(
                "Attempt %d/%d | score=%.1f | wish: %s",
                attempt, max_retries, score_result["total"], wish[:50],
            )

            if score_result["total"] > best_score:
                best_score = score_result["total"]
                best_wish  = wish
                best_result = score_result

            if score_result["passed"]:
                log_score(contact_name, wish, score_result, attempt - 1)
                return {
                    "wish_text": wish,
                    "score":     score_result["total"],
                    "passed":    True,
                    "attempts":  attempt,
                    "breakdown": score_result["breakdown"],
                }

        except Exception as e:
            logger.error("Wish generation attempt %d failed: %s", attempt, e)

    # Return best even if below threshold
    if best_wish:
        log_score(contact_name, best_wish, best_result, max_retries)
        logger.warning(
            "Best score after %d attempts: %.1f (threshold: %d)",
            max_retries, best_score, threshold,
        )
        return {
            "wish_text": best_wish,
            "score":     best_score,
            "passed":    best_score >= threshold,
            "attempts":  max_retries,
            "breakdown": best_result.get("breakdown", {}),
        }

    # Absolute fallback
    fallback = f"Happy Birthday {contact_name.split()[0]}! Wishing you an amazing day!"
    return {
        "wish_text": fallback,
        "score":     3.0,
        "passed":    False,
        "attempts":  max_retries,
        "breakdown": {},
    }


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_personalization_report() -> str:
    """Build personalization score report from DB."""
    if not DB_FILE.exists():
        return "No personalization data yet."

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT contact, score, passed, retries, scored_date
            FROM   personalization_scores
            ORDER  BY scored_date DESC
            LIMIT  20
        """).fetchall()

        avg = conn.execute(
            "SELECT AVG(score), COUNT(*), SUM(passed) FROM personalization_scores"
        ).fetchone()

    if not rows:
        return "No personalization scores yet."

    avg_score   = avg[0] or 0
    total       = avg[1] or 0
    passed      = avg[2] or 0
    pass_rate   = round(passed / total * 100, 1) if total else 0

    lines = [
        "Wish Personalization Score Report",
        "-" * 55,
        f"  Total scored  : {total}",
        f"  Avg score     : {avg_score:.1f}/10",
        f"  Pass rate     : {pass_rate:.1f}% (>= {DEFAULT_THRESHOLD}/10)",
        "-" * 55,
        "",
        f"  {'Contact':<20} {'Score':>6} {'Status':<6} {'Retries':>8}",
        "  " + "-" * 44,
    ]

    for contact, score, passed_val, retries, scored_date in rows:
        status = "PASS" if passed_val else "FAIL"
        lines.append(
            f"  {contact:<20} {score:>6.1f} {status:<6} {retries:>8}"
        )

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# QUICK SCORE HELPER
# ------------------------------------------------------------

def check_wish_before_send(
    wish: str,
    contact_name: str,
    profile_info: dict | None = None,
) -> tuple[bool, float, str]:
    """
    Quick check before sending a wish.

    Returns:
        (should_send, score, feedback)
    """
    result   = score_personalization(wish, contact_name, profile_info)
    score    = result["total"]
    passed   = result["passed"]
    b        = result["breakdown"]

    missing = []
    if b.get("name", 0) == 0:
        missing.append("name not mentioned")
    if b.get("job_context", 0) == 0 and profile_info:
        missing.append("no job/company reference")
    if b.get("unique", 0) < 1:
        missing.append("too generic")

    feedback = f"Score: {score:.1f}/10"
    if missing:
        feedback += f" | Missing: {', '.join(missing)}"

    return passed, score, feedback
