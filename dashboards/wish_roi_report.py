"""
wish_roi_report.py
------------------
Wish ROI Report for Birthday Wishes Agent.

Calculates the return on investment of birthday wishes:
  - How many wishes sent
  - How many got replies
  - How many led to new connections
  - Reply rate per platform
  - Best performing wish styles

Usage:
    from wish_roi_report import (
        init_roi_table,
        run_roi_report,
        get_roi_summary,
        build_roi_report,
    )

    await run_roi_report(dry_run=True)
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


def init_roi_table():
    """Create ROI tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wish_roi (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                period_start   TEXT NOT NULL,
                period_end     TEXT NOT NULL,
                wishes_sent    INTEGER DEFAULT 0,
                replies_received INTEGER DEFAULT 0,
                connections_made INTEGER DEFAULT 0,
                reply_rate     REAL DEFAULT 0,
                connection_rate REAL DEFAULT 0,
                best_platform  TEXT,
                best_style     TEXT,
                created_at     TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("ROI table ready.")


def get_roi_summary(days: int = 30) -> dict:
    """Calculate ROI metrics for the last N days."""
    if not DB_FILE.exists():
        return {}

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        # Total wishes sent
        wishes = conn.execute("""
            SELECT COUNT(*) FROM history
            WHERE task LIKE '%Wish%' AND date >= ? AND dry_run = 0
        """, (cutoff,)).fetchone()[0] or 0

        # Replies received
        try:
            replies = conn.execute("""
                SELECT COUNT(*) FROM ab_tests
                WHERE replied = 1 AND date >= ? AND dry_run = 0
            """, (cutoff,)).fetchone()[0] or 0
        except sqlite3.OperationalError:
            replies = 0

        # New connections made
        try:
            connections = conn.execute("""
                SELECT COUNT(*) FROM personalized_connect_requests
                WHERE wish_date >= ? AND dry_run = 0
            """, (cutoff,)).fetchone()[0] or 0
        except sqlite3.OperationalError:
            connections = 0

        # Per platform breakdown
        platform_rows = conn.execute("""
            SELECT task, COUNT(*) FROM history
            WHERE task LIKE '%Wish%' AND date >= ? AND dry_run = 0
            GROUP BY task
        """, (cutoff,)).fetchall()

        # Best wish style from A/B testing
        try:
            style_rows = conn.execute("""
                SELECT variant, COUNT(*) as cnt, SUM(replied) as rep
                FROM ab_tests
                WHERE date >= ? AND dry_run = 0
                GROUP BY variant
                ORDER BY CAST(rep AS REAL)/cnt DESC
                LIMIT 1
            """, (cutoff,)).fetchone()
            best_style = style_rows[0] if style_rows else "N/A"
        except sqlite3.OperationalError:
            best_style = "N/A"

    reply_rate      = round(replies / wishes * 100, 1) if wishes else 0
    connection_rate = round(connections / wishes * 100, 1) if wishes else 0

    platforms = {}
    for task, count in platform_rows:
        platform = "LinkedIn"
        if "whatsapp" in task.lower():
            platform = "WhatsApp"
        elif "facebook" in task.lower():
            platform = "Facebook"
        elif "instagram" in task.lower():
            platform = "Instagram"
        platforms[platform] = platforms.get(platform, 0) + count

    best_platform = max(platforms, key=platforms.get) if platforms else "N/A"

    return {
        "period_days":      days,
        "wishes_sent":      wishes,
        "replies_received": replies,
        "connections_made": connections,
        "reply_rate":       reply_rate,
        "connection_rate":  connection_rate,
        "best_platform":    best_platform,
        "best_style":       best_style,
        "platforms":        platforms,
    }


def build_roi_report(days: int = 30) -> str:
    """Build human-readable ROI report."""
    s = get_roi_summary(days)

    if not s:
        return "No wish data found. Send some wishes first!"

    # Simple bar chart for reply rate
    bar_len  = min(int(s["reply_rate"] / 2), 40)
    rate_bar = "#" * bar_len + " " * (40 - bar_len)

    lines = [
        "Wish ROI Report",
        "-" * 55,
        f"  Period        : Last {s['period_days']} days",
        f"  Wishes sent   : {s['wishes_sent']}",
        f"  Replies       : {s['replies_received']}",
        f"  Connections   : {s['connections_made']}",
        "-" * 55,
        f"  Reply rate    : {s['reply_rate']:.1f}%  [{rate_bar}]",
        f"  Connect rate  : {s['connection_rate']:.1f}%",
        f"  Best platform : {s['best_platform']}",
        f"  Best style    : {s['best_style']}",
        "-" * 55,
        "",
    ]

    if s["platforms"]:
        lines.append("Platform breakdown:")
        for platform, count in sorted(s["platforms"].items(),
                                      key=lambda x: x[1], reverse=True):
            pct = round(count / s["wishes_sent"] * 100, 1) if s["wishes_sent"] else 0
            lines.append(f"  {platform:<12} {count:>5} wishes ({pct:.0f}%)")
        lines.append("")

    # ROI grade
    if s["reply_rate"] >= 50:
        grade = "A+ Excellent"
    elif s["reply_rate"] >= 30:
        grade = "A  Great"
    elif s["reply_rate"] >= 15:
        grade = "B  Good"
    elif s["reply_rate"] >= 5:
        grade = "C  Average"
    else:
        grade = "D  Needs improvement"

    lines += [
        f"  ROI Grade : {grade}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    return "\n".join(lines)


def save_roi_snapshot(days: int = 30):
    """Save ROI snapshot to DB."""
    s   = get_roi_summary(days)
    now = datetime.now().isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO wish_roi
            (period_start, period_end, wishes_sent, replies_received,
             connections_made, reply_rate, connection_rate,
             best_platform, best_style, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            (date.today() - timedelta(days=days)).isoformat(),
            date.today().isoformat(),
            s.get("wishes_sent", 0),
            s.get("replies_received", 0),
            s.get("connections_made", 0),
            s.get("reply_rate", 0),
            s.get("connection_rate", 0),
            s.get("best_platform", ""),
            s.get("best_style", ""),
            now,
        ))
        conn.commit()
    logger.info("ROI snapshot saved.")


async def run_roi_report(
    dry_run: bool = True,
    days: int = 30,
    send_report: bool = False,
) -> dict:
    """Main runner. Call from agent.py weekly."""
    logger.info("=== Wish ROI Report === [DRY RUN: %s]", dry_run)

    summary = get_roi_summary(days)
    report  = build_roi_report(days)

    logger.info("\n%s", report)

    if not dry_run:
        save_roi_snapshot(days)

    if send_report and not dry_run:
        try:
            from notifications import send_email
            send_email(subject=f"Wish ROI Report — Last {days} Days", body=report)
        except Exception as e:
            logger.warning("Could not send ROI report: %s", e)

    return {**summary, "report": report}
