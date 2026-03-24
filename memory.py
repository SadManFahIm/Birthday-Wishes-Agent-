"""
memory.py
─────────
Contact Memory System for Birthday Wishes Agent.

Remembers key details about each contact from previous interactions
and uses them to craft more personal, meaningful wishes next time.

How it works:
  1. After wishing someone, saves key profile details to SQLite
  2. Next year, retrieves those details before wishing
  3. Injects the memory into the wish prompt
  4. Agent generates a wish that references last year's context

Examples:
  "Last year you were starting a new job at Google — hope it's going amazing!"
  "Hope your startup is thriving — you were so excited about it last year!"
  "It's been a year since your promotion — hope the new role is treating you well!"

Usage:
    from memory import save_contact_memory, get_contact_memory, build_memory_instructions
"""

import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_memory_table():
    """Create the contact memory table if it doesn't exist."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_memory (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact       TEXT    NOT NULL,
                linkedin_url  TEXT,
                year          INTEGER NOT NULL,
                job_title     TEXT,
                company       TEXT,
                life_event    TEXT,
                interests     TEXT,
                last_wish     TEXT,
                notes         TEXT,
                created_at    TEXT    NOT NULL,
                UNIQUE(contact, year)
            )
        """)
        conn.commit()
    logger.info("🗄️  Contact memory table ready.")


# ──────────────────────────────────────────────
# SAVE MEMORY
# ──────────────────────────────────────────────
def save_contact_memory(
    contact: str,
    job_title: str = "",
    company: str = "",
    life_event: str = "",
    interests: list[str] = None,
    last_wish: str = "",
    notes: str = "",
    linkedin_url: str = "",
):
    """
    Save or update memory for a contact for the current year.

    Args:
        contact      : Contact's first name
        job_title    : Their current job title
        company      : Their current company
        life_event   : Any notable life event (e.g. "just got promoted", "started a startup")
        interests    : List of interests or topics they care about
        last_wish    : The exact wish message sent to them
        notes        : Any other relevant notes
        linkedin_url : Their LinkedIn profile URL
    """
    year         = date.today().year
    interests_str = json.dumps(interests or [])

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO contact_memory
                (contact, linkedin_url, year, job_title, company,
                 life_event, interests, last_wish, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact, year) DO UPDATE SET
                linkedin_url = excluded.linkedin_url,
                job_title    = excluded.job_title,
                company      = excluded.company,
                life_event   = excluded.life_event,
                interests    = excluded.interests,
                last_wish    = excluded.last_wish,
                notes        = excluded.notes
        """, (
            contact, linkedin_url, year, job_title, company,
            life_event, interests_str, last_wish, notes,
            datetime.now().isoformat(),
        ))
        conn.commit()
    logger.info("🧠 Memory saved for %s (%d)", contact, year)


# ──────────────────────────────────────────────
# GET MEMORY
# ──────────────────────────────────────────────
def get_contact_memory(contact: str, year: int = None) -> dict | None:
    """
    Retrieve memory for a contact from a previous year.

    Args:
        contact : Contact's first name
        year    : Year to retrieve (default: last year)

    Returns:
        Dict with memory details, or None if no memory found.
    """
    if not DB_FILE.exists():
        return None

    target_year = year or (date.today().year - 1)

    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT job_title, company, life_event, interests,
                   last_wish, notes, linkedin_url, year
            FROM contact_memory
            WHERE LOWER(contact) = LOWER(?) AND year = ?
        """, (contact, target_year)).fetchone()

    if not row:
        logger.info("🔍 No memory found for %s in %d", contact, target_year)
        return None

    interests = []
    try:
        interests = json.loads(row[3]) if row[3] else []
    except Exception:
        interests = []

    memory = {
        "job_title":   row[0] or "",
        "company":     row[1] or "",
        "life_event":  row[2] or "",
        "interests":   interests,
        "last_wish":   row[4] or "",
        "notes":       row[5] or "",
        "linkedin_url": row[6] or "",
        "year":        row[7],
    }
    logger.info("🧠 Memory retrieved for %s (%d): %s at %s",
                contact, target_year, memory["job_title"], memory["company"])
    return memory


def get_all_memories(contact: str) -> list[dict]:
    """
    Retrieve all memory records for a contact across all years.
    Useful for long-term context.
    """
    if not DB_FILE.exists():
        return []

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT year, job_title, company, life_event,
                   interests, last_wish, notes
            FROM contact_memory
            WHERE LOWER(contact) = LOWER(?)
            ORDER BY year DESC
        """, (contact,)).fetchall()

    return [
        {
            "year":      r[0],
            "job_title": r[1] or "",
            "company":   r[2] or "",
            "life_event": r[3] or "",
            "interests": json.loads(r[4]) if r[4] else [],
            "last_wish": r[5] or "",
            "notes":     r[6] or "",
        }
        for r in rows
    ]


# ──────────────────────────────────────────────
# BUILD MEMORY CONTEXT STRING
# ──────────────────────────────────────────────
def build_memory_context(contact: str) -> str:
    """
    Build a natural language memory context string for a contact.
    This is injected into the wish generation prompt.

    Returns:
        A string describing what we know about this contact from last year,
        or an empty string if no memory exists.
    """
    memory = get_contact_memory(contact)
    if not memory:
        return ""

    parts = []
    year  = memory["year"]

    if memory["life_event"]:
        parts.append(f"Last year ({year}) they mentioned: {memory['life_event']}")

    if memory["job_title"] and memory["company"]:
        parts.append(f"They were working as {memory['job_title']} at {memory['company']}")
    elif memory["job_title"]:
        parts.append(f"They were a {memory['job_title']}")
    elif memory["company"]:
        parts.append(f"They were working at {memory['company']}")

    if memory["interests"]:
        interests_str = ", ".join(memory["interests"])
        parts.append(f"Their interests include: {interests_str}")

    if memory["notes"]:
        parts.append(f"Additional context: {memory['notes']}")

    if not parts:
        return ""

    context = ". ".join(parts) + "."
    logger.info("🧠 Memory context for %s: %s", contact, context[:80] + "...")
    return context


# ──────────────────────────────────────────────
# MEMORY-AWARE WISH PROMPT BUILDER
# ──────────────────────────────────────────────
async def generate_memory_aware_wish(llm, name: str, profile_info: dict) -> str:
    """
    Generate a birthday wish that references last year's memory.

    Args:
        llm          : LangChain LLM instance
        name         : Contact's first name
        profile_info : Current profile info (job, company, etc.)

    Returns:
        A unique, memory-aware birthday wish string.
    """
    from langchain_core.messages import HumanMessage

    memory_context = build_memory_context(name)
    current_job    = profile_info.get("job_title", "")
    current_company = profile_info.get("company", "")
    interests      = ", ".join(profile_info.get("shared_interests", []))

    # Build memory reference section
    memory_section = ""
    if memory_context:
        memory_section = f"""
  MEMORY FROM LAST YEAR:
  {memory_context}

  Use this memory to make the wish feel personal and continuous.
  Reference something from last year naturally — but ONLY if it still
  seems relevant and positive. Do not bring up anything negative.

  Example references:
  - "Hope your journey at Google is going amazing — it's been a year already!"
  - "Last year you were just starting your new role — hope it's been incredible!"
  - "Hope the startup is thriving — you were so passionate about it last year!"
"""
    else:
        memory_section = "  No previous memory found — write a warm first-time wish."

    prompt = f"""
You are writing a birthday wish for a LinkedIn connection.

Contact: {name}
Current job title: {current_job or "Unknown"}
Current company:   {current_company or "Unknown"}
Interests:         {interests or "Unknown"}

{memory_section}

Write ONE birthday wish (2-3 sentences) that:
  ✅ Starts with "Happy Birthday {name}!"
  ✅ If memory exists → naturally references something from last year
  ✅ Mentions their current role or company if known
  ✅ Feels warm, genuine, and personal
  ✅ Ends with a positive wish for the year ahead
  ✅ Includes 1-2 relevant emojis
  ❌ Does NOT sound like a template or AI text
  ❌ Is NOT longer than 3 sentences

Reply with ONLY the wish. No quotes, no explanation.
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        wish = response.content.strip().strip('"').strip("'")
        logger.info("✨ Memory-aware wish for %s: %s", name, wish[:60] + "...")
        return wish
    except Exception as e:
        logger.error("❌ Memory wish generation failed for %s: %s", name, e)
        return f"Happy Birthday {name}! 🎂 Wishing you an incredible year ahead!"


# ──────────────────────────────────────────────
# BROWSER AGENT INSTRUCTIONS
# ──────────────────────────────────────────────
def build_memory_instructions(contact: str) -> str:
    """
    Build memory-aware instructions for the browser agent.
    Injects last year's context into the wish prompt.
    """
    memory_context = build_memory_context(contact)

    if not memory_context:
        return """
  MEMORY SYSTEM: No previous memory found for this contact.
  Write a warm, genuine first-time birthday wish.
"""

    return f"""
  MEMORY SYSTEM — LAST YEAR'S CONTEXT:
  {memory_context}

  Use this information to make the wish feel personal and thoughtful.
  Naturally reference something from last year in the wish.
  Keep it warm, positive, and genuine — 2-3 sentences max.

  Example:
  "Happy Birthday Rahul! 🎂 Hope your first year at Google has been
   everything you dreamed of — you were so excited about it last year!
   Wishing you even bigger milestones in the year ahead! 🚀"
"""


# ──────────────────────────────────────────────
# SAVE MEMORY FROM AGENT RESULT
# ──────────────────────────────────────────────
def extract_and_save_memory(contact: str, profile_info: dict, wish_sent: str):
    """
    Extract key details from profile_info and save to memory.
    Called after a wish is successfully sent.

    Args:
        contact      : Contact's first name
        profile_info : Profile details scraped from LinkedIn
        wish_sent    : The exact wish message that was sent
    """
    save_contact_memory(
        contact=contact,
        job_title=profile_info.get("job_title", ""),
        company=profile_info.get("company", ""),
        life_event=profile_info.get("additional_notes", ""),
        interests=profile_info.get("shared_interests", []),
        last_wish=wish_sent,
        linkedin_url=profile_info.get("linkedin_url", ""),
    )