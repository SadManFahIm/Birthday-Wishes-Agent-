"""
Conversation Summary Memory -- Birthday Wishes Agent v10.0
Maintains a rolling AI-generated summary for each contact,
updated after every interaction. Summaries are injected into
the LangGraph generate node for hyper-personalized wishes.

How it works:
  1. After each wish/reply/event, append the raw interaction note
  2. When summary is stale (new notes since last summary), re-summarize
  3. AI compresses all notes into a 3-5 sentence rolling summary
  4. Summary is served to langgraph_workflow.py generate node

Summary update modes:
  ai       -- use model_config.generate() to summarize (best quality)
  rule     -- extractive: keep most recent N notes (no API needed)
  hybrid   -- AI when available, rule fallback

Integrates with: vector_memory.py, model_config.py,
                 langgraph_workflow.py (generate node), agent.py
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path("agent_history.db")

SUMMARY_MAX_NOTES  = 20      # max raw notes to keep per contact
SUMMARY_SENTENCES  = 5       # target summary length
STALE_THRESHOLD    = 3       # re-summarize after N new notes

NOTE_TYPES = {
    "wish_sent":     {"icon": "🎂", "color": "#f78166", "label": "Wish Sent"},
    "reply":         {"icon": "💬", "color": "#3fb950", "label": "Reply Received"},
    "no_reply":      {"icon": "😶", "color": "#8b949e", "label": "No Reply"},
    "life_event":    {"icon": "🎉", "color": "#bc8cff", "label": "Life Event"},
    "deal":          {"icon": "💰", "color": "#3fb950", "label": "Revenue Deal"},
    "vip_flagged":   {"icon": "💎", "color": "#d29922", "label": "VIP Flagged"},
    "gift_sent":     {"icon": "🎁", "color": "#f78166", "label": "Gift Sent"},
    "checkin":       {"icon": "👋", "color": "#58a6ff", "label": "Check-in"},
    "manual":        {"icon": "📝", "color": "#8b949e", "label": "Manual Note"},
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_summary_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_notes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            note_type       TEXT NOT NULL DEFAULT 'manual',
            content         TEXT NOT NULL,
            platform        TEXT,
            metadata_json   TEXT,
            created_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_summaries (
            contact_id      TEXT PRIMARY KEY,
            contact_name    TEXT NOT NULL,
            summary         TEXT NOT NULL,
            notes_count     INTEGER NOT NULL DEFAULT 0,
            summarized_up_to INTEGER NOT NULL DEFAULT 0,
            model_used      TEXT,
            updated_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cn_contact
        ON conversation_notes(contact_id)
    """)
    conn.commit()
    conn.close()


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Add notes ─────────────────────────────────────────────────────────────────

def add_note(
    contact_id:   str,
    contact_name: str,
    content:      str,
    note_type:    str = "manual",
    platform:     str = "",
    metadata:     Optional[dict] = None,
    auto_resummarize: bool = True,
) -> int:
    """
    Append an interaction note to a contact's conversation history.

    Args:
        contact_id:   Unique contact identifier.
        contact_name: Full name.
        content:      Free-text note describing the interaction.
        note_type:    wish_sent / reply / no_reply / life_event / deal /
                      vip_flagged / gift_sent / checkin / manual.
        platform:     Platform where interaction happened.
        metadata:     Optional structured data dict.
        auto_resummarize: If True, check staleness and re-summarize.

    Returns:
        Note row ID.
    """
    init_summary_tables()
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute("""
        INSERT INTO conversation_notes
            (contact_id, contact_name, note_type, content,
             platform, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, note_type, content,
          platform, json.dumps(metadata or {}),
          datetime.now().isoformat()))
    note_id = cur.lastrowid
    conn.commit()
    conn.close()

    if auto_resummarize:
        _check_and_resummarize(contact_id, contact_name)

    return note_id


def add_wish_note(
    contact_id:   str,
    contact_name: str,
    wish_text:    str,
    platform:     str,
    replied:      bool = False,
    sentiment:    Optional[float] = None,
) -> int:
    """Convenience: log a wish send + reply outcome as a note."""
    reply_part = ""
    if replied:
        s = f" (sentiment {sentiment}/5)" if sentiment else ""
        reply_part = f" They replied positively{s}."
    else:
        reply_part = " No reply received."

    content = (f"Sent birthday wish via {platform}: "
               f"\"{wish_text[:80]}...\"{reply_part}")
    ntype   = "reply" if replied else "wish_sent"
    return add_note(contact_id, contact_name, content, ntype, platform,
                    {"wish_text": wish_text[:200], "replied": replied,
                     "sentiment": sentiment})


def add_life_event_note(
    contact_id:   str,
    contact_name: str,
    event_type:   str,
    description:  str,
) -> int:
    """Log a detected life event (promotion, wedding, etc.)."""
    content = f"Life event detected: {event_type}. {description}"
    return add_note(contact_id, contact_name, content, "life_event",
                    metadata={"event_type": event_type})


def add_deal_note(
    contact_id:   str,
    contact_name: str,
    deal_name:    str,
    deal_value:   float,
    currency:     str = "BDT",
) -> int:
    """Log a revenue deal attributed to this contact."""
    content = f"Revenue deal: {deal_name} — {deal_value:,.0f} {currency}."
    return add_note(contact_id, contact_name, content, "deal",
                    metadata={"deal_name": deal_name,
                              "deal_value": deal_value,
                              "currency": currency})


# ── Summarization ─────────────────────────────────────────────────────────────

def _check_and_resummarize(contact_id: str, contact_name: str):
    """Re-summarize if enough new notes have accumulated."""
    conn  = _db()
    total = conn.execute("""
        SELECT COUNT(*) FROM conversation_notes WHERE contact_id=?
    """, (contact_id,)).fetchone()[0]

    existing = conn.execute("""
        SELECT summarized_up_to FROM conversation_summaries WHERE contact_id=?
    """, (contact_id,)).fetchone()
    conn.close()

    last_summarized = existing["summarized_up_to"] if existing else 0
    new_notes       = total - last_summarized

    if new_notes >= STALE_THRESHOLD:
        summarize_contact(contact_id, contact_name)


def summarize_contact(
    contact_id:   str,
    contact_name: str,
    mode:         str = "hybrid",
) -> str:
    """
    Generate or update the rolling summary for a contact.

    Args:
        mode: ai / rule / hybrid

    Returns:
        The summary text.
    """
    init_summary_tables()
    conn  = _db()
    conn2 = sqlite3.connect(DB_PATH)
    conn2.row_factory = sqlite3.Row
    notes = conn2.execute("""
        SELECT note_type, content, platform, created_at, metadata_json
        FROM conversation_notes WHERE contact_id=?
        ORDER BY created_at ASC
    """, (contact_id,)).fetchall()
    conn2.close()

    if not notes:
        return "(No interaction history yet.)"

    notes_text = "\n".join(
        f"[{n['created_at'][:10]}] ({n['note_type']}) {n['content']}"
        for n in notes[-SUMMARY_MAX_NOTES:]
    )

    summary    = ""
    model_used = "rule"

    if mode in ("ai", "hybrid"):
        summary, model_used = _ai_summarize(contact_name, notes_text)

    if not summary:
        summary    = _rule_summarize(contact_name, notes)
        model_used = "rule"

    # Persist
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO conversation_summaries
            (contact_id, contact_name, summary, notes_count,
             summarized_up_to, model_used, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id) DO UPDATE SET
            contact_name     = excluded.contact_name,
            summary          = excluded.summary,
            notes_count      = excluded.notes_count,
            summarized_up_to = excluded.summarized_up_to,
            model_used       = excluded.model_used,
            updated_at       = excluded.updated_at
    """, (contact_id, contact_name, summary, len(notes),
          len(notes), model_used, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    return summary


def _ai_summarize(contact_name: str, notes_text: str) -> tuple:
    """Use model_config.generate() to produce a rolling summary."""
    try:
        from model_config import generate as model_generate
    except ImportError:
        return ("", "")

    prompt = (
        f"You are summarizing the interaction history between me and "
        f"{contact_name}. Below are chronological notes:\n\n"
        f"{notes_text}\n\n"
        f"Write a {SUMMARY_SENTENCES}-sentence rolling summary that captures:\n"
        f"1. How we know each other and the relationship quality\n"
        f"2. Their communication preferences (platform, tone, style)\n"
        f"3. Key events (deals, life events, memorable interactions)\n"
        f"4. What has worked well in past wishes\n"
        f"5. Any important things to remember for the next interaction\n\n"
        f"Be concise. Use third person ('{contact_name}...')."
    )

    try:
        result = model_generate(
            prompt, task="summarization", mode="fast", max_tokens=250,
            system="You are a CRM assistant that writes concise contact summaries.")
        text = result.get("text", "")
        if text and not text.startswith("[Error"):
            return (text.strip(), result.get("model_id", "ai"))
    except Exception:
        pass

    return ("", "")


def _rule_summarize(contact_name: str, notes: list) -> str:
    """Extractive rule-based summary (no AI needed)."""
    recent      = notes[-SUMMARY_MAX_NOTES:]
    wish_count  = sum(1 for n in recent if n["note_type"] in ("wish_sent", "reply"))
    reply_count = sum(1 for n in recent if n["note_type"] == "reply")
    events      = [n for n in recent if n["note_type"] == "life_event"]
    deals       = [n for n in recent if n["note_type"] == "deal"]
    platforms   = list({n["platform"] for n in recent if n["platform"]})

    parts = []
    parts.append(f"{contact_name}: {len(recent)} interactions recorded.")

    if wish_count:
        rate = reply_count / wish_count if wish_count else 0
        parts.append(f"{wish_count} wishes sent, {rate:.0%} reply rate.")

    if platforms:
        parts.append(f"Active on: {', '.join(platforms[:3])}.")

    if events:
        latest_event = events[-1]["content"][:60]
        parts.append(f"Recent event: {latest_event}.")

    if deals:
        total = sum(
            json.loads(d["metadata_json"] or "{}").get("deal_value", 0)
            for d in deals)
        parts.append(f"{len(deals)} deals totaling {total:,.0f}.")

    if recent:
        last = recent[-1]
        parts.append(f"Last interaction: {last['created_at'][:10]} "
                     f"({last['note_type']}).")

    return " ".join(parts[:SUMMARY_SENTENCES])


# ── Retrieval ─────────────────────────────────────────────────────────────────

def get_summary(contact_id: str) -> Optional[str]:
    """Get the current rolling summary for a contact."""
    init_summary_tables()
    conn = _db()
    row  = conn.execute("""
        SELECT summary FROM conversation_summaries WHERE contact_id=?
    """, (contact_id,)).fetchone()
    conn.close()
    return row["summary"] if row else None


def get_summary_with_meta(contact_id: str) -> Optional[dict]:
    """Get summary plus metadata (notes count, model used, freshness)."""
    init_summary_tables()
    conn = _db()
    row  = conn.execute("""
        SELECT * FROM conversation_summaries WHERE contact_id=?
    """, (contact_id,)).fetchone()
    if not row:
        conn.close()
        return None
    total_notes = conn.execute("""
        SELECT COUNT(*) FROM conversation_notes WHERE contact_id=?
    """, (contact_id,)).fetchone()[0]
    conn.close()
    stale_count = total_notes - row["summarized_up_to"]
    return {
        "contact_id":   row["contact_id"],
        "contact_name": row["contact_name"],
        "summary":      row["summary"],
        "notes_count":  row["notes_count"],
        "total_notes":  total_notes,
        "stale_notes":  stale_count,
        "is_stale":     stale_count >= STALE_THRESHOLD,
        "model_used":   row["model_used"],
        "updated_at":   row["updated_at"],
    }


def get_contact_notes(contact_id: str, limit: int = 20) -> list[dict]:
    """Get raw notes for a contact."""
    init_summary_tables()
    conn = _db()
    rows = conn.execute("""
        SELECT note_type, content, platform, created_at
        FROM conversation_notes WHERE contact_id=?
        ORDER BY created_at DESC LIMIT ?
    """, (contact_id, limit)).fetchall()
    conn.close()
    return [{
        "note_type":  r["note_type"],
        "content":    r["content"],
        "platform":   r["platform"] or "",
        "created_at": r["created_at"],
        "icon":       NOTE_TYPES.get(r["note_type"],{}).get("icon","📝"),
        "color":      NOTE_TYPES.get(r["note_type"],{}).get("color","#8b949e"),
    } for r in rows]


def get_all_summaries() -> list[dict]:
    """Get summaries for all contacts."""
    init_summary_tables()
    conn = _db()
    rows = conn.execute("""
        SELECT contact_id, contact_name, summary, notes_count,
               summarized_up_to, model_used, updated_at
        FROM conversation_summaries
        ORDER BY updated_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Context builder (for LangGraph) ──────────────────────────────────────────

def get_wish_context(contact_id: str, contact_name: str = "") -> str:
    """
    Build a prompt-ready context string from the contact's summary.
    Used by langgraph_workflow.py generate node.

    Returns:
        Multi-line string ready for prompt injection.
    """
    summary = get_summary(contact_id)
    if summary:
        return f"Relationship context for {contact_name or contact_id}:\n{summary}"

    # No summary yet — try to build one from notes
    notes = get_contact_notes(contact_id, limit=5)
    if notes:
        lines = [f"Recent interactions with {contact_name or contact_id}:"]
        for n in notes[:3]:
            lines.append(f"- [{n['note_type']}] {n['content'][:80]}")
        return "\n".join(lines)

    return f"(No prior interaction history with {contact_name or contact_id}.)"


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_summary_tables()
    conn  = _db()
    count = conn.execute(
        "SELECT COUNT(*) FROM conversation_notes").fetchone()[0]
    conn.close()
    if count > 0:
        return

    demo = [
        ("urn_rakib_001", "Rakib Hossain", [
            ("wish_sent", "Sent birthday wish via LinkedIn: professional tone, mentioned his Pathao work.", "LinkedIn"),
            ("reply", "Rakib replied within 2 hours: 'Thanks man! Really appreciated the thoughtful message.' Sentiment 4.5/5.", "LinkedIn"),
            ("deal", "Revenue deal: Backend Dev Contract — 480,000 BDT. Attributed to birthday wish.", "LinkedIn"),
            ("manual", "Rakib prefers concise messages. Responds well to career milestone references.", ""),
            ("wish_sent", "Sent follow-up birthday wish year 2: referenced his promotion to Senior Engineer.", "LinkedIn"),
            ("reply", "Replied same day with a heart react and forwarded to his team.", "LinkedIn"),
        ]),
        ("urn_nadia_002", "Nadia Islam", [
            ("wish_sent", "Sent birthday wish via WhatsApp with emoji-rich warm style.", "WhatsApp"),
            ("reply", "Nadia replied with voice note thanking warmly. Sentiment 5/5.", "WhatsApp"),
            ("life_event", "Life event detected: promotion. Nadia joined bKash as Senior Product Designer.", "WhatsApp"),
            ("manual", "Nadia loves creative, visual messages. Prefers WhatsApp over email.", ""),
        ]),
        ("urn_mim_004", "Mim Chowdhury", [
            ("wish_sent", "Sent birthday wish mentioning her ML research at Brain Station 23.", "WhatsApp"),
            ("no_reply", "No reply after 5 days. May need to try different approach next year.", "WhatsApp"),
            ("manual", "Mim values deeply personal messages. Mention IUT days or ML research for engagement.", ""),
        ]),
    ]

    for cid, cname, notes in demo:
        for ntype, content, platform in notes:
            add_note(cid, cname, content, ntype, platform,
                     auto_resummarize=False)
        summarize_contact(cid, cname, mode="rule")


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Conversation Summary", page_icon="📋",
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
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);
                font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:var(--muted);margin:22px 0 10px;
                   display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .s-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .note-row{background:#0d1117;border:1px solid #21262d;border-radius:6px;
              padding:8px 12px;margin-bottom:4px;font-size:0.76rem;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.3rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);
        border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_summary_tables()
    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📋</span>
      <h1>Conversation Summary Memory</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    summaries = get_all_summaries()
    conn = _db()
    total_notes = conn.execute(
        "SELECT COUNT(*) FROM conversation_notes").fetchone()[0]
    conn.close()

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Contacts",    len(summaries),  "#58a6ff"),
        (m2, "Total Notes", total_notes,     "#f78166"),
        (m3, "Summaries",   len(summaries),  "#3fb950"),
        (m4, "Stale Threshold", f"{STALE_THRESHOLD} notes", "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" '
                        f'style="color:{color};font-size:0.95rem">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.5], gap="large")

    with left:
        st.markdown('<div class="section-title">Contact Summaries</div>',
                    unsafe_allow_html=True)
        for s in summaries:
            meta = get_summary_with_meta(s["contact_id"])
            stale_badge = ""
            if meta and meta["is_stale"]:
                stale_badge = ('<span style="font-size:0.6rem;color:#d29922;'
                               'margin-left:6px">⚠ stale</span>')
            st.markdown(f"""
            <div class="s-card">
              <div style="display:flex;justify-content:space-between;
                          margin-bottom:6px">
                <span style="font-weight:700">{s['contact_name']}{stale_badge}</span>
                <span style="font-size:0.65rem;color:#8b949e">
                  {s['notes_count']} notes · {s['model_used']}
                </span>
              </div>
              <div style="font-size:0.78rem;color:#c9d1d9;line-height:1.5">
                {s['summary'][:200]}{'...' if len(s['summary'])>200 else ''}
              </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"View notes", key=f"vn_{s['contact_id']}",
                         use_container_width=True):
                st.session_state["sel_cid"]  = s["contact_id"]
                st.session_state["sel_name"] = s["contact_name"]
                st.rerun()

        # Add note form
        st.markdown('<div class="section-title">Add Note</div>',
                    unsafe_allow_html=True)
        n_cid  = st.text_input("Contact ID", placeholder="urn_rakib_001",
                               label_visibility="collapsed", key="ncid")
        n_name = st.text_input("Name", placeholder="Rakib Hossain",
                               label_visibility="collapsed", key="nname")
        n_text = st.text_area("Note", height=60,
                              label_visibility="collapsed", key="ntext",
                              placeholder="Sent birthday wish via LinkedIn...")
        n_type = st.selectbox("Type", list(NOTE_TYPES.keys()),
                              label_visibility="collapsed", key="ntype")
        if st.button("💾 Add Note", type="primary", use_container_width=True):
            if n_cid and n_text:
                add_note(n_cid, n_name or n_cid, n_text, n_type)
                st.success("Note added")
                st.rerun()

    with right:
        sel_cid  = st.session_state.get("sel_cid")
        sel_name = st.session_state.get("sel_name", "")
        if sel_cid:
            st.markdown(f'<div class="section-title">'
                        f'{sel_name} — Notes</div>', unsafe_allow_html=True)

            # Summary
            meta = get_summary_with_meta(sel_cid)
            if meta:
                st.markdown(f"""
                <div style="background:#0a1a2a;border:1px solid #1f3a5a;
                            border-left:3px solid #58a6ff;border-radius:8px;
                            padding:12px 14px;margin-bottom:12px;
                            font-size:0.80rem;color:#c9d1d9;line-height:1.6;">
                  <div style="font-size:0.65rem;color:#58a6ff;font-weight:700;
                               margin-bottom:4px">ROLLING SUMMARY
                    <span style="color:#8b949e;font-weight:400;margin-left:8px">
                      via {meta['model_used']}
                    </span>
                  </div>
                  {meta['summary']}
                </div>
                """, unsafe_allow_html=True)

            # Notes
            notes = get_contact_notes(sel_cid, limit=15)
            for n in notes:
                st.markdown(f"""
                <div class="note-row" style="border-left:2px solid {n['color']}">
                  <div style="display:flex;justify-content:space-between">
                    <span>{n['icon']} {NOTE_TYPES.get(n['note_type'],{}).get('label',n['note_type'])}</span>
                    <span style="color:#8b949e;font-size:0.65rem">
                      {n['created_at'][:16].replace('T',' ')}
                    </span>
                  </div>
                  <div style="color:#c9d1d9;margin-top:3px">
                    {n['content'][:120]}{'...' if len(n['content'])>120 else ''}
                  </div>
                </div>
                """, unsafe_allow_html=True)

            # Re-summarize button
            if st.button("🔄 Re-summarize", use_container_width=True):
                with st.spinner("Summarizing..."):
                    summarize_contact(sel_cid, sel_name, mode="hybrid")
                st.success("Summary updated")
                st.rerun()
        else:
            st.info("Click a contact on the left to view their notes and summary.")

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Conversation Summary Memory</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_summary_tables()
    _seed_demo()
    print("=== Conversation Summary Memory -- self test ===\n")

    summaries = get_all_summaries()
    print(f"Contacts with summaries: {len(summaries)}\n")

    for s in summaries:
        meta = get_summary_with_meta(s["contact_id"])
        stale = "⚠ STALE" if meta and meta["is_stale"] else "✅ fresh"
        print(f"  {s['contact_name']:<22} [{stale}] "
              f"({s['notes_count']} notes, via {s['model_used']})")
        print(f"    {s['summary'][:80]}...")
        print()

    # Test wish context builder
    print("Wish context for Rakib:")
    ctx = get_wish_context("urn_rakib_001", "Rakib Hossain")
    for line in ctx.split("\n"):
        print(f"  {line}")

    # Test adding a new note triggers re-summarize
    print("\nAdding new note to Rakib...")
    add_note("urn_rakib_001", "Rakib Hossain",
             "Rakib mentioned he is moving to a new startup as CTO.",
             "life_event", "LinkedIn")
    updated = get_summary_with_meta("urn_rakib_001")
    print(f"  Notes: {updated['total_notes']}, "
          f"Stale: {updated['stale_notes']}, "
          f"Is stale: {updated['is_stale']}")
else:
    render_dashboard()
