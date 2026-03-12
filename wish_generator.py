"""
wish_generator.py
─────────────────
AI-powered personalized birthday wish generator.

Instead of using fixed templates, this module:
  1. Fetches the contact's LinkedIn profile info
     (job title, company, mutual connections, shared interests)
  2. Sends that info to the LLM
  3. Gets back a completely unique, personalized birthday wish

Usage:
    from wish_generator import generate_custom_wish

    wish = await generate_custom_wish(
        llm=llm,
        name="Rahul Ahmed",
        profile_info={
            "job_title": "Software Engineer",
            "company": "Google",
            "mutual_connections": 12,
            "shared_interests": ["AI", "Python"],
        }
    )
    print(wish)
    # "Happy Birthday Rahul! 🎂 Hope your journey at Google keeps inspiring
    #  the amazing engineer in you. Wishing you a year full of breakthroughs!"
"""

import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# WISH GENERATOR
# ──────────────────────────────────────────────
async def generate_custom_wish(
    llm,
    name: str,
    profile_info: dict,
) -> str:
    """
    Generate a unique, personalized birthday wish using the LLM.

    Args:
        llm          : LangChain LLM instance (Gemini or OpenAI)
        name         : Contact's first name
        profile_info : Dict with keys:
                         - job_title        (str)
                         - company          (str)
                         - mutual_connections (int)
                         - shared_interests  (list[str])
                         - additional_notes  (str, optional)

    Returns:
        A unique birthday wish string.
    """
    job_title         = profile_info.get("job_title", "")
    company           = profile_info.get("company", "")
    mutual_connections = profile_info.get("mutual_connections", 0)
    shared_interests  = profile_info.get("shared_interests", [])
    additional_notes  = profile_info.get("additional_notes", "")

    interests_str = ", ".join(shared_interests) if shared_interests else "not available"

    prompt = f"""
You are writing a warm, genuine birthday wish for a LinkedIn connection.

Contact details:
  Name              : {name}
  Job Title         : {job_title or "Not available"}
  Company           : {company or "Not available"}
  Mutual Connections: {mutual_connections}
  Shared Interests  : {interests_str}
  Additional Notes  : {additional_notes or "None"}

Write ONE short birthday wish (2-3 sentences max) that:
  ✅ Starts with "Happy Birthday {name}!"
  ✅ Mentions their profession or company naturally (if available)
  ✅ Feels warm, genuine, and personal — not generic
  ✅ Ends with a positive wish for the year ahead
  ✅ Includes 1-2 relevant emojis
  ❌ Does NOT sound like a template or AI-generated text
  ❌ Does NOT mention "mutual connections" directly
  ❌ Is NOT longer than 3 sentences

Reply with ONLY the wish text. No quotes, no explanation.
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        wish = response.content.strip().strip('"').strip("'")
        logger.info("✨ Custom wish generated for %s: %s", name, wish)
        return wish
    except Exception as e:
        logger.error("❌ Wish generation failed for %s: %s", name, e)
        # Fallback to a simple wish
        return f"Happy Birthday {name}! 🎂 Wishing you an amazing year ahead!"


# ──────────────────────────────────────────────
# PROFILE SCRAPER TASK (for browser agent)
# ──────────────────────────────────────────────
def build_profile_scrape_task(profile_url: str) -> str:
    """
    Build a browser agent task to scrape profile info from LinkedIn.

    Returns a task string that instructs the agent to extract
    job title, company, mutual connections, and shared interests.
    """
    return f"""
  Go to this LinkedIn profile: {profile_url}

  Extract the following information and return it as JSON:
  {{
    "name": "<full name>",
    "first_name": "<first name only>",
    "job_title": "<current job title>",
    "company": "<current company name>",
    "mutual_connections": <number of mutual connections, 0 if not shown>,
    "shared_interests": ["<interest1>", "<interest2>"],
    "additional_notes": "<any other relevant info like recent achievement, post, etc.>"
  }}

  Rules:
  - If any field is not available, use "" for strings and 0 for numbers.
  - For shared_interests, look at their skills, posts, or activity section.
  - Return ONLY the JSON object. No extra text.
"""