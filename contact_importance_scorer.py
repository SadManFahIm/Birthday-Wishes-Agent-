"""
contact_importance_scorer.py
-----------------------------
Contact Importance Scorer for Birthday Wishes Agent.

Ranks LinkedIn contacts by importance using multiple signals:
  - Interaction frequency and recency
  - Reply rate (do they respond to wishes?)
  - Job seniority (CEO, Director, Manager etc.)
  - Industry relevance
  - Connection strength score
  - Engagement on posts

Importance levels:
  - Tier 1 (VIP)     : Score 80-100 — top priority
  - Tier 2 (Key)     : Score 60-79  — high priority
  - Tier 3 (Regular) : Score 40-59  — normal priority
  - Tier 4 (Casual)  : Score 0-39   — low priority

Usage:
    from contact_importance_scorer import (
        init_importance_table,
        score_contact,
        score_all_contacts,
        get_top_contacts,
        build_importance_report,
    )

    score_all_contacts()
    top = get_top_contacts(10)
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Seniority keywords and their weights
SENIORITY_WEIGHTS = {
    "ceo":          10,
    "cto":          10,
    "coo":          10,
    "cfo":          10,
    "founder":      10,
    "co-founder":   10,
    "president":    9,
    "vp":           8,
    "vice president": 8,
    "director":     7,
    "head of":      7,
    "principal":    6,
    "senior":       5,
    "lead":         5,
    "manager":      4,
    "engineer":     3,
    "analyst":      3,
    "associate":    2,
    "intern":       1,
    "student":      1,
}

# Tier thresholds
TIER_1_THRESHOLD = 80
TIER_2_THRESHOLD = 60
TIER_3_THRESHOLD = 40


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_importance_table():
    """Create contact importance scoring table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_importance (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                contact           TEXT    NOT NULL UNIQUE,
                importance_score  REAL    DEFAULT 0,
                tier              TEXT    DEFAULT 'Casual',
                interaction_score REAL    DEFAULT 0,
                reply_score       REAL    DEFAULT 0,
                seniority_score   REAL    DEFAULT 0,
                strength_score    REAL    DEFAULT 0,
                job_title         TEXT,
                company           TEXT,
                last_scored       TEXT,
                created_at        TEXT    NOT NULL,
                updated_at        TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Contact importance table ready.")


# ------------------------------------------------------------
# SCORING COMPONENTS
# ------------------------------------------------------------

def _score_interactions(contact: str) -> float:
    """Score based on interaction frequency and recency (0-30)."""
    if not DB_FILE.exists():
        return 0.0

    cutoff_recent = (date.today() - timedelta(days=30)).isoformat()
    cutoff_all    = (date.today() - timedelta(days=365)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        # Recent interactions (last 30 days)
        recent = conn.execute("""
            SELECT COUNT(*) FROM history
            WHERE LOWER(contact) = LOWER(?) AND date >= ? AND dry_run = 0
        """, (contact, cutoff_recent)).fetchone()[0] or 0

        # Total interactions (last year)
        total = conn.execute("""
            SELECT COUNT(*) FROM history
            WHERE LOWER(contact) = LOWER(?) AND date >= ? AND dry_run = 0
        """, (contact, cutoff_all)).fetchone()[0] or 0

    recent_score = min(15, recent * 3)
    total_score  = min(15, total * 1.5)
    return recent_score + total_score


def _score_replies(contact: str) -> float:
    """Score based on reply rate from contact (0-30)."""
    if not DB_FILE.exists():
        return 0.0

    with sqlite3.connect(DB_FILE) as conn:
        # Wishes sent
        try:
            sent = conn.execute("""
                SELECT COUNT(*) FROM ab_tests
                WHERE LOWER(contact) = LOWER(?) AND dry_run = 0
            """, (contact,)).fetchone()[0] or 0

            replied = conn.execute("""
                SELECT COUNT(*) FROM ab_tests
                WHERE LOWER(contact) = LOWER(?) AND replied = 1 AND dry_run = 0
            """, (contact,)).fetchone()[0] or 0
        except sqlite3.OperationalError:
            sent    = 0
            replied = 0

    if sent == 0:
        return 10.0  # Unknown — give neutral score

    reply_rate = replied / sent
    return min(30, reply_rate * 30)


def _score_seniority(job_title: str) -> float:
    """Score based on job seniority (0-25)."""
    if not job_title:
        return 5.0  # Unknown — neutral

    title_lower = job_title.lower()
    max_weight  = 0

    for keyword, weight in SENIORITY_WEIGHTS.items():
        if keyword in title_lower:
            max_weight = max(max_weight, weight)

    # Scale to 0-25
    return min(25, max_weight * 2.5)


def _score_connection_strength(contact: str) -> float:
    """Score based on connection strength tracker (0-15)."""
    if not DB_FILE.exists():
        return 5.0

    with sqlite3.connect(DB_FILE) as conn:
        try:
            row = conn.execute("""
                SELECT strength_score FROM connection_strength
                WHERE LOWER(contact) = LOWER(?)
            """, (contact,)).fetchone()
            if row:
                return min(15, (row[0] or 0) / 100 * 15)
        except sqlite3.OperationalError:
            pass

        # Fallback: use tracker table
        try:
            row = conn.execute("""
                SELECT COUNT(*) FROM interaction_log
                WHERE LOWER(contact) = LOWER(?)
            """, (contact,)).fetchone()
            if row:
                return min(15, (row[0] or 0) * 1.5)
        except sqlite3.OperationalError:
            pass

    return 5.0


def _get_job_info(contact: str) -> dict:
    """Get stored job title and company for a contact."""
    if not DB_FILE.exists():
        return {}

    with sqlite3.connect(DB_FILE) as conn:
        # Try job_change_detector table
        try:
            row = conn.execute("""
                SELECT job_title, company FROM contact_jobs
                WHERE LOWER(contact) = LOWER(?)
            """, (contact,)).fetchone()
            if row:
                return {"job_title": row[0], "company": row[1]}
        except sqlite3.OperationalError:
            pass

        # Try contact_anniversaries
        try:
            row = conn.execute("""
                SELECT job_title, company FROM contact_anniversaries
                WHERE LOWER(contact) = LOWER(?)
            """, (contact,)).fetchone()
            if row:
                return {"job_title": row[0], "company": row[1]}
        except sqlite3.OperationalError:
            pass

    return {}


# ------------------------------------------------------------
# MAIN SCORING
# ------------------------------------------------------------

def score_contact(contact: str, job_title: str = "") -> dict:
    """
    Calculate importance score for a single contact.

    Args:
        contact   : Contact name
        job_title : Job title (optional, auto-reads from DB if not given)

    Returns:
        Dict with score, tier, and component scores.
    """
    if not job_title:
        job_info  = _get_job_info(contact)
        job_title = job_info.get("job_title", "")
        company   = job_info.get("company", "")
    else:
        company = ""

    interaction_score = _score_interactions(contact)
    reply_score       = _score_replies(contact)
    seniority_score   = _score_seniority(job_title)
    strength_score    = _score_connection_strength(contact)

    total = (interaction_score + reply_score +
             seniority_score + strength_score)
    total = round(min(100, total), 1)

    tier = (
        "VIP"     if total >= TIER_1_THRESHOLD else
        "Key"     if total >= TIER_2_THRESHOLD else
        "Regular" if total >= TIER_3_THRESHOLD else
        "Casual"
    )

    result = {
        "contact":           contact,
        "importance_score":  total,
        "tier":              tier,
        "interaction_score": round(interaction_score, 1),
        "reply_score":       round(reply_score, 1),
        "seniority_score":   round(seniority_score, 1),
        "strength_score":    round(strength_score, 1),
        "job_title":         job_title,
        "company":           company,
    }

    # Save to DB
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO contact_importance
                (contact, importance_score, tier, interaction_score,
                 reply_score, seniority_score, strength_score,
                 job_title, company, last_scored, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact) DO UPDATE SET
                importance_score  = excluded.importance_score,
                tier              = excluded.tier,
                interaction_score = excluded.interaction_score,
                reply_score       = excluded.reply_score,
                seniority_score   = excluded.seniority_score,
                strength_score    = excluded.strength_score,
                job_title         = excluded.job_title,
                company           = excluded.company,
                last_scored       = excluded.last_scored,
                updated_at        = excluded.updated_at
        """, (contact, total, tier,
              interaction_score, reply_score,
              seniority_score, strength_score,
              job_title, company,
              date.today().isoformat(), now, now))
        conn.commit()

    logger.info(
        "Scored %s: %.1f (%s) | interactions=%.1f reply=%.1f "
        "seniority=%.1f strength=%.1f",
        contact, total, tier,
        interaction_score, reply_score,
        seniority_score, strength_score,
    )
    return result


def score_all_contacts() -> list[dict]:
    """Score all contacts from history table."""
    if not DB_FILE.exists():
        return []

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT DISTINCT contact FROM history
            WHERE dry_run = 0 AND contact IS NOT NULL
        """).fetchall()

    contacts = [row[0] for row in rows if row[0]]
    results  = []

    for contact in contacts:
        result = score_contact(contact)
        results.append(result)

    results.sort(key=lambda x: x["importance_score"], reverse=True)
    logger.info("Scored %d contacts.", len(results))
    return results


# ------------------------------------------------------------
# RETRIEVAL
# ------------------------------------------------------------

def get_top_contacts(limit: int = 10, tier: str = "") -> list[dict]:
    """
    Get top contacts by importance score.

    Args:
        limit : Number of contacts to return
        tier  : Filter by tier (VIP/Key/Regular/Casual) or empty for all
    """
    if not DB_FILE.exists():
        return []

    query  = "SELECT contact, importance_score, tier, job_title, company FROM contact_importance"
    params = []

    if tier:
        query  += " WHERE tier = ?"
        params.append(tier)

    query += " ORDER BY importance_score DESC LIMIT ?"
    params.append(limit)

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        {
            "contact":          row[0],
            "importance_score": row[1],
            "tier":             row[2],
            "job_title":        row[3] or "",
            "company":          row[4] or "",
        }
        for row in rows
    ]


def get_tier_counts() -> dict:
    """Get count of contacts per tier."""
    if not DB_FILE.exists():
        return {"VIP": 0, "Key": 0, "Regular": 0, "Casual": 0}

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT tier, COUNT(*) FROM contact_importance GROUP BY tier
        """).fetchall()

    counts = {"VIP": 0, "Key": 0, "Regular": 0, "Casual": 0}
    for tier, count in rows:
        if tier in counts:
            counts[tier] = count
    return counts


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_importance_report(top_n: int = 20) -> str:
    """Build human-readable importance score report."""
    tier_counts = get_tier_counts()
    top         = get_top_contacts(top_n)
    total       = sum(tier_counts.values())

    lines = [
        "Contact Importance Scorer Report",
        "-" * 60,
        f"  Total scored : {total}",
        f"  VIP (80-100) : {tier_counts['VIP']}",
        f"  Key (60-79)  : {tier_counts['Key']}",
        f"  Regular      : {tier_counts['Regular']}",
        f"  Casual       : {tier_counts['Casual']}",
        "-" * 60,
        "",
        f"  {'Contact':<25} {'Score':>6} {'Tier':<10} {'Title'}",
        "  " + "-" * 56,
    ]

    tier_markers = {"VIP": "***", "Key": "** ", "Regular": "*  ", "Casual": "   "}

    for c in top:
        marker = tier_markers.get(c["tier"], "   ")
        title  = (c["job_title"] or "")[:20]
        lines.append(
            f"  {marker} {c['contact']:<22} {c['importance_score']:>6.1f} "
            f"{c['tier']:<10} {title}"
        )

    lines += [
        "",
        "  Score breakdown (max per component):",
        "    Interactions : 30 pts",
        "    Reply rate   : 30 pts",
        "    Seniority    : 25 pts",
        "    Strength     : 15 pts",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_contact_importance_scorer(
    dry_run: bool = True,
    send_report: bool = False,
) -> dict:
    """
    Main runner. Call from agent.py weekly.

    Returns:
        Dict with scoring summary.
    """
    logger.info("=== Contact Importance Scorer ===")

    results     = score_all_contacts()
    tier_counts = get_tier_counts()
    report      = build_importance_report()

    logger.info("\n%s", report)

    if send_report and not dry_run:
        try:
            from notifications import send_email
            send_email(
                subject="Contact Importance Score Report",
                body=report,
            )
        except Exception as e:
            logger.warning("Could not send importance report: %s", e)

    return {
        "total_scored": len(results),
        "tier_counts":  tier_counts,
        "top_contacts": get_top_contacts(5),
        "report":       report,
    }
