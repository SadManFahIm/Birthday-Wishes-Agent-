"""
engagement_heatmap.py
---------------------
Engagement Heatmap for Birthday Wishes Agent.

Tracks when contacts reply to wishes and builds a heatmap
showing which days and hours get the most engagement.

How it works:
  1. Logs every reply received with timestamp
  2. Aggregates by day of week and hour of day
  3. Generates ASCII heatmap for terminal/logs
  4. Generates Streamlit heatmap for dashboard
  5. Recommends best send times based on data

Usage:
    from engagement_heatmap import (
        init_heatmap_table,
        log_reply_engagement,
        get_best_send_times,
        build_heatmap_report,
        run_heatmap_analysis,
    )

    log_reply_engagement("John Smith", replied_at=datetime.now())
    best_times = get_best_send_times()
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

DAYS   = ["Monday", "Tuesday", "Wednesday", "Thursday",
          "Friday", "Saturday", "Sunday"]
HOURS  = list(range(24))


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_heatmap_table():
    """Create engagement heatmap tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS engagement_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                event_type   TEXT    NOT NULL DEFAULT 'reply',
                day_of_week  INTEGER NOT NULL,
                hour_of_day  INTEGER NOT NULL,
                platform     TEXT    DEFAULT 'linkedin',
                event_date   TEXT    NOT NULL,
                event_time   TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Engagement heatmap table ready.")


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def log_reply_engagement(
    contact: str,
    replied_at: datetime | None = None,
    platform: str = "linkedin",
    event_type: str = "reply",
):
    """
    Log an engagement event (reply, like, comment).

    Args:
        contact    : Contact name
        replied_at : When the reply came in (default: now)
        platform   : Platform (linkedin/whatsapp/slack)
        event_type : Type of engagement (reply/like/comment)
    """
    if not replied_at:
        replied_at = datetime.now()

    day_of_week = replied_at.weekday()  # 0=Monday, 6=Sunday
    hour_of_day = replied_at.hour

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO engagement_events
            (contact, event_type, day_of_week, hour_of_day,
             platform, event_date, event_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (contact, event_type, day_of_week, hour_of_day,
              platform, replied_at.date().isoformat(),
              replied_at.strftime("%H:%M"), datetime.now().isoformat()))
        conn.commit()

    logger.info("Engagement logged: %s | %s %02d:00 | %s",
                contact, DAYS[day_of_week], hour_of_day, platform)


def sync_replies_from_history():
    """
    Sync existing reply data from ab_tests and history tables.
    Call this once to populate heatmap from existing data.
    """
    if not DB_FILE.exists():
        return

    synced = 0
    with sqlite3.connect(DB_FILE) as conn:
        # From ab_tests (has reply tracking)
        try:
            rows = conn.execute("""
                SELECT contact, replied_date
                FROM   ab_tests
                WHERE  replied = 1 AND replied_date IS NOT NULL
            """).fetchall()

            for contact, replied_date in rows:
                try:
                    dt = datetime.fromisoformat(replied_date)
                    log_reply_engagement(contact, dt)
                    synced += 1
                except Exception:
                    continue
        except sqlite3.OperationalError:
            pass

    logger.info("Synced %d engagement events from history.", synced)


# ------------------------------------------------------------
# HEATMAP DATA
# ------------------------------------------------------------

def get_heatmap_data(days_back: int = 90) -> dict:
    """
    Get engagement counts by day and hour.

    Returns:
        Dict[day_of_week][hour_of_day] = count
    """
    if not DB_FILE.exists():
        return {}

    cutoff = (date.today() - timedelta(days=days_back)).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT day_of_week, hour_of_day, COUNT(*) as cnt
            FROM   engagement_events
            WHERE  event_date >= ?
            GROUP  BY day_of_week, hour_of_day
        """, (cutoff,)).fetchall()

    heatmap = defaultdict(lambda: defaultdict(int))
    for day, hour, count in rows:
        heatmap[day][hour] = count

    return dict(heatmap)


def get_hourly_totals(days_back: int = 90) -> dict:
    """Get total engagements per hour (0-23)."""
    if not DB_FILE.exists():
        return {h: 0 for h in HOURS}

    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT hour_of_day, COUNT(*) as cnt
            FROM   engagement_events
            WHERE  event_date >= ?
            GROUP  BY hour_of_day
        """, (cutoff,)).fetchall()

    totals = {h: 0 for h in HOURS}
    for hour, count in rows:
        totals[hour] = count
    return totals


def get_daily_totals(days_back: int = 90) -> dict:
    """Get total engagements per day of week (0=Mon, 6=Sun)."""
    if not DB_FILE.exists():
        return {d: 0 for d in range(7)}

    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT day_of_week, COUNT(*) as cnt
            FROM   engagement_events
            WHERE  event_date >= ?
            GROUP  BY day_of_week
        """, (cutoff,)).fetchall()

    totals = {d: 0 for d in range(7)}
    for day, count in rows:
        totals[day] = count
    return totals


# ------------------------------------------------------------
# BEST SEND TIMES
# ------------------------------------------------------------

def get_best_send_times(top_n: int = 3) -> list[dict]:
    """
    Get the best times to send wishes based on engagement data.

    Returns:
        List of top N day+hour combinations by engagement count.
    """
    heatmap = get_heatmap_data()
    if not heatmap:
        # No data yet — return sensible defaults
        return [
            {"day": "Tuesday",   "hour": 9,  "count": 0, "note": "default"},
            {"day": "Thursday",  "hour": 10, "count": 0, "note": "default"},
            {"day": "Wednesday", "hour": 11, "count": 0, "note": "default"},
        ]

    scored = []
    for day_idx, hours in heatmap.items():
        for hour, count in hours.items():
            if count > 0:
                scored.append({
                    "day":   DAYS[day_idx],
                    "hour":  hour,
                    "count": count,
                    "note":  "data-driven",
                })

    scored.sort(key=lambda x: x["count"], reverse=True)
    return scored[:top_n]


def get_best_hour() -> int:
    """Get single best hour to send wishes."""
    hourly = get_hourly_totals()
    if not any(hourly.values()):
        return 9  # Default 9 AM
    return max(hourly, key=hourly.get)


def get_best_day() -> str:
    """Get single best day of week to send wishes."""
    daily = get_daily_totals()
    if not any(daily.values()):
        return "Tuesday"  # Default
    best_idx = max(daily, key=daily.get)
    return DAYS[best_idx]


# ------------------------------------------------------------
# ASCII HEATMAP
# ------------------------------------------------------------

def build_ascii_heatmap(days_back: int = 90) -> str:
    """
    Build an ASCII heatmap showing engagement by day/hour.

    Example output:
          00 01 02 ... 09 10 11 ... 22 23
    Mon    .  .  .  ...  #  ##  .  ...  .  .
    Tue    .  .  .  ...  .  #  ##  ...  .  .
    ...
    """
    heatmap = get_heatmap_data(days_back)

    if not heatmap:
        return "No engagement data yet. Send some wishes first!"

    # Find max value for scaling
    all_values = [
        heatmap[d][h]
        for d in heatmap
        for h in heatmap[d]
    ]
    max_val = max(all_values) if all_values else 1

    def scale(count: int) -> str:
        if count == 0:
            return " ."
        ratio = count / max_val
        if ratio < 0.25:
            return " o"
        if ratio < 0.5:
            return " O"
        if ratio < 0.75:
            return " #"
        return "##"

    # Show hours 6-22 (common active hours)
    show_hours = list(range(6, 23))

    header = "       " + "".join(f"{h:2d}" for h in show_hours)
    lines  = [
        f"Engagement Heatmap (last {days_back} days)",
        "-" * (7 + len(show_hours) * 2),
        header,
    ]

    for day_idx, day_name in enumerate(DAYS):
        row = f"{day_name[:3]:<7}"
        for h in show_hours:
            count = heatmap.get(day_idx, {}).get(h, 0)
            row  += scale(count)
        lines.append(row)

    lines += [
        "-" * (7 + len(show_hours) * 2),
        "  Legend: .=none  o=low  O=medium  #=high  ##=peak",
    ]

    # Best times
    best = get_best_send_times(3)
    if best and best[0]["count"] > 0:
        lines.append("")
        lines.append("Best send times:")
        for b in best:
            lines.append(
                f"  {b['day']:<12} {b['hour']:02d}:00 "
                f"({b['count']} replies)"
            )

    return "\n".join(lines)


# ------------------------------------------------------------
# STREAMLIT CHART DATA
# ------------------------------------------------------------

def get_heatmap_chart_data() -> dict:
    """
    Get heatmap data formatted for Streamlit/plotly visualization.

    Returns:
        Dict with days, hours, values (2D matrix).
    """
    heatmap = get_heatmap_data()
    show_hours = list(range(6, 23))

    matrix = []
    for day_idx in range(7):
        row = []
        for h in show_hours:
            count = heatmap.get(day_idx, {}).get(h, 0)
            row.append(count)
        matrix.append(row)

    return {
        "days":   DAYS,
        "hours":  [f"{h:02d}:00" for h in show_hours],
        "values": matrix,
    }


# ------------------------------------------------------------
# FULL REPORT
# ------------------------------------------------------------

def build_heatmap_report() -> str:
    """Build full engagement heatmap report."""
    hourly = get_hourly_totals()
    daily  = get_daily_totals()
    best   = get_best_send_times(5)

    total_engagements = sum(hourly.values())

    lines = [
        "Engagement Heatmap Report",
        "-" * 55,
        f"  Total engagements : {total_engagements}",
        f"  Best day          : {get_best_day()}",
        f"  Best hour         : {get_best_hour():02d}:00",
        "-" * 55,
        "",
        build_ascii_heatmap(),
        "",
        "Hourly breakdown (top 5 hours):",
    ]

    top_hours = sorted(hourly.items(), key=lambda x: x[1], reverse=True)[:5]
    for hour, count in top_hours:
        bar = "#" * min(count, 20)
        lines.append(f"  {hour:02d}:00  {bar} ({count})")

    lines.append("")
    lines.append("Daily breakdown:")
    for day_idx in range(7):
        count = daily[day_idx]
        bar   = "#" * min(count, 20)
        lines.append(f"  {DAYS[day_idx]:<12} {bar} ({count})")

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# MAIN RUNNER
# ------------------------------------------------------------

async def run_heatmap_analysis(
    dry_run: bool = True,
    send_report: bool = False,
) -> dict:
    """
    Main runner. Call from agent.py weekly.

    Returns:
        Dict with engagement summary.
    """
    logger.info("=== Engagement Heatmap Analysis ===")

    sync_replies_from_history()

    hourly = get_hourly_totals()
    daily  = get_daily_totals()
    best   = get_best_send_times(3)

    total  = sum(hourly.values())
    report = build_heatmap_report()

    logger.info("\n%s", report)

    if send_report and not dry_run:
        try:
            from notifications import send_email
            send_email(subject="Engagement Heatmap Report", body=report)
        except Exception as e:
            logger.warning("Could not send heatmap report: %s", e)

    return {
        "total_engagements": total,
        "best_day":          get_best_day(),
        "best_hour":         get_best_hour(),
        "best_times":        best,
        "report":            report,
    }
