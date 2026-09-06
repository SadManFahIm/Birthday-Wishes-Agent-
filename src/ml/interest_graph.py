"""
Interest Graph -- Birthday Wishes Agent v10.0
Tracks how each contact's interests evolve over time by extracting
signals from status updates, replies, life events, and manual tags.

How it works:
  1. Extract interests from text (regex keywords + optional AI)
  2. Store each interest with a timestamp and source
  3. Time-weighted scoring: recent signals decay slower
  4. Serve ranked interests to gift_suggestion.py and generate node

Interest categories:
  tech, design, books, food, fitness, travel, gaming, music,
  finance, education, career, family, spirituality, sports

Integrates with: ai/gift_suggestion.py, conversation_summary.py,
                 platforms/whatsapp_status_watcher.py,
                 model_config.py, langgraph_workflow.py
"""

import sqlite3
import json
import re
import math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

DECAY_HALF_LIFE_DAYS = 180   # interest signal halves every 6 months

INTEREST_CATEGORIES = {
    "tech":        {"icon": "💻", "color": "#58a6ff"},
    "design":      {"icon": "🎨", "color": "#bc8cff"},
    "books":       {"icon": "📚", "color": "#3fb950"},
    "food":        {"icon": "🍕", "color": "#f78166"},
    "fitness":     {"icon": "💪", "color": "#3fb950"},
    "travel":      {"icon": "✈️", "color": "#d29922"},
    "gaming":      {"icon": "🎮", "color": "#4fc3f7"},
    "music":       {"icon": "🎵", "color": "#bc8cff"},
    "finance":     {"icon": "💹", "color": "#3fb950"},
    "education":   {"icon": "🎓", "color": "#58a6ff"},
    "career":      {"icon": "💼", "color": "#d29922"},
    "family":      {"icon": "👨‍👩‍👧", "color": "#f78166"},
    "spirituality":{"icon": "🕌", "color": "#8b949e"},
    "sports":      {"icon": "⚽", "color": "#3fb950"},
}

KEYWORD_MAP = {
    "tech":     ["python","javascript","react","node","api","backend","frontend",
                 "developer","engineer","coding","programming","software","ai",
                 "machine learning","data science","devops","cloud","aws","docker",
                 "kubernetes","typescript","rust","golang","nextjs","fastapi",
                 "database","linux","github","vscode","algorithm","startup","saas"],
    "design":   ["figma","ui","ux","design","photoshop","illustrator","sketch",
                 "prototype","wireframe","typography","branding","creative",
                 "graphic","canva","procreate","color","layout","responsive"],
    "books":    ["book","reading","novel","author","kindle","literature",
                 "nonfiction","fiction","biography","audiobook","goodreads"],
    "food":     ["food","cooking","recipe","restaurant","coffee","tea","baking",
                 "chef","foodie","biryani","pizza","sushi","vegan","cuisine"],
    "fitness":  ["gym","workout","fitness","running","yoga","exercise","health",
                 "muscle","protein","marathon","cycling","swimming","crossfit"],
    "travel":   ["travel","trip","vacation","flight","hotel","backpack",
                 "explore","adventure","tourism","visa","airport","destination"],
    "gaming":   ["game","gaming","playstation","xbox","steam","esports","rpg",
                 "fps","nintendo","twitch","valorant","minecraft","gamer"],
    "music":    ["music","song","guitar","piano","singing","concert","spotify",
                 "band","album","playlist","rapper","beats","melody","dj"],
    "finance":  ["invest","stock","crypto","bitcoin","trading","finance",
                 "portfolio","dividend","market","mutual fund","nft","defi"],
    "education":["study","university","degree","course","exam","thesis",
                 "research","phd","masters","scholarship","lecture","campus"],
    "career":   ["promoted","promotion","job","hired","interview","resume",
                 "salary","manager","director","ceo","cto","leadership","role"],
    "family":   ["family","baby","married","wedding","parent","child","wife",
                 "husband","son","daughter","anniversary","nikkah"],
    "spirituality":["prayer","namaz","quran","ramadan","eid","hajj","umrah",
                    "alhamdulillah","mashallah","dua","mosque","masjid"],
    "sports":   ["football","cricket","basketball","tennis","soccer","match",
                 "league","tournament","goal","champion","fifa","ipl","bpl"],
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_interest_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interest_signals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            interest        TEXT NOT NULL,
            category        TEXT NOT NULL,
            source          TEXT NOT NULL DEFAULT 'manual',
            source_text     TEXT,
            confidence      REAL NOT NULL DEFAULT 0.5,
            detected_at     TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interest_profiles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            category        TEXT NOT NULL,
            score           REAL NOT NULL DEFAULT 0.0,
            top_interests   TEXT,
            signal_count    INTEGER NOT NULL DEFAULT 0,
            last_signal_at  TEXT,
            updated_at      TEXT NOT NULL,
            UNIQUE(contact_id, category)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_is_contact
        ON interest_signals(contact_id)
    """)
    conn.commit()
    conn.close()


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Interest extraction ───────────────────────────────────────────────────────

def extract_interests(text: str) -> list[dict]:
    """
    Extract interests from free text using keyword matching.

    Returns:
        List of { interest, category, confidence }
    """
    text_lower = text.lower()
    found      = []
    seen       = set()

    for category, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            pattern = rf'\b{re.escape(kw)}\b'
            if re.search(pattern, text_lower) and kw not in seen:
                seen.add(kw)
                # Confidence: longer keywords = higher confidence
                conf = min(0.9, 0.4 + len(kw) * 0.03)
                found.append({
                    "interest":   kw,
                    "category":   category,
                    "confidence": round(conf, 2),
                })

    # Sort by confidence descending
    found.sort(key=lambda x: -x["confidence"])
    return found


def extract_interests_ai(text: str, contact_name: str = "") -> list[dict]:
    """
    Use AI to extract interests (higher quality, needs API key).
    Falls back to keyword extraction if AI unavailable.
    """
    try:
        from model_config import generate as model_generate
    except ImportError:
        return extract_interests(text)

    prompt = (
        f"Extract specific interests, hobbies, and topics from this text "
        f"about {contact_name or 'a person'}:\n\n"
        f"\"{text}\"\n\n"
        f"Return ONLY a JSON array of objects with keys: "
        f"interest (string), category (one of: {','.join(INTEREST_CATEGORIES.keys())}), "
        f"confidence (0.0-1.0).\n"
        f"Example: [{{'interest':'Python','category':'tech','confidence':0.9}}]\n"
        f"No other text, just the JSON array."
    )

    try:
        result = model_generate(prompt, task="scoring", mode="fast",
                                max_tokens=200)
        raw = result.get("text", "")
        # Strip markdown fences
        raw = raw.strip().strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [{"interest":   p.get("interest",""),
                     "category":   p.get("category","tech"),
                     "confidence": p.get("confidence",0.5)}
                    for p in parsed if p.get("interest")]
    except Exception:
        pass

    return extract_interests(text)


# ── Signal recording ──────────────────────────────────────────────────────────

def record_interests(
    contact_id:   str,
    contact_name: str,
    text:         str,
    source:       str = "manual",
    use_ai:       bool = False,
) -> list[dict]:
    """
    Extract interests from text and record them as signals.

    Args:
        contact_id:   Unique contact identifier.
        contact_name: Full name.
        text:         Source text (status update, reply, note, etc.)
        source:       manual / status_update / reply / life_event / profile
        use_ai:       Use AI extraction (better quality, needs API key).

    Returns:
        List of recorded interest signals.
    """
    init_interest_tables()

    if use_ai:
        interests = extract_interests_ai(text, contact_name)
    else:
        interests = extract_interests(text)

    if not interests:
        return []

    now  = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    for i in interests:
        conn.execute("""
            INSERT INTO interest_signals
                (contact_id, contact_name, interest, category,
                 source, source_text, confidence, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (contact_id, contact_name, i["interest"], i["category"],
              source, text[:200], i["confidence"], now))
    conn.commit()
    conn.close()

    # Refresh profile
    _refresh_profile(contact_id, contact_name)

    return interests


def _refresh_profile(contact_id: str, contact_name: str = ""):
    """Recompute time-weighted interest scores for a contact."""
    init_interest_tables()
    conn = _db()
    rows = conn.execute("""
        SELECT interest, category, confidence, detected_at
        FROM interest_signals WHERE contact_id=?
        ORDER BY detected_at ASC
    """, (contact_id,)).fetchall()
    conn.close()

    if not rows:
        return

    now = datetime.now()
    cat_scores: dict = {}   # category → total weighted score
    cat_interests: dict = {}  # category → { interest: weighted_score }
    cat_last: dict = {}     # category → last signal date
    cat_count: dict = {}    # category → signal count

    for r in rows:
        cat   = r["category"]
        intr  = r["interest"]
        conf  = r["confidence"]
        try:
            sig_date = datetime.fromisoformat(r["detected_at"])
        except (ValueError, TypeError):
            sig_date = now

        # Time decay: exponential with half-life
        days_ago = max(0, (now - sig_date).days)
        decay    = math.pow(0.5, days_ago / DECAY_HALF_LIFE_DAYS)
        weighted = conf * decay

        cat_scores[cat]     = cat_scores.get(cat, 0) + weighted
        cat_count[cat]      = cat_count.get(cat, 0) + 1
        cat_last[cat]       = max(cat_last.get(cat, ""), r["detected_at"])

        if cat not in cat_interests:
            cat_interests[cat] = {}
        cat_interests[cat][intr] = (
            cat_interests[cat].get(intr, 0) + weighted)

    # Persist profiles
    conn = sqlite3.connect(DB_PATH)
    now_str = now.isoformat()
    for cat, score in cat_scores.items():
        # Top 5 interests in this category
        sorted_interests = sorted(
            cat_interests[cat].items(), key=lambda x: -x[1])[:5]
        top_json = json.dumps([i[0] for i in sorted_interests])

        conn.execute("""
            INSERT INTO interest_profiles
                (contact_id, category, score, top_interests,
                 signal_count, last_signal_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(contact_id, category) DO UPDATE SET
                score          = excluded.score,
                top_interests  = excluded.top_interests,
                signal_count   = excluded.signal_count,
                last_signal_at = excluded.last_signal_at,
                updated_at     = excluded.updated_at
        """, (contact_id, cat, round(score, 3), top_json,
              cat_count[cat], cat_last[cat], now_str))
    conn.commit()
    conn.close()


# ── Retrieval ─────────────────────────────────────────────────────────────────

def get_interest_profile(contact_id: str) -> list[dict]:
    """
    Get ranked interest categories for a contact.

    Returns:
        List of { category, score, top_interests, signal_count, icon, color }
        sorted by score descending.
    """
    init_interest_tables()
    conn = _db()
    rows = conn.execute("""
        SELECT category, score, top_interests, signal_count, last_signal_at
        FROM interest_profiles WHERE contact_id=?
        ORDER BY score DESC
    """, (contact_id,)).fetchall()
    conn.close()

    return [{
        "category":      r["category"],
        "score":         round(r["score"], 3),
        "top_interests": json.loads(r["top_interests"] or "[]"),
        "signal_count":  r["signal_count"],
        "last_signal":   (r["last_signal_at"] or "")[:10],
        "icon":          INTEREST_CATEGORIES.get(r["category"],{}).get("icon","?"),
        "color":         INTEREST_CATEGORIES.get(r["category"],{}).get("color","#8b949e"),
    } for r in rows]


def get_top_interests(contact_id: str, limit: int = 10) -> list[str]:
    """Get flat list of top interest keywords for a contact."""
    profile = get_interest_profile(contact_id)
    result  = []
    for p in profile:
        for i in p["top_interests"]:
            if i not in result:
                result.append(i)
            if len(result) >= limit:
                return result
    return result


def get_interest_context(contact_id: str, contact_name: str = "") -> str:
    """Build a prompt-ready context string from interests."""
    profile = get_interest_profile(contact_id)
    if not profile:
        return f"(No interests tracked for {contact_name or contact_id}.)"

    lines = [f"Known interests for {contact_name or contact_id}:"]
    for p in profile[:5]:
        interests_str = ", ".join(p["top_interests"][:3])
        lines.append(f"- {p['icon']} {p['category']}: {interests_str} "
                     f"(score {p['score']:.1f})")
    return "\n".join(lines)


def get_interest_evolution(
    contact_id: str,
    months_back: int = 12,
) -> list[dict]:
    """
    Track how interests changed over time (monthly buckets).

    Returns:
        List of { month, categories: { cat: signal_count } }
    """
    init_interest_tables()
    conn = _db()
    cutoff = (datetime.now() - timedelta(days=months_back*30)).isoformat()
    rows = conn.execute("""
        SELECT category, detected_at
        FROM interest_signals
        WHERE contact_id=? AND detected_at >= ?
        ORDER BY detected_at ASC
    """, (contact_id, cutoff)).fetchall()
    conn.close()

    months: dict = {}
    for r in rows:
        month = r["detected_at"][:7]   # YYYY-MM
        if month not in months:
            months[month] = {}
        cat = r["category"]
        months[month][cat] = months[month].get(cat, 0) + 1

    return [{"month": m, "categories": cats} for m, cats in months.items()]


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_interest_tables()
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM interest_signals").fetchone()[0]
    conn.close()
    if count > 0:
        return

    demo = [
        ("urn_rakib_001", "Rakib Hossain", [
            ("Working on distributed systems with Python and Docker at Pathao", "profile"),
            ("Just finished reading Clean Code — amazing book", "status_update"),
            ("Morning gym session done! 💪 Leg day is brutal", "status_update"),
            ("Promoted to Senior Backend Engineer! Alhamdulillah 🚀", "life_event"),
        ]),
        ("urn_nadia_002", "Nadia Islam", [
            ("New Figma prototype ready for the bKash redesign project 🎨", "status_update"),
            ("Coffee and design reviews — perfect Monday ☕", "status_update"),
            ("Started a typography course on Coursera", "status_update"),
        ]),
        ("urn_mim_004", "Mim Chowdhury", [
            ("Training a new transformer model for Bengali NLP 🤖", "status_update"),
            ("✈️ Off to Singapore for a data science conference!", "status_update"),
            ("Published my first research paper on recommendation systems!", "life_event"),
            ("Reading Thinking Fast and Slow — mind-blowing", "status_update"),
        ]),
    ]

    now = datetime.now()
    for cid, cname, entries in demo:
        for i, (text, source) in enumerate(entries):
            # Stagger dates
            offset = timedelta(days=(len(entries)-i)*30)
            interests = extract_interests(text)
            conn = sqlite3.connect(DB_PATH)
            dt   = (now - offset).isoformat()
            for intr in interests:
                conn.execute("""
                    INSERT INTO interest_signals
                        (contact_id, contact_name, interest, category,
                         source, source_text, confidence, detected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (cid, cname, intr["interest"], intr["category"],
                      source, text[:200], intr["confidence"], dt))
            conn.commit()
            conn.close()
        _refresh_profile(cid, cname)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Interest Graph", page_icon="🕸",
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
    .ig-card{background:var(--surface);border:1px solid var(--border);
             border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .int-pill{display:inline-flex;align-items:center;gap:4px;font-size:0.65rem;
              font-weight:600;padding:3px 8px;border-radius:16px;margin:2px;}
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

    init_interest_tables()
    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🕸</span>
      <h1>Interest Graph</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    conn = _db()
    total_signals = conn.execute("SELECT COUNT(*) FROM interest_signals").fetchone()[0]
    total_contacts = conn.execute("SELECT COUNT(DISTINCT contact_id) FROM interest_signals").fetchone()[0]
    total_cats = conn.execute("SELECT COUNT(DISTINCT category) FROM interest_signals").fetchone()[0]
    conn.close()

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Signals",    total_signals,  "#f78166"),
        (m2, "Contacts",   total_contacts, "#58a6ff"),
        (m3, "Categories", total_cats,     "#3fb950"),
        (m4, "Half-life",  f"{DECAY_HALF_LIFE_DAYS}d", "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" '
                        f'style="color:{color};font-size:0.95rem">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.5], gap="large")

    with left:
        st.markdown('<div class="section-title">Extract Interests</div>',
                    unsafe_allow_html=True)
        e_cid  = st.text_input("Contact ID", placeholder="urn_rakib_001",
                               label_visibility="collapsed", key="ecid")
        e_name = st.text_input("Name", placeholder="Rakib Hossain",
                               label_visibility="collapsed", key="ename")
        e_text = st.text_area("Source text", height=60,
                              label_visibility="collapsed", key="etext",
                              placeholder="Working on Python backend with Docker...")
        if st.button("🔍 Extract & Record", type="primary",
                     use_container_width=True):
            if e_cid and e_text:
                found = record_interests(e_cid, e_name or e_cid, e_text,
                                         source="manual")
                if found:
                    st.success(f"Extracted {len(found)} interests")
                else:
                    st.info("No interests detected")
                st.rerun()

        # Contact profiles
        st.markdown('<div class="section-title">Contact Profiles</div>',
                    unsafe_allow_html=True)
        conn = _db()
        cids = conn.execute("""
            SELECT DISTINCT contact_id, contact_name
            FROM interest_signals ORDER BY contact_name
        """).fetchall()
        conn.close()

        for row in cids:
            cid   = row["contact_id"]
            cname = row["contact_name"]
            profile = get_interest_profile(cid)
            if not profile:
                continue
            top_score = profile[0]["score"] if profile else 0
            pills = ""
            for p in profile[:4]:
                pills += (f'<span class="int-pill" style="background:{p["color"]}22;'
                          f'color:{p["color"]};border:1px solid {p["color"]}44">'
                          f'{p["icon"]} {p["category"]}</span>')

            sel = st.session_state.get("sel_cid") == cid
            st.markdown(f"""
            <div class="ig-card" style="{'border-color:var(--accent);' if sel else ''}">
              <div style="display:flex;justify-content:space-between;margin-bottom:6px">
                <span style="font-weight:700">{cname}</span>
                <span style="font-size:0.68rem;color:#8b949e">
                  {sum(p['signal_count'] for p in profile)} signals
                </span>
              </div>
              <div>{pills}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"View details", key=f"vd_{cid}",
                         use_container_width=True):
                st.session_state["sel_cid"]  = cid
                st.session_state["sel_name"] = cname
                st.rerun()

    with right:
        sel_cid  = st.session_state.get("sel_cid")
        sel_name = st.session_state.get("sel_name", "")
        if sel_cid:
            st.markdown(f'<div class="section-title">'
                        f'{sel_name} — Interest Profile</div>',
                        unsafe_allow_html=True)
            profile = get_interest_profile(sel_cid)
            max_sc  = max((p["score"] for p in profile), default=1)

            for p in profile:
                pct = int(p["score"] / max_sc * 100) if max_sc else 0
                interests_str = ", ".join(p["top_interests"][:5])
                st.markdown(f"""
                <div class="ig-card" style="border-left:3px solid {p['color']}">
                  <div style="display:flex;justify-content:space-between;
                              margin-bottom:4px">
                    <span style="font-weight:700">{p['icon']} {p['category']}</span>
                    <span style="font-family:'JetBrains Mono',monospace;
                                 font-size:0.78rem;color:{p['color']}">
                      {p['score']:.2f}
                    </span>
                  </div>
                  <div style="background:#0d1117;border-radius:3px;height:6px;
                              overflow:hidden;margin-bottom:6px">
                    <div style="width:{pct}%;height:100%;background:{p['color']};
                                border-radius:3px"></div>
                  </div>
                  <div style="font-size:0.72rem;color:#c9d1d9">
                    {interests_str}
                  </div>
                  <div style="font-size:0.62rem;color:#8b949e;margin-top:3px">
                    {p['signal_count']} signals · last {p['last_signal']}
                  </div>
                </div>
                """, unsafe_allow_html=True)

            # Prompt context preview
            st.markdown('<div class="section-title">Prompt Context</div>',
                        unsafe_allow_html=True)
            ctx = get_interest_context(sel_cid, sel_name)
            st.code(ctx, language=None)
        else:
            st.info("Click a contact to view their interest profile.")

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Interest Graph</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_interest_tables()
    _seed_demo()
    print("=== Interest Graph -- self test ===\n")

    # Test extraction
    test_text = "Working on Python backend with Docker and Kubernetes at Pathao. Also training for a marathon!"
    found = extract_interests(test_text)
    print(f"Extracted from: \"{test_text[:50]}...\"")
    for f in found:
        cat_meta = INTEREST_CATEGORIES.get(f["category"],{})
        print(f"  {cat_meta.get('icon','?')} {f['interest']:<16} "
              f"{f['category']:<12} conf={f['confidence']}")

    # Show profiles
    print("\nContact interest profiles:")
    conn = _db()
    cids = conn.execute("""
        SELECT DISTINCT contact_id, contact_name FROM interest_signals
    """).fetchall()
    conn.close()

    for row in cids:
        profile = get_interest_profile(row["contact_id"])
        top     = get_top_interests(row["contact_id"], limit=5)
        print(f"\n  {row['contact_name']}:")
        for p in profile[:4]:
            interests = ", ".join(p["top_interests"][:3])
            print(f"    {p['icon']} {p['category']:<14} "
                  f"score={p['score']:<6.3f} [{interests}]")
        print(f"    Top: {', '.join(top[:5])}")

    # Context builder
    print(f"\nInterest context for Rakib:")
    ctx = get_interest_context("urn_rakib_001", "Rakib Hossain")
    for line in ctx.split("\n"):
        print(f"  {line}")
else:
    render_dashboard()
