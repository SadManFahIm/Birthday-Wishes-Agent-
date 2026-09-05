"""
Error Budget Dashboard — Birthday Wishes Agent v10.0
======================================================
SRE-style error budgets per module. Tracks error rates,
budget consumption, burn rates, and exhaustion predictions
from the audit_trail and gdpr_audit_log tables.

Usage:
  python error_budget.py                # self-test
  python error_budget.py status         # print module health
  python error_budget.py check          # check + alert if budget low

Integration:
  from error_budget import get_module_health, check_alerts
  health = get_module_health()
  alerts = check_alerts()

Author : Fahim (SadManFahIm)
Branch : feature/error-budget (→ 10.0)
"""

import sqlite3
import json
import math
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.getenv("BWA_DB_PATH", "agent_history.db"))

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Default budget configuration
# ──────────────────────────────────────────────────────────────

# All known modules the agent uses
MODULES = [
    "agent", "autonomous_agent", "morning_briefing",
    "push_notifications", "audit_log", "jwt_auth",
    "gdpr_compliance", "rate_limit_dashboard", "churn_predictor",
    "roi_forecasting", "wish_performance_predictor",
    "interest_graph", "vector_memory", "conversation_summary",
    "crm_sync", "google_calendar_sync", "notion_sync",
    "email_outreach", "engagement_calendar", "model_config",
    "langgraph_workflow", "mcp_server",
]

DEFAULT_ERROR_BUDGET_PCT = 1.0     # 1% error rate allowed
DEFAULT_BUDGET_WINDOW_DAYS = 30
ALERT_THRESHOLD_PCT = 50.0         # alert when 50% budget consumed
CRITICAL_THRESHOLD_PCT = 80.0      # critical when 80% consumed


# ──────────────────────────────────────────────────────────────
# Schema — minimal config table
# ──────────────────────────────────────────────────────────────


def init_budget_tables(db_path: Path = DB_PATH) -> None:
    """Create budget config table if not present."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS error_budget_config (
            module          TEXT PRIMARY KEY,
            budget_pct      REAL NOT NULL DEFAULT 1.0,
            window_days     INTEGER NOT NULL DEFAULT 30,
            alert_threshold REAL NOT NULL DEFAULT 50.0,
            enabled         INTEGER NOT NULL DEFAULT 1,
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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


# ──────────────────────────────────────────────────────────────
# Budget configuration
# ──────────────────────────────────────────────────────────────


def set_budget(module: str, budget_pct: float = DEFAULT_ERROR_BUDGET_PCT,
               window_days: int = DEFAULT_BUDGET_WINDOW_DAYS,
               alert_threshold: float = ALERT_THRESHOLD_PCT,
               db_path: Path = DB_PATH) -> dict:
    """Set error budget for a module."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO error_budget_config
               (module, budget_pct, window_days, alert_threshold, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(module) DO UPDATE SET
               budget_pct=excluded.budget_pct,
               window_days=excluded.window_days,
               alert_threshold=excluded.alert_threshold,
               updated_at=excluded.updated_at""",
            (module, budget_pct, window_days, alert_threshold,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"module": module, "budget_pct": budget_pct,
                "window_days": window_days}
    finally:
        conn.close()


def get_budget_config(module: str,
                      db_path: Path = DB_PATH) -> dict:
    """Get budget config for a module (or defaults)."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM error_budget_config WHERE module=?",
            (module,),
        ).fetchone()
        if row:
            return dict(row)
        return {
            "module": module,
            "budget_pct": DEFAULT_ERROR_BUDGET_PCT,
            "window_days": DEFAULT_BUDGET_WINDOW_DAYS,
            "alert_threshold": ALERT_THRESHOLD_PCT,
            "enabled": 1,
        }
    finally:
        conn.close()


def get_all_configs(db_path: Path = DB_PATH) -> list[dict]:
    """Get all configured budgets."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM error_budget_config ORDER BY module"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Error counting — reads from audit_trail + gdpr_audit_log
# ──────────────────────────────────────────────────────────────


def _count_events(conn: sqlite3.Connection, module: str,
                  since: str, severity: str = "") -> dict:
    """Count total and error events for a module since a timestamp."""
    total = 0
    errors = 0

    # Source 1: audit_trail
    if _table_exists(conn, "audit_trail"):
        if module:
            total += conn.execute(
                "SELECT COUNT(*) FROM audit_trail "
                "WHERE module=? AND timestamp >= ?",
                (module, since),
            ).fetchone()[0]
            errors += conn.execute(
                "SELECT COUNT(*) FROM audit_trail "
                "WHERE module=? AND severity='critical' AND timestamp >= ?",
                (module, since),
            ).fetchone()[0]
        else:
            total += conn.execute(
                "SELECT COUNT(*) FROM audit_trail WHERE timestamp >= ?",
                (since,),
            ).fetchone()[0]
            errors += conn.execute(
                "SELECT COUNT(*) FROM audit_trail "
                "WHERE severity='critical' AND timestamp >= ?",
                (since,),
            ).fetchone()[0]

    # Source 2: gdpr_audit_log (maps to gdpr_compliance module)
    if _table_exists(conn, "gdpr_audit_log") and module in (
            "gdpr_compliance", ""):
        gdpr_total = conn.execute(
            "SELECT COUNT(*) FROM gdpr_audit_log WHERE timestamp >= ?",
            (since,),
        ).fetchone()[0]
        total += gdpr_total
        # GDPR audit log doesn't have severity, count action='right_to_forget'
        # failures as errors (if any fail)

    return {"total": total, "errors": errors}


def get_error_counts(module: str = "",
                     db_path: Path = DB_PATH) -> dict:
    """Get error counts for 24h, 7d, 30d windows."""
    conn = _get_conn(db_path)
    now = datetime.now(timezone.utc)
    try:
        windows = {}
        for label, days in [("24h", 1), ("7d", 7), ("30d", 30)]:
            since = (now - timedelta(days=days)).isoformat()
            windows[label] = _count_events(conn, module, since)
        return windows
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Budget calculations
# ──────────────────────────────────────────────────────────────


def calculate_budget(module: str,
                     db_path: Path = DB_PATH) -> dict:
    """
    Calculate error budget status for one module.
    Returns: budget_pct, error_rate, budget_consumed_pct,
             burn_rate, time_to_exhaustion, health.
    """
    config = get_budget_config(module, db_path)
    window_days = config["window_days"]
    budget_pct = config["budget_pct"]
    alert_threshold = config.get("alert_threshold", ALERT_THRESHOLD_PCT)

    conn = _get_conn(db_path)
    now = datetime.now(timezone.utc)
    try:
        since = (now - timedelta(days=window_days)).isoformat()
        counts = _count_events(conn, module, since)

        total = counts["total"]
        errors = counts["errors"]

        # Error rate
        error_rate = (errors / max(total, 1)) * 100

        # Budget consumed
        budget_consumed_pct = (error_rate / max(budget_pct, 0.01)) * 100

        # Burn rate: how fast are we consuming budget?
        # Compare last 24h rate vs the window average
        since_24h = (now - timedelta(days=1)).isoformat()
        counts_24h = _count_events(conn, module, since_24h)
        rate_24h = (counts_24h["errors"] / max(counts_24h["total"], 1)) * 100
        rate_window = error_rate

        burn_rate = rate_24h / max(rate_window, 0.001) if rate_window > 0 else (
            0.0 if rate_24h == 0 else float("inf"))

        # Time to exhaustion (days at current 24h rate)
        budget_remaining_pct = max(0, 100 - budget_consumed_pct)
        if rate_24h > 0 and budget_remaining_pct > 0:
            # Proportion of budget left / daily consumption rate
            daily_consumption = (rate_24h / max(budget_pct, 0.01)) * 100
            if daily_consumption > 0:
                days_left = (budget_remaining_pct / daily_consumption
                             ) * window_days
                time_to_exhaustion = max(0, round(days_left, 1))
            else:
                time_to_exhaustion = float("inf")
        elif rate_24h == 0:
            time_to_exhaustion = float("inf")
        else:
            time_to_exhaustion = 0

        # Health status
        if budget_consumed_pct >= CRITICAL_THRESHOLD_PCT:
            health = "critical"
        elif budget_consumed_pct >= alert_threshold:
            health = "warning"
        else:
            health = "healthy"

        return {
            "module": module,
            "budget_pct": budget_pct,
            "window_days": window_days,
            "total_events": total,
            "error_events": errors,
            "error_rate_pct": round(error_rate, 3),
            "budget_consumed_pct": round(min(budget_consumed_pct, 100), 1),
            "budget_remaining_pct": round(max(budget_remaining_pct, 0), 1),
            "burn_rate": round(burn_rate, 2) if burn_rate != float("inf") else "∞",
            "time_to_exhaustion_days": time_to_exhaustion if time_to_exhaustion != float("inf") else "∞",
            "health": health,
            "errors_24h": counts_24h["errors"],
            "total_24h": counts_24h["total"],
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Module health grid
# ──────────────────────────────────────────────────────────────


def get_module_health(db_path: Path = DB_PATH) -> list[dict]:
    """Calculate budget status for ALL modules."""
    results = []
    for module in MODULES:
        budget = calculate_budget(module, db_path)
        results.append(budget)
    results.sort(key=lambda x: -(x["budget_consumed_pct"]
                                  if isinstance(x["budget_consumed_pct"],
                                                (int, float)) else 0))
    return results


def check_alerts(db_path: Path = DB_PATH) -> list[dict]:
    """Return modules that have breached their alert threshold."""
    alerts = []
    for module in MODULES:
        budget = calculate_budget(module, db_path)
        if budget["health"] in ("warning", "critical"):
            alerts.append({
                "module": module,
                "health": budget["health"],
                "budget_consumed_pct": budget["budget_consumed_pct"],
                "error_rate_pct": budget["error_rate_pct"],
                "errors_24h": budget["errors_24h"],
                "time_to_exhaustion_days": budget["time_to_exhaustion_days"],
            })
    return alerts


def get_error_timeline(module: str = "", limit: int = 50,
                       db_path: Path = DB_PATH) -> list[dict]:
    """Recent error events from audit_trail."""
    conn = _get_conn(db_path)
    try:
        if not _table_exists(conn, "audit_trail"):
            return []

        if module:
            rows = conn.execute(
                """SELECT timestamp, module, action, summary, severity
                   FROM audit_trail
                   WHERE severity='critical' AND module=?
                   ORDER BY timestamp DESC LIMIT ?""",
                (module, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT timestamp, module, action, summary, severity
                   FROM audit_trail WHERE severity='critical'
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_daily_error_trend(days: int = 30,
                          db_path: Path = DB_PATH) -> list[dict]:
    """Daily error counts for burn-down chart."""
    conn = _get_conn(db_path)
    try:
        if not _table_exists(conn, "audit_trail"):
            return []
        since = (datetime.now(timezone.utc)
                 - timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT DATE(timestamp) as day,
                      COUNT(*) as total,
                      SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) as errors
               FROM audit_trail WHERE timestamp >= ?
               GROUP BY day ORDER BY day""",
            (since,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_stats(db_path: Path = DB_PATH) -> dict:
    """Overall error budget stats."""
    health_list = get_module_health(db_path)
    healthy = sum(1 for h in health_list if h["health"] == "healthy")
    warning = sum(1 for h in health_list if h["health"] == "warning")
    critical = sum(1 for h in health_list if h["health"] == "critical")
    total_errors_24h = sum(h["errors_24h"] for h in health_list)
    total_events_24h = sum(h["total_24h"] for h in health_list)

    return {
        "total_modules": len(MODULES),
        "healthy": healthy,
        "warning": warning,
        "critical": critical,
        "total_errors_24h": total_errors_24h,
        "total_events_24h": total_events_24h,
        "overall_health": ("critical" if critical > 0
                           else "warning" if warning > 0
                           else "healthy"),
    }


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """Error budget monitoring dashboard."""
    try:
        import streamlit as st
        import pandas as pd
    except ImportError:
        return

    st.set_page_config(page_title="Error Budget", page_icon="🎯",
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
        border:1px solid var(--border);color:var(--text);border-radius:8px;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div.stTabs [data-baseweb="tab-list"]{gap:0;border-bottom:1px solid var(--border);}
    div.stTabs [data-baseweb="tab"]{color:var(--muted)!important;background:transparent!important;
        border-bottom:2px solid transparent;padding:0.5rem 1rem;}
    div.stTabs [aria-selected="true"]{color:var(--accent)!important;
        border-bottom:2px solid var(--accent)!important;}
    .health-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;}
    .health-healthy{background:var(--green);}
    .health-warning{background:var(--yellow);}
    .health-critical{background:var(--red);}
    .mod-card{background:var(--surface);border:1px solid var(--border);
              border-radius:10px;padding:12px 14px;margin-bottom:6px;}
    .bar-track{background:#0d1117;border-radius:3px;height:12px;width:100%;}
    .bar-fill{height:12px;border-radius:3px;}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    </style>
    """, unsafe_allow_html=True)

    init_budget_tables()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🎯</span>
      <h1>Error Budget Dashboard</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    stats = get_stats()

    # KPIs
    st.markdown('<div class="section-title">Overview</div>',
                unsafe_allow_html=True)
    overall_color = {"healthy": "--green", "warning": "--yellow",
                     "critical": "--red"}.get(stats["overall_health"], "--muted")
    k1, k2, k3, k4, k5 = st.columns(5)
    for col, val, lbl in [
        (k1, stats["healthy"], "Healthy"),
        (k2, stats["warning"], "Warning"),
        (k3, stats["critical"], "Critical"),
        (k4, stats["total_errors_24h"], "Errors (24h)"),
        (k5, stats["total_modules"], "Modules"),
    ]:
        col.markdown(
            f'<div class="mini"><div class="mini-val">{val}</div>'
            f'<div class="mini-lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

    tabs = st.tabs(["🏥 Health Grid", "📈 Trends", "🔴 Errors",
                     "⚙️ Config"])

    # Health Grid tab
    with tabs[0]:
        st.markdown('<div class="section-title">Module Health</div>',
                    unsafe_allow_html=True)
        health_list = get_module_health()

        for h in health_list:
            dot_cls = f"health-{h['health']}"
            consumed = h["budget_consumed_pct"]
            bar_color = ("--green" if h["health"] == "healthy"
                         else "--yellow" if h["health"] == "warning"
                         else "--red")
            tte = h["time_to_exhaustion_days"]
            tte_str = f"{tte}d" if isinstance(tte, (int, float)) else "∞"

            st.markdown(
                f'<div class="mod-card">'
                f'<div style="display:flex;align-items:center;gap:8px;'
                f'margin-bottom:6px">'
                f'<span class="health-dot {dot_cls}"></span>'
                f'<span style="font-weight:600;font-size:0.85rem;'
                f'min-width:200px">{h["module"]}</span>'
                f'<span style="font-size:0.7rem;color:var(--muted)">'
                f'{h["errors_24h"]} err/24h · '
                f'rate {h["error_rate_pct"]}% · '
                f'exhaust {tte_str}</span></div>'
                f'<div style="display:flex;align-items:center;gap:8px">'
                f'<span style="font-size:0.6rem;color:var(--muted);'
                f'min-width:60px">Budget</span>'
                f'<div class="bar-track"><div class="bar-fill" '
                f'style="width:{min(consumed, 100):.0f}%;'
                f'background:var({bar_color})"></div></div>'
                f'<span style="font-size:0.7rem;color:var(--muted);'
                f'min-width:45px;text-align:right;'
                f'font-family:JetBrains Mono,monospace">'
                f'{consumed:.0f}%</span></div>'
                f'</div>',
                unsafe_allow_html=True)

    # Trends tab
    with tabs[1]:
        st.markdown('<div class="section-title">Daily Error Trend (30d)'
                    '</div>', unsafe_allow_html=True)
        trend = get_daily_error_trend()
        if trend:
            df = pd.DataFrame(trend)
            df.columns = ["Date", "Total Events", "Errors"]
            st.bar_chart(df.set_index("Date")["Errors"],
                         color="#f85149", height=250)
            st.dataframe(df, use_container_width=True, height=200)
        else:
            st.info("No audit data yet for trend analysis.")

    # Errors tab
    with tabs[2]:
        st.markdown('<div class="section-title">Recent Critical Errors'
                    '</div>', unsafe_allow_html=True)
        e_mod = st.selectbox("Filter module",
                             [""] + MODULES, key="e_mod")
        timeline = get_error_timeline(e_mod, 50)
        if timeline:
            df = pd.DataFrame(timeline)
            st.dataframe(df, use_container_width=True, height=400)
        else:
            st.info("No critical errors found.")

    # Config tab
    with tabs[3]:
        st.markdown('<div class="section-title">Budget Configuration'
                    '</div>', unsafe_allow_html=True)
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            c_mod = st.selectbox("Module", MODULES, key="c_mod")
            c_pct = st.number_input("Budget (%)", 0.1, 100.0,
                                    DEFAULT_ERROR_BUDGET_PCT,
                                    step=0.5, key="c_pct")
        with c2:
            c_window = st.number_input("Window (days)", 1, 365,
                                       DEFAULT_BUDGET_WINDOW_DAYS,
                                       key="c_win")
            c_alert = st.number_input("Alert threshold (%)", 10.0,
                                      100.0, ALERT_THRESHOLD_PCT,
                                      step=5.0, key="c_alert")
        if st.button("💾 Save", key="btn_save"):
            set_budget(c_mod, c_pct, c_window, c_alert)
            st.success(f"Budget set: {c_mod} → {c_pct}% over {c_window}d")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        configs = get_all_configs()
        if configs:
            st.markdown('<div class="section-title">Saved Configs</div>',
                        unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(configs),
                         use_container_width=True, height=200)

    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/error-budget</code> · Error Budget v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test."""
    import tempfile
    import uuid

    print("=" * 60)
    print("Error Budget Dashboard — Self-Test")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    try:
        init_budget_tables(tdb)

        # Create audit_trail table for testing
        conn = sqlite3.connect(tdb)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                action TEXT NOT NULL, category TEXT DEFAULT 'system',
                severity TEXT DEFAULT 'info', actor TEXT DEFAULT 'system',
                actor_type TEXT DEFAULT 'system', entity_type TEXT,
                entity_id TEXT, contact_id TEXT, session_id TEXT,
                ip_hash TEXT, module TEXT, summary TEXT NOT NULL,
                details TEXT, before_snapshot TEXT, after_snapshot TEXT,
                metadata TEXT, prev_hash TEXT, row_hash TEXT NOT NULL
            );
        """)

        # Seed test events
        now = datetime.now(timezone.utc)
        events = []
        # 100 normal events across modules
        for i in range(100):
            mod = MODULES[i % len(MODULES)]
            ts = (now - timedelta(hours=i)).isoformat()
            events.append((
                str(uuid.uuid4()), ts, "system_event", "system",
                "info", "system", "system", None, None, None, None,
                None, mod, f"Normal event {i}", None, None, None,
                None, None, uuid.uuid4().hex[:16]))

        # 5 critical errors for push_notifications
        for i in range(5):
            ts = (now - timedelta(hours=i * 2)).isoformat()
            events.append((
                str(uuid.uuid4()), ts, "system_alert", "system",
                "critical", "system", "system", None, None, None,
                None, None, "push_notifications",
                f"Push delivery failed: timeout #{i}", None, None,
                None, None, None, uuid.uuid4().hex[:16]))

        # 2 critical errors for crm_sync
        for i in range(2):
            ts = (now - timedelta(days=i)).isoformat()
            events.append((
                str(uuid.uuid4()), ts, "system_alert", "system",
                "critical", "system", "system", None, None, None,
                None, None, "crm_sync",
                f"CRM sync failed #{i}", None, None, None,
                None, None, uuid.uuid4().hex[:16]))

        conn.executemany(
            "INSERT INTO audit_trail VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            events)
        conn.commit()
        conn.close()

        # 1. Budget config
        print("\n[1/8] Budget configuration ...")
        set_budget("push_notifications", 2.0, 30, 50.0, tdb)
        cfg = get_budget_config("push_notifications", tdb)
        assert cfg["budget_pct"] == 2.0
        assert cfg["window_days"] == 30
        print("      ✅ Budget set and retrieved")

        # 2. Error counts
        print("[2/8] Error counts ...")
        counts = get_error_counts("push_notifications", tdb)
        assert counts["24h"]["errors"] >= 1
        assert counts["30d"]["errors"] == 5
        print(f"      ✅ push: {counts['24h']['errors']} err/24h, "
              f"{counts['30d']['errors']} err/30d")

        # 3. Budget calculation
        print("[3/8] Budget calculation ...")
        budget = calculate_budget("push_notifications", tdb)
        assert budget["error_events"] == 5
        assert budget["error_rate_pct"] > 0
        assert budget["budget_consumed_pct"] > 0
        assert budget["health"] in ("healthy", "warning", "critical")
        print(f"      ✅ rate={budget['error_rate_pct']}%, "
              f"consumed={budget['budget_consumed_pct']}%, "
              f"health={budget['health']}")

        # 4. Healthy module
        print("[4/8] Healthy module ...")
        budget_h = calculate_budget("agent", tdb)
        assert budget_h["health"] == "healthy"
        assert budget_h["budget_consumed_pct"] == 0
        print(f"      ✅ agent: healthy (0 errors)")

        # 5. Module health grid
        print("[5/8] Health grid ...")
        health = get_module_health(tdb)
        assert len(health) == len(MODULES)
        unhealthy = [h for h in health if h["health"] != "healthy"]
        print(f"      ✅ {len(health)} modules, "
              f"{len(unhealthy)} with issues")

        # 6. Alerts
        print("[6/8] Alerts ...")
        alerts = check_alerts(tdb)
        # push has errors, might trigger depending on rate
        print(f"      ✅ {len(alerts)} alert(s)")

        # 7. Error timeline
        print("[7/8] Error timeline ...")
        timeline = get_error_timeline("push_notifications", db_path=tdb)
        assert len(timeline) == 5
        assert all(e["severity"] == "critical" for e in timeline)
        print(f"      ✅ {len(timeline)} critical events for push")

        # 8. Stats
        print("[8/8] Overall stats ...")
        s = get_stats(tdb)
        assert s["total_modules"] == len(MODULES)
        assert s["total_errors_24h"] >= 1
        assert s["overall_health"] in ("healthy", "warning", "critical")
        print(f"      ✅ {s['healthy']} healthy, {s['warning']} warning, "
              f"{s['critical']} critical")

        print("\n" + "=" * 60)
        print("✅ ALL ERROR BUDGET SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(tdb)


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_budget_tables()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            health = get_module_health()
            for h in health:
                icon = {"healthy": "🟢", "warning": "🟡",
                        "critical": "🔴"}.get(h["health"], "⚪")
                tte = h["time_to_exhaustion_days"]
                tte_str = f"{tte}d" if isinstance(tte, (int, float)) else "∞"
                print(f"  {icon} {h['module']:<30} "
                      f"err={h['error_rate_pct']:>5.2f}%  "
                      f"budget={h['budget_consumed_pct']:>5.1f}%  "
                      f"exhaust={tte_str}")
        elif cmd == "check":
            alerts = check_alerts()
            if alerts:
                print(f"⚠️  {len(alerts)} module(s) over budget threshold:")
                for a in alerts:
                    print(f"  🔴 {a['module']}: "
                          f"{a['budget_consumed_pct']}% consumed, "
                          f"{a['errors_24h']} errors/24h")
            else:
                print("✅ All modules within error budget.")
        else:
            print(f"Unknown: {cmd}")
            print("Usage: python error_budget.py [status|check]")
    else:
        print("=== Error Budget -- self test ===\n")
        _self_test()
else:
    render_dashboard()
