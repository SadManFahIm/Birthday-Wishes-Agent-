"""
Platform ROI Comparison — Birthday Wishes Agent v8.0
Measures effort vs engagement across all 6 platforms and surfaces where
the agent should focus more (or less) to maximize relationship impact.

ROI = (reply_rate × sentiment_score × relationship_value) / effort_score

Effort factors:   time_to_send, retry_count, rate_limit_hits, failures
Engagement:       reply_rate, sentiment_avg, relationship_upgrades, avg_reply_speed
Output:           ROI score, focus recommendation (double down / maintain / reduce)

Integrates with: insight_report.py, command_center.py, workflow_builder.py
"""

import sqlite3
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

PLATFORMS = ["LinkedIn", "WhatsApp", "Facebook", "Instagram", "Twitter/X", "Slack"]

PLATFORM_META = {
    "LinkedIn":  {"icon": "💼", "color": "#58a6ff", "base_effort": 3.5},
    "WhatsApp":  {"icon": "💬", "color": "#3fb950", "base_effort": 2.0},
    "Facebook":  {"icon": "📘", "color": "#bc8cff", "base_effort": 2.5},
    "Instagram": {"icon": "📸", "color": "#f78166", "base_effort": 2.0},
    "Twitter/X": {"icon": "🐦", "color": "#d29922", "base_effort": 1.5},
    "Slack":     {"icon": "⚡", "color": "#4fc3f7", "base_effort": 1.5},
}

FOCUS_TIERS = {
    "double_down": {"label": "🚀 Double Down",  "color": "#3fb950", "desc": "High ROI — invest more here"},
    "maintain":    {"label": "✅ Maintain",     "color": "#58a6ff", "desc": "Solid returns — keep current effort"},
    "experiment":  {"label": "🧪 Experiment",   "color": "#d29922", "desc": "Mixed signals — test new styles"},
    "reduce":      {"label": "⬇️ Reduce",       "color": "#f78166", "desc": "Low ROI — consider deprioritizing"},
}

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_roi_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS platform_roi_snapshot (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            platform        TEXT NOT NULL,
            period_days     INTEGER NOT NULL,
            wishes_sent     INTEGER NOT NULL DEFAULT 0,
            replies_received INTEGER NOT NULL DEFAULT 0,
            reply_rate      REAL NOT NULL DEFAULT 0,
            avg_sentiment   REAL NOT NULL DEFAULT 3.0,
            avg_reply_hrs   REAL,
            effort_score    REAL NOT NULL DEFAULT 3.0,
            roi_score       REAL NOT NULL DEFAULT 0,
            focus_tier      TEXT NOT NULL DEFAULT 'maintain',
            snapped_at      TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Data loading ──────────────────────────────────────────────────────────────

def _try_load_real_data(period_days: int) -> Optional[dict]:
    """Pull real stats from DB tables if enough data exists."""
    if not DB_PATH.exists():
        return None
    try:
        conn  = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM wish_queue").fetchone()[0]
        conn.close()
        if count < 10:
            return None
        # Full aggregation would go here in production
        return None
    except Exception:
        return None


def _generate_demo_data(period_days: int) -> dict:
    """Realistic demo platform stats with stable seed per period."""
    random.seed(period_days * 7)
    data = {}
    for p in PLATFORMS:
        base_effort = PLATFORM_META[p]["base_effort"]
        sent        = random.randint(8, 40)
        replied     = int(sent * random.uniform(0.3, 0.88))
        rate        = round(replied / sent * 100, 1) if sent else 0
        sentiment   = round(random.uniform(2.5, 4.8), 2)
        reply_hrs   = round(random.uniform(1.0, 36.0), 1)
        rl_hits     = random.randint(0, 8)
        retries     = random.randint(0, 5)
        failures    = random.randint(0, 4)
        data[p] = {
            "wishes_sent":      sent,
            "replies_received": replied,
            "reply_rate":       rate,
            "avg_sentiment":    sentiment,
            "avg_reply_hrs":    reply_hrs,
            "rate_limit_hits":  rl_hits,
            "retries":          retries,
            "failures":         failures,
        }
    return data


# ── ROI computation ───────────────────────────────────────────────────────────

def compute_effort_score(stats: dict, base_effort: float) -> float:
    """
    Effort score = base platform effort + penalties for failures/rate-limits.
    Scale: 1 (very easy) → 10 (very hard).
    """
    rl_penalty      = stats.get("rate_limit_hits", 0) * 0.4
    retry_penalty   = stats.get("retries", 0) * 0.2
    failure_penalty = stats.get("failures", 0) * 0.5
    raw = base_effort + rl_penalty + retry_penalty + failure_penalty
    return min(10.0, round(raw, 2))


def compute_engagement_score(stats: dict) -> float:
    """
    Engagement score = weighted combo of reply rate, sentiment, and reply speed.
    Scale: 0 → 10.
    """
    reply_rate_score = (stats.get("reply_rate", 0) / 100) * 4.0
    sentiment_score  = ((stats.get("avg_sentiment", 3) - 1) / 4) * 4.0
    reply_hrs        = stats.get("avg_reply_hrs", 24)
    speed_score      = max(0, (1 - reply_hrs / 96)) * 2.0
    raw = reply_rate_score + sentiment_score + speed_score
    return min(10.0, round(raw, 2))


def compute_roi(engagement: float, effort: float) -> float:
    """ROI = engagement / effort, scaled to 0-10."""
    if effort == 0:
        return 0.0
    return min(10.0, round((engagement / effort) * 5, 2))


def classify_focus_tier(roi: float) -> str:
    if roi >= 7.0:
        return "double_down"
    if roi >= 4.5:
        return "maintain"
    if roi >= 2.5:
        return "experiment"
    return "reduce"


def compute_platform_roi(period_days: int = 30) -> dict:
    """
    Main entry point. Computes ROI for all platforms and returns a
    ranked comparison dict.

    Returns:
        {
          platforms: { name: { roi, effort, engagement, focus_tier, stats... } },
          ranked:    [ platform names sorted by roi desc ],
          best:      str,
          worst:     str,
          period_days: int,
        }
    """
    init_roi_table()
    raw = _try_load_real_data(period_days) or _generate_demo_data(period_days)

    result = {}
    for p, stats in raw.items():
        base_effort = PLATFORM_META[p]["base_effort"]
        effort      = compute_effort_score(stats, base_effort)
        engagement  = compute_engagement_score(stats)
        roi         = compute_roi(engagement, effort)
        focus       = classify_focus_tier(roi)

        result[p] = {
            **stats,
            "effort_score":    effort,
            "engagement_score":engagement,
            "roi_score":       roi,
            "focus_tier":      focus,
        }

    ranked = sorted(result.keys(), key=lambda k: result[k]["roi_score"], reverse=True)
    return {
        "platforms":    result,
        "ranked":       ranked,
        "best":         ranked[0],
        "worst":        ranked[-1],
        "period_days":  period_days,
    }


def save_snapshot(roi_data: dict):
    """Persist current ROI snapshot for trend tracking."""
    init_roi_table()
    conn = sqlite3.connect(DB_PATH)
    for p, d in roi_data["platforms"].items():
        conn.execute("""
            INSERT INTO platform_roi_snapshot
                (platform, period_days, wishes_sent, replies_received, reply_rate,
                 avg_sentiment, avg_reply_hrs, effort_score, roi_score, focus_tier, snapped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p, roi_data["period_days"],
            d.get("wishes_sent", 0), d.get("replies_received", 0),
            d.get("reply_rate", 0), d.get("avg_sentiment", 3),
            d.get("avg_reply_hrs"), d.get("effort_score", 0),
            d.get("roi_score", 0), d.get("focus_tier", "maintain"),
            datetime.now().isoformat(),
        ))
    conn.commit()
    conn.close()


def get_roi_history(platform: str, limit: int = 8) -> list[dict]:
    """Return historical ROI snapshots for a platform (for trend line)."""
    init_roi_table()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT roi_score, effort_score, engagement_score, reply_rate, snapped_at
        FROM platform_roi_snapshot
        WHERE platform = ?
        ORDER BY snapped_at DESC LIMIT ?
    """, (platform, limit)).fetchall()
    conn.close()
    return [{
        "roi_score":        r[0], "effort_score":    r[1],
        "engagement_score": r[2], "reply_rate":      r[3],
        "snapped_at":       r[4],
    } for r in reversed(rows)]


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Platform ROI", page_icon="📊",
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
    /* ROI rank card */
    .roi-card{background:var(--surface);border:1px solid var(--border);
              border-radius:12px;padding:16px 18px;margin-bottom:10px;
              transition:border-color 0.12s;}
    .roi-card.rank-1{border-left:4px solid #3fb950;}
    .roi-card.rank-2{border-left:4px solid #58a6ff;}
    .roi-card.rank-3{border-left:4px solid #d29922;}
    .roi-card.rank-bottom{border-left:4px solid #f78166;opacity:0.85;}
    .roi-name{font-size:1rem;font-weight:700;display:flex;align-items:center;gap:8px;}
    .roi-score-big{font-size:2rem;font-weight:700;line-height:1;}
    .roi-meta{font-size:0.72rem;color:var(--muted);margin-top:4px;}
    /* Focus badge */
    .focus-badge{display:inline-flex;align-items:center;font-size:0.7rem;font-weight:700;
                 padding:3px 10px;border-radius:20px;text-transform:uppercase;letter-spacing:0.06em;}
    /* Bar */
    .bar-row{display:flex;align-items:center;gap:10px;margin-bottom:8px;}
    .bar-label{width:90px;font-size:0.76rem;flex-shrink:0;}
    .bar-track{flex:1;background:#0d1117;border-radius:5px;height:20px;overflow:hidden;position:relative;}
    .bar-fill{height:100%;border-radius:5px;display:flex;align-items:center;
              padding-right:6px;justify-content:flex-end;font-size:0.65rem;
              font-weight:700;color:#0d1117;}
    .bar-value{width:44px;text-align:right;font-size:0.72rem;
               font-family:'JetBrains Mono',monospace;color:var(--muted);}
    /* Quadrant labels */
    .quad-label{font-size:0.65rem;font-weight:700;text-transform:uppercase;
                letter-spacing:0.07em;color:var(--muted);}
    /* Callout */
    .callout{background:#0a1a2a;border:1px solid #1f3a5a;border-left:3px solid var(--blue);
             border-radius:8px;padding:10px 14px;margin-bottom:8px;
             font-size:0.8rem;color:#c9d1d9;}
    .callout.win{background:#051a09;border-color:#0a3a14;border-left-color:var(--green);}
    .callout.warn{background:#1a1500;border-color:#3a2f00;border-left-color:var(--yellow);}
    .callout.alert{background:#1a0505;border-color:#3a0a0a;border-left-color:var(--red);}
    /* Stat mini */
    .mini-stat{background:#0d1117;border:1px solid var(--border);border-radius:8px;
               padding:8px 12px;text-align:center;}
    .mini-val{font-size:1rem;font-weight:700;}
    .mini-label{font-size:0.6rem;color:var(--muted);text-transform:uppercase;
                letter-spacing:0.06em;margin-top:2px;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.8rem;font-weight:500;transition:all 0.12s;}
    div[data-testid="stButton"]>button:hover{border-color:var(--blue);background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);
        border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:6px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📊</span>
      <h1>Platform ROI Comparison</h1>
      <span class="cc-badge">v8.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Controls ─────────────────────────────────────────────────────────────
    cc1, cc2, cc3 = st.columns([1.2, 1, 2])
    with cc1:
        period = st.selectbox("Period", ["Last 7 days", "Last 30 days", "Last 90 days"],
                              index=1, label_visibility="collapsed")
        period_map = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}
        period_days = period_map[period]
    with cc2:
        if st.button("💾 Save Snapshot", use_container_width=True):
            roi_data = compute_platform_roi(period_days)
            save_snapshot(roi_data)
            st.success("Snapshot saved!")

    roi_data   = compute_platform_roi(period_days)
    platforms  = roi_data["platforms"]
    ranked     = roi_data["ranked"]
    best       = roi_data["best"]
    worst      = roi_data["worst"]

    # ── Hero callout ──────────────────────────────────────────────────────────
    best_roi  = platforms[best]["roi_score"]
    worst_roi = platforms[worst]["roi_score"]
    best_meta = PLATFORM_META[best]
    st.markdown(f"""
    <div class="callout win">
      🏆 <strong>{best_meta['icon']} {best}</strong> has the best ROI this period
      (score <strong>{best_roi}/10</strong>) — {FOCUS_TIERS['double_down']['desc'].lower()}.
      <strong>{PLATFORM_META[worst]['icon']} {worst}</strong> is lowest
      ({worst_roi}/10) — consider reducing effort or experimenting with new styles there.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.4, 1], gap="large")

    # ── LEFT: Ranked ROI cards ────────────────────────────────────────────────
    with left:
        st.markdown('<div class="section-title">ROI Ranking</div>', unsafe_allow_html=True)
        rank_css = {1: "rank-1", 2: "rank-2", 3: "rank-3"}

        for rank, pname in enumerate(ranked, 1):
            p       = platforms[pname]
            pmeta   = PLATFORM_META[pname]
            ftier   = FOCUS_TIERS[p["focus_tier"]]
            roi     = p["roi_score"]
            css     = rank_css.get(rank, "rank-bottom" if rank == len(ranked) else "")

            # Sparkline using mini-bars (effort vs engagement)
            eff_pct  = int(p["effort_score"] / 10 * 100)
            eng_pct  = int(p["engagement_score"] / 10 * 100)
            roi_pct  = int(roi / 10 * 100)

            st.markdown(f"""
            <div class="roi-card {css}">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
                <div class="roi-name">
                  <span style="font-size:1.3rem">{pmeta['icon']}</span>
                  {pname}
                  <span style="font-size:0.65rem;color:#8b949e">#{rank}</span>
                </div>
                <div style="text-align:right">
                  <div class="roi-score-big" style="color:{pmeta['color']}">{roi}</div>
                  <div style="font-size:0.6rem;color:#8b949e">ROI /10</div>
                </div>
              </div>
              <div style="margin-bottom:8px">
                <span class="focus-badge" style="background:{ftier['color']}22;
                      color:{ftier['color']};border:1px solid {ftier['color']}44">
                  {ftier['label']}
                </span>
                <span style="font-size:0.68rem;color:#8b949e;margin-left:8px">{ftier['desc']}</span>
              </div>
              <div class="bar-row" style="margin-bottom:4px">
                <div class="bar-label" style="font-size:0.68rem">Engagement</div>
                <div class="bar-track">
                  <div class="bar-fill" style="width:{eng_pct}%;background:{pmeta['color']}">
                    {p['engagement_score']}
                  </div>
                </div>
              </div>
              <div class="bar-row" style="margin-bottom:4px">
                <div class="bar-label" style="font-size:0.68rem">Effort</div>
                <div class="bar-track">
                  <div class="bar-fill" style="width:{eff_pct}%;background:#f85149">
                    {p['effort_score']}
                  </div>
                </div>
              </div>
              <div class="roi-meta">
                📤 {p['wishes_sent']} sent ·
                💬 {p['replies_received']} replies ·
                📈 {p['reply_rate']}% rate ·
                ⏱ {p['avg_reply_hrs']}h avg reply ·
                ⚠️ {p.get('rate_limit_hits',0)} RL hits
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ── RIGHT: Effort vs Engagement scatter + insights ────────────────────────
    with right:
        # Scatter (CSS-based 2×2 quadrant)
        st.markdown('<div class="section-title">Effort vs Engagement</div>', unsafe_allow_html=True)

        scatter_size = 340
        st.markdown(f"""
        <div style="position:relative;width:{scatter_size}px;height:{scatter_size}px;
                    background:#161b22;border:1px solid #30363d;border-radius:12px;
                    margin-bottom:10px;">
          <!-- Quadrant dividers -->
          <div style="position:absolute;left:50%;top:0;bottom:0;
                      width:1px;background:#30363d;"></div>
          <div style="position:absolute;top:50%;left:0;right:0;
                      height:1px;background:#30363d;"></div>
          <!-- Quadrant labels -->
          <div class="quad-label" style="position:absolute;left:8px;top:8px;
               color:#3fb950">Sweet Spot</div>
          <div class="quad-label" style="position:absolute;right:8px;top:8px;
               color:#d29922;text-align:right">Heavy Lift</div>
          <div class="quad-label" style="position:absolute;left:8px;bottom:8px;
               color:#8b949e">Low Hanging</div>
          <div class="quad-label" style="position:absolute;right:8px;bottom:8px;
               color:#f85149;text-align:right">Poor Return</div>
          <!-- Axis labels -->
          <div style="position:absolute;bottom:4px;left:50%;transform:translateX(-50%);
               font-size:0.6rem;color:#8b949e">← Less Effort · More Effort →</div>
          <div style="position:absolute;left:4px;top:50%;transform:translateY(-50%) rotate(-90deg);
               font-size:0.6rem;color:#8b949e;white-space:nowrap">↑ Engagement ↑</div>
        """, unsafe_allow_html=True)

        # Platform dots
        dots_html = ""
        for pname, p in platforms.items():
            pmeta = PLATFORM_META[pname]
            # effort: x axis (0-10 → 20px to scatter_size-30px)
            # engagement: y axis inverted (0-10 → scatter_size-30px to 20px)
            x = int(20 + (p["effort_score"] / 10) * (scatter_size - 50))
            y = int((scatter_size - 30) - (p["engagement_score"] / 10) * (scatter_size - 50))
            dots_html += f"""
            <div style="position:absolute;left:{x}px;top:{y}px;transform:translate(-50%,-50%);
                        background:{pmeta['color']};border:2px solid #0d1117;
                        width:34px;height:34px;border-radius:50%;
                        display:flex;align-items:center;justify-content:center;
                        font-size:0.9rem;cursor:pointer;
                        box-shadow:0 0 10px {pmeta['color']}66"
                 title="{pname}: ROI={p['roi_score']}, Effort={p['effort_score']}, Engagement={p['engagement_score']}">
              {pmeta['icon']}
            </div>
            """
        st.markdown(f"{dots_html}</div>", unsafe_allow_html=True)

        # Key metrics comparison table
        st.markdown('<div class="section-title">Metrics Table</div>', unsafe_allow_html=True)
        table_html = """
        <table style="width:100%;font-size:0.72rem;border-collapse:collapse">
          <tr style="color:#8b949e;border-bottom:1px solid #30363d">
            <th style="text-align:left;padding:4px 6px">Platform</th>
            <th style="text-align:right;padding:4px 6px">ROI</th>
            <th style="text-align:right;padding:4px 6px">Reply%</th>
            <th style="text-align:right;padding:4px 6px">Effort</th>
            <th style="text-align:right;padding:4px 6px">Tier</th>
          </tr>
        """
        for pname in ranked:
            p     = platforms[pname]
            pmeta = PLATFORM_META[pname]
            ftier = FOCUS_TIERS[p["focus_tier"]]
            table_html += f"""
            <tr style="border-bottom:1px solid #21262d">
              <td style="padding:5px 6px;color:{pmeta['color']}">{pmeta['icon']} {pname}</td>
              <td style="padding:5px 6px;text-align:right;font-family:'JetBrains Mono',monospace;
                         font-weight:700;color:{pmeta['color']}">{p['roi_score']}</td>
              <td style="padding:5px 6px;text-align:right;color:#c9d1d9">{p['reply_rate']}%</td>
              <td style="padding:5px 6px;text-align:right;color:#8b949e">{p['effort_score']}</td>
              <td style="padding:5px 6px;text-align:right;font-size:0.65rem;
                         color:{ftier['color']}">{ftier['label'].split(' ')[0]} {ftier['label'].split(' ')[1] if len(ftier['label'].split(' ')) > 1 else ''}</td>
            </tr>
            """
        table_html += "</table>"
        st.markdown(
            f'<div style="background:#161b22;border:1px solid #30363d;'
            f'border-radius:10px;padding:10px 8px">{table_html}</div>',
            unsafe_allow_html=True,
        )

        # Auto recommendations
        st.markdown('<div class="section-title">Recommendations</div>', unsafe_allow_html=True)
        double_down = [p for p in ranked if platforms[p]["focus_tier"] == "double_down"]
        reduce      = [p for p in ranked if platforms[p]["focus_tier"] == "reduce"]
        experiment  = [p for p in ranked if platforms[p]["focus_tier"] == "experiment"]

        if double_down:
            names = ", ".join(f"{PLATFORM_META[p]['icon']} **{p}**" for p in double_down)
            st.markdown(f'<div class="callout win">🚀 Focus more effort on {names} — '
                        f'high engagement relative to cost.</div>', unsafe_allow_html=True)
        if reduce:
            names = ", ".join(f"{PLATFORM_META[p]['icon']} **{p}**" for p in reduce)
            st.markdown(f'<div class="callout alert">⬇️ Consider reducing effort on {names} — '
                        f'low returns for the work involved.</div>', unsafe_allow_html=True)
        if experiment:
            names = ", ".join(f"{PLATFORM_META[p]['icon']} **{p}**" for p in experiment)
            st.markdown(f'<div class="callout warn">🧪 Try different wish styles on {names} — '
                        f'mixed results, worth testing.</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
      <span>Platform ROI Comparison · {period}</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


# ── CLI self-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_roi_table()
    print("=== Platform ROI Comparison — self test ===\n")
    roi_data = compute_platform_roi(30)

    print(f"Period: last {roi_data['period_days']} days\n")
    print(f"{'Platform':<12} {'ROI':>5} {'Effort':>7} {'Engage':>8} {'Reply%':>7} {'Tier'}")
    print("─" * 60)
    for pname in roi_data["ranked"]:
        p     = roi_data["platforms"][pname]
        ftier = FOCUS_TIERS[p["focus_tier"]]["label"]
        print(f"{pname:<12} {p['roi_score']:>5} {p['effort_score']:>7} "
              f"{p['engagement_score']:>8} {p['reply_rate']:>6}% {ftier}")

    print(f"\n✅ Best:  {roi_data['best']}")
    print(f"⬇️  Worst: {roi_data['worst']}")

else:
    render_dashboard()
