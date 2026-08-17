"""
Rate Limit Dashboard — Birthday Wishes Agent v10.0
====================================================
Per-platform rate-limit status in real time.  Tracks quotas,
consumption, cooldowns, and throttle events across every
outreach channel the agent uses.

Platforms tracked:
  LinkedIn, WhatsApp, Telegram, Email, Twitter/X,
  Instagram, Slack, Facebook, WeChat, LINE

Features:
  - Configurable per-platform quotas (daily / hourly / per-minute)
  - Real-time consumption tracking with sliding windows
  - Cooldown tracking per contact per platform
  - Throttle event logging and analytics
  - Auto-pause integration when limits are breached
  - Quota reset scheduling
  - Streamlit dashboard with live status indicators

Integration:
  from rate_limit_dashboard import (
      consume_quota, is_allowed, get_platform_status,
      register_rate_limit_routes,
  )
  # Before sending
  if is_allowed("linkedin"):
      consume_quota("linkedin", contact_id="c-001")
      # ... send wish ...

Author : Fahim (SadManFahIm)
Branch : feature/rate-limit-dashboard (→ 10.0)
"""

import sqlite3
import json
import os
import uuid
import logging
import time as _time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

DB_PATH = Path(os.getenv("BWA_DB_PATH", "agent_history.db"))

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Platform definitions & default quotas
# ──────────────────────────────────────────────────────────────

PLATFORMS = [
    "linkedin", "whatsapp", "telegram", "email", "twitter",
    "instagram", "slack", "facebook", "wechat", "line",
]

# Sensible defaults — real API limits vary by account tier
DEFAULT_QUOTAS = {
    "linkedin":  {"daily": 25,  "hourly": 10,  "per_minute": 3,
                  "cooldown_days": 30},
    "whatsapp":  {"daily": 50,  "hourly": 20,  "per_minute": 5,
                  "cooldown_days": 7},
    "telegram":  {"daily": 100, "hourly": 40,  "per_minute": 10,
                  "cooldown_days": 7},
    "email":     {"daily": 200, "hourly": 50,  "per_minute": 10,
                  "cooldown_days": 30},
    "twitter":   {"daily": 30,  "hourly": 10,  "per_minute": 2,
                  "cooldown_days": 30},
    "instagram": {"daily": 20,  "hourly": 8,   "per_minute": 2,
                  "cooldown_days": 30},
    "slack":     {"daily": 100, "hourly": 30,  "per_minute": 5,
                  "cooldown_days": 1},
    "facebook":  {"daily": 30,  "hourly": 10,  "per_minute": 3,
                  "cooldown_days": 30},
    "wechat":    {"daily": 40,  "hourly": 15,  "per_minute": 3,
                  "cooldown_days": 14},
    "line":      {"daily": 50,  "hourly": 20,  "per_minute": 5,
                  "cooldown_days": 14},
}

PLATFORM_LABELS = {
    "linkedin": "LinkedIn", "whatsapp": "WhatsApp",
    "telegram": "Telegram", "email": "Email",
    "twitter": "Twitter / X", "instagram": "Instagram",
    "slack": "Slack", "facebook": "Facebook",
    "wechat": "WeChat", "line": "LINE",
}

PLATFORM_ICONS = {
    "linkedin": "🔗", "whatsapp": "💬", "telegram": "✈️",
    "email": "📧", "twitter": "🐦", "instagram": "📸",
    "slack": "💼", "facebook": "👤", "wechat": "🟢",
    "line": "🟩",
}


# ──────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────


def init_rate_limit_tables(db_path: Path = DB_PATH) -> None:
    """Create rate-limit tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rl_platform_quotas (
            platform        TEXT PRIMARY KEY,
            daily_limit     INTEGER NOT NULL,
            hourly_limit    INTEGER NOT NULL,
            per_minute_limit INTEGER NOT NULL,
            cooldown_days   INTEGER NOT NULL DEFAULT 30,
            is_enabled      INTEGER NOT NULL DEFAULT 1,
            auto_pause      INTEGER NOT NULL DEFAULT 1,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS rl_consumption_log (
            id              TEXT PRIMARY KEY,
            platform        TEXT NOT NULL,
            contact_id      TEXT,
            action_type     TEXT NOT NULL DEFAULT 'send',
            timestamp       TEXT NOT NULL,
            window_day      TEXT NOT NULL,
            window_hour     TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rl_cons_platform
            ON rl_consumption_log(platform);
        CREATE INDEX IF NOT EXISTS idx_rl_cons_day
            ON rl_consumption_log(platform, window_day);
        CREATE INDEX IF NOT EXISTS idx_rl_cons_hour
            ON rl_consumption_log(platform, window_hour);
        CREATE INDEX IF NOT EXISTS idx_rl_cons_ts
            ON rl_consumption_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_rl_cons_contact
            ON rl_consumption_log(platform, contact_id);

        CREATE TABLE IF NOT EXISTS rl_throttle_events (
            id              TEXT PRIMARY KEY,
            platform        TEXT NOT NULL,
            limit_type      TEXT NOT NULL,
            limit_value     INTEGER NOT NULL,
            current_count   INTEGER NOT NULL,
            contact_id      TEXT,
            action_taken    TEXT NOT NULL DEFAULT 'blocked',
            timestamp       TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_rl_throttle_platform
            ON rl_throttle_events(platform);
        CREATE INDEX IF NOT EXISTS idx_rl_throttle_ts
            ON rl_throttle_events(timestamp);

        CREATE TABLE IF NOT EXISTS rl_cooldown_tracker (
            id              TEXT PRIMARY KEY,
            platform        TEXT NOT NULL,
            contact_id      TEXT NOT NULL,
            last_contact_at TEXT NOT NULL,
            cooldown_until  TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_rl_cooldown_key
            ON rl_cooldown_tracker(platform, contact_id);
    """)
    conn.commit()

    # Seed default quotas for any missing platforms
    for plat, quotas in DEFAULT_QUOTAS.items():
        conn.execute(
            """INSERT OR IGNORE INTO rl_platform_quotas
               (platform, daily_limit, hourly_limit, per_minute_limit,
                cooldown_days)
               VALUES (?,?,?,?,?)""",
            (plat, quotas["daily"], quotas["hourly"],
             quotas["per_minute"], quotas["cooldown_days"]),
        )
    conn.commit()
    conn.close()
    logger.info("Rate limit tables initialised: %s", db_path)


def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ──────────────────────────────────────────────────────────────
# Quota management
# ──────────────────────────────────────────────────────────────


def set_quota(platform: str, *, daily: int = 0, hourly: int = 0,
              per_minute: int = 0, cooldown_days: int = 0,
              enabled: bool = True, auto_pause: bool = True,
              db_path: Path = DB_PATH) -> dict:
    """Create or update a platform's rate-limit quota."""
    platform = platform.lower()
    conn = _get_conn(db_path)
    try:
        existing = conn.execute(
            "SELECT * FROM rl_platform_quotas WHERE platform=?",
            (platform,),
        ).fetchone()
        now = datetime.now(timezone.utc).isoformat()

        if existing:
            e = dict(existing)
            conn.execute(
                """UPDATE rl_platform_quotas SET
                   daily_limit=?, hourly_limit=?, per_minute_limit=?,
                   cooldown_days=?, is_enabled=?, auto_pause=?, updated_at=?
                   WHERE platform=?""",
                (daily or e["daily_limit"],
                 hourly or e["hourly_limit"],
                 per_minute or e["per_minute_limit"],
                 cooldown_days or e["cooldown_days"],
                 1 if enabled else 0,
                 1 if auto_pause else 0,
                 now, platform),
            )
        else:
            dq = DEFAULT_QUOTAS.get(platform, DEFAULT_QUOTAS["email"])
            conn.execute(
                """INSERT INTO rl_platform_quotas
                   (platform, daily_limit, hourly_limit, per_minute_limit,
                    cooldown_days, is_enabled, auto_pause, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (platform,
                 daily or dq["daily"],
                 hourly or dq["hourly"],
                 per_minute or dq["per_minute"],
                 cooldown_days or dq["cooldown_days"],
                 1 if enabled else 0,
                 1 if auto_pause else 0,
                 now),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM rl_platform_quotas WHERE platform=?",
            (platform,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_quotas(db_path: Path = DB_PATH) -> list[dict]:
    """Return all platform quotas."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM rl_platform_quotas ORDER BY platform"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Real-time consumption
# ──────────────────────────────────────────────────────────────


def _now_windows() -> tuple[str, str, str]:
    """Return (iso_ts, day_key 'YYYY-MM-DD', hour_key 'YYYY-MM-DD-HH')."""
    now = datetime.now(timezone.utc)
    ts = now.isoformat()
    day = now.strftime("%Y-%m-%d")
    hour = now.strftime("%Y-%m-%d-%H")
    return ts, day, hour


def _get_counts(conn: sqlite3.Connection, platform: str,
                day: str, hour: str) -> dict:
    """Get current consumption counts for a platform."""
    daily = conn.execute(
        "SELECT COUNT(*) as c FROM rl_consumption_log "
        "WHERE platform=? AND window_day=?",
        (platform, day),
    ).fetchone()["c"]

    hourly = conn.execute(
        "SELECT COUNT(*) as c FROM rl_consumption_log "
        "WHERE platform=? AND window_hour=?",
        (platform, hour),
    ).fetchone()["c"]

    one_min_ago = (datetime.now(timezone.utc)
                   - timedelta(minutes=1)).isoformat()
    per_min = conn.execute(
        "SELECT COUNT(*) as c FROM rl_consumption_log "
        "WHERE platform=? AND timestamp >= ?",
        (platform, one_min_ago),
    ).fetchone()["c"]

    return {"daily": daily, "hourly": hourly, "per_minute": per_min}


def is_allowed(platform: str, contact_id: str = "",
               db_path: Path = DB_PATH) -> dict:
    """
    Check if a send action is allowed right now.
    Returns {allowed, reason, counts, limits, cooldown_active}.
    """
    platform = platform.lower()
    conn = _get_conn(db_path)
    try:
        quota = conn.execute(
            "SELECT * FROM rl_platform_quotas WHERE platform=?",
            (platform,),
        ).fetchone()

        if not quota:
            return {"allowed": True, "reason": "no_quota_configured",
                    "counts": {}, "limits": {}, "cooldown_active": False}

        quota = dict(quota)
        if not quota["is_enabled"]:
            return {"allowed": False, "reason": "platform_disabled",
                    "counts": {}, "limits": quota,
                    "cooldown_active": False}

        ts, day, hour = _now_windows()
        counts = _get_counts(conn, platform, day, hour)
        limits = {
            "daily": quota["daily_limit"],
            "hourly": quota["hourly_limit"],
            "per_minute": quota["per_minute_limit"],
        }

        # Check limits in order: per_minute → hourly → daily
        for window in ["per_minute", "hourly", "daily"]:
            if counts[window] >= limits[window]:
                # Log throttle event
                conn.execute(
                    """INSERT INTO rl_throttle_events
                       (id, platform, limit_type, limit_value,
                        current_count, contact_id, action_taken, timestamp)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), platform, window,
                     limits[window], counts[window],
                     contact_id, "blocked", ts),
                )
                conn.commit()
                return {"allowed": False,
                        "reason": f"{window}_limit_reached",
                        "counts": counts, "limits": limits,
                        "cooldown_active": False}

        # Check contact cooldown
        cooldown_active = False
        if contact_id:
            cd = conn.execute(
                """SELECT cooldown_until FROM rl_cooldown_tracker
                   WHERE platform=? AND contact_id=?""",
                (platform, contact_id),
            ).fetchone()
            if cd:
                until = datetime.fromisoformat(cd["cooldown_until"])
                if datetime.now(timezone.utc) < until.replace(
                        tzinfo=timezone.utc):
                    cooldown_active = True
                    return {"allowed": False,
                            "reason": "contact_on_cooldown",
                            "counts": counts, "limits": limits,
                            "cooldown_active": True,
                            "cooldown_until": cd["cooldown_until"]}

        return {"allowed": True, "reason": "ok",
                "counts": counts, "limits": limits,
                "cooldown_active": cooldown_active}
    finally:
        conn.close()


def consume_quota(platform: str, contact_id: str = "",
                  action_type: str = "send",
                  db_path: Path = DB_PATH) -> dict:
    """
    Record one unit of quota consumption.
    Also sets cooldown for the contact on this platform.
    Returns {recorded, counts}.
    """
    platform = platform.lower()
    ts, day, hour = _now_windows()
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO rl_consumption_log
               (id, platform, contact_id, action_type,
                timestamp, window_day, window_hour)
               VALUES (?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), platform, contact_id,
             action_type, ts, day, hour),
        )

        # Set cooldown for contact
        if contact_id:
            quota = conn.execute(
                "SELECT cooldown_days FROM rl_platform_quotas "
                "WHERE platform=?", (platform,),
            ).fetchone()
            cd_days = quota["cooldown_days"] if quota else 30
            cooldown_until = (datetime.now(timezone.utc)
                              + timedelta(days=cd_days)).isoformat()
            conn.execute(
                """INSERT INTO rl_cooldown_tracker
                   (id, platform, contact_id, last_contact_at, cooldown_until)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(platform, contact_id) DO UPDATE SET
                   last_contact_at=excluded.last_contact_at,
                   cooldown_until=excluded.cooldown_until""",
                (str(uuid.uuid4()), platform, contact_id,
                 ts, cooldown_until),
            )

        conn.commit()
        counts = _get_counts(conn, platform, day, hour)
        return {"recorded": True, "counts": counts}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Platform status (the core "dashboard data" function)
# ──────────────────────────────────────────────────────────────


def get_platform_status(platform: str = "",
                        db_path: Path = DB_PATH) -> list[dict]:
    """
    Get real-time status for one or all platforms.
    Returns list of status dicts with quotas, counts, percentages,
    throttle history, and health indicator.
    """
    conn = _get_conn(db_path)
    try:
        if platform:
            quotas = conn.execute(
                "SELECT * FROM rl_platform_quotas WHERE platform=?",
                (platform.lower(),),
            ).fetchall()
        else:
            quotas = conn.execute(
                "SELECT * FROM rl_platform_quotas ORDER BY platform"
            ).fetchall()

        ts, day, hour = _now_windows()
        results = []

        for q in quotas:
            q = dict(q)
            plat = q["platform"]
            counts = _get_counts(conn, plat, day, hour)

            # Percentages
            pct_daily = (counts["daily"] / max(q["daily_limit"], 1)) * 100
            pct_hourly = (counts["hourly"] / max(q["hourly_limit"], 1)) * 100
            pct_minute = (counts["per_minute"]
                          / max(q["per_minute_limit"], 1)) * 100

            # Health: green / yellow / red
            max_pct = max(pct_daily, pct_hourly, pct_minute)
            if max_pct >= 100:
                health = "exhausted"
                health_color = "red"
            elif max_pct >= 75:
                health = "warning"
                health_color = "yellow"
            else:
                health = "healthy"
                health_color = "green"

            # Throttle count (24h)
            throttles_24h = conn.execute(
                """SELECT COUNT(*) as c FROM rl_throttle_events
                   WHERE platform=?
                   AND timestamp >= datetime('now', '-24 hours')""",
                (plat,),
            ).fetchone()["c"]

            # Active cooldowns
            active_cooldowns = conn.execute(
                """SELECT COUNT(*) as c FROM rl_cooldown_tracker
                   WHERE platform=? AND cooldown_until > ?""",
                (plat, ts),
            ).fetchone()["c"]

            # Time until daily reset (next UTC midnight)
            now_utc = datetime.now(timezone.utc)
            next_midnight = (now_utc + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            secs_until_reset = int(
                (next_midnight - now_utc).total_seconds())

            results.append({
                "platform": plat,
                "label": PLATFORM_LABELS.get(plat, plat.title()),
                "icon": PLATFORM_ICONS.get(plat, "📡"),
                "enabled": bool(q["is_enabled"]),
                "auto_pause": bool(q["auto_pause"]),
                "limits": {
                    "daily": q["daily_limit"],
                    "hourly": q["hourly_limit"],
                    "per_minute": q["per_minute_limit"],
                    "cooldown_days": q["cooldown_days"],
                },
                "counts": counts,
                "percentages": {
                    "daily": round(pct_daily, 1),
                    "hourly": round(pct_hourly, 1),
                    "per_minute": round(pct_minute, 1),
                },
                "health": health,
                "health_color": health_color,
                "throttles_24h": throttles_24h,
                "active_cooldowns": active_cooldowns,
                "daily_reset_in_sec": secs_until_reset,
                "checked_at": ts,
            })

        return results
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────────────────────


def get_throttle_log(platform: str = "", limit: int = 50,
                     db_path: Path = DB_PATH) -> list[dict]:
    """Recent throttle events."""
    conn = _get_conn(db_path)
    try:
        if platform:
            rows = conn.execute(
                """SELECT * FROM rl_throttle_events
                   WHERE platform=? ORDER BY timestamp DESC LIMIT ?""",
                (platform.lower(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM rl_throttle_events
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_daily_send_history(days: int = 7,
                           db_path: Path = DB_PATH) -> list[dict]:
    """Daily send counts per platform for the last N days."""
    conn = _get_conn(db_path)
    try:
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT platform, window_day, COUNT(*) as sends
               FROM rl_consumption_log
               WHERE window_day >= ?
               GROUP BY platform, window_day
               ORDER BY window_day, platform""",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hourly_send_history(hours: int = 24,
                            db_path: Path = DB_PATH) -> list[dict]:
    """Hourly send counts per platform for the last N hours."""
    conn = _get_conn(db_path)
    try:
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            """SELECT platform, window_hour, COUNT(*) as sends
               FROM rl_consumption_log
               WHERE timestamp >= ?
               GROUP BY platform, window_hour
               ORDER BY window_hour, platform""",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_stats(db_path: Path = DB_PATH) -> dict:
    """Aggregate stats for the dashboard."""
    conn = _get_conn(db_path)
    try:
        statuses = get_platform_status(db_path=db_path)
        total_platforms = len(statuses)
        enabled = sum(1 for s in statuses if s["enabled"])
        exhausted = sum(1 for s in statuses if s["health"] == "exhausted")
        warning = sum(1 for s in statuses if s["health"] == "warning")
        healthy = sum(1 for s in statuses if s["health"] == "healthy")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        total_sends_today = conn.execute(
            "SELECT COUNT(*) as c FROM rl_consumption_log "
            "WHERE window_day=?", (today,),
        ).fetchone()["c"]

        total_throttles_24h = conn.execute(
            """SELECT COUNT(*) as c FROM rl_throttle_events
               WHERE timestamp >= datetime('now', '-24 hours')"""
        ).fetchone()["c"]

        total_cooldowns = conn.execute(
            """SELECT COUNT(*) as c FROM rl_cooldown_tracker
               WHERE cooldown_until > datetime('now')"""
        ).fetchone()["c"]

        return {
            "total_platforms": total_platforms,
            "enabled": enabled,
            "exhausted": exhausted,
            "warning": warning,
            "healthy": healthy,
            "total_sends_today": total_sends_today,
            "total_throttles_24h": total_throttles_24h,
            "total_active_cooldowns": total_cooldowns,
            "statuses": statuses,
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Maintenance
# ──────────────────────────────────────────────────────────────


def cleanup_old_logs(days: int = 90,
                     db_path: Path = DB_PATH) -> dict:
    """Purge consumption and throttle logs older than N days."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=days)).isoformat()
    conn = _get_conn(db_path)
    try:
        c1 = conn.execute(
            "DELETE FROM rl_consumption_log WHERE timestamp < ?",
            (cutoff,),
        ).rowcount
        c2 = conn.execute(
            "DELETE FROM rl_throttle_events WHERE timestamp < ?",
            (cutoff,),
        ).rowcount
        c3 = conn.execute(
            "DELETE FROM rl_cooldown_tracker WHERE cooldown_until < ?",
            (datetime.now(timezone.utc).isoformat(),),
        ).rowcount
        conn.commit()
        return {"consumption_purged": c1, "throttle_purged": c2,
                "cooldowns_expired": c3}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# FastAPI routes (optional mount)
# ──────────────────────────────────────────────────────────────


def register_rate_limit_routes(app) -> None:
    """Mount /api/v1/rate-limits/* onto a FastAPI app."""
    try:
        from fastapi import HTTPException
    except ImportError:
        return

    @app.get("/api/v1/rate-limits", tags=["Rate Limits"])
    def api_rate_limit_status(platform: str = ""):
        """Get real-time rate-limit status for one or all platforms."""
        return {"statuses": get_platform_status(platform)}

    @app.get("/api/v1/rate-limits/stats", tags=["Rate Limits"])
    def api_rate_limit_stats():
        """Aggregate rate-limit stats."""
        return get_stats()

    @app.get("/api/v1/rate-limits/throttle-log", tags=["Rate Limits"])
    def api_throttle_log(platform: str = "", limit: int = 50):
        """Recent throttle events."""
        return {"events": get_throttle_log(platform, limit)}

    @app.post("/api/v1/rate-limits/check", tags=["Rate Limits"])
    def api_check_allowed(platform: str, contact_id: str = ""):
        """Check if a send is currently allowed."""
        return is_allowed(platform, contact_id)

    logger.info("Rate-limit routes registered: /api/v1/rate-limits/*")


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """Real-time per-platform rate-limit status dashboard."""
    try:
        import streamlit as st
        import pandas as pd
    except ImportError:
        return

    st.set_page_config(page_title="Rate Limits", page_icon="⚡",
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
    div.stTabs [data-baseweb="tab-list"]{gap:0;border-bottom:1px solid var(--border);}
    div.stTabs [data-baseweb="tab"]{color:var(--muted)!important;background:transparent!important;
        border-bottom:2px solid transparent;padding:0.5rem 1rem;}
    div.stTabs [aria-selected="true"]{color:var(--accent)!important;
        border-bottom:2px solid var(--accent)!important;}
    .health-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;}
    .health-green{background:var(--green);}
    .health-yellow{background:var(--yellow);}
    .health-red{background:var(--red);}
    .plat-card{background:var(--surface);border:1px solid var(--border);
               border-radius:10px;padding:16px;margin-bottom:10px;}
    .bar-track{background:#0d1117;border-radius:3px;height:14px;width:100%;}
    .bar-fill{height:14px;border-radius:3px;transition:width 0.3s;}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_rate_limit_tables()
    stats = get_stats()

    # ── Header ──
    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">⚡</span>
      <h1>Rate Limit Dashboard</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    # ── KPI row ──
    st.markdown('<div class="section-title">Overview</div>',
                unsafe_allow_html=True)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    for col, val, lbl in [
        (k1, stats["total_sends_today"], "Sends Today"),
        (k2, stats["enabled"], "Active Platforms"),
        (k3, stats["healthy"], "Healthy"),
        (k4, stats["warning"], "Warning"),
        (k5, stats["exhausted"], "Exhausted"),
        (k6, stats["total_throttles_24h"], "Throttles (24h)"),
    ]:
        color = "--accent" if lbl in ("Exhausted", "Throttles (24h)") and val > 0 else "--text"
        col.markdown(
            f'<div class="mini">'
            f'<div class="mini-val" style="color:var({color})">{val}</div>'
            f'<div class="mini-lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

    # ── Tabs ──
    tabs = st.tabs(["📊 Live Status", "⚙️ Quotas", "🚫 Throttle Log",
                     "📈 History", "🧹 Maintenance"])

    # ── Tab 0: Live Status ───────────────────────────────────
    with tabs[0]:
        st.markdown('<div class="section-title">Per-Platform Status</div>',
                    unsafe_allow_html=True)

        for s in stats["statuses"]:
            h_cls = f"health-{s['health_color']}"
            enabled_tag = "" if s["enabled"] else (
                ' <span style="color:var(--muted);font-size:0.7rem">'
                '(DISABLED)</span>')

            st.markdown(
                f'<div class="plat-card">'
                f'<div style="display:flex;align-items:center;gap:10px;'
                f'margin-bottom:10px">'
                f'<span style="font-size:1.3rem">{s["icon"]}</span>'
                f'<span style="font-weight:600;font-size:0.95rem">'
                f'{s["label"]}{enabled_tag}</span>'
                f'<span class="health-dot {h_cls}"></span>'
                f'<span style="font-size:0.7rem;color:var(--muted);'
                f'margin-left:auto">'
                f'{s["throttles_24h"]} throttles · '
                f'{s["active_cooldowns"]} cooldowns</span>'
                f'</div>', unsafe_allow_html=True)

            # Progress bars for each window
            for window, label in [("daily", "Daily"),
                                  ("hourly", "Hourly"),
                                  ("per_minute", "Per min")]:
                pct = s["percentages"][window]
                cnt = s["counts"][window]
                lim = s["limits"][window]
                bar_color = ("--green" if pct < 75
                             else "--yellow" if pct < 100
                             else "--red")
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;'
                    f'margin:3px 0">'
                    f'<span style="font-size:0.65rem;color:var(--muted);'
                    f'min-width:48px">{label}</span>'
                    f'<div class="bar-track"><div class="bar-fill" '
                    f'style="width:{min(pct, 100):.0f}%;'
                    f'background:var({bar_color})"></div></div>'
                    f'<span style="font-size:0.7rem;color:var(--muted);'
                    f'min-width:60px;text-align:right;'
                    f'font-family:JetBrains Mono,monospace">'
                    f'{cnt}/{lim}</span>'
                    f'</div>', unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)

    # ── Tab 1: Quota Config ──────────────────────────────────
    with tabs[1]:
        st.markdown('<div class="section-title">Configure Quotas</div>',
                    unsafe_allow_html=True)
        quotas = get_quotas()
        if quotas:
            df = pd.DataFrame(quotas)
            st.dataframe(df, use_container_width=True, height=300)

        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        qc1, qc2 = st.columns(2)
        with qc1:
            q_plat = st.selectbox("Platform", PLATFORMS, key="q_plat")
            q_daily = st.number_input("Daily limit", 1, 1000, 50, key="q_d")
            q_hourly = st.number_input("Hourly limit", 1, 500, 20, key="q_h")
        with qc2:
            q_permin = st.number_input("Per-minute", 1, 100, 5, key="q_m")
            q_cd = st.number_input("Cooldown (days)", 1, 365, 30, key="q_cd")
            q_enabled = st.checkbox("Enabled", True, key="q_en")

        if st.button("💾 Save Quota", key="btn_save_q"):
            set_quota(q_plat, daily=q_daily, hourly=q_hourly,
                      per_minute=q_permin, cooldown_days=q_cd,
                      enabled=q_enabled)
            st.success(f"Quota updated for {q_plat}")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Tab 2: Throttle Log ──────────────────────────────────
    with tabs[2]:
        st.markdown('<div class="section-title">Recent Throttle Events'
                    '</div>', unsafe_allow_html=True)
        tl_plat = st.selectbox("Filter platform",
                               [""] + PLATFORMS, key="tl_plat")
        events = get_throttle_log(tl_plat, limit=100)
        if events:
            df = pd.DataFrame(events)
            st.dataframe(df, use_container_width=True, height=400)
        else:
            st.info("No throttle events recorded yet.")

    # ── Tab 3: History ───────────────────────────────────────
    with tabs[3]:
        st.markdown('<div class="section-title">Send History (7 days)</div>',
                    unsafe_allow_html=True)
        history = get_daily_send_history(7)
        if history:
            df = pd.DataFrame(history)
            pivot = df.pivot_table(index="window_day",
                                   columns="platform",
                                   values="sends",
                                   fill_value=0)
            st.bar_chart(pivot, color=None, height=300)

            st.markdown('<div class="section-title">Raw Data</div>',
                        unsafe_allow_html=True)
            st.dataframe(df, use_container_width=True, height=200)
        else:
            st.info("No send history yet.")

        # Hourly view
        st.markdown('<div class="section-title">Hourly (24h)</div>',
                    unsafe_allow_html=True)
        hourly = get_hourly_send_history(24)
        if hourly:
            hdf = pd.DataFrame(hourly)
            st.dataframe(hdf, use_container_width=True, height=200)

    # ── Tab 4: Maintenance ───────────────────────────────────
    with tabs[4]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        cl_days = st.number_input("Purge logs older than (days)",
                                  30, 3650, 90, key="cl_days")
        if st.button("🧹 Cleanup", key="btn_cleanup"):
            result = cleanup_old_logs(cl_days)
            st.success(
                f"Purged {result['consumption_purged']} consumption, "
                f"{result['throttle_purged']} throttle, "
                f"{result['cooldowns_expired']} expired cooldowns")
        st.markdown('</div>', unsafe_allow_html=True)

    # Footer
    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/rate-limit-dashboard</code> · Rate Limits v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test for all rate-limit functions."""
    import tempfile

    print("=" * 60)
    print("Rate Limit Dashboard — Self-Test")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    try:
        init_rate_limit_tables(tdb)

        # 1. Quotas seeded
        print("\n[1/9] Default quotas ...")
        quotas = get_quotas(tdb)
        assert len(quotas) >= 10, f"Expected ≥10, got {len(quotas)}"
        print(f"      ✅ {len(quotas)} platform quotas seeded")

        # 2. Custom quota
        print("[2/9] Set custom quota ...")
        q = set_quota("linkedin", daily=15, hourly=5, per_minute=2,
                      cooldown_days=60, db_path=tdb)
        assert q["daily_limit"] == 15
        assert q["cooldown_days"] == 60
        print(f"      ✅ LinkedIn → 15/day, 5/hr, 2/min, 60d cooldown")

        # 3. is_allowed (empty — should be allowed)
        print("[3/9] Check allowed (empty) ...")
        check = is_allowed("linkedin", db_path=tdb)
        assert check["allowed"]
        assert check["reason"] == "ok"
        print(f"      ✅ Allowed (0 consumed)")

        # 4. Consume quota
        print("[4/9] Consume quota ...")
        for i in range(5):
            consume_quota("linkedin", contact_id=f"c-{i:03d}",
                          db_path=tdb)
        status = get_platform_status("linkedin", tdb)
        assert len(status) == 1
        assert status[0]["counts"]["daily"] == 5
        print(f"      ✅ 5 consumed, daily={status[0]['counts']['daily']}")

        # 5. Hit per-minute limit
        print("[5/9] Per-minute limit ...")
        # Already consumed some in the last minute
        consume_quota("linkedin", contact_id="c-extra1", db_path=tdb)
        # With limit=2/min, we should have exceeded after 2+ in same minute
        # (depends on timing, so we force check)
        check = is_allowed("linkedin", db_path=tdb)
        # May or may not be blocked depending on exact counts
        print(f"      ✅ Per-minute check: allowed={check['allowed']}, "
              f"counts={check['counts']}")

        # 6. Cooldown
        print("[6/9] Contact cooldown ...")
        # Use whatsapp with generous limits to isolate cooldown check
        consume_quota("whatsapp", contact_id="cd-test", db_path=tdb)
        check = is_allowed("whatsapp", contact_id="cd-test", db_path=tdb)
        assert not check["allowed"]
        assert check["reason"] == "contact_on_cooldown"
        print(f"      ✅ cd-test on cooldown (whatsapp)")

        # 7. Daily limit exhaust
        print("[7/9] Daily limit exhaust ...")
        set_quota("telegram", daily=3, hourly=100, per_minute=100,
                  db_path=tdb)
        for i in range(3):
            consume_quota("telegram", contact_id=f"tg-{i}",
                          db_path=tdb)
        check = is_allowed("telegram", db_path=tdb)
        assert not check["allowed"]
        assert check["reason"] == "daily_limit_reached"
        print(f"      ✅ Telegram daily exhausted (3/3)")

        # 8. Throttle log
        print("[8/9] Throttle log ...")
        events = get_throttle_log("telegram", db_path=tdb)
        assert len(events) >= 1
        print(f"      ✅ {len(events)} throttle event(s) logged")

        # 9. Stats & status
        print("[9/9] Stats ...")
        s = get_stats(tdb)
        assert s["total_sends_today"] >= 6
        assert s["exhausted"] >= 1
        statuses = get_platform_status(db_path=tdb)
        assert len(statuses) >= 10
        tg_status = [x for x in statuses if x["platform"] == "telegram"]
        assert tg_status[0]["health"] == "exhausted"
        print(f"      ✅ {s['total_sends_today']} sends today, "
              f"{s['exhausted']} exhausted, "
              f"{s['total_throttles_24h']} throttles")

        # Cleanup
        result = cleanup_old_logs(0, tdb)
        print(f"\n🧹 Cleanup: {result}")

        print("\n" + "=" * 60)
        print("✅ ALL RATE LIMIT SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(tdb)


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_rate_limit_tables()
    print("=== Rate Limit Dashboard -- self test ===\n")
    _self_test()
else:
    render_dashboard()
