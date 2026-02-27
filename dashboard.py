import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

# ──────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Birthday Wishes Agent",
    page_icon="🎂",
    layout="wide",
)

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
CONFIG_FILE = Path("dashboard_config.json")
LOG_FILE    = Path("agent.log")


# ──────────────────────────────────────────────
# CONFIG LOAD / SAVE
# ──────────────────────────────────────────────
def load_config() -> dict:
    defaults = {
        "dry_run": True,
        "schedule_hour": 9,
        "schedule_minute": 0,
    }
    if CONFIG_FILE.exists():
        try:
            return {**defaults, **json.loads(CONFIG_FILE.read_text())}
        except Exception:
            pass
    return defaults


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ──────────────────────────────────────────────
# SESSION STATE INIT
# ──────────────────────────────────────────────
if "config" not in st.session_state:
    st.session_state.config = load_config()

if "agent_running" not in st.session_state:
    st.session_state.agent_running = False

if "agent_process" not in st.session_state:
    st.session_state.agent_process = None

if "run_output" not in st.session_state:
    st.session_state.run_output = ""


# ──────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────
st.title("🎂 Birthday Wishes Agent Dashboard")
st.markdown("Automate your LinkedIn birthday wishes with ease.")
st.divider()


# ──────────────────────────────────────────────
# LAYOUT: Two columns
# ──────────────────────────────────────────────
left, right = st.columns([1, 2])


# ══════════════════════════════════════════════
# LEFT COLUMN — Controls
# ══════════════════════════════════════════════
with left:
    st.subheader("⚙️ Settings")

    # ── DRY RUN TOGGLE ────────────────────────
    dry_run = st.toggle(
        "🧪 Dry Run Mode",
        value=st.session_state.config["dry_run"],
        help="ON = Only simulate, no messages sent. OFF = Actually send messages.",
    )
    if dry_run:
        st.info("Dry Run is ON — no messages will be sent.")
    else:
        st.warning("⚠️ Dry Run is OFF — messages WILL be sent!")

    st.divider()

    # ── SCHEDULER TIME ────────────────────────
    st.markdown("**⏰ Daily Schedule Time**")
    col1, col2 = st.columns(2)
    with col1:
        hour = st.number_input(
            "Hour (0–23)",
            min_value=0, max_value=23,
            value=st.session_state.config["schedule_hour"],
        )
    with col2:
        minute = st.number_input(
            "Minute (0–59)",
            min_value=0, max_value=59,
            value=st.session_state.config["schedule_minute"],
            step=5,
        )

    st.caption(f"Agent will run daily at **{int(hour):02d}:{int(minute):02d}**")

    # ── SAVE SETTINGS ─────────────────────────
    if st.button("💾 Save Settings", use_container_width=True):
        st.session_state.config = {
            "dry_run": dry_run,
            "schedule_hour": int(hour),
            "schedule_minute": int(minute),
        }
        save_config(st.session_state.config)

        # Update agent.py with new settings
        agent_path = Path("agent.py")
        if agent_path.exists():
            content = agent_path.read_text()
            content = __import__('re').sub(
                r"DRY_RUN\s*=\s*(True|False)",
                f"DRY_RUN = {dry_run}",
                content,
            )
            content = __import__('re').sub(
                r"SCHEDULE_HOUR\s*=\s*\d+",
                f"SCHEDULE_HOUR   = {int(hour)}",
                content,
            )
            content = __import__('re').sub(
                r"SCHEDULE_MINUTE\s*=\s*\d+",
                f"SCHEDULE_MINUTE = {int(minute)}",
                content,
            )
            agent_path.write_text(content)
        st.success("✅ Settings saved!")

    st.divider()

    # ── RUN BUTTONS ───────────────────────────
    st.subheader("🚀 Run Agent")

    mode = st.radio(
        "Select task:",
        ["🎂 Birthday Detection (Wish Contacts)", "💬 Reply to Wishes", "📅 Start Scheduler"],
        index=0,
    )

    run_clicked  = st.button("▶️ Run Now",  use_container_width=True, type="primary")
    stop_clicked = st.button("⏹️ Stop",     use_container_width=True)

    if run_clicked:
        st.session_state.agent_running = True
        st.session_state.run_output = "⏳ Agent is starting...\n"

        # Map mode to function name
        task_map = {
            "🎂 Birthday Detection (Wish Contacts)": "run_birthday_detection_task",
            "💬 Reply to Wishes":                    "run_linkedin_reply_task",
            "📅 Start Scheduler":                    "run_scheduler",
        }
        task_fn = task_map[mode]

        # Run agent.py with the selected task as a subprocess
        script = f"""
import asyncio, sys
sys.path.insert(0, '.')
from agent import {task_fn}, close_browser
async def _main():
    try:
        await {task_fn}()
    finally:
        await close_browser()
asyncio.run(_main())
"""
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            st.session_state.agent_process = proc
        except Exception as e:
            st.session_state.run_output = f"❌ Failed to start agent: {e}"
            st.session_state.agent_running = False

    if stop_clicked and st.session_state.agent_process:
        st.session_state.agent_process.terminate()
        st.session_state.agent_running = False
        st.session_state.run_output += "\n🛑 Agent stopped by user."
        st.session_state.agent_process = None

    # Poll subprocess output
    if st.session_state.agent_process:
        proc = st.session_state.agent_process
        if proc.poll() is None:
            # Still running — read available output
            try:
                line = proc.stdout.readline()
                if line:
                    st.session_state.run_output += line
            except Exception:
                pass
        else:
            st.session_state.agent_running = False
            remaining = proc.stdout.read()
            if remaining:
                st.session_state.run_output += remaining
            st.session_state.agent_process = None

    # Status indicator
    if st.session_state.agent_running:
        st.success("🟢 Agent is running…")
    else:
        st.info("⚪ Agent is idle.")


# ══════════════════════════════════════════════
# RIGHT COLUMN — Output + Logs
# ══════════════════════════════════════════════
with right:

    # ── LIVE RUN OUTPUT ───────────────────────
    st.subheader("📤 Agent Output")
    st.text_area(
        label="",
        value=st.session_state.run_output or "No output yet. Run the agent to see results.",
        height=200,
        key="output_box",
    )

    st.divider()

    # ── LOG VIEWER ────────────────────────────
    st.subheader("📋 Live Log Viewer (agent.log)")

    col_a, col_b = st.columns([3, 1])
    with col_a:
        log_lines = st.slider("Show last N lines:", 10, 200, 50)
    with col_b:
        refresh = st.button("🔄 Refresh", use_container_width=True)

    if LOG_FILE.exists():
        lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
        display = "\n".join(lines[-log_lines:]) if lines else "Log file is empty."
    else:
        display = "agent.log not found. Run the agent first."

    st.text_area(
        label="",
        value=display,
        height=350,
        key="log_box",
    )

    # Auto-refresh every 5 seconds while agent is running
    if st.session_state.agent_running:
        time.sleep(2)
        st.rerun()


# ──────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────
st.divider()
st.caption("Birthday Wishes Agent • Built with 🐍 Python + Streamlit")
