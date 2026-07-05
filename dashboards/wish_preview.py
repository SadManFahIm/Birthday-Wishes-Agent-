"""
Real-time Wish Preview — Birthday Wishes Agent v7.0
Select a contact, AI-generate a wish, edit it live, and preview exactly how it
will render on the target platform (LinkedIn / WhatsApp / etc.) before sending.
"""

import streamlit as st
import sqlite3
import time
import random
from pathlib import Path
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Wish Preview",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling (matches Command Center theme) ────────────────────────────────────
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

/* Score badge */
.score-badge {
    display: inline-flex; align-items: center; gap: 6px; font-weight: 700;
    font-size: 1.4rem; padding: 6px 16px; border-radius: 10px;
}
.score-high { background: #051a09; color: var(--green); border: 1px solid var(--green); }
.score-mid  { background: #1a1500; color: var(--yellow); border: 1px solid var(--yellow); }
.score-low  { background: #1a0505; color: var(--red); border: 1px solid var(--red); }

.score-row { display: flex; justify-content: space-between; font-size: 0.78rem; padding: 5px 0; border-bottom: 1px solid #21262d; }
.score-row:last-child { border-bottom: none; }
.score-pts { font-family: 'JetBrains Mono', monospace; color: var(--green); font-weight: 600; }
.score-pts.zero { color: var(--muted); }

/* Platform preview frames */
.preview-frame {
    border-radius: 12px; padding: 16px; border: 1px solid var(--border);
    background: var(--surface); min-height: 140px;
}
.preview-linkedin { background: #1b1f23; border-color: #2a3744; }
.preview-whatsapp  { background: #0b141a; border-color: #1f3a30; }

.li-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.li-avatar { width: 38px; height: 38px; border-radius: 50%; background: linear-gradient(135deg,#f78166,#d29922); display:flex; align-items:center; justify-content:center; font-weight:700; color:#fff; font-size:0.9rem; }
.li-name { font-size: 0.85rem; font-weight: 600; color: var(--text); }
.li-sub { font-size: 0.7rem; color: var(--muted); }
.li-text { font-size: 0.82rem; line-height: 1.5; color: #e6edf3; white-space: pre-wrap; }

.wa-bubble {
    background: #005c4b; border-radius: 8px; padding: 10px 12px; max-width: 90%;
    margin-left: auto; font-size: 0.82rem; line-height: 1.5; color: #e9edef; white-space: pre-wrap;
    position: relative;
}
.wa-meta { font-size: 0.65rem; color: #8696a0; text-align: right; margin-top: 4px; }

.contact-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 14px; margin-bottom: 6px; cursor: pointer; transition: border-color 0.15s;
}
.contact-card:hover { border-color: var(--blue); }
.contact-card.selected { border-color: var(--accent); background: #1c1410; }
.contact-name { font-weight: 600; font-size: 0.85rem; }
.contact-meta { font-size: 0.7rem; color: var(--muted); }

div[data-testid="stButton"] > button {
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    border-radius: 8px; font-size: 0.82rem; font-weight: 500; transition: all 0.15s;
}
div[data-testid="stButton"] > button:hover { border-color: var(--blue); background: #1c2128; color: var(--text); }
div[data-testid="stButton"] > button[kind="primary"] { background: var(--accent); border-color: var(--accent); color: #fff; }
div[data-testid="stButton"] > button[kind="primary"]:hover { background: #e56d55; border-color: #e56d55; }

textarea { background: #0d1117 !important; color: #e6edf3 !important; border-color: var(--border) !important; font-size: 0.85rem !important; }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ── Demo contact data (swap with real DB query: SELECT * FROM contacts) ──────
DEMO_CONTACTS = [
    {"name": "Rakib Hossain", "job": "Senior Backend Engineer", "company": "Pathao", "platform": "LinkedIn", "memory": "you both talked about distributed systems at PyCon BD last year", "industry": "tech"},
    {"name": "Nadia Islam",   "job": "Product Designer",        "company": "bKash",  "platform": "WhatsApp", "memory": "she just shipped a big redesign for the app", "industry": "design"},
    {"name": "Tanvir Ahmed",  "job": "Founder",                 "company": "ShopUp", "platform": "LinkedIn", "memory": "he raised a new funding round last month", "industry": "startup"},
    {"name": "Mim Chowdhury", "job": "Data Scientist",          "company": "Brain Station 23", "platform": "WhatsApp", "memory": "you used to be university batchmates", "industry": "tech"},
]

# ── Session state ─────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "selected_contact_idx": 0,
        "wish_text": "",
        "generated_once": False,
        "manual_edit": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── Mock AI wish generator (swap with real LangChain/Gemini call) ────────────
TEMPLATES = [
    "Happy Birthday, {name}! 🎉 Hope your day as {job} at {company} is as great as the work you do. Remember {memory} — here's to another year of wins!",
    "Happy Birthday, {name}! 🎂 Wishing you an amazing year ahead at {company}. I still think about how {memory}. Take some time today just for you!",
    "Hey {name}, Happy Birthday! 🥳 Your work as {job} continues to inspire — and {memory}. Hope it's a great one!",
]

def generate_ai_wish(contact: dict) -> str:
    template = random.choice(TEMPLATES)
    return template.format(
        name=contact["name"].split()[0],
        job=contact["job"],
        company=contact["company"],
        memory=contact["memory"],
    )

def score_wish(text: str, contact: dict) -> dict:
    """Mirrors wish_personalization_score.py scoring logic for live preview."""
    score = 0
    breakdown = {}

    first_name = contact["name"].split()[0]
    has_name = first_name.lower() in text.lower()
    breakdown["Name mentioned"] = 2 if has_name else 0

    has_job = contact["job"].split()[-1].lower() in text.lower() or contact["company"].lower() in text.lower()
    breakdown["Job/company ref"] = 2 if has_job else 0

    has_industry = contact["industry"].lower() in text.lower()
    breakdown["Industry ref"] = 1 if has_industry else 0

    memory_keywords = contact["memory"].lower().split()[:3]
    has_memory = any(k in text.lower() for k in memory_keywords if len(k) > 3)
    breakdown["Memory/past context"] = 2 if has_memory else 0

    generic_phrases = ["have a great day", "best wishes", "many happy returns"]
    is_unique = not any(p in text.lower() for p in generic_phrases)
    breakdown["Unique language"] = 1 if is_unique else 0

    word_count = len(text.split())
    right_length = 15 <= word_count <= 60
    breakdown["Right length"] = 1 if right_length else 0

    warm_words = ["hope", "wishing", "amazing", "great", "celebrate", "🎉", "🎂", "🥳"]
    has_warmth = any(w in text.lower() for w in warm_words)
    breakdown["Warm tone"] = 1 if has_warmth else 0

    score = sum(breakdown.values())
    return {"score": score, "breakdown": breakdown}

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="cc-header">
  <span style="font-size:1.6rem">✨</span>
  <h1>Real-time Wish Preview</h1>
  <span class="cc-badge">v7.0</span>
  <span class="cc-version">Birthday Wishes Agent</span>
</div>
""", unsafe_allow_html=True)

# ── Layout: contact list | editor + score | platform preview ────────────────
col_contacts, col_editor, col_preview = st.columns([1, 1.5, 1.3], gap="large")

# ── Column 1: Contact picker ──────────────────────────────────────────────────
with col_contacts:
    st.markdown('<div class="section-title">Today\'s Birthdays</div>', unsafe_allow_html=True)
    for idx, c in enumerate(DEMO_CONTACTS):
        selected = idx == st.session_state.selected_contact_idx
        css = "contact-card selected" if selected else "contact-card"
        plat_icon = "💼" if c["platform"] == "LinkedIn" else "💬"
        st.markdown(f"""
        <div class="{css}">
          <div class="contact-name">{c['name']}</div>
          <div class="contact-meta">{plat_icon} {c['job']} · {c['company']}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button(f"Select {c['name'].split()[0]}", key=f"select_{idx}", use_container_width=True):
            st.session_state.selected_contact_idx = idx
            st.session_state.wish_text = ""
            st.session_state.generated_once = False
            st.rerun()

contact = DEMO_CONTACTS[st.session_state.selected_contact_idx]

# ── Column 2: AI generate + manual edit ───────────────────────────────────────
with col_editor:
    st.markdown('<div class="section-title">Generate & Edit</div>', unsafe_allow_html=True)

    gen_col1, gen_col2 = st.columns([1, 1])
    with gen_col1:
        if st.button("✨ Generate AI Wish", type="primary", use_container_width=True):
            with st.spinner("Generating..."):
                time.sleep(0.4)
                st.session_state.wish_text = generate_ai_wish(contact)
                st.session_state.generated_once = True
            st.rerun()
    with gen_col2:
        if st.button("🔁 Regenerate", use_container_width=True, disabled=not st.session_state.generated_once):
            with st.spinner("Regenerating..."):
                time.sleep(0.4)
                st.session_state.wish_text = generate_ai_wish(contact)
            st.rerun()

    wish_text = st.text_area(
        "Edit wish (updates preview live)",
        value=st.session_state.wish_text,
        height=180,
        key="wish_editor",
        placeholder="Click 'Generate AI Wish' or start typing your own...",
    )
    st.session_state.wish_text = wish_text

    word_count = len(wish_text.split()) if wish_text else 0
    char_count = len(wish_text)
    st.caption(f"📝 {word_count} words · {char_count} characters · target platform: **{contact['platform']}**")

    # ── Live score ────────────────────────────────────────────────────────────
    if wish_text.strip():
        result = score_wish(wish_text, contact)
        score = result["score"]

        if score >= 8:
            badge_cls, badge_label = "score-high", f"⭐ {score}/10"
        elif score >= 6:
            badge_cls, badge_label = "score-mid", f"⚡ {score}/10"
        else:
            badge_cls, badge_label = "score-low", f"⚠️ {score}/10"

        st.markdown(f'<div class="section-title">Personalization Score</div>', unsafe_allow_html=True)
        st.markdown(f'<span class="score-badge {badge_cls}">{badge_label}</span>', unsafe_allow_html=True)

        if score < 6:
            st.warning("Score below 6 — auto-retry would trigger here in live mode.")

        rows = ""
        for label, pts in result["breakdown"].items():
            pts_cls = "score-pts" if pts > 0 else "score-pts zero"
            max_pts = {"Name mentioned": 2, "Job/company ref": 2, "Industry ref": 1,
                       "Memory/past context": 2, "Unique language": 1, "Right length": 1, "Warm tone": 1}[label]
            rows += f'<div class="score-row"><span>{label}</span><span class="{pts_cls}">+{pts}/{max_pts}</span></div>'
        st.markdown(f'<div class="preview-frame">{rows}</div>', unsafe_allow_html=True)
    else:
        st.info("Generate or type a wish to see the live personalization score.")

# ── Column 3: Platform preview ────────────────────────────────────────────────
with col_preview:
    st.markdown('<div class="section-title">Platform Preview</div>', unsafe_allow_html=True)

    initials = "".join([p[0] for p in contact["name"].split()[:2]]).upper()
    now_str = datetime.now().strftime("%I:%M %p")

    if not wish_text.strip():
        st.markdown(f"""
        <div class="preview-frame" style="display:flex;align-items:center;justify-content:center;color:#8b949e;font-size:0.8rem;">
          Preview will appear here
        </div>
        """, unsafe_allow_html=True)
    elif contact["platform"] == "LinkedIn":
        st.markdown(f"""
        <div class="preview-frame preview-linkedin">
          <div class="li-header">
            <div class="li-avatar">{initials}</div>
            <div>
              <div class="li-name">You</div>
              <div class="li-sub">to {contact['name']} · just now</div>
            </div>
          </div>
          <div class="li-text">{wish_text}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="preview-frame preview-whatsapp">
          <div class="wa-bubble">
            {wish_text}
            <div class="wa-meta">{now_str} ✓✓</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    send_col1, send_col2 = st.columns(2)
    with send_col1:
        st.button("📤 Send Now", type="primary", use_container_width=True, disabled=not wish_text.strip())
    with send_col2:
        st.button("📅 Schedule", use_container_width=True, disabled=not wish_text.strip())

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:center;
            font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
  <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">7.0</code></span>
  <span>Real-time Wish Preview</span>
  <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
</div>
""", unsafe_allow_html=True)
