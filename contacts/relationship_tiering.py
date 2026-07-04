"""
Relationship Tiering Auto-Adjust — Birthday Wishes Agent v8.0
Automatically moves contacts between tiers (Close Friend / Colleague / Acquaintance)
based on reply speed, reply depth, interaction frequency, and sentiment trend —
not just a static score set once and forgotten.

Tier rules:
  Close Friend   → replies fast (<6h), long/warm replies, interacts 3+/year
  Colleague      → replies within 48h, moderate depth, interacts 1-2/year
  Acquaintance   → slow/no reply, short/cold replies, rare interaction

Integrates with: contacts/connection_tracker.py, contacts/reply_sentiment_trend.py,
                 agent.py, contact_timeline.py
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

# ── Tier definitions ──────────────────────────────────────────────────────────

TIERS = {
    "Close Friend":  {"rank": 3, "color": "#3fb950", "emoji": "💚"},
    "Colleague":     {"rank": 2, "color": "#58a6ff", "emoji": "💼"},
    "Acquaintance":  {"rank": 1, "color": "#8b949e", "emoji": "👋"},
}

# Thresholds for auto-adjustment
THRESHOLDS = {
    # Reply speed (hours) — lower = faster
    "fast_reply_hrs":   6,
    "medium_reply_hrs": 48,

    # Reply depth (word count)
    "deep_reply_words":    15,
    "shallow_reply_words":  4,

    # Interaction frequency per year
    "high_freq_per_year":   3,
    "low_freq_per_year":    1,

    # Sentiment score (1-5 scale)
    "warm_sentiment":    4.0,
    "cold_sentiment":    2.5,

    # Consecutive no-replies before downgrade
    "no_reply_downgrade": 2,

    # Minimum interactions before auto-adjust kicks in
    "min_interactions": 2,
}

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_tiering_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_tier (
            contact_id      TEXT PRIMARY KEY,
            contact_name    TEXT NOT NULL,
            current_tier    TEXT NOT NULL DEFAULT 'Acquaintance',
            previous_tier   TEXT,
            tier_score      REAL NOT NULL DEFAULT 0,
            last_adjusted   TEXT,
            adjustment_reason TEXT,
            locked          INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tier_change_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            from_tier       TEXT NOT NULL,
            to_tier         TEXT NOT NULL,
            reason          TEXT,
            score_before    REAL,
            score_after     REAL,
            changed_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interaction_signal (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            signal_type     TEXT NOT NULL,
            signal_value    REAL,
            signal_meta     TEXT,
            logged_at       TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Signal logging ─────────────────────────────────────────────────────────────

def log_signal(
    contact_id:   str,
    contact_name: str,
    signal_type:  str,
    value:        float,
    meta:         Optional[dict] = None,
):
    """
    Log one interaction signal for a contact.
    Call this from agent.py after every wish/reply event.

    signal_type options:
        reply_speed_hrs   — hours between wish and reply (lower = better)
        reply_word_count  — word count of their reply
        sentiment_score   — 1-5 from reply_sentiment_trend
        no_reply          — 1.0 when no reply received
        wish_sent         — 1.0 when a wish was sent (tracks frequency)
    """
    init_tiering_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO interaction_signal
            (contact_id, contact_name, signal_type, signal_value, signal_meta, logged_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, signal_type, value,
          json.dumps(meta or {}), datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Score computation ──────────────────────────────────────────────────────────

def compute_tier_score(contact_id: str, lookback_days: int = 365) -> dict:
    """
    Compute a 0-100 relationship score from recent interaction signals.

    Score components:
      Reply speed     (0-30 pts)
      Reply depth     (0-25 pts)
      Frequency       (0-25 pts)
      Sentiment       (0-20 pts)
    Penalty:
      No-reply streak (-10 pts each)

    Returns:
        { score, components, interaction_count, no_reply_streak }
    """
    init_tiering_tables()
    cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    rows   = conn.execute("""
        SELECT signal_type, signal_value FROM interaction_signal
        WHERE contact_id = ? AND logged_at >= ?
        ORDER BY logged_at DESC
    """, (contact_id, cutoff)).fetchall()
    conn.close()

    if not rows:
        return {"score": 0, "components": {}, "interaction_count": 0, "no_reply_streak": 0}

    signals: dict[str, list] = {}
    for stype, val in rows:
        signals.setdefault(stype, []).append(val)

    t = THRESHOLDS
    comps = {}

    # ── Reply speed (0-30) ────────────────────────────────────────────────────
    speeds = signals.get("reply_speed_hrs", [])
    if speeds:
        avg_speed = sum(speeds) / len(speeds)
        if avg_speed <= t["fast_reply_hrs"]:
            comps["reply_speed"] = 30
        elif avg_speed <= t["medium_reply_hrs"]:
            comps["reply_speed"] = int(30 * (1 - (avg_speed - t["fast_reply_hrs"]) /
                                              (t["medium_reply_hrs"] - t["fast_reply_hrs"])))
        else:
            comps["reply_speed"] = max(0, int(10 * (1 - (avg_speed - t["medium_reply_hrs"]) / 120)))
    else:
        comps["reply_speed"] = 0

    # ── Reply depth (0-25) ────────────────────────────────────────────────────
    depths = signals.get("reply_word_count", [])
    if depths:
        avg_depth = sum(depths) / len(depths)
        comps["reply_depth"] = min(25, int(avg_depth / t["deep_reply_words"] * 25))
    else:
        comps["reply_depth"] = 0

    # ── Frequency (0-25) ─────────────────────────────────────────────────────
    wishes_sent = len(signals.get("wish_sent", []))
    years = lookback_days / 365
    freq_per_year = wishes_sent / years if years > 0 else 0
    if freq_per_year >= t["high_freq_per_year"]:
        comps["frequency"] = 25
    elif freq_per_year >= t["low_freq_per_year"]:
        comps["frequency"] = int(25 * freq_per_year / t["high_freq_per_year"])
    else:
        comps["frequency"] = max(0, int(10 * freq_per_year))

    # ── Sentiment (0-20) ─────────────────────────────────────────────────────
    sentiments = signals.get("sentiment_score", [])
    if sentiments:
        avg_sent = sum(sentiments) / len(sentiments)
        comps["sentiment"] = min(20, int((avg_sent - 1) / 4 * 20))
    else:
        comps["sentiment"] = 0

    # ── No-reply penalty ──────────────────────────────────────────────────────
    no_replies = signals.get("no_reply", [])
    # Streak = consecutive no-replies at the END of the signal list
    streak = 0
    for stype, _ in rows:
        if stype == "no_reply":
            streak += 1
        elif stype == "reply_speed_hrs":
            break

    penalty = streak * 10

    raw_score = sum(comps.values()) - penalty
    score     = max(0, min(100, raw_score))

    return {
        "score":             round(score, 1),
        "components":        comps,
        "interaction_count": len(rows),
        "no_reply_streak":   streak,
        "avg_speed_hrs":     round(sum(speeds)/len(speeds), 1) if speeds else None,
        "avg_depth_words":   round(sum(depths)/len(depths), 1) if depths else None,
    }


# ── Tier classification ────────────────────────────────────────────────────────

def classify_tier(score: float) -> str:
    if score >= 65:
        return "Close Friend"
    if score >= 35:
        return "Colleague"
    return "Acquaintance"


# ── Auto-adjust ────────────────────────────────────────────────────────────────

def auto_adjust_tier(
    contact_id:   str,
    contact_name: str,
    verbose:      bool = True,
) -> dict:
    """
    Main entry point. Recompute tier for one contact and apply if changed.

    Args:
        contact_id:   Unique contact identifier.
        contact_name: Human-readable name.
        verbose:      Print result to console.

    Returns:
        {
          contact_id, contact_name,
          previous_tier, new_tier, changed,
          score, components, reason
        }
    """
    init_tiering_tables()

    # Skip locked contacts (manually set by user)
    conn = sqlite3.connect(DB_PATH)
    lock_row = conn.execute(
        "SELECT locked, current_tier FROM contact_tier WHERE contact_id = ?",
        (contact_id,)
    ).fetchone()
    conn.close()

    if lock_row and lock_row[0]:
        return {
            "contact_id": contact_id, "contact_name": contact_name,
            "previous_tier": lock_row[1], "new_tier": lock_row[1],
            "changed": False, "locked": True,
            "score": None, "reason": "Tier manually locked",
        }

    result   = compute_tier_score(contact_id)
    score    = result["score"]
    n        = result["interaction_count"]
    new_tier = classify_tier(score)

    # Need minimum interactions before adjusting
    if n < THRESHOLDS["min_interactions"]:
        return {
            "contact_id": contact_id, "contact_name": contact_name,
            "previous_tier": _get_current_tier(contact_id),
            "new_tier": new_tier, "changed": False,
            "score": score, "reason": f"Insufficient data ({n} interactions)",
        }

    prev_tier = _get_current_tier(contact_id)
    changed   = new_tier != prev_tier

    # Build reason string
    comps  = result["components"]
    streak = result["no_reply_streak"]
    parts  = []
    if result.get("avg_speed_hrs"):
        parts.append(f"avg reply {result['avg_speed_hrs']}h")
    if result.get("avg_depth_words"):
        parts.append(f"avg {result['avg_depth_words']} words/reply")
    if streak:
        parts.append(f"{streak} consecutive no-replies")
    reason = f"Score {score}/100 — " + ", ".join(parts) if parts else f"Score {score}/100"

    # Persist
    _upsert_tier(contact_id, contact_name, new_tier, prev_tier, score, reason)
    if changed:
        _log_tier_change(contact_id, contact_name, prev_tier, new_tier,
                         reason, score, score)

    if verbose:
        direction = ("↑ UPGRADED" if TIERS[new_tier]["rank"] > TIERS.get(prev_tier, {}).get("rank", 0)
                     else "↓ DOWNGRADED" if TIERS[new_tier]["rank"] < TIERS.get(prev_tier, {}).get("rank", 99)
                     else "→ unchanged")
        print(f"[TierAdjust] {contact_name}: {prev_tier} → {new_tier} {direction} (score={score})")
        if changed:
            print(f"  Reason: {reason}")

    return {
        "contact_id":   contact_id, "contact_name": contact_name,
        "previous_tier":prev_tier,  "new_tier":     new_tier,
        "changed":      changed,    "score":         score,
        "components":   comps,      "reason":        reason,
        "locked":       False,
    }


def auto_adjust_all(verbose: bool = True) -> list[dict]:
    """Run auto-adjust for every contact that has interaction signals."""
    init_tiering_tables()
    conn = sqlite3.connect(DB_PATH)
    ids  = conn.execute(
        "SELECT DISTINCT contact_id, contact_name FROM interaction_signal"
    ).fetchall()
    conn.close()

    results  = []
    upgraded = downgraded = unchanged = 0
    for cid, cname in ids:
        r = auto_adjust_tier(cid, cname, verbose=verbose)
        results.append(r)
        if r["changed"]:
            prev_rank = TIERS.get(r["previous_tier"], {}).get("rank", 0)
            new_rank  = TIERS.get(r["new_tier"], {}).get("rank", 0)
            if new_rank > prev_rank: upgraded += 1
            else: downgraded += 1
        else:
            unchanged += 1

    if verbose:
        print(f"\n[TierAdjust] Batch complete: "
              f"{upgraded} upgraded, {downgraded} downgraded, {unchanged} unchanged")
    return results


# ── Tier management ───────────────────────────────────────────────────────────

def lock_tier(contact_id: str, tier: str):
    """Manually pin a contact's tier — auto-adjust will skip them."""
    init_tiering_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE contact_tier SET locked=1, current_tier=? WHERE contact_id=?",
                 (tier, contact_id))
    conn.commit()
    conn.close()


def unlock_tier(contact_id: str):
    """Re-enable auto-adjust for a contact."""
    init_tiering_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE contact_tier SET locked=0 WHERE contact_id=?", (contact_id,))
    conn.commit()
    conn.close()


def get_all_tiers() -> list[dict]:
    init_tiering_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_id, contact_name, current_tier, previous_tier,
               tier_score, last_adjusted, adjustment_reason, locked
        FROM contact_tier ORDER BY tier_score DESC
    """).fetchall()
    conn.close()
    return [{
        "contact_id": r[0], "contact_name": r[1], "current_tier": r[2],
        "previous_tier": r[3], "tier_score": r[4], "last_adjusted": r[5],
        "reason": r[6], "locked": bool(r[7]),
    } for r in rows]


def get_tier_change_log(limit: int = 30) -> list[dict]:
    init_tiering_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_name, from_tier, to_tier, reason, score_after, changed_at
        FROM tier_change_log ORDER BY changed_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"contact_name": r[0], "from_tier": r[1], "to_tier": r[2],
             "reason": r[3], "score": r[4], "changed_at": r[5]} for r in rows]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_current_tier(contact_id: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute(
        "SELECT current_tier FROM contact_tier WHERE contact_id=?", (contact_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else "Acquaintance"


def _upsert_tier(contact_id, contact_name, tier, prev_tier, score, reason):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO contact_tier
            (contact_id, contact_name, current_tier, previous_tier,
             tier_score, last_adjusted, adjustment_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id) DO UPDATE SET
            previous_tier     = excluded.previous_tier,
            current_tier      = excluded.current_tier,
            tier_score        = excluded.tier_score,
            last_adjusted     = excluded.last_adjusted,
            adjustment_reason = excluded.adjustment_reason
    """, (contact_id, contact_name, tier, prev_tier, score,
          datetime.now().isoformat(), reason))
    conn.commit()
    conn.close()


def _log_tier_change(contact_id, contact_name, from_tier, to_tier, reason, score_before, score_after):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO tier_change_log
            (contact_id, contact_name, from_tier, to_tier,
             reason, score_before, score_after, changed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, from_tier, to_tier,
          reason, score_before, score_after, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Streamlit panel ───────────────────────────────────────────────────────────

def render_tiering_panel():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Tier Auto-Adjust", page_icon="🏆",
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
    .tier-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
               padding:14px 16px;margin-bottom:8px;}
    .tier-pill{display:inline-flex;align-items:center;gap:4px;font-size:0.68rem;font-weight:700;
               padding:2px 9px;border-radius:20px;text-transform:uppercase;letter-spacing:0.06em;}
    .t-close{background:#051a09;color:#3fb950;border:1px solid #3fb950;}
    .t-colleague{background:#0a1a2a;color:#58a6ff;border:1px solid #58a6ff;}
    .t-acquaint{background:#21262d;color:#8b949e;border:1px solid #30363d;}
    .score-bar-wrap{background:#0d1117;border-radius:4px;height:6px;margin-top:6px;overflow:hidden;}
    .score-bar{height:100%;border-radius:4px;}
    .change-row{background:var(--surface);border:1px solid var(--border);border-radius:8px;
                padding:10px 14px;margin-bottom:6px;font-size:0.78rem;}
    .arrow-up{color:#3fb950;font-weight:700;}
    .arrow-dn{color:#f85149;font-weight:700;}
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
      <span style="font-size:1.6rem">🏆</span>
      <h1>Relationship Tier Auto-Adjust</h1>
      <span class="cc-badge">v8.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        if st.button("⚡ Run Auto-Adjust (All)", type="primary", use_container_width=True):
            results = auto_adjust_all(verbose=False)
            changed = [r for r in results if r["changed"]]
            st.success(f"Done — {len(changed)} tier change(s)")
            st.rerun()
    with c2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    tiers  = get_all_tiers()
    changes = get_tier_change_log(limit=20)

    left, right = st.columns([1.4, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">All Contacts</div>', unsafe_allow_html=True)

        tier_filter = st.selectbox("Filter by tier",
                                   ["All", "Close Friend", "Colleague", "Acquaintance"],
                                   label_visibility="collapsed")
        if tier_filter != "All":
            tiers = [t for t in tiers if t["current_tier"] == tier_filter]

        for t in tiers:
            tier  = t["current_tier"]
            prev  = t["previous_tier"] or tier
            score = t["tier_score"] or 0
            pill_cls = {"Close Friend": "t-close", "Colleague": "t-colleague",
                        "Acquaintance": "t-acquaint"}.get(tier, "t-acquaint")
            tier_meta = TIERS.get(tier, {})
            color = tier_meta.get("color", "#8b949e")
            lock_icon = "🔒 " if t["locked"] else ""

            changed_str = ""
            if prev != tier:
                prev_rank = TIERS.get(prev, {}).get("rank", 0)
                new_rank  = TIERS.get(tier, {}).get("rank", 0)
                changed_str = f' <span style="color:{"#3fb950" if new_rank>prev_rank else "#f85149"};font-size:0.65rem">{"↑" if new_rank>prev_rank else "↓"} from {prev}</span>'

            st.markdown(f"""
            <div class="tier-card">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
                <div style="font-weight:700;font-size:0.86rem">{lock_icon}{t['contact_name']}</div>
                <span class="tier-pill {pill_cls}">{tier_meta.get('emoji','')} {tier}</span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e">
                Score: {score}/100{changed_str}
                {f' · {t["reason"][:60]}…' if t.get("reason") and len(t.get("reason",""))>10 else ''}
              </div>
              <div class="score-bar-wrap">
                <div class="score-bar" style="width:{score}%;background:{color}"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            bc1, bc2 = st.columns(2)
            with bc1:
                if t["locked"]:
                    if st.button("🔓 Unlock", key=f"ul_{t['contact_id']}", use_container_width=True):
                        unlock_tier(t["contact_id"])
                        st.rerun()
                else:
                    if st.button("🔒 Lock tier", key=f"lk_{t['contact_id']}", use_container_width=True):
                        lock_tier(t["contact_id"], tier)
                        st.rerun()
            with bc2:
                if st.button("⚡ Recalculate", key=f"rc_{t['contact_id']}", use_container_width=True):
                    auto_adjust_tier(t["contact_id"], t["contact_name"], verbose=False)
                    st.rerun()

    with right:
        st.markdown('<div class="section-title">Tier Change Log</div>', unsafe_allow_html=True)
        if not changes:
            st.caption("No tier changes yet.")
        else:
            for c in changes:
                prev_rank = TIERS.get(c["from_tier"], {}).get("rank", 0)
                new_rank  = TIERS.get(c["to_tier"],   {}).get("rank", 0)
                direction = "↑" if new_rank > prev_rank else "↓"
                arr_cls   = "arrow-up" if new_rank > prev_rank else "arrow-dn"
                ts        = (c["changed_at"] or "")[:16].replace("T", " ")
                st.markdown(f"""
                <div class="change-row">
                  <span style="font-weight:700">{c['contact_name']}</span>
                  <span class="{arr_cls}"> {direction} {c['from_tier']} → {c['to_tier']}</span><br>
                  <span style="font-size:0.68rem;color:#8b949e">{ts} · {(c.get('reason') or '')[:55]}</span>
                </div>
                """, unsafe_allow_html=True)

        # Log test signal
        st.markdown('<div class="section-title" style="margin-top:20px">Log Test Signal</div>',
                    unsafe_allow_html=True)
        all_tiers = get_all_tiers()
        if all_tiers:
            names = [t["contact_name"] for t in all_tiers]
            sel_n = st.selectbox("Contact", names, label_visibility="collapsed", key="sig_contact")
            sel_t = next(t for t in all_tiers if t["contact_name"] == sel_n)
            sig_type = st.selectbox("Signal", ["reply_speed_hrs","reply_word_count",
                                                "sentiment_score","no_reply","wish_sent"],
                                    label_visibility="collapsed", key="sig_type")
            sig_val = st.number_input("Value", value=2.0, key="sig_val",
                                      label_visibility="collapsed")
            if st.button("📥 Log Signal", type="primary", use_container_width=True):
                log_signal(sel_t["contact_id"], sel_n, sig_type, sig_val)
                auto_adjust_tier(sel_t["contact_id"], sel_n, verbose=False)
                st.success(f"Signal logged + tier recalculated ✅")
                st.rerun()

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
      <span>Relationship Tier Auto-Adjust</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


def _seed_demo():
    """Seed demo signals if tables are empty."""
    init_tiering_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM interaction_signal").fetchone()[0]
    conn.close()
    if count > 0:
        return

    import random as _r
    _r.seed(42)
    contacts = [
        ("urn_rakib_001","Rakib Hossain",  [("reply_speed_hrs",2),("reply_word_count",22),
                                             ("sentiment_score",4.5),("wish_sent",1),
                                             ("reply_speed_hrs",4),("reply_word_count",18),
                                             ("wish_sent",1),("reply_speed_hrs",3)]),
        ("urn_nadia_002","Nadia Islam",    [("wish_sent",1),("reply_speed_hrs",8),
                                             ("reply_word_count",12),("wish_sent",1),
                                             ("no_reply",1),("wish_sent",1),("no_reply",1)]),
        ("urn_tanvir_003","Tanvir Ahmed",  [("wish_sent",1),("reply_speed_hrs",72),
                                             ("reply_word_count",3),("wish_sent",1),
                                             ("no_reply",1)]),
        ("urn_mim_004","Mim Chowdhury",    [("reply_speed_hrs",1),("reply_word_count",35),
                                             ("sentiment_score",5),("wish_sent",1),
                                             ("reply_speed_hrs",2),("reply_word_count",28),
                                             ("wish_sent",1),("reply_speed_hrs",1),
                                             ("reply_word_count",40),("wish_sent",1)]),
    ]
    for cid, cname, signals in contacts:
        for stype, val in signals:
            log_signal(cid, cname, stype, float(val))
        auto_adjust_tier(cid, cname, verbose=False)


# ── CLI self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_tiering_tables()
    _seed_demo()
    print("=== Relationship Tiering Auto-Adjust — self test ===\n")
    results = auto_adjust_all(verbose=True)
    print("\nFinal tiers:")
    for t in get_all_tiers():
        meta = TIERS.get(t["current_tier"], {})
        print(f"  {meta.get('emoji','')} {t['contact_name']:<22} "
              f"{t['current_tier']:<15} score={t['tier_score']}/100")
    print(f"\nChange log: {len(get_tier_change_log())} entries")

else:
    render_tiering_panel()


streamlit run relationship_tiering.py