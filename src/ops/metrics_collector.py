"""
Metrics & Observability — Birthday Wishes Agent v10.0
======================================================
In-process metrics registry with counters, gauges, and histograms.
Collects live data from all module tables, exports in JSON and
Prometheus text format, and provides a /health endpoint.

Usage:
  python metrics_collector.py                # self-test
  python metrics_collector.py collect        # print current metrics
  python metrics_collector.py health         # print health status
  python metrics_collector.py prometheus     # Prometheus text format

Integration:
  from metrics_collector import collect, health_check
  from metrics_collector import register_metrics_routes
  register_metrics_routes(app)  # mounts /api/v1/metrics + /api/v1/health

Author : Fahim (SadManFahIm)
Branch : feature/observability (→ 10.0)
"""

import sqlite3
import json
import os
import time
import logging
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.getenv("BWA_DB_PATH", "agent_history.db"))

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Metric types
# ──────────────────────────────────────────────────────────────


class Counter:
    """Monotonically increasing counter."""

    def __init__(self, name: str, help_text: str, labels: dict = None):
        self.name = name
        self.help = help_text
        self.labels = labels or {}
        self.value = 0
        self._lock = threading.Lock()

    def inc(self, amount: int = 1):
        with self._lock:
            self.value += amount

    def set_value(self, val: int):
        with self._lock:
            self.value = val

    def to_dict(self) -> dict:
        return {"name": self.name, "type": "counter",
                "help": self.help, "value": self.value,
                "labels": self.labels}

    def to_prometheus(self) -> str:
        labels_str = ""
        if self.labels:
            pairs = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
            labels_str = "{" + pairs + "}"
        return (f"# HELP {self.name} {self.help}\n"
                f"# TYPE {self.name} counter\n"
                f"{self.name}{labels_str} {self.value}\n")


class Gauge:
    """Point-in-time value that can go up and down."""

    def __init__(self, name: str, help_text: str, labels: dict = None):
        self.name = name
        self.help = help_text
        self.labels = labels or {}
        self.value = 0.0
        self._lock = threading.Lock()

    def set_value(self, val: float):
        with self._lock:
            self.value = val

    def to_dict(self) -> dict:
        return {"name": self.name, "type": "gauge",
                "help": self.help, "value": self.value,
                "labels": self.labels}

    def to_prometheus(self) -> str:
        labels_str = ""
        if self.labels:
            pairs = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
            labels_str = "{" + pairs + "}"
        return (f"# HELP {self.name} {self.help}\n"
                f"# TYPE {self.name} gauge\n"
                f"{self.name}{labels_str} {self.value}\n")


class Histogram:
    """Tracks distribution of values with configurable buckets."""

    DEFAULT_BUCKETS = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5,
                       1.0, 2.5, 5.0, 10.0]

    def __init__(self, name: str, help_text: str,
                 buckets: list = None):
        self.name = name
        self.help = help_text
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self.bucket_counts = {b: 0 for b in self.buckets}
        self.bucket_counts[float("inf")] = 0
        self.sum_value = 0.0
        self.count = 0
        self._lock = threading.Lock()

    def observe(self, value: float):
        with self._lock:
            self.sum_value += value
            self.count += 1
            for b in self.buckets:
                if value <= b:
                    self.bucket_counts[b] += 1
            self.bucket_counts[float("inf")] += 1

    def to_dict(self) -> dict:
        return {"name": self.name, "type": "histogram",
                "help": self.help, "count": self.count,
                "sum": round(self.sum_value, 4),
                "buckets": {str(k): v for k, v in self.bucket_counts.items()
                            if k != float("inf")},
                "inf": self.bucket_counts[float("inf")]}

    def to_prometheus(self) -> str:
        lines = [f"# HELP {self.name} {self.help}",
                 f"# TYPE {self.name} histogram"]
        cumulative = 0
        for b in self.buckets:
            cumulative += self.bucket_counts[b]
            lines.append(f'{self.name}_bucket{{le="{b}"}} {cumulative}')
        cumulative += self.bucket_counts.get(float("inf"), 0) - cumulative
        lines.append(f'{self.name}_bucket{{le="+Inf"}} '
                     f'{self.bucket_counts[float("inf")]}')
        lines.append(f"{self.name}_sum {self.sum_value:.4f}")
        lines.append(f"{self.name}_count {self.count}")
        return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────────────────────
# Metrics Registry
# ──────────────────────────────────────────────────────────────

# Counters
wishes_sent_total = Counter(
    "bwa_wishes_sent_total",
    "Total birthday wishes sent")
login_attempts_total = Counter(
    "bwa_login_attempts_total",
    "Total login attempts (success + failed)")
login_success_total = Counter(
    "bwa_login_success_total",
    "Successful login count")
login_failed_total = Counter(
    "bwa_login_failed_total",
    "Failed login count")
push_sent_total = Counter(
    "bwa_push_sent_total",
    "Total push notifications sent")
push_failed_total = Counter(
    "bwa_push_failed_total",
    "Failed push notifications")
errors_total = Counter(
    "bwa_errors_total",
    "Total critical errors across all modules")
audit_entries_total = Counter(
    "bwa_audit_entries_total",
    "Total audit trail entries")
consent_granted_total = Counter(
    "bwa_consent_granted_total",
    "Total consent grants")
erasure_total = Counter(
    "bwa_erasure_total",
    "Total right-to-forget erasures")

# Gauges
active_devices = Gauge(
    "bwa_active_devices",
    "Currently active push notification devices")
active_users = Gauge(
    "bwa_active_users",
    "Active user accounts")
contacts_total = Gauge(
    "bwa_contacts_total",
    "Total contacts in contact_tier")
vip_contacts = Gauge(
    "bwa_vip_contacts",
    "VIP contact count")

# Per-platform rate limit gauges (created dynamically)
PLATFORMS = ["linkedin", "whatsapp", "telegram", "email", "twitter",
             "instagram", "slack", "facebook", "wechat", "line"]

rate_limit_gauges: dict[str, Gauge] = {}
for _plat in PLATFORMS:
    rate_limit_gauges[_plat] = Gauge(
        f"bwa_rate_limit_pct",
        f"Daily rate limit consumption percentage",
        labels={"platform": _plat})

# Histograms
wish_generation_duration = Histogram(
    "bwa_wish_generation_duration_seconds",
    "Time to generate a birthday wish",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0])
api_request_duration = Histogram(
    "bwa_api_request_duration_seconds",
    "API request processing time",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0])

ALL_COUNTERS = [
    wishes_sent_total, login_attempts_total,
    login_success_total, login_failed_total,
    push_sent_total, push_failed_total,
    errors_total, audit_entries_total,
    consent_granted_total, erasure_total,
]
ALL_GAUGES = [active_devices, active_users, contacts_total, vip_contacts]
ALL_HISTOGRAMS = [wish_generation_duration, api_request_duration]


# ──────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────


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


def _safe_count(conn: sqlite3.Connection, query: str,
                params: tuple = ()) -> int:
    try:
        return conn.execute(query, params).fetchone()[0]
    except Exception:
        return 0


# ──────────────────────────────────────────────────────────────
# Collect — gather metrics from all tables
# ──────────────────────────────────────────────────────────────


def collect(db_path: Path = DB_PATH) -> dict:
    """
    Gather current metrics from all module tables.
    Updates the in-process registry and returns a snapshot dict.
    """
    conn = _get_conn(db_path)
    collected_at = datetime.now(timezone.utc).isoformat()

    try:
        # Wishes
        if _table_exists(conn, "wish_outcome_log"):
            wishes_sent_total.set_value(
                _safe_count(conn, "SELECT COUNT(*) FROM wish_outcome_log"))

        # Auth
        if _table_exists(conn, "auth_login_log"):
            login_attempts_total.set_value(
                _safe_count(conn, "SELECT COUNT(*) FROM auth_login_log"))
            login_success_total.set_value(
                _safe_count(conn,
                            "SELECT COUNT(*) FROM auth_login_log "
                            "WHERE success=1"))
            login_failed_total.set_value(
                _safe_count(conn,
                            "SELECT COUNT(*) FROM auth_login_log "
                            "WHERE success=0"))

        if _table_exists(conn, "auth_users"):
            active_users.set_value(
                _safe_count(conn,
                            "SELECT COUNT(*) FROM auth_users "
                            "WHERE is_active=1"))

        # Push
        if _table_exists(conn, "push_notification_log"):
            push_sent_total.set_value(
                _safe_count(conn,
                            "SELECT COUNT(*) FROM push_notification_log "
                            "WHERE status IN ('sent','delivered','opened')"))
            push_failed_total.set_value(
                _safe_count(conn,
                            "SELECT COUNT(*) FROM push_notification_log "
                            "WHERE status='failed'"))

        if _table_exists(conn, "push_devices"):
            active_devices.set_value(
                _safe_count(conn,
                            "SELECT COUNT(*) FROM push_devices "
                            "WHERE is_active=1"))

        # Audit
        if _table_exists(conn, "audit_trail"):
            audit_entries_total.set_value(
                _safe_count(conn, "SELECT COUNT(*) FROM audit_trail"))
            errors_total.set_value(
                _safe_count(conn,
                            "SELECT COUNT(*) FROM audit_trail "
                            "WHERE severity='critical'"))

        # GDPR
        if _table_exists(conn, "gdpr_consent"):
            consent_granted_total.set_value(
                _safe_count(conn,
                            "SELECT COUNT(*) FROM gdpr_consent "
                            "WHERE granted=1"))

        if _table_exists(conn, "gdpr_audit_log"):
            erasure_total.set_value(
                _safe_count(conn,
                            "SELECT COUNT(*) FROM gdpr_audit_log "
                            "WHERE action='right_to_forget'"))

        # Contacts
        if _table_exists(conn, "contact_tier"):
            contacts_total.set_value(
                _safe_count(conn, "SELECT COUNT(*) FROM contact_tier"))

        if _table_exists(conn, "vip_contacts"):
            vip_contacts.set_value(
                _safe_count(conn, "SELECT COUNT(*) FROM vip_contacts"))

        # Rate limits per platform
        if (_table_exists(conn, "rl_platform_quotas")
                and _table_exists(conn, "rl_consumption_log")):
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for plat in PLATFORMS:
                quota = conn.execute(
                    "SELECT daily_limit FROM rl_platform_quotas "
                    "WHERE platform=?", (plat,),
                ).fetchone()
                if quota:
                    used = _safe_count(
                        conn,
                        "SELECT COUNT(*) FROM rl_consumption_log "
                        "WHERE platform=? AND window_day=?",
                        (plat, today))
                    pct = round((used / max(quota[0], 1)) * 100, 1)
                    rate_limit_gauges[plat].set_value(pct)

    finally:
        conn.close()

    # Build result
    metrics = {
        "collected_at": collected_at,
        "counters": {c.name: c.to_dict() for c in ALL_COUNTERS},
        "gauges": {g.name: g.to_dict() for g in ALL_GAUGES},
        "rate_limits": {p: g.to_dict() for p, g in rate_limit_gauges.items()},
        "histograms": {h.name: h.to_dict() for h in ALL_HISTOGRAMS},
    }
    return metrics


# ──────────────────────────────────────────────────────────────
# Export: Prometheus text format
# ──────────────────────────────────────────────────────────────


def to_prometheus(db_path: Path = DB_PATH) -> str:
    """Collect and export all metrics in Prometheus text format."""
    collect(db_path)
    lines = []
    for c in ALL_COUNTERS:
        lines.append(c.to_prometheus())
    for g in ALL_GAUGES:
        lines.append(g.to_prometheus())
    for p, g in rate_limit_gauges.items():
        lines.append(g.to_prometheus())
    for h in ALL_HISTOGRAMS:
        lines.append(h.to_prometheus())
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────────────────────

HEALTH_MODULES = [
    ("audit_trail", "audit_log", "timestamp"),
    ("push_notification_log", "push_notifications", "created_at"),
    ("auth_login_log", "jwt_auth", "timestamp"),
    ("rl_consumption_log", "rate_limit_dashboard", "timestamp"),
    ("briefing_log", "morning_briefing", "generated_at"),
]


def health_check(db_path: Path = DB_PATH) -> dict:
    """
    Check system health:
    - DB connection
    - Each module's last operation within 24h
    Returns {"status", "checks", "checked_at"}.
    """
    checks = {}
    overall = "healthy"

    # DB connection
    try:
        conn = _get_conn(db_path)
        conn.execute("SELECT 1")
        checks["database"] = {"status": "ok", "detail": str(db_path)}
    except Exception as exc:
        checks["database"] = {"status": "fail", "detail": str(exc)}
        overall = "unhealthy"
        return {"status": overall, "checks": checks,
                "checked_at": datetime.now(timezone.utc).isoformat()}

    # Module last-activity checks
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        for table, module, ts_col in HEALTH_MODULES:
            if not _table_exists(conn, table):
                checks[module] = {"status": "unknown",
                                  "detail": f"table {table} not found"}
                continue

            last = conn.execute(
                f"SELECT MAX({ts_col}) FROM {table}"
            ).fetchone()[0]

            if not last:
                checks[module] = {"status": "idle",
                                  "detail": "no data yet"}
            elif last >= cutoff:
                checks[module] = {"status": "ok",
                                  "detail": f"last: {last[:19]}"}
            else:
                checks[module] = {"status": "stale",
                                  "detail": f"last: {last[:19]} (>24h)"}
                if overall == "healthy":
                    overall = "degraded"

        # Wish outcome
        if _table_exists(conn, "wish_outcome_log"):
            wish_count = _safe_count(
                conn, "SELECT COUNT(*) FROM wish_outcome_log")
            checks["wishes"] = {"status": "ok",
                                "detail": f"{wish_count} total wishes"}

        # Contact count
        if _table_exists(conn, "contact_tier"):
            ct = _safe_count(conn, "SELECT COUNT(*) FROM contact_tier")
            checks["contacts"] = {"status": "ok" if ct > 0 else "empty",
                                  "detail": f"{ct} contacts"}

    finally:
        conn.close()

    # Check for any failures
    for check in checks.values():
        if check["status"] == "fail":
            overall = "unhealthy"
            break

    return {"status": overall, "checks": checks,
            "checked_at": datetime.now(timezone.utc).isoformat()}


# ──────────────────────────────────────────────────────────────
# FastAPI routes
# ──────────────────────────────────────────────────────────────


def register_metrics_routes(app) -> None:
    """Mount /api/v1/metrics and /api/v1/health onto a FastAPI app."""
    try:
        from fastapi.responses import PlainTextResponse
    except ImportError:
        return

    @app.get("/api/v1/metrics", tags=["Observability"])
    def api_metrics_json():
        """Current metrics as JSON."""
        return collect()

    @app.get("/api/v1/metrics/prometheus", tags=["Observability"],
             response_class=PlainTextResponse)
    def api_metrics_prometheus():
        """Prometheus text format for Grafana scraping."""
        return to_prometheus()

    @app.get("/api/v1/health", tags=["Observability"])
    def api_health():
        """System health check."""
        result = health_check()
        return result

    logger.info("Metrics routes registered: /api/v1/metrics, /api/v1/health")


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """Observability dashboard with live metrics."""
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Observability", page_icon="📡",
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
    .health-ok{color:var(--green);font-weight:600;}
    .health-degraded{color:var(--yellow);font-weight:600;}
    .health-unhealthy{color:var(--red);font-weight:600;}
    .bar-track{background:#0d1117;border-radius:3px;height:12px;width:100%;}
    .bar-fill{height:12px;border-radius:3px;}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📡</span>
      <h1>Observability</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    metrics = collect()
    health = health_check()

    # KPIs
    st.markdown('<div class="section-title">Key Metrics</div>',
                unsafe_allow_html=True)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    for col, name, lbl in [
        (k1, "bwa_wishes_sent_total", "Wishes Sent"),
        (k2, "bwa_push_sent_total", "Push Sent"),
        (k3, "bwa_login_success_total", "Logins"),
        (k4, "bwa_errors_total", "Errors"),
        (k5, "bwa_active_devices", "Devices"),
        (k6, "bwa_contacts_total", "Contacts"),
    ]:
        val = 0
        if name in metrics["counters"]:
            val = metrics["counters"][name]["value"]
        elif name in metrics["gauges"]:
            val = int(metrics["gauges"][name]["value"])
        col.markdown(
            f'<div class="mini"><div class="mini-val">{val}</div>'
            f'<div class="mini-lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

    tabs = st.tabs(["🏥 Health", "📊 Counters & Gauges",
                     "⚡ Rate Limits", "📡 Prometheus"])

    # Health tab
    with tabs[0]:
        st.markdown('<div class="section-title">System Health</div>',
                    unsafe_allow_html=True)
        h_cls = f"health-{health['status']}"
        h_icon = {"healthy": "🟢", "degraded": "🟡",
                  "unhealthy": "🔴"}.get(health["status"], "⚪")
        st.markdown(
            f'<div class="c-card"><span class="{h_cls}">'
            f'{h_icon} {health["status"].upper()}</span> — '
            f'{health["checked_at"][:19]}</div>',
            unsafe_allow_html=True)

        for module, check in health["checks"].items():
            icon = {"ok": "✅", "fail": "❌", "stale": "⚠️",
                    "idle": "💤", "unknown": "❓",
                    "empty": "📭"}.get(check["status"], "❓")
            st.markdown(
                f'<div class="c-card">{icon} <strong>{module}</strong>'
                f' — {check["detail"]}</div>',
                unsafe_allow_html=True)

    # Counters & Gauges tab
    with tabs[1]:
        st.markdown('<div class="section-title">Counters</div>',
                    unsafe_allow_html=True)
        cc1, cc2 = st.columns(2)
        counters = list(metrics["counters"].values())
        for i, c in enumerate(counters):
            col = cc1 if i % 2 == 0 else cc2
            col.markdown(
                f'<div class="c-card">'
                f'<span style="font-weight:600;font-size:0.85rem">'
                f'{c["name"]}</span><br>'
                f'<span style="font-size:1.3rem;font-weight:700;'
                f'color:var(--accent)">{c["value"]}</span><br>'
                f'<span style="font-size:0.7rem;color:var(--muted)">'
                f'{c["help"]}</span></div>',
                unsafe_allow_html=True)

        st.markdown('<div class="section-title">Gauges</div>',
                    unsafe_allow_html=True)
        gc1, gc2 = st.columns(2)
        gauges = list(metrics["gauges"].values())
        for i, g in enumerate(gauges):
            col = gc1 if i % 2 == 0 else gc2
            col.markdown(
                f'<div class="c-card">'
                f'<span style="font-weight:600;font-size:0.85rem">'
                f'{g["name"]}</span><br>'
                f'<span style="font-size:1.3rem;font-weight:700;'
                f'color:var(--blue)">{int(g["value"])}</span><br>'
                f'<span style="font-size:0.7rem;color:var(--muted)">'
                f'{g["help"]}</span></div>',
                unsafe_allow_html=True)

    # Rate Limits tab
    with tabs[2]:
        st.markdown('<div class="section-title">Platform Rate Limits'
                    '</div>', unsafe_allow_html=True)
        for plat, data in metrics["rate_limits"].items():
            pct = data["value"]
            bar_color = ("--green" if pct < 75
                         else "--yellow" if pct < 100
                         else "--red")
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;'
                f'margin:4px 0">'
                f'<span style="min-width:90px;font-size:0.8rem;'
                f'font-weight:500">{plat}</span>'
                f'<div class="bar-track"><div class="bar-fill" '
                f'style="width:{min(pct, 100):.0f}%;'
                f'background:var({bar_color})"></div></div>'
                f'<span style="font-size:0.7rem;color:var(--muted);'
                f'min-width:45px;text-align:right;'
                f'font-family:JetBrains Mono,monospace">'
                f'{pct:.0f}%</span></div>',
                unsafe_allow_html=True)

    # Prometheus tab
    with tabs[3]:
        st.markdown('<div class="section-title">Prometheus Format</div>',
                    unsafe_allow_html=True)
        prom_text = to_prometheus()
        st.code(prom_text[:3000], language="text")
        st.markdown(
            f'<p style="font-size:0.7rem;color:var(--muted)">'
            f'Scrape endpoint: <code>GET /api/v1/metrics/prometheus</code>'
            f'</p>', unsafe_allow_html=True)

    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/observability</code> · Observability v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test."""
    import tempfile
    import uuid

    print("=" * 60)
    print("Metrics & Observability — Self-Test")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    try:
        # Create tables and seed data
        conn = sqlite3.connect(tdb)
        conn.executescript("""
            CREATE TABLE wish_outcome_log (
                id TEXT PRIMARY KEY, contact_id TEXT,
                sent_at TEXT, replied INTEGER DEFAULT 0);
            CREATE TABLE auth_login_log (
                id TEXT PRIMARY KEY, user_id TEXT,
                username TEXT, success INTEGER,
                timestamp TEXT);
            CREATE TABLE auth_users (
                id TEXT PRIMARY KEY, username TEXT,
                is_active INTEGER DEFAULT 1);
            CREATE TABLE push_notification_log (
                id TEXT PRIMARY KEY, user_id TEXT,
                status TEXT, created_at TEXT);
            CREATE TABLE push_devices (
                id TEXT PRIMARY KEY, user_id TEXT,
                is_active INTEGER DEFAULT 1);
            CREATE TABLE audit_trail (
                id TEXT PRIMARY KEY, timestamp TEXT,
                action TEXT, severity TEXT DEFAULT 'info',
                module TEXT, summary TEXT, row_hash TEXT);
            CREATE TABLE gdpr_consent (
                id TEXT PRIMARY KEY, contact_id TEXT,
                granted INTEGER);
            CREATE TABLE gdpr_audit_log (
                id TEXT PRIMARY KEY, action TEXT,
                timestamp TEXT);
            CREATE TABLE contact_tier (
                contact_id TEXT PRIMARY KEY, contact_name TEXT,
                current_tier TEXT, tier_score REAL);
            CREATE TABLE vip_contacts (
                contact_id TEXT PRIMARY KEY);
            CREATE TABLE rl_platform_quotas (
                platform TEXT PRIMARY KEY, daily_limit INTEGER);
            CREATE TABLE rl_consumption_log (
                id TEXT PRIMARY KEY, platform TEXT,
                window_day TEXT, timestamp TEXT);
            CREATE TABLE briefing_log (
                id TEXT PRIMARY KEY, generated_at TEXT);
        """)

        now = datetime.now(timezone.utc).isoformat()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Seed wishes
        for i in range(15):
            conn.execute("INSERT INTO wish_outcome_log VALUES (?,?,?,?)",
                         (str(uuid.uuid4()), f"c-{i}", now, i % 3))
        # Seed logins
        for i in range(20):
            conn.execute(
                "INSERT INTO auth_login_log VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), "u1", "admin", 1 if i < 17 else 0, now))
        conn.execute("INSERT INTO auth_users VALUES (?,?,?)",
                     ("u1", "admin", 1))
        # Seed push
        for i in range(10):
            conn.execute(
                "INSERT INTO push_notification_log VALUES (?,?,?,?)",
                (str(uuid.uuid4()), "u1",
                 "sent" if i < 8 else "failed", now))
        conn.execute("INSERT INTO push_devices VALUES (?,?,?)",
                     ("d1", "u1", 1))
        # Seed audit
        for i in range(25):
            sev = "critical" if i < 3 else "info"
            conn.execute(
                "INSERT INTO audit_trail VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), now, "test", sev, "test",
                 "test event", uuid.uuid4().hex[:16]))
        # Seed contacts
        for i in range(8):
            conn.execute(
                "INSERT INTO contact_tier VALUES (?,?,?,?)",
                (f"c-{i}", f"Contact {i}", "Friend", 7.0 + i))
        conn.execute("INSERT INTO vip_contacts VALUES (?)", ("c-0",))
        conn.execute("INSERT INTO vip_contacts VALUES (?)", ("c-1",))
        # Seed GDPR
        for i in range(5):
            conn.execute("INSERT INTO gdpr_consent VALUES (?,?,?)",
                         (str(uuid.uuid4()), f"c-{i}", 1))
        conn.execute("INSERT INTO gdpr_audit_log VALUES (?,?,?)",
                     (str(uuid.uuid4()), "right_to_forget", now))
        # Seed rate limits
        conn.execute("INSERT INTO rl_platform_quotas VALUES (?,?)",
                     ("linkedin", 25))
        for i in range(10):
            conn.execute(
                "INSERT INTO rl_consumption_log VALUES (?,?,?,?)",
                (str(uuid.uuid4()), "linkedin", today, now))
        # Seed briefing
        conn.execute("INSERT INTO briefing_log VALUES (?,?)",
                     (str(uuid.uuid4()), now))
        conn.commit()
        conn.close()

        # 1. Collect
        print("\n[1/6] Collect metrics ...")
        metrics = collect(tdb)
        assert metrics["counters"]["bwa_wishes_sent_total"]["value"] == 15
        assert metrics["counters"]["bwa_login_attempts_total"]["value"] == 20
        assert metrics["counters"]["bwa_login_success_total"]["value"] == 17
        assert metrics["counters"]["bwa_login_failed_total"]["value"] == 3
        assert metrics["counters"]["bwa_push_sent_total"]["value"] == 8
        assert metrics["counters"]["bwa_push_failed_total"]["value"] == 2
        assert metrics["counters"]["bwa_errors_total"]["value"] == 3
        assert metrics["gauges"]["bwa_active_devices"]["value"] == 1
        assert metrics["gauges"]["bwa_contacts_total"]["value"] == 8
        assert metrics["gauges"]["bwa_vip_contacts"]["value"] == 2
        print("      ✅ All counters + gauges correct")

        # 2. Rate limit gauges
        print("[2/6] Rate limit gauges ...")
        rl = metrics["rate_limits"]["linkedin"]
        assert rl["value"] == 40.0  # 10/25 = 40%
        print(f"      ✅ LinkedIn: {rl['value']}%")

        # 3. Prometheus export
        print("[3/6] Prometheus format ...")
        prom = to_prometheus(tdb)
        assert "# HELP bwa_wishes_sent_total" in prom
        assert "# TYPE bwa_wishes_sent_total counter" in prom
        assert "bwa_wishes_sent_total 15" in prom
        assert "bwa_active_devices 1" in prom
        assert 'platform="linkedin"' in prom
        print(f"      ✅ Valid Prometheus text ({len(prom)} chars)")

        # 4. Health check
        print("[4/6] Health check ...")
        h = health_check(tdb)
        assert h["status"] in ("healthy", "degraded", "unhealthy")
        assert h["checks"]["database"]["status"] == "ok"
        assert h["checks"]["contacts"]["status"] == "ok"
        assert h["checks"]["contacts"]["detail"] == "8 contacts"
        print(f"      ✅ Status: {h['status']}, "
              f"{len(h['checks'])} checks")

        # 5. Histogram
        print("[5/6] Histogram ...")
        wish_generation_duration.observe(0.5)
        wish_generation_duration.observe(1.2)
        wish_generation_duration.observe(0.08)
        assert wish_generation_duration.count == 3
        assert wish_generation_duration.sum_value > 1.7
        hd = wish_generation_duration.to_dict()
        assert hd["type"] == "histogram"
        hp = wish_generation_duration.to_prometheus()
        assert "bwa_wish_generation_duration_seconds_count 3" in hp
        print(f"      ✅ 3 observations, sum={wish_generation_duration.sum_value:.2f}s")

        # 6. Counter / Gauge thread safety
        print("[6/6] Thread safety ...")
        test_counter = Counter("test_counter", "test")
        threads = []
        for _ in range(10):
            t = threading.Thread(target=lambda: [test_counter.inc()
                                                 for _ in range(100)])
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        assert test_counter.value == 1000
        print(f"      ✅ 10 threads × 100 increments = {test_counter.value}")

        print("\n" + "=" * 60)
        print("✅ ALL OBSERVABILITY SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(tdb)


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "collect":
            print(json.dumps(collect(), indent=2, default=str))
        elif cmd == "health":
            h = health_check()
            icon = {"healthy": "🟢", "degraded": "🟡",
                    "unhealthy": "🔴"}.get(h["status"], "⚪")
            print(f"{icon} {h['status'].upper()}")
            for mod, chk in h["checks"].items():
                s_icon = {"ok": "✅", "fail": "❌", "stale": "⚠️",
                          "idle": "💤"}.get(chk["status"], "❓")
                print(f"  {s_icon} {mod}: {chk['detail']}")
        elif cmd == "prometheus":
            print(to_prometheus())
        else:
            print(f"Unknown: {cmd}")
            print("Usage: python metrics_collector.py "
                  "[collect|health|prometheus]")
    else:
        print("=== Metrics & Observability -- self test ===\n")
        _self_test()
else:
    render_dashboard()
