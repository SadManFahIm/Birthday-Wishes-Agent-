"""
network_growth_tracker.py
-------------------------
Network Growth Tracker for Birthday Wishes Agent.

Tracks LinkedIn network growth over time:
  - New connections added
  - Contacts who have faded (no interaction)
  - Weekly growth trend
  - Network health score
  - Top growing periods

How it works:
  1. Scans LinkedIn connection count periodically
  2. Tracks new connections from interaction history
  3. Identifies fading contacts (decreasing interaction)
  4. Generates weekly growth report
  5. Sends summary via email/Telegram

Usage:
    from network_growth_tracker import (
        init_network_table,
        run_network_growth_tracker,
        get_growth_summary,
        build_growth_report,
    )

    await run_network_growth_tracker(dry_run=True)
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_network_table():
    """Create network growth tracking tables."""
    with sqlite3.connect(DB_FILE) as conn:
        # Weekly snapshots of network size
        conn.execute("""
            CREATE TABLE IF NOT EXISTS network_snapshots (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date    TEXT    NOT NULL UNIQUE,
                total_connections INTEGER DEFAULT 0,
                new_this_week    INTEGER DEFAULT 0,
                faded_this_week  INTEGER DEFAULT 0,
                active_contacts  INTEGER DEFAULT 0,
                network_score    REAL    DEFAULT 0,
                created_at       TEXT    NOT NULL
            )
        """)
        # Individual contact tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS network_contacts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                contact         TEXT    NOT NULL UNIQUE,
                first_seen      TEXT    NOT NULL,
                last_interaction TEXT,
                interaction_count INTEGER DEFAULT 0,
                status          TEXT    DEFAULT 'active',
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Network growth tables ready.")


# ------------------------------------------------------------
# CONTACT TRACKING
# ------------------------------------------------------------

def sync_contacts_from_history():
    """
    Sync contact list from agent history table.
    Call this daily to keep network_contacts up to date.
    """
    if not DB_FILE.exists():
        return

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT LOWER(contact), MIN(date), MAX(date), COUNT(*)
            FROM   history
            WHERE  dry_run = 0
            GROUP  BY LOWER(contact)
        """).fetchall()

        now = datetime.now().isoformat()
        for contact, first_seen, last_seen, count in rows:
            if not contact:
                continue
            conn.execute("""
                INSERT INTO network_contacts
                    (contact, first_seen, last_interaction,
                     interaction_count, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(contact) DO UPDATE SET
                    last_interaction  = excluded.last_interaction,
                    interaction_count = excluded.interaction_count,
                    updated_at        = excluded.updated_at
            """, (contact, first_seen, last_seen, count, now, now))

        conn.commit()

    logger.info("Synced %d contacts from history.", len(rows))


def get_new_contacts(days: int = 7) -> list[dict]:
    """Get contacts first seen in the last N days."""
    if not DB_FILE.exists():
        return []

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT contact, first_seen, interaction_count
            FROM   network_contacts
            WHERE  first_seen >= ?
            ORDER  BY first_seen DESC
        """, (cutoff,)).fetchall()

    return [{"contact": r[0], "first_seen": r[1], "interactions": r[2]}
            for r in rows]


def get_fading_contacts(inactive_days: int = 60) -> list[dict]:
    """Get contacts with no interaction in the last N days."""
    if not DB_FILE.exists():
        return []

    cutoff = (date.today() - timedelta(days=inactive_days)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT contact, last_interaction, interaction_count
            FROM   network_contacts
            WHERE  last_interaction < ? OR last_interaction IS NULL
            ORDER  BY last_interaction ASC
            LIMIT  50
        """, (cutoff,)).fetchall()

    return [
        {
            "contact":      r[0],
            "last_seen":    r[1] or "never",
            "interactions": r[2],
            "days_silent":  (date.today() - date.fromisoformat(r[1])).days
                            if r[1] else 999,
        }
        for r in rows
    ]


def get_active_contacts(active_days: int = 30) -> list[dict]:
    """Get contacts with interaction in the last N days."""
    if not DB_FILE.exists():
        return []

    cutoff = (date.today() - timedelta(days=active_days)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT contact, last_interaction, interaction_count
            FROM   network_contacts
            WHERE  last_interaction >= ?
            ORDER  BY interaction_count DESC
            LIMIT  100
        """, (cutoff,)).fetchall()

    return [{"contact": r[0], "last_seen": r[1], "interactions": r[2]}
            for r in rows]


def get_total_contacts() -> int:
    """Get total number of tracked contacts."""
    if not DB_FILE.exists():
        return 0
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM network_contacts"
        ).fetchone()
    return row[0] or 0


# ------------------------------------------------------------
# GROWTH CALCULATION
# ------------------------------------------------------------

def calculate_network_score() -> float:
    """
    Calculate a network health score (0-100).

    Based on:
    - Active contact ratio (40%)
    - Recent growth (30%)
    - Interaction frequency (30%)
    """
    total  = get_total_contacts()
    if total == 0:
        return 0.0

    active  = len(get_active_contacts(30))
    new_7d  = len(get_new_contacts(7))
    fading  = len(get_fading_contacts(60))

    # Active ratio score (0-40)
    active_ratio  = active / total if total else 0
    active_score  = min(40, active_ratio * 40)

    # Growth score (0-30)
    growth_score  = min(30, new_7d * 3)

    # Retention score (0-30)
    fading_ratio  = fading / total if total else 0
    retention     = max(0, 1 - fading_ratio)
    retention_score = retention * 30

    score = active_score + growth_score + retention_score
    return round(score, 1)


def take_network_snapshot():
    """Take a weekly snapshot of network stats."""
    today = date.today().isoformat()

    sync_contacts_from_history()

    total   = get_total_contacts()
    new_7d  = len(get_new_contacts(7))
    fading  = len(get_fading_contacts(60))
    active  = len(get_active_contacts(30))
    score   = calculate_network_score()

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO network_snapshots
                (snapshot_date, total_connections, new_this_week,
                 faded_this_week, active_contacts, network_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                total_connections = excluded.total_connections,
                new_this_week     = excluded.new_this_week,
                faded_this_week   = excluded.faded_this_week,
                active_contacts   = excluded.active_contacts,
                network_score     = excluded.network_score
        """, (today, total, new_7d, fading, active, score,
              datetime.now().isoformat()))
        conn.commit()

    logger.info(
        "Network snapshot: total=%d | new=%d | fading=%d | active=%d | score=%.1f",
        total, new_7d, fading, active, score,
    )
    return {
        "total":   total,
        "new":     new_7d,
        "fading":  fading,
        "active":  active,
        "score":   score,
    }


def get_weekly_trend(weeks: int = 4) -> list[dict]:
    """Get weekly network growth trend for last N weeks."""
    if not DB_FILE.exists():
        return []

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT snapshot_date, total_connections, new_this_week,
                   faded_this_week, active_contacts, network_score
            FROM   network_snapshots
            ORDER  BY snapshot_date DESC
            LIMIT  ?
        """, (weeks,)).fetchall()

    return [
        {
            "date":    r[0],
            "total":   r[1],
            "new":     r[2],
            "fading":  r[3],
            "active":  r[4],
            "score":   r[5],
        }
        for r in rows
    ]


# ------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------

def get_growth_summary() -> dict:
    """Get current network growth summary."""
    sync_contacts_from_history()

    total   = get_total_contacts()
    new_7d  = get_new_contacts(7)
    new_30d = get_new_contacts(30)
    fading  = get_fading_contacts(60)
    active  = get_active_contacts(30)
    score   = calculate_network_score()
    trend   = get_weekly_trend(4)

    # Calculate week-over-week growth
    wow_growth = 0
    if len(trend) >= 2:
        wow_growth = trend[0]["new"] - trend[1]["new"]

    return {
        "total_contacts":    total,
        "new_this_week":     len(new_7d),
        "new_this_month":    len(new_30d),
        "fading_contacts":   len(fading),
        "active_contacts":   len(active),
        "network_score":     score,
        "wow_growth":        wow_growth,
        "weekly_trend":      trend,
        "top_new":           new_7d[:5],
        "most_fading":       fading[:5],
    }


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_growth_report(summary: dict | None = None) -> str:
    """Build human-readable network growth report."""
    if summary is None:
        summary = get_growth_summary()

    score       = summary["network_score"]
    score_label = (
        "Excellent" if score >= 80
        else "Good" if score >= 60
        else "Fair" if score >= 40
        else "Needs attention"
    )

    wow = summary["wow_growth"]
    wow_str = f"+{wow}" if wow >= 0 else str(wow)

    lines = [
        "Network Growth Tracker Report",
        "-" * 55,
        f"  Network Score  : {score:.1f}/100 ({score_label})",
        f"  Total contacts : {summary['total_contacts']}",
        f"  Active (30d)   : {summary['active_contacts']}",
        f"  New this week  : {summary['new_this_week']} ({wow_str} vs last week)",
        f"  New this month : {summary['new_this_month']}",
        f"  Fading (60d+)  : {summary['fading_contacts']}",
        "-" * 55,
        "",
    ]

    if summary["top_new"]:
        lines.append("New contacts this week:")
        for c in summary["top_new"]:
            lines.append(f"  + {c['contact']}")
        lines.append("")

    if summary["most_fading"]:
        lines.append("Most fading contacts:")
        for c in summary["most_fading"]:
            months = round(c["days_silent"] / 30)
            lines.append(f"  - {c['contact']} ({months}m silent)")
        lines.append("")

    if summary["weekly_trend"]:
        lines.append("Weekly trend (last 4 weeks):")
        for t in summary["weekly_trend"]:
            lines.append(
                f"  {t['date']} | total={t['total']} "
                f"new={t['new']} score={t['score']:.0f}"
            )
        lines.append("")

    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# NOTIFICATION
# ------------------------------------------------------------

def send_growth_notification(report: str, dry_run: bool = True):
    """Send growth report via email/Telegram."""
    if dry_run:
        logger.info("[DRY RUN] Would send growth report:\n%s", report[:300])
        return

    try:
        from notifications import send_email, send_telegram
        try:
            send_email(subject="Weekly Network Growth Report", body=report)
            logger.info("Growth report sent via email.")
        except Exception as e:
            logger.warning("Email failed: %s", e)

        try:
            send_telegram(f"*Weekly Network Growth*\n\n```\n{report[:3000]}\n```")
            logger.info("Growth report sent via Telegram.")
        except Exception as e:
            logger.warning("Telegram failed: %s", e)

    except ImportError:
        logger.warning("notifications.py not available.")


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_network_growth_tracker(
    dry_run: bool = True,
    send_report: bool = True,
) -> dict:
    """
    Main runner. Call from agent.py weekly (Mondays recommended).

    Args:
        dry_run     : If True, log only - do not send notifications
        send_report : If True, send report via email/Telegram

    Returns:
        Dict with growth summary stats.
    """
    logger.info("=== Network Growth Tracker === [DRY RUN: %s]", dry_run)

    # Take snapshot
    snapshot = take_network_snapshot()

    # Get full summary
    summary = get_growth_summary()

    # Build report
    report = build_growth_report(summary)
    logger.info("\n%s", report)

    # Send notification
    if send_report:
        send_growth_notification(report, dry_run=dry_run)

    logger.info(
        "Network growth done: total=%d | new=%d | fading=%d | score=%.1f",
        summary["total_contacts"], summary["new_this_week"],
        summary["fading_contacts"], summary["network_score"],
    )

    return summary
