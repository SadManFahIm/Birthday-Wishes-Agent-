"""
Unified Command Center — Birthday Wishes Agent v7.0
Single dashboard: platform control, live agent status, manual task triggers, logs & alerts.
"""

import streamlit as st
import sqlite3
import subprocess
import threading
import time
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Command Center",
    page_icon="🎂",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Inject custom CSS ─────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Dark command-room palette */
:root {
    --bg:        #0d1117;
    --surface:   #161b22;
    --border:    #30363d;
    --accent:    #f78166;
    --green:     #3fb950;
    --yellow:    #d29922;
    --red:       #f85149;
    --blue:      #58a6ff;
    --muted:     #8b949e;
    --text:      #e6edf3;
}

.stApp { background: var(--bg); color: var(--text); }

/* Header bar */
.cc-header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 18px 0 10px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 24px;
}
.cc-header h1 {
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin: 0;
    color: var(--text);
}
.cc-badge {
    background: var(--accent);
    color: #fff;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 20px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.cc-version {
    margin-left: auto;
    font-size: 0.75rem;
    color: var(--muted);
    font-family: 'JetBrains Mono', monospace;
}

/* Metric cards */
.metric-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.metric-label { font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
.metric-value { font-size: 1.8rem; font-weight: 700; line-height: 1; }
.metric-sub   { font-size: 0.72rem; color: var(--muted); }

/* Platform grid */
.platform-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.platform-tile {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    transition: border-color 0.15s;
}
.platform-tile:hover { border-color: var(--blue); }
.platform-tile.active { border-color: var(--green); }
.ptile-left { display: flex; align-items: center; gap: 10px; }
.ptile-icon { font-size: 1.2rem; }
.ptile-name { font-size: 0.85rem; font-weight: 600; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-green  { background: var(--green); box-shadow: 0 0 6px var(--green); }
.dot-yellow { background: var(--yellow); }
.dot-red    { background: var(--red); }
.dot-muted  { background: var(--muted); }

/* Section headers */
.section-title {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted);
    margin: 22px 0 10px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
}

/* Task buttons */
.task-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--text);
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    text-align: left;
    transition: background 0.15s, border-color 0.15s;
}
.task-btn:hover { background: #1c2128; border-color: var(--blue); }
.task-btn .task-icon { font-size: 1rem; }
.task-new { border-color: var(--accent) !important; }

/* Log terminal */
.log-terminal {
    background: #010409;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.73rem;
    max-height: 300px;
    overflow-y: auto;
    color: #7ee787;
    line-height: 1.6;
}
.log-error  { color: var(--red); }
.log-warn   { color: var(--yellow); }
.log-info   { color: #58a6ff; }
.log-muted  { color: var(--muted); }

/* Alert strip */
.alert-strip {
    background: #1a1500;
    border: 1px solid #3a2f00;
    border-left: 3px solid var(--yellow);
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 0.8rem;
    color: #f0c000;
    margin: 6px 0;
    display: flex;
    align-items: center;
    gap: 10px;
}
.alert-strip.red {
    background: #1a0505;
    border-color: #3a0a0a;
    border-left-color: var(--red);
    color: var(--red);
}
.alert-strip.green {
    background: #051a09;
    border-color: #0a3a14;
    border-left-color: var(--green);
    color: var(--green);
}

/* Streamlit overrides */
div[data-testid="stButton"] > button {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 8px;
    font-size: 0.82rem;
    font-weight: 500;
    transition: all 0.15s;
}
div[data-testid="stButton"] > button:hover {
    border-color: var(--blue);
    background: #1c2128;
    color: var(--text);
}
div[data-testid="stButton"] > button[kind="primary"] {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #e56d55;
    border-color: #e56d55;
}
div[data-testid="metric-container"] { display: none; }

/* Toggle */
div[data-testid="stToggle"] label { color: var(--text) !important; font-size: 0.85rem; }

/* Selectbox */
div[data-testid="stSelectbox"] > div { background: var(--surface) !important; border-color: var(--border) !important; }

/* Horizontal rule */
hr { border-color: var(--border); }

/* Expander */
details { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; }
summary { color: var(--text) !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* Status pill */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.pill-running { background: #051a09; color: var(--green); border: 1px solid var(--green); }
.pill-idle    { background: #161b22; color: var(--muted); border: 1px solid var(--border); }
.pill-error   { background: #1a0505; color: var(--red);   border: 1px solid var(--red); }
.pill-dry     { background: #1a1500; color: var(--yellow); border: 1px solid var(--yellow); }

</style>
""", unsafe_allow_html=True)

# ── Session state init ────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "dry_run": True,
        "running_tasks": {},
        "log_entries": [],
        "platforms": {
            "LinkedIn":  {"enabled": True,  "icon": "💼", "status": "idle"},
            "WhatsApp":  {"enabled": True,  "icon": "💬", "status": "idle"},
            "Facebook":  {"enabled": False, "icon": "📘", "status": "off"},
            "Instagram": {"enabled": False, "icon": "📸", "status": "off"},
            "Twitter/X": {"enabled": False, "icon": "🐦", "status": "off"},
            "Slack":     {"enabled": False, "icon": "⚡", "status": "off"},
        },
        "last_refresh": datetime.now(),
        "alerts": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── DB helpers ────────────────────────────────────────────────────────────────
DB_PATH = Path("agent_history.db")

def get_db_stats():
    """Pull stats from SQLite if it exists, else return mock data."""
    if not DB_PATH.exists():
        # Demo data so the dashboard looks alive out of the box
        today = datetime.now().date()
        return {
            "total_wishes": 142,
            "today_wishes": 7,
            "pending_followups": 4,
            "missed_birthdays": 2,
            "platforms_active": 2,
            "last_run": datetime.now() - timedelta(hours=2),
            "recent_logs": [
                {"ts": datetime.now() - timedelta(minutes=5),  "level": "INFO",  "msg": "LinkedIn birthday scan complete — 3 contacts found"},
                {"ts": datetime.now() - timedelta(minutes=12), "level": "INFO",  "msg": "AI wish generated for Rakib Hossain (score: 9.1/10)"},
                {"ts": datetime.now() - timedelta(minutes=18), "level": "WARN",  "msg": "WhatsApp session expired — re-login required"},
                {"ts": datetime.now() - timedelta(minutes=45), "level": "INFO",  "msg": "Follow-up sent to 2 contacts (no reply in 3 days)"},
                {"ts": datetime.now() - timedelta(hours=2),    "level": "INFO",  "msg": "Daily scheduler triggered at 09:00 AM"},
                {"ts": datetime.now() - timedelta(hours=3),    "level": "ERROR", "msg": "Proxy rotation failed — falling back to direct connection"},
                {"ts": datetime.now() - timedelta(hours=5),    "level": "INFO",  "msg": "Relationship decay alert sent for 1 contact (90+ days)"},
            ],
        }
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        today_str = datetime.now().strftime("%Y-%m-%d")
        total  = c.execute("SELECT COUNT(*) FROM wish_history").fetchone()[0]
        today_ = c.execute("SELECT COUNT(*) FROM wish_history WHERE date(timestamp) = ?", (today_str,)).fetchone()[0]
        conn.close()
        return {"total_wishes": total, "today_wishes": today_}
    except Exception:
        return {}

def add_log(level: str, msg: str):
    st.session_state.log_entries.insert(0, {
        "ts": datetime.now(), "level": level, "msg": msg
    })
    if len(st.session_state.log_entries) > 200:
        st.session_state.log_entries.pop()

# ── Mock task runner ──────────────────────────────────────────────────────────
TASKS = [
    {"id": "birthday_scan",       "label": "Birthday Detection",        "icon": "🎂", "new": False, "desc": "Scan all enabled platforms for today's birthdays"},
    {"id": "ai_wish",             "label": "AI Custom Wish",            "icon": "✨", "new": False, "desc": "Generate & send personalized AI wishes"},
    {"id": "linkedin_reply",      "label": "LinkedIn Reply",            "icon": "💼", "new": False, "desc": "Reply to incoming LinkedIn birthday messages"},
    {"id": "whatsapp_reply",      "label": "WhatsApp Reply",            "icon": "💬", "new": False, "desc": "Reply to WhatsApp birthday messages"},
    {"id": "smart_followup",      "label": "Smart Follow-up",           "icon": "📩", "new": True,  "desc": "Auto follow-up for contacts with no reply (3 days)"},
    {"id": "decay_alert",         "label": "Decay Alert",               "icon": "📉", "new": True,  "desc": "Alert & check-in for fading relationships"},
    {"id": "miss_tracker",        "label": "Birthday Miss Tracker",     "icon": "🔍", "new": True,  "desc": "Find missed birthdays and send late wishes"},
    {"id": "auto_timezone",       "label": "Auto Timezone Scheduler",   "icon": "🌐", "new": True,  "desc": "Schedule wishes at 9 AM contact's local time"},
    {"id": "personalized_connect","label": "Personalized Connect",      "icon": "🤝", "new": True,  "desc": "Send connection request after wishing"},
    {"id": "twitter_birthday",    "label": "Twitter/X Birthday",        "icon": "🐦", "new": True,  "desc": "Detect & reply to birthday tweets"},
    {"id": "slack_birthday",      "label": "Slack Birthday Bot",        "icon": "⚡", "new": True,  "desc": "DM + channel birthday announcements"},
    {"id": "ab_testing",          "label": "A/B Style Optimizer",       "icon": "🧪", "new": False, "desc": "Run A/B test to find best-performing wish style"},
    {"id": "relationship_health", "label": "Relationship Health Report","icon": "💝", "new": False, "desc": "Generate weekly relationship health email"},
]

def _run_task_thread(task_id: str, dry_run: bool):
    """Simulate running an agent task in a thread."""
    time.sleep(1.5)
    st.session_state.running_tasks[task_id] = "done"

def trigger_task(task_id: str, task_label: str):
    mode = "DRY RUN" if st.session_state.dry_run else "LIVE"
    add_log("INFO", f"[{mode}] Task triggered: {task_label}")
    if st.session_state.dry_run:
        add_log("INFO", f"[DRY RUN] Simulating {task_label} — no real actions taken")
        st.session_state.alerts.insert(0, {"type": "yellow", "msg": f"⚠️ DRY RUN: {task_label} simulated. Toggle Dry Run off to go live."})
    else:
        add_log("INFO", f"[LIVE] Launching {task_label}...")
        st.session_state.running_tasks[task_id] = "running"
        t = threading.Thread(target=_run_task_thread, args=(task_id, False), daemon=True)
        t.start()

# ── Stats ─────────────────────────────────────────────────────────────────────
stats = get_db_stats()

# ─────────────────────────────────────────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

# Header
st.markdown("""
<div class="cc-header">
  <span style="font-size:1.6rem">🎂</span>
  <h1>Unified Command Center</h1>
  <span class="cc-badge">v7.0</span>
  <span class="cc-version">Birthday Wishes Agent</span>
</div>
""", unsafe_allow_html=True)

# ── Top controls row ──────────────────────────────────────────────────────────
ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2, 1, 1, 1])

with ctrl_col1:
    dry = st.toggle("🧪 Dry Run Mode", value=st.session_state.dry_run,
                    help="Simulate tasks without sending real messages")
    st.session_state.dry_run = dry
    if dry:
        st.markdown('<span class="status-pill pill-dry">● Dry Run Active</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-pill pill-running">● Live Mode</span>', unsafe_allow_html=True)

with ctrl_col2:
    if st.button("▶ Run All Active", type="primary", use_container_width=True):
        trigger_task("all", "All Active Platform Tasks")
        st.rerun()

with ctrl_col3:
    if st.button("⏹ Stop All", use_container_width=True):
        st.session_state.running_tasks.clear()
        add_log("WARN", "All running tasks stopped by user")
        st.rerun()

with ctrl_col4:
    if st.button("🔄 Refresh", use_container_width=True):
        st.session_state.last_refresh = datetime.now()
        st.rerun()

st.markdown("---")

# ── Metric cards ──────────────────────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)

cards = [
    (m1, "Total Wishes Sent", stats.get("total_wishes", 142),      "all time",         "#f78166"),
    (m2, "Sent Today",        stats.get("today_wishes", 7),         "across platforms", "#3fb950"),
    (m3, "Pending Follow-ups",stats.get("pending_followups", 4),    "no reply > 3 days","#d29922"),
    (m4, "Missed Birthdays",  stats.get("missed_birthdays", 2),     "late wish queued", "#f85149"),
    (m5, "Active Platforms",  stats.get("platforms_active", 2),     "of 6 configured",  "#58a6ff"),
]

for col, label, value, sub, color in cards:
    with col:
        st.markdown(f"""
        <div class="metric-card">
          <div class="metric-label">{label}</div>
          <div class="metric-value" style="color:{color}">{value}</div>
          <div class="metric-sub">{sub}</div>
        </div>
        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Main two-column layout
# ─────────────────────────────────────────────────────────────────────────────
left, right = st.columns([1.1, 1.9], gap="large")

# ── LEFT: Platform toggles ────────────────────────────────────────────────────
with left:
    st.markdown('<div class="section-title">Platform Control</div>', unsafe_allow_html=True)

    for name, info in st.session_state.platforms.items():
        col_a, col_b = st.columns([3, 1])
        with col_a:
            enabled = st.toggle(f"{info['icon']}  {name}", value=info["enabled"], key=f"plat_{name}")
            st.session_state.platforms[name]["enabled"] = enabled
            st.session_state.platforms[name]["status"] = "idle" if enabled else "off"
        with col_b:
            task_id = name.lower().replace("/", "").replace(" ", "")
            if enabled:
                is_running = st.session_state.running_tasks.get(task_id) == "running"
                label = "⏳" if is_running else "▶"
                if st.button(label, key=f"run_{name}", use_container_width=True,
                             help=f"Run {name} task now"):
                    trigger_task(task_id, f"{name} Birthday Task")
                    st.rerun()

    # Last run info
    last_run = stats.get("last_run", datetime.now() - timedelta(hours=2))
    elapsed  = int((datetime.now() - last_run).total_seconds() / 60)
    st.markdown(f"""
    <div style="margin-top:16px; padding:10px 14px; background:#161b22;
                border:1px solid #30363d; border-radius:8px; font-size:0.75rem; color:#8b949e;">
      🕐 Last scheduler run: <strong style="color:#e6edf3">{elapsed}m ago</strong><br>
      🔁 Next run: <strong style="color:#e6edf3">
        {(datetime.now().replace(hour=9, minute=0, second=0) + timedelta(days=1)).strftime("%b %d, 09:00 AM")}
      </strong>
    </div>
    """, unsafe_allow_html=True)

    # Alerts
    st.markdown('<div class="section-title" style="margin-top:20px">Alerts</div>', unsafe_allow_html=True)

    # Built-in alerts from stats
    if stats.get("missed_birthdays", 0) > 0:
        st.markdown(f'<div class="alert-strip">🎂 {stats["missed_birthdays"]} missed birthday(s) detected — Miss Tracker queued</div>', unsafe_allow_html=True)
    if stats.get("pending_followups", 0) > 0:
        st.markdown(f'<div class="alert-strip">📩 {stats["pending_followups"]} follow-up(s) pending (no reply > 3 days)</div>', unsafe_allow_html=True)

    for alert in st.session_state.alerts[:3]:
        css_class = {"red": "red", "green": "green"}.get(alert["type"], "")
        st.markdown(f'<div class="alert-strip {css_class}">{alert["msg"]}</div>', unsafe_allow_html=True)

    if st.button("Clear alerts", use_container_width=True):
        st.session_state.alerts.clear()
        st.rerun()


# ── RIGHT: Task triggers + Logs ───────────────────────────────────────────────
with right:
    st.markdown('<div class="section-title">Task Triggers</div>', unsafe_allow_html=True)

    # Display tasks in a 2-col grid
    task_rows = [TASKS[i:i+2] for i in range(0, len(TASKS), 2)]
    for row in task_rows:
        cols = st.columns(len(row))
        for col, task in zip(cols, row):
            with col:
                is_running = st.session_state.running_tasks.get(task["id"]) == "running"
                border_style = "border-left: 3px solid #f78166;" if task["new"] else ""
                state_icon   = "⏳" if is_running else task["icon"]
                new_badge    = ' <span style="font-size:0.6rem;background:#f78166;color:#fff;padding:1px 5px;border-radius:4px;vertical-align:middle">NEW</span>' if task["new"] else ""

                clicked = st.button(
                    f"{state_icon}  {task['label']}{new_badge}",
                    key=f"task_{task['id']}",
                    use_container_width=True,
                    help=task["desc"],
                    disabled=is_running,
                )
                if clicked:
                    trigger_task(task["id"], task["label"])
                    st.rerun()

    # ── Live Logs ─────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title" style="margin-top:20px">Live Logs</div>', unsafe_allow_html=True)

    log_filter = st.selectbox("Filter", ["ALL", "INFO", "WARN", "ERROR"],
                              label_visibility="collapsed")

    # Merge session logs + stats logs
    all_logs = list(st.session_state.log_entries)
    for entry in stats.get("recent_logs", []):
        all_logs.append(entry)
    all_logs.sort(key=lambda x: x["ts"], reverse=True)

    if log_filter != "ALL":
        all_logs = [l for l in all_logs if l["level"] == log_filter]

    lines = []
    for entry in all_logs[:60]:
        ts  = entry["ts"].strftime("%H:%M:%S")
        lvl = entry["level"]
        msg = entry["msg"]
        if lvl == "ERROR":
            cls = "log-error"
        elif lvl == "WARN":
            cls = "log-warn"
        elif lvl == "INFO":
            cls = "log-info"
        else:
            cls = "log-muted"
        lines.append(f'<span class="{cls}">[{ts}] [{lvl}] {msg}</span>')

    log_html = "<br>".join(lines) if lines else '<span class="log-muted">No logs yet — trigger a task to begin.</span>'
    st.markdown(f'<div class="log-terminal">{log_html}</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑 Clear logs", use_container_width=True):
            st.session_state.log_entries.clear()
            st.rerun()
    with col_b:
        if st.button("💾 Export logs", use_container_width=True):
            export = "\n".join(
                f"[{e['ts'].strftime('%Y-%m-%d %H:%M:%S')}] [{e['level']}] {e['msg']}"
                for e in all_logs
            )
            st.download_button("Download .txt", export, file_name="agent_logs.txt",
                               mime="text/plain", use_container_width=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:center;
            font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
  <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">7.0</code></span>
  <span>Last refreshed: {st.session_state.last_refresh.strftime("%H:%M:%S")}</span>
  <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
</div>
""", unsafe_allow_html=True)
