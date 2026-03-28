"""
wish_scorer.py
──────────────
Wish Quality Scorer module for Birthday Wishes Agent.

Uses the LLM to score AI-generated birthday wishes on a scale of 1-10.
If a wish scores below the threshold, it is automatically regenerated
until a good wish is produced or the retry limit is reached.

Scoring Criteria:
  - Personalization (does it mention name/job/context?)
  - Warmth (does it feel genuine and caring?)
  - Originality (does it avoid generic phrases?)
  - Length (is it the right length — not too short, not too long?)
  - Tone (does it match the relationship type?)

Usage:
    from wish_scorer import score_wish, generate_scored_wish

    score = await score_wish(llm, wish, context)
    # score = {"score": 8, "feedback": "...", "passed": True}

    final_wish = await generate_scored_wish(llm, name, profile_info)
    # Automatically retries until score >= threshold
"""

import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

# Minimum acceptable score (1-10)
SCORE_THRESHOLD = 7

# Maximum number of retries if score is too low
MAX_RETRIES = 3


# ──────────────────────────────────────────────
# SCORE A WISH
# ──────────────────────────────────────────────
async def score_wish(
    llm,
    wish: str,
    context: dict = None,
) -> dict:
    """
    Score a birthday wish on a scale of 1-10 using the LLM.

    Args:
        llm     : LangChain LLM instance
        wish    : The wish text to score
        context : Optional dict with name, job_title, company, relationship

    Returns:
        Dict with:
            - score      (int 1-10)
            - feedback   (str — what's good/bad)
            - passed     (bool — score >= threshold)
            - breakdown  (dict — scores per criterion)
    """
    name         = context.get("name", "the person") if context else "the person"
    job_title    = context.get("job_title", "") if context else ""
    company      = context.get("company", "") if context else ""
    relationship = context.get("relationship", "acquaintance") if context else "acquaintance"

    context_str = ""
    if job_title or company:
        context_str = f"Contact works as {job_title} at {company}." if job_title and company \
                      else f"Contact works as {job_title}." if job_title \
                      else f"Contact works at {company}."

    prompt = f"""
You are evaluating the quality of a birthday wish message.

Wish to evaluate:
"{wish}"

Context:
  - Recipient name   : {name}
  - Relationship type: {relationship}
  - {context_str}

Score this wish on each criterion (1-10):

1. PERSONALIZATION — Does it mention name, job, or personal context?
2. WARMTH          — Does it feel genuine, caring, and human?
3. ORIGINALITY     — Does it avoid generic/cliché phrases?
4. LENGTH          — Is it the right length? (2-3 sentences ideal)
5. TONE            — Does the tone match the relationship type?

Return ONLY a JSON object like this:
{{
  "breakdown": {{
    "personalization": 8,
    "warmth": 9,
    "originality": 7,
    "length": 9,
    "tone": 8
  }},
  "score": 8,
  "feedback": "Good personalization and warm tone. Could be more original.",
  "suggestion": "Try referencing their specific role or a recent achievement."
}}

No extra text. JSON only.
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        import json
        text = response.content.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        score  = result.get("score", 5)
        result["passed"] = score >= SCORE_THRESHOLD

        logger.info(
            "📊 Wish score: %d/10 (%s) — %s",
            score,
            "✅ PASSED" if result["passed"] else "❌ FAILED",
            result.get("feedback", ""),
        )
        return result

    except Exception as e:
        logger.warning("⚠️  Wish scoring failed: %s. Defaulting to pass.", e)
        return {
            "score":     7,
            "feedback":  "Scoring unavailable — defaulting to pass.",
            "passed":    True,
            "breakdown": {},
            "suggestion": "",
        }


# ──────────────────────────────────────────────
# IMPROVE A WISH
# ──────────────────────────────────────────────
async def improve_wish(
    llm,
    original_wish: str,
    feedback: str,
    suggestion: str,
    context: dict = None,
) -> str:
    """
    Improve a wish based on scorer feedback.

    Args:
        llm           : LangChain LLM instance
        original_wish : The wish that scored too low
        feedback      : What was wrong with it
        suggestion    : How to improve it
        context       : Contact context dict

    Returns:
        Improved wish string.
    """
    name         = context.get("name", "the person") if context else "the person"
    job_title    = context.get("job_title", "") if context else ""
    company      = context.get("company", "") if context else ""
    relationship = context.get("relationship", "acquaintance") if context else "acquaintance"

    prompt = f"""
You wrote this birthday wish:
"{original_wish}"

A quality scorer gave this feedback:
Feedback   : {feedback}
Suggestion : {suggestion}

Please rewrite the wish to address this feedback.

Contact info:
  Name         : {name}
  Job Title    : {job_title or "Unknown"}
  Company      : {company or "Unknown"}
  Relationship : {relationship}

Rules:
  ✅ Keep it 2-3 sentences
  ✅ Start with "Happy Birthday {name}!"
  ✅ Feel genuine and personal
  ✅ Address the feedback above
  ❌ Do NOT sound like a template

Reply with ONLY the improved wish. No explanation.
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        wish = response.content.strip().strip('"').strip("'")
        logger.info("✨ Improved wish for %s: %s", name, wish[:60] + "...")
        return wish
    except Exception as e:
        logger.error("❌ Wish improvement failed: %s", e)
        return original_wish


# ──────────────────────────────────────────────
# GENERATE + SCORE + RETRY
# ──────────────────────────────────────────────
async def generate_scored_wish(
    llm,
    name: str,
    profile_info: dict,
    relationship: str = "acquaintance",
) -> dict:
    """
    Generate a wish, score it, and retry if score is too low.
    Automatically improves the wish based on feedback.

    Args:
        llm          : LangChain LLM instance
        name         : Contact's first name
        profile_info : Dict with job_title, company, shared_interests, etc.
        relationship : "close_friend", "colleague", or "acquaintance"

    Returns:
        Dict with:
            - wish       (str — final wish)
            - score      (int — final score)
            - attempts   (int — how many attempts it took)
            - passed     (bool)
    """
    from wish_generator import generate_custom_wish

    context = {
        "name":         name,
        "job_title":    profile_info.get("job_title", ""),
        "company":      profile_info.get("company", ""),
        "relationship": relationship,
    }

    wish     = await generate_custom_wish(llm, name, profile_info)
    attempts = 1

    for attempt in range(1, MAX_RETRIES + 1):
        result = await score_wish(llm, wish, context)
        score  = result.get("score", 7)

        logger.info(
            "🎯 Attempt %d/%d — Score: %d/10 for %s",
            attempt, MAX_RETRIES, score, name,
        )

        if result["passed"]:
            logger.info("✅ Wish passed quality check on attempt %d.", attempt)
            return {
                "wish":     wish,
                "score":    score,
                "attempts": attempt,
                "passed":   True,
                "feedback": result.get("feedback", ""),
            }

        # Score too low — improve and retry
        logger.info(
            "🔄 Score %d < %d — improving wish (attempt %d/%d)...",
            score, SCORE_THRESHOLD, attempt, MAX_RETRIES,
        )
        wish     = await improve_wish(
            llm, wish,
            feedback=result.get("feedback", ""),
            suggestion=result.get("suggestion", ""),
            context=context,
        )
        attempts = attempt + 1

    # Final score after all retries
    final_result = await score_wish(llm, wish, context)
    logger.warning(
        "⚠️  Could not reach score threshold after %d attempts. "
        "Using best wish with score %d.",
        MAX_RETRIES, final_result.get("score", 0),
    )

    return {
        "wish":     wish,
        "score":    final_result.get("score", 0),
        "attempts": attempts,
        "passed":   False,
        "feedback": final_result.get("feedback", ""),
    }


# ──────────────────────────────────────────────
# SCORER INSTRUCTIONS (for browser agent)
# ──────────────────────────────────────────────
def build_scorer_instructions() -> str:
    """
    Returns instructions for the browser agent to self-evaluate
    wishes before sending them.
    """
    return f"""
  WISH QUALITY CHECK:
  Before sending any birthday wish, evaluate it internally:

  Score it on these criteria (1-10 each):
    1. Personalization — mentions name, job, or personal context?
    2. Warmth          — feels genuine and caring?
    3. Originality     — avoids "Happy Birthday! Hope you have a great day!"?
    4. Length          — 2-3 sentences, not too short or long?
    5. Tone            — matches the relationship type?

  Calculate average score.

  If average score < {SCORE_THRESHOLD}/10:
    → Rewrite the wish and try again (max {MAX_RETRIES} attempts)
    → Address whatever made the score low

  If average score >= {SCORE_THRESHOLD}/10:
    → Proceed and send the wish

  Never send a wish you would score below {SCORE_THRESHOLD}/10.
"""