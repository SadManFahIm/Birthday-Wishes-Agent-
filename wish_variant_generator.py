"""
Multi-Wish Variant Generator — Birthday Wishes Agent v8.0
Generates 3 distinct birthday wish variants (formal / casual / funny) simultaneously,
displays them side-by-side with live personalization scores, and lets the user
pick one to send — or manually edit any of them before sending.

Integrates with: wish_style_memory.py, wish_personalization_score.py, agent.py
"""

import streamlit as st
import sqlite3
import time
import random
from pathlib import Path
from datetime import datetime

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Wish Variants",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Theme (matches Command Center palette) ────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

:root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --accent: #f78166; --green: #3fb950; --yellow: #d29922;
    --red: #f85149; --blue: #58a6ff; --muted: #8b949e; --text: #e6edf3;
    --purple: #bc8cff;
}
.stApp { background: var(--bg); color: var(--text); }

.cc-header {
    display: flex; align-items: center; gap: 14px;
    padding: 18px 0 10px; border-bottom: 1px solid var(--border); margin-bottom: 24px;
}
.cc-header h1 { font-size: 1.4rem; font-weight: 700; letter-spacing: -0.02em; margin: 0; }
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

/* Variant card */
.variant-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 18px; height: 100%;
    transition: border-color 0.15s;
}
.variant-card.selected { border-color: var(--green); background: #0a1f10; }
.variant-card.winner   { border-color: var(--accent); background: #1c1410; }

.variant-header {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
}
.style-pill {
    font-size: 0.7rem; font-weight: 700; padding: 3px 10px; border-radius: 20px;
    text-transform: uppercase; letter-spacing: 0.07em;
}
.pill-formal     { background: #1a2a3a; color: var(--blue); }
.pill-casual     { background: #1a3a1a; color: var(--green); }
.pill-funny      { background: #3a2a00; color: var(--yellow); }
.pill-poetic     { background: #2a1a3a; color: var(--purple); }
.pill-warm       { background: #3a1a10; color: var(--accent); }
.pill-motivational { background: #0a2a2a; color: #4fc3f7; }

.score-chip {
    font-size: 0.75rem; font-weight: 700; padding: 2px 9px;
    border-radius: 20px; font-family: 'JetBrains Mono', monospace;
}
.chip-high { background: #051a09; color: var(--green); border: 1px solid var(--green); }
.chip-mid  { background: #1a1500; color: var(--yellow); border: 1px solid var(--yellow); }
.chip-low  { background: #1a0505; color: var(--red); border: 1px solid var(--red); }

.wish-text {
    font-size: 0.83rem; line-height: 1.65; color: #c9d1d9;
    white-space: pre-wrap; min-height: 90px;
    padding: 10px 12px; background: #0d1117;
    border: 1px solid var(--border); border-radius: 8px;
    margin-bottom: 12px;
}

.score-breakdown { font-size: 0.72rem; }
.sb-row {
    display: flex; justify-content: space-between; padding: 3px 0;
    border-bottom: 1px solid #21262d;
}
.sb-row:last-child { border-bottom: none; }
.sb-pts { font-family: 'JetBrains Mono', monospace; font-weight: 600; }
.pts-on  { color: var(--green); }
.pts-off { color: var(--muted); }

/* Platform preview */
.wa-bubble {
    background: #005c4b; border-radius: 8px; padding: 10px 12px;
    font-size: 0.78rem; line-height: 1.5; color: #e9edef;
    white-space: pre-wrap; margin-top: 8px;
}
.wa-meta { font-size: 0.62rem; color: #8696a0; text-align: right; margin-top: 4px; }
.li-post {
    background: #1b1f23; border: 1px solid #2a3744; border-radius: 8px;
    padding: 10px 12px; font-size: 0.78rem; color: #e6edf3; line-height: 1.5;
    white-space: pre-wrap; margin-top: 8px;
}

/* Winner banner */
.winner-banner {
    background: linear-gradient(90deg, #051a09, #0a2a10);
    border: 1px solid var(--green); border-radius: 10px;
    padding: 14px 18px; display: flex; align-items: center; gap: 12px;
    margin-bottom: 20px;
}
.winner-banner .wb-label { font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
.winner-banner .wb-text  { font-size: 0.88rem; color: var(--text); line-height: 1.5; }

/* Streamlit overrides */
div[data-testid="stButton"] > button {
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    border-radius: 8px; font-size: 0.8rem; font-weight: 500; transition: all 0.15s;
}
div[data-testid="stButton"] > button:hover  { border-color: var(--blue); background: #1c2128; }
div[data-testid="stButton"] > button[kind="primary"] { background: var(--accent); border-color: var(--accent); color: #fff; }
div[data-testid="stButton"] > button[kind="primary"]:hover { background: #e56d55; }

textarea {
    background: #0d1117 !important; color: #e6edf3 !important;
    border-color: var(--border) !important; font-size: 0.83rem !important;
}
::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ── Demo data ─────────────────────────────────────────────────────────────────
DEMO_CONTACTS = [
    {"id": "urn_rakib_001",  "name": "Rakib Hossain", "job": "Senior Backend Engineer", "company": "Pathao",         "platform": "LinkedIn", "memory": "you talked about distributed systems at PyCon BD", "industry": "tech"},
    {"id": "urn_nadia_002",  "name": "Nadia Islam",   "job": "Product Designer",        "company": "bKash",          "platform": "WhatsApp", "memory": "she just shipped a major redesign",             "industry": "design"},
    {"id": "urn_tanvir_003", "name": "Tanvir Ahmed",  "job": "Founder",                 "company": "ShopUp",         "platform": "LinkedIn", "memory": "he raised a new round last month",              "industry": "startup"},
    {"id": "urn_mim_004",    "name": "Mim Chowdhury", "job": "Data Scientist",          "company": "Brain Station 23","platform": "WhatsApp","memory": "you were university batchmates",                "industry": "tech"},
]

# Variant styles generated — 3 shown side-by-side
VARIANTS = [
    {"style": "formal",  "label": "Formal",  "pill": "pill-formal",  "emoji": "🤝"},
    {"style": "casual",  "label": "Casual",  "pill": "pill-casual",  "emoji": "😊"},
    {"style": "funny",   "label": "Funny",   "pill": "pill-funny",   "emoji": "😄"},
]

# ── Wish generation (mock — swap with Gemini/GPT-4o call using style prompt) ──
WISH_TEMPLATES = {
    "formal": [
        "Dear {first}, on the occasion of your birthday, I wanted to take a moment to wish you continued success in your role as {job} at {company}. Your {memory_ref} reflects the caliber of professional you are. Wishing you a wonderful year ahead.",
        "Happy Birthday, {first}. Your dedication as {job} at {company} is something I genuinely admire. I hope this year brings you new milestones worth celebrating. Best wishes.",
    ],
    "casual": [
        "Hey {first}! 🎉 Happy Birthday! Hope your day is as amazing as the work you do at {company}. Still thinking about {memory_ref} — you've come a long way. Enjoy every bit of today!",
        "Happy Birthday {first}! 🎂 Can't believe another year has gone by. Your work at {company} keeps getting better and better. Have an awesome one — you deserve it!",
    ],
    "funny": [
        "Happy Birthday {first}! 🎈 Another year wiser, another year of pretending to know what you're doing at {company} — just kidding, you're clearly the one who actually does! Hope it's a great one. 🎂",
        "Happy Birthday {first}! 😄 Officially one year closer to being the most experienced person in the room at {company}. I'm told that's called 'seniority', not 'old'. Enjoy the day! 🎉",
    ],
}

MEMORY_REFS = {
    "tech":    "how you tackled that architectural challenge",
    "design":  "the design thinking you bring to every project",
    "startup": "your entrepreneurial drive and vision",
    "default": "the conversations we've had",
}

def generate_variant(contact: dict, style: str) -> str:
    templates = WISH_TEMPLATES.get(style, WISH_TEMPLATES["casual"])
    template  = random.choice(templates)
    first     = contact["name"].split()[0]
    memory_ref = MEMORY_REFS.get(contact["industry"], MEMORY_REFS["default"])
    return template.format(
        first=first,
        job=contact["job"],
        company=contact["company"],
        memory_ref=memory_ref,
    )

# ── Personalization scorer (mirrors wish_personalization_score.py) ─────────────
def score_wish(text: str, contact: dict) -> dict:
    score = 0
    bd = {}
    first = contact["name"].split()[0]
    bd["Name mentioned"]      = 2 if first.lower() in text.lower() else 0
    has_job = (contact["job"].split()[-1].lower() in text.lower() or contact["company"].lower() in text.lower())
    bd["Job/company ref"]     = 2 if has_job else 0
    bd["Industry ref"]        = 1 if contact["industry"].lower() in text.lower() else 0
    mem_kw = contact["memory"].lower().split()[:4]
    bd["Memory/past context"] = 2 if any(k in text.lower() for k in mem_kw if len(k) > 3) else 0
    generic = ["have a great day", "best wishes", "many happy returns"]
    bd["Unique language"]     = 1 if not any(p in text.lower() for p in generic) else 0
    wc = len(text.split())
    bd["Right length"]        = 1 if 15 <= wc <= 70 else 0
    warm = ["hope", "wishing", "amazing", "great", "celebrate", "🎉", "🎂", "🥳", "awesome"]
    bd["Warm tone"]           = 1 if any(w in text.lower() for w in warm) else 0
    return {"score": sum(bd.values()), "breakdown": bd}

# ── Session state ─────────────────────────────────────────────────────────────
def _init():
    defaults = {
        "contact_idx":  0,
        "variants":     {},   # style → text
        "generated":    False,
        "selected":     None, # style of chosen variant
        "editing":      None, # style being edited
        "edit_text":    {},   # style → edited text
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init()

contact = DEMO_CONTACTS[st.session_state.contact_idx]

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="cc-header">
  <span style="font-size:1.6rem">🎨</span>
  <h1>Multi-Wish Variant Generator</h1>
  <span class="cc-badge">v8.0</span>
  <span class="cc-version">Birthday Wishes Agent</span>
</div>
""", unsafe_allow_html=True)

# ── Top row: contact picker + generate ────────────────────────────────────────
top_left, top_right = st.columns([2, 1], gap="large")

with top_left:
    st.markdown('<div class="section-title">Contact</div>', unsafe_allow_html=True)
    names = [c["name"] for c in DEMO_CONTACTS]
    choice = st.selectbox("Select contact", names, index=st.session_state.contact_idx,
                          label_visibility="collapsed")
    new_idx = names.index(choice)
    if new_idx != st.session_state.contact_idx:
        st.session_state.contact_idx = new_idx
        st.session_state.variants    = {}
        st.session_state.generated   = False
        st.session_state.selected    = None
        st.session_state.editing     = None
        st.session_state.edit_text   = {}
        st.rerun()
    contact = DEMO_CONTACTS[st.session_state.contact_idx]
    plat_icon = "💼" if contact["platform"] == "LinkedIn" else "💬"
    st.caption(f"{plat_icon} {contact['job']} · {contact['company']} · {contact['platform']}")

with top_right:
    st.markdown('<div class="section-title">Generate</div>', unsafe_allow_html=True)
    btn_label = "🔁 Regenerate All" if st.session_state.generated else "✨ Generate 3 Variants"
    if st.button(btn_label, type="primary", use_container_width=True):
        with st.spinner("Generating formal, casual, and funny variants..."):
            time.sleep(0.6)
            for v in VARIANTS:
                st.session_state.variants[v["style"]] = generate_variant(contact, v["style"])
                st.session_state.edit_text[v["style"]] = st.session_state.variants[v["style"]]
            st.session_state.generated = True
            st.session_state.selected  = None
            st.session_state.editing   = None
        st.rerun()

# ── Winner banner ─────────────────────────────────────────────────────────────
if st.session_state.selected:
    sel   = st.session_state.selected
    final = st.session_state.edit_text.get(sel, st.session_state.variants.get(sel, ""))
    style_label = next((v["label"] for v in VARIANTS if v["style"] == sel), sel.title())
    st.markdown(f"""
    <div class="winner-banner">
      <span style="font-size:1.4rem">✅</span>
      <div>
        <div class="wb-label">Selected variant · {style_label}</div>
        <div class="wb-text">{final[:120]}{"…" if len(final) > 120 else ""}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    send_col1, send_col2, send_col3 = st.columns(3)
    with send_col1:
        if st.button("📤 Send Now", type="primary", use_container_width=True):
            st.success(f"Wish sent via {contact['platform']}! ✅")
    with send_col2:
        if st.button("📅 Schedule for 9 AM", use_container_width=True):
            st.info("Scheduled for 09:00 AM contact's local time.")
    with send_col3:
        if st.button("↩ Deselect", use_container_width=True):
            st.session_state.selected = None
            st.rerun()

# ── Variant columns ────────────────────────────────────────────────────────────
if not st.session_state.generated:
    st.markdown("""
    <div style="text-align:center; padding: 60px 20px; color: #8b949e; font-size: 0.9rem;">
      Select a contact and click <strong style="color:#e6edf3">Generate 3 Variants</strong> to see formal, casual, and funny wishes side-by-side.
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown('<div class="section-title">Choose a Variant</div>', unsafe_allow_html=True)
    cols = st.columns(3, gap="medium")

    for col, variant in zip(cols, VARIANTS):
        style      = variant["style"]
        wish_text  = st.session_state.edit_text.get(style, st.session_state.variants.get(style, ""))
        scored     = score_wish(wish_text, contact)
        score      = scored["score"]
        breakdown  = scored["breakdown"]
        is_selected = st.session_state.selected == style
        is_editing  = st.session_state.editing  == style

        # Score chip
        if score >= 8:
            chip_cls, chip_icon = "chip-high", "⭐"
        elif score >= 6:
            chip_cls, chip_icon = "chip-mid",  "⚡"
        else:
            chip_cls, chip_icon = "chip-low",  "⚠️"

        card_cls = "variant-card selected" if is_selected else "variant-card"

        with col:
            st.markdown(f"""
            <div class="{card_cls}">
              <div class="variant-header">
                <span class="style-pill {variant['pill']}">{variant['emoji']} {variant['label']}</span>
                <span class="score-chip {chip_cls}">{chip_icon} {score}/10</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Editable text area or read-only display
            if is_editing:
                edited = st.text_area(
                    "Edit wish",
                    value=wish_text,
                    height=160,
                    key=f"edit_area_{style}",
                    label_visibility="collapsed",
                )
                st.session_state.edit_text[style] = edited

                done_col, cancel_col = st.columns(2)
                with done_col:
                    if st.button("✓ Done", key=f"done_{style}", use_container_width=True):
                        st.session_state.editing = None
                        st.rerun()
                with cancel_col:
                    if st.button("✕ Cancel", key=f"cancel_{style}", use_container_width=True):
                        st.session_state.edit_text[style] = st.session_state.variants[style]
                        st.session_state.editing = None
                        st.rerun()
            else:
                st.markdown(f'<div class="wish-text">{wish_text}</div>', unsafe_allow_html=True)

                # Action buttons
                pick_col, edit_col, regen_col = st.columns(3)
                with pick_col:
                    btn_label = "✅ Picked" if is_selected else "Pick"
                    if st.button(btn_label, key=f"pick_{style}", use_container_width=True,
                                 type="primary" if is_selected else "secondary"):
                        st.session_state.selected = None if is_selected else style
                        st.rerun()
                with edit_col:
                    if st.button("✏️ Edit", key=f"edit_{style}", use_container_width=True):
                        st.session_state.editing = style
                        st.rerun()
                with regen_col:
                    if st.button("🔁", key=f"regen_{style}", use_container_width=True,
                                 help=f"Regenerate {style} variant only"):
                        with st.spinner(""):
                            time.sleep(0.3)
                            new_text = generate_variant(contact, style)
                            st.session_state.variants[style]  = new_text
                            st.session_state.edit_text[style] = new_text
                        st.rerun()

            # Score breakdown (collapsed)
            with st.expander("Score breakdown", expanded=False):
                MAX_PTS = {"Name mentioned": 2, "Job/company ref": 2, "Industry ref": 1,
                           "Memory/past context": 2, "Unique language": 1, "Right length": 1, "Warm tone": 1}
                rows_html = ""
                for label, pts in breakdown.items():
                    cls = "pts-on" if pts > 0 else "pts-off"
                    rows_html += f'<div class="sb-row score-breakdown"><span>{label}</span><span class="sb-pts {cls}">+{pts}/{MAX_PTS[label]}</span></div>'
                st.markdown(f'<div>{rows_html}</div>', unsafe_allow_html=True)

            # Platform preview
            with st.expander("Platform preview", expanded=False):
                now_str = datetime.now().strftime("%I:%M %p")
                if contact["platform"] == "WhatsApp":
                    st.markdown(f"""
                    <div class="wa-bubble">{wish_text}
                    <div class="wa-meta">{now_str} ✓✓</div></div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="li-post">{wish_text}</div>', unsafe_allow_html=True)

# ── Comparison table ──────────────────────────────────────────────────────────
if st.session_state.generated:
    st.markdown('<div class="section-title">Score Comparison</div>', unsafe_allow_html=True)
    rows_data = []
    for v in VARIANTS:
        style     = v["style"]
        text      = st.session_state.edit_text.get(style, "")
        scored    = score_wish(text, contact)
        rows_data.append({
            "Style":      f"{v['emoji']} {v['label']}",
            "Score":      f"{scored['score']}/10",
            "Words":      len(text.split()),
            "Characters": len(text),
            "Selected":   "✅" if st.session_state.selected == style else "",
        })
    st.dataframe(rows_data, use_container_width=True, hide_index=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:center;
            font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
  <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
  <span>Multi-Wish Variant Generator</span>
  <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
</div>
""", unsafe_allow_html=True)
