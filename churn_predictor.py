"""
Predictive Churn Model -- Birthday Wishes Agent v10.0
Uses a lightweight ML model (RandomForest + fallback rule-based)
to predict which contacts are likely to disengage before it happens.

Features used:
  - days_since_last_contact
  - reply_rate (replies / wishes_sent)
  - avg_sentiment_score (1-5)
  - tier_score (0-10)
  - wishes_sent_total
  - days_since_reply
  - is_vip (0/1)
  - platform_reply_rate (platform avg)

Churn labels:
  high    -- very likely to disengage (probability > 0.7)
  medium  -- at risk (0.4 - 0.7)
  low     -- healthy (< 0.4)

Alert system:
  - High risk contacts → immediate alert + enqueue checkin
  - Medium risk → weekly summary flag
  - Low risk → no action

Integrates with: contacts/relationship_tiering.py,
                 contacts/reply_sentiment_trend.py,
                 dashboards/relationship_graph.py,
                 redis_cache.py, autonomous_agent.py
"""

import sqlite3
import json
import pickle
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH    = Path("agent_history.db")
MODEL_PATH = Path("churn_model.pkl")

CHURN_LABELS = {
    "high":   {"label": "High Risk",   "color": "#f85149", "icon": "🔴", "threshold": 0.7},
    "medium": {"label": "Medium Risk", "color": "#d29922", "icon": "🟡", "threshold": 0.4},
    "low":    {"label": "Low Risk",    "color": "#3fb950", "icon": "🟢", "threshold": 0.0},
}

FEATURE_NAMES = [
    "days_since_last_contact",
    "reply_rate",
    "avg_sentiment",
    "tier_score",
    "wishes_sent_total",
    "days_since_reply",
    "is_vip",
    "platform_reply_rate",
]


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_churn_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS churn_predictions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            churn_prob      REAL NOT NULL,
            churn_label     TEXT NOT NULL,
            features_json   TEXT NOT NULL,
            model_version   TEXT NOT NULL DEFAULT 'v1',
            alerted         INTEGER NOT NULL DEFAULT 0,
            predicted_at    TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS churn_model_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT NOT NULL,
            contacts_scored INTEGER NOT NULL DEFAULT 0,
            high_risk       INTEGER NOT NULL DEFAULT 0,
            medium_risk     INTEGER NOT NULL DEFAULT 0,
            low_risk        INTEGER NOT NULL DEFAULT 0,
            model_version   TEXT NOT NULL DEFAULT 'v1',
            ran_at          TEXT NOT NULL
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

def extract_features(contact_id: str, contact: dict) -> dict:
    """
    Extract numeric ML features for one contact from the DB.
    Returns feature dict (always has all keys, uses defaults if data missing).
    """
    conn = _db()

    # --- days_since_last_contact ---
    days_since = 999
    if _table_exists(conn, "wish_outcome_log"):
        row = conn.execute("""
            SELECT sent_at FROM wish_outcome_log
            WHERE contact_id=? ORDER BY sent_at DESC LIMIT 1
        """, (contact_id,)).fetchone()
        if row:
            try:
                last = datetime.fromisoformat(row["sent_at"])
                days_since = (datetime.now() - last).days
            except ValueError:
                pass

    # --- reply_rate and wishes_sent_total ---
    reply_rate    = 0.5   # default: no data
    wishes_total  = 0
    if _table_exists(conn, "wish_outcome_log"):
        row = conn.execute("""
            SELECT COUNT(*) as total, SUM(replied) as replies
            FROM wish_outcome_log WHERE contact_id=?
        """, (contact_id,)).fetchone()
        if row and row["total"]:
            wishes_total = row["total"]
            reply_rate   = round((row["replies"] or 0) / row["total"], 3)

    # --- avg_sentiment ---
    avg_sentiment = 3.0   # neutral default
    if _table_exists(conn, "wish_outcome_log"):
        row = conn.execute("""
            SELECT AVG(sentiment_score) FROM wish_outcome_log
            WHERE contact_id=? AND sentiment_score IS NOT NULL
        """, (contact_id,)).fetchone()
        if row and row[0]:
            avg_sentiment = round(row[0], 2)
    elif _table_exists(conn, "reply_sentiment_log"):
        row = conn.execute("""
            SELECT AVG(sentiment_score) FROM reply_sentiment_log
            WHERE contact_id=?
        """, (contact_id,)).fetchone()
        if row and row[0]:
            avg_sentiment = round(row[0], 2)

    # --- tier_score ---
    tier_score = contact.get("tier_score", 5.0)
    if _table_exists(conn, "contact_tier"):
        row = conn.execute("""
            SELECT tier_score FROM contact_tier WHERE contact_id=?
        """, (contact_id,)).fetchone()
        if row:
            tier_score = row["tier_score"] or 5.0

    # --- days_since_reply ---
    days_since_reply = 999
    if _table_exists(conn, "wish_outcome_log"):
        row = conn.execute("""
            SELECT replied_at FROM wish_outcome_log
            WHERE contact_id=? AND replied_at IS NOT NULL
            ORDER BY replied_at DESC LIMIT 1
        """, (contact_id,)).fetchone()
        if row and row["replied_at"]:
            try:
                last_r = datetime.fromisoformat(row["replied_at"])
                days_since_reply = (datetime.now() - last_r).days
            except ValueError:
                pass

    # --- is_vip ---
    is_vip = 0
    if _table_exists(conn, "vip_contacts"):
        row = conn.execute("""
            SELECT active FROM vip_contacts WHERE contact_id=? AND active=1
        """, (contact_id,)).fetchone()
        is_vip = 1 if row else 0

    # --- platform_reply_rate ---
    platform        = contact.get("platform", "LinkedIn")
    plat_reply_rate = 0.35
    if _table_exists(conn, "wish_outcome_log"):
        row = conn.execute("""
            SELECT COUNT(*) as total, SUM(replied) as replies
            FROM wish_outcome_log WHERE platform=?
        """, (platform,)).fetchone()
        if row and row["total"]:
            plat_reply_rate = round((row["replies"] or 0) / row["total"], 3)

    conn.close()

    return {
        "days_since_last_contact": days_since,
        "reply_rate":              reply_rate,
        "avg_sentiment":           avg_sentiment,
        "tier_score":              tier_score,
        "wishes_sent_total":       wishes_total,
        "days_since_reply":        days_since_reply,
        "is_vip":                  is_vip,
        "platform_reply_rate":     plat_reply_rate,
    }


def features_to_vector(features: dict) -> list:
    """Convert feature dict to ordered numeric list for sklearn."""
    return [features[k] for k in FEATURE_NAMES]


# ── Model training ────────────────────────────────────────────────────────────

def _generate_synthetic_training_data(n: int = 500):
    """
    Generate labelled synthetic data for initial model training.
    In production, replace with real historical churn labels.

    Churn heuristic:
      - churned if days_since_last_contact > 120 AND reply_rate < 0.2
      - churned if avg_sentiment < 2.5 AND days_since_reply > 90
    """
    random.seed(42)
    X, y = [], []
    for _ in range(n):
        days_contact = random.randint(0, 365)
        reply_rate   = random.uniform(0, 1)
        sentiment    = random.uniform(1, 5)
        tier         = random.uniform(1, 10)
        wishes       = random.randint(0, 30)
        days_reply   = random.randint(0, 365)
        is_vip       = random.choice([0, 0, 0, 1])
        plat_rate    = random.uniform(0.1, 0.8)

        # Label: 1 = churned (disengaged)
        churned = int(
            (days_contact > 120 and reply_rate < 0.2) or
            (sentiment < 2.5 and days_reply > 90) or
            (days_contact > 200 and tier < 4) or
            (reply_rate < 0.1 and wishes > 3)
        )
        X.append([days_contact, reply_rate, sentiment, tier,
                  wishes, days_reply, is_vip, plat_rate])
        y.append(churned)
    return X, y


def train_model(save: bool = True) -> object:
    """
    Train a RandomForestClassifier on synthetic data.
    In production, call this periodically with real labelled data.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    X, y = _generate_synthetic_training_data(800)
    clf  = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestClassifier(
            n_estimators=100, max_depth=6,
            random_state=42, class_weight="balanced",
        )),
    ])
    clf.fit(X, y)

    if save:
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(clf, f)
        print(f"[ChurnModel] Model trained and saved to {MODEL_PATH}")

    return clf


def load_or_train_model():
    """Load saved model or train from scratch if not found."""
    if MODEL_PATH.exists():
        try:
            with open(MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    return train_model(save=True)


# ── Prediction ────────────────────────────────────────────────────────────────

def predict_churn(
    contact_id:   str,
    contact:      dict,
    model=None,
) -> dict:
    """
    Predict churn probability for one contact.

    Args:
        contact_id: Unique identifier.
        contact:    Dict with at least contact_name, platform, tier_score.
        model:      Pre-loaded sklearn model (loaded if None).

    Returns:
        {
          contact_id, contact_name, churn_prob, churn_label,
          churn_color, churn_icon, features, top_risk_factors
        }
    """
    if model is None:
        model = load_or_train_model()

    features = extract_features(contact_id, contact)
    vec      = [features_to_vector(features)]

    try:
        proba       = model.predict_proba(vec)[0]
        churn_prob  = round(float(proba[1]), 3)
    except Exception:
        # Fallback: rule-based estimate
        churn_prob = _rule_based_churn(features)

    # Label
    if churn_prob >= CHURN_LABELS["high"]["threshold"]:
        label = "high"
    elif churn_prob >= CHURN_LABELS["medium"]["threshold"]:
        label = "medium"
    else:
        label = "low"

    meta   = CHURN_LABELS[label]
    risks  = _top_risk_factors(features, churn_prob)

    return {
        "contact_id":       contact_id,
        "contact_name":     contact.get("contact_name", "Unknown"),
        "churn_prob":       churn_prob,
        "churn_label":      label,
        "churn_color":      meta["color"],
        "churn_icon":       meta["icon"],
        "churn_label_text": meta["label"],
        "features":         features,
        "top_risk_factors": risks,
    }


def _rule_based_churn(features: dict) -> float:
    """Simple rule-based fallback when sklearn unavailable."""
    score = 0.0
    if features["days_since_last_contact"] > 120:
        score += 0.3
    if features["reply_rate"] < 0.2:
        score += 0.25
    if features["avg_sentiment"] < 2.5:
        score += 0.2
    if features["days_since_reply"] > 90:
        score += 0.15
    if features["tier_score"] < 4:
        score += 0.1
    if features["is_vip"]:
        score -= 0.1
    return min(1.0, max(0.0, round(score, 3)))


def _top_risk_factors(features: dict, churn_prob: float) -> list[str]:
    """Identify the top 3 human-readable risk factors."""
    risks = []
    if features["days_since_last_contact"] > 90:
        risks.append(f"No contact in {features['days_since_last_contact']}d")
    if features["reply_rate"] < 0.25:
        risks.append(f"Low reply rate ({features['reply_rate']:.0%})")
    if features["avg_sentiment"] < 3.0:
        risks.append(f"Low sentiment ({features['avg_sentiment']:.1f}/5)")
    if features["days_since_reply"] > 60:
        risks.append(f"Last reply {features['days_since_reply']}d ago")
    if features["wishes_sent_total"] > 5 and features["reply_rate"] < 0.3:
        risks.append("High outreach, low engagement")
    return risks[:3] if risks else ["No significant risk factors"]


# ── Batch scoring ─────────────────────────────────────────────────────────────

def score_all_contacts(
    contacts: Optional[list] = None,
    verbose:  bool = True,
) -> list[dict]:
    """
    Score every contact for churn risk.

    Args:
        contacts: List of contact dicts. Loads from DB if None.
        verbose:  Print progress.

    Returns:
        List of prediction dicts sorted by churn_prob descending.
    """
    init_churn_tables()
    model = load_or_train_model()

    if contacts is None:
        contacts = _load_contacts()

    if verbose:
        print(f"[ChurnModel] Scoring {len(contacts)} contacts...\n")

    run_id      = datetime.now().strftime("churn_%Y%m%d_%H%M%S")
    predictions = []
    counts      = {"high": 0, "medium": 0, "low": 0}

    for c in contacts:
        cid  = c.get("contact_id", "unknown")
        pred = predict_churn(cid, c, model=model)
        predictions.append(pred)
        counts[pred["churn_label"]] += 1

        # Persist
        _save_prediction(pred)

        if verbose and pred["churn_label"] in ("high", "medium"):
            icon = pred["churn_icon"]
            print(f"  {icon} {pred['contact_name']:<22} "
                  f"{pred['churn_prob']:.0%}  "
                  f"{pred['top_risk_factors'][0]}")

    # Log run
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO churn_model_runs
            (run_id, contacts_scored, high_risk, medium_risk, low_risk, ran_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (run_id, len(contacts), counts["high"],
          counts["medium"], counts["low"],
          datetime.now().isoformat()))
    conn.commit()
    conn.close()

    predictions.sort(key=lambda x: -x["churn_prob"])

    if verbose:
        print(f"\n[ChurnModel] Results: 🔴 {counts['high']} high | "
              f"🟡 {counts['medium']} medium | 🟢 {counts['low']} low")

    return predictions


def _save_prediction(pred: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO churn_predictions
            (contact_id, contact_name, churn_prob, churn_label,
             features_json, predicted_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (pred["contact_id"], pred["contact_name"],
          pred["churn_prob"], pred["churn_label"],
          json.dumps(pred["features"]), datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Alert system ──────────────────────────────────────────────────────────────

def send_churn_alerts(
    predictions:  list[dict],
    dry_run:      bool = True,
    threshold:    str = "high",
) -> dict:
    """
    Send alerts for high-risk contacts and enqueue check-in tasks.

    Args:
        predictions:  From score_all_contacts().
        dry_run:      If True, don't actually enqueue.
        threshold:    Alert for contacts at or above this risk level.

    Returns:
        { alerted, queued, contacts }
    """
    thresholds = {"high": 0.7, "medium": 0.4, "low": 0.0}
    min_prob   = thresholds.get(threshold, 0.7)
    at_risk    = [p for p in predictions if p["churn_prob"] >= min_prob]

    enqueue_fn = _safe("redis_cache", "enqueue")
    alerted    = []

    for p in at_risk:
        payload = {
            "contact_id":    p["contact_id"],
            "contact_name":  p["contact_name"],
            "churn_prob":    p["churn_prob"],
            "churn_label":   p["churn_label"],
            "risk_factors":  p["top_risk_factors"],
            "action":        "checkin",
        }
        if not dry_run and enqueue_fn:
            try:
                enqueue_fn("alerts", "churn_alert", payload, priority=8)
            except Exception:
                pass

        alerted.append(p["contact_name"])

        # Mark as alerted
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            UPDATE churn_predictions SET alerted=1
            WHERE contact_id=? AND alerted=0
        """, (p["contact_id"],))
        conn.commit()
        conn.close()

    return {
        "alerted": len(at_risk),
        "queued":  len(at_risk) if not dry_run else 0,
        "contacts":alerted,
        "dry_run": dry_run,
    }


# ── Retrieval ─────────────────────────────────────────────────────────────────

def get_high_risk_contacts(limit: int = 20) -> list[dict]:
    """Return most recent high/medium risk predictions."""
    init_churn_tables()
    conn = _db()
    rows = conn.execute("""
        SELECT contact_id, contact_name, churn_prob, churn_label,
               features_json, alerted, predicted_at
        FROM churn_predictions
        WHERE churn_label IN ('high','medium')
        ORDER BY predicted_at DESC, churn_prob DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        label = r["churn_label"]
        meta  = CHURN_LABELS.get(label, CHURN_LABELS["medium"])
        result.append({
            "contact_id":   r["contact_id"],
            "contact_name": r["contact_name"],
            "churn_prob":   r["churn_prob"],
            "churn_label":  label,
            "color":        meta["color"],
            "icon":         meta["icon"],
            "label_text":   meta["label"],
            "features":     json.loads(r["features_json"] or "{}"),
            "alerted":      bool(r["alerted"]),
            "predicted_at": r["predicted_at"],
        })
    return result


def _load_contacts() -> list[dict]:
    """Load contacts from DB for batch scoring."""
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
            contacts.append({"contact_id": r["contact_id"],
                             "contact_name": r["contact_name"],
                             "tier": r["current_tier"],
                             "tier_score": r["tier_score"] or 5.0,
                             "platform": "LinkedIn"})
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
        {"contact_id":"urn_farah_007","contact_name":"Farah Akter",
         "tier":"Acquaintance","tier_score":2.0,"platform":"LinkedIn"},
    ]


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Churn Predictor", page_icon="📉",
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
    .c-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
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

    init_churn_tables()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📉</span>
      <h1>Predictive Churn Model</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    preds = st.session_state.get("churn_preds", [])
    high  = [p for p in preds if p.get("churn_label") == "high"]
    med   = [p for p in preds if p.get("churn_label") == "medium"]
    low   = [p for p in preds if p.get("churn_label") == "low"]

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Scored",      len(preds),  "#e6edf3"),
        (m2, "High Risk",   len(high),   "#f85149"),
        (m3, "Medium Risk", len(med),    "#d29922"),
        (m4, "Low Risk",    len(low),    "#3fb950"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.5], gap="large")

    with left:
        st.markdown('<div class="section-title">Controls</div>',
                    unsafe_allow_html=True)
        dry_run = st.checkbox("Dry Run (no real alerts)", value=True)
        thresh  = st.selectbox("Alert threshold",
                               ["high","medium"], label_visibility="collapsed",
                               key="thresh")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔍 Score All", type="primary",
                         use_container_width=True):
                with st.spinner("Scoring contacts..."):
                    preds = score_all_contacts(verbose=False)
                st.session_state["churn_preds"] = preds
                st.rerun()
        with c2:
            if st.button("🔔 Send Alerts",
                         use_container_width=True,
                         disabled=not preds):
                alerts = send_churn_alerts(preds, dry_run=dry_run,
                                           threshold=thresh)
                st.success(f"Alerted {alerts['alerted']} contacts"
                           + (" (dry)" if dry_run else ""))

        # Feature importance (static)
        st.markdown('<div class="section-title">Feature Weights</div>',
                    unsafe_allow_html=True)
        feat_weights = [
            ("days_since_last_contact", 0.28, "#f85149"),
            ("reply_rate",              0.24, "#d29922"),
            ("avg_sentiment",           0.18, "#d29922"),
            ("days_since_reply",        0.12, "#58a6ff"),
            ("tier_score",              0.08, "#3fb950"),
            ("wishes_sent_total",       0.05, "#3fb950"),
            ("is_vip",                  0.03, "#3fb950"),
            ("platform_reply_rate",     0.02, "#3fb950"),
        ]
        for fname, weight, color in feat_weights:
            pct = int(weight * 100)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">
              <div style="width:160px;font-size:0.70rem;font-family:'JetBrains Mono',
                          monospace;color:#c9d1d9;overflow:hidden;
                          text-overflow:ellipsis">{fname}</div>
              <div style="flex:1;background:#0d1117;border-radius:3px;height:14px">
                <div style="width:{pct}%;height:100%;background:{color};
                            border-radius:3px"></div>
              </div>
              <div style="width:32px;font-size:0.68rem;color:#8b949e;
                          text-align:right">{pct}%</div>
            </div>
            """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Risk Predictions</div>',
                    unsafe_allow_html=True)
        if not preds:
            st.caption("Click 'Score All' to run predictions.")
        for p in preds:
            color = p.get("churn_color", "#8b949e")
            prob  = p.get("churn_prob", 0)
            risks = p.get("top_risk_factors", [])
            ts    = (p.get("predicted_at","")or"")[:16].replace("T"," ")
            pct   = int(prob * 100)
            st.markdown(f"""
            <div class="c-card" style="border-left:3px solid {color}">
              <div style="display:flex;align-items:center;
                          justify-content:space-between;margin-bottom:6px">
                <div style="font-weight:700">{p['churn_icon']} {p['contact_name']}</div>
                <div style="font-weight:700;font-family:'JetBrains Mono',monospace;
                            color:{color}">{prob:.0%}</div>
              </div>
              <div style="background:#0d1117;border-radius:4px;height:6px;
                          overflow:hidden;margin-bottom:6px">
                <div style="width:{pct}%;height:100%;background:{color};
                            border-radius:4px"></div>
              </div>
              <div style="font-size:0.68rem;color:#8b949e">
                {" · ".join(risks[:2])}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Predictive Churn Model</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_churn_tables()
    print("=== Churn Predictor -- self test ===\n")
    preds = score_all_contacts(verbose=True)
    print(f"\nAll predictions ({len(preds)}):")
    for p in preds:
        print(f"  {p['churn_icon']} {p['contact_name']:<22} "
              f"{p['churn_prob']:.0%}  {p['churn_label']:<8} "
              f"{p['top_risk_factors'][0]}")
    alerts = send_churn_alerts(preds, dry_run=True, threshold="high")
    print(f"\nAlerts (dry): {alerts['alerted']} contacts → {alerts['contacts']}")
else:
    render_dashboard()
