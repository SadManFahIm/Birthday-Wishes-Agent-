"""
ROI Forecasting -- Birthday Wishes Agent v10.0
Predicts which contacts are most likely to generate business
in the next 90 days, based on:
  - Past revenue attribution history
  - Relationship tier and health score
  - Recency of last interaction
  - Reply rate and sentiment trend
  - Network centrality (mutual connections)

Output: ranked list of contacts with expected revenue probability
        and recommended action (wish now / reconnect / nurture).

Integrates with: dashboards/revenue_attribution.py,
                 contacts/relationship_tiering.py,
                 dashboards/relationship_graph.py,
                 churn_predictor.py, autonomous_agent.py
"""

import sqlite3
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

FORECAST_HORIZON_DAYS = 90

OPPORTUNITY_TYPES = {
    "direct":      {"label": "Direct Deal",     "icon": "💰", "color": "#3fb950"},
    "referral":    {"label": "Referral",         "icon": "🤝", "color": "#58a6ff"},
    "upsell":      {"label": "Upsell",           "icon": "📈", "color": "#bc8cff"},
    "partnership": {"label": "Partnership",      "icon": "🏢", "color": "#d29922"},
    "unlikely":    {"label": "Unlikely",         "icon": "⏭",  "color": "#8b949e"},
}

ACTION_RECOMMENDATIONS = {
    "wish_now":    {"label": "Wish Now",    "icon": "🎂", "color": "#f78166"},
    "reconnect":   {"label": "Reconnect",   "icon": "👋", "color": "#58a6ff"},
    "nurture":     {"label": "Nurture",     "icon": "🌱", "color": "#3fb950"},
    "maintain":    {"label": "Maintain",    "icon": "✅", "color": "#8b949e"},
    "gift":        {"label": "Send Gift",   "icon": "🎁", "color": "#d29922"},
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_forecast_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roi_forecasts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            forecast_score  REAL NOT NULL,
            expected_value_usd REAL,
            opportunity_type TEXT NOT NULL,
            confidence      REAL NOT NULL,
            action_rec      TEXT NOT NULL,
            reasoning       TEXT,
            horizon_days    INTEGER NOT NULL DEFAULT 90,
            alerted         INTEGER NOT NULL DEFAULT 0,
            forecasted_at   TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone())


def _safe(module: str, attr: str):
    try:
        mod = __import__(module, fromlist=[attr])
        return getattr(mod, attr, None)
    except ImportError:
        return None


# ── Feature extraction ────────────────────────────────────────────────────────

def extract_roi_features(contact_id: str, contact: dict) -> dict:
    """
    Build ROI feature set for one contact.
    All features normalize to 0-1 scale.
    """
    conn = _db()

    # --- Past revenue (direct signal) ---
    past_revenue_usd = 0.0
    deal_count       = 0
    avg_deal_usd     = 0.0
    if _table_exists(conn, "revenue_attributions"):
        row = conn.execute("""
            SELECT SUM(deal_value_usd), COUNT(*)
            FROM revenue_attributions WHERE contact_id=?
        """, (contact_id,)).fetchone()
        if row and row[0]:
            past_revenue_usd = float(row[0])
            deal_count       = row[1] or 0
            avg_deal_usd     = past_revenue_usd / max(deal_count, 1)

    # --- Tier score (0-10) ---
    tier_score = contact.get("tier_score", 5.0)
    if _table_exists(conn, "contact_tier"):
        row = conn.execute("""
            SELECT tier_score, current_tier FROM contact_tier WHERE contact_id=?
        """, (contact_id,)).fetchone()
        if row:
            tier_score = row["tier_score"] or 5.0
            contact["tier"] = row["current_tier"] or contact.get("tier","Acquaintance")

    # --- Reply rate ---
    reply_rate = 0.4
    if _table_exists(conn, "wish_outcome_log"):
        row = conn.execute("""
            SELECT COUNT(*), SUM(replied) FROM wish_outcome_log WHERE contact_id=?
        """, (contact_id,)).fetchone()
        if row and row[0]:
            reply_rate = (row[1] or 0) / row[0]

    # --- Recency (days since last contact, 0=recent) ---
    days_since = 60
    if _table_exists(conn, "wish_outcome_log"):
        row = conn.execute("""
            SELECT sent_at FROM wish_outcome_log
            WHERE contact_id=? ORDER BY sent_at DESC LIMIT 1
        """, (contact_id,)).fetchone()
        if row:
            try:
                days_since = (datetime.now() -
                              datetime.fromisoformat(row["sent_at"])).days
            except ValueError:
                pass

    # --- Sentiment ---
    avg_sentiment = 3.0
    if _table_exists(conn, "wish_outcome_log"):
        row = conn.execute("""
            SELECT AVG(sentiment_score) FROM wish_outcome_log
            WHERE contact_id=? AND sentiment_score IS NOT NULL
        """, (contact_id,)).fetchone()
        if row and row[0]:
            avg_sentiment = float(row[0])

    # --- Network strength ---
    network_strength = 5.0
    if _table_exists(conn, "graph_nodes"):
        row = conn.execute("""
            SELECT strength FROM graph_nodes WHERE contact_id=?
        """, (contact_id,)).fetchone()
        if row:
            network_strength = float(row["strength"] or 5.0)

    # --- Days to birthday ---
    days_to_birthday = 999
    today  = datetime.now()
    if _table_exists(conn, "contact_life_events"):
        row = conn.execute("""
            SELECT event_date FROM contact_life_events
            WHERE contact_id=? AND event_type='birthday'
            ORDER BY event_date ASC LIMIT 1
        """, (contact_id,)).fetchone()
        if row and row["event_date"]:
            try:
                bday_str = row["event_date"]
                bday_md  = bday_str[5:10]
                for yr_off in [0, 1]:
                    candidate = datetime(today.year + yr_off,
                                         int(bday_md[:2]), int(bday_md[3:]))
                    delta = (candidate - today).days
                    if delta >= 0:
                        days_to_birthday = delta
                        break
            except (ValueError, IndexError):
                pass

    conn.close()

    return {
        "past_revenue_usd":  past_revenue_usd,
        "deal_count":        deal_count,
        "avg_deal_usd":      avg_deal_usd,
        "tier_score":        tier_score,
        "reply_rate":        reply_rate,
        "days_since":        days_since,
        "avg_sentiment":     avg_sentiment,
        "network_strength":  network_strength,
        "days_to_birthday":  days_to_birthday,
    }


# ── Scoring model ─────────────────────────────────────────────────────────────

def score_roi_potential(features: dict, contact: dict) -> dict:
    """
    Compute ROI forecast score (0-100) and expected value.
    Weighted rule-based model (no sklearn dependency).

    Returns:
        { score, expected_value_usd, opportunity_type, confidence, reasoning }
    """
    f    = features
    tier = contact.get("tier", "Acquaintance")

    # ── Component scores (each 0-1) ──────────────────────────────────────────

    # 1. Past revenue (strongest signal — repeated behavior)
    past_rev_score = min(1.0, f["past_revenue_usd"] / 2000)   # caps at $2k
    if f["past_revenue_usd"] > 0:
        past_rev_score = min(1.0, past_rev_score + 0.3)        # bonus for any history

    # 2. Tier quality
    tier_scores = {"Close Friend": 1.0, "Colleague": 0.65, "Acquaintance": 0.3}
    tier_score  = tier_scores.get(tier, 0.5)

    # 3. Relationship health (reply rate + sentiment)
    health_score = (f["reply_rate"] * 0.6) + ((f["avg_sentiment"] - 1) / 4 * 0.4)

    # 4. Recency (fades off sharply after 90 days)
    recency_score = max(0.0, 1.0 - f["days_since"] / 180)

    # 5. Network strength
    network_score = min(1.0, f["network_strength"] / 10)

    # 6. Birthday proximity (opportunity window)
    bday_score = 0.0
    if f["days_to_birthday"] <= FORECAST_HORIZON_DAYS:
        bday_score = 1.0 - (f["days_to_birthday"] / FORECAST_HORIZON_DAYS)

    # ── Weighted composite ────────────────────────────────────────────────────
    weights = {
        "past_rev":   0.35,
        "tier":       0.20,
        "health":     0.18,
        "recency":    0.12,
        "network":    0.10,
        "bday":       0.05,
    }
    raw = (
        past_rev_score  * weights["past_rev"]  +
        tier_score      * weights["tier"]       +
        health_score    * weights["health"]     +
        recency_score   * weights["recency"]    +
        network_score   * weights["network"]    +
        bday_score      * weights["bday"]
    )
    score = round(min(100, raw * 100), 1)

    # ── Expected value estimate ───────────────────────────────────────────────
    base_values = {"Close Friend": 800, "Colleague": 350, "Acquaintance": 100}
    base        = base_values.get(tier, 200)
    if f["avg_deal_usd"] > 0:
        base    = f["avg_deal_usd"] * 0.8  # use historical avg
    expected_usd = round(base * (score / 100) * 1.3, 0)

    # ── Opportunity type ──────────────────────────────────────────────────────
    if score < 15:
        opp_type = "unlikely"
    elif f["past_revenue_usd"] > 0 and f["deal_count"] > 1:
        opp_type = "upsell"
    elif f["past_revenue_usd"] > 0:
        opp_type = "direct"
    elif tier == "Close Friend" and health_score > 0.6:
        opp_type = "referral"
    elif tier in ("Close Friend", "Colleague") and score > 40:
        opp_type = "partnership"
    else:
        opp_type = "referral"

    # ── Confidence ────────────────────────────────────────────────────────────
    data_points = sum([
        f["deal_count"] > 0,
        f["reply_rate"] != 0.4,   # not default
        f["avg_sentiment"] != 3.0,
        f["network_strength"] != 5.0,
    ])
    confidence = round(0.4 + (data_points / 4) * 0.5, 2)

    # ── Reasoning ─────────────────────────────────────────────────────────────
    reasons = []
    if f["past_revenue_usd"] > 0:
        reasons.append(f"${f['past_revenue_usd']:,.0f} revenue history")
    if tier == "Close Friend":
        reasons.append("Close Friend tier")
    if f["reply_rate"] > 0.5:
        reasons.append(f"{f['reply_rate']:.0%} reply rate")
    if f["days_to_birthday"] <= FORECAST_HORIZON_DAYS:
        reasons.append(f"Birthday in {f['days_to_birthday']}d")
    if f["days_since"] > 90:
        reasons.append(f"Not contacted in {f['days_since']}d (reconnect)")
    reasoning = "; ".join(reasons) if reasons else "Based on tier and network score"

    return {
        "score":              score,
        "expected_value_usd": expected_usd,
        "opportunity_type":   opp_type,
        "confidence":         confidence,
        "reasoning":          reasoning,
        "components": {
            "past_revenue":   round(past_rev_score * 100, 1),
            "tier":           round(tier_score * 100, 1),
            "health":         round(health_score * 100, 1),
            "recency":        round(recency_score * 100, 1),
            "network":        round(network_score * 100, 1),
            "birthday":       round(bday_score * 100, 1),
        },
    }


# ── Action recommendation ─────────────────────────────────────────────────────

def recommend_action(features: dict, score: float,
                     days_to_birthday: int) -> str:
    """Pick the most impactful action to unlock the ROI opportunity."""
    if days_to_birthday <= 14:
        return "wish_now"
    if features["days_since"] > 90:
        return "reconnect"
    if features["past_revenue_usd"] > 0 and features["days_since"] > 30:
        return "gift"
    if score > 60:
        return "nurture"
    return "maintain"


# ── Forecast runner ───────────────────────────────────────────────────────────

def run_forecast(
    contacts: Optional[list] = None,
    verbose:  bool = True,
) -> list[dict]:
    """
    Forecast ROI potential for all contacts over next 90 days.

    Args:
        contacts: List of contact dicts (loads from DB if None).
        verbose:  Print ranked results.

    Returns:
        List of forecast dicts sorted by score descending.
    """
    init_forecast_tables()
    if contacts is None:
        contacts = _load_contacts()

    if verbose:
        print(f"[ROI Forecast] Scoring {len(contacts)} contacts "
              f"({FORECAST_HORIZON_DAYS}d horizon)\n")

    results = []
    for c in contacts:
        cid      = c.get("contact_id", "unknown")
        features = extract_roi_features(cid, c)
        scored   = score_roi_potential(features, c)
        action   = recommend_action(features, scored["score"],
                                    features["days_to_birthday"])
        opp_meta = OPPORTUNITY_TYPES.get(
            scored["opportunity_type"], OPPORTUNITY_TYPES["unlikely"])
        act_meta = ACTION_RECOMMENDATIONS.get(action, ACTION_RECOMMENDATIONS["maintain"])

        forecast = {
            "contact_id":         cid,
            "contact_name":       c.get("contact_name", "Unknown"),
            "tier":               c.get("tier", "Acquaintance"),
            "score":              scored["score"],
            "expected_value_usd": scored["expected_value_usd"],
            "opportunity_type":   scored["opportunity_type"],
            "opp_icon":           opp_meta["icon"],
            "opp_color":          opp_meta["color"],
            "opp_label":          opp_meta["label"],
            "confidence":         scored["confidence"],
            "action_rec":         action,
            "action_icon":        act_meta["icon"],
            "action_label":       act_meta["label"],
            "action_color":       act_meta["color"],
            "reasoning":          scored["reasoning"],
            "components":         scored["components"],
            "features":           features,
        }
        results.append(forecast)
        _save_forecast(forecast)

    results.sort(key=lambda x: -x["score"])

    if verbose:
        print(f"  {'Rank':<5} {'Contact':<22} {'Score':<8} "
              f"{'Expected ($)':<14} {'Opportunity':<16} {'Action'}")
        print(f"  {'─'*5} {'─'*22} {'─'*8} {'─'*14} {'─'*16} {'─'*14}")
        for i, r in enumerate(results, 1):
            skip = r["opportunity_type"] == "unlikely"
            if skip and i > 6:
                continue
            print(f"  #{i:<4} {r['contact_name']:<22} {r['score']:<8.1f}"
                  f"${r['expected_value_usd']:<13,.0f} "
                  f"{r['opp_icon']} {r['opp_label']:<14} "
                  f"{r['action_icon']} {r['action_label']}")

        total_pipeline = sum(r["expected_value_usd"] for r in results
                             if r["opportunity_type"] != "unlikely")
        print(f"\n  Total pipeline: ${total_pipeline:,.0f} USD "
              f"({FORECAST_HORIZON_DAYS}d forecast)")

    return results


def _save_forecast(forecast: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO roi_forecasts
            (contact_id, contact_name, forecast_score, expected_value_usd,
             opportunity_type, confidence, action_rec, reasoning,
             horizon_days, forecasted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (forecast["contact_id"], forecast["contact_name"],
          forecast["score"], forecast["expected_value_usd"],
          forecast["opportunity_type"], forecast["confidence"],
          forecast["action_rec"], forecast["reasoning"],
          FORECAST_HORIZON_DAYS, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_forecast_summary() -> dict:
    """Aggregate pipeline and top contacts from latest forecast run."""
    init_forecast_tables()
    conn    = _db()
    cutoff  = (datetime.now() - timedelta(hours=24)).isoformat()
    rows    = conn.execute("""
        SELECT contact_id, contact_name, forecast_score, expected_value_usd,
               opportunity_type, confidence, action_rec, reasoning
        FROM roi_forecasts
        WHERE forecasted_at >= ?
        ORDER BY forecast_score DESC LIMIT 20
    """, (cutoff,)).fetchall()
    conn.close()

    forecasts = [dict(r) for r in rows]
    pipeline  = sum(f["expected_value_usd"] for f in forecasts
                    if f["opportunity_type"] != "unlikely")
    top5      = [f for f in forecasts if f["opportunity_type"] != "unlikely"][:5]

    return {
        "total_pipeline_usd": round(pipeline, 0),
        "contacts_scored":    len(forecasts),
        "top_opportunities":  top5,
        "horizon_days":       FORECAST_HORIZON_DAYS,
        "as_of":              datetime.now().isoformat(),
    }


def _load_contacts() -> list[dict]:
    if not DB_PATH.exists():
        return _demo_contacts()
    conn = _db()
    contacts = []
    if _table_exists(conn, "contact_tier"):
        rows = conn.execute("""
            SELECT contact_id, contact_name, current_tier, tier_score
            FROM contact_tier
        """).fetchall()
        for r in rows:
            contacts.append({"contact_id":   r["contact_id"],
                              "contact_name": r["contact_name"],
                              "tier":         r["current_tier"],
                              "tier_score":   r["tier_score"] or 5.0,
                              "platform":     "LinkedIn"})
    conn.close()
    return contacts if contacts else _demo_contacts()


def _demo_contacts() -> list[dict]:
    return [
        {"contact_id":"urn_rakib_001","contact_name":"Rakib Hossain",
         "tier":"Close Friend","tier_score":9.0,"platform":"LinkedIn"},
        {"contact_id":"urn_nadia_002","contact_name":"Nadia Islam",
         "tier":"Colleague","tier_score":7.0,"platform":"WhatsApp"},
        {"contact_id":"urn_tanvir_003","contact_name":"Tanvir Ahmed",
         "tier":"Colleague","tier_score":5.0,"platform":"LinkedIn"},
        {"contact_id":"urn_mim_004","contact_name":"Mim Chowdhury",
         "tier":"Close Friend","tier_score":9.5,"platform":"WhatsApp"},
        {"contact_id":"urn_sara_005","contact_name":"Sara Khan",
         "tier":"Acquaintance","tier_score":3.0,"platform":"LinkedIn"},
        {"contact_id":"urn_imran_006","contact_name":"Imran Hossain",
         "tier":"Colleague","tier_score":6.5,"platform":"Slack"},
    ]


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="ROI Forecast", page_icon="📈",
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
    .f-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
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

    init_forecast_tables()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📈</span>
      <h1>ROI Forecasting</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">90-day pipeline</span>
    </div>
    """, unsafe_allow_html=True)

    results   = st.session_state.get("roi_results", [])
    pipeline  = sum(r["expected_value_usd"] for r in results
                    if r.get("opportunity_type") != "unlikely")
    top_opps  = [r for r in results if r.get("opportunity_type") != "unlikely"]

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Pipeline (USD)", f"${pipeline:,.0f}", "#3fb950"),
        (m2, "Opportunities",  len(top_opps),       "#58a6ff"),
        (m3, "Contacts Scored",len(results),         "#f78166"),
        (m4, "Horizon",        "90 days",            "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("📈 Run Forecast", type="primary"):
        with st.spinner("Forecasting..."):
            results = run_forecast(verbose=False)
        st.session_state["roi_results"] = results
        st.rerun()

    left, right = st.columns([1.5, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Ranked Opportunities</div>',
                    unsafe_allow_html=True)
        for r in results[:12]:
            skip    = r["opportunity_type"] == "unlikely"
            opacity = "opacity:0.4;" if skip else ""
            score   = r["score"]
            pct     = int(score)
            oc      = r["opp_color"]
            st.markdown(f"""
            <div class="f-card" style="{opacity}border-left:3px solid {oc}">
              <div style="display:flex;align-items:center;
                          justify-content:space-between;margin-bottom:6px">
                <div>
                  <span style="font-weight:700">{r['contact_name']}</span>
                  <span style="font-size:0.68rem;color:#8b949e;margin-left:8px">
                    {r['tier']}
                  </span>
                </div>
                <div style="text-align:right">
                  <div style="font-weight:700;font-family:'JetBrains Mono',monospace;
                              color:{oc}">{score:.0f}/100</div>
                  <div style="font-size:0.68rem;color:#3fb950">
                    ${r['expected_value_usd']:,.0f}
                  </div>
                </div>
              </div>
              <div style="background:#0d1117;border-radius:3px;height:5px;
                          overflow:hidden;margin-bottom:8px">
                <div style="width:{pct}%;height:100%;background:{oc};
                            border-radius:3px"></div>
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap">
                <span style="font-size:0.62rem;padding:2px 7px;border-radius:12px;
                             background:{oc}22;color:{oc};border:1px solid {oc}44">
                  {r['opp_icon']} {r['opp_label']}
                </span>
                <span style="font-size:0.62rem;padding:2px 7px;border-radius:12px;
                             background:{r['action_color']}22;
                             color:{r['action_color']};
                             border:1px solid {r['action_color']}44">
                  {r['action_icon']} {r['action_label']}
                </span>
                <span style="font-size:0.62rem;color:#8b949e">
                  {int(r['confidence']*100)}% conf
                </span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:6px">
                {r['reasoning'][:80]}
              </div>
            </div>
            """, unsafe_allow_html=True)

    with right:
        if results:
            st.markdown('<div class="section-title">Score Components</div>',
                        unsafe_allow_html=True)
            top = next((r for r in results
                        if r.get("opportunity_type") != "unlikely"), None)
            if top:
                st.markdown(f"**{top['contact_name']}** — top opportunity",
                            help="Breakdown of forecast score components")
                comps = top.get("components", {})
                COMP_COLORS = {
                    "past_revenue":"#3fb950","tier":"#58a6ff",
                    "health":"#bc8cff","recency":"#d29922",
                    "network":"#4fc3f7","birthday":"#f78166",
                }
                for cname, val in comps.items():
                    color = COMP_COLORS.get(cname, "#8b949e")
                    st.markdown(f"""
                    <div style="display:flex;align-items:center;
                                gap:8px;margin-bottom:6px">
                      <div style="width:100px;font-size:0.70rem;color:#c9d1d9">
                        {cname}
                      </div>
                      <div style="flex:1;background:#0d1117;border-radius:3px;
                                  height:16px;overflow:hidden">
                        <div style="width:{int(val)}%;height:100%;
                                    background:{color};border-radius:3px"></div>
                      </div>
                      <div style="width:32px;font-size:0.68rem;color:#8b949e;
                                  text-align:right">{val:.0f}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Opportunity type breakdown
            st.markdown('<div class="section-title">By Opportunity Type</div>',
                        unsafe_allow_html=True)
            type_counts: dict = {}
            type_values: dict = {}
            for r in results:
                t = r["opportunity_type"]
                type_counts[t] = type_counts.get(t, 0) + 1
                type_values[t] = type_values.get(t, 0) + r["expected_value_usd"]
            max_val = max(type_values.values(), default=1)
            for t, cnt in sorted(type_counts.items(),
                                  key=lambda x: -type_values.get(x[0], 0)):
                meta  = OPPORTUNITY_TYPES.get(t, OPPORTUNITY_TYPES["unlikely"])
                val   = type_values.get(t, 0)
                pct   = int(val / max_val * 100) if max_val else 0
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                  <div style="width:90px;font-size:0.72rem">
                    {meta['icon']} {t}
                  </div>
                  <div style="flex:1;background:#0d1117;border-radius:3px;height:18px">
                    <div style="width:{pct}%;height:100%;background:{meta['color']};
                                border-radius:3px"></div>
                  </div>
                  <div style="width:60px;font-size:0.68rem;color:#8b949e;
                              text-align:right">${val:,.0f}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>ROI Forecasting</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_forecast_tables()
    print("=== ROI Forecasting -- self test ===\n")
    results = run_forecast(verbose=True)
    summary = get_forecast_summary()
    print(f"\nSummary: ${summary['total_pipeline_usd']:,.0f} pipeline "
          f"| {summary['contacts_scored']} contacts scored")
else:
    render_dashboard()
