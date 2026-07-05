"""
Mutual Connection Insights — Birthday Wishes Agent v8.0
Detects common connections, shared interests, and mutual context between
you and a contact, then suggests a natural way to weave one into the
birthday wish — making it feel written by someone who actually knows them.

Sources of mutual context:
  • Shared LinkedIn connections (mutual 2nd-degree)
  • Common interests / skills from profiles
  • Shared groups, events, companies, universities
  • Past conversation topics (from memory.py)

Integrates with: ai/context_aware_opener.py, ai/memory.py, agent.py
"""

import sqlite3
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path("agent_history.db")

# ── Insight categories ────────────────────────────────────────────────────────

INSIGHT_TYPES = {
    "mutual_connection": {"label": "Mutual Connection", "icon": "🤝", "weight": 3},
    "shared_interest":   {"label": "Shared Interest",   "icon": "💡", "weight": 2},
    "shared_group":      {"label": "Shared Group",      "icon": "👥", "weight": 2},
    "shared_company":    {"label": "Past Colleague",    "icon": "🏢", "weight": 3},
    "shared_university": {"label": "Alumni",            "icon": "🎓", "weight": 3},
    "shared_skill":      {"label": "Shared Skill",      "icon": "⚙️", "weight": 1},
    "shared_event":      {"label": "Shared Event",      "icon": "📅", "weight": 2},
    "conversation_topic":{"label": "Past Topic",        "icon": "💬", "weight": 2},
}

# Wish mention templates per insight type
MENTION_TEMPLATES = {
    "mutual_connection": [
        "I was actually chatting with {value} the other day — small world!",
        "Funny, {value} mentioned you recently — happy birthday!",
        "Between knowing {value} and following your work, I always feel like we're connected.",
    ],
    "shared_interest": [
        "Fellow {value} enthusiast here — hope your birthday is as great as the craft!",
        "Your passion for {value} always stands out. Hope you get to indulge in some today!",
        "One {value} fan to another — happy birthday!",
    ],
    "shared_group": [
        "Our paths crossing in {value} made this feel overdue — happy birthday!",
        "Glad {value} brought us into the same orbit. Hope it's a great one!",
    ],
    "shared_company": [
        "The time at {value} was short but memorable — hope your birthday is just as good.",
        "Our {value} days feel like yesterday. Happy birthday!",
    ],
    "shared_university": [
        "Fellow {value} alumnus here — hope the birthday is properly celebrated!",
        "From {value} to where you are now — what a run. Happy birthday!",
    ],
    "shared_skill": [
        "One {value} practitioner to another — happy birthday!",
        "Your take on {value} always makes me think. Hope today's a good one!",
    ],
    "shared_event": [
        "Still think about what you said at {value}. Happy birthday!",
        "Ever since {value}, I've followed your work closely. Hope it's a great day!",
    ],
    "conversation_topic": [
        "We talked about {value} and I never forgot your perspective. Happy birthday!",
        "Your take on {value} stuck with me. Hope today's a great one!",
    ],
}

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_mutual_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mutual_insights (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            insight_type    TEXT NOT NULL,
            insight_value   TEXT NOT NULL,
            confidence      REAL NOT NULL DEFAULT 1.0,
            source          TEXT,
            used_in_wish    INTEGER NOT NULL DEFAULT 0,
            fetched_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wish_mention_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            insight_type    TEXT NOT NULL,
            insight_value   TEXT NOT NULL,
            mention_text    TEXT NOT NULL,
            wish_date       TEXT NOT NULL,
            logged_at       TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Store insights ────────────────────────────────────────────────────────────

def save_insight(
    contact_id:    str,
    contact_name:  str,
    insight_type:  str,
    insight_value: str,
    confidence:    float = 1.0,
    source:        str   = "linkedin_scrape",
):
    """
    Persist one mutual insight for a contact.
    Call after scraping LinkedIn or from memory module.

    Args:
        insight_type:  Key from INSIGHT_TYPES.
        insight_value: Human-readable value (e.g. "Python", "Ahmed Karim", "IUT").
        confidence:    0.0–1.0 confidence from scraper.
        source:        Where this came from (linkedin_scrape / memory / manual).
    """
    init_mutual_tables()
    conn = sqlite3.connect(DB_PATH)
    # Avoid duplicates
    exists = conn.execute("""
        SELECT id FROM mutual_insights
        WHERE contact_id=? AND insight_type=? AND insight_value=?
    """, (contact_id, insight_type, insight_value)).fetchone()
    if not exists:
        conn.execute("""
            INSERT INTO mutual_insights
                (contact_id, contact_name, insight_type, insight_value,
                 confidence, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (contact_id, contact_name, insight_type, insight_value,
              confidence, source, datetime.now().isoformat()))
        conn.commit()
    conn.close()


def save_insights_batch(contact_id: str, contact_name: str, insights: list[dict]):
    """
    Save multiple insights at once.
    Each dict: { type, value, confidence?, source? }
    """
    for ins in insights:
        save_insight(
            contact_id, contact_name,
            ins["type"], ins["value"],
            ins.get("confidence", 1.0),
            ins.get("source", "linkedin_scrape"),
        )


# ── Retrieve & rank ───────────────────────────────────────────────────────────

def get_insights(contact_id: str, limit: int = 10) -> list[dict]:
    """Return all stored insights for a contact, ranked by weight × confidence."""
    init_mutual_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT insight_type, insight_value, confidence, source, used_in_wish, fetched_at
        FROM mutual_insights WHERE contact_id=?
        ORDER BY confidence DESC
    """, (contact_id,)).fetchall()
    conn.close()

    result = []
    for r in rows:
        itype = r[0]
        weight = INSIGHT_TYPES.get(itype, {}).get("weight", 1)
        result.append({
            "type":        itype,
            "value":       r[1],
            "confidence":  r[2],
            "source":      r[3],
            "used":        bool(r[4]),
            "fetched_at":  r[5],
            "rank_score":  round(weight * r[2], 2),
            "icon":        INSIGHT_TYPES.get(itype, {}).get("icon", "•"),
            "label":       INSIGHT_TYPES.get(itype, {}).get("label", itype),
        })
    result.sort(key=lambda x: x["rank_score"], reverse=True)
    return result[:limit]


def get_best_insight(contact_id: str, exclude_used: bool = True) -> Optional[dict]:
    """Return the single highest-ranked insight — the one to use in the wish."""
    insights = get_insights(contact_id)
    if exclude_used:
        insights = [i for i in insights if not i["used"]]
    return insights[0] if insights else None


# ── Mention generation ────────────────────────────────────────────────────────

def generate_mention(insight: dict) -> str:
    """
    Generate a natural sentence that weaves the insight into a wish.
    Returns a ready-to-use sentence (inject before/after the main wish body).
    """
    templates = MENTION_TEMPLATES.get(insight["type"], [
        f"Always good to cross paths — happy birthday!"
    ])
    template = random.choice(templates)
    return template.format(value=insight["value"])


def get_wish_mention(
    contact_id:   str,
    contact_name: str,
    verbose:      bool = True,
) -> dict:
    """
    Main entry point. Returns the best insight + a ready mention sentence.

    Returns:
        {
          found:        bool,
          insight:      dict | None,
          mention_text: str,
          prompt_snippet: str,   ← inject into AI wish prompt
        }
    """
    init_mutual_tables()
    insight = get_best_insight(contact_id)

    if not insight:
        return {
            "found":          False,
            "insight":        None,
            "mention_text":   "",
            "prompt_snippet": "",
        }

    mention = generate_mention(insight)

    prompt_snippet = (
        f"Subtly reference this mutual connection/shared context in the wish: "
        f"{insight['label']} — {insight['value']}. "
        f"For example, you could open with or weave in: \"{mention}\" "
        f"Keep it natural, not forced."
    )

    if verbose:
        print(f"[MutualInsight] {contact_name}: "
              f"{insight['icon']} {insight['label']} — {insight['value']} "
              f"(score={insight['rank_score']})")
        print(f"  Mention: {mention}")

    # Mark as used
    _mark_used(contact_id, insight["type"], insight["value"])
    _log_mention(contact_id, insight["type"], insight["value"], mention)

    return {
        "found":          True,
        "insight":        insight,
        "mention_text":   mention,
        "prompt_snippet": prompt_snippet,
    }


def _mark_used(contact_id: str, itype: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE mutual_insights SET used_in_wish=1
        WHERE contact_id=? AND insight_type=? AND insight_value=?
    """, (contact_id, itype, value))
    conn.commit()
    conn.close()


def _log_mention(contact_id: str, itype: str, value: str, mention: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO wish_mention_log
            (contact_id, insight_type, insight_value, mention_text, wish_date, logged_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (contact_id, itype, value, mention,
          datetime.now().date().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Profile builder (from LinkedIn scrape result) ─────────────────────────────

def extract_insights_from_profile(
    contact_id:   str,
    contact_name: str,
    profile:      dict,
    my_profile:   dict,
) -> list[dict]:
    """
    Compare two LinkedIn profile dicts and extract mutual insights.

    profile / my_profile keys (all optional):
        connections: list[str]  — names of connections
        interests:   list[str]
        skills:      list[str]
        groups:      list[str]
        companies:   list[str]  — past + current employers
        universities:list[str]
        events:      list[str]

    Returns list of insight dicts ready for save_insights_batch().
    """
    found = []

    def overlap(key, itype):
        theirs = set(s.lower() for s in profile.get(key, []))
        mine   = set(s.lower() for s in my_profile.get(key, []))
        common = theirs & mine
        for val in common:
            # Find original casing from their profile
            orig = next((v for v in profile.get(key, []) if v.lower() == val), val.title())
            found.append({"type": itype, "value": orig, "confidence": 0.9})

    overlap("connections",  "mutual_connection")
    overlap("interests",    "shared_interest")
    overlap("skills",       "shared_skill")
    overlap("groups",       "shared_group")
    overlap("companies",    "shared_company")
    overlap("universities", "shared_university")
    overlap("events",       "shared_event")

    if found:
        save_insights_batch(contact_id, contact_name, found)

    return found


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_mutual_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM mutual_insights").fetchone()[0]
    conn.close()
    if count > 0:
        return

    demo = [
        ("urn_rakib_001", "Rakib Hossain", [
            {"type": "mutual_connection", "value": "Tanvir Ahmed",   "confidence": 1.0},
            {"type": "shared_interest",   "value": "Distributed Systems", "confidence": 0.9},
            {"type": "shared_group",      "value": "PyCon BD",       "confidence": 0.85},
        ]),
        ("urn_nadia_002", "Nadia Islam", [
            {"type": "shared_university", "value": "BUET",           "confidence": 1.0},
            {"type": "shared_interest",   "value": "Design Thinking","confidence": 0.8},
        ]),
        ("urn_tanvir_003", "Tanvir Ahmed", [
            {"type": "mutual_connection", "value": "Rakib Hossain",  "confidence": 1.0},
            {"type": "shared_company",    "value": "Grameenphone",   "confidence": 0.7},
        ]),
        ("urn_mim_004", "Mim Chowdhury", [
            {"type": "shared_university", "value": "IUT",            "confidence": 1.0},
            {"type": "conversation_topic","value": "machine learning","confidence": 0.85},
            {"type": "shared_skill",      "value": "Python",         "confidence": 0.9},
        ]),
    ]
    for cid, cname, insights in demo:
        save_insights_batch(cid, cname, insights)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Mutual Insights", page_icon="🤝",
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
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;
                   color:var(--muted);margin:22px 0 10px;display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .insight-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
                  padding:14px 16px;margin-bottom:8px;}
    .insight-pill{display:inline-flex;align-items:center;gap:4px;font-size:0.65rem;font-weight:700;
                  padding:2px 8px;border-radius:20px;background:#21262d;color:var(--muted);
                  border:1px solid var(--border);margin-right:4px;}
    .mention-box{background:#010409;border:1px solid var(--border);border-radius:8px;
                 padding:12px 14px;font-size:0.82rem;color:#7ee787;font-style:italic;margin-top:8px;}
    .prompt-box{background:#0a1a2a;border:1px solid #1f3a5a;border-left:3px solid var(--blue);
                border-radius:7px;padding:10px 14px;font-size:0.76rem;color:#c9d1d9;margin-top:6px;}
    div[data-testid="stButton"]>button{background:var(--surface);border:1px solid var(--border);
        color:var(--text);border-radius:8px;font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:var(--blue);background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🤝</span>
      <h1>Mutual Connection Insights</h1>
      <span class="cc-badge">v8.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    DEMO_CONTACTS = [
        ("urn_rakib_001","Rakib Hossain"),
        ("urn_nadia_002","Nadia Islam"),
        ("urn_tanvir_003","Tanvir Ahmed"),
        ("urn_mim_004","Mim Chowdhury"),
    ]

    left, right = st.columns([1, 1.5], gap="large")

    with left:
        st.markdown('<div class="section-title">Select Contact</div>', unsafe_allow_html=True)
        if "sel_cid" not in st.session_state:
            st.session_state.sel_cid  = DEMO_CONTACTS[0][0]
            st.session_state.sel_name = DEMO_CONTACTS[0][1]

        for cid, cname in DEMO_CONTACTS:
            insights = get_insights(cid)
            count    = len(insights)
            best     = insights[0] if insights else None
            selected = cid == st.session_state.sel_cid

            st.markdown(f"""
            <div class="insight-card" style="{'border-color:var(--accent);background:#1c1410' if selected else ''}">
              <div style="font-weight:700;font-size:0.86rem">{cname}</div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:3px">
                {count} insight{'s' if count!=1 else ''} found
                {f'· Best: {best["icon"]} {best["label"]}' if best else ''}
              </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Select", key=f"sel_{cid}", use_container_width=True):
                st.session_state.sel_cid  = cid
                st.session_state.sel_name = cname
                st.rerun()

        st.markdown('<div class="section-title" style="margin-top:20px">Add Insight</div>',
                    unsafe_allow_html=True)
        add_type  = st.selectbox("Type", list(INSIGHT_TYPES.keys()),
                                 label_visibility="collapsed", key="add_type")
        add_value = st.text_input("Value", placeholder="e.g. Ahmed Karim / Python / BUET",
                                  label_visibility="collapsed", key="add_value")
        add_conf  = st.slider("Confidence", 0.1, 1.0, 0.9, 0.1, key="add_conf")
        if st.button("➕ Add Insight", type="primary", use_container_width=True):
            if add_value.strip():
                save_insight(st.session_state.sel_cid, st.session_state.sel_name,
                             add_type, add_value.strip(), add_conf, "manual")
                st.success("Insight saved ✅")
                st.rerun()

    with right:
        cid   = st.session_state.sel_cid
        cname = st.session_state.sel_name
        st.markdown(f'<div class="section-title">{cname} — Insights</div>',
                    unsafe_allow_html=True)

        insights = get_insights(cid)
        if not insights:
            st.info("No insights yet. Add some on the left or run the LinkedIn scraper.")
        else:
            for ins in insights:
                used_tag = ' <span style="font-size:0.6rem;color:#8b949e">(used)</span>' if ins["used"] else ""
                st.markdown(f"""
                <div class="insight-card">
                  <div style="display:flex;align-items:center;justify-content:space-between">
                    <div style="font-weight:700;font-size:0.85rem">
                      {ins['icon']} {ins['value']}{used_tag}
                    </div>
                    <span class="insight-pill">{ins['label']} · {ins['rank_score']}</span>
                  </div>
                  <div style="font-size:0.68rem;color:#8b949e;margin-top:3px">
                    Confidence: {ins['confidence']} · Source: {ins['source']}
                  </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Generated Mention</div>',
                    unsafe_allow_html=True)
        if st.button("✨ Generate Wish Mention", type="primary", use_container_width=True):
            result = get_wish_mention(cid, cname, verbose=False)
            if result["found"]:
                st.session_state[f"mention_{cid}"] = result
                st.rerun()
            else:
                st.warning("No unused insights available. Add more above.")

        cached = st.session_state.get(f"mention_{cid}")
        if cached and cached["found"]:
            ins = cached["insight"]
            st.markdown(f"""
            <div class="insight-card">
              <div style="font-size:0.7rem;color:#8b949e;margin-bottom:4px">
                Using: {ins['icon']} {ins['label']} — <strong style="color:#e6edf3">{ins['value']}</strong>
              </div>
              <div class="mention-box">"{cached['mention_text']}"</div>
              <div class="prompt-box" style="margin-top:8px">
                <strong>Prompt snippet:</strong><br>{cached['prompt_snippet']}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
      <span>Mutual Connection Insights</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_mutual_tables()
    _seed_demo()
    print("=== Mutual Connection Insights — self test ===\n")
    contacts = [
        ("urn_rakib_001","Rakib Hossain"),
        ("urn_nadia_002","Nadia Islam"),
        ("urn_tanvir_003","Tanvir Ahmed"),
        ("urn_mim_004","Mim Chowdhury"),
    ]
    for cid, cname in contacts:
        result = get_wish_mention(cid, cname, verbose=False)
        if result["found"]:
            ins = result["insight"]
            print(f"  {ins['icon']} {cname:<20} [{ins['label']}] {ins['value']}")
            print(f"     → \"{result['mention_text']}\"")
        else:
            print(f"  — {cname}: no insights")

if __name__ != "__main__":
    render_dashboard()
