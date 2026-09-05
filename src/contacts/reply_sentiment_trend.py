"""
Reply Sentiment Trend — Birthday Wishes Agent v8.0
Tracks each contact's reply tone over time (excited → positive → neutral → cold → no_reply),
builds a per-contact and aggregate trend graph, and surfaces contacts whose sentiment
is declining before they become fully disengaged.

Sentiment levels (5 tiers):
  excited   → 😄  reply fast, lots of emoji, warm words
  positive  → 😊  friendly, engaged, timely
  neutral   → 😐  polite but brief, no emoji
  cold      → 🥶  very short, delayed, minimal
  no_reply  → 🔇  no response (logged as a data point)

Integrates with: agent.py, contact_timeline.py, insight_report.py
"""

import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Optional

DB_PATH = Path("agent_history.db")

# ── Sentiment config ──────────────────────────────────────────────────────────
SENTIMENT_LEVELS = ["excited", "positive", "neutral", "cold", "no_reply"]

SENTIMENT_META = {
    "excited":  {"emoji": "😄", "label": "Excited",  "score": 5, "color": "#3fb950"},
    "positive": {"emoji": "😊", "label": "Positive", "score": 4, "color": "#4fc3f7"},
    "neutral":  {"emoji": "😐", "label": "Neutral",  "score": 3, "color": "#d29922"},
    "cold":     {"emoji": "🥶", "label": "Cold",     "score": 2, "color": "#f78166"},
    "no_reply": {"emoji": "🔇", "label": "No Reply", "score": 1, "color": "#f85149"},
}

# Heuristic classifiers
EXCITED_WORDS  = ["amazing","love","so happy","wonderful","wow","awesome","fantastic",
                  "🎉","🥳","😍","🔥","💯","🙌","❤️","brilliant","incredible","thrilled"]
POSITIVE_WORDS = ["thank","thanks","appreciate","happy","great","good","nice",
                  "lovely","😊","🙏","☺️","glad","pleased"]
COLD_PATTERNS  = [r"^ok$", r"^okay$", r"^thanks?\.?$", r"^k$", r"^noted$"]

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_sentiment_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reply_sentiment_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            platform        TEXT NOT NULL,
            reply_text      TEXT,
            sentiment       TEXT NOT NULL,
            sentiment_score INTEGER NOT NULL,
            reply_delay_hrs REAL,
            wish_date       TEXT,
            logged_at       TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_sentiment_profile (
            contact_id      TEXT PRIMARY KEY,
            contact_name    TEXT NOT NULL,
            current_sentiment TEXT NOT NULL DEFAULT 'neutral',
            trend_direction TEXT NOT NULL DEFAULT 'stable',
            avg_score       REAL NOT NULL DEFAULT 3.0,
            last_sentiment  TEXT,
            last_updated    TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Sentiment classification ──────────────────────────────────────────────────

def classify_sentiment(
    reply_text:      Optional[str],
    reply_delay_hrs: Optional[float] = None,
) -> str:
    """
    Classify a reply's sentiment based on text content and reply speed.

    Args:
        reply_text:      Raw reply string. None or empty → no_reply.
        reply_delay_hrs: Hours between wish sent and reply received.

    Returns:
        Sentiment level string.
    """
    if not reply_text or reply_text.strip() == "":
        return "no_reply"

    text_lower = reply_text.lower().strip()
    word_count = len(text_lower.split())

    # Check excited signals
    for word in EXCITED_WORDS:
        if word.lower() in text_lower:
            return "excited"

    # Check cold patterns (very short, generic)
    if word_count <= 3:
        for pattern in COLD_PATTERNS:
            if re.match(pattern, text_lower, re.IGNORECASE):
                return "cold"

    # Delay penalty: very slow reply → downgrade
    if reply_delay_hrs is not None and reply_delay_hrs > 96:
        # >4 days → at best neutral
        for word in POSITIVE_WORDS:
            if word in text_lower:
                return "neutral"
        return "cold"

    # Positive signals
    for word in POSITIVE_WORDS:
        if word in text_lower:
            if word_count >= 8:
                return "positive"
            return "neutral"

    # Long reply with no positive/excited → neutral
    if word_count >= 8:
        return "neutral"

    return "cold"


# ── Logging ───────────────────────────────────────────────────────────────────

def log_reply_sentiment(
    contact_id:      str,
    contact_name:    str,
    platform:        str,
    reply_text:      Optional[str],
    reply_delay_hrs: Optional[float] = None,
    wish_date:       Optional[str] = None,
):
    """
    Classify and persist the sentiment of one reply.
    Call this whenever agent.py receives a reply.

    Args:
        contact_id:      Unique contact ID.
        contact_name:    Human-readable name.
        platform:        Platform the reply came from.
        reply_text:      Raw reply text (None = no reply received).
        reply_delay_hrs: Time between wish sent and reply (hours).
        wish_date:       ISO date of the wish that triggered this reply.
    """
    init_sentiment_tables()
    sentiment = classify_sentiment(reply_text, reply_delay_hrs)
    score     = SENTIMENT_META[sentiment]["score"]

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO reply_sentiment_log
            (contact_id, contact_name, platform, reply_text, sentiment,
             sentiment_score, reply_delay_hrs, wish_date, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        contact_id, contact_name, platform,
        (reply_text or "")[:500],
        sentiment, score,
        reply_delay_hrs, wish_date or date.today().isoformat(),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()

    _update_sentiment_profile(contact_id, contact_name, sentiment, score)
    return sentiment


def _update_sentiment_profile(
    contact_id:   str,
    contact_name: str,
    new_sentiment:str,
    new_score:    int,
):
    """Recompute the contact's sentiment profile after each new log entry."""
    init_sentiment_tables()
    conn = sqlite3.connect(DB_PATH)

    rows = conn.execute("""
        SELECT sentiment_score FROM reply_sentiment_log
        WHERE contact_id = ? ORDER BY logged_at DESC LIMIT 10
    """, (contact_id,)).fetchall()

    scores = [r[0] for r in rows]
    avg    = round(sum(scores) / len(scores), 2) if scores else new_score

    # Trend: compare last 3 vs previous 3
    if len(scores) >= 6:
        recent_avg = sum(scores[:3]) / 3
        older_avg  = sum(scores[3:6]) / 3
        diff = recent_avg - older_avg
        trend = "improving" if diff > 0.3 else ("declining" if diff < -0.3 else "stable")
    elif len(scores) >= 2:
        diff  = scores[0] - scores[-1]
        trend = "improving" if diff > 0 else ("declining" if diff < 0 else "stable")
    else:
        trend = "stable"

    prev = conn.execute(
        "SELECT current_sentiment FROM contact_sentiment_profile WHERE contact_id=?",
        (contact_id,)
    ).fetchone()
    prev_sentiment = prev[0] if prev else None

    conn.execute("""
        INSERT INTO contact_sentiment_profile
            (contact_id, contact_name, current_sentiment, trend_direction,
             avg_score, last_sentiment, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id) DO UPDATE SET
            current_sentiment = excluded.current_sentiment,
            trend_direction   = excluded.trend_direction,
            avg_score         = excluded.avg_score,
            last_sentiment    = excluded.last_sentiment,
            last_updated      = excluded.last_updated
    """, (
        contact_id, contact_name, new_sentiment, trend,
        avg, prev_sentiment, datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_contact_trend(contact_id: str, limit: int = 12) -> list[dict]:
    """Return the chronological sentiment history for one contact."""
    init_sentiment_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT sentiment, sentiment_score, reply_delay_hrs, wish_date, logged_at, platform
        FROM reply_sentiment_log
        WHERE contact_id = ?
        ORDER BY logged_at ASC LIMIT ?
    """, (contact_id, limit)).fetchall()
    conn.close()
    return [{
        "sentiment":       r[0],
        "score":           r[1],
        "reply_delay_hrs": r[2],
        "wish_date":       r[3],
        "logged_at":       r[4],
        "platform":        r[5],
    } for r in rows]


def get_all_profiles() -> list[dict]:
    """Return all contact sentiment profiles, sorted by declining trend first."""
    init_sentiment_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_id, contact_name, current_sentiment, trend_direction,
               avg_score, last_sentiment, last_updated
        FROM contact_sentiment_profile
        ORDER BY avg_score ASC, last_updated DESC
    """).fetchall()
    conn.close()
    return [{
        "contact_id":        r[0], "contact_name":    r[1],
        "current_sentiment": r[2], "trend_direction": r[3],
        "avg_score":         r[4], "last_sentiment":  r[5],
        "last_updated":      r[6],
    } for r in rows]


def get_aggregate_trend(period_days: int = 30) -> dict:
    """
    Return aggregate sentiment distribution and weekly trend for all contacts.
    Returns:
        { distribution: {sentiment: count}, weekly_avg: [{week, avg_score}] }
    """
    init_sentiment_tables()
    cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
    conn   = sqlite3.connect(DB_PATH)

    dist_rows = conn.execute("""
        SELECT sentiment, COUNT(*) FROM reply_sentiment_log
        WHERE logged_at >= ?
        GROUP BY sentiment
    """, (cutoff,)).fetchall()

    week_rows = conn.execute("""
        SELECT strftime('%Y-W%W', logged_at) as wk, AVG(sentiment_score)
        FROM reply_sentiment_log
        WHERE logged_at >= ?
        GROUP BY wk ORDER BY wk ASC
    """, (cutoff,)).fetchall()

    conn.close()
    distribution = {s: 0 for s in SENTIMENT_LEVELS}
    for r in dist_rows:
        if r[0] in distribution:
            distribution[r[0]] = r[1]

    weekly_avg = [{"week": r[0], "avg_score": round(r[1], 2)} for r in week_rows]
    return {"distribution": distribution, "weekly_avg": weekly_avg}


# ── Demo data seeder ─────────────────────────────────────────────────────────

def seed_demo_sentiment():
    """Seed realistic sentiment history if tables are empty."""
    init_sentiment_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM reply_sentiment_log").fetchone()[0]
    conn.close()
    if count > 0:
        return

    import random as _r
    _r.seed(42)
    demo = [
        {
            "contact_id": "urn_rakib_001", "contact_name": "Rakib Hossain",
            "platform": "LinkedIn",
            "history": [
                ("Thank you so much! Really appreciate it 🙏🎉", 2.5),
                ("Happy birthday to me! Thanks Faahim 😊", 1.2),
                ("Appreciate it! Means a lot bro 🤗🔥", 0.8),
                ("Thanks! Good to hear from you 😊", 3.0),
                ("Thanks!", 6.0),
            ],
        },
        {
            "contact_id": "urn_nadia_002", "contact_name": "Nadia Islam",
            "platform": "WhatsApp",
            "history": [
                ("OMG thank you so much!! 😍🎊🥳 You remembered!!", 0.5),
                ("Aww thank you!! 😊💛 You're so sweet", 1.0),
                ("Haha thanks! 😄", 2.0),
                ("Thanks 😊", 5.0),
                ("ok thanks", 48.0),
            ],
        },
        {
            "contact_id": "urn_tanvir_003", "contact_name": "Tanvir Ahmed",
            "platform": "LinkedIn",
            "history": [
                ("Thank you! Really appreciate the kind words 🙏", 4.0),
                ("Thank you", 12.0),
                ("Thanks.", 36.0),
                (None, None),
            ],
        },
        {
            "contact_id": "urn_mim_004", "contact_name": "Mim Chowdhury",
            "platform": "WhatsApp",
            "history": [
                ("YESSS thank you!! 🎉🥳💃 Best day ever!", 0.3),
                ("Thank you Faahim!! Always appreciate you 😊🙌", 1.0),
                ("Aww happy birthday to me! Thanks 😊", 0.8),
                ("Thanks!! 🎂", 2.0),
                ("Thanks!! You're the best 😍🔥🎊", 0.5),
            ],
        },
        {
            "contact_id": "urn_imran_006", "contact_name": "Imran Hossain",
            "platform": "Slack",
            "history": [
                ("🙌🔥💯 Thanks brother!!", 0.2),
                ("Appreciate it 🚀", 1.5),
                ("Thanks man 🎉", 3.0),
            ],
        },
    ]

    base_date = datetime.now() - timedelta(days=365)
    for c in demo:
        for i, (text, delay) in enumerate(c["history"]):
            wish_date = (base_date + timedelta(days=i * 73)).date().isoformat()
            logged_at = (base_date + timedelta(days=i * 73, hours=(delay or 0) + 1)).isoformat()
            sentiment = classify_sentiment(text, delay)
            score     = SENTIMENT_META[sentiment]["score"]
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                INSERT INTO reply_sentiment_log
                    (contact_id, contact_name, platform, reply_text, sentiment,
                     sentiment_score, reply_delay_hrs, wish_date, logged_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (c["contact_id"], c["contact_name"], c["platform"],
                  text, sentiment, score, delay, wish_date, logged_at))
            conn.commit()
            conn.close()
            _update_sentiment_profile(c["contact_id"], c["contact_name"], sentiment, score)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Sentiment Trend", page_icon="💬",
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
    /* Contact card */
    .c-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
            padding:12px 14px;margin-bottom:6px;cursor:pointer;transition:border-color 0.12s;}
    .c-card:hover{border-color:#58a6ff44;}
    .c-card.selected{border-color:var(--accent);background:#1c1410;}
    .c-name{font-weight:700;font-size:0.86rem;}
    .c-meta{font-size:0.7rem;color:var(--muted);margin-top:2px;}
    /* Trend line dots */
    .trend-dot{display:inline-flex;flex-direction:column;align-items:center;flex:1;}
    .trend-dot-circle{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;
                      justify-content:center;font-size:1.1rem;border:2px solid #30363d;}
    .trend-dot-label{font-size:0.6rem;color:#8b949e;margin-top:4px;}
    .trend-dot-date{font-size:0.55rem;color:#8b949e;}
    /* Connector line */
    .trend-connector{flex:1;height:2px;margin-bottom:12px;}
    /* Callout */
    .callout{background:#0a1a2a;border:1px solid #1f3a5a;border-left:3px solid var(--blue);
             border-radius:8px;padding:10px 14px;margin-bottom:8px;font-size:0.8rem;color:#c9d1d9;}
    .callout.warn{background:#1a1500;border-color:#3a2f00;border-left-color:var(--yellow);}
    .callout.alert{background:#1a0505;border-color:#3a0a0a;border-left-color:var(--red);}
    .callout.win{background:#051a09;border-color:#0a3a14;border-left-color:var(--green);}
    /* Donut-style dist */
    .dist-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
    .dist-bar{flex:1;background:#0d1117;border-radius:4px;height:18px;overflow:hidden;}
    .dist-fill{height:100%;border-radius:4px;}
    .dist-label{width:80px;font-size:0.74rem;}
    .dist-val{width:38px;text-align:right;font-size:0.72rem;font-family:'JetBrains Mono',monospace;color:var(--muted);}
    div[data-testid="stButton"]>button{background:var(--surface);border:1px solid var(--border);
        color:var(--text);border-radius:8px;font-size:0.78rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:var(--blue);background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:6px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    seed_demo_sentiment()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">💬</span>
      <h1>Reply Sentiment Trend</h1>
      <span class="cc-badge">v8.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    profiles = get_all_profiles()
    agg      = get_aggregate_trend(30)

    if "selected_cid" not in st.session_state:
        st.session_state.selected_cid = profiles[0]["contact_id"] if profiles else None

    left, mid, right = st.columns([1, 1.8, 1.2], gap="large")

    # ── LEFT: Contact list ────────────────────────────────────────────────────
    with left:
        st.markdown('<div class="section-title">Contacts</div>', unsafe_allow_html=True)
        trend_filter = st.selectbox("Filter", ["All","Declining","Improving","Stable"],
                                    label_visibility="collapsed")

        for p in profiles:
            if trend_filter != "All" and p["trend_direction"] != trend_filter.lower():
                continue
            meta    = SENTIMENT_META.get(p["current_sentiment"], SENTIMENT_META["neutral"])
            t_arrow = {"improving":"↑ ","declining":"↓ ","stable":"→ "}.get(
                p["trend_direction"],"→ ")
            t_color = {"improving":"#3fb950","declining":"#f85149","stable":"#8b949e"}.get(
                p["trend_direction"],"#8b949e")
            is_sel  = p["contact_id"] == st.session_state.selected_cid
            css     = "c-card selected" if is_sel else "c-card"

            st.markdown(f"""
            <div class="{css}">
              <div class="c-name">{meta['emoji']} {p['contact_name']}</div>
              <div class="c-meta">
                {meta['label']} ·
                <span style="color:{t_color}">{t_arrow}{p['trend_direction']}</span>
              </div>
              <div class="c-meta">Avg score: {p['avg_score']:.1f}/5</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"View", key=f"sel_{p['contact_id']}", use_container_width=True):
                st.session_state.selected_cid = p["contact_id"]
                st.rerun()

        # ── Aggregate distribution ────────────────────────────────────────────
        st.markdown('<div class="section-title" style="margin-top:20px">30-Day Distribution</div>',
                    unsafe_allow_html=True)
        dist  = agg["distribution"]
        total = sum(dist.values()) or 1
        for s in SENTIMENT_LEVELS:
            cnt  = dist.get(s, 0)
            pct  = cnt / total * 100
            meta = SENTIMENT_META[s]
            st.markdown(f"""
            <div class="dist-row">
              <div class="dist-label">{meta['emoji']} {meta['label']}</div>
              <div class="dist-bar">
                <div class="dist-fill" style="width:{pct:.0f}%;background:{meta['color']}"></div>
              </div>
              <div class="dist-val">{cnt}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── MID: Per-contact trend timeline ──────────────────────────────────────
    with mid:
        sel_profile = next((p for p in profiles
                            if p["contact_id"] == st.session_state.selected_cid), None)
        if not sel_profile:
            st.info("Select a contact to view their sentiment trend.")
        else:
            name     = sel_profile["contact_name"]
            cur_meta = SENTIMENT_META.get(sel_profile["current_sentiment"], SENTIMENT_META["neutral"])
            t_dir    = sel_profile["trend_direction"]
            t_color  = {"improving":"#3fb950","declining":"#f85149","stable":"#8b949e"}.get(t_dir,"#8b949e")

            st.markdown(f'<div class="section-title">{name} — Sentiment Timeline</div>',
                        unsafe_allow_html=True)

            # Current status header
            st.markdown(f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;
                        padding:14px 18px;display:flex;align-items:center;gap:14px;margin-bottom:16px;">
              <span style="font-size:2rem">{cur_meta['emoji']}</span>
              <div>
                <div style="font-size:0.95rem;font-weight:700">{cur_meta['label']}</div>
                <div style="font-size:0.75rem;color:{t_color}">Trend: {t_dir}</div>
                <div style="font-size:0.7rem;color:#8b949e">Avg score: {sel_profile['avg_score']:.1f}/5</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            history = get_contact_trend(sel_profile["contact_id"])

            if not history:
                st.info("No reply history yet.")
            else:
                # ── Timeline dots ─────────────────────────────────────────────
                dots_html = '<div style="display:flex;align-items:center;padding:16px 0;">'
                for i, h in enumerate(history):
                    meta  = SENTIMENT_META[h["sentiment"]]
                    dt    = h["logged_at"][:10] if h["logged_at"] else ""
                    dots_html += f"""
                    <div class="trend-dot">
                      <div class="trend-dot-circle" style="background:{meta['color']}22;
                           border-color:{meta['color']}">
                        {meta['emoji']}
                      </div>
                      <div class="trend-dot-label">{meta['label']}</div>
                      <div class="trend-dot-date">{dt}</div>
                    </div>
                    """
                    if i < len(history) - 1:
                        next_s = history[i + 1]["sentiment"]
                        next_score = SENTIMENT_META[next_s]["score"]
                        cur_score  = meta["score"]
                        conn_color = "#3fb950" if next_score >= cur_score else "#f85149"
                        dots_html += f"""
                        <div class="trend-connector" style="background:{conn_color}44;
                             border-top:2px dashed {conn_color}"></div>
                        """
                dots_html += "</div>"
                st.markdown(dots_html, unsafe_allow_html=True)

                # ── Score bar chart ───────────────────────────────────────────
                st.markdown('<div class="section-title">Score Over Time</div>', unsafe_allow_html=True)
                bars_html = '<div style="display:flex;align-items:flex-end;gap:6px;height:100px">'
                for h in history:
                    meta   = SENTIMENT_META[h["sentiment"]]
                    height = int(h["score"] / 5 * 80)
                    dt_lbl = h["logged_at"][2:7] if h["logged_at"] else ""
                    bars_html += f"""
                    <div style="flex:1;display:flex;flex-direction:column;align-items:center">
                      <div style="font-size:0.6rem;color:#8b949e;margin-bottom:2px">{h['score']}</div>
                      <div style="width:100%;height:{height}px;background:{meta['color']};
                                  border-radius:4px 4px 0 0;min-height:4px"></div>
                      <div style="font-size:0.55rem;color:#8b949e;margin-top:3px">{dt_lbl}</div>
                    </div>
                    """
                bars_html += "</div>"
                st.markdown(
                    f'<div style="background:#161b22;border:1px solid #30363d;'
                    f'border-radius:10px;padding:14px">{bars_html}</div>',
                    unsafe_allow_html=True,
                )

                # ── Reply details table ───────────────────────────────────────
                st.markdown('<div class="section-title">Reply History</div>', unsafe_allow_html=True)
                table_html = """
                <table style="width:100%;font-size:0.74rem;border-collapse:collapse">
                  <tr style="color:#8b949e;border-bottom:1px solid #30363d">
                    <th style="text-align:left;padding:4px 8px">Date</th>
                    <th style="text-align:left;padding:4px 8px">Tone</th>
                    <th style="text-align:left;padding:4px 8px">Reply (preview)</th>
                    <th style="text-align:right;padding:4px 8px">Delay</th>
                  </tr>
                """
                for h in reversed(history):
                    meta     = SENTIMENT_META[h["sentiment"]]
                    dt       = h["logged_at"][:10] if h["logged_at"] else "—"
                    preview  = (h.get("reply_text","") or "—")[:40]
                    delay    = f"{h['reply_delay_hrs']:.1f}h" if h.get("reply_delay_hrs") else "—"
                    table_html += f"""
                    <tr style="border-bottom:1px solid #21262d">
                      <td style="padding:5px 8px;color:#8b949e">{dt}</td>
                      <td style="padding:5px 8px">
                        <span style="color:{meta['color']}">{meta['emoji']} {meta['label']}</span>
                      </td>
                      <td style="padding:5px 8px;color:#c9d1d9">{preview}</td>
                      <td style="padding:5px 8px;text-align:right;color:#8b949e;
                                 font-family:'JetBrains Mono',monospace">{delay}</td>
                    </tr>
                    """
                table_html += "</table>"
                st.markdown(
                    f'<div style="background:#161b22;border:1px solid #30363d;'
                    f'border-radius:10px;padding:12px 6px">{table_html}</div>',
                    unsafe_allow_html=True,
                )

    # ── RIGHT: Alerts + Log reply ─────────────────────────────────────────────
    with right:
        st.markdown('<div class="section-title">Attention Needed</div>', unsafe_allow_html=True)

        declining = [p for p in profiles if p["trend_direction"] == "declining"]
        cold_now  = [p for p in profiles if p["current_sentiment"] in ("cold","no_reply")]

        if not declining and not cold_now:
            st.markdown('<div class="callout win">✅ All contacts trending neutral or better.</div>',
                        unsafe_allow_html=True)

        for p in declining[:4]:
            meta = SENTIMENT_META.get(p["current_sentiment"], SENTIMENT_META["neutral"])
            st.markdown(f"""
            <div class="callout alert">
              {meta['emoji']} <strong>{p['contact_name']}</strong> is declining
              — currently {meta['label']} (avg {p['avg_score']:.1f}/5).
              Consider a personalised check-in.
            </div>
            """, unsafe_allow_html=True)

        for p in cold_now:
            if p not in declining:
                meta = SENTIMENT_META.get(p["current_sentiment"], SENTIMENT_META["neutral"])
                st.markdown(f"""
                <div class="callout warn">
                  {meta['emoji']} <strong>{p['contact_name']}</strong>
                  last reply was {meta['label']} — worth following up soon.
                </div>
                """, unsafe_allow_html=True)

        # ── Log a test reply ──────────────────────────────────────────────────
        st.markdown('<div class="section-title" style="margin-top:20px">Log Reply (test)</div>',
                    unsafe_allow_html=True)
        if profiles:
            names = [p["contact_name"] for p in profiles]
            sel_n = st.selectbox("Contact", names, label_visibility="collapsed",
                                 key="log_contact_name")
            sel_p = next(p for p in profiles if p["contact_name"] == sel_n)
            reply_txt   = st.text_area("Reply text", height=70, label_visibility="collapsed",
                                       placeholder="Paste reply text here...", key="log_reply_txt")
            delay_hrs   = st.number_input("Reply delay (hours)", min_value=0.0,
                                          value=2.0, step=0.5, key="log_delay")
            plat_opts   = ["LinkedIn","WhatsApp","Facebook","Instagram","Twitter/X","Slack"]
            log_plat    = st.selectbox("Platform", plat_opts, label_visibility="collapsed",
                                       key="log_plat_sent")
            if st.button("📥 Log Reply", type="primary", use_container_width=True):
                sentiment = log_reply_sentiment(
                    sel_p["contact_id"], sel_p["contact_name"],
                    log_plat, reply_txt or None, delay_hrs,
                )
                meta = SENTIMENT_META[sentiment]
                st.success(f"Logged as {meta['emoji']} **{meta['label']}**")
                st.rerun()

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
      <span>Reply Sentiment Trend</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    # CLI self-test
    init_sentiment_tables()
    seed_demo_sentiment()
    print("=== Reply Sentiment Trend — self test ===\n")

    test_replies = [
        ("OMG thank you so much!! 🎉🥳", 0.5),
        ("Thanks! Appreciate it 😊", 3.0),
        ("Thanks.", 24.0),
        (None, None),
    ]
    print("Classifying test replies:")
    for text, delay in test_replies:
        s = classify_sentiment(text, delay)
        m = SENTIMENT_META[s]
        print(f"  {m['emoji']} {m['label']:10} ← '{text}' (delay: {delay}h)")

    profiles = get_all_profiles()
    print(f"\n{len(profiles)} contact profiles loaded:")
    for p in profiles:
        m = SENTIMENT_META.get(p["current_sentiment"], SENTIMENT_META["neutral"])
        print(f"  {m['emoji']} {p['contact_name']:<20} {m['label']:<10} {p['trend_direction']}")
else:
    render_dashboard()
