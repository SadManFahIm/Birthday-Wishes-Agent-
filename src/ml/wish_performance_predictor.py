"""
Wish Performance Predictor -- Birthday Wishes Agent v10.0
Predicts reply probability (0-100%) BEFORE sending a wish,
so the LangGraph review node can flag low-probability wishes
for editing or style change.

Scoring components (weighted, rule-based):
  contact_reply_rate   (25) -- historical reply ratio for this contact
  platform_fit         (20) -- platform's overall reply rate
  timing_score         (15) -- is now the contact's best engagement slot?
  tier_score           (15) -- Close Friend > Colleague > Acquaintance
  interest_match       (10) -- does wish text reference known interests?
  churn_risk_inv       (10) -- inverse of churn probability
  vip_bonus            (5)  -- VIP contacts reply more

Risk labels:
  high    (>=70%)  -- likely to get a reply
  medium  (40-70%) -- might reply, consider tweaking
  low     (<40%)   -- low chance, flag for review/restyle

Integrates with: engagement_calendar.py, interest_graph.py,
                 churn_predictor.py, langgraph_workflow.py (review node)
"""

import sqlite3
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path("agent_history.db")

WEIGHTS = {
    "contact_reply_rate": 25,
    "platform_fit":       20,
    "timing_score":       15,
    "tier_score":         15,
    "interest_match":     10,
    "churn_risk_inv":     10,
    "vip_bonus":          5,
}

CONFIDENCE_LABELS = {
    "high":   {"label": "Likely Reply",  "icon": "🟢", "color": "#3fb950"},
    "medium": {"label": "Uncertain",     "icon": "🟡", "color": "#d29922"},
    "low":    {"label": "Low Chance",    "icon": "🔴", "color": "#f85149"},
}

PLATFORM_BASE_RATES = {
    "WhatsApp":  0.55,
    "Telegram":  0.45,
    "LinkedIn":  0.35,
    "Discord":   0.40,
    "Facebook":  0.30,
    "Slack":     0.50,
    "Email":     0.20,
}

TIER_SCORES = {
    "Close Friend": 1.0,
    "Colleague":    0.65,
    "Acquaintance": 0.35,
}

STYLE_MODIFIERS = {
    "warm":         1.05,
    "funny":        1.10,
    "professional": 0.95,
    "formal":       0.90,
    "poetic":       1.00,
    "brief":        0.85,
    "festive":      1.08,
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_predictor_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wish_predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            probability     REAL NOT NULL,
            confidence_label TEXT NOT NULL,
            platform        TEXT NOT NULL,
            style           TEXT,
            components_json TEXT,
            risk_factors    TEXT,
            recommendations TEXT,
            actual_replied  INTEGER,
            predicted_at    TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table):
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone())


def _safe(module, attr):
    try:
        mod = __import__(module, fromlist=[attr])
        return getattr(mod, attr, None)
    except ImportError:
        return None


# ── Component scorers (each returns 0.0 - 1.0) ───────────────────────────────

def _score_contact_reply_rate(contact_id: str) -> tuple:
    """Historical reply rate for this specific contact."""
    conn = _db()
    if not _table_exists(conn, "wish_outcome_log"):
        conn.close()
        return 0.5, "No wish history (default 50%)"
    row = conn.execute("""
        SELECT COUNT(*) as total, SUM(replied) as replies
        FROM wish_outcome_log WHERE contact_id=?
    """, (contact_id,)).fetchone()
    conn.close()
    total   = row["total"] or 0
    replies = row["replies"] or 0
    if total == 0:
        return 0.5, "No prior wishes sent (default 50%)"
    rate = replies / total
    note = f"{replies}/{total} past wishes got replies ({rate:.0%})"
    return rate, note


def _score_platform_fit(platform: str) -> tuple:
    """Platform's baseline reply rate from historical data or defaults."""
    conn = _db()
    if _table_exists(conn, "wish_outcome_log"):
        row = conn.execute("""
            SELECT COUNT(*) as total, SUM(replied) as replies
            FROM wish_outcome_log WHERE platform=?
        """, (platform,)).fetchone()
        if row and row["total"] and row["total"] >= 3:
            rate = (row["replies"] or 0) / row["total"]
            conn.close()
            return rate, f"{platform} historical rate: {rate:.0%}"
    conn.close()
    base = PLATFORM_BASE_RATES.get(platform, 0.30)
    return base, f"{platform} baseline rate: {base:.0%}"


def _score_timing(contact_id: str, platform: str) -> tuple:
    """Is the current time a good engagement slot for this contact?"""
    compute_fn = _safe("engagement_calendar", "compute_heatmap")
    if not compute_fn:
        return 0.5, "Timing data unavailable (default)"

    try:
        hm   = compute_fn(contact_id, platform, days_back=180)
        now  = datetime.now()
        dow  = now.weekday()
        hour = now.hour

        # Current slot reply rate
        matrix = hm.get("matrix", [[0]*24]*7)
        current_rate = matrix[dow][hour] if dow < len(matrix) else 0

        # Compare to best slot
        best_rate = max(max(row) for row in matrix) if matrix else 0.01
        ratio     = current_rate / best_rate if best_rate > 0 else 0.5

        if ratio > 0.8:
            note = f"Excellent timing (current slot is near best)"
        elif ratio > 0.5:
            note = f"Good timing (current slot is above average)"
        elif ratio > 0.2:
            note = f"Average timing (not the best slot)"
        else:
            note = f"Poor timing (consider waiting for {hm.get('best_slot','best slot')})"

        return min(1.0, ratio), note
    except Exception:
        return 0.5, "Timing calculation failed (default)"


def _score_tier(contact: dict) -> tuple:
    """Score based on relationship tier."""
    tier  = contact.get("tier", "Acquaintance")
    score = TIER_SCORES.get(tier, 0.5)
    return score, f"{tier} tier (score {score:.0%})"


def _score_interest_match(contact_id: str, wish_text: str) -> tuple:
    """Does the wish text reference the contact's known interests?"""
    get_top = _safe("interest_graph", "get_top_interests")
    if not get_top:
        return 0.3, "Interest graph unavailable"

    try:
        interests = get_top(contact_id, limit=10)
        if not interests:
            return 0.3, "No interests tracked for contact"

        text_lower = wish_text.lower()
        matches    = [i for i in interests if i.lower() in text_lower]
        ratio      = len(matches) / max(len(interests), 1)
        score      = min(1.0, 0.3 + ratio * 0.7)

        if matches:
            return score, f"Wish references: {', '.join(matches[:3])}"
        return 0.2, "Wish doesn't reference known interests"
    except Exception:
        return 0.3, "Interest matching failed"


def _score_churn_risk(contact_id: str) -> tuple:
    """Inverse of churn probability (high churn = low reply chance)."""
    predict_fn = _safe("churn_predictor", "predict_churn")
    if not predict_fn:
        return 0.5, "Churn model unavailable (default)"

    try:
        pred       = predict_fn(contact_id, {})
        churn_prob = pred.get("churn_prob", 0.5)
        inv_score  = 1.0 - churn_prob
        label      = pred.get("churn_label", "unknown")
        return inv_score, f"Churn risk: {label} ({churn_prob:.0%})"
    except Exception:
        return 0.5, "Churn prediction failed (default)"


def _score_vip(contact_id: str) -> tuple:
    """VIP contacts tend to reply more (they've been flagged for a reason)."""
    conn = _db()
    if not _table_exists(conn, "vip_contacts"):
        conn.close()
        return 0.0, "Not VIP"
    row = conn.execute("""
        SELECT active FROM vip_contacts WHERE contact_id=? AND active=1
    """, (contact_id,)).fetchone()
    conn.close()
    if row:
        return 1.0, "VIP contact — higher engagement expected"
    return 0.0, "Not a VIP contact"


# ── Main predictor ────────────────────────────────────────────────────────────

def get_reply_prediction(
    contact_id:   str,
    contact_name: str = "Unknown",
    wish_text:    str = "",
    platform:     str = "LinkedIn",
    style:        str = "warm",
    contact:      Optional[dict] = None,
    save:         bool = True,
) -> dict:
    """
    Predict reply probability for a wish before sending.

    Args:
        contact_id:   Unique contact identifier.
        contact_name: Full name (for logging).
        wish_text:    The wish message text.
        platform:     Target platform.
        style:        Wish style (warm/formal/funny/etc.)
        contact:      Optional contact dict with tier info.
        save:         Persist prediction to DB.

    Returns:
        {
          probability (0-100), confidence_label, icon, color,
          components: { name: { score, weighted, note } },
          risk_factors: [str], recommendations: [str],
          style_modifier: float
        }
    """
    init_predictor_tables()
    if contact is None:
        contact = {"tier": "Colleague"}

    # Score each component
    components = {}

    rate, note = _score_contact_reply_rate(contact_id)
    components["contact_reply_rate"] = {"raw": rate, "note": note}

    rate, note = _score_platform_fit(platform)
    components["platform_fit"] = {"raw": rate, "note": note}

    rate, note = _score_timing(contact_id, platform)
    components["timing_score"] = {"raw": rate, "note": note}

    rate, note = _score_tier(contact)
    components["tier_score"] = {"raw": rate, "note": note}

    rate, note = _score_interest_match(contact_id, wish_text)
    components["interest_match"] = {"raw": rate, "note": note}

    rate, note = _score_churn_risk(contact_id)
    components["churn_risk_inv"] = {"raw": rate, "note": note}

    rate, note = _score_vip(contact_id)
    components["vip_bonus"] = {"raw": rate, "note": note}

    # Weighted sum
    total = 0.0
    for key, weight in WEIGHTS.items():
        raw = components[key]["raw"]
        weighted = raw * weight
        components[key]["weighted"] = round(weighted, 2)
        total += weighted

    # Apply style modifier
    style_mod = STYLE_MODIFIERS.get(style, 1.0)
    total     = total * style_mod

    probability = round(min(100, max(0, total)), 1)

    # Confidence label
    if probability >= 70:
        label = "high"
    elif probability >= 40:
        label = "medium"
    else:
        label = "low"
    meta = CONFIDENCE_LABELS[label]

    # Risk factors
    risks = []
    if components["contact_reply_rate"]["raw"] < 0.25:
        risks.append("Low historical reply rate")
    if components["platform_fit"]["raw"] < 0.30:
        risks.append(f"{platform} has low engagement rates")
    if components["timing_score"]["raw"] < 0.3:
        risks.append("Suboptimal send time")
    if components["interest_match"]["raw"] < 0.3:
        risks.append("Wish doesn't reference known interests")
    if components["churn_risk_inv"]["raw"] < 0.4:
        risks.append("Contact has high churn risk")
    if style_mod < 0.95:
        risks.append(f"'{style}' style may reduce engagement")

    # Recommendations
    recs = []
    if components["timing_score"]["raw"] < 0.5:
        recs.append("Wait for a better time slot (check engagement calendar)")
    if components["interest_match"]["raw"] < 0.3 and wish_text:
        recs.append("Add a reference to their interests (tech/design/etc.)")
    if components["contact_reply_rate"]["raw"] < 0.25:
        recs.append("Try a different platform or a warmer style")
    if style_mod < 0.95:
        recs.append("Switch to 'warm' or 'funny' style for better engagement")
    if components["churn_risk_inv"]["raw"] < 0.4:
        recs.append("Consider a more personal approach (voice note / gift)")
    if not risks:
        recs.append("All signals look good — send with confidence!")

    result = {
        "contact_id":       contact_id,
        "contact_name":     contact_name,
        "probability":      probability,
        "confidence_label": label,
        "icon":             meta["icon"],
        "color":            meta["color"],
        "label_text":       meta["label"],
        "components":       components,
        "risk_factors":     risks[:4],
        "recommendations":  recs[:4],
        "style":            style,
        "style_modifier":   style_mod,
        "platform":         platform,
    }

    if save:
        _save_prediction(result)

    return result


def _save_prediction(result: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO wish_predictions
            (contact_id, contact_name, probability, confidence_label,
             platform, style, components_json, risk_factors,
             recommendations, predicted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (result["contact_id"], result["contact_name"],
          result["probability"], result["confidence_label"],
          result["platform"], result["style"],
          json.dumps({k: v["weighted"] for k, v in result["components"].items()}),
          json.dumps(result["risk_factors"]),
          json.dumps(result["recommendations"]),
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def record_actual_outcome(contact_id: str, replied: bool):
    """Update the most recent prediction with the actual outcome."""
    init_predictor_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE wish_predictions SET actual_replied=?
        WHERE contact_id=? AND actual_replied IS NULL
        ORDER BY predicted_at DESC LIMIT 1
    """, (1 if replied else 0, contact_id))
    conn.commit()
    conn.close()


# ── Batch prediction ──────────────────────────────────────────────────────────

def predict_batch(
    contacts: list[dict],
    wish_text: str = "",
    style:     str = "warm",
    verbose:   bool = True,
) -> list[dict]:
    """Predict reply probability for a list of contacts."""
    if verbose:
        print(f"[Predictor] Scoring {len(contacts)} contacts...\n")

    results = []
    for c in contacts:
        pred = get_reply_prediction(
            c.get("contact_id", "unknown"),
            c.get("contact_name", "Unknown"),
            wish_text, c.get("platform", "LinkedIn"),
            style, c, save=True)
        results.append(pred)

        if verbose:
            print(f"  {pred['icon']} {pred['contact_name']:<22} "
                  f"{pred['probability']:5.1f}%  "
                  f"{pred['label_text']:<14} "
                  f"{pred['risk_factors'][0] if pred['risk_factors'] else 'No risks'}")

    results.sort(key=lambda x: -x["probability"])
    return results


def get_prediction_accuracy(days: int = 30) -> dict:
    """Compare predictions vs actual outcomes for calibration."""
    init_predictor_tables()
    conn = _db()
    rows = conn.execute("""
        SELECT probability, actual_replied
        FROM wish_predictions
        WHERE actual_replied IS NOT NULL
        ORDER BY predicted_at DESC LIMIT 100
    """).fetchall()
    conn.close()

    if not rows:
        return {"total": 0, "accuracy": None, "calibration": None}

    correct = 0
    total   = len(rows)
    for r in rows:
        predicted_reply = r["probability"] >= 50
        actual_reply    = bool(r["actual_replied"])
        if predicted_reply == actual_reply:
            correct += 1

    return {
        "total":       total,
        "accuracy":    round(correct / total, 3) if total else None,
        "correct":     correct,
        "sample_size": total,
    }


def get_prediction_log(limit: int = 20) -> list[dict]:
    """Return recent predictions."""
    init_predictor_tables()
    conn = _db()
    rows = conn.execute("""
        SELECT contact_name, probability, confidence_label,
               platform, style, actual_replied, predicted_at
        FROM wish_predictions ORDER BY predicted_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{
        "contact_name":     r["contact_name"],
        "probability":      r["probability"],
        "confidence_label": r["confidence_label"],
        "platform":         r["platform"],
        "style":            r["style"] or "warm",
        "actual_replied":   r["actual_replied"],
        "predicted_at":     r["predicted_at"],
        "icon":  CONFIDENCE_LABELS.get(r["confidence_label"],{}).get("icon","?"),
        "color": CONFIDENCE_LABELS.get(r["confidence_label"],{}).get("color","#8b949e"),
    } for r in rows]


# ── Demo contacts ─────────────────────────────────────────────────────────────

def _demo_contacts():
    return [
        {"contact_id":"urn_rakib_001","contact_name":"Rakib Hossain",
         "tier":"Close Friend","platform":"LinkedIn"},
        {"contact_id":"urn_nadia_002","contact_name":"Nadia Islam",
         "tier":"Colleague","platform":"WhatsApp"},
        {"contact_id":"urn_mim_004","contact_name":"Mim Chowdhury",
         "tier":"Close Friend","platform":"WhatsApp"},
        {"contact_id":"urn_tanvir_003","contact_name":"Tanvir Ahmed",
         "tier":"Colleague","platform":"LinkedIn"},
        {"contact_id":"urn_sara_005","contact_name":"Sara Khan",
         "tier":"Acquaintance","platform":"LinkedIn"},
    ]


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Wish Predictor", page_icon="🎯",
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
    .p-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .rec-card{background:#0a1a2a;border:1px solid #1f3a5a;border-left:3px solid #58a6ff;
              border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:0.78rem;}
    .risk-card{background:#1a0505;border:1px solid #3a1515;border-left:3px solid #f85149;
               border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:0.78rem;}
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

    init_predictor_tables()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🎯</span>
      <h1>Wish Performance Predictor</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    log     = get_prediction_log(50)
    acc     = get_prediction_accuracy()
    high_ct = sum(1 for p in log if p["confidence_label"] == "high")
    low_ct  = sum(1 for p in log if p["confidence_label"] == "low")

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Predictions", len(log), "#e6edf3"),
        (m2, "Likely Reply", high_ct, "#3fb950"),
        (m3, "Low Chance",  low_ct,  "#f85149"),
        (m4, "Accuracy",    f"{acc['accuracy']:.0%}" if acc['accuracy'] else "N/A",
         "#58a6ff"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" '
                        f'style="color:{color};font-size:0.95rem">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.5], gap="large")

    with left:
        st.markdown('<div class="section-title">Predict Reply</div>',
                    unsafe_allow_html=True)
        p_cid   = st.text_input("Contact ID", placeholder="urn_rakib_001",
                                label_visibility="collapsed", key="pcid")
        p_name  = st.text_input("Name", placeholder="Rakib Hossain",
                                label_visibility="collapsed", key="pname")
        p_wish  = st.text_area("Wish text", height=60,
                               label_visibility="collapsed", key="pwish",
                               placeholder="Happy Birthday! Your Python work inspires...")
        p_plat  = st.selectbox("Platform",
                               list(PLATFORM_BASE_RATES.keys()),
                               label_visibility="collapsed", key="pplat")
        p_style = st.selectbox("Style",
                               list(STYLE_MODIFIERS.keys()),
                               label_visibility="collapsed", key="pstyle")

        if st.button("🎯 Predict", type="primary", use_container_width=True):
            if p_cid:
                pred = get_reply_prediction(
                    p_cid, p_name or p_cid, p_wish or "",
                    p_plat, p_style)
                st.session_state["last_pred"] = pred
                st.rerun()

        pred = st.session_state.get("last_pred")
        if pred:
            prob  = pred["probability"]
            color = pred["color"]
            pct   = int(prob)
            st.markdown(f"""
            <div class="p-card" style="border-left:4px solid {color};text-align:center">
              <div style="font-size:2.5rem;font-weight:700;font-family:'JetBrains Mono',
                          monospace;color:{color}">{prob:.0f}%</div>
              <div style="font-size:0.82rem;color:{color};font-weight:700;margin-top:4px">
                {pred['icon']} {pred['label_text']}
              </div>
              <div style="background:#0d1117;border-radius:4px;height:8px;
                          margin:10px 20px;overflow:hidden">
                <div style="width:{pct}%;height:100%;background:{color};
                            border-radius:4px"></div>
              </div>
              <div style="font-size:0.68rem;color:#8b949e">
                Style: {pred['style']} (×{pred['style_modifier']:.2f}) ·
                {pred['platform']}
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Risks
            if pred["risk_factors"]:
                for rf in pred["risk_factors"]:
                    st.markdown(f'<div class="risk-card">⚠️ {rf}</div>',
                                unsafe_allow_html=True)
            # Recommendations
            for rec in pred["recommendations"]:
                st.markdown(f'<div class="rec-card">💡 {rec}</div>',
                            unsafe_allow_html=True)

    with right:
        pred = st.session_state.get("last_pred")
        if pred:
            st.markdown('<div class="section-title">Score Breakdown</div>',
                        unsafe_allow_html=True)
            COMP_COLORS = {
                "contact_reply_rate":"#58a6ff", "platform_fit":"#3fb950",
                "timing_score":"#d29922", "tier_score":"#bc8cff",
                "interest_match":"#f78166", "churn_risk_inv":"#4fc3f7",
                "vip_bonus":"#d29922",
            }
            for key, weight in WEIGHTS.items():
                comp  = pred["components"][key]
                color = COMP_COLORS.get(key, "#8b949e")
                pct   = int(comp["raw"] * 100)
                st.markdown(f"""
                <div style="margin-bottom:10px">
                  <div style="display:flex;justify-content:space-between;
                              font-size:0.76rem;margin-bottom:3px">
                    <span>{key.replace('_',' ').title()}</span>
                    <span style="font-family:'JetBrains Mono',monospace;
                                 color:{color}">{comp['weighted']:.1f}/{weight}</span>
                  </div>
                  <div style="background:#0d1117;border-radius:3px;height:14px;
                              overflow:hidden">
                    <div style="width:{pct}%;height:100%;background:{color};
                                border-radius:3px"></div>
                  </div>
                  <div style="font-size:0.62rem;color:#8b949e;margin-top:2px">
                    {comp['note']}
                  </div>
                </div>
                """, unsafe_allow_html=True)

        # Prediction log
        st.markdown('<div class="section-title">Prediction Log</div>',
                    unsafe_allow_html=True)
        for entry in log[:10]:
            color = entry["color"]
            ts    = entry["predicted_at"][:16].replace("T"," ")
            actual = ""
            if entry["actual_replied"] is not None:
                actual = (" · ✅ replied" if entry["actual_replied"]
                          else " · ❌ no reply")
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:8px;
                        padding:6px 0;border-bottom:1px solid #21262d;
                        font-size:0.76rem">
              <span>{entry['icon']}</span>
              <span style="flex:1">{entry['contact_name']}</span>
              <span style="color:{color};font-weight:700;
                          font-family:'JetBrains Mono',monospace">
                {entry['probability']:.0f}%
              </span>
              <span style="color:#8b949e;font-size:0.65rem">
                {entry['platform']} · {ts}{actual}
              </span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Wish Performance Predictor</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_predictor_tables()
    print("=== Wish Performance Predictor -- self test ===\n")

    wish = "Happy Birthday Rakib! Your Python and distributed systems work at Pathao is inspiring."
    contacts = _demo_contacts()
    results  = predict_batch(contacts, wish_text=wish, style="warm", verbose=True)

    print(f"\nRanked by reply probability:")
    for r in results:
        risks = r["risk_factors"][0] if r["risk_factors"] else "No risks"
        print(f"  {r['icon']} {r['contact_name']:<22} {r['probability']:5.1f}%  "
              f"[{r['label_text']}]  {risks}")

    print(f"\nDetailed breakdown for top contact ({results[0]['contact_name']}):")
    for key, comp in results[0]["components"].items():
        print(f"  {key:<22} {comp['weighted']:5.1f}/{WEIGHTS[key]}  {comp['note']}")

    print(f"\nRecommendations:")
    for rec in results[0]["recommendations"]:
        print(f"  💡 {rec}")

    acc = get_prediction_accuracy()
    print(f"\nModel accuracy: {acc}")
else:
    render_dashboard()
