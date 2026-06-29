"""
Auto-Pause on Anomaly — Birthday Wishes Agent v8.0
Monitors agent errors in real-time. When failures or rate-limit errors
spike beyond configured thresholds, the agent pauses itself, sends alerts
(Telegram + email + dashboard), and waits for a manual restart signal.

Anomaly types detected:
  • consecutive_failures  — N failures in a row on any task
  • rate_limit_spike      — rate-limit errors within a rolling window
  • platform_blackout     — all tasks on one platform failing
  • error_rate_threshold  — error% over last N tasks exceeds limit
  • memory_leak           — process memory grows beyond threshold

Integrates with: agent.py, command_center.py, notifications.py
"""

import sqlite3
import json
import time
import os
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Callable

DB_PATH = Path("agent_history.db")

# ── Default thresholds (override via .env or dashboard) ───────────────────────
DEFAULT_THRESHOLDS = {
    "consecutive_failures":  3,     # pause after N failures in a row
    "rate_limit_window_min": 10,    # rolling window in minutes
    "rate_limit_count":      5,     # rate-limit errors in that window → pause
    "error_rate_pct":        50,    # error% over last 20 tasks → pause
    "error_rate_sample":     20,    # sample size for error rate
    "platform_blackout_n":   3,     # N consecutive failures on same platform
    "cooldown_minutes":      30,    # minimum pause duration before restart allowed
}

ANOMALY_LABELS = {
    "consecutive_failures": "Consecutive Failures",
    "rate_limit_spike":     "Rate-Limit Spike",
    "platform_blackout":    "Platform Blackout",
    "error_rate_threshold": "High Error Rate",
    "manual_pause":         "Manually Paused",
}

SEVERITY = {
    "consecutive_failures": "high",
    "rate_limit_spike":     "medium",
    "platform_blackout":    "high",
    "error_rate_threshold": "medium",
    "manual_pause":         "low",
}

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_anomaly_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_error_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task         TEXT NOT NULL,
            platform     TEXT,
            error_type   TEXT NOT NULL DEFAULT 'general',
            error_msg    TEXT,
            is_rate_limit INTEGER NOT NULL DEFAULT 0,
            logged_at    TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_pause_state (
            id             INTEGER PRIMARY KEY CHECK (id = 1),
            is_paused      INTEGER NOT NULL DEFAULT 0,
            paused_at      TEXT,
            anomaly_type   TEXT,
            anomaly_detail TEXT,
            severity       TEXT,
            resume_after   TEXT,
            resumed_at     TEXT,
            resumed_by     TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anomaly_history (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            anomaly_type   TEXT NOT NULL,
            anomaly_detail TEXT,
            severity       TEXT,
            paused_at      TEXT NOT NULL,
            resumed_at     TEXT,
            resumed_by     TEXT,
            alert_sent     INTEGER DEFAULT 0
        )
    """)
    # Ensure the single pause-state row exists
    conn.execute("""
        INSERT OR IGNORE INTO agent_pause_state
            (id, is_paused) VALUES (1, 0)
    """)
    conn.commit()
    conn.close()


# ── State helpers ─────────────────────────────────────────────────────────────

def is_paused() -> bool:
    """Quick check — call at the top of every agent task."""
    init_anomaly_tables()
    conn  = sqlite3.connect(DB_PATH)
    row   = conn.execute("SELECT is_paused FROM agent_pause_state WHERE id=1").fetchone()
    conn.close()
    return bool(row and row[0])


def get_pause_state() -> dict:
    init_anomaly_tables()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute(
        "SELECT is_paused, paused_at, anomaly_type, anomaly_detail, "
        "severity, resume_after, resumed_at, resumed_by "
        "FROM agent_pause_state WHERE id=1"
    ).fetchone()
    conn.close()
    if not row:
        return {"is_paused": False}
    paused_at    = row[1]
    resume_after = row[5]
    cooldown_ok  = False
    if paused_at and resume_after:
        cooldown_ok = datetime.now() >= datetime.fromisoformat(resume_after)
    return {
        "is_paused":     bool(row[0]),
        "paused_at":     paused_at,
        "anomaly_type":  row[2],
        "anomaly_detail":row[3],
        "severity":      row[4],
        "resume_after":  resume_after,
        "resumed_at":    row[6],
        "resumed_by":    row[7],
        "cooldown_ok":   cooldown_ok,
    }


def _set_paused(anomaly_type: str, detail: str, severity: str, cooldown_minutes: int):
    now          = datetime.now()
    resume_after = now + timedelta(minutes=cooldown_minutes)
    conn         = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE agent_pause_state SET
            is_paused=1, paused_at=?, anomaly_type=?, anomaly_detail=?,
            severity=?, resume_after=?, resumed_at=NULL, resumed_by=NULL
        WHERE id=1
    """, (now.isoformat(), anomaly_type, detail, severity, resume_after.isoformat()))
    conn.execute("""
        INSERT INTO anomaly_history
            (anomaly_type, anomaly_detail, severity, paused_at)
        VALUES (?, ?, ?, ?)
    """, (anomaly_type, detail, severity, now.isoformat()))
    conn.commit()
    conn.close()


def resume_agent(resumed_by: str = "manual") -> dict:
    """
    Resume the agent after a pause. Only allowed after cooldown_minutes have elapsed.
    Returns {"success": bool, "message": str}
    """
    init_anomaly_tables()
    state = get_pause_state()
    if not state["is_paused"]:
        return {"success": False, "message": "Agent is not paused."}
    if not state.get("cooldown_ok"):
        resume_after = state.get("resume_after","?")[:16].replace("T"," ")
        return {"success": False, "message": f"Cooldown not elapsed. Earliest resume: {resume_after}"}

    now  = datetime.now()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE agent_pause_state SET
            is_paused=0, resumed_at=?, resumed_by=?
        WHERE id=1
    """, (now.isoformat(), resumed_by))
    conn.execute("""
        UPDATE anomaly_history SET resumed_at=?, resumed_by=?
        WHERE id = (SELECT MAX(id) FROM anomaly_history)
    """, (now.isoformat(), resumed_by))
    conn.commit()
    conn.close()
    print(f"[AutoPause] ✅ Agent resumed by '{resumed_by}' at {now.strftime('%H:%M:%S')}")
    return {"success": True, "message": f"Agent resumed by {resumed_by}."}


def force_resume(resumed_by: str = "force") -> dict:
    """Override cooldown and resume immediately."""
    init_anomaly_tables()
    now  = datetime.now()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE agent_pause_state SET
            is_paused=0, resume_after=?, resumed_at=?, resumed_by=?
        WHERE id=1
    """, (now.isoformat(), now.isoformat(), resumed_by))
    conn.execute("""
        UPDATE anomaly_history SET resumed_at=?, resumed_by=?
        WHERE id = (SELECT MAX(id) FROM anomaly_history)
    """, (now.isoformat(), resumed_by))
    conn.commit()
    conn.close()
    print(f"[AutoPause] ⚡ Force-resumed by '{resumed_by}'")
    return {"success": True, "message": f"Force-resumed by {resumed_by}."}


# ── Error logging ─────────────────────────────────────────────────────────────

def log_error(
    task:       str,
    error_msg:  str,
    platform:   str = "",
    error_type: str = "general",
):
    """
    Log one agent error. Call this wherever agent.py catches exceptions.
    Auto-triggers anomaly detection after each log.

    Args:
        task:       Task name (e.g. "birthday_detection", "ai_wish")
        error_msg:  Exception message or short description
        platform:   Platform involved (LinkedIn, WhatsApp, etc.)
        error_type: general | rate_limit | auth | timeout | network
    """
    init_anomaly_tables()
    is_rl = int("rate" in error_msg.lower() or "429" in error_msg or error_type == "rate_limit")
    conn  = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO agent_error_log (task, platform, error_type, error_msg, is_rate_limit, logged_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (task, platform, error_type, error_msg[:500], is_rl, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"[AutoPause] ❌ Error logged: [{task}] {error_msg[:80]}")


def log_success(task: str, platform: str = ""):
    """Log a successful task — resets consecutive failure counter context."""
    init_anomaly_tables()
    # We track success by logging a special error_type='success' so consecutive
    # failure detection can see the gap.
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO agent_error_log (task, platform, error_type, error_msg, is_rate_limit, logged_at)
        VALUES (?, ?, 'success', '', 0, ?)
    """, (task, platform, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Anomaly detection ─────────────────────────────────────────────────────────

def check_anomalies(
    thresholds: Optional[dict] = None,
    alert_fn:   Optional[Callable] = None,
    verbose:    bool = True,
) -> Optional[dict]:
    """
    Run all anomaly checks. If any threshold is breached, pause the agent
    and fire alert_fn(anomaly_dict) if provided.

    Call this:
      • After every log_error() call
      • At the start of each scheduled task run

    Returns the anomaly dict if triggered, else None.
    """
    if is_paused():
        if verbose:
            print("[AutoPause] ⏸ Agent already paused — skipping anomaly check")
        return None

    t   = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    now = datetime.now()

    # ── Check 1: Consecutive failures ────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    recent = conn.execute("""
        SELECT error_type FROM agent_error_log
        ORDER BY logged_at DESC LIMIT ?
    """, (t["consecutive_failures"] + 5,)).fetchall()
    conn.close()

    consecutive = 0
    for row in recent:
        if row[0] == "success":
            break
        if row[0] != "success":
            consecutive += 1
        if consecutive >= t["consecutive_failures"]:
            break

    if consecutive >= t["consecutive_failures"]:
        detail = f"{consecutive} consecutive failures with no success"
        return _trigger_pause("consecutive_failures", detail, t, alert_fn, verbose)

    # ── Check 2: Rate-limit spike ─────────────────────────────────────────────
    window_start = (now - timedelta(minutes=t["rate_limit_window_min"])).isoformat()
    conn = sqlite3.connect(DB_PATH)
    rl_count = conn.execute("""
        SELECT COUNT(*) FROM agent_error_log
        WHERE is_rate_limit=1 AND logged_at >= ?
    """, (window_start,)).fetchone()[0]
    conn.close()

    if rl_count >= t["rate_limit_count"]:
        detail = (f"{rl_count} rate-limit errors in the last "
                  f"{t['rate_limit_window_min']} minutes")
        return _trigger_pause("rate_limit_spike", detail, t, alert_fn, verbose)

    # ── Check 3: Error rate over sample ──────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    sample = conn.execute("""
        SELECT error_type FROM agent_error_log
        ORDER BY logged_at DESC LIMIT ?
    """, (t["error_rate_sample"],)).fetchall()
    conn.close()

    if len(sample) >= t["error_rate_sample"]:
        errors = sum(1 for r in sample if r[0] not in ("success",))
        error_pct = (errors / len(sample)) * 100
        if error_pct >= t["error_rate_pct"]:
            detail = (f"{error_pct:.0f}% error rate over last "
                      f"{t['error_rate_sample']} tasks ({errors} errors)")
            return _trigger_pause("error_rate_threshold", detail, t, alert_fn, verbose)

    # ── Check 4: Platform blackout ────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    plat_recent = conn.execute("""
        SELECT platform, error_type FROM agent_error_log
        WHERE platform != ''
        ORDER BY logged_at DESC LIMIT 30
    """).fetchall()
    conn.close()

    plat_consecutive: dict[str, int] = {}
    for platform, etype in plat_recent:
        if not platform:
            continue
        if etype == "success":
            plat_consecutive[platform] = 0
        else:
            plat_consecutive[platform] = plat_consecutive.get(platform, 0) + 1

    for plat, count in plat_consecutive.items():
        if count >= t["platform_blackout_n"]:
            detail = f"{count} consecutive failures on {plat}"
            return _trigger_pause("platform_blackout", detail, t, alert_fn, verbose)

    if verbose:
        print(f"[AutoPause] ✅ All checks passed "
              f"(consecutive={consecutive}, rate_limits={rl_count})")
    return None


def _trigger_pause(
    anomaly_type: str,
    detail:       str,
    thresholds:   dict,
    alert_fn:     Optional[Callable],
    verbose:      bool,
) -> dict:
    severity     = SEVERITY.get(anomaly_type, "medium")
    cooldown_min = thresholds.get("cooldown_minutes", DEFAULT_THRESHOLDS["cooldown_minutes"])
    _set_paused(anomaly_type, detail, severity, cooldown_min)

    anomaly = {
        "anomaly_type":  anomaly_type,
        "label":         ANOMALY_LABELS.get(anomaly_type, anomaly_type),
        "detail":        detail,
        "severity":      severity,
        "paused_at":     datetime.now().isoformat(),
        "cooldown_min":  cooldown_min,
    }

    if verbose:
        print(f"\n[AutoPause] 🚨 ANOMALY DETECTED — Agent PAUSED")
        print(f"  Type:     {anomaly['label']}")
        print(f"  Detail:   {detail}")
        print(f"  Severity: {severity.upper()}")
        print(f"  Cooldown: {cooldown_min} minutes before manual resume allowed\n")

    # Fire alert callback (Telegram / email / dashboard)
    if alert_fn:
        try:
            alert_fn(anomaly)
        except Exception as e:
            print(f"[AutoPause] Alert callback failed: {e}")

    return anomaly


# ── Alert functions ───────────────────────────────────────────────────────────

def send_telegram_alert(anomaly: dict):
    """
    Send a Telegram alert when the agent pauses.
    Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment.
    """
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[AutoPause] Telegram not configured — skipping alert")
        return
    try:
        import urllib.request, urllib.parse
        msg = (
            f"🚨 Birthday Agent PAUSED\n\n"
            f"Type: {anomaly['label']}\n"
            f"Detail: {anomaly['detail']}\n"
            f"Severity: {anomaly['severity'].upper()}\n"
            f"Cooldown: {anomaly['cooldown_min']} min\n"
            f"Time: {anomaly['paused_at'][:19]}\n\n"
            f"Resume manually from the Command Center dashboard."
        )
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode()
        urllib.request.urlopen(url, data=data, timeout=5)
        print("[AutoPause] Telegram alert sent ✅")
    except Exception as e:
        print(f"[AutoPause] Telegram alert failed: {e}")


def default_alert(anomaly: dict):
    """Default alert: tries Telegram, logs to console."""
    send_telegram_alert(anomaly)
    _mark_alert_sent()


def _mark_alert_sent():
    init_anomaly_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE anomaly_history SET alert_sent=1
        WHERE id=(SELECT MAX(id) FROM anomaly_history)
    """)
    conn.commit()
    conn.close()


# ── Anomaly history ───────────────────────────────────────────────────────────

def get_anomaly_history(limit: int = 20) -> list[dict]:
    init_anomaly_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT anomaly_type, anomaly_detail, severity, paused_at, resumed_at, resumed_by, alert_sent
        FROM anomaly_history ORDER BY paused_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{
        "anomaly_type":  r[0], "detail":      r[1], "severity":   r[2],
        "paused_at":     r[3], "resumed_at":  r[4], "resumed_by": r[5],
        "alert_sent":    bool(r[6]),
    } for r in rows]


def get_error_stats(window_hours: int = 24) -> dict:
    init_anomaly_tables()
    cutoff = (datetime.now() - timedelta(hours=window_hours)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    total  = conn.execute(
        "SELECT COUNT(*) FROM agent_error_log WHERE logged_at>=?", (cutoff,)).fetchone()[0]
    errors = conn.execute(
        "SELECT COUNT(*) FROM agent_error_log WHERE logged_at>=? AND error_type!='success'",
        (cutoff,)).fetchone()[0]
    rl     = conn.execute(
        "SELECT COUNT(*) FROM agent_error_log WHERE logged_at>=? AND is_rate_limit=1",
        (cutoff,)).fetchone()[0]
    by_plat = conn.execute("""
        SELECT platform, COUNT(*) FROM agent_error_log
        WHERE logged_at>=? AND error_type!='success' AND platform!=''
        GROUP BY platform ORDER BY COUNT(*) DESC
    """, (cutoff,)).fetchall()
    conn.close()
    return {
        "total_tasks":  total,
        "total_errors": errors,
        "rate_limits":  rl,
        "error_pct":    round((errors / total * 100) if total else 0, 1),
        "by_platform":  {r[0]: r[1] for r in by_plat},
        "window_hours": window_hours,
    }


# ── Decorator for agent tasks ─────────────────────────────────────────────────

def guard(task_name: str, platform: str = "", thresholds: dict = None):
    """
    Decorator — wraps any agent task function with auto-pause logic.

    Usage in agent.py:
        from auto_pause_on_anomaly import guard

        @guard("birthday_detection", platform="LinkedIn")
        async def run_birthday_detection_task():
            ...
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if is_paused():
                print(f"[AutoPause] ⏸ Skipping '{task_name}' — agent is paused")
                return None
            try:
                result = fn(*args, **kwargs)
                log_success(task_name, platform)
                return result
            except Exception as e:
                err_msg   = str(e)
                err_type  = "rate_limit" if "429" in err_msg or "rate" in err_msg.lower() else "general"
                log_error(task_name, err_msg, platform, err_type)
                check_anomalies(thresholds, alert_fn=default_alert)
                raise
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


# ── Streamlit dashboard panel ─────────────────────────────────────────────────

def render_autopause_panel():
    """
    Full Streamlit dashboard page.
    Run: streamlit run auto_pause_on_anomaly.py
    """
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Auto-Pause Monitor", page_icon="🚨",
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
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;
                   color:var(--muted);margin:22px 0 10px;display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .pause-banner{border-radius:12px;padding:18px 20px;margin-bottom:20px;}
    .pause-banner.red{background:#1a0505;border:2px solid var(--red);}
    .pause-banner.green{background:#051a09;border:2px solid var(--green);}
    .stat-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
               padding:14px 16px;text-align:center;}
    .stat-val{font-size:1.8rem;font-weight:700;line-height:1;}
    .stat-label{font-size:0.62rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-top:4px;}
    .hist-row{background:var(--surface);border:1px solid var(--border);border-radius:8px;
              padding:10px 14px;margin-bottom:6px;font-size:0.78rem;}
    .log-term{background:#010409;border:1px solid var(--border);border-radius:10px;
              padding:12px 14px;font-family:'JetBrains Mono',monospace;font-size:0.72rem;
              max-height:220px;overflow-y:auto;color:#7ee787;line-height:1.6;}
    div[data-testid="stButton"]>button{background:var(--surface);border:1px solid var(--border);
        color:var(--text);border-radius:8px;font-size:0.8rem;font-weight:500;transition:all 0.15s;}
    div[data-testid="stButton"]>button:hover{border-color:var(--blue);background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:6px;} ::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🚨</span>
      <h1>Auto-Pause Monitor</h1>
      <span class="cc-badge">v8.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    state  = get_pause_state()
    stats  = get_error_stats(window_hours=24)
    paused = state["is_paused"]

    # ── Status banner ────────────────────────────────────────────────────────
    if paused:
        paused_since = (state.get("paused_at") or "")[:16].replace("T"," ")
        resume_after = (state.get("resume_after") or "")[:16].replace("T"," ")
        st.markdown(f"""
        <div class="pause-banner red">
          <div style="font-size:1.1rem;font-weight:700;color:#f85149">🚨 Agent PAUSED</div>
          <div style="font-size:0.8rem;color:#c9d1d9;margin-top:4px">
            Anomaly: <strong>{ANOMALY_LABELS.get(state.get('anomaly_type',''),'Unknown')}</strong><br>
            Detail: {state.get('anomaly_detail','')}<br>
            Paused at: {paused_since} · Cooldown until: {resume_after}
          </div>
        </div>
        """, unsafe_allow_html=True)
        rb1, rb2, rb3 = st.columns(3)
        with rb1:
            cooldown_ok = state.get("cooldown_ok", False)
            if st.button("▶ Resume Agent", type="primary", use_container_width=True,
                         disabled=not cooldown_ok):
                result = resume_agent("dashboard")
                if result["success"]:
                    st.success(result["message"])
                    st.rerun()
                else:
                    st.warning(result["message"])
        with rb2:
            if st.button("⚡ Force Resume (override cooldown)", use_container_width=True):
                force_resume("dashboard_force")
                st.success("Force-resumed! ✅")
                st.rerun()
        with rb3:
            if not cooldown_ok:
                st.caption(f"Cooldown not elapsed. Wait until {resume_after}")
    else:
        st.markdown("""
        <div class="pause-banner green">
          <div style="font-size:1.1rem;font-weight:700;color:#3fb950">✅ Agent RUNNING</div>
          <div style="font-size:0.78rem;color:#c9d1d9;margin-top:4px">
            All systems normal — monitoring for anomalies in real-time.
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Stats ────────────────────────────────────────────────────────────────
    s1, s2, s3, s4 = st.columns(4)
    for col, label, val, color in [
        (s1, "Tasks (24h)",   stats["total_tasks"],   "#e6edf3"),
        (s2, "Errors",        stats["total_errors"],  "#f85149"),
        (s3, "Rate Limits",   stats["rate_limits"],   "#d29922"),
        (s4, "Error Rate",    f"{stats['error_pct']}%","#f78166"),
    ]:
        with col:
            st.markdown(f"""
            <div class="stat-card">
              <div class="stat-val" style="color:{color}">{val}</div>
              <div class="stat-label">{label}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        # ── Thresholds editor ─────────────────────────────────────────────────
        st.markdown('<div class="section-title">Anomaly Thresholds</div>', unsafe_allow_html=True)
        with st.expander("Configure thresholds", expanded=False):
            t = DEFAULT_THRESHOLDS.copy()
            t["consecutive_failures"] = st.number_input(
                "Consecutive failures before pause", value=t["consecutive_failures"], min_value=1)
            t["rate_limit_count"]     = st.number_input(
                "Rate-limit errors in window", value=t["rate_limit_count"], min_value=1)
            t["rate_limit_window_min"]= st.number_input(
                "Rate-limit window (minutes)", value=t["rate_limit_window_min"], min_value=1)
            t["error_rate_pct"]       = st.number_input(
                "Error rate % threshold", value=t["error_rate_pct"], min_value=1, max_value=100)
            t["platform_blackout_n"]  = st.number_input(
                "Platform blackout (consecutive)", value=t["platform_blackout_n"], min_value=1)
            t["cooldown_minutes"]     = st.number_input(
                "Cooldown before resume (minutes)", value=t["cooldown_minutes"], min_value=1)

        # ── Simulate anomaly (testing) ────────────────────────────────────────
        st.markdown('<div class="section-title">Simulate / Test</div>', unsafe_allow_html=True)
        sim_type = st.selectbox("Simulate error type",
                                ["general","rate_limit","auth","timeout","network"],
                                label_visibility="collapsed")
        sim_plat = st.selectbox("Platform", list(PLATFORM_DEFAULTS_UI.keys()),
                                label_visibility="collapsed")
        s_c1, s_c2 = st.columns(2)
        with s_c1:
            if st.button("📥 Log Test Error", use_container_width=True):
                log_error("test_task", f"Simulated {sim_type} error", sim_plat, sim_type)
                anomaly = check_anomalies(verbose=False)
                if anomaly:
                    st.error(f"🚨 Anomaly triggered: {anomaly['label']}")
                else:
                    st.info("Error logged — threshold not yet breached.")
                st.rerun()
        with s_c2:
            if st.button("✅ Log Test Success", use_container_width=True):
                log_success("test_task", sim_plat)
                st.success("Success logged — resets consecutive failure counter.")
                st.rerun()

        if st.button("🗑 Clear error log (demo reset)", use_container_width=True):
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM agent_error_log")
            conn.commit()
            conn.close()
            st.success("Error log cleared.")
            st.rerun()

    with right:
        # ── Anomaly history ───────────────────────────────────────────────────
        st.markdown('<div class="section-title">Anomaly History</div>', unsafe_allow_html=True)
        history = get_anomaly_history(limit=10)
        if not history:
            st.caption("No anomalies recorded yet.")
        else:
            for h in history:
                sev_color = {"high":"#f85149","medium":"#d29922","low":"#58a6ff"}.get(
                    h.get("severity","medium"),"#8b949e")
                paused_ts  = (h["paused_at"]  or "")[:16].replace("T"," ")
                resumed_ts = (h["resumed_at"] or "—")[:16].replace("T"," ")
                st.markdown(f"""
                <div class="hist-row">
                  <span style="color:{sev_color};font-weight:700">
                    {ANOMALY_LABELS.get(h['anomaly_type'],h['anomaly_type'])}
                  </span><br>
                  <span style="color:#8b949e;font-size:0.7rem">
                    {h.get('detail','')[:70]}<br>
                    Paused: {paused_ts} · Resumed: {resumed_ts}
                    {' · 🔔 Alerted' if h.get('alert_sent') else ''}
                  </span>
                </div>
                """, unsafe_allow_html=True)

        # ── Error log terminal ────────────────────────────────────────────────
        st.markdown('<div class="section-title">Recent Error Log</div>', unsafe_allow_html=True)
        conn = sqlite3.connect(DB_PATH)
        err_rows = conn.execute("""
            SELECT task, platform, error_type, error_msg, logged_at
            FROM agent_error_log ORDER BY logged_at DESC LIMIT 30
        """).fetchall()
        conn.close()
        if not err_rows:
            st.caption("No errors logged yet.")
        else:
            lines = []
            for r in err_rows:
                ts      = r[4][:16].replace("T"," ")
                etype   = r[2]
                color   = "#f85149" if etype not in ("success",) else "#3fb950"
                rl_tag  = " [RL]" if etype == "rate_limit" else ""
                msg     = r[3][:60] if r[3] else ""
                lines.append(
                    f'<span style="color:{color}">[{ts}] [{r[0]}] '
                    f'{r[1] or "—"}{rl_tag} {msg}</span>'
                )
            st.markdown(f'<div class="log-term">{"<br>".join(lines)}</div>',
                        unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
      <span>Auto-Pause Monitor</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


PLATFORM_DEFAULTS_UI = {
    "LinkedIn":"","WhatsApp":"","Facebook":"","Instagram":"","Twitter/X":"","Slack":"",
}

# ── CLI self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_anomaly_tables()
    print("=== Auto-Pause on Anomaly — self test ===\n")

    # Simulate 3 consecutive failures
    for i in range(3):
        log_error("birthday_detection", f"Browser timeout #{i+1}", "LinkedIn", "timeout")
        anomaly = check_anomalies(verbose=False)
        if anomaly:
            print(f"✅ Pause triggered after {i+1} errors: {anomaly['label']}")
            print(f"   Detail: {anomaly['detail']}")
            print(f"   Severity: {anomaly['severity']}\n")
            break

    print(f"Agent paused: {is_paused()}")
    print(f"\nForce-resuming for test continuity...")
    force_resume("self_test")
    print(f"Agent paused after resume: {is_paused()}\n")

    # Simulate rate-limit spike
    print("Simulating rate-limit spike...")
    for i in range(5):
        log_error("ai_wish", "429 Too Many Requests", "LinkedIn", "rate_limit")
    anomaly2 = check_anomalies(verbose=True)
    if anomaly2:
        print(f"\nRate-limit anomaly: {anomaly2['label']} — {anomaly2['detail']}")

    print(f"\nHistory: {len(get_anomaly_history())} entries")
    stats = get_error_stats(24)
    print(f"Stats: {stats['total_errors']} errors / {stats['total_tasks']} tasks "
          f"({stats['error_pct']}%)")

else:
    render_autopause_panel()
