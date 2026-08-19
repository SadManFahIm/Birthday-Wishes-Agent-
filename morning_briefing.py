"""
Morning Briefing Module — Birthday Wishes Agent v10.0
======================================================
প্রতিদিন সকালে আজকের birthdays + tasks summary push করে।

Generates a structured morning brief containing:
  - Today's birthdays (with tier, platform, VIP status)
  - Upcoming birthdays (next 7 days)
  - Pending tasks (wishes to send, follow-ups, check-ins)
  - Agent status (last run, error rate, paused?)
  - Rate-limit health across platforms
  - Overnight events summary
  - Actionable next steps

Delivery channels:
  - Push notification (via push_notifications module)
  - In-app Streamlit dashboard
  - JSON export for external integrations

Scheduling:
  - Cron-compatible: python morning_briefing.py run
  - Configurable delivery time (default 07:00 UTC)
  - Skip weekends option

Author : Fahim (SadManFahIm)
Branch : feature/morning-briefing (→ 10.0)
"""

import sqlite3
import json
import os
import uuid
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

DB_PATH = Path(os.getenv("BWA_DB_PATH", "agent_history.db"))

BRIEFING_HOUR = int(os.getenv("BWA_BRIEFING_HOUR", "7"))
UPCOMING_DAYS = 7

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────


def init_briefing_tables(db_path: Path = DB_PATH) -> None:
    """Create briefing tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS briefing_log (
            id              TEXT PRIMARY KEY,
            briefing_date   TEXT NOT NULL,
            generated_at    TEXT NOT NULL,
            delivered_at    TEXT,
            delivery_method TEXT DEFAULT 'dashboard',
            birthdays_today INTEGER NOT NULL DEFAULT 0,
            birthdays_week  INTEGER NOT NULL DEFAULT 0,
            pending_tasks   INTEGER NOT NULL DEFAULT 0,
            alerts_count    INTEGER NOT NULL DEFAULT 0,
            payload         TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'generated'
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_brief_date
            ON briefing_log(briefing_date);

        CREATE TABLE IF NOT EXISTS briefing_preferences (
            user_id         TEXT PRIMARY KEY,
            enabled         INTEGER NOT NULL DEFAULT 1,
            delivery_hour   INTEGER NOT NULL DEFAULT 7,
            skip_weekends   INTEGER NOT NULL DEFAULT 0,
            include_upcoming INTEGER NOT NULL DEFAULT 1,
            include_tasks   INTEGER NOT NULL DEFAULT 1,
            include_agent   INTEGER NOT NULL DEFAULT 1,
            include_rates   INTEGER NOT NULL DEFAULT 1,
            push_enabled    INTEGER NOT NULL DEFAULT 1,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ──────────────────────────────────────────────────────────────
# Data collectors — each gathers one section of the brief
# ──────────────────────────────────────────────────────────────


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _collect_todays_birthdays(conn: sqlite3.Connection) -> list[dict]:
    """Find contacts with birthdays today."""
    today_md = datetime.now(timezone.utc).strftime("%m-%d")
    birthdays = []

    # Source 1: contact_tier table (has contact_name)
    if _table_exists(conn, "contact_tier"):
        rows = conn.execute(
            """SELECT ct.contact_id, ct.contact_name, ct.current_tier,
                      ct.tier_score
               FROM contact_tier ct"""
        ).fetchall()

        for r in rows:
            # Check life_events for birthday
            has_bday = False
            if _table_exists(conn, "contact_life_events"):
                ev = conn.execute(
                    """SELECT event_date FROM contact_life_events
                       WHERE contact_id=? AND event_type='birthday'
                       AND substr(event_date, 6, 5) = ?""",
                    (r["contact_id"], today_md),
                ).fetchone()
                has_bday = bool(ev)

            if has_bday:
                # Check VIP status
                is_vip = False
                if _table_exists(conn, "vip_contacts"):
                    vip = conn.execute(
                        "SELECT contact_id FROM vip_contacts WHERE contact_id=?",
                        (r["contact_id"],),
                    ).fetchone()
                    is_vip = bool(vip)

                # Get platform from graph_nodes
                platform = "Unknown"
                if _table_exists(conn, "graph_nodes"):
                    gn = conn.execute(
                        "SELECT platform FROM graph_nodes WHERE contact_id=?",
                        (r["contact_id"],),
                    ).fetchone()
                    if gn:
                        platform = gn["platform"]

                # Check if wish already sent today
                wish_sent = False
                if _table_exists(conn, "wish_outcome_log"):
                    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    ws = conn.execute(
                        """SELECT id FROM wish_outcome_log
                           WHERE contact_id=?
                           AND DATE(sent_at)=?""",
                        (r["contact_id"], today_iso),
                    ).fetchone()
                    wish_sent = bool(ws)

                birthdays.append({
                    "contact_id": r["contact_id"],
                    "contact_name": r["contact_name"],
                    "tier": r["current_tier"],
                    "tier_score": r["tier_score"] or 0,
                    "is_vip": is_vip,
                    "platform": platform,
                    "wish_sent": wish_sent,
                })

    # Sort by tier score (VIPs first)
    birthdays.sort(key=lambda x: (-x["is_vip"], -x["tier_score"]))
    return birthdays


def _collect_upcoming_birthdays(conn: sqlite3.Connection,
                                days: int = UPCOMING_DAYS) -> list[dict]:
    """Find birthdays in the next N days (excluding today)."""
    upcoming = []
    if not _table_exists(conn, "contact_life_events"):
        return upcoming
    if not _table_exists(conn, "contact_tier"):
        return upcoming

    now = datetime.now(timezone.utc)
    for d in range(1, days + 1):
        check_date = now + timedelta(days=d)
        md = check_date.strftime("%m-%d")
        rows = conn.execute(
            """SELECT cle.contact_id, cle.event_date,
                      ct.contact_name, ct.current_tier
               FROM contact_life_events cle
               JOIN contact_tier ct ON ct.contact_id = cle.contact_id
               WHERE cle.event_type='birthday'
               AND substr(cle.event_date, 6, 5) = ?""",
            (md,),
        ).fetchall()
        for r in rows:
            upcoming.append({
                "contact_id": r["contact_id"],
                "contact_name": r["contact_name"],
                "tier": r["current_tier"],
                "days_until": d,
                "date": check_date.strftime("%Y-%m-%d"),
                "day_name": check_date.strftime("%A"),
            })
    return upcoming


def _collect_pending_tasks(conn: sqlite3.Connection) -> dict:
    """Gather pending wishes, follow-ups, and action items."""
    tasks = {
        "wishes_pending": [],
        "followups_due": [],
        "checkins_due": [],
        "total": 0,
    }

    # Pending wishes = today's birthdays without a sent wish
    todays = _collect_todays_birthdays(conn)
    tasks["wishes_pending"] = [
        {"contact_id": b["contact_id"],
         "contact_name": b["contact_name"],
         "tier": b["tier"],
         "platform": b["platform"],
         "is_vip": b["is_vip"]}
        for b in todays if not b["wish_sent"]
    ]

    # Follow-ups: wishes sent 3 days ago with no reply
    if _table_exists(conn, "wish_outcome_log"):
        cutoff_start = (datetime.now(timezone.utc)
                        - timedelta(days=5)).isoformat()
        cutoff_end = (datetime.now(timezone.utc)
                      - timedelta(days=2)).isoformat()
        rows = conn.execute(
            """SELECT contact_id, sent_at FROM wish_outcome_log
               WHERE sent_at BETWEEN ? AND ? AND replied=0""",
            (cutoff_start, cutoff_end),
        ).fetchall()
        for r in rows:
            name = ""
            if _table_exists(conn, "contact_tier"):
                ct = conn.execute(
                    "SELECT contact_name FROM contact_tier WHERE contact_id=?",
                    (r["contact_id"],),
                ).fetchone()
                name = ct["contact_name"] if ct else r["contact_id"]
            tasks["followups_due"].append({
                "contact_id": r["contact_id"],
                "contact_name": name,
                "wish_sent_at": r["sent_at"],
            })

    # Autonomous agent scheduled actions
    if _table_exists(conn, "autonomous_decisions"):
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT contact_id, contact_name, action, reason
               FROM autonomous_decisions
               WHERE DATE(decided_at)=? AND action != 'skip'
               AND executed=0""",
            (today_iso,),
        ).fetchall()
        for r in rows:
            if r["action"] == "checkin":
                tasks["checkins_due"].append(dict(r))

    tasks["total"] = (len(tasks["wishes_pending"])
                      + len(tasks["followups_due"])
                      + len(tasks["checkins_due"]))
    return tasks


def _collect_agent_status(conn: sqlite3.Connection) -> dict:
    """Get autonomous agent health status."""
    status = {
        "last_run": None,
        "total_decisions": 0,
        "error_rate_pct": 0.0,
        "is_paused": False,
        "wishes_sent_today": 0,
    }

    if _table_exists(conn, "autonomous_decisions"):
        last = conn.execute(
            """SELECT decided_at FROM autonomous_decisions
               ORDER BY decided_at DESC LIMIT 1"""
        ).fetchone()
        if last:
            status["last_run"] = last["decided_at"]

        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        total = conn.execute(
            """SELECT COUNT(*) as c FROM autonomous_decisions
               WHERE DATE(decided_at)=?""",
            (today_iso,),
        ).fetchone()["c"]
        status["total_decisions"] = total

    # Wishes sent today
    if _table_exists(conn, "wish_outcome_log"):
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sent = conn.execute(
            "SELECT COUNT(*) as c FROM wish_outcome_log WHERE DATE(sent_at)=?",
            (today_iso,),
        ).fetchone()["c"]
        status["wishes_sent_today"] = sent

    # Check for recent errors in audit log
    if _table_exists(conn, "audit_trail"):
        last_24h = (datetime.now(timezone.utc)
                    - timedelta(hours=24)).isoformat()
        total_events = conn.execute(
            "SELECT COUNT(*) as c FROM audit_trail WHERE timestamp >= ?",
            (last_24h,),
        ).fetchone()["c"]
        error_events = conn.execute(
            """SELECT COUNT(*) as c FROM audit_trail
               WHERE timestamp >= ? AND severity='critical'""",
            (last_24h,),
        ).fetchone()["c"]
        if total_events > 0:
            status["error_rate_pct"] = round(
                (error_events / total_events) * 100, 1)

    return status


def _collect_rate_limit_health(conn: sqlite3.Connection) -> list[dict]:
    """Get rate-limit status per platform."""
    health = []
    if not _table_exists(conn, "rl_platform_quotas"):
        return health
    if not _table_exists(conn, "rl_consumption_log"):
        return health

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    quotas = conn.execute(
        "SELECT * FROM rl_platform_quotas WHERE is_enabled=1"
    ).fetchall()

    for q in quotas:
        q = dict(q)
        used = conn.execute(
            """SELECT COUNT(*) as c FROM rl_consumption_log
               WHERE platform=? AND window_day=?""",
            (q["platform"], today),
        ).fetchone()["c"]
        pct = round((used / max(q["daily_limit"], 1)) * 100, 1)
        health.append({
            "platform": q["platform"],
            "used": used,
            "limit": q["daily_limit"],
            "pct": pct,
            "status": ("exhausted" if pct >= 100
                       else "warning" if pct >= 75
                       else "healthy"),
        })

    return health


def _collect_overnight_events(conn: sqlite3.Connection) -> dict:
    """Summarise notable events from the last 12 hours."""
    events = {
        "consent_changes": 0,
        "erasure_requests": 0,
        "new_contacts": 0,
        "throttle_events": 0,
    }

    since = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()

    if _table_exists(conn, "gdpr_audit_log"):
        events["consent_changes"] = conn.execute(
            """SELECT COUNT(*) as c FROM gdpr_audit_log
               WHERE action='consent_recorded' AND timestamp >= ?""",
            (since,),
        ).fetchone()["c"]
        events["erasure_requests"] = conn.execute(
            """SELECT COUNT(*) as c FROM gdpr_audit_log
               WHERE action='right_to_forget' AND timestamp >= ?""",
            (since,),
        ).fetchone()["c"]

    if _table_exists(conn, "audit_trail"):
        events["new_contacts"] = conn.execute(
            """SELECT COUNT(*) as c FROM audit_trail
               WHERE action='contact_created' AND timestamp >= ?""",
            (since,),
        ).fetchone()["c"]

    if _table_exists(conn, "rl_throttle_events"):
        events["throttle_events"] = conn.execute(
            "SELECT COUNT(*) as c FROM rl_throttle_events WHERE timestamp >= ?",
            (since,),
        ).fetchone()["c"]

    return events


# ──────────────────────────────────────────────────────────────
# Core: generate the briefing
# ──────────────────────────────────────────────────────────────


def generate_briefing(db_path: Path = DB_PATH) -> dict:
    """
    Generate today's morning briefing.
    Returns a structured dict with all sections.
    """
    conn = _get_conn(db_path)
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        birthdays_today = _collect_todays_birthdays(conn)
        upcoming = _collect_upcoming_birthdays(conn)
        tasks = _collect_pending_tasks(conn)
        agent = _collect_agent_status(conn)
        rates = _collect_rate_limit_health(conn)
        overnight = _collect_overnight_events(conn)

        # Count alerts (things needing attention)
        alerts = []
        if any(b["is_vip"] and not b["wish_sent"]
               for b in birthdays_today):
            alerts.append({
                "type": "vip_birthday",
                "severity": "high",
                "message": "VIP contact(s) have birthday today — wish pending",
            })
        if agent["error_rate_pct"] > 20:
            alerts.append({
                "type": "high_error_rate",
                "severity": "high",
                "message": f"Error rate at {agent['error_rate_pct']}% in last 24h",
            })
        exhausted = [r for r in rates if r["status"] == "exhausted"]
        if exhausted:
            platforms = ", ".join(r["platform"] for r in exhausted)
            alerts.append({
                "type": "rate_limit_exhausted",
                "severity": "warning",
                "message": f"Daily quota exhausted: {platforms}",
            })
        if overnight["erasure_requests"] > 0:
            alerts.append({
                "type": "erasure_requests",
                "severity": "info",
                "message": f"{overnight['erasure_requests']} erasure request(s) overnight",
            })

        briefing = {
            "briefing_id": str(uuid.uuid4()),
            "date": today,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "greeting": _build_greeting(),
            "summary": {
                "birthdays_today": len(birthdays_today),
                "birthdays_week": len(upcoming),
                "pending_tasks": tasks["total"],
                "alerts": len(alerts),
            },
            "birthdays_today": birthdays_today,
            "upcoming_birthdays": upcoming,
            "tasks": tasks,
            "agent_status": agent,
            "rate_limit_health": rates,
            "overnight_events": overnight,
            "alerts": alerts,
        }

        # Persist
        conn.execute(
            """INSERT OR REPLACE INTO briefing_log
               (id, briefing_date, generated_at, birthdays_today,
                birthdays_week, pending_tasks, alerts_count,
                payload, status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (briefing["briefing_id"], today, briefing["generated_at"],
             len(birthdays_today), len(upcoming),
             tasks["total"], len(alerts),
             json.dumps(briefing, default=str), "generated"),
        )
        conn.commit()
        return briefing
    finally:
        conn.close()


def _build_greeting() -> str:
    """Time-aware greeting message."""
    hour = datetime.now(timezone.utc).hour
    if hour < 12:
        return "Good morning! ☀️"
    elif hour < 17:
        return "Good afternoon! 🌤"
    else:
        return "Good evening! 🌙"


# ──────────────────────────────────────────────────────────────
# Delivery
# ──────────────────────────────────────────────────────────────


def deliver_push(user_id: str, briefing: dict,
                 db_path: Path = DB_PATH) -> dict:
    """Send the briefing summary as a push notification."""
    try:
        from push_notifications import send_push
    except ImportError:
        logger.warning("push_notifications not available — skipping push")
        return {"delivered": False, "reason": "module_not_available"}

    s = briefing["summary"]
    lines = []
    if s["birthdays_today"] > 0:
        lines.append(f"🎂 {s['birthdays_today']} birthday(s) today")
    if s["pending_tasks"] > 0:
        lines.append(f"📋 {s['pending_tasks']} pending task(s)")
    if s["alerts"] > 0:
        lines.append(f"⚠️ {s['alerts']} alert(s)")
    if s["birthdays_week"] > 0:
        lines.append(f"📅 {s['birthdays_week']} upcoming this week")

    body = " · ".join(lines) if lines else "No birthdays or tasks today ✨"

    results = send_push(
        user_id, "weekly_digest",
        title="☀️ Morning Briefing",
        body=body,
        data={
            "type": "morning_briefing",
            "date": briefing["date"],
            "birthdays": s["birthdays_today"],
            "tasks": s["pending_tasks"],
        },
        respect_quiet=False,
        db_path=db_path,
    )

    # Update delivery status
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """UPDATE briefing_log SET delivered_at=?,
               delivery_method='push', status='delivered'
               WHERE briefing_date=?""",
            (datetime.now(timezone.utc).isoformat(), briefing["date"]),
        )
        conn.commit()
    finally:
        conn.close()

    return {"delivered": True, "push_results": results}


def format_text_briefing(briefing: dict) -> str:
    """Format the briefing as a readable text block (for logs/CLI)."""
    s = briefing["summary"]
    lines = [
        f"\n{'='*50}",
        f"  {briefing['greeting']}  Morning Briefing — {briefing['date']}",
        f"{'='*50}",
        "",
    ]

    # Alerts first
    if briefing["alerts"]:
        lines.append("⚠️  ALERTS:")
        for a in briefing["alerts"]:
            marker = "🔴" if a["severity"] == "high" else "🟡"
            lines.append(f"  {marker} {a['message']}")
        lines.append("")

    # Today's birthdays
    lines.append(f"🎂 TODAY'S BIRTHDAYS ({s['birthdays_today']}):")
    if briefing["birthdays_today"]:
        for b in briefing["birthdays_today"]:
            vip = " ⭐VIP" if b["is_vip"] else ""
            sent = " ✅sent" if b["wish_sent"] else " ⏳pending"
            lines.append(
                f"  • {b['contact_name']} [{b['tier']}]{vip}"
                f" — {b['platform']}{sent}")
    else:
        lines.append("  No birthdays today")
    lines.append("")

    # Upcoming
    if briefing["upcoming_birthdays"]:
        lines.append(f"📅 UPCOMING ({s['birthdays_week']} this week):")
        for u in briefing["upcoming_birthdays"][:5]:
            lines.append(
                f"  • {u['contact_name']} — {u['day_name']} "
                f"({u['days_until']}d)")
        lines.append("")

    # Tasks
    t = briefing["tasks"]
    if t["total"] > 0:
        lines.append(f"📋 PENDING TASKS ({t['total']}):")
        for w in t["wishes_pending"]:
            vip = " ⭐" if w["is_vip"] else ""
            lines.append(f"  🎁 Send wish → {w['contact_name']}{vip}")
        for f in t["followups_due"]:
            lines.append(f"  🔄 Follow up → {f['contact_name']}")
        for c in t["checkins_due"]:
            lines.append(
                f"  👋 Check in → {c.get('contact_name', c['contact_id'])}")
        lines.append("")

    # Agent status
    ag = briefing["agent_status"]
    lines.append("🤖 AGENT STATUS:")
    lines.append(f"  Last run: {ag['last_run'] or 'Never'}")
    lines.append(f"  Wishes sent today: {ag['wishes_sent_today']}")
    if ag["error_rate_pct"] > 0:
        lines.append(f"  Error rate (24h): {ag['error_rate_pct']}%")
    lines.append("")

    # Rate limits
    if briefing["rate_limit_health"]:
        lines.append("⚡ RATE LIMITS:")
        for r in briefing["rate_limit_health"]:
            icon = ("🟢" if r["status"] == "healthy"
                    else "🟡" if r["status"] == "warning" else "🔴")
            lines.append(
                f"  {icon} {r['platform']}: "
                f"{r['used']}/{r['limit']} ({r['pct']}%)")
        lines.append("")

    # Overnight
    ov = briefing["overnight_events"]
    notable = {k: v for k, v in ov.items() if v > 0}
    if notable:
        lines.append("🌙 OVERNIGHT:")
        for k, v in notable.items():
            lines.append(f"  • {k.replace('_', ' ').title()}: {v}")
        lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Preferences
# ──────────────────────────────────────────────────────────────


def set_briefing_prefs(user_id: str, *,
                       enabled: bool = True,
                       delivery_hour: int = 7,
                       skip_weekends: bool = False,
                       push_enabled: bool = True,
                       db_path: Path = DB_PATH) -> dict:
    """Set morning briefing preferences."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO briefing_preferences
               (user_id, enabled, delivery_hour, skip_weekends,
                push_enabled, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
               enabled=excluded.enabled,
               delivery_hour=excluded.delivery_hour,
               skip_weekends=excluded.skip_weekends,
               push_enabled=excluded.push_enabled,
               updated_at=excluded.updated_at""",
            (user_id, 1 if enabled else 0, delivery_hour,
             1 if skip_weekends else 0, 1 if push_enabled else 0,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"user_id": user_id, "enabled": enabled,
                "delivery_hour": delivery_hour,
                "push_enabled": push_enabled}
    finally:
        conn.close()


def get_briefing_prefs(user_id: str,
                       db_path: Path = DB_PATH) -> dict:
    """Get briefing preferences."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM briefing_preferences WHERE user_id=?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else {
            "user_id": user_id, "enabled": True,
            "delivery_hour": BRIEFING_HOUR,
            "skip_weekends": False, "push_enabled": True,
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# History
# ──────────────────────────────────────────────────────────────


def get_briefing_history(limit: int = 30,
                         db_path: Path = DB_PATH) -> list[dict]:
    """Return past briefing summaries."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            """SELECT id, briefing_date, generated_at, delivered_at,
                      delivery_method, birthdays_today, birthdays_week,
                      pending_tasks, alerts_count, status
               FROM briefing_log ORDER BY briefing_date DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_briefing_by_date(date_str: str,
                         db_path: Path = DB_PATH) -> Optional[dict]:
    """Retrieve the full briefing payload for a specific date."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT payload FROM briefing_log WHERE briefing_date=?",
            (date_str,),
        ).fetchone()
        return json.loads(row["payload"]) if row else None
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Stats
# ──────────────────────────────────────────────────────────────


def get_stats(db_path: Path = DB_PATH) -> dict:
    """Dashboard aggregate stats."""
    conn = _get_conn(db_path)
    try:
        total_briefs = conn.execute(
            "SELECT COUNT(*) as c FROM briefing_log"
        ).fetchone()["c"]
        delivered = conn.execute(
            "SELECT COUNT(*) as c FROM briefing_log WHERE status='delivered'"
        ).fetchone()["c"]

        avg_birthdays = conn.execute(
            "SELECT AVG(birthdays_today) as a FROM briefing_log"
        ).fetchone()["a"] or 0

        avg_tasks = conn.execute(
            "SELECT AVG(pending_tasks) as a FROM briefing_log"
        ).fetchone()["a"] or 0

        last_brief = conn.execute(
            """SELECT briefing_date, status FROM briefing_log
               ORDER BY briefing_date DESC LIMIT 1"""
        ).fetchone()

        streak = 0
        dates = conn.execute(
            """SELECT briefing_date FROM briefing_log
               ORDER BY briefing_date DESC LIMIT 30"""
        ).fetchall()
        if dates:
            today = datetime.now(timezone.utc).date()
            for i, d in enumerate(dates):
                expected = today - timedelta(days=i)
                if d["briefing_date"] == expected.isoformat():
                    streak += 1
                else:
                    break

        return {
            "total_briefings": total_briefs,
            "delivered": delivered,
            "avg_birthdays_per_day": round(avg_birthdays, 1),
            "avg_tasks_per_day": round(avg_tasks, 1),
            "last_briefing": dict(last_brief) if last_brief else None,
            "streak_days": streak,
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """Morning briefing dashboard."""
    try:
        import streamlit as st
        import pandas as pd
    except ImportError:
        return

    st.set_page_config(page_title="Morning Briefing", page_icon="☀️",
                       layout="wide", initial_sidebar_state="collapsed")

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    html,body,[class*="css"]{font-family:'Inter',sans-serif;}
    :root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--accent:#f78166;
          --green:#3fb950;--yellow:#d29922;--red:#f85149;--blue:#58a6ff;
          --muted:#8b949e;--text:#e6edf3;}
    .stApp{background:var(--bg);color:var(--text);}
    .cc-header{display:flex;align-items:center;gap:14px;padding:18px 0 10px;
               border-bottom:1px solid var(--border);margin-bottom:24px;}
    .cc-header h1{font-size:1.4rem;font-weight:700;letter-spacing:-0.02em;margin:0;}
    .cc-badge{background:var(--accent);color:#fff;font-size:0.65rem;font-weight:700;
              padding:2px 8px;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;}
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);
                font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:var(--muted);margin:22px 0 10px;
                   display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .c-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);
        border-color:var(--accent);color:#fff;}
    div.stTabs [data-baseweb="tab-list"]{gap:0;border-bottom:1px solid var(--border);}
    div.stTabs [data-baseweb="tab"]{color:var(--muted)!important;background:transparent!important;
        border-bottom:2px solid transparent;padding:0.5rem 1rem;}
    div.stTabs [aria-selected="true"]{color:var(--accent)!important;
        border-bottom:2px solid var(--accent)!important;}
    .alert-high{border-left:3px solid var(--red);padding-left:12px;margin:6px 0;}
    .alert-warning{border-left:3px solid var(--yellow);padding-left:12px;margin:6px 0;}
    .alert-info{border-left:3px solid var(--blue);padding-left:12px;margin:6px 0;}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    </style>
    """, unsafe_allow_html=True)

    init_briefing_tables()

    # Header
    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">☀️</span>
      <h1>Morning Briefing</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    tabs = st.tabs(["📋 Today's Brief", "📊 History", "⚙️ Settings"])

    # Tab 0: Today's briefing
    with tabs[0]:
        if st.button("🔄 Generate Today's Briefing", key="btn_gen"):
            st.rerun()

        briefing = generate_briefing()
        s = briefing["summary"]

        # KPIs
        st.markdown('<div class="section-title">Summary</div>',
                    unsafe_allow_html=True)
        k1, k2, k3, k4 = st.columns(4)
        for col, val, lbl, color in [
            (k1, s["birthdays_today"], "Birthdays Today", "--accent"),
            (k2, s["pending_tasks"], "Pending Tasks", "--yellow"),
            (k3, s["alerts"], "Alerts", "--red"),
            (k4, s["birthdays_week"], "This Week", "--blue"),
        ]:
            col.markdown(
                f'<div class="mini">'
                f'<div class="mini-val" style="color:var({color})">'
                f'{val}</div>'
                f'<div class="mini-lbl">{lbl}</div></div>',
                unsafe_allow_html=True)

        # Alerts
        if briefing["alerts"]:
            st.markdown('<div class="section-title">Alerts</div>',
                        unsafe_allow_html=True)
            for a in briefing["alerts"]:
                cls = f"alert-{a['severity']}"
                st.markdown(
                    f'<div class="{cls}">{a["message"]}</div>',
                    unsafe_allow_html=True)

        # Birthdays today
        st.markdown('<div class="section-title">Birthdays Today</div>',
                    unsafe_allow_html=True)
        if briefing["birthdays_today"]:
            for b in briefing["birthdays_today"]:
                vip = " ⭐" if b["is_vip"] else ""
                status_icon = "✅" if b["wish_sent"] else "⏳"
                st.markdown(
                    f'<div class="c-card">'
                    f'<span style="font-weight:600">'
                    f'{b["contact_name"]}</span>{vip} '
                    f'<span style="color:var(--muted);font-size:0.8rem">'
                    f'[{b["tier"]}] · {b["platform"]}</span> '
                    f'{status_icon}</div>',
                    unsafe_allow_html=True)
        else:
            st.info("No birthdays today")

        # Upcoming
        if briefing["upcoming_birthdays"]:
            st.markdown('<div class="section-title">Upcoming This Week'
                        '</div>', unsafe_allow_html=True)
            for u in briefing["upcoming_birthdays"][:7]:
                st.markdown(
                    f'<div class="c-card">'
                    f'📅 <strong>{u["contact_name"]}</strong> — '
                    f'{u["day_name"]} '
                    f'<span style="color:var(--muted)">'
                    f'(in {u["days_until"]}d)</span></div>',
                    unsafe_allow_html=True)

        # Tasks
        t = briefing["tasks"]
        if t["total"] > 0:
            st.markdown('<div class="section-title">Pending Tasks</div>',
                        unsafe_allow_html=True)
            for w in t["wishes_pending"]:
                vip = " ⭐" if w["is_vip"] else ""
                st.markdown(
                    f'<div class="c-card">🎁 Send wish → '
                    f'<strong>{w["contact_name"]}</strong>{vip} '
                    f'<span style="color:var(--muted)">'
                    f'{w["platform"]}</span></div>',
                    unsafe_allow_html=True)
            for f in t["followups_due"]:
                st.markdown(
                    f'<div class="c-card">🔄 Follow up → '
                    f'<strong>{f["contact_name"]}</strong></div>',
                    unsafe_allow_html=True)

        # Rate limits
        if briefing["rate_limit_health"]:
            st.markdown('<div class="section-title">Platform Health</div>',
                        unsafe_allow_html=True)
            for r in briefing["rate_limit_health"]:
                icon = ("🟢" if r["status"] == "healthy"
                        else "🟡" if r["status"] == "warning" else "🔴")
                bar_color = ("--green" if r["status"] == "healthy"
                             else "--yellow" if r["status"] == "warning"
                             else "--red")
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;'
                    f'margin:3px 0">'
                    f'<span style="min-width:90px;font-size:0.8rem">'
                    f'{icon} {r["platform"]}</span>'
                    f'<div style="flex:1;background:#0d1117;'
                    f'border-radius:3px;height:12px">'
                    f'<div style="width:{min(r["pct"],100):.0f}%;'
                    f'background:var({bar_color});height:12px;'
                    f'border-radius:3px"></div></div>'
                    f'<span style="font-size:0.7rem;color:var(--muted);'
                    f'min-width:55px;text-align:right;'
                    f'font-family:JetBrains Mono,monospace">'
                    f'{r["used"]}/{r["limit"]}</span></div>',
                    unsafe_allow_html=True)

        # Push delivery button
        st.markdown("")
        if st.button("📱 Send as Push Notification", key="btn_push"):
            result = deliver_push("default", briefing)
            if result.get("delivered"):
                st.success("Briefing pushed to devices")
            else:
                st.warning(f"Push: {result.get('reason', 'unknown')}")

    # Tab 1: History
    with tabs[1]:
        st.markdown('<div class="section-title">Briefing History</div>',
                    unsafe_allow_html=True)
        history = get_briefing_history()
        if history:
            df = pd.DataFrame(history)
            st.dataframe(df, use_container_width=True, height=400)
        else:
            st.info("No briefing history yet.")

        bstats = get_stats()
        st.markdown('<div class="section-title">Stats</div>',
                    unsafe_allow_html=True)
        s1, s2, s3, s4 = st.columns(4)
        for col, val, lbl in [
            (s1, bstats["total_briefings"], "Total Briefs"),
            (s2, bstats["streak_days"], "Day Streak"),
            (s3, bstats["avg_birthdays_per_day"], "Avg Birthdays/Day"),
            (s4, bstats["avg_tasks_per_day"], "Avg Tasks/Day"),
        ]:
            col.markdown(
                f'<div class="mini"><div class="mini-val">{val}</div>'
                f'<div class="mini-lbl">{lbl}</div></div>',
                unsafe_allow_html=True)

    # Tab 2: Settings
    with tabs[2]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        uid = st.text_input("User ID", "default", key="pref_uid")
        prefs = get_briefing_prefs(uid)
        p_en = st.checkbox("Enable briefings",
                           prefs.get("enabled", True), key="p_en")
        p_hour = st.number_input("Delivery hour (UTC)",
                                 0, 23, prefs.get("delivery_hour", 7),
                                 key="p_hr")
        p_skip = st.checkbox("Skip weekends",
                             prefs.get("skip_weekends", False), key="p_skip")
        p_push = st.checkbox("Push notification",
                             prefs.get("push_enabled", True), key="p_push")
        if st.button("Save", key="btn_prefs"):
            set_briefing_prefs(uid, enabled=p_en,
                               delivery_hour=p_hour,
                               skip_weekends=p_skip,
                               push_enabled=p_push)
            st.success("Preferences saved")
        st.markdown('</div>', unsafe_allow_html=True)

    # Footer
    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/morning-briefing</code> · Morning Briefing v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test for morning briefing."""
    import tempfile

    print("=" * 60)
    print("Morning Briefing Module — Self-Test")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    try:
        init_briefing_tables(tdb)
        conn = _get_conn(tdb)

        # Seed test data
        print("\n[1/8] Seeding test data ...")
        today_md = datetime.now(timezone.utc).strftime("%m-%d")
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tmrw_md = (datetime.now(timezone.utc)
                   + timedelta(days=1)).strftime("%m-%d")
        in3d_md = (datetime.now(timezone.utc)
                   + timedelta(days=3)).strftime("%m-%d")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS contact_tier (
                contact_id TEXT PRIMARY KEY, contact_name TEXT,
                current_tier TEXT, tier_score REAL);
            CREATE TABLE IF NOT EXISTS contact_life_events (
                id TEXT PRIMARY KEY, contact_id TEXT,
                event_type TEXT, event_date TEXT);
            CREATE TABLE IF NOT EXISTS vip_contacts (
                contact_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS graph_nodes (
                contact_id TEXT PRIMARY KEY, platform TEXT);
            CREATE TABLE IF NOT EXISTS wish_outcome_log (
                id TEXT PRIMARY KEY, contact_id TEXT,
                sent_at TEXT, replied INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS autonomous_decisions (
                id TEXT PRIMARY KEY, contact_id TEXT,
                contact_name TEXT, action TEXT,
                reason TEXT, decided_at TEXT, executed INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS rl_platform_quotas (
                platform TEXT PRIMARY KEY, daily_limit INTEGER,
                hourly_limit INTEGER, per_minute_limit INTEGER,
                cooldown_days INTEGER, is_enabled INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS rl_consumption_log (
                id TEXT PRIMARY KEY, platform TEXT,
                contact_id TEXT, action_type TEXT,
                timestamp TEXT, window_day TEXT, window_hour TEXT);
        """)

        # Contacts
        contacts = [
            ("c-001", "Alice Chen", "Close Friend", 9.5),
            ("c-002", "Bob Rahman", "Colleague", 7.0),
            ("c-003", "Sara Khan", "Close Friend", 8.5),
            ("c-004", "Tanvir Ahmed", "Acquaintance", 4.0),
        ]
        for c in contacts:
            conn.execute(
                "INSERT INTO contact_tier VALUES (?,?,?,?)", c)

        # Birthdays
        conn.execute(
            "INSERT INTO contact_life_events VALUES (?,?,?,?)",
            ("ev-1", "c-001", "birthday", f"1995-{today_md}"))
        conn.execute(
            "INSERT INTO contact_life_events VALUES (?,?,?,?)",
            ("ev-2", "c-003", "birthday", f"1998-{today_md}"))
        conn.execute(
            "INSERT INTO contact_life_events VALUES (?,?,?,?)",
            ("ev-3", "c-002", "birthday", f"1992-{tmrw_md}"))
        conn.execute(
            "INSERT INTO contact_life_events VALUES (?,?,?,?)",
            ("ev-4", "c-004", "birthday", f"1990-{in3d_md}"))

        # VIP
        conn.execute("INSERT INTO vip_contacts VALUES (?)", ("c-001",))

        # Platforms
        conn.execute("INSERT INTO graph_nodes VALUES (?,?)",
                     ("c-001", "LinkedIn"))
        conn.execute("INSERT INTO graph_nodes VALUES (?,?)",
                     ("c-003", "WhatsApp"))

        # One wish already sent
        conn.execute(
            "INSERT INTO wish_outcome_log VALUES (?,?,?,?)",
            ("w-1", "c-003", f"{today_iso}T08:00:00", 0))

        # Rate limit quotas
        conn.execute(
            "INSERT INTO rl_platform_quotas VALUES (?,?,?,?,?,?)",
            ("linkedin", 25, 10, 3, 30, 1))
        conn.execute(
            "INSERT INTO rl_platform_quotas VALUES (?,?,?,?,?,?)",
            ("whatsapp", 50, 20, 5, 7, 1))

        # Some consumption
        for i in range(20):
            conn.execute(
                "INSERT INTO rl_consumption_log VALUES (?,?,?,?,?,?,?)",
                (f"rl-{i}", "linkedin", f"c-{i}", "send",
                 datetime.now(timezone.utc).isoformat(),
                 today_iso, datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")))

        conn.commit()
        conn.close()
        print("       ✅ Test DB seeded (4 contacts, 2 today, 2 upcoming)")

        # 2. Generate briefing
        print("[2/8] Generate briefing ...")
        briefing = generate_briefing(tdb)
        assert briefing["summary"]["birthdays_today"] == 2
        assert briefing["summary"]["birthdays_week"] >= 2
        print(f"       ✅ {briefing['summary']['birthdays_today']} today, "
              f"{briefing['summary']['birthdays_week']} this week")

        # 3. Birthday details
        print("[3/8] Birthday details ...")
        alice = [b for b in briefing["birthdays_today"]
                 if b["contact_name"] == "Alice Chen"]
        assert len(alice) == 1
        assert alice[0]["is_vip"]
        assert not alice[0]["wish_sent"]
        assert alice[0]["platform"] == "LinkedIn"
        sara = [b for b in briefing["birthdays_today"]
                if b["contact_name"] == "Sara Khan"]
        assert sara[0]["wish_sent"]  # already sent today
        print(f"       ✅ Alice=VIP+pending, Sara=sent")

        # 4. Tasks
        print("[4/8] Tasks ...")
        t = briefing["tasks"]
        assert len(t["wishes_pending"]) == 1  # only Alice (Sara already sent)
        assert t["wishes_pending"][0]["is_vip"]
        print(f"       ✅ {t['total']} total tasks, "
              f"{len(t['wishes_pending'])} wishes pending")

        # 5. Alerts
        print("[5/8] Alerts ...")
        alert_types = [a["type"] for a in briefing["alerts"]]
        assert "vip_birthday" in alert_types
        print(f"       ✅ {len(briefing['alerts'])} alert(s): {alert_types}")

        # 6. Rate limit health
        print("[6/8] Rate limit health ...")
        rl = briefing["rate_limit_health"]
        assert len(rl) >= 2
        li = [r for r in rl if r["platform"] == "linkedin"][0]
        assert li["used"] == 20
        assert li["pct"] == 80.0
        assert li["status"] == "warning"
        print(f"       ✅ LinkedIn 20/25 (80%, warning)")

        # 7. Text format
        print("[7/8] Text format ...")
        text = format_text_briefing(briefing)
        assert "Alice Chen" in text
        assert "Morning Briefing" in text
        assert "VIP" in text
        print(f"       ✅ Text formatted ({len(text)} chars)")
        print(text)

        # 8. History + preferences
        print("[8/8] History & prefs ...")
        history = get_briefing_history(db_path=tdb)
        assert len(history) == 1
        set_briefing_prefs("test-user", delivery_hour=8,
                           skip_weekends=True, db_path=tdb)
        prefs = get_briefing_prefs("test-user", tdb)
        assert prefs["delivery_hour"] == 8
        assert prefs["skip_weekends"]
        stats = get_stats(tdb)
        assert stats["total_briefings"] == 1
        print(f"       ✅ History={len(history)}, prefs saved, "
              f"streak={stats['streak_days']}")

        print("\n" + "=" * 60)
        print("✅ ALL MORNING BRIEFING SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(tdb)


# ──────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    init_briefing_tables()

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        briefing = generate_briefing()
        print(format_text_briefing(briefing))
        if "--push" in sys.argv:
            user = sys.argv[sys.argv.index("--push") + 1] if (
                sys.argv.index("--push") + 1 < len(sys.argv)
            ) else "default"
            result = deliver_push(user, briefing)
            print(f"\nPush: {result}")
    else:
        print("=== Morning Briefing -- self test ===\n")
        _self_test()
else:
    render_dashboard()
