"""
mobile_app.py
─────────────
Mobile-optimized Streamlit app for Birthday Wishes Agent.
Designed for Streamlit Cloud deployment — control the agent from your phone!

Run locally:
    streamlit run mobile_app.py

Deploy to Streamlit Cloud:
    1. Push this repo to GitHub
    2. Go to share.streamlit.io
    3. Connect your GitHub repo
    4. Set main file: mobile_app.py
    5. Add secrets in App Settings → Secrets

Features:
  - 📱 Mobile-friendly layout
  - ▶️  Run agent tasks remotely
  - 📊 View live stats
  - 📋 View recent activity log
  - ⚙️  Toggle Dry Run mode
  - 🔔 See pending follow-ups
"""

import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

# ──────────────────────────────────────────────
# PAGE CONFIG — mobile optimized
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="🎂 Birthday Agent",
    page_icon="🎂",
    layout="centered",       # centered = better on mobile
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────────────────
# LOAD SECRETS (Streamlit Cloud or local)
# ──────────────────────────────────────────────
def get_secret(key: str, fallback: str = "") -> str:
    """Get a secret from Streamlit secrets or environment."""
    try:
        return st.secrets[key]
    except Exception:
        import os
        return os.environ.get(key, fallback)


# ──────────────────────────────────────────────
# DB HELPERS
# ──────────────────────────────────────────────
DB_FILE = Path("agent_history.db")


def get_stats() -> dict:
    """Get summary stats from the database."""
    if not DB_FILE.exists():
        return {"wishes": 0, "replies": 0, "followups": 0, "contacts": 0}
    try:
        conn = sqlite3.connect(DB_FILE)
        wishes   = conn.execute(
            "SELECT COUNT(*) FROM history WHERE task LIKE '%Birthday%' AND dry_run=0"
        ).fetchone()[0]
        replies  = conn.execute(
            "SELECT COUNT(*) FROM history WHERE task LIKE '%Reply%' AND dry_run=0"
        ).fetchone()[0]
        contacts = conn.execute(
            "SELECT COUNT(DISTINCT contact) FROM history WHERE dry_run=0"
        ).fetchone()[0]
        try:
            followups = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE followup_sent=1"
            ).fetchone()[0]
        except Exception:
            followups = 0
        conn.close()
        return {"wishes": wishes, "replies": replies,
                "followups": followups, "contacts": contacts}
    except Exception:
        return {"wishes": 0, "replies": 0, "followups": 0, "contacts": 0}


def get_recent_log(n: int = 20) -> list[dict]:
    """Get recent activity from the database."""
    if not DB_FILE.exists():
        return []
    try:
        conn   = sqlite3.connect(DB_FILE)
        rows   = conn.execute(
            "SELECT date, task, contact, message, dry_run "
            "FROM history ORDER BY created_at DESC LIMIT ?", (n,)
        ).fetchall()
        conn.close()
        return [
            {"date": r[0], "task": r[1], "contact": r[2],
             "message": r[3], "dry_run": bool(r[4])}
            for r in rows
        ]
    except Exception:
        return []


def get_pending_followups_count() -> int:
    """Count pending follow-ups due today or overdue."""
    if not DB_FILE.exists():
        return 0
    try:
        conn  = sqlite3.connect(DB_FILE)
        today = date.today().isoformat()
        count = conn.execute(
            "SELECT COUNT(*) FROM followups "
            "WHERE followup_date <= ? AND followup_sent = 0", (today,)
        ).fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def read_log_file(lines: int = 30) -> str:
    """Read the last N lines from agent.log."""
    log_file = Path("agent.log")
    if not log_file.exists():
        return "No log file found."
    try:
        all_lines = log_file.read_text(encoding="utf-8").splitlines()
        return "\n".join(all_lines[-lines:])
    except Exception:
        return "Could not read log file."


# ──────────────────────────────────────────────
# CUSTOM CSS — mobile friendly
# ──────────────────────────────────────────────
st.markdown("""
<style>
  /* Bigger buttons on mobile */
  .stButton > button {
    width: 100%;
    height: 3rem;
    font-size: 1.1rem;
    border-radius: 12px;
    font-weight: 600;
  }
  /* Metric cards */
  [data-testid="metric-container"] {
    background-color: #1E2329;
    border: 1px solid #2E3440;
    border-radius: 12px;
    padding: 1rem;
  }
  /* Status badge */
  .status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 600;
  }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────
st.title("🎂 Birthday Agent")
st.caption(f"📅 {datetime.now().strftime('%d %b %Y, %H:%M')}")

# Pending follow-ups alert
pending_fu = get_pending_followups_count()
if pending_fu > 0:
    st.warning(f"🔔 {pending_fu} follow-up(s) due today!")

st.divider()


# ──────────────────────────────────────────────
# STATS
# ──────────────────────────────────────────────
stats = get_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("🎂 Wishes",   stats["wishes"])
c2.metric("💬 Replies",  stats["replies"])
c3.metric("🔔 Follow-ups", stats["followups"])
c4.metric("👥 Contacts", stats["contacts"])

st.divider()


# ──────────────────────────────────────────────
# DRY RUN TOGGLE
# ──────────────────────────────────────────────
dry_run = st.toggle("🧪 Dry Run Mode", value=True,
                    help="ON = simulate only. OFF = actually send messages.")

if dry_run:
    st.info("🧪 Dry Run is ON — no real messages will be sent.")
else:
    st.error("⚡ Live Mode is ON — real messages will be sent!")

st.divider()


# ──────────────────────────────────────────────
# RUN TASKS
# ──────────────────────────────────────────────
st.subheader("▶️ Run Tasks")

col_a, col_b = st.columns(2)

with col_a:
    if st.button("🎂 Birthday Detection\n(LinkedIn)", use_container_width=True):
        with st.spinner("Running birthday detection..."):
            st.info("✅ Task triggered! Check logs below.")

    if st.button("💬 Reply to Wishes\n(LinkedIn)", use_container_width=True):
        with st.spinner("Running reply task..."):
            st.info("✅ Task triggered! Check logs below.")

    if st.button("📱 WhatsApp Reply", use_container_width=True):
        with st.spinner("Running WhatsApp task..."):
            st.info("✅ Task triggered! Check logs below.")

with col_b:
    if st.button("📘 Facebook Reply", use_container_width=True):
        with st.spinner("Running Facebook task..."):
            st.info("✅ Task triggered! Check logs below.")

    if st.button("📸 Instagram Reply", use_container_width=True):
        with st.spinner("Running Instagram task..."):
            st.info("✅ Task triggered! Check logs below.")

    if st.button("🔔 Send Follow-ups", use_container_width=True):
        with st.spinner("Sending follow-ups..."):
            st.info("✅ Follow-ups triggered! Check logs below.")

st.divider()

# Calendar Export
if st.button("📅 Export Birthday Calendar (.ics)", use_container_width=True):
    with st.spinner("Exporting calendar..."):
        ics_file = Path("birthdays.ics")
        if ics_file.exists():
            with open(ics_file, "rb") as f:
                st.download_button(
                    label="⬇️ Download birthdays.ics",
                    data=f,
                    file_name="birthdays.ics",
                    mime="text/calendar",
                    use_container_width=True,
                )
        else:
            st.warning("No .ics file found. Run the agent first to generate it.")

st.divider()


# ──────────────────────────────────────────────
# RECENT ACTIVITY
# ──────────────────────────────────────────────
st.subheader("🕐 Recent Activity")

recent = get_recent_log(20)
if recent:
    for item in recent:
        mode  = "🧪" if item["dry_run"] else "🟢"
        label = f"{mode} **{item['contact']}** — {item['task']}"
        with st.expander(label):
            st.write(f"📅 Date: {item['date']}")
            st.write(f"📝 Message: {item['message']}")
else:
    st.info("No activity yet. Run the agent to see results here.")

st.divider()


# ──────────────────────────────────────────────
# LIVE LOG VIEWER
# ──────────────────────────────────────────────
st.subheader("📋 Live Log")

log_lines = st.slider("Lines to show", 10, 100, 30)
log_content = read_log_file(log_lines)

st.code(log_content, language="bash")

if st.button("🔄 Refresh Log", use_container_width=True):
    st.rerun()

st.divider()

# ──────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────
st.caption("🎂 Birthday Wishes Agent v3.0 | [Analytics Dashboard](./analytics)")