"""
linkedin_post_commenter.py
--------------------------
LinkedIn Post Auto-Commenter for Birthday Wishes Agent.

Monitors LinkedIn connections' new posts and automatically
leaves smart, personalized comments to stay engaged.

How it works:
  1. Scans recent posts from tracked contacts
  2. Detects post topic/tone using AI
  3. Generates a relevant, natural comment
  4. Posts the comment (with cooldown to avoid spam)
  5. Logs all comments to SQLite

Comment rules:
  - Max 1 comment per contact per day
  - Max 10 comments per run
  - Skips posts older than 48 hours
  - Never comments on own posts
  - Avoids generic/spammy comments

Post types handled:
  - Career update (promotion, new job)
  - Achievement / milestone
  - Thought leadership / opinion
  - Industry news share
  - Personal update
  - General post

Usage:
    from linkedin_post_commenter import (
        init_commenter_table,
        run_post_commenter,
        get_recent_comments,
        build_comment_report,
    )

    await run_post_commenter(dry_run=True)
"""

import logging
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

MAX_COMMENTS_PER_RUN = 10
MAX_COMMENTS_PER_DAY = 15
COMMENT_COOLDOWN_DAYS = 1
POST_MAX_AGE_HOURS = 48

# Comment templates per post type
COMMENT_TEMPLATES = {
    "career_update": [
        "Congratulations {name}! This is well deserved. Wishing you all the best in this new chapter!",
        "Amazing news {name}! Congratulations on this exciting move. Looking forward to seeing what you achieve!",
        "Big congratulations {name}! You have worked hard for this. Exciting times ahead!",
    ],
    "achievement": [
        "Fantastic achievement {name}! Really inspiring to see. Keep up the great work!",
        "Congratulations on this milestone {name}! Well done and well deserved.",
        "This is incredible {name}! Congratulations on this accomplishment.",
    ],
    "thought_leadership": [
        "Really insightful perspective {name}! This resonates a lot. Thanks for sharing.",
        "Great point {name}! This is something many of us can relate to in the industry.",
        "Valuable insights as always {name}! Really appreciate you sharing this perspective.",
    ],
    "industry_news": [
        "Thanks for sharing this {name}! Really interesting development in the space.",
        "Great share {name}! This is definitely something worth keeping an eye on.",
        "Insightful share {name}! This is going to have a big impact on the industry.",
    ],
    "personal_update": [
        "That sounds amazing {name}! Thanks for sharing this with us.",
        "Lovely update {name}! Wishing you all the best with this.",
        "Really happy to hear this {name}! All the very best.",
    ],
    "general": [
        "Great post {name}! Really enjoyed reading this.",
        "Thanks for sharing {name}! Really valuable content.",
        "Love this {name}! Always great to see your posts.",
    ],
}


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_commenter_table():
    """Create post commenter tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS post_comments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact       TEXT    NOT NULL,
                post_url      TEXT,
                post_type     TEXT,
                comment_text  TEXT,
                dry_run       INTEGER DEFAULT 1,
                comment_date  TEXT    NOT NULL,
                created_at    TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Post commenter table ready.")


# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def get_comments_today() -> int:
    """Count comments sent today."""
    if not DB_FILE.exists():
        return 0
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM post_comments
            WHERE comment_date = ? AND dry_run = 0
        """, (date.today().isoformat(),)).fetchone()
    return row[0] or 0


def already_commented_recently(contact: str) -> bool:
    """Check if we already commented on this contact's post recently."""
    if not DB_FILE.exists():
        return False
    cutoff = (date.today() - timedelta(days=COMMENT_COOLDOWN_DAYS)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM post_comments
            WHERE LOWER(contact) = LOWER(?)
              AND comment_date >= ?
              AND dry_run = 0
        """, (contact, cutoff)).fetchone()
    return (row[0] or 0) > 0


def log_comment(
    contact: str,
    post_url: str,
    post_type: str,
    comment_text: str,
    dry_run: bool = True,
):
    """Log a posted comment."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO post_comments
            (contact, post_url, post_type, comment_text,
             dry_run, comment_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (contact, post_url, post_type, comment_text,
              int(dry_run), date.today().isoformat(),
              datetime.now().isoformat()))
        conn.commit()
    logger.info("Comment logged: %s | type: %s", contact, post_type)


def get_recent_comments(days: int = 7) -> list[dict]:
    """Get recently posted comments."""
    if not DB_FILE.exists():
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT contact, post_type, comment_text, comment_date, dry_run
            FROM   post_comments
            WHERE  comment_date >= ?
            ORDER  BY comment_date DESC
        """, (cutoff,)).fetchall()
    return [
        {
            "contact":      row[0],
            "post_type":    row[1],
            "comment_text": row[2],
            "date":         row[3],
            "dry_run":      bool(row[4]),
        }
        for row in rows
    ]


# ------------------------------------------------------------
# COMMENT GENERATION
# ------------------------------------------------------------

def get_comment(contact_name: str, post_type: str) -> str:
    """Get a personalized comment for a post."""
    first_name = contact_name.split()[0].capitalize()
    templates  = COMMENT_TEMPLATES.get(post_type, COMMENT_TEMPLATES["general"])
    template   = random.choice(templates)
    return template.format(name=first_name)


def detect_post_type(post_text: str) -> str:
    """
    Detect post type from text content.

    Returns:
        Post type string: career_update / achievement / thought_leadership /
                          industry_news / personal_update / general
    """
    text = post_text.lower()

    career_keywords = [
        "excited to announce", "thrilled to share", "new role",
        "joined", "starting", "promotion", "promoted",
        "new position", "new chapter", "new opportunity",
    ]
    achievement_keywords = [
        "achieved", "milestone", "certified", "graduated",
        "award", "recognized", "completed", "launched", "published",
    ]
    thought_keywords = [
        "thoughts on", "i believe", "in my opinion", "perspective",
        "lesson", "learned", "experience has taught", "unpopular opinion",
        "hot take", "here is why",
    ]
    news_keywords = [
        "breaking", "news", "report", "study shows", "according to",
        "article", "research", "survey", "data shows", "industry",
    ]
    personal_keywords = [
        "grateful", "blessed", "family", "personal", "journey",
        "reflection", "anniversary", "birthday", "travel",
    ]

    if any(k in text for k in career_keywords):
        return "career_update"
    if any(k in text for k in achievement_keywords):
        return "achievement"
    if any(k in text for k in thought_keywords):
        return "thought_leadership"
    if any(k in text for k in news_keywords):
        return "industry_news"
    if any(k in text for k in personal_keywords):
        return "personal_update"
    return "general"


# ------------------------------------------------------------
# AGENT TASK
# ------------------------------------------------------------

def build_commenter_task(
    contacts: list[str],
    username: str,
    password: str,
    already_logged_in: bool = False,
    dry_run: bool = True,
    max_comments: int = MAX_COMMENTS_PER_RUN,
) -> str:
    """Build agent task to scan and comment on recent posts."""
    login = (
        "You are already logged into LinkedIn. Skip login."
        if already_logged_in
        else f"Go to https://linkedin.com and log in:\n"
             f"  Email: {username}\n  Password: {password}\n"
    )

    dry = "[DRY RUN] Do NOT post. Print what you would comment." if dry_run else ""

    contacts_str = "\n".join(f"  - {c}" for c in contacts)

    return f"""
Open browser. {login}
{dry}

GOAL: Find recent posts from contacts and leave smart comments.

Contacts to check:
{contacts_str}

For each contact:
  1. Go to their LinkedIn profile
  2. Look at their recent posts (last 48 hours only)
  3. If they have a recent post:
     a) Read the post content
     b) Detect the post type:
        - career_update: promotion, new job, new role
        - achievement: award, milestone, certification
        - thought_leadership: opinion, insight, lesson
        - industry_news: sharing news or article
        - personal_update: personal story, gratitude
        - general: anything else
     c) Generate a natural, relevant comment (2-3 sentences max)
     d) Post the comment
     e) Report: COMMENTED: <name> | <post_type> | <comment_text>
  4. If no recent post (older than 48h): SKIPPED: <name> (no recent post)
  5. If already commented recently: SKIPPED: <name> (already commented)

Rules:
  - Max {max_comments} comments total this run
  - Never use generic phrases like "Great post!" alone
  - Comment must be relevant to the post content
  - Keep it professional and warm
  - Never comment on sensitive or controversial posts
"""


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_comment_report(results: list[dict]) -> str:
    """Build human-readable comment report."""
    if not results:
        return "No comments posted."

    commented = [r for r in results if r.get("status") == "commented"]
    skipped   = [r for r in results if r.get("status") == "skipped"]

    lines = [
        "LinkedIn Post Auto-Comment Report",
        "-" * 55,
        f"  Commented : {len(commented)}",
        f"  Skipped   : {len(skipped)}",
        f"  Date      : {date.today().isoformat()}",
        "-" * 55,
        "",
    ]

    if commented:
        lines.append("Comments Posted:")
        for r in commented:
            lines.append(f"  + {r['contact']} [{r.get('post_type', 'general')}]")
            lines.append(f"    {r.get('comment', '')[:80]}...")
            lines.append("")

    if skipped:
        lines.append("Skipped:")
        for r in skipped:
            lines.append(f"  - {r['contact']}: {r.get('reason', '')}")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# RESULT PARSER
# ------------------------------------------------------------

def parse_comment_result(result_text: str) -> list[dict]:
    """
    Parse agent result into list of comment results.

    Expected formats:
      COMMENTED: <name> | <post_type> | <comment_text>
      SKIPPED: <name> (reason)
    """
    results = []
    for line in result_text.splitlines():
        line = line.strip()
        if line.upper().startswith("COMMENTED:"):
            try:
                parts = line[10:].split("|")
                if len(parts) >= 3:
                    results.append({
                        "contact":   parts[0].strip(),
                        "post_type": parts[1].strip(),
                        "comment":   parts[2].strip(),
                        "status":    "commented",
                    })
            except Exception:
                continue
        elif line.upper().startswith("SKIPPED:"):
            try:
                content = line[8:].strip()
                name    = content.split("(")[0].strip()
                reason  = content.split("(")[1].rstrip(")") if "(" in content else ""
                results.append({
                    "contact": name,
                    "reason":  reason,
                    "status":  "skipped",
                })
            except Exception:
                continue
    return results


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_post_commenter(
    llm=None,
    browser=None,
    username: str = "",
    password: str = "",
    already_logged_in: bool = False,
    dry_run: bool = True,
    contacts: list[str] | None = None,
    max_comments: int = MAX_COMMENTS_PER_RUN,
) -> dict:
    """
    Main runner. Call from agent.py daily.

    Args:
        llm               : LangChain LLM instance
        browser           : browser_use Browser instance
        username          : LinkedIn email
        password          : LinkedIn password
        already_logged_in : Skip login if True
        dry_run           : If True, log only - do not post
        contacts          : List of contacts to check.
                            If None, reads from history.
        max_comments      : Max comments to post per run

    Returns:
        Dict with summary stats.
    """
    from browser_use import Agent

    logger.info("=== LinkedIn Post Auto-Commenter === [DRY RUN: %s]", dry_run)

    # Check daily limit
    today_count = get_comments_today()
    if today_count >= MAX_COMMENTS_PER_DAY:
        logger.info("Daily comment limit reached (%d/%d).",
                    today_count, MAX_COMMENTS_PER_DAY)
        return {"commented": 0, "reason": "daily limit reached"}

    remaining = min(max_comments, MAX_COMMENTS_PER_DAY - today_count)

    # Get contacts
    if not contacts:
        contacts = _get_contacts_from_history()

    # Filter already commented recently
    contacts = [
        c for c in contacts
        if not already_commented_recently(c)
    ][:remaining]

    if not contacts:
        logger.info("No contacts to comment on.")
        return {"commented": 0, "skipped": 0}

    logger.info("Checking posts for %d contacts...", len(contacts))

    task = build_commenter_task(
        contacts=contacts,
        username=username,
        password=password,
        already_logged_in=already_logged_in,
        dry_run=dry_run,
        max_comments=remaining,
    )

    results = []
    try:
        agent       = Agent(task=task, llm=llm, browser=browser)
        result      = await agent.run()
        results     = parse_comment_result(str(result))

        # Log commented posts
        for r in results:
            if r["status"] == "commented" and not dry_run:
                log_comment(
                    contact=r["contact"],
                    post_url="",
                    post_type=r.get("post_type", "general"),
                    comment_text=r.get("comment", ""),
                    dry_run=False,
                )
            elif r["status"] == "commented" and dry_run:
                log_comment(
                    contact=r["contact"],
                    post_url="",
                    post_type=r.get("post_type", "general"),
                    comment_text=r.get("comment", ""),
                    dry_run=True,
                )

    except Exception as e:
        logger.error("Post commenter task failed: %s", e)

    commented = len([r for r in results if r["status"] == "commented"])
    skipped   = len([r for r in results if r["status"] == "skipped"])

    report = build_comment_report(results)
    logger.info("Post commenter done: %d commented | %d skipped.",
                commented, skipped)

    return {
        "commented": commented,
        "skipped":   skipped,
        "report":    report,
    }


def _get_contacts_from_history() -> list[str]:
    """Get contacts from agent history."""
    if not DB_FILE.exists():
        return []
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT DISTINCT contact FROM history
            WHERE date >= ? AND dry_run = 0
            LIMIT 50
        """, (cutoff,)).fetchall()
    return [row[0] for row in rows if row[0]]


# ------------------------------------------------------------
# AGENT INSTRUCTIONS
# ------------------------------------------------------------

def build_commenter_instructions(contact: str, post_text: str) -> str:
    """Build comment instructions for a specific post."""
    post_type = detect_post_type(post_text)
    comment   = get_comment(contact, post_type)

    return f"""
  POST AUTO-COMMENT:
  Contact   : {contact}
  Post type : {post_type}
  Comment   : "{comment}"

  Post the comment above on {contact}'s recent LinkedIn post.
  Report: COMMENTED: {contact} | {post_type} | {comment}
"""
