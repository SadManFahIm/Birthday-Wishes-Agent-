"""
model_ensemble.py
-----------------
Claude + Gemini + GPT-4o Ensemble for Birthday Wishes Agent.

Generates birthday wishes using multiple AI models and
automatically selects the best one based on quality scoring.

How it works:
  1. Sends the same prompt to Claude, Gemini, and GPT-4o in parallel
  2. Scores each response using wish_scorer logic
  3. Picks the highest-scoring wish
  4. Falls back to single model if others are unavailable

.env setup:
  ANTHROPIC_API_KEY=...   (for Claude)
  GOOGLE_API_KEY=...      (for Gemini)
  OPENAI_API_KEY=...      (for GPT-4o)
  ENSEMBLE_ENABLED=true
  ENSEMBLE_MODELS=claude,gemini,gpt-4o  (pick which to use)

Usage:
    from model_ensemble import (
        generate_ensemble_wish,
        get_ensemble_status,
    )

    wish = await generate_ensemble_wish(
        name="John",
        profile_info={"job_title": "Engineer", "company": "Google"},
    )
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

def load_ensemble_config() -> dict:
    """Load ensemble config from .env."""
    from dotenv import dotenv_values
    config = dotenv_values(".env")

    models_str = config.get("ENSEMBLE_MODELS", "gemini,gpt-4o")
    models     = [m.strip().lower() for m in models_str.split(",") if m.strip()]

    return {
        "enabled":         config.get("ENSEMBLE_ENABLED", "false").lower() == "true",
        "models":          models,
        "anthropic_key":   config.get("ANTHROPIC_API_KEY", ""),
        "google_key":      config.get("GOOGLE_API_KEY", ""),
        "openai_key":      config.get("OPENAI_API_KEY", ""),
    }


def get_ensemble_status() -> dict:
    """Check which models are available."""
    config    = load_ensemble_config()
    available = []

    if config["anthropic_key"] and "claude" in config["models"]:
        available.append("claude")
    if config["google_key"] and "gemini" in config["models"]:
        available.append("gemini")
    if config["openai_key"] and "gpt-4o" in config["models"]:
        available.append("gpt-4o")

    return {
        "enabled":   config["enabled"],
        "requested": config["models"],
        "available": available,
    }


# ------------------------------------------------------------
# INDIVIDUAL MODEL GENERATORS
# ------------------------------------------------------------

async def _generate_with_claude(prompt: str, api_key: str) -> str | None:
    """Generate wish using Claude (claude-sonnet)."""
    try:
        import anthropic
        client   = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip().strip('"').strip("'")
        logger.info("[Ensemble] Claude generated: %s", text[:60])
        return text
    except Exception as e:
        logger.warning("[Ensemble] Claude failed: %s", e)
        return None


async def _generate_with_gemini(prompt: str, api_key: str) -> str | None:
    """Generate wish using Google Gemini 2.5 Pro."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage

        llm      = ChatGoogleGenerativeAI(
            model="models/gemini-2.5-pro-preview-05-06",
            google_api_key=api_key,
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text     = response.content.strip().strip('"').strip("'")
        logger.info("[Ensemble] Gemini generated: %s", text[:60])
        return text
    except Exception as e:
        logger.warning("[Ensemble] Gemini failed: %s", e)
        return None


async def _generate_with_gpt4o(prompt: str, api_key: str) -> str | None:
    """Generate wish using OpenAI GPT-4o."""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm      = ChatOpenAI(model="gpt-4o", api_key=api_key)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text     = response.content.strip().strip('"').strip("'")
        logger.info("[Ensemble] GPT-4o generated: %s", text[:60])
        return text
    except Exception as e:
        logger.warning("[Ensemble] GPT-4o failed: %s", e)
        return None


# ------------------------------------------------------------
# SCORING
# ------------------------------------------------------------

def _score_wish(wish: str, name: str, job_title: str) -> float:
    """
    Score a wish on multiple criteria (0-10).

    Criteria:
    - Mentions contact's name (+2)
    - Mentions job/context (+2)
    - Not too short (<20 chars = -3)
    - Not too long (>300 chars = -1)
    - Has warm/positive words (+2)
    - Ends with ! or positive punctuation (+1)
    - No generic phrases like "Great post!" (-2)
    """
    if not wish:
        return 0.0

    score       = 5.0
    wish_lower  = wish.lower()
    name_lower  = name.lower().split()[0] if name else ""

    # Name mention
    if name_lower and name_lower in wish_lower:
        score += 2.0

    # Job context
    if job_title and any(
        word in wish_lower
        for word in job_title.lower().split()[:3]
    ):
        score += 2.0

    # Length check
    if len(wish) < 20:
        score -= 3.0
    elif len(wish) > 300:
        score -= 1.0

    # Warm words
    warm_words = ["amazing", "wonderful", "fantastic", "incredible",
                  "great", "best", "hope", "wish", "joy", "success"]
    if any(w in wish_lower for w in warm_words):
        score += 2.0

    # Positive ending
    if wish.rstrip().endswith(("!", "??")):
        score += 0.5

    # Generic phrases (bad)
    generic = ["great post", "nice post", "interesting", "well done"]
    if any(g in wish_lower for g in generic):
        score -= 2.0

    return max(0.0, min(10.0, round(score, 1)))


# ------------------------------------------------------------
# ENSEMBLE GENERATOR
# ------------------------------------------------------------

def _build_wish_prompt(
    name: str,
    job_title: str = "",
    company: str = "",
    style: str = "warm and personal",
) -> str:
    """Build the wish generation prompt."""
    context = ""
    if job_title and company:
        context = f"They work as {job_title} at {company}."
    elif job_title:
        context = f"They work as {job_title}."

    return f"""Write a birthday wish for {name}.

Style: {style}, genuine, 2-3 sentences, 1-2 emoji
{context}

Rules:
- Start with "Happy Birthday {name}!"
- Keep it warm and personal
- Do not use generic phrases
- Reply with ONLY the wish text
"""


async def generate_ensemble_wish(
    name: str,
    profile_info: dict | None = None,
    style: str = "warm and personal",
    fallback_llm=None,
) -> dict:
    """
    Generate wish using multiple models and pick the best.

    Args:
        name         : Contact's first name
        profile_info : Dict with job_title, company etc.
        style        : Wish style description
        fallback_llm : LangChain LLM to use if ensemble is disabled

    Returns:
        Dict with best_wish, model_used, all_candidates, scores.
    """
    config    = load_ensemble_config()
    job_title = (profile_info or {}).get("job_title", "")
    company   = (profile_info or {}).get("company", "")
    prompt    = _build_wish_prompt(name, job_title, company, style)

    # If ensemble disabled or no keys → use fallback
    status = get_ensemble_status()
    if not config["enabled"] or len(status["available"]) < 2:
        logger.info("[Ensemble] Disabled or insufficient models — using fallback.")
        if fallback_llm:
            try:
                from langchain_core.messages import HumanMessage
                response = await fallback_llm.ainvoke([HumanMessage(content=prompt)])
                wish     = response.content.strip()
                return {
                    "best_wish":    wish,
                    "model_used":   "fallback",
                    "all_candidates": [wish],
                    "scores":       {"fallback": 7.0},
                }
            except Exception as e:
                logger.error("Fallback LLM failed: %s", e)
        return {
            "best_wish":    f"Happy Birthday {name}! Wishing you an amazing day!",
            "model_used":   "default",
            "all_candidates": [],
            "scores":       {},
        }

    # Build parallel tasks for available models
    tasks     = {}
    available = status["available"]

    if "claude" in available:
        tasks["claude"] = _generate_with_claude(prompt, config["anthropic_key"])
    if "gemini" in available:
        tasks["gemini"] = _generate_with_gemini(prompt, config["google_key"])
    if "gpt-4o" in available:
        tasks["gpt-4o"] = _generate_with_gpt4o(prompt, config["openai_key"])

    # Run all models in parallel
    logger.info("[Ensemble] Running %d models in parallel: %s",
                len(tasks), list(tasks.keys()))

    task_results = await asyncio.gather(
        *tasks.values(), return_exceptions=True
    )

    # Map results back to model names
    candidates = {}
    for model, result in zip(tasks.keys(), task_results):
        if isinstance(result, Exception) or result is None:
            logger.warning("[Ensemble] %s returned no result.", model)
        else:
            candidates[model] = result

    if not candidates:
        fallback = f"Happy Birthday {name}! Wishing you an amazing day!"
        return {
            "best_wish":    fallback,
            "model_used":   "default",
            "all_candidates": [fallback],
            "scores":       {"default": 5.0},
        }

    # Score each candidate
    scores = {
        model: _score_wish(wish, name, job_title)
        for model, wish in candidates.items()
    }

    best_model = max(scores, key=scores.get)
    best_wish  = candidates[best_model]

    logger.info(
        "[Ensemble] Winner: %s (score: %.1f) | All scores: %s",
        best_model, scores[best_model],
        {m: f"{s:.1f}" for m, s in scores.items()},
    )

    return {
        "best_wish":      best_wish,
        "model_used":     best_model,
        "all_candidates": list(candidates.values()),
        "scores":         scores,
    }


# ------------------------------------------------------------
# BATCH ENSEMBLE
# ------------------------------------------------------------

async def generate_ensemble_wishes_batch(
    contacts: list[dict],
    style: str = "warm and personal",
    fallback_llm=None,
) -> list[dict]:
    """
    Generate ensemble wishes for multiple contacts in parallel.

    Args:
        contacts: List of dicts with 'name' and optional 'profile_info'

    Returns:
        List of dicts with contact name, best_wish, model_used.
    """
    tasks = [
        generate_ensemble_wish(
            name=c.get("name", "Friend"),
            profile_info=c.get("profile_info", {}),
            style=style,
            fallback_llm=fallback_llm,
        )
        for c in contacts
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = []
    for contact, result in zip(contacts, results):
        if isinstance(result, Exception):
            output.append({
                "name":       contact.get("name", ""),
                "best_wish":  f"Happy Birthday {contact.get('name', 'there')}!",
                "model_used": "error",
            })
        else:
            output.append({
                "name":       contact.get("name", ""),
                "best_wish":  result["best_wish"],
                "model_used": result["model_used"],
                "score":      max(result["scores"].values(), default=0),
            })

    logger.info(
        "[Ensemble Batch] Generated %d wishes | Models: %s",
        len(output),
        set(r["model_used"] for r in output),
    )
    return output


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_ensemble_report(result: dict) -> str:
    """Build a short ensemble result report."""
    lines = [
        "Model Ensemble Report",
        "-" * 40,
        f"  Winner    : {result.get('model_used', 'N/A')}",
        f"  Best wish : {result.get('best_wish', '')[:60]}...",
        "",
        "  All candidates:",
    ]

    scores = result.get("scores", {})
    for model, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"    {model:<10} score={score:.1f}")

    return "\n".join(lines)
