"""
contact_categorizer.py
──────────────────────
Contact Categorizer module for Birthday Wishes Agent.

Automatically categorizes LinkedIn contacts by:
  - Industry (Tech, Finance, Healthcare, Education, etc.)
  - Seniority (Student, Junior, Mid, Senior, Executive, Founder)
  - Location (Country/Region)
  - Relationship Type (Colleague, Mentor, Peer, Client, etc.)
  - Engagement Level (High, Medium, Low, Dormant)

Categories are saved to SQLite and used to:
  - Filter contacts for targeted campaigns
  - Customize wish/message style per category
  - Generate category-based analytics

Usage:
    from contact_categorizer import (
        categorize_contact,
        get_contacts_by_category,
        build_categorization_task
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
# CATEGORY DEFINITIONS
# ──────────────────────────────────────────────
INDUSTRIES = [
    "Technology", "Finance", "Healthcare", "Education",
    "Marketing", "Sales", "Design", "Engineering",
    "Consulting", "Legal", "Media", "Real Estate",
    "Retail", "Manufacturing", "Non-profit", "Government",
    "Hospitality", "Agriculture", "Energy", "Other",
]

SENIORITY_LEVELS = [
    "Student", "Intern", "Junior", "Mid-level",
    "Senior", "Lead", "Manager", "Director",
    "VP", "C-Suite", "Founder", "Freelancer",
]

RELATIONSHIP_TYPES = [
    "Colleague", "Former Colleague", "Classmate",
    "Mentor", "Mentee", "Client", "Vendor",
    "Peer", "Friend", "Recruiter", "Investor",
    "Industry Contact", "Unknown",
]

ENGAGEMENT_LEVELS = {
    "high":    "Regularly interacts — likes, comments, messages",
    "medium":  "Occasional interactions",
    "low":     "Rarely interacts",
    "dormant": "No interaction in 6+ months",
}


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_categorizer_table():
    """Create the contact categories table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_categories (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                contact          TEXT    NOT NULL UNIQUE,
                industry         TEXT,
                seniority        TEXT,
                location         TEXT,
                country          TEXT,
                relationship_type TEXT,
                engagement_level TEXT,
                tags             TEXT,
                notes            TEXT,
                confidence       REAL    DEFAULT 0.0,
                last_updated     TEXT    NOT NULL,
                created_at       TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  Contact categorizer table ready.")


def save_category(
    contact: str,
    industry: str = "",
    seniority: str = "",
    location: str = "",
    country: str = "",
    relationship_type: str = "",
    engagement_level: str = "",
    tags: list[str] = None,
    notes: str = "",
    confidence: float = 0.0,
):
    """Save or update a contact's categories."""
    tags_str = json.dumps(tags or [])
    now      = datetime.now().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO contact_categories
                (contact, industry, seniority, location, country,
                 relationship_type, engagement_level, tags, notes,
                 confidence, last_updated, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact) DO UPDATE SET
                industry         = excluded.industry,
                seniority        = excluded.seniority,
                location         = excluded.location,
                country          = excluded.country,
                relationship_type= excluded.relationship_type,
                engagement_level = excluded.engagement_level,
                tags             = excluded.tags,
                notes            = excluded.notes,
                confidence       = excluded.confidence,
                last_updated     = excluded.last_updated
        """, (
            contact, industry, seniority, location, country,
            relationship_type, engagement_level, tags_str, notes,
            confidence, now, now,
        ))
        conn.commit()
    logger.info("🏷️  Category saved for %s: %s | %s | %s",
                contact, industry, seniority, engagement_level)


def get_category(contact: str) -> dict | None:
    """Get categories for a specific contact."""
    if not DB_FILE.exists():
        return None
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT industry, seniority, location, country, "
            "relationship_type, engagement_level, tags, notes, confidence "
            "FROM contact_categories WHERE LOWER(contact) = LOWER(?)",
            (contact,),
        ).fetchone()
    if not row:
        return None
    return {
        "industry":         row[0] or "",
        "seniority":        row[1] or "",
        "location":         row[2] or "",
        "country":          row[3] or "",
        "relationship_type": row[4] or "",
        "engagement_level": row[5] or "",
        "tags":             json.loads(row[6]) if row[6] else [],
        "notes":            row[7] or "",
        "confidence":       row[8] or 0.0,
    }


def get_contacts_by_category(
    industry: str = None,
    seniority: str = None,
    country: str = None,
    engagement_level: str = None,
    relationship_type: str = None,
) -> list[str]:
    """
    Get contacts filtered by one or more categories.

    Returns:
        List of contact names matching all provided filters.
    """
    if not DB_FILE.exists():
        return []

    query  = "SELECT contact FROM contact_categories WHERE 1=1"
    params = []

    if industry:
        query  += " AND LOWER(industry) = LOWER(?)"
        params.append(industry)
    if seniority:
        query  += " AND LOWER(seniority) = LOWER(?)"
        params.append(seniority)
    if country:
        query  += " AND LOWER(country) = LOWER(?)"
        params.append(country)
    if engagement_level:
        query  += " AND LOWER(engagement_level) = LOWER(?)"
        params.append(engagement_level)
    if relationship_type:
        query  += " AND LOWER(relationship_type) = LOWER(?)"
        params.append(relationship_type)

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(query, params).fetchall()

    contacts = [r[0] for r in rows]
    logger.info("🔍 Found %d contacts matching filters.", len(contacts))
    return contacts


def get_category_stats() -> dict:
    """Get statistics across all categories."""
    if not DB_FILE.exists():
        return {}
    with sqlite3.connect(DB_FILE) as conn:
        by_industry = conn.execute(
            "SELECT industry, COUNT(*) FROM contact_categories "
            "WHERE industry != '' GROUP BY industry ORDER BY COUNT(*) DESC"
        ).fetchall()
        by_seniority = conn.execute(
            "SELECT seniority, COUNT(*) FROM contact_categories "
            "WHERE seniority != '' GROUP BY seniority ORDER BY COUNT(*) DESC"
        ).fetchall()
        by_country = conn.execute(
            "SELECT country, COUNT(*) FROM contact_categories "
            "WHERE country != '' GROUP BY country ORDER BY COUNT(*) DESC LIMIT 10"
        ).fetchall()
        by_engagement = conn.execute(
            "SELECT engagement_level, COUNT(*) FROM contact_categories "
            "WHERE engagement_level != '' GROUP BY engagement_level"
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM contact_categories"
        ).fetchone()[0]

    return {
        "total_categorized": total,
        "by_industry":   {r[0]: r[1] for r in by_industry},
        "by_seniority":  {r[0]: r[1] for r in by_seniority},
        "by_country":    {r[0]: r[1] for r in by_country},
        "by_engagement": {r[0]: r[1] for r in by_engagement},
    }


# ──────────────────────────────────────────────
# RULE-BASED FAST CATEGORIZATION
# ──────────────────────────────────────────────
def quick_categorize(job_title: str, company: str = "") -> dict:
    """
    Fast rule-based categorization from job title.
    Returns partial categories with lower confidence.
    """
    title_lower = job_title.lower()

    # Seniority detection
    seniority = "Mid-level"
    if any(w in title_lower for w in ["intern", "student", "trainee"]):
        seniority = "Intern"
    elif any(w in title_lower for w in ["junior", "jr.", "associate"]):
        seniority = "Junior"
    elif any(w in title_lower for w in ["senior", "sr.", "lead", "principal"]):
        seniority = "Senior"
    elif any(w in title_lower for w in ["manager", "head of", "team lead"]):
        seniority = "Manager"
    elif any(w in title_lower for w in ["director", "vp", "vice president"]):
        seniority = "Director"
    elif any(w in title_lower for w in ["ceo", "cto", "cfo", "coo", "chief",
                                         "founder", "co-founder", "president"]):
        seniority = "C-Suite"

    # Industry detection
    industry = "Other"
    if any(w in title_lower for w in ["engineer", "developer", "software",
                                       "data", "ai", "ml", "tech", "it ",
                                       "product", "devops", "cloud"]):
        industry = "Technology"
    elif any(w in title_lower for w in ["finance", "accounting", "analyst",
                                         "investment", "banking", "trader"]):
        industry = "Finance"
    elif any(w in title_lower for w in ["doctor", "nurse", "medical", "health",
                                         "pharma", "clinical"]):
        industry = "Healthcare"
    elif any(w in title_lower for w in ["teacher", "professor", "lecturer",
                                         "education", "academic", "researcher"]):
        industry = "Education"
    elif any(w in title_lower for w in ["marketing", "brand", "content",
                                         "social media", "seo", "growth"]):
        industry = "Marketing"
    elif any(w in title_lower for w in ["design", "ux", "ui", "graphic",
                                         "creative", "art director"]):
        industry = "Design"
    elif any(w in title_lower for w in ["sales", "business development",
                                         "account executive", "revenue"]):
        industry = "Sales"
    elif any(w in title_lower for w in ["lawyer", "attorney", "legal",
                                         "counsel", "paralegal"]):
        industry = "Legal"

    return {
        "industry":   industry,
        "seniority":  seniority,
        "confidence": 0.6,
    }


# ──────────────────────────────────────────────
# LLM CATEGORIZATION
# ──────────────────────────────────────────────
async def categorize_contact_with_llm(
    llm,
    contact: str,
    profile_info: dict,
) -> dict:
    """
    Use LLM to categorize a contact from their profile info.

    Args:
        llm          : LangChain LLM instance
        contact      : Contact's name
        profile_info : Dict with job_title, company, location, bio, etc.

    Returns:
        Full category dict.
    """
    from langchain_core.messages import HumanMessage

    industries_str   = ", ".join(INDUSTRIES)
    seniority_str    = ", ".join(SENIORITY_LEVELS)
    rel_types_str    = ", ".join(RELATIONSHIP_TYPES)
    engagement_str   = ", ".join(ENGAGEMENT_LEVELS.keys())

    prompt = f"""
Categorize this LinkedIn contact based on their profile information.

Contact: {contact}
Job Title: {profile_info.get('job_title', 'Unknown')}
Company: {profile_info.get('company', 'Unknown')}
Location: {profile_info.get('location', 'Unknown')}
Bio/About: {profile_info.get('bio', 'Not available')}
Recent Activity: {profile_info.get('recent_activity', 'Unknown')}

Categorize using these options:
  Industry         : {industries_str}
  Seniority        : {seniority_str}
  Relationship Type: {rel_types_str}
  Engagement Level : {engagement_str}

Return ONLY a JSON object:
{{
  "industry":         "Technology",
  "seniority":        "Senior",
  "location":         "Dhaka, Bangladesh",
  "country":          "Bangladesh",
  "relationship_type": "Industry Contact",
  "engagement_level": "medium",
  "tags":             ["AI", "Python", "startup"],
  "confidence":       0.85
}}

No extra text. JSON only.
"""
    try:
        import json as jsonlib
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text     = response.content.strip().replace("```json", "").replace("```", "").strip()
        result   = jsonlib.loads(text)
        logger.info("🏷️  LLM categorized %s: %s | %s",
                    contact, result.get("industry"), result.get("seniority"))
        return result
    except Exception as e:
        logger.warning("⚠️  LLM categorization failed for %s: %s", contact, e)
        # Fall back to rule-based
        quick = quick_categorize(
            profile_info.get("job_title", ""),
            profile_info.get("company", ""),
        )
        return {**quick, "location": "", "country": "",
                "relationship_type": "Unknown",
                "engagement_level": "low", "tags": []}


# ──────────────────────────────────────────────
# BROWSER TASK
# ──────────────────────────────────────────────
def build_categorization_task(
    username: str,
    password: str,
    already_logged_in: bool,
    max_contacts: int = 30,
) -> str:
    """Build a browser agent task to categorize LinkedIn contacts."""
    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {username}\n"
            f"  Password: {password}\n"
        )
    )

    industries_str = ", ".join(INDUSTRIES[:10])
    seniority_str  = ", ".join(SENIORITY_LEVELS[:8])

    return f"""
  Open the browser.
  {login_instructions}

  GOAL: Categorize your LinkedIn connections by industry, seniority,
  location, and relationship type.

  STEP 1 — Go to https://www.linkedin.com/mynetwork/
    Click "Connections" to see your full connection list.

  STEP 2 — For each connection (up to {max_contacts}):
    a) Visit their profile.
    b) Extract:
       - Full name and first name
       - Current job title
       - Current company
       - Location (city, country)
       - Industry (from profile or infer from job title)
       - Seniority level (from job title)
       - How you know them (colleague, classmate, industry contact, etc.)

  STEP 3 — Return all data as a JSON array:
  [
    {{
      "name": "Rahul Ahmed",
      "job_title": "Senior Software Engineer",
      "company": "Google",
      "location": "Dhaka, Bangladesh",
      "country": "Bangladesh",
      "industry": "Technology",
      "seniority": "Senior",
      "relationship_type": "Industry Contact",
      "tags": ["Python", "AI", "Open Source"]
    }}
  ]

  Industry options: {industries_str}, etc.
  Seniority options: {seniority_str}, etc.

  Return ONLY the JSON array. No extra text.
"""


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_contact_categorizer(
    llm,
    browser,
    username: str,
    password: str,
    already_logged_in: bool,
    max_contacts: int = 30,
) -> int:
    """
    Scan and categorize LinkedIn contacts.

    Returns:
        Number of contacts categorized.
    """
    import json as jsonlib
    from browser_use import Agent

    logger.info("=== Contact Categorizer === (up to %d contacts)", max_contacts)

    task   = build_categorization_task(
        username=username,
        password=password,
        already_logged_in=already_logged_in,
        max_contacts=max_contacts,
    )
    agent  = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()

    # Parse and save categories
    count = 0
    try:
        result_str = str(result)
        start      = result_str.find("[")
        end        = result_str.rfind("]") + 1
        if start != -1 and end > start:
            contacts = jsonlib.loads(result_str[start:end])
            for c in contacts:
                name = c.get("name", "")
                if not name:
                    continue
                # Quick engagement level from history
                engagement = _infer_engagement(name)
                save_category(
                    contact=c.get("name", ""),
                    industry=c.get("industry", ""),
                    seniority=c.get("seniority", ""),
                    location=c.get("location", ""),
                    country=c.get("country", ""),
                    relationship_type=c.get("relationship_type", ""),
                    engagement_level=engagement,
                    tags=c.get("tags", []),
                    confidence=0.8,
                )
                count += 1
            logger.info("🏷️  Categorized %d contacts.", count)
    except Exception as e:
        logger.error("❌ Could not parse categorization result: %s", e)

    return count


def _infer_engagement(contact: str) -> str:
    """Infer engagement level from interaction history."""
    if not DB_FILE.exists():
        return "low"
    from datetime import date, timedelta
    month_ago = (date.today() - timedelta(days=30)).isoformat()
    year_ago  = (date.today() - timedelta(days=365)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        recent = conn.execute(
            "SELECT COUNT(*) FROM history "
            "WHERE LOWER(contact) = LOWER(?) AND date >= ? AND dry_run = 0",
            (contact, month_ago),
        ).fetchone()[0]
        yearly = conn.execute(
            "SELECT COUNT(*) FROM history "
            "WHERE LOWER(contact) = LOWER(?) AND date >= ? AND dry_run = 0",
            (contact, year_ago),
        ).fetchone()[0]
    if recent >= 3:
        return "high"
    elif recent >= 1 or yearly >= 3:
        return "medium"
    elif yearly >= 1:
        return "low"
    else:
        return "dormant"