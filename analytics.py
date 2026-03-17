"""
analytics.py
────────────
Analytics Dashboard for Birthday Wishes Agent.

Run with:
    streamlit run analytics.py

Shows:
  - Total wishes sent (all time + this month)
  - Platform breakdown (LinkedIn, WhatsApp, Facebook, Instagram)
  - Relationship breakdown (close friend, colleague, acquaintance)
  - Language breakdown of incoming wishes
  - Daily activity chart
  - Recent activity table
  - Follow-up stats
"""

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd

DB_FILE = Path("agent_history.db")

# ──────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Birthday Wishes Agent — Analytics",
    page_icon="🎂",
    layout="wide",
)

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def get_db():
    if not DB_FILE.exists():
        return None
    return sqlite3.connect(DB_FILE)


def load_history() -> pd.DataFrame:
    conn = get_db()
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM history ORDER BY created_at DESC", conn
        )
        conn.close()
        if df.empty:
            return df
        df["created_at"] = pd.to_datetime(df["created_at"])
        df["date"]       = pd.to_datetime(df["date"])
        return df
    except Exception:
        return pd.DataFrame()


def load_followups() -> pd.DataFrame:
    conn = get_db()
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM followups ORDER BY created_at DESC", conn
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


def detect_language(message: str) -> str:
    """Detect language from message content."""
    if not isinstance(message, str):
        return "English"
    msg = message.lower()
    if any(c for c in msg if "\u0980" <= c <= "\u09FF"):
        return "Bengali"
    if any(c for c in msg if "\u0600" <= c <= "\u06FF"):
        return "Arabic"
    if any(c for c in msg if "\u0900" <= c <= "\u097F"):
        return "Hindi"
    if "feliz" in msg:
        return "Spanish"
    if "joyeux" in msg or "anniversaire" in msg:
        return "French"
    if "geburtstag" in msg:
        return "German"
    if "doğum" in msg:
        return "Turkish"
    if "ulang tahun" in msg:
        return "Indonesian"
    return "English"


# ──────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────
df         = load_history()
df_followup = load_followups()
today      = date.today()
this_month = today.replace(day=1)

# ──────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────
st.title("🎂 Birthday Wishes Agent — Analytics")
st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y, %H:%M')}")
st.divider()

# ──────────────────────────────────────────────
# NO DATA STATE
# ──────────────────────────────────────────────
if df.empty:
    st.info(
        "📭 No data yet! Run the agent first to see analytics here.\n\n"
        "Make sure `agent_history.db` exists in the same folder as `analytics.py`."
    )
    st.stop()

# ──────────────────────────────────────────────
# FILTER: Live vs Dry Run
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Filters")
    show_dry_run = st.toggle("Include Dry Run data", value=False)
    if not show_dry_run:
        df = df[df["dry_run"] == 0]

    date_range = st.selectbox(
        "Date range",
        ["All time", "This month", "Last 7 days", "Today"],
    )
    if date_range == "Today":
        df = df[df["date"].dt.date == today]
    elif date_range == "Last 7 days":
        df = df[df["date"].dt.date >= today - timedelta(days=7)]
    elif date_range == "This month":
        df = df[df["date"].dt.date >= this_month]

    st.divider()
    st.caption("🗄️ Database: agent_history.db")
    st.caption(f"📋 Total records: {len(load_history())}")

# ──────────────────────────────────────────────
# KPI CARDS — ROW 1
# ──────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

total_wishes   = len(df[df["task"].str.contains("Birthday|Wish", case=False, na=False)])
total_replies  = len(df[df["task"].str.contains("Reply", case=False, na=False)])
total_followups_sent = len(df_followup[df_followup["followup_sent"] == 1]) if not df_followup.empty else 0
unique_contacts = df["contact"].nunique()

col1.metric("🎂 Wishes Sent",      total_wishes)
col2.metric("💬 Replies Sent",     total_replies)
col3.metric("🔔 Follow-ups Sent",  total_followups_sent)
col4.metric("👥 Unique Contacts",  unique_contacts)

st.divider()

# ──────────────────────────────────────────────
# ROW 2 — Daily Activity + Platform Breakdown
# ──────────────────────────────────────────────
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("📈 Daily Activity")
    if not df.empty:
        daily = (
            df.groupby(df["date"].dt.date)
            .size()
            .reset_index(name="Actions")
        )
        daily.columns = ["Date", "Actions"]
        st.bar_chart(daily.set_index("Date"), color="#4CAF50")
    else:
        st.info("No activity data in selected range.")

with col_right:
    st.subheader("🌐 Platform Breakdown")
    platforms = {
        "LinkedIn":  len(df[df["task"].str.contains("LinkedIn", case=False, na=False)]),
        "WhatsApp":  len(df[df["task"].str.contains("WhatsApp", case=False, na=False)]),
        "Facebook":  len(df[df["task"].str.contains("Facebook", case=False, na=False)]),
        "Instagram": len(df[df["task"].str.contains("Instagram", case=False, na=False)]),
    }
    platform_df = pd.DataFrame(
        list(platforms.items()), columns=["Platform", "Count"]
    ).set_index("Platform")
    st.bar_chart(platform_df, color="#2196F3")

st.divider()

# ──────────────────────────────────────────────
# ROW 3 — Relationship + Language Breakdown
# ──────────────────────────────────────────────
col_rel, col_lang = st.columns(2)

with col_rel:
    st.subheader("💝 Relationship Breakdown")
    if "relationship" in df.columns:
        rel_counts = df["relationship"].value_counts()
        rel_df = rel_counts.reset_index()
        rel_df.columns = ["Relationship", "Count"]
        st.bar_chart(rel_df.set_index("Relationship"), color="#E91E63")
    else:
        # Estimate from task names
        rel_data = {
            "Close Friend": len(df[df["message"].str.contains("close_friend", case=False, na=False)]),
            "Colleague":    len(df[df["message"].str.contains("colleague", case=False, na=False)]),
            "Acquaintance": len(df[df["message"].str.contains("acquaintance", case=False, na=False)]),
        }
        rel_df = pd.DataFrame(list(rel_data.items()), columns=["Type", "Count"]).set_index("Type")
        st.bar_chart(rel_df, color="#E91E63")

with col_lang:
    st.subheader("🌍 Language Breakdown")
    if not df.empty:
        df["language"] = df["message"].apply(detect_language)
        lang_counts = df["language"].value_counts()
        lang_df = lang_counts.reset_index()
        lang_df.columns = ["Language", "Count"]
        st.bar_chart(lang_df.set_index("Language"), color="#FF9800")
    else:
        st.info("No language data available.")

st.divider()

# ──────────────────────────────────────────────
# ROW 4 — Monthly Summary + Follow-up Stats
# ──────────────────────────────────────────────
col_monthly, col_fu = st.columns(2)

with col_monthly:
    st.subheader("📅 Monthly Summary")
    if not df.empty:
        df["month"] = df["date"].dt.to_period("M").astype(str)
        monthly = df.groupby("month").size().reset_index(name="Actions")
        monthly.columns = ["Month", "Actions"]
        st.bar_chart(monthly.set_index("Month"), color="#9C27B0")
    else:
        st.info("No monthly data available.")

with col_fu:
    st.subheader("🔔 Follow-up Stats")
    if not df_followup.empty:
        total_scheduled = len(df_followup)
        total_sent_fu   = len(df_followup[df_followup["followup_sent"] == 1])
        total_pending   = len(df_followup[df_followup["followup_sent"] == 0])
        completion_rate = (total_sent_fu / total_scheduled * 100) if total_scheduled > 0 else 0

        m1, m2, m3 = st.columns(3)
        m1.metric("Scheduled", total_scheduled)
        m2.metric("Sent",      total_sent_fu)
        m3.metric("Pending",   total_pending)
        st.progress(int(completion_rate), text=f"Completion rate: {completion_rate:.1f}%")
    else:
        st.info("No follow-up data yet.")

st.divider()

# ──────────────────────────────────────────────
# ROW 5 — Recent Activity Table
# ──────────────────────────────────────────────
st.subheader("🕐 Recent Activity")

if not df.empty:
    display_df = df[["date", "task", "contact", "message", "dry_run"]].copy()
    display_df["date"]    = display_df["date"].dt.strftime("%Y-%m-%d")
    display_df["dry_run"] = display_df["dry_run"].map({0: "🟢 Live", 1: "🧪 Dry Run"})
    display_df.columns   = ["Date", "Task", "Contact", "Message", "Mode"]

    st.dataframe(
        display_df.head(50),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No recent activity.")

# ──────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────
st.divider()
st.caption("🎂 Birthday Wishes Agent v3.0 — Analytics Dashboard")