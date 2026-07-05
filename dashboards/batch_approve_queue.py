"""
Batch Approve Queue — Birthday Wishes Agent v8.0
Every morning's AI-generated wishes land here. Review, edit, approve,
or reject them all from one screen — then send the approved batch in one click.

Queue states: pending → approved / rejected / sent / edited+approved
Integrates with: agent.py, wish_style_memory.py, wish_personalization_score.py
"""

import streamlit as st
import sqlite3
import json
import uuid
import time
import random
from pathlib import Path
from datetime import datetime, date

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Batch Approve Queue",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Theme ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

:root {
    --bg:#0d1117; --surface:#161b22; --border:#30363d;
    --accent:#f78166; --green:#3fb950; --yellow:#d29922;
    --red:#f85149; --blue:#58a6ff; --muted:#8b949e; --text:#e6edf3;
    --purple:#bc8cff;
}
.stApp { background:var(--bg); color:var(--text); }

.cc-header {
    display:flex; align-items:center; gap:14px;
    padding:18px 0 10px; border-bottom:1px solid var(--border); margin-bottom:24px;
}
.cc-header h1 { font-size:1.4rem; font-weight:700; letter-spacing:-0.02em; margin:0; }
.cc-badge {
    background:var(--accent); color:#fff; font-size:0.65rem; font-weight:700;
    padding:2px 8px; border-radius:20px; letter-spacing:0.08em; text-transform:uppercase;
}
.cc-version { margin-left:auto; font-size:0.75rem; color:var(--muted); font-family:'JetBrains Mono',monospace; }

.section-title {
    font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.1em;
    color:var(--muted); margin:22px 0 10px; display:flex; align-items:center; gap:8px;
}
.section-title::after { content:''; flex:1; height:1px; background:var(--border); }

/* Queue row card */
.q-row {
    background:var(--surface); border:1px solid var(--border); border-radius:10px;
    padding:14px 16px; margin-bottom:8px; transition:border-color 0.12s;
}
.q-row.approved  { border-left:3px solid var(--green); }
.q-row.rejected  { border-left:3px solid var(--red);   opacity:0.6; }
.q-row.sent      { border-left:3px solid var(--blue);  opacity:0.55; }
.q-row.pending   { border-left:3px solid var(--yellow);}
.q-row.edited    { border-left:3px solid var(--purple);}

.q-contact { font-weight:700; font-size:0.88rem; }
.q-meta    { font-size:0.7rem; color:var(--muted); margin-top:2px; }
.q-wish    { font-size:0.8rem; color:#c9d1d9; line-height:1.5;
             background:#0d1117; border:1px solid var(--border);
             border-radius:6px; padding:8px 10px; margin:8px 0; white-space:pre-wrap; }

/* Status pill */
.spill {
    display:inline-flex; align-items:center; gap:4px; font-size:0.65rem;
    font-weight:700; padding:2px 8px; border-radius:20px;
    text-transform:uppercase; letter-spacing:0.06em;
}
.sp-pending  { background:#1a1500; color:var(--yellow); border:1px solid var(--yellow); }
.sp-approved { background:#051a09; color:var(--green);  border:1px solid var(--green); }
.sp-rejected { background:#1a0505; color:var(--red);    border:1px solid var(--red); }
.sp-sent     { background:#0a1020; color:var(--blue);   border:1px solid var(--blue); }
.sp-edited   { background:#1a0a2a; color:var(--purple); border:1px solid var(--purple); }

/* Score chip */
.sc { display:inline-flex; font-size:0.65rem; font-weight:700; padding:1px 7px;
      border-radius:20px; font-family:'JetBrains Mono',monospace; margin-left:6px; }
.sc-hi  { background:#051a09; color:var(--green); }
.sc-mid { background:#1a1500; color:var(--yellow); }
.sc-lo  { background:#1a0505; color:var(--red); }

/* Stat cards */
.stat-card {
    background:var(--surface); border:1px solid var(--border); border-radius:10px;
    padding:14px 16px; text-align:center;
}
.stat-val   { font-size:1.8rem; font-weight:700; line-height:1; }
.stat-label { font-size:0.62rem; color:var(--muted); text-transform:uppercase;
              letter-spacing:0.08em; margin-top:4px; }

/* Send banner */
.send-banner {
    background:linear-gradient(90deg,#051a09,#0a2a10);
    border:1px solid var(--green); border-radius:10px;
    padding:14px 18px; display:flex; align-items:center; gap:14px; margin-bottom:18px;
}

/* Streamlit overrides */
div[data-testid="stButton"] > button {
    background:var(--surface); border:1px solid var(--border); color:var(--text);
    border-radius:8px; font-size:0.78rem; font-weight:500; transition:all 0.12s;
}
div[data-testid="stButton"] > button:hover { border-color:var(--blue); background:#1c2128; }
div[data-testid="stButton"] > button[kind="primary"] {
    background:var(--accent); border-color:var(--accent); color:#fff;
}
div[data-testid="stButton"] > button[kind="primary"]:hover { background:#e56d55; }
textarea { background:#0d1117 !important; color:#e6edf3 !important;
           border-color:var(--border) !important; font-size:0.8rem !important; }
div[data-testid="stSelectbox"] > div { background:var(--surface) !important; border-color:var(--border) !important; }
div[data-testid="stCheckbox"] label { font-size:0.82rem; color:var(--text) !important; }
::-webkit-scrollbar { width:6px; } ::-webkit-scrollbar-track { background:var(--bg); }
::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }
</style>
""", unsafe_allow_html=True)

# ── DB setup ───────────────────────────────────────────────────────────────────
DB_PATH = Path("agent_history.db")

def init_queue_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wish_queue (
            id            TEXT PRIMARY KEY,
            contact_id    TEXT NOT NULL,
            contact_name  TEXT NOT NULL,
            platform      TEXT NOT NULL,
            wish_text     TEXT NOT NULL,
            edited_text   TEXT,
            style         TEXT,
            score         INTEGER,
            status        TEXT NOT NULL DEFAULT 'pending',
            queue_date    TEXT NOT NULL,
            sent_at       TEXT,
            created_at    TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def seed_demo_queue():
    """Seed realistic demo data if queue is empty for today."""
    conn = sqlite3.connect(DB_PATH)
    today = date.today().isoformat()
    count = conn.execute("SELECT COUNT(*) FROM wish_queue WHERE queue_date = ?", (today,)).fetchone()[0]
    if count == 0:
        demo = [
            {
                "id": str(uuid.uuid4()), "contact_id": "urn_rakib_001",
                "contact_name": "Rakib Hossain", "platform": "LinkedIn",
                "wish_text": "Hey Rakib! Happy Birthday 🎉 Hope your day as Senior Backend Engineer at Pathao is as solid as your distributed systems. Still think about that PyCon BD talk — you've come a long way! Wishing you a brilliant year ahead.",
                "style": "casual", "score": 9, "status": "pending",
            },
            {
                "id": str(uuid.uuid4()), "contact_id": "urn_nadia_002",
                "contact_name": "Nadia Islam", "platform": "WhatsApp",
                "wish_text": "Happy Birthday Nadia! 😊🎂 Your design work at bKash keeps getting better and better. The redesign you just shipped was genuinely impressive. Have an amazing day — you deserve it! 🌟",
                "style": "warm", "score": 8, "status": "pending",
            },
            {
                "id": str(uuid.uuid4()), "contact_id": "urn_tanvir_003",
                "contact_name": "Tanvir Ahmed", "platform": "LinkedIn",
                "wish_text": "Happy Birthday Tanvir. Wishing you continued success as Founder of ShopUp. Your recent funding announcement was well-deserved recognition of the team's hard work. May this year bring new milestones.",
                "style": "formal", "score": 7, "status": "pending",
            },
            {
                "id": str(uuid.uuid4()), "contact_id": "urn_mim_004",
                "contact_name": "Mim Chowdhury", "platform": "WhatsApp",
                "wish_text": "Happy Birthday!! 🥳🎊 Can't believe we've been out of uni this long! Hope your data science work at Brain Station 23 is going amazing. Celebrate properly today! 🎂🎉",
                "style": "funny", "score": 8, "status": "pending",
            },
            {
                "id": str(uuid.uuid4()), "contact_id": "urn_sara_005",
                "contact_name": "Sara Khan", "platform": "LinkedIn",
                "wish_text": "Happy Birthday Sara! Wishing you a wonderful day.",
                "style": "formal", "score": 3, "status": "pending",
            },
            {
                "id": str(uuid.uuid4()), "contact_id": "urn_imran_006",
                "contact_name": "Imran Hossain", "platform": "Slack",
                "wish_text": "🚀🔥 Happy Birthday Imran!! Another year of shipping great products — keep crushing it! 🎉💯",
                "style": "motivational", "score": 6, "status": "pending",
            },
            {
                "id": str(uuid.uuid4()), "contact_id": "urn_farah_007",
                "contact_name": "Farah Akter", "platform": "Facebook",
                "wish_text": "Like the seasons that turn, another year graces your path — Happy Birthday Farah. May it bring clarity, growth, and quiet joy.",
                "style": "poetic", "score": 7, "status": "pending",
            },
        ]
        for d in demo:
            conn.execute("""
                INSERT INTO wish_queue
                    (id, contact_id, contact_name, platform, wish_text, style, score,
                     status, queue_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (d["id"], d["contact_id"], d["contact_name"], d["platform"],
                  d["wish_text"], d["style"], d["score"], d["status"],
                  today, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def load_queue(queue_date: str = None) -> list[dict]:
    init_queue_table()
    seed_demo_queue()
    conn = sqlite3.connect(DB_PATH)
    qd   = queue_date or date.today().isoformat()
    rows = conn.execute("""
        SELECT id, contact_id, contact_name, platform, wish_text, edited_text,
               style, score, status, queue_date, sent_at, created_at
        FROM wish_queue WHERE queue_date = ? ORDER BY score DESC, created_at ASC
    """, (qd,)).fetchall()
    conn.close()
    return [{
        "id": r[0], "contact_id": r[1], "contact_name": r[2], "platform": r[3],
        "wish_text": r[4], "edited_text": r[5], "style": r[6], "score": r[7],
        "status": r[8], "queue_date": r[9], "sent_at": r[10], "created_at": r[11],
    } for r in rows]

def update_status(item_id: str, status: str, edited_text: str = None):
    init_queue_table()
    conn = sqlite3.connect(DB_PATH)
    if edited_text is not None:
        conn.execute("UPDATE wish_queue SET status=?, edited_text=? WHERE id=?",
                     (status, edited_text, item_id))
    else:
        conn.execute("UPDATE wish_queue SET status=? WHERE id=?", (status, item_id))
    conn.commit()
    conn.close()

def mark_sent(item_id: str):
    init_queue_table()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE wish_queue SET status='sent', sent_at=? WHERE id=?",
                 (datetime.now().isoformat(), item_id))
    conn.commit()
    conn.close()

def bulk_update(item_ids: list[str], status: str):
    init_queue_table()
    conn = sqlite3.connect(DB_PATH)
    for iid in item_ids:
        conn.execute("UPDATE wish_queue SET status=? WHERE id=?", (status, iid))
    conn.commit()
    conn.close()

def regenerate_wish(item: dict) -> str:
    """Mock regen — swap with real AI call in production."""
    templates = [
        f"Happy Birthday {item['contact_name'].split()[0]}! 🎉 Wishing you a fantastic year filled with growth and great moments. Hope today is as amazing as you are!",
        f"Hey {item['contact_name'].split()[0]}, Happy Birthday! 🎂 Another year wiser — and from what I can see, you're making every one count. Enjoy your day!",
        f"Wishing you a very Happy Birthday {item['contact_name'].split()[0]}! May this year bring you everything you've been working toward. Celebrate well! 🌟",
    ]
    return random.choice(templates)

# ── Session state ─────────────────────────────────────────────────────────────
def _init():
    defaults = {
        "editing_id":  None,
        "edit_buffer": {},
        "selected":    set(),
        "dry_run":     True,
        "filter":      "All",
        "sent_log":    [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init()

init_queue_table()
queue = load_queue()

PLAT_ICON = {"LinkedIn":"💼","WhatsApp":"💬","Facebook":"📘","Instagram":"📸","Twitter/X":"🐦","Slack":"⚡","Facebook":"📘"}
STATUS_PILL = {
    "pending":  '<span class="spill sp-pending">⏳ Pending</span>',
    "approved": '<span class="spill sp-approved">✅ Approved</span>',
    "rejected": '<span class="spill sp-rejected">✕ Rejected</span>',
    "sent":     '<span class="spill sp-sent">📤 Sent</span>',
    "edited":   '<span class="spill sp-edited">✏️ Edited</span>',
}

def score_chip(score):
    if score is None: return ""
    if score >= 8: return f'<span class="sc sc-hi">⭐ {score}/10</span>'
    if score >= 6: return f'<span class="sc sc-mid">⚡ {score}/10</span>'
    return f'<span class="sc sc-lo">⚠️ {score}/10</span>'

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="cc-header">
  <span style="font-size:1.6rem">📋</span>
  <h1>Batch Approve Queue</h1>
  <span class="cc-badge">v8.0</span>
  <span class="cc-version">Birthday Wishes Agent</span>
</div>
""", unsafe_allow_html=True)

# ── Stats row ─────────────────────────────────────────────────────────────────
total    = len(queue)
pending  = sum(1 for q in queue if q["status"] == "pending")
approved = sum(1 for q in queue if q["status"] in ("approved","edited"))
rejected = sum(1 for q in queue if q["status"] == "rejected")
sent     = sum(1 for q in queue if q["status"] == "sent")
low_score= sum(1 for q in queue if (q["score"] or 10) < 6)

s1,s2,s3,s4,s5,s6 = st.columns(6)
for col, label, val, color in [
    (s1,"Total Today",   total,    "#e6edf3"),
    (s2,"Pending",       pending,  "#d29922"),
    (s3,"Approved",      approved, "#3fb950"),
    (s4,"Rejected",      rejected, "#f85149"),
    (s5,"Sent",          sent,     "#58a6ff"),
    (s6,"Low Score (<6)",low_score,"#f78166"),
]:
    with col:
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-val" style="color:{color}">{val}</div>
          <div class="stat-label">{label}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Send approved banner ──────────────────────────────────────────────────────
approved_items = [q for q in queue if q["status"] in ("approved","edited")]
if approved_items:
    st.markdown(f"""
    <div class="send-banner">
      <span style="font-size:1.5rem">✅</span>
      <div style="flex:1">
        <div style="font-size:0.7rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.08em">Ready to send</div>
        <div style="font-size:0.95rem;font-weight:700">{len(approved_items)} wish{'es' if len(approved_items)!=1 else ''} approved</div>
      </div>
    </div>
    """, unsafe_allow_html=True)
    bc1,bc2,bc3 = st.columns([1,1,2])
    with bc1:
        mode = "🧪 Send All (Dry)" if st.session_state.dry_run else "📤 Send All Now"
        if st.button(mode, type="primary", use_container_width=True):
            for item in approved_items:
                mark_sent(item["id"])
                st.session_state.sent_log.append(
                    f"[{'DRY RUN' if st.session_state.dry_run else 'LIVE'}] "
                    f"{item['contact_name']} via {item['platform']} — sent at {datetime.now().strftime('%H:%M:%S')}"
                )
            st.success(f"{'Simulated' if st.session_state.dry_run else 'Sent'} {len(approved_items)} wishes! ✅")
            time.sleep(0.4)
            st.rerun()
    with bc2:
        if st.button("📅 Schedule 9 AM", use_container_width=True):
            st.info(f"{len(approved_items)} wishes scheduled for 09:00 AM (contact local time).")

# ── Controls row ──────────────────────────────────────────────────────────────
ctrl1, ctrl2, ctrl3, ctrl4, ctrl5 = st.columns([1.2,1,1,1,1])
with ctrl1:
    dry = st.toggle("🧪 Dry Run", value=st.session_state.dry_run)
    st.session_state.dry_run = dry
with ctrl2:
    filt = st.selectbox("Filter", ["All","Pending","Approved","Rejected","Sent","Low Score"],
                        index=["All","Pending","Approved","Rejected","Sent","Low Score"].index(st.session_state.filter),
                        label_visibility="collapsed")
    st.session_state.filter = filt
with ctrl3:
    if st.button("✅ Approve All Pending", use_container_width=True):
        ids = [q["id"] for q in queue if q["status"] == "pending"]
        bulk_update(ids, "approved")
        st.rerun()
with ctrl4:
    if st.button("✕ Reject Low Score", use_container_width=True):
        ids = [q["id"] for q in queue if (q["score"] or 10) < 6 and q["status"] == "pending"]
        bulk_update(ids, "rejected")
        st.rerun()
with ctrl5:
    if st.button("🔄 Refresh Queue", use_container_width=True):
        st.rerun()

st.markdown("---")

# ── Filter queue ──────────────────────────────────────────────────────────────
def filter_queue(items, f):
    if f == "All":       return items
    if f == "Pending":   return [i for i in items if i["status"] == "pending"]
    if f == "Approved":  return [i for i in items if i["status"] in ("approved","edited")]
    if f == "Rejected":  return [i for i in items if i["status"] == "rejected"]
    if f == "Sent":      return [i for i in items if i["status"] == "sent"]
    if f == "Low Score": return [i for i in items if (i["score"] or 10) < 6]
    return items

visible = filter_queue(queue, st.session_state.filter)

# ─────────────────────────────────────────────────────────────────────────────
# QUEUE LIST
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f'<div class="section-title">Queue — {date.today().strftime("%B %d, %Y")} ({len(visible)} items)</div>',
            unsafe_allow_html=True)

if not visible:
    st.info("No items match this filter.")

for item in visible:
    status    = item["status"]
    card_cls  = f"q-row {status if status != 'edited' else 'edited'}"
    plat_icon = PLAT_ICON.get(item["platform"], "📱")
    display_text = item["edited_text"] if item["edited_text"] else item["wish_text"]
    is_editing   = st.session_state.editing_id == item["id"]
    sc_chip      = score_chip(item["score"])
    style_tag    = f'<span style="font-size:0.65rem;color:#8b949e;background:#21262d;padding:1px 6px;border-radius:4px;margin-left:4px">{item["style"] or "—"}</span>' if item["style"] else ""

    st.markdown(f"""
    <div class="{card_cls}">
      <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:4px">
        <div class="q-contact">{item['contact_name']}</div>
        <div>{STATUS_PILL.get(status,'')} {sc_chip} {style_tag}</div>
      </div>
      <div class="q-meta">{plat_icon} {item['platform']} · Queue: {item['queue_date']}</div>
    </div>
    """, unsafe_allow_html=True)

    # Wish text or edit box
    if is_editing:
        buf_key = f"buf_{item['id']}"
        if buf_key not in st.session_state.edit_buffer:
            st.session_state.edit_buffer[buf_key] = display_text
        edited = st.text_area(
            "Edit wish",
            value=st.session_state.edit_buffer[buf_key],
            height=130,
            key=f"ta_{item['id']}",
            label_visibility="collapsed",
        )
        st.session_state.edit_buffer[buf_key] = edited
        word_count = len(edited.split())
        st.caption(f"📝 {word_count} words · {len(edited)} chars")
    else:
        st.markdown(f'<div class="q-wish">{display_text}</div>', unsafe_allow_html=True)
        if item["edited_text"]:
            st.caption("✏️ Manually edited")

    # Action buttons
    if status == "sent":
        st.caption(f"📤 Sent at {(item['sent_at'] or '')[:16].replace('T',' ')}")
    else:
        if is_editing:
            ea, eb, ec, ed = st.columns([1,1,1,1])
            with ea:
                if st.button("✅ Save & Approve", key=f"save_{item['id']}", type="primary", use_container_width=True):
                    update_status(item["id"], "edited", st.session_state.edit_buffer.get(f"buf_{item['id']}", display_text))
                    st.session_state.editing_id = None
                    st.rerun()
            with eb:
                if st.button("✓ Save only", key=f"saveonly_{item['id']}", use_container_width=True):
                    update_status(item["id"], "edited", st.session_state.edit_buffer.get(f"buf_{item['id']}", display_text))
                    st.session_state.editing_id = None
                    st.rerun()
            with ec:
                if st.button("🔁 Regenerate", key=f"regen_{item['id']}", use_container_width=True):
                    new_text = regenerate_wish(item)
                    st.session_state.edit_buffer[f"buf_{item['id']}"] = new_text
                    st.rerun()
            with ed:
                if st.button("✕ Cancel", key=f"cancel_{item['id']}", use_container_width=True):
                    st.session_state.editing_id = None
                    st.rerun()
        else:
            ba, bb, bc, bd, be = st.columns([1,1,1,1,1])
            with ba:
                ap_label = "✅ Approved" if status in ("approved","edited") else "✅ Approve"
                ap_type  = "primary" if status not in ("approved","edited") else "secondary"
                if st.button(ap_label, key=f"ap_{item['id']}", use_container_width=True, type=ap_type):
                    new_s = "pending" if status in ("approved","edited") else "approved"
                    update_status(item["id"], new_s)
                    st.rerun()
            with bb:
                rj_label = "↩ Undo" if status == "rejected" else "✕ Reject"
                if st.button(rj_label, key=f"rj_{item['id']}", use_container_width=True):
                    new_s = "pending" if status == "rejected" else "rejected"
                    update_status(item["id"], new_s)
                    st.rerun()
            with bc:
                if st.button("✏️ Edit", key=f"ed_{item['id']}", use_container_width=True):
                    st.session_state.editing_id = item["id"]
                    st.rerun()
            with bd:
                if st.button("🔁 Regen", key=f"rg_{item['id']}", use_container_width=True,
                             help="Regenerate AI wish"):
                    new_text = regenerate_wish(item)
                    update_status(item["id"], "pending", new_text)
                    st.rerun()
            with be:
                if st.button("📤 Send Now", key=f"sn_{item['id']}", use_container_width=True,
                             disabled=(status == "rejected")):
                    mark_sent(item["id"])
                    st.session_state.sent_log.append(
                        f"[{'DRY' if st.session_state.dry_run else 'LIVE'}] "
                        f"{item['contact_name']} → {item['platform']} at {datetime.now().strftime('%H:%M:%S')}"
                    )
                    st.rerun()

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SEND LOG
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.sent_log:
    st.markdown('<div class="section-title">Send Log</div>', unsafe_allow_html=True)
    lines = "".join(
        f'<span style="color:#58a6ff">{e}</span><br>'
        for e in reversed(st.session_state.sent_log)
    )
    st.markdown(
        f'<div style="background:#010409;border:1px solid #30363d;border-radius:10px;'
        f'padding:12px 14px;font-family:JetBrains Mono,monospace;font-size:0.72rem;'
        f'max-height:160px;overflow-y:auto">{lines}</div>',
        unsafe_allow_html=True,
    )
    if st.button("🗑 Clear log"):
        st.session_state.sent_log.clear()
        st.rerun()

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"""
<div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
  <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
  <span>Batch Approve Queue · {date.today().strftime("%B %d, %Y")}</span>
  <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
</div>
""", unsafe_allow_html=True)
