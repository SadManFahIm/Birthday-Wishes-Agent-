"""
contact_importance_scorer.py  (v2)
-----------------------------------
Contact Importance Scorer for Birthday Wishes Agent.

Ranks LinkedIn contacts by importance using multiple signals:
  - Interaction frequency and recency
  - Reply rate (do they respond to wishes?)
  - Job seniority (CEO, Director, Manager etc.)
  - Connection strength score
  - LinkedIn follower count                    🆕 v2
  - Company size (employee count)               🆕 v2
  - Mutual connections                          🆕 v2

Importance levels:
  - Tier 1 (VIP)     : Score 80-100 — top priority
  - Tier 2 (Key)     : Score 60-79  — high priority
  - Tier 3 (Regular) : Score 40-59  — normal priority
  - Tier 4 (Casual)  : Score 0-39   — low priority

v2 score breakdown (max 100 total):
  - Interactions        : 20 pts
  - Reply rate           : 20 pts
  - Job seniority         : 15 pts
  - Connection strength    : 10 pts
  - LinkedIn followers      : 15 pts   🆕
  - Company size             : 10 pts   🆕
  - Mutual connections        : 10 pts   🆕

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

    # v2: pass live LinkedIn signals directly when available
    score_contact(
        "Jane Doe",
        job_title="VP of Engineering",
        linkedin_followers=8200,
        company_size=1500,
        mutual_connections=34,
    )
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
# v2: LinkedIn follower count bands -> points out of 15
# ------------------------------------------------------------
FOLLOWER_BANDS = [
    (100_000, 15),
    (50_000,  13),
    (10_000,  11),
    (5_000,    9),
    (1_000,    6),
    (500,      4),
    (100,      2),
    (0,        0),
]

# v2: Company size (employee count) bands -> points out of 10
# Both very large (enterprise) and mid-size scale companies score well;
# unknown/solo is treated as neutral-low rather than zero.
COMPANY_SIZE_BANDS = [
    (10_000, 10),   # Enterprise
    (1_000,   9),   # Large
    (200,     8),   # Mid-market
    (50,      6),   # Small business
    (10,      4),   # Startup
    (1,       2),   # Micro / solo founder
    (0,       1),   # Unknown
]

# v2: Mutual connections -> points out of 10
MUTUAL_CONNECTIONS_BANDS = [
    (100, 10),
    (50,   8),
    (25,   6),
    (10,   4),
    (5,    2),
    (1,    1),
    (0,    0),
]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_importance_table():
    """Create contact importance scoring table (v2 schema)."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_importance (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                contact              TEXT    NOT NULL UNIQUE,
                importance_score     REAL    DEFAULT 0,
                tier                 TEXT    DEFAULT 'Casual',
                interaction_score    REAL    DEFAULT 0,
                reply_score          REAL    DEFAULT 0,
                seniority_score      REAL    DEFAULT 0,
                strength_score       REAL    DEFAULT 0,
                follower_score       REAL    DEFAULT 0,
                company_size_score   REAL    DEFAULT 0,
                mutual_score         REAL    DEFAULT 0,
                linkedin_followers   INTEGER DEFAULT 0,
                company_size         INTEGER DEFAULT 0,
                mutual_connections   INTEGER DEFAULT 0,
                job_title            TEXT,
                company              TEXT,
                last_scored          TEXT,
                created_at           TEXT    NOT NULL,
                updated_at           TEXT    NOT NULL
            )
        """)
        conn.commit()
        _migrate_v1_to_v2(conn)
    logger.info("Contact importance table ready (v2).")


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add v2 columns to a table created by the v1 scorer, if missing."""
    existing = {row[1] for row in conn.execute(
        "PRAGMA table_info(contact_importance)"
    ).fetchall()}

    new_columns = {
        "follower_score":     "REAL DEFAULT 0",
        "company_size_score": "REAL DEFAULT 0",
        "mutual_score":       "REAL DEFAULT 0",
        "linkedin_followers": "INTEGER DEFAULT 0",
        "company_size":       "INTEGER DEFAULT 0",
        "mutual_connections": "INTEGER DEFAULT 0",
    }

    for column, ddl in new_columns.items():
        if column not in existing:
            conn.execute(
                f"ALTER TABLE contact_importance ADD COLUMN {column} {ddl}"
            )
            logger.info("Migrated contact_importance: added column '%s'.", column)

    conn.commit()


# ------------------------------------------------------------
# SCORING COMPONENTS
# ------------------------------------------------------------

def _score_interactions(contact: str) -> float:
    """Score based on interaction frequency and recency (0-20). [v2: rebalanced from 0-30]"""
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

    recent_score = min(10, recent * 2)
    total_score  = min(10, total * 1.0)
    return recent_score + total_score


def _score_replies(contact: str) -> float:
    """Score based on reply rate from contact (0-20). [v2: rebalanced from 0-30]"""
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
        return 7.0  # Unknown — give neutral score

    reply_rate = replied / sent
    return min(20, reply_rate * 20)


def _score_seniority(job_title: str) -> float:
    """Score based on job seniority (0-15). [v2: rebalanced from 0-25]"""
    if not job_title:
        return 3.0  # Unknown — neutral

    title_lower = job_title.lower()
    max_weight  = 0

    for keyword, weight in SENIORITY_WEIGHTS.items():
        if keyword in title_lower:
            max_weight = max(max_weight, weight)

    # Scale to 0-15
    return min(15, max_weight * 1.5)


def _score_connection_strength(contact: str) -> float:
    """Score based on connection strength tracker (0-10). [v2: rebalanced from 0-15]"""
    if not DB_FILE.exists():
        return 3.0

    with sqlite3.connect(DB_FILE) as conn:
        try:
            row = conn.execute("""
                SELECT strength_score FROM connection_strength
                WHERE LOWER(contact) = LOWER(?)
            """, (contact,)).fetchone()
            if row:
                return min(10, (row[0] or 0) / 100 * 10)
        except sqlite3.OperationalError:
            pass

        # Fallback: use tracker table
        try:
            row = conn.execute("""
                SELECT COUNT(*) FROM interaction_log
                WHERE LOWER(contact) = LOWER(?)
            """, (contact,)).fetchone()
            if row:
                return min(10, (row[0] or 0) * 1.0)
        except sqlite3.OperationalError:
            pass

    return 3.0


def _score_from_bands(value: int, bands: list) -> float:
    """Shared helper: score a raw count against a descending list of (threshold, points)."""
    if value is None:
        value = 0
    for threshold, points in bands:
        if value >= threshold:
            return float(points)
    return 0.0


def _score_followers(linkedin_followers: int) -> float:
    """Score based on LinkedIn follower count (0-15). 🆕 v2"""
    return _score_from_bands(linkedin_followers, FOLLOWER_BANDS)


def _score_company_size(company_size: int) -> float:
    """Score based on employer's employee count (0-10). 🆕 v2"""
    return _score_from_bands(company_size, COMPANY_SIZE_BANDS)


def _score_mutual_connections(mutual_connections: int) -> float:
    """Score based on number of mutual connections (0-10). 🆕 v2"""
    return _score_from_bands(mutual_connections, MUTUAL_CONNECTIONS_BANDS)


def _get_linkedin_stats(contact: str) -> dict:
    """
    Look up cached LinkedIn stats (followers, company size, mutual
    connections) for a contact. 🆕 v2

    Reads from a `contact_linkedin_stats` table if present (populated by
    the LinkedIn scraping/platform layer). Falls back to zeros — which
    score as neutral-low, not a penalty — if the table or contact isn't
    found, so v1 databases keep working without a migration step.
    """
    defaults = {"linkedin_followers": 0, "company_size": 0, "mutual_connections": 0}

    if not DB_FILE.exists():
        return defaults

    with sqlite3.connect(DB_FILE) as conn:
        try:
            row = conn.execute("""
                SELECT followers, company_size, mutual_connections
                FROM contact_linkedin_stats
                WHERE LOWER(contact) = LOWER(?)
            """, (contact,)).fetchone()
            if row:
                return {
                    "linkedin_followers": row[0] or 0,
                    "company_size":       row[1] or 0,
                    "mutual_connections": row[2] or 0,
                }
        except sqlite3.OperationalError:
            pass

    return defaults


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

def score_contact(
    contact: str,
    job_title: str = "",
    linkedin_followers: int = None,
    company_size: int = None,
    mutual_connections: int = None,
) -> dict:
    """
    Calculate importance score for a single contact.

    Args:
        contact             : Contact name
        job_title           : Job title (optional, auto-reads from DB if not given)
        linkedin_followers  : LinkedIn follower count (optional, auto-reads from
                               DB if not given) 🆕 v2
        company_size        : Current employer's employee count (optional,
                               auto-reads from DB if not given) 🆕 v2
        mutual_connections  : Number of mutual connections (optional,
                               auto-reads from DB if not given) 🆕 v2

    Returns:
        Dict with score, tier, and component scores.
    """
    if not job_title:
        job_info  = _get_job_info(contact)
        job_title = job_info.get("job_title", "")
        company   = job_info.get("company", "")
    else:
        company = ""

    # v2: fall back to cached LinkedIn stats for any signal not passed in directly
    if linkedin_followers is None or company_size is None or mutual_connections is None:
        cached = _get_linkedin_stats(contact)
        if linkedin_followers is None:
            linkedin_followers = cached["linkedin_followers"]
        if company_size is None:
            company_size = cached["company_size"]
        if mutual_connections is None:
            mutual_connections = cached["mutual_connections"]

    interaction_score  = _score_interactions(contact)
    reply_score        = _score_replies(contact)
    seniority_score    = _score_seniority(job_title)
    strength_score     = _score_connection_strength(contact)
    follower_score      = _score_followers(linkedin_followers)             # 🆕 v2
    company_size_score  = _score_company_size(company_size)                # 🆕 v2
    mutual_score        = _score_mutual_connections(mutual_connections)    # 🆕 v2

    total = (interaction_score + reply_score +
             seniority_score + strength_score +
             follower_score + company_size_score + mutual_score)
    total = round(min(100, total), 1)

    tier = (
        "VIP"     if total >= TIER_1_THRESHOLD else
        "Key"     if total >= TIER_2_THRESHOLD else
        "Regular" if total >= TIER_3_THRESHOLD else
        "Casual"
    )

    result = {
        "contact":             contact,
        "importance_score":    total,
        "tier":                tier,
        "interaction_score":   round(interaction_score, 1),
        "reply_score":         round(reply_score, 1),
        "seniority_score":     round(seniority_score, 1),
        "strength_score":      round(strength_score, 1),
        "follower_score":      round(follower_score, 1),        # 🆕 v2
        "company_size_score":  round(company_size_score, 1),    # 🆕 v2
        "mutual_score":        round(mutual_score, 1),          # 🆕 v2
        "linkedin_followers":  linkedin_followers,               # 🆕 v2
        "company_size":        company_size,                     # 🆕 v2
        "mutual_connections":  mutual_connections,                # 🆕 v2
        "job_title":           job_title,
        "company":             company,
    }

    # Save to DB
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO contact_importance
                (contact, importance_score, tier, interaction_score,
                 reply_score, seniority_score, strength_score,
                 follower_score, company_size_score, mutual_score,
                 linkedin_followers, company_size, mutual_connections,
                 job_title, company, last_scored, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact) DO UPDATE SET
                importance_score    = excluded.importance_score,
                tier                = excluded.tier,
                interaction_score   = excluded.interaction_score,
                reply_score         = excluded.reply_score,
                seniority_score     = excluded.seniority_score,
                strength_score      = excluded.strength_score,
                follower_score      = excluded.follower_score,
                company_size_score  = excluded.company_size_score,
                mutual_score        = excluded.mutual_score,
                linkedin_followers  = excluded.linkedin_followers,
                company_size        = excluded.company_size,
                mutual_connections  = excluded.mutual_connections,
                job_title           = excluded.job_title,
                company             = excluded.company,
                last_scored         = excluded.last_scored,
                updated_at          = excluded.updated_at
        """, (contact, total, tier,
              interaction_score, reply_score,
              seniority_score, strength_score,
              follower_score, company_size_score, mutual_score,
              linkedin_followers, company_size, mutual_connections,
              job_title, company,
              date.today().isoformat(), now, now))
        conn.commit()

    logger.info(
        "Scored %s: %.1f (%s) | interactions=%.1f reply=%.1f "
        "seniority=%.1f strength=%.1f followers=%.1f company_size=%.1f mutual=%.1f",
        contact, total, tier,
        interaction_score, reply_score,
        seniority_score, strength_score,
        follower_score, company_size_score, mutual_score,
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
        "  Score breakdown (max per component) — v2:",
        "    Interactions        : 20 pts",
        "    Reply rate          : 20 pts",
        "    Seniority           : 15 pts",
        "    Connection strength : 10 pts",
        "    LinkedIn followers  : 15 pts  🆕",
        "    Company size        : 10 pts  🆕",
        "    Mutual connections  : 10 pts  🆕",
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
