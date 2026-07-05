"""
Contact Timeline View — Birthday Wishes Agent v7.0
Browse contacts, select one, and see the full chronological history of every
interaction: wishes sent, replies received, follow-ups, decay alerts, and
relationship health changes — all on one vertical timeline.
"""

import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Contact Timeline",
    page_icon="🕓",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling (matches Command Center / Wish Preview theme) ────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

:root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --accent: #f78166; --green: #3fb950; --yellow: #d29922;
    --red: #f85149; --blue: #58a6ff; --muted: #8b949e; --text: #e6edf3;
}
.stApp { background: var(--bg); color: var(--text); }

.cc-header {
    display: flex; align-items: center; gap: 14px;
    padding: 18px 0 10px; border-bottom: 1px solid var(--border); margin-bottom: 24px;
}
.cc-header h1 { font-size: 1.4rem; font-weight: 700; letter-spacing: -0.02em; margin: 0; color: var(--text); }
.cc-badge {
    background: var(--accent); color: #fff; font-size: 0.65rem; font-weight: 700;
    padding: 2px 8px; border-radius: 20px; letter-spacing: 0.08em; text-transform: uppercase;
}
.cc-version { margin-left: auto; font-size: 0.75rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; }

.section-title {
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em;
    color: var(--muted); margin: 22px 0 10px; display: flex; align-items: center; gap: 8px;
}
.section-title::after { content: ''; flex: 1; height: 1px; background: var(--border); }

/* Contact list */
.contact-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 14px; margin-bottom: 6px; cursor: pointer; transition: border-color 0.15s;
}
.contact-card:hover { border-color: var(--blue); }
.contact-card.selected { border-color: var(--accent); background: #1c1410; }
.contact-name { font-weight: 600; font-size: 0.85rem; display:flex; align-items:center; gap:6px; }
.contact-meta { font-size: 0.7rem; color: var(--muted); margin-top: 2px; }
.health-dot { width: 7px; height: 7px; border-radius: 50%; display:inline-block; }
.health-good { background: var(--green); box-shadow: 0 0 5px var(--green); }
.health-warn { background: var(--yellow); }
.health-bad  { background: var(--red); }

/* Profile header */
.profile-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px 20px; display: flex; align-items: center; gap: 16px; margin-bottom: 18px;
}
.profile-avatar {
    width: 52px; height: 52px; border-radius: 50%;
    background: linear-gradient(135deg,#f78166,#d29922);
    display:flex; align-items:center; justify-content:center; font-weight:700; color:#fff; font-size:1.1rem;
    flex-shrink: 0;
}
.profile-name { font-size: 1.05rem; font-weight: 700; }
.profile-sub { font-size: 0.78rem; color: var(--muted); margin-top: 2px; }
.profile-stats { margin-left: auto; display: flex; gap: 22px; }
.pstat { text-align: center; }
.pstat-val { font-size: 1.1rem; font-weight: 700; }
.pstat-label { font-size: 0.62rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }

/* Timeline */
.timeline { position: relative; padding-left: 28px; }
.timeline::before {
    content: ''; position: absolute; left: 9px; top: 6px; bottom: 6px;
    width: 2px; background: var(--border);
}
.tl-item { position: relative; margin-bottom: 18px; }
.tl-dot {
    position: absolute; left: -28px; top: 3px; width: 18px; height: 18px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; font-size: 0.7rem;
    border: 2px solid var(--bg);
}
.tl-wish     { background: #1a3a1a; }
.tl-reply    { background: #1a2a3a; }
.tl-followup { background: #3a2f00; }
.tl-decay    { background: #3a0a0a; }
.tl-system   { background: #21262d; }

.tl-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 14px;
}
.tl-top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
.tl-label { font-size: 0.8rem; font-weight: 600; }
.tl-time { font-size: 0.68rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; }
.tl-body { font-size: 0.78rem; color: #c9d1d9; line-height: 1.5; }
.tl-platform-tag {
    display: inline-block; font-size: 0.62rem; font-weight: 600; padding: 1px 7px;
    border-radius: 10px; background: #21262d; color: var(--muted); margin-top: 6px;
}
.tl-score-tag {
    display: inline-block; font-size: 0.62rem; font-weight: 700; padding: 1px 7px;
    border-radius: 10px; margin-top: 6px; margin-left: 6px;
}
.score-good { background: #051a09; color: var(--green); }
.score-mid  { background: #1a1500; color: var(--yellow); }
.score-bad  { background: #1a0505; color: var(--red); }

.year-divider {
    font-size: 0.68rem; color: var(--muted); font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; margin: 16px 0 10px -28px; padding-left: 0;
}

div[data-testid="stButton"] > button {
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    border-radius: 8px; font-size: 0.8rem; font-weight: 500; transition: all 0.15s;
}
div[data-testid="stButton"] > button:hover { border-color: var(--blue); background: #1c2128; color: var(--text); }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ── Demo data (swap with real DB: SELECT * FROM contacts / interaction_log) ──
DEMO_CONTACTS = [
    {
        "name": "Rakib Hossain", "job": "Senior Backend Engineer", "company": "Pathao",
        "platform": "LinkedIn", "health": "good", "birthday": "June 18",
        "events": [
            {"type": "wish",     "date": datetime.now() - timedelta(days=3, hours=2),  "title": "AI Wish Sent",      "body": "Happy Birthday, Rakib! Hope your day as Senior Backend Engineer at Pathao is amazing...", "platform": "LinkedIn", "score": 9},
            {"type": "reply",    "date": datetime.now() - timedelta(days=3, hours=1),  "title": "Reply Received",    "body": "Thanks so much! Means a lot 🙏", "platform": "LinkedIn"},
            {"type": "system",   "date": datetime.now() - timedelta(days=3, hours=1, minutes=5), "title": "Relationship Health Updated", "body": "Health score moved to Good (replied within 1 hour)"},
            {"type": "wish",     "date": datetime.now() - timedelta(days=368), "title": "AI Wish Sent",      "body": "Happy Birthday Rakib! Wishing you a fantastic year ahead...", "platform": "LinkedIn", "score": 7},
            {"type": "reply",    "date": datetime.now() - timedelta(days=367), "title": "Reply Received",    "body": "Appreciate it, thank you!", "platform": "LinkedIn"},
        ],
    },
    {
        "name": "Nadia Islam", "job": "Product Designer", "company": "bKash",
        "platform": "WhatsApp", "health": "warn", "birthday": "June 20",
        "events": [
            {"type": "wish",     "date": datetime.now() - timedelta(days=1, hours=4), "title": "AI Wish Sent",     "body": "Happy Birthday Nadia! Hope your design work at bKash keeps shining...", "platform": "WhatsApp", "score": 8},
            {"type": "followup", "date": datetime.now() - timedelta(hours=6),         "title": "Follow-up Sent",   "body": "Auto follow-up triggered — no reply after 3 days"},
            {"type": "system",   "date": datetime.now() - timedelta(hours=6, minutes=2), "title": "Relationship Health Updated", "body": "Health score moved to Warning (no reply yet)"},
        ],
    },
    {
        "name": "Tanvir Ahmed", "job": "Founder", "company": "ShopUp",
        "platform": "LinkedIn", "health": "bad", "birthday": "May 30",
        "events": [
            {"type": "decay",    "date": datetime.now() - timedelta(days=2),  "title": "Relationship Decay Alert", "body": "No interaction in 94 days — consider a check-in message"},
            {"type": "wish",     "date": datetime.now() - timedelta(days=387), "title": "AI Wish Sent",     "body": "Happy Birthday Tanvir! Congrats on the new funding round...", "platform": "LinkedIn", "score": 9},
            {"type": "reply",    "date": datetime.now() - timedelta(days=386), "title": "Reply Received",   "body": "Thank you brother! 🚀", "platform": "LinkedIn"},
        ],
    },
    {
        "name": "Mim Chowdhury", "job": "Data Scientist", "company": "Brain Station 23",
        "platform": "WhatsApp", "health": "good", "birthday": "June 21",
        "events": [
            {"type": "wish",     "date": datetime.now() - timedelta(hours=3), "title": "AI Wish Sent",   "body": "Happy Birthday Mim! Can't believe it's been this long since uni — hope it's a great one!", "platform": "WhatsApp", "score": 10},
            {"type": "reply",    "date": datetime.now() - timedelta(hours=2), "title": "Reply Received", "body": "Haha thank you!! Miss those days 😄", "platform": "WhatsApp"},
        ],
    },
]

ICONS = {"wish": "🎂", "reply": "💬", "followup": "📩", "decay": "📉", "system": "⚙️"}
DOT_CLASS = {"wish": "tl-wish", "reply": "tl-reply", "followup": "tl-followup", "decay": "tl-decay", "system": "tl-system"}
HEALTH_CLASS = {"good": "health-good", "warn": "health-warn", "bad": "health-bad"}
HEALTH_LABEL = {"good": "Healthy", "warn": "Needs attention", "bad": "At risk"}

# ── Session state ─────────────────────────────────────────────────────────────
if "selected_contact_idx" not in st.session_state:
    st.session_state.selected_contact_idx = 0
if "event_filter" not in st.session_state:
    st.session_state.event_filter = "All"

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="cc-header">
  <span style="font-size:1.6rem">🕓</span>
  <h1>Contact Timeline View</h1>
  <span class="cc-badge">v7.0</span>
  <span class="cc-version">Birthday Wishes Agent</span>
</div>
""", unsafe_allow_html=True)

col_list, col_timeline = st.columns([1, 2.4], gap="large")

# ── LEFT: Contact list ────────────────────────────────────────────────────────
with col_list:
    st.markdown('<div class="section-title">Contacts</div>', unsafe_allow_html=True)

    search = st.text_input("Search", placeholder="🔍 Search contacts...", label_visibility="collapsed")

    for idx, c in enumerate(DEMO_CONTACTS):
        if search and search.lower() not in c["name"].lower() and search.lower() not in c["company"].lower():
            continue
        selected = idx == st.session_state.selected_contact_idx
        css = "contact-card selected" if selected else "contact-card"
        plat_icon = "💼" if c["platform"] == "LinkedIn" else "💬"
        last_event = c["events"][0]
        days_ago = (datetime.now() - last_event["date"]).days
        when = "today" if days_ago == 0 else f"{days_ago}d ago"

        st.markdown(f"""
        <div class="{css}">
          <div class="contact-name">
            <span class="health-dot {HEALTH_CLASS[c['health']]}"></span>
            {c['name']}
          </div>
          <div class="contact-meta">{plat_icon} {c['job']} · {c['company']}</div>
          <div class="contact-meta">Last activity: {when}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button(f"View timeline", key=f"select_{idx}", use_container_width=True):
            st.session_state.selected_contact_idx = idx
            st.rerun()

contact = DEMO_CONTACTS[st.session_state.selected_contact_idx]

# ── RIGHT: Profile + Timeline ─────────────────────────────────────────────────
with col_timeline:
    initials = "".join([p[0] for p in contact["name"].split()[:2]]).upper()
    total_wishes = sum(1 for e in contact["events"] if e["type"] == "wish")
    total_replies = sum(1 for e in contact["events"] if e["type"] == "reply")
    reply_rate = int((total_replies / total_wishes) * 100) if total_wishes else 0
    avg_score_events = [e["score"] for e in contact["events"] if e.get("score")]
    avg_score = round(sum(avg_score_events) / len(avg_score_events), 1) if avg_score_events else "—"

    st.markdown(f"""
    <div class="profile-card">
      <div class="profile-avatar">{initials}</div>
      <div>
        <div class="profile-name">{contact['name']}</div>
        <div class="profile-sub">{contact['job']} at {contact['company']} · 🎂 {contact['birthday']}</div>
        <div class="profile-sub">
          <span class="health-dot {HEALTH_CLASS[contact['health']]}"></span>
          &nbsp;{HEALTH_LABEL[contact['health']]} relationship
        </div>
      </div>
      <div class="profile-stats">
        <div class="pstat"><div class="pstat-val">{total_wishes}</div><div class="pstat-label">Wishes</div></div>
        <div class="pstat"><div class="pstat-val">{reply_rate}%</div><div class="pstat-label">Reply Rate</div></div>
        <div class="pstat"><div class="pstat-val">{avg_score}</div><div class="pstat-label">Avg Score</div></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Filter row
    filt_col1, filt_col2 = st.columns([3, 1])
    with filt_col1:
        filt = st.radio(
            "Filter",
            ["All", "Wishes", "Replies", "Follow-ups", "Alerts"],
            horizontal=True,
            label_visibility="collapsed",
        )
    with filt_col2:
        st.button("📤 Export", use_container_width=True)

    type_map = {
        "All": None, "Wishes": "wish", "Replies": "reply",
        "Follow-ups": "followup", "Alerts": "decay",
    }
    active_filter = type_map[filt]

    events = sorted(contact["events"], key=lambda e: e["date"], reverse=True)
    if active_filter:
        events = [e for e in events if e["type"] == active_filter]

    st.markdown('<div class="section-title">Timeline</div>', unsafe_allow_html=True)

    if not events:
        st.info("No events match this filter.")
    else:
        st.markdown('<div class="timeline">', unsafe_allow_html=True)
        last_year = None
        for e in events:
            this_year = e["date"].year
            if this_year != last_year:
                st.markdown(f'<div class="year-divider">{this_year}</div>', unsafe_allow_html=True)
                last_year = this_year

            time_str = e["date"].strftime("%b %d, %I:%M %p")
            score_tag = ""
            if e.get("score") is not None:
                s = e["score"]
                s_cls = "score-good" if s >= 8 else ("score-mid" if s >= 6 else "score-bad")
                score_tag = f'<span class="tl-score-tag {s_cls}">⭐ {s}/10</span>'
            platform_tag = f'<span class="tl-platform-tag">{e["platform"]}</span>' if e.get("platform") else ""

            st.markdown(f"""
            <div class="tl-item">
              <div class="tl-dot {DOT_CLASS[e['type']]}">{ICONS[e['type']]}</div>
              <div class="tl-card">
                <div class="tl-top">
                  <span class="tl-label">{e['title']}</span>
                  <span class="tl-time">{time_str}</span>
                </div>
                <div class="tl-body">{e['body']}</div>
                {platform_tag}{score_tag}
              </div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:center;
            font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
  <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">7.0</code></span>
  <span>Contact Timeline View</span>
  <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
</div>
""", unsafe_allow_html=True)
