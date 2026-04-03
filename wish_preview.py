"""
wish_preview.py
───────────────
Wish Preview dashboard for Birthday Wishes Agent.

Before sending any birthday wishes, shows a preview of each
generated wish so the user can approve, edit, or reject them.

Run with:
    streamlit run wish_preview.py

Features:
  - Shows all pending wishes for today
  - Displays contact name, job, relationship, and generated wish
  - Approve → marks as approved, agent will send
  - Edit → allows editing the wish before approving
  - Reject → skips this contact today
  - Bulk approve all
  - Stores approval status in SQLite
"""

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import streamlit as st

DB_FILE = Path("agent_history.db")

# ──────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Wish Preview",
    page_icon="👀",
    layout="wide",
)

# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_preview_table():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wish_previews (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            contact      TEXT    NOT NULL,
            platform     TEXT    NOT NULL DEFAULT 'linkedin',
            relationship TEXT    NOT NULL DEFAULT 'acquaintance',
            job_title    TEXT,
            company      TEXT,
            wish_text    TEXT    NOT NULL,
            score        INTEGER DEFAULT 0,
            status       TEXT    NOT NULL DEFAULT 'pending',
            edited       INTEGER NOT NULL DEFAULT 0,
            date         TEXT    NOT NULL,
            created_at   TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_pending_previews() -> list[dict]:
    if not DB_FILE.exists():
        return []
    today = date.today().isoformat()
    conn  = sqlite3.connect(DB_FILE)
    rows  = conn.execute(
        "SELECT id, contact, platform, relationship, job_title, "
        "company, wish_text, score, status, edited "
        "FROM wish_previews WHERE date = ? ORDER BY id",
        (today,),
    ).fetchall()
    conn.close()
    return [
        {
            "id":           r[0],
            "contact":      r[1],
            "platform":     r[2],
            "relationship": r[3],
            "job_title":    r[4] or "",
            "company":      r[5] or "",
            "wish_text":    r[6],
            "score":        r[7] or 0,
            "status":       r[8],
            "edited":       bool(r[9]),
        }
        for r in rows
    ]


def update_preview_status(preview_id: int, status: str,
                           wish_text: str = None):
    conn = sqlite3.connect(DB_FILE)
    if wish_text:
        conn.execute(
            "UPDATE wish_previews SET status=?, wish_text=?, edited=1 WHERE id=?",
            (status, wish_text, preview_id),
        )
    else:
        conn.execute(
            "UPDATE wish_previews SET status=? WHERE id=?",
            (status, preview_id),
        )
    conn.commit()
    conn.close()


def add_preview(
    contact: str,
    wish_text: str,
    platform: str = "linkedin",
    relationship: str = "acquaintance",
    job_title: str = "",
    company: str = "",
    score: int = 0,
):
    """Add a wish to the preview queue."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO wish_previews "
        "(contact, platform, relationship, job_title, company, "
        "wish_text, score, status, date, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
        (contact, platform, relationship, job_title, company,
         wish_text, score, date.today().isoformat(),
         datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_approved_wishes() -> list[dict]:
    """Get all approved wishes for today — used by the agent to send."""
    if not DB_FILE.exists():
        return []
    today = date.today().isoformat()
    conn  = sqlite3.connect(DB_FILE)
    rows  = conn.execute(
        "SELECT contact, platform, wish_text, relationship "
        "FROM wish_previews WHERE date = ? AND status = 'approved'",
        (today,),
    ).fetchall()
    conn.close()
    return [
        {"contact": r[0], "platform": r[1],
         "wish_text": r[2], "relationship": r[3]}
        for r in rows
    ]


# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
  .wish-card {
    background: #1E2329;
    border: 1px solid #2E3440;
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
  }
  .wish-card.approved { border-color: #4CAF50; }
  .wish-card.rejected { border-color: #F44336; opacity: 0.6; }
  .wish-card.edited   { border-color: #FF9800; }
  .status-badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 700;
  }
  .badge-pending  { background: #2E3440; color: #aaa; }
  .badge-approved { background: #1a3a2a; color: #4CAF50; }
  .badge-rejected { background: #3a1a1a; color: #F44336; }
  .score-bar { height: 6px; border-radius: 3px; background: #2E3440; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# INIT DB
# ──────────────────────────────────────────────
if DB_FILE.exists():
    init_preview_table()

# ──────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────
st.title("👀 Wish Preview")
st.caption("Review and approve birthday wishes before they are sent.")
st.divider()

# ──────────────────────────────────────────────
# ADD SAMPLE PREVIEWS (Demo Mode)
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Options")

    if st.button("➕ Add Sample Wish (Demo)", use_container_width=True):
        if DB_FILE.exists():
            init_preview_table()
            import random
            samples = [
                ("Rahul Ahmed",  "linkedin", "colleague",     "Software Engineer", "Google",
                 "Happy Birthday Rahul! 🎂 Hope your journey at Google keeps inspiring the engineer in you. Wishing you a year full of breakthroughs! 🚀", 9),
                ("Priya Sharma", "linkedin", "close_friend",  "Product Manager",   "Meta",
                 "Hey Priya! 🥳 Can't believe another year has gone by — hope today is as incredible as you always make everything around you! Let's celebrate soon! 🎉", 8),
                ("Ahmed Hassan", "whatsapp", "acquaintance",  "Marketing Manager", "Startup",
                 "Happy Birthday Ahmed! 🎂 Hope you have a wonderful day and a fantastic year ahead!", 7),
            ]
            s = random.choice(samples)
            add_preview(s[0], s[5], s[1], s[2], s[3], s[4], s[6])
            st.success(f"Sample wish added for {s[0]}!")
            st.rerun()

    st.divider()
    st.caption("Agent reads approved wishes and sends them automatically.")
    st.caption("Rejected wishes are skipped for today.")

# ──────────────────────────────────────────────
# LOAD PREVIEWS
# ──────────────────────────────────────────────
previews = get_pending_previews()

if not previews:
    st.info(
        "📭 No wishes pending review today.\n\n"
        "The agent will add wishes here before sending them "
        "when `WISH_PREVIEW_ENABLED = True` in `agent.py`."
    )
    st.stop()

# ──────────────────────────────────────────────
# SUMMARY BAR
# ──────────────────────────────────────────────
pending  = sum(1 for p in previews if p["status"] == "pending")
approved = sum(1 for p in previews if p["status"] == "approved")
rejected = sum(1 for p in previews if p["status"] == "rejected")
edited   = sum(1 for p in previews if p["edited"])

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("📋 Total",    len(previews))
c2.metric("⏳ Pending",  pending)
c3.metric("✅ Approved", approved)
c4.metric("❌ Rejected", rejected)
c5.metric("✏️ Edited",   edited)

# ──────────────────────────────────────────────
# BULK ACTIONS
# ──────────────────────────────────────────────
col_a, col_b = st.columns(2)
with col_a:
    if st.button("✅ Approve All Pending", use_container_width=True, type="primary"):
        for p in previews:
            if p["status"] == "pending":
                update_preview_status(p["id"], "approved")
        st.success("All pending wishes approved!")
        st.rerun()

with col_b:
    if st.button("❌ Reject All Pending", use_container_width=True):
        for p in previews:
            if p["status"] == "pending":
                update_preview_status(p["id"], "rejected")
        st.warning("All pending wishes rejected.")
        st.rerun()

st.divider()

# ──────────────────────────────────────────────
# WISH CARDS
# ──────────────────────────────────────────────
PLATFORM_ICONS = {
    "linkedin":  "💼",
    "whatsapp":  "📱",
    "facebook":  "📘",
    "instagram": "📸",
}
RELATIONSHIP_COLORS = {
    "close_friend": "#4CAF50",
    "colleague":    "#2196F3",
    "acquaintance": "#9E9E9E",
}

for preview in previews:
    status    = preview["status"]
    platform  = preview["platform"]
    rel       = preview["relationship"]
    score     = preview["score"]
    pid       = preview["id"]

    badge_class  = f"badge-{status}"
    status_label = {"pending": "⏳ Pending",
                    "approved": "✅ Approved",
                    "rejected": "❌ Rejected"}.get(status, status)

    with st.container():
        # Header row
        h1, h2, h3 = st.columns([3, 1, 1])
        with h1:
            st.markdown(
                f"### {PLATFORM_ICONS.get(platform, '💬')} {preview['contact']}"
            )
            job_line = ""
            if preview["job_title"] and preview["company"]:
                job_line = f"{preview['job_title']} @ {preview['company']}"
            elif preview["job_title"]:
                job_line = preview["job_title"]
            if job_line:
                st.caption(f"💼 {job_line}")
        with h2:
            rel_color = RELATIONSHIP_COLORS.get(rel, "#9E9E9E")
            st.markdown(
                f'<span style="color:{rel_color};font-weight:600;">'
                f'● {rel.replace("_", " ").title()}</span>',
                unsafe_allow_html=True,
            )
        with h3:
            st.markdown(
                f'<span class="status-badge {badge_class}">'
                f'{status_label}</span>',
                unsafe_allow_html=True,
            )

        # Score bar
        if score > 0:
            score_color = "#4CAF50" if score >= 7 else "#FFC107" if score >= 5 else "#F44336"
            st.markdown(
                f'<div style="margin:8px 0;">'
                f'Quality Score: <strong style="color:{score_color};">'
                f'{score}/10</strong></div>',
                unsafe_allow_html=True,
            )

        # Wish text
        if status == "pending":
            edited_wish = st.text_area(
                "📝 Wish message",
                value=preview["wish_text"],
                key=f"wish_{pid}",
                height=100,
            )
        else:
            st.info(f"💬 {preview['wish_text']}")
            edited_wish = preview["wish_text"]

        # Action buttons
        if status == "pending":
            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("✅ Approve", key=f"approve_{pid}",
                             use_container_width=True, type="primary"):
                    update_preview_status(pid, "approved", edited_wish)
                    st.success(f"Approved wish for {preview['contact']}!")
                    st.rerun()
            with b2:
                if st.button("✏️ Save Edit", key=f"edit_{pid}",
                             use_container_width=True):
                    update_preview_status(pid, "pending", edited_wish)
                    st.info("Edit saved. Click Approve when ready.")
                    st.rerun()
            with b3:
                if st.button("❌ Reject", key=f"reject_{pid}",
                             use_container_width=True):
                    update_preview_status(pid, "rejected")
                    st.warning(f"Rejected wish for {preview['contact']}.")
                    st.rerun()
        elif status == "approved":
            if st.button("↩️ Undo Approval", key=f"undo_{pid}",
                         use_container_width=True):
                update_preview_status(pid, "pending")
                st.rerun()

        st.divider()

# ──────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────
st.caption(
    f"🎂 Birthday Wishes Agent v4.0 — Wish Preview | "
    f"Today: {date.today().strftime('%B %d, %Y')}"
)
