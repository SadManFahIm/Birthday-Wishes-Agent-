"""
Multi-Model Consensus -- Birthday Wishes Agent v9.0
Generates birthday wishes using both Gemini and GPT-4o independently,
scores each wish on personalization (1-10), and picks the best one.
Falls back gracefully if one model is unavailable.

Flow:
  1. Generate wish with Gemini 2.5 Pro
  2. Generate wish with GPT-4o (parallel)
  3. Score both wishes (name, job, memory, tone, uniqueness)
  4. Pick winner; log both for future self-improvement analytics

Integrates with: ai/self_improving_agent.py, ai/wish_scorer.py,
                 dashboards/batch_approve_queue.py, agent.py
"""

import sqlite3
import os
import time
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path("agent_history.db")

# ── Score weights ─────────────────────────────────────────────────────────────

SCORE_COMPONENTS = {
    "name_mentioned":  {"max": 2, "weight": 1.0},
    "job_company_ref": {"max": 2, "weight": 1.0},
    "memory_context":  {"max": 2, "weight": 1.2},
    "unique_language": {"max": 2, "weight": 0.8},
    "warm_tone":       {"max": 1, "weight": 1.0},
    "right_length":    {"max": 1, "weight": 0.8},
}

MODELS = {
    "gemini": {"label": "Gemini 2.5 Pro", "color": "#4fc3f7", "icon": "♊"},
    "gpt4o":  {"label": "GPT-4o",         "color": "#3fb950", "icon": "🤖"},
    "mock":   {"label": "Mock (testing)",  "color": "#8b949e", "icon": "🔧"},
}

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_consensus_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consensus_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id          TEXT NOT NULL,
            contact_name        TEXT NOT NULL,
            platform            TEXT NOT NULL,
            gemini_wish         TEXT,
            gemini_score        REAL,
            gemini_latency_ms   INTEGER,
            gpt4o_wish          TEXT,
            gpt4o_score         REAL,
            gpt4o_latency_ms    INTEGER,
            winner_model        TEXT NOT NULL,
            winner_wish         TEXT NOT NULL,
            winner_score        REAL NOT NULL,
            score_delta         REAL,
            sent                INTEGER NOT NULL DEFAULT 0,
            logged_at           TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_wish(wish_text: str, contact: dict) -> dict:
    """
    Score a wish 0-10 on personalization.
    contact keys: name, job, company, memory (optional), industry (optional)
    """
    text  = wish_text.lower()
    comps = {}
    first = contact.get("name", "").split()[0].lower() if contact.get("name") else ""

    comps["name_mentioned"]  = 2 if first and first in text else 0
    job_hit = (contact.get("job","").split()[-1].lower() in text
               or contact.get("company","").lower() in text)
    comps["job_company_ref"] = 2 if job_hit else 0
    mem_words = contact.get("memory","").lower().split()[:4]
    comps["memory_context"]  = 2 if any(w in text for w in mem_words if len(w) > 3) else 0
    generic = ["have a great day","best wishes","many happy returns"]
    comps["unique_language"] = 2 if not any(g in text for g in generic) else 0
    warm = ["hope","wishing","amazing","great","celebrate","brilliant"]
    comps["warm_tone"]       = 1 if any(w in text for w in warm) else 0
    wc = len(wish_text.split())
    comps["right_length"]    = 1 if 12 <= wc <= 70 else 0

    weighted = sum(
        comps[k] * SCORE_COMPONENTS[k]["weight"]
        for k in comps
    )
    max_weighted = sum(
        SCORE_COMPONENTS[k]["max"] * SCORE_COMPONENTS[k]["weight"]
        for k in SCORE_COMPONENTS
    )
    score = round((weighted / max_weighted) * 10, 1) if max_weighted else 0
    return {"score": score, "components": comps, "word_count": wc}


# ── Model callers ─────────────────────────────────────────────────────────────

def _build_prompt(contact: dict, style: str = "warm") -> str:
    return (
        f"Write a {style} birthday wish for {contact.get('name','them')} "
        f"who works as {contact.get('job','a professional')} "
        f"at {contact.get('company','their company')}. "
        f"Context: {contact.get('memory','')}. "
        f"2-3 sentences, personal, no generic phrases. "
        f"Return ONLY the wish text."
    )


def _call_gemini(prompt: str) -> tuple:
    """
    Call Gemini 2.5 Pro. Returns (wish_text, latency_ms).
    Requires GOOGLE_API_KEY in environment.
    Falls back to mock if not configured.
    """
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return _mock_wish("gemini"), 0

    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
        model  = genai.GenerativeModel("gemini-2.5-pro")
        t0     = time.time()
        resp   = model.generate_content(prompt)
        ms     = int((time.time() - t0) * 1000)
        return resp.text.strip(), ms
    except Exception as exc:
        print(f"[Consensus] Gemini error: {exc}")
        return None, 0


def _call_gpt4o(prompt: str) -> tuple:
    """
    Call GPT-4o. Returns (wish_text, latency_ms).
    Requires OPENAI_API_KEY in environment.
    Falls back to mock if not configured.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return _mock_wish("gpt4o"), 0

    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key)
        t0     = time.time()
        resp   = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.8,
        )
        ms   = int((time.time() - t0) * 1000)
        text = resp.choices[0].message.content.strip()
        return text, ms
    except Exception as exc:
        print(f"[Consensus] GPT-4o error: {exc}")
        return None, 0


def _mock_wish(model: str) -> str:
    """Realistic mock wishes for testing without API keys."""
    wishes = {
        "gemini": [
            "Happy Birthday {name}! Your work as {job} at {company} continues to inspire. {memory_ref} Wishing you a year as brilliant as your contributions.",
            "Hey {name}, hope your birthday is as outstanding as the impact you make at {company}. {memory_ref} Here's to another great year!",
        ],
        "gpt4o": [
            "Happy Birthday {name}! Being a {job} at {company} suits you perfectly. {memory_ref} May this year bring everything you've been working toward.",
            "Wishing you a brilliant birthday {name}! The dedication you bring to {company} as {job} is genuinely impressive. {memory_ref} Enjoy every moment today!",
        ],
    }
    return random.choice(wishes.get(model, wishes["gemini"]))


def _fill_mock(template: str, contact: dict) -> str:
    first      = contact.get("name","").split()[0]
    mem_words  = contact.get("memory","").split()[:4]
    mem_ref    = " ".join(mem_words) + "..." if mem_words else ""
    return (template
            .replace("{name}", first)
            .replace("{job}", contact.get("job","your role"))
            .replace("{company}", contact.get("company","your company"))
            .replace("{memory_ref}", mem_ref))


# ── Main consensus function ───────────────────────────────────────────────────

def generate_consensus_wish(
    contact_id:   str,
    contact:      dict,
    platform:     str    = "LinkedIn",
    style:        str    = "warm",
    verbose:      bool   = True,
) -> dict:
    """
    Generate wishes from both models, score them, return the winner.

    Args:
        contact_id: Unique contact identifier for logging.
        contact:    Dict with name, job, company, memory (optional).
        platform:   Target platform.
        style:      Wish style hint (warm/formal/funny).
        verbose:    Print comparison to console.

    Returns:
        {
          winner_model, winner_wish, winner_score,
          gemini_wish, gemini_score,
          gpt4o_wish,  gpt4o_score,
          score_delta, log_id
        }
    """
    init_consensus_tables()
    prompt = _build_prompt(contact, style)

    # Generate from both models
    g_text, g_ms = _call_gemini(prompt)
    o_text, o_ms = _call_gpt4o(prompt)

    # Fill mock templates if needed (no API key)
    if g_text and "{name}" in g_text:
        g_text = _fill_mock(g_text, contact)
    if o_text and "{name}" in o_text:
        o_text = _fill_mock(o_text, contact)

    # Score both
    g_scored = score_wish(g_text, contact) if g_text else {"score": 0}
    o_scored = score_wish(o_text, contact) if o_text else {"score": 0}
    g_score  = g_scored["score"]
    o_score  = o_scored["score"]

    # Pick winner
    if g_text and o_text:
        if g_score >= o_score:
            winner_model, winner_wish, winner_score = "gemini", g_text, g_score
        else:
            winner_model, winner_wish, winner_score = "gpt4o", o_text, o_score
    elif g_text:
        winner_model, winner_wish, winner_score = "gemini", g_text, g_score
    elif o_text:
        winner_model, winner_wish, winner_score = "gpt4o", o_text, o_score
    else:
        mock = _fill_mock(_mock_wish("gemini"), contact)
        winner_model, winner_wish, winner_score = "mock", mock, 5.0

    delta = round(abs(g_score - o_score), 1)

    if verbose:
        print(f"[Consensus] {contact.get('name')}")
        print(f"  Gemini  {g_score:4.1f}/10  {(g_text or '')[:60]}...")
        print(f"  GPT-4o  {o_score:4.1f}/10  {(o_text or '')[:60]}...")
        print(f"  Winner: {winner_model} (delta={delta})")

    # Log
    conn   = sqlite3.connect(DB_PATH)
    cur    = conn.execute("""
        INSERT INTO consensus_log
            (contact_id, contact_name, platform,
             gemini_wish, gemini_score, gemini_latency_ms,
             gpt4o_wish,  gpt4o_score,  gpt4o_latency_ms,
             winner_model, winner_wish, winner_score,
             score_delta, logged_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (contact_id, contact.get("name",""), platform,
          g_text, g_score, g_ms,
          o_text, o_score, o_ms,
          winner_model, winner_wish, winner_score,
          delta, datetime.now().isoformat()))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        "winner_model":  winner_model,
        "winner_wish":   winner_wish,
        "winner_score":  winner_score,
        "gemini_wish":   g_text,
        "gemini_score":  g_score,
        "gpt4o_wish":    o_text,
        "gpt4o_score":   o_score,
        "score_delta":   delta,
        "log_id":        log_id,
    }


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_model_stats(limit: int = 100) -> dict:
    """Return win rate and avg score per model over last N entries."""
    init_consensus_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT winner_model, COUNT(*) as wins,
               AVG(winner_score) as avg_score
        FROM consensus_log
        GROUP BY winner_model
    """).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM consensus_log").fetchone()[0]
    conn.close()

    stats = {}
    for r in rows:
        stats[r[0]] = {
            "wins":      r[1],
            "win_rate":  round(r[1] / total, 2) if total else 0,
            "avg_score": round(r[2], 1),
        }
    stats["total"] = total
    return stats


def get_recent_comparisons(limit: int = 10) -> list[dict]:
    """Return recent head-to-head comparisons."""
    init_consensus_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_name, gemini_score, gpt4o_score,
               winner_model, winner_score, score_delta, logged_at
        FROM consensus_log ORDER BY logged_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"contact_name": r[0], "gemini_score": r[1], "gpt4o_score": r[2],
             "winner_model": r[3], "winner_score": r[4],
             "score_delta": r[5], "logged_at": r[6]} for r in rows]


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Multi-Model Consensus", page_icon="⚖️",
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
    .model-card{background:var(--surface);border:1px solid var(--border);
                border-radius:12px;padding:16px 18px;}
    .wish-box{background:#010409;border:1px solid var(--border);border-radius:8px;
              padding:12px 14px;font-size:0.82rem;color:#c9d1d9;line-height:1.6;
              min-height:80px;margin:8px 0;}
    .winner-badge{background:#051a09;border:1px solid #3fb950;border-radius:8px;
                  padding:8px 14px;font-size:0.75rem;color:#3fb950;font-weight:700;
                  text-align:center;margin-top:8px;}
    .cmp-row{background:var(--surface);border:1px solid var(--border);
             border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:0.78rem;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.6rem;color:#8b949e;text-transform:uppercase;
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

    init_consensus_tables()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">⚖️</span>
      <h1>Multi-Model Consensus</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    stats = get_model_stats()
    total = stats.get("total", 0)

    m1, m2, m3, m4 = st.columns(4)
    g_wins = stats.get("gemini", {}).get("wins", 0)
    o_wins = stats.get("gpt4o",  {}).get("wins", 0)
    for col, lbl, val, color in [
        (m1, "Total Comparisons", total,                     "#e6edf3"),
        (m2, "Gemini Wins",       f"{g_wins} ({stats.get('gemini',{}).get('win_rate',0):.0%})", "#4fc3f7"),
        (m3, "GPT-4o Wins",       f"{o_wins} ({stats.get('gpt4o',{}).get('win_rate',0):.0%})",  "#3fb950"),
        (m4, "Avg Winner Score",
         f"{stats.get('gemini',{}).get('avg_score', 0):.1f}/10", "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Generate & Compare</div>',
                    unsafe_allow_html=True)

        DEMO = [
            {"id":"urn_rakib_001","name":"Rakib Hossain","job":"Senior Backend Engineer",
             "company":"Pathao","memory":"you discussed distributed systems at PyCon BD"},
            {"id":"urn_nadia_002","name":"Nadia Islam","job":"Product Designer",
             "company":"bKash","memory":"she shipped a major redesign recently"},
            {"id":"urn_mim_004","name":"Mim Chowdhury","job":"Data Scientist",
             "company":"Brain Station 23","memory":"university batchmates"},
        ]
        names = [c["name"] for c in DEMO]
        sel   = st.selectbox("Contact", names, label_visibility="collapsed", key="sel_c")
        contact_obj = next(c for c in DEMO if c["name"] == sel)
        style_opt   = st.selectbox("Style", ["warm","formal","funny","poetic"],
                                   label_visibility="collapsed", key="sel_s")

        if st.button("Generate & Compare", type="primary", use_container_width=True):
            with st.spinner("Asking both models..."):
                result = generate_consensus_wish(
                    contact_obj["id"], contact_obj, "LinkedIn",
                    style_opt, verbose=False)
            st.session_state["last_result"] = result
            st.rerun()

        res = st.session_state.get("last_result")
        if res:
            gc1, gc2 = st.columns(2)
            with gc1:
                g_color = "#4fc3f7"
                st.markdown(f"""
                <div class="model-card" style="border-color:{g_color}55">
                  <div style="font-weight:700;color:{g_color}">♊ Gemini 2.5 Pro</div>
                  <div style="font-size:1.1rem;font-weight:700;margin:4px 0">
                    {res['gemini_score']}/10
                  </div>
                  <div class="wish-box">{res['gemini_wish'] or 'Unavailable'}</div>
                  {'<div class="winner-badge">Winner</div>' if res["winner_model"]=="gemini" else ''}
                </div>
                """, unsafe_allow_html=True)
            with gc2:
                o_color = "#3fb950"
                st.markdown(f"""
                <div class="model-card" style="border-color:{o_color}55">
                  <div style="font-weight:700;color:{o_color}">🤖 GPT-4o</div>
                  <div style="font-size:1.1rem;font-weight:700;margin:4px 0">
                    {res['gpt4o_score']}/10
                  </div>
                  <div class="wish-box">{res['gpt4o_wish'] or 'Unavailable'}</div>
                  {'<div class="winner-badge">Winner</div>' if res["winner_model"]=="gpt4o" else ''}
                </div>
                """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;
                        padding:12px 16px;margin-top:10px;font-size:0.8rem;">
              Winner: <strong style="color:#3fb950">{MODELS.get(res['winner_model'],{}).get('label', res['winner_model'])}</strong>
              with score <strong>{res['winner_score']}/10</strong>
              (delta: {res['score_delta']})
            </div>
            """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Recent Comparisons</div>',
                    unsafe_allow_html=True)
        comparisons = get_recent_comparisons(limit=8)
        if not comparisons:
            st.caption("No comparisons yet. Generate one on the left.")
        for c in comparisons:
            wm    = c["winner_model"]
            color = MODELS.get(wm, {}).get("color", "#8b949e")
            icon  = MODELS.get(wm, {}).get("icon", "?")
            ts    = c["logged_at"][:16].replace("T", " ")
            st.markdown(f"""
            <div class="cmp-row">
              <div style="font-weight:700">{c['contact_name']}</div>
              <div style="color:#8b949e;font-size:0.68rem;margin-top:2px">
                ♊ Gemini: {c['gemini_score']}/10 |
                🤖 GPT-4o: {c['gpt4o_score']}/10 |
                Winner: <span style="color:{color}">{icon} {wm}</span>
                ({c['score_delta']} delta) | {ts}
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Model win rate bars
        st.markdown('<div class="section-title">Model Win Rates</div>',
                    unsafe_allow_html=True)
        for model_key, meta in MODELS.items():
            if model_key == "mock":
                continue
            s    = stats.get(model_key, {})
            rate = s.get("win_rate", 0)
            pct  = int(rate * 100)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              <div style="width:100px;font-size:0.76rem">{meta['icon']} {meta['label']}</div>
              <div style="flex:1;background:#0d1117;border-radius:4px;height:18px;overflow:hidden">
                <div style="width:{pct}%;height:100%;background:{meta['color']};border-radius:4px">
                </div>
              </div>
              <div style="width:36px;font-size:0.72px;font-family:'JetBrains Mono',monospace;
                          color:#8b949e;font-size:0.72rem">{pct}%</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>Multi-Model Consensus</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_consensus_tables()
    print("=== Multi-Model Consensus -- self test ===\n")
    contacts = [
        {"id":"urn_rakib_001","name":"Rakib Hossain",
         "job":"Senior Backend Engineer","company":"Pathao",
         "memory":"discussed distributed systems at PyCon BD"},
        {"id":"urn_nadia_002","name":"Nadia Islam",
         "job":"Product Designer","company":"bKash",
         "memory":"shipped a major app redesign"},
    ]
    for c in contacts:
        r = generate_consensus_wish(c["id"], c, verbose=True)
        print(f"  Winner: {r['winner_model']} score={r['winner_score']}/10\n")
    stats = get_model_stats()
    print(f"Stats: Gemini {stats.get('gemini',{}).get('wins',0)} wins | "
          f"GPT-4o {stats.get('gpt4o',{}).get('wins',0)} wins | "
          f"Total {stats.get('total',0)}")
else:
    render_dashboard()
