"""
Network Health Score -- Birthday Wishes Agent v9.0
Computes a single 0-100 health score for your entire contact network
by combining activity, reply rates, sentiment trends, tier distribution,
and fading relationship ratios.

Score components (weighted):
  Activity ratio      (25) -- % of contacts interacted with in last 90d
  Reply rate          (25) -- overall wish reply rate
  Sentiment avg       (20) -- average reply sentiment across contacts
  Tier quality        (15) -- ratio of Close Friends to Acquaintances
  Fading penalty      (15) -- penalty for fading/dormant contacts

Grade:
  90-100  A+  Thriving
  75-89   A   Healthy
  60-74   B   Good
  45-59   C   Needs attention
  0-44    D   At risk

Integrates with: contacts/reply_sentiment_trend.py,
                 contacts/relationship_tiering.py,
                 dashboards/relationship_graph.py, agent.py
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

GRADE_MAP = [
    (90, "A+", "Thriving",        "#3fb950"),
    (75, "A",  "Healthy",         "#58a6ff"),
    (60, "B",  "Good",            "#4fc3f7"),
    (45, "C",  "Needs Attention", "#d29922"),
    (0,  "D",  "At Risk",         "#f85149"),
]

WEIGHTS = {
    "activity_ratio": 25,
    "reply_rate":     25,
    "sentiment_avg":  20,
    "tier_quality":   15,
    "fading_penalty": 15,
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_health_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS network_health_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            score           REAL NOT NULL,
            grade           TEXT NOT NULL,
            grade_label     TEXT NOT NULL,
            components_json TEXT NOT NULL,
            total_contacts  INTEGER NOT NULL,
            active_contacts INTEGER NOT NULL,
            fading_contacts INTEGER NOT NULL,
            snapped_at      TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Component calculators ─────────────────────────────────────────────────────

def _calc_activity_ratio(conn, days: int = 90) -> dict:
    """% of contacts with at least one interaction in last N days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    total = conn.execute(
        "SELECT COUNT(DISTINCT contact_id) FROM graph_nodes"
    ).fetchone()[0] if _table_exists(conn, "graph_nodes") else 0

    if total == 0:
        # Fallback: use wish_outcome_log
        total = conn.execute("""
            SELECT COUNT(DISTINCT contact_id) FROM wish_outcome_log
        """).fetchone()[0] if _table_exists(conn, "wish_outcome_log") else 0
        active = conn.execute("""
            SELECT COUNT(DISTINCT contact_id) FROM wish_outcome_log
            WHERE sent_at >= ?
        """, (cutoff,)).fetchone()[0] if total else 0
    else:
        active = conn.execute("""
            SELECT COUNT(*) FROM graph_nodes WHERE last_interaction >= ?
        """, (cutoff,)).fetchone()[0]

    ratio = active / total if total else 0
    return {
        "raw":    round(ratio, 3),
        "score":  round(ratio * WEIGHTS["activity_ratio"], 1),
        "total":  total,
        "active": active,
    }


def _calc_reply_rate(conn) -> dict:
    """Overall wish reply rate from wish_outcome_log."""
    if not _table_exists(conn, "wish_outcome_log"):
        return {"raw": 0.5, "score": round(0.5 * WEIGHTS["reply_rate"], 1),
                "total": 0, "replied": 0}

    row = conn.execute("""
        SELECT COUNT(*), SUM(replied) FROM wish_outcome_log
    """).fetchone()
    total   = row[0] or 0
    replied = row[1] or 0
    rate    = replied / total if total else 0.5  # default 50% if no data
    return {
        "raw":     round(rate, 3),
        "score":   round(rate * WEIGHTS["reply_rate"], 1),
        "total":   total,
        "replied": replied,
    }


def _calc_sentiment_avg(conn) -> dict:
    """Average sentiment score (1-5) from reply_sentiment_log."""
    if not _table_exists(conn, "reply_sentiment_log"):
        return {"raw": 3.0, "score": round(0.5 * WEIGHTS["sentiment_avg"], 1),
                "sample": 0}

    row = conn.execute("""
        SELECT AVG(sentiment_score), COUNT(*) FROM reply_sentiment_log
    """).fetchone()
    avg    = row[0] or 3.0
    sample = row[1] or 0
    # Normalize 1-5 to 0-1
    norm   = (avg - 1) / 4
    return {
        "raw":    round(avg, 2),
        "score":  round(norm * WEIGHTS["sentiment_avg"], 1),
        "sample": sample,
    }


def _calc_tier_quality(conn) -> dict:
    """Ratio: (Close Friends * 3 + Colleagues * 1.5) / total contacts."""
    if not _table_exists(conn, "contact_tier"):
        return {"raw": 0.5, "score": round(0.5 * WEIGHTS["tier_quality"], 1),
                "breakdown": {}}

    rows = conn.execute("""
        SELECT current_tier, COUNT(*) FROM contact_tier GROUP BY current_tier
    """).fetchall()
    counts   = {r[0]: r[1] for r in rows}
    total    = sum(counts.values()) or 1
    cf_count = counts.get("Close Friend", 0)
    co_count = counts.get("Colleague", 0)
    ac_count = counts.get("Acquaintance", 0)
    weighted = (cf_count * 3 + co_count * 1.5 + ac_count * 0.5)
    max_w    = total * 3
    ratio    = weighted / max_w if max_w else 0.5
    return {
        "raw":   round(ratio, 3),
        "score": round(ratio * WEIGHTS["tier_quality"], 1),
        "breakdown": {
            "Close Friend": cf_count,
            "Colleague":    co_count,
            "Acquaintance": ac_count,
        },
    }


def _calc_fading_penalty(conn) -> dict:
    """Penalty for high % of fading/dormant contacts."""
    if not _table_exists(conn, "graph_nodes"):
        return {"raw": 0.0, "score": WEIGHTS["fading_penalty"],
                "fading": 0, "total": 0}

    total  = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0] or 1
    fading = conn.execute("""
        SELECT COUNT(*) FROM graph_nodes
        WHERE node_state IN ('fading','dormant')
    """).fetchone()[0]
    fading_ratio = fading / total
    # Penalty: 0 fading = full score; 100% fading = 0 score
    score = round((1 - fading_ratio) * WEIGHTS["fading_penalty"], 1)
    return {
        "raw":    round(fading_ratio, 3),
        "score":  score,
        "fading": fading,
        "total":  total,
    }


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone())


# ── Main scorer ───────────────────────────────────────────────────────────────

def compute_health_score(
    activity_days: int = 90,
    save_snapshot: bool = True,
    verbose:       bool = True,
) -> dict:
    """
    Compute the overall network health score.

    Args:
        activity_days: Lookback window for activity ratio.
        save_snapshot: Persist result to history table.
        verbose:       Print summary to console.

    Returns:
        {
          score, grade, grade_label, color,
          components: { activity_ratio, reply_rate, sentiment_avg,
                        tier_quality, fading_penalty },
          total_contacts, active_contacts, fading_contacts,
          recommendations: [str]
        }
    """
    init_health_tables()
    conn = sqlite3.connect(DB_PATH)

    activity  = _calc_activity_ratio(conn, activity_days)
    reply     = _calc_reply_rate(conn)
    sentiment = _calc_sentiment_avg(conn)
    tier      = _calc_tier_quality(conn)
    fading    = _calc_fading_penalty(conn)
    conn.close()

    total_score = round(
        activity["score"] + reply["score"] + sentiment["score"] +
        tier["score"] + fading["score"], 1)
    total_score = max(0, min(100, total_score))

    # Grade
    grade, grade_label, color = "D", "At Risk", "#f85149"
    for threshold, g, gl, c in GRADE_MAP:
        if total_score >= threshold:
            grade, grade_label, color = g, gl, c
            break

    # Recommendations
    recs = []
    if activity["raw"] < 0.5:
        recs.append(f"Only {activity['active']}/{activity['total']} contacts "
                    f"interacted with in {activity_days}d — run a birthday catch-up.")
    if reply["raw"] < 0.35:
        recs.append("Reply rate below 35% — consider improving wish personalization "
                    "or switching to a higher-scoring style.")
    if sentiment["raw"] < 3.0:
        recs.append("Average reply sentiment is below neutral — review recent wish "
                    "tone and follow-up warmth.")
    if tier["breakdown"].get("Close Friend", 0) < 3:
        recs.append("Fewer than 3 Close Friends — nurture your highest-value "
                    "relationships more regularly.")
    if fading["raw"] > 0.3:
        recs.append(f"{fading['fading']} contacts are fading/dormant — "
                    f"run decay alert and schedule check-ins.")
    if not recs:
        recs.append("Network is in great shape — keep the current cadence.")

    components = {
        "activity_ratio": activity,
        "reply_rate":     reply,
        "sentiment_avg":  sentiment,
        "tier_quality":   tier,
        "fading_penalty": fading,
    }

    result = {
        "score":           total_score,
        "grade":           grade,
        "grade_label":     grade_label,
        "color":           color,
        "components":      components,
        "total_contacts":  activity["total"],
        "active_contacts": activity["active"],
        "fading_contacts": fading["fading"],
        "recommendations": recs,
    }

    if save_snapshot:
        _save_snapshot(result)

    if verbose:
        print(f"[NetworkHealth] Score: {total_score}/100 "
              f"({grade} — {grade_label})")
        for k, v in components.items():
            print(f"  {k:<20} {v['score']:5.1f} / {WEIGHTS[k]}")

    return result


def _save_snapshot(result: dict):
    init_health_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO network_health_snapshots
            (score, grade, grade_label, components_json,
             total_contacts, active_contacts, fading_contacts, snapped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (result["score"], result["grade"], result["grade_label"],
          json.dumps({k: v["score"] for k, v in result["components"].items()}),
          result["total_contacts"], result["active_contacts"],
          result["fading_contacts"], datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_score_history(limit: int = 12) -> list[dict]:
    """Return recent health score snapshots for trend chart."""
    init_health_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT score, grade, grade_label, active_contacts,
               fading_contacts, snapped_at
        FROM network_health_snapshots
        ORDER BY snapped_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"score": r[0], "grade": r[1], "grade_label": r[2],
             "active": r[3], "fading": r[4],
             "snapped_at": r[5]} for r in reversed(rows)]


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    """Seed historical snapshots if none exist."""
    init_health_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM network_health_snapshots").fetchone()[0]
    conn.close()
    if count > 0:
        return

    import random as _r
    _r.seed(42)
    now  = datetime.now()
    base = 52.0
    for mo in range(5, -1, -1):
        base += _r.uniform(-3, 8)
        base  = max(40, min(95, base))
        snapped = (now - timedelta(days=mo*30)).isoformat()
        grade, grade_label, color = "D", "At Risk", "#f85149"
        for threshold, g, gl, c in GRADE_MAP:
            if base >= threshold:
                grade, grade_label, color = g, gl, c
                break
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO network_health_snapshots
                (score, grade, grade_label, components_json,
                 total_contacts, active_contacts, fading_contacts, snapped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (round(base, 1), grade, grade_label,
              json.dumps({"activity_ratio": round(base*0.25, 1),
                          "reply_rate": round(base*0.25, 1)}),
              10, _r.randint(4, 9), _r.randint(1, 4), snapped))
        conn.commit()
        conn.close()


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Network Health", page_icon="💪",
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
    .score-hero{text-align:center;padding:28px 0 18px;
                background:var(--surface);border:1px solid var(--border);
                border-radius:16px;margin-bottom:20px;}
    .score-big{font-size:4rem;font-weight:700;line-height:1;font-family:'JetBrains Mono',monospace;}
    .score-grade{font-size:1.1rem;font-weight:700;margin-top:6px;}
    .comp-row{display:flex;align-items:center;gap:10px;margin-bottom:10px;}
    .comp-label{width:140px;font-size:0.74rem;flex-shrink:0;}
    .comp-track{flex:1;background:#0d1117;border-radius:5px;height:20px;overflow:hidden;}
    .comp-fill{height:100%;border-radius:5px;display:flex;align-items:center;
               padding-right:6px;justify-content:flex-end;font-size:0.65rem;
               font-weight:700;color:#0d1117;}
    .comp-max{width:32px;text-align:right;font-size:0.68rem;color:#8b949e;}
    .rec-card{background:var(--surface);border:1px solid var(--border);
              border-left:3px solid var(--accent);border-radius:8px;
              padding:10px 14px;margin-bottom:8px;font-size:0.80rem;color:#c9d1d9;}
    .rec-card.ok{border-left-color:var(--green);background:#051a09;}
    .hist-bar{display:flex;flex-direction:column;align-items:center;flex:1;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
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

    init_health_tables()
    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">💪</span>
      <h1>Network Health Score</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    cc1, cc2 = st.columns([1, 3])
    with cc1:
        days = st.selectbox("Activity window",
                            ["30 days","60 days","90 days","180 days"],
                            index=2, label_visibility="collapsed")
        days_map = {"30 days":30,"60 days":60,"90 days":90,"180 days":180}
    with cc2:
        if st.button("⚡ Recompute Now", type="primary",
                     use_container_width=False):
            st.rerun()

    result = compute_health_score(
        activity_days=days_map[days], save_snapshot=False, verbose=False)

    left, right = st.columns([1, 1.5], gap="large")

    with left:
        # Hero score
        st.markdown(f"""
        <div class="score-hero">
          <div class="score-big" style="color:{result['color']}">
            {result['score']}
          </div>
          <div style="font-size:0.7rem;color:#8b949e;margin-top:2px">out of 100</div>
          <div class="score-grade" style="color:{result['color']}">
            {result['grade']} — {result['grade_label']}
          </div>
          <div style="font-size:0.72rem;color:#8b949e;margin-top:8px">
            {result['active_contacts']}/{result['total_contacts']} active ·
            {result['fading_contacts']} fading
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Mini stats
        m1, m2, m3 = st.columns(3)
        comps = result["components"]
        rr    = comps["reply_rate"]["raw"]
        sa    = comps["sentiment_avg"]["raw"]
        ac    = comps["activity_ratio"]["raw"]
        for col, lbl, val, color in [
            (m1, "Reply Rate",  f"{rr:.0%}",  "#3fb950" if rr>=0.35 else "#f85149"),
            (m2, "Sentiment",   f"{sa:.1f}/5", "#3fb950" if sa>=3.5 else "#d29922"),
            (m3, "Active %",    f"{ac:.0%}",   "#3fb950" if ac>=0.5 else "#d29922"),
        ]:
            with col:
                st.markdown(
                    f'<div class="mini"><div class="mini-val" style="color:{color}">'
                    f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                    unsafe_allow_html=True)

        # Recommendations
        st.markdown('<div class="section-title" style="margin-top:18px">'
                    'Recommendations</div>', unsafe_allow_html=True)
        for rec in result["recommendations"]:
            is_ok = "keep the current" in rec
            st.markdown(f'<div class="rec-card {"ok" if is_ok else ""}">'
                        f'{"✅" if is_ok else "⚠️"} {rec}</div>',
                        unsafe_allow_html=True)

    with right:
        # Component breakdown
        st.markdown('<div class="section-title">Score Breakdown</div>',
                    unsafe_allow_html=True)

        comp_meta = {
            "activity_ratio": ("Activity Ratio",  "#58a6ff"),
            "reply_rate":     ("Reply Rate",       "#3fb950"),
            "sentiment_avg":  ("Sentiment Avg",    "#bc8cff"),
            "tier_quality":   ("Tier Quality",     "#d29922"),
            "fading_penalty": ("Fading Penalty",   "#f78166"),
        }
        for key, (label, color) in comp_meta.items():
            comp  = comps[key]
            max_w = WEIGHTS[key]
            pct   = int(comp["score"] / max_w * 100) if max_w else 0
            st.markdown(f"""
            <div class="comp-row">
              <div class="comp-label">{label}</div>
              <div class="comp-track">
                <div class="comp-fill" style="width:{pct}%;background:{color}">
                  {comp['score']}
                </div>
              </div>
              <div class="comp-max">/{max_w}</div>
            </div>
            """, unsafe_allow_html=True)

        # Grade scale
        st.markdown('<div class="section-title">Grade Scale</div>',
                    unsafe_allow_html=True)
        for threshold, grade, label, color in GRADE_MAP:
            active = result["score"] >= threshold
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;
                        padding:6px 0;border-bottom:1px solid #21262d">
              <div style="width:28px;font-weight:700;
                          color:{color if active else '#30363d'}">{grade}</div>
              <div style="flex:1;font-size:0.78rem;
                          color:{'#e6edf3' if active else '#8b949e'}">{label}</div>
              <div style="font-size:0.68rem;color:#8b949e">{threshold}+</div>
              {'<span style="color:'+color+';font-size:0.7rem">← you</span>'
               if result['grade']==grade else ''}
            </div>
            """, unsafe_allow_html=True)

        # History trend
        st.markdown('<div class="section-title">Score History</div>',
                    unsafe_allow_html=True)
        history = get_score_history(8)
        if history:
            bars = ""
            for h in history:
                h_px  = int(h["score"] / 100 * 90)
                color = next((c for t,g,l,c in GRADE_MAP if h["score"]>=t), "#f85149")
                lbl   = (h["snapped_at"] or "")[:7]
                bars += f"""
                <div class="hist-bar">
                  <div style="font-size:0.58rem;color:#8b949e;margin-bottom:2px">
                    {h['score']:.0f}
                  </div>
                  <div style="width:70%;height:{h_px}px;background:{color};
                              border-radius:3px 3px 0 0;min-height:3px"></div>
                  <div style="font-size:0.55rem;color:#8b949e;margin-top:3px">
                    {lbl}
                  </div>
                </div>"""
            st.markdown(
                f'<div style="background:#161b22;border:1px solid #30363d;'
                f'border-radius:10px;padding:14px;display:flex;'
                f'align-items:flex-end;height:140px">{bars}</div>',
                unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>Network Health Score</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_health_tables()
    _seed_demo()
    print("=== Network Health Score -- self test ===\n")
    result = compute_health_score(activity_days=90, save_snapshot=True, verbose=True)
    print(f"\nGrade : {result['grade']} — {result['grade_label']}")
    print(f"Color : {result['color']}")
    print(f"\nRecommendations:")
    for r in result["recommendations"]:
        print(f"  • {r}")
    history = get_score_history(6)
    print(f"\nHistory ({len(history)} snapshots):")
    for h in history:
        print(f"  {h['snapped_at'][:10]}  {h['score']:5.1f}  {h['grade']}")
else:
    render_dashboard()
