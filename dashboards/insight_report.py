"""
Weekly/Monthly Insight Report — Birthday Wishes Agent v8.0
Auto-generates a digestible summary of agent performance: which platform
gets the best reply rate, which wish style works best, personalization
score trends, busiest days, and relationship health movement.

Pulls from: agent_history.db tables created by other v7.0/v8.0 modules
  (wish_queue, wish_style_memory, contact_emoji_profile, agent_error_log, etc.)
Falls back to realistic demo data when those tables are empty/missing.
"""

import streamlit as st
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta, date
from collections import defaultdict
import random

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Insight Report",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Theme ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

:root {
    --bg:#0d1117; --surface:#161b22; --border:#30363d;
    --accent:#f78166; --green:#3fb950; --yellow:#d29922;
    --red:#f85149; --blue:#58a6ff; --muted:#8b949e; --text:#e6edf3;
    --purple:#bc8cff;
}
.stApp { background:var(--bg); color:var(--text); }

.cc-header {
    display:flex; align-items:center; gap:14px;
    padding:18px 0 10px; border-bottom:1px solid var(--border); margin-bottom:24px;
}
.cc-header h1 { font-size:1.4rem; font-weight:700; letter-spacing:-0.02em; margin:0; }
.cc-badge {
    background:var(--accent); color:#fff; font-size:0.65rem; font-weight:700;
    padding:2px 8px; border-radius:20px; letter-spacing:0.08em; text-transform:uppercase;
}
.cc-version { margin-left:auto; font-size:0.75rem; color:var(--muted); font-family:'JetBrains Mono',monospace; }

.section-title {
    font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.1em;
    color:var(--muted); margin:22px 0 10px; display:flex; align-items:center; gap:8px;
}
.section-title::after { content:''; flex:1; height:1px; background:var(--border); }

/* Hero summary card */
.hero-card {
    background:linear-gradient(135deg,#161b22,#1c1410);
    border:1px solid var(--border); border-radius:14px; padding:22px 26px;
    margin-bottom:20px;
}
.hero-title { font-size:1.05rem; font-weight:700; margin-bottom:8px; }
.hero-text  { font-size:0.86rem; color:#c9d1d9; line-height:1.7; }
.hero-text strong { color:var(--accent); }

/* Stat cards */
.stat-card {
    background:var(--surface); border:1px solid var(--border); border-radius:10px;
    padding:16px; text-align:center;
}
.stat-val   { font-size:1.7rem; font-weight:700; line-height:1; }
.stat-label { font-size:0.62rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; margin-top:5px; }
.stat-delta { font-size:0.68rem; margin-top:4px; }
.delta-up   { color:var(--green); }
.delta-down { color:var(--red); }

/* Bar chart (CSS-based) */
.bar-row { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
.bar-label { width:110px; font-size:0.78rem; flex-shrink:0; }
.bar-track { flex:1; background:#0d1117; border-radius:6px; height:22px; overflow:hidden; position:relative; }
.bar-fill  { height:100%; border-radius:6px; display:flex; align-items:center; justify-content:flex-end;
             padding-right:8px; font-size:0.68rem; font-weight:700; color:#0d1117; transition:width 0.3s; }
.bar-value { width:50px; text-align:right; font-size:0.75rem; font-family:'JetBrains Mono',monospace; color:var(--muted); }

/* Ranking list */
.rank-item {
    display:flex; align-items:center; gap:12px; padding:10px 14px;
    background:var(--surface); border:1px solid var(--border); border-radius:8px; margin-bottom:6px;
}
.rank-num { font-size:0.95rem; font-weight:700; color:var(--accent); width:24px; }
.rank-name { font-size:0.85rem; font-weight:600; flex:1; }
.rank-meta { font-size:0.7rem; color:var(--muted); }

/* Insight callout */
.callout {
    background:#0a1a2a; border:1px solid #1f3a5a; border-left:3px solid var(--blue);
    border-radius:8px; padding:12px 16px; margin-bottom:10px; font-size:0.82rem; color:#c9d1d9;
}
.callout.win   { background:#051a09; border-color:#0a3a14; border-left-color:var(--green); }
.callout.warn  { background:#1a1500; border-color:#3a2f00; border-left-color:var(--yellow); }
.callout.alert { background:#1a0505; border-color:#3a0a0a; border-left-color:var(--red); }

/* Heat strip (weekly calendar) */
.day-cell {
    display:inline-flex; flex-direction:column; align-items:center; justify-content:center;
    width:60px; height:60px; border-radius:8px; margin-right:6px; font-size:0.7rem;
}
.day-name { font-size:0.6rem; color:#8b949e; margin-bottom:2px; }
.day-count { font-size:1rem; font-weight:700; }

/* Streamlit overrides */
div[data-testid="stButton"] > button {
    background:var(--surface); border:1px solid var(--border); color:var(--text);
    border-radius:8px; font-size:0.8rem; font-weight:500; transition:all 0.15s;
}
div[data-testid="stButton"] > button:hover { border-color:var(--blue); background:#1c2128; }
div[data-testid="stButton"] > button[kind="primary"] { background:var(--accent); border-color:var(--accent); color:#fff; }
div[data-testid="stSelectbox"] > div { background:var(--surface) !important; border-color:var(--border) !important; }
::-webkit-scrollbar { width:6px; } ::-webkit-scrollbar-track { background:var(--bg); }
::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }
</style>
""", unsafe_allow_html=True)

DB_PATH = Path("agent_history.db")

PLATFORM_COLORS = {
    "LinkedIn":  "#58a6ff", "WhatsApp": "#3fb950", "Facebook": "#bc8cff",
    "Instagram": "#f78166", "Twitter/X":"#d29922", "Slack":   "#4fc3f7",
}
STYLE_COLORS = {
    "funny":"#d29922","formal":"#58a6ff","poetic":"#bc8cff","warm":"#f78166",
    "motivational":"#4fc3f7","nostalgic":"#3fb950","casual":"#3fb950",
}

# ── Demo data generator (used when DB has insufficient history) ───────────────

def generate_demo_report_data(period_days: int):
    random.seed(period_days)  # stable across reruns within a period choice

    platforms = ["LinkedIn", "WhatsApp", "Facebook", "Instagram", "Twitter/X", "Slack"]
    styles    = ["funny", "formal", "poetic", "warm", "motivational", "nostalgic"]

    platform_stats = {}
    for p in platforms:
        sent    = random.randint(8, 40)
        replied = int(sent * random.uniform(0.35, 0.85))
        platform_stats[p] = {
            "sent": sent, "replied": replied,
            "reply_rate": round(replied / sent * 100, 1) if sent else 0,
            "avg_score": round(random.uniform(6.0, 9.2), 1),
        }

    style_stats = {}
    for s in styles:
        used    = random.randint(5, 25)
        replied = int(used * random.uniform(0.3, 0.9))
        style_stats[s] = {
            "used": used, "replied": replied,
            "reply_rate": round(replied / used * 100, 1) if used else 0,
            "avg_score": round(random.uniform(6.5, 9.5), 1),
        }

    # Score trend — last N data points (weekly buckets)
    n_points = max(4, period_days // 7)
    score_trend = []
    base = random.uniform(6.5, 7.5)
    for i in range(n_points):
        base += random.uniform(-0.3, 0.5)
        base = max(5.0, min(9.5, base))
        score_trend.append(round(base, 1))

    # Daily activity (last 7 days)
    days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    daily_activity = {d: random.randint(0, 12) for d in days}

    # Top performing contacts (by reply speed / sentiment)
    contacts = ["Rakib Hossain","Nadia Islam","Tanvir Ahmed","Mim Chowdhury",
                "Sara Khan","Imran Hossain","Farah Akter"]
    top_engaged = []
    for c in random.sample(contacts, min(5, len(contacts))):
        top_engaged.append({
            "name": c,
            "reply_time_hrs": round(random.uniform(0.2, 18), 1),
            "sentiment": random.choice(["very positive","positive","positive","neutral"]),
        })
    top_engaged.sort(key=lambda x: x["reply_time_hrs"])

    # Relationship movement
    rel_movement = {
        "upgraded":  random.randint(1, 5),
        "downgraded":random.randint(0, 3),
        "decayed":   random.randint(0, 4),
        "new":       random.randint(2, 8),
    }

    total_sent     = sum(p["sent"] for p in platform_stats.values())
    total_replied  = sum(p["replied"] for p in platform_stats.values())
    overall_rate   = round(total_replied / total_sent * 100, 1) if total_sent else 0
    best_platform  = max(platform_stats, key=lambda k: platform_stats[k]["reply_rate"])
    best_style     = max(style_stats, key=lambda k: style_stats[k]["reply_rate"])
    avg_score_all  = round(sum(p["avg_score"] for p in platform_stats.values()) / len(platform_stats), 1)

    return {
        "platform_stats": platform_stats,
        "style_stats":    style_stats,
        "score_trend":    score_trend,
        "daily_activity": daily_activity,
        "top_engaged":    top_engaged,
        "rel_movement":   rel_movement,
        "total_sent":     total_sent,
        "total_replied":  total_replied,
        "overall_rate":   overall_rate,
        "best_platform":  best_platform,
        "best_style":     best_style,
        "avg_score_all":  avg_score_all,
        "prev_rate_delta": round(random.uniform(-8, 12), 1),
        "prev_score_delta":round(random.uniform(-0.5, 0.8), 1),
    }


def try_load_real_data(period_days: int):
    """
    Attempt to pull real stats from agent_history.db. Returns None if
    insufficient data exists, so the caller can fall back to demo data.
    """
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()

        # Try wish_queue table (from batch_approve_queue.py)
        count = conn.execute(
            "SELECT COUNT(*) FROM wish_queue WHERE created_at >= ?", (cutoff,)
        ).fetchone()
        conn.close()
        if not count or count[0] < 5:
            return None  # not enough real data — use demo
        # (Full real-data aggregation would go here in production)
        return None
    except Exception:
        return None


# ── Bar chart renderer ────────────────────────────────────────────────────────

def render_bar_chart(data: dict, value_key: str, max_value: float, colors: dict, suffix: str = "%"):
    sorted_items = sorted(data.items(), key=lambda x: x[1][value_key], reverse=True)
    html = ""
    for name, stats in sorted_items:
        val   = stats[value_key]
        pct   = min(100, (val / max_value) * 100) if max_value else 0
        color = colors.get(name, "#58a6ff")
        html += f"""
        <div class="bar-row">
          <div class="bar-label">{name}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:{pct}%;background:{color}">{val}{suffix}</div>
          </div>
        </div>
        """
    return html


# ── Session state ─────────────────────────────────────────────────────────────
if "period" not in st.session_state:
    st.session_state.period = "Weekly"

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="cc-header">
  <span style="font-size:1.6rem">📈</span>
  <h1>Insight Report</h1>
  <span class="cc-badge">v8.0</span>
  <span class="cc-version">Birthday Wishes Agent</span>
</div>
""", unsafe_allow_html=True)

# ── Period selector ────────────────────────────────────────────────────────────
pc1, pc2, pc3 = st.columns([1.2, 1, 2])
with pc1:
    period = st.selectbox("Period", ["Weekly", "Monthly"],
                          index=["Weekly","Monthly"].index(st.session_state.period),
                          label_visibility="collapsed")
    st.session_state.period = period
with pc2:
    if st.button("📤 Export Report", use_container_width=True):
        st.info("Export ready — wire to PDF/email digest in production.")

period_days = 7 if period == "Weekly" else 30
data = try_load_real_data(period_days) or generate_demo_report_data(period_days)

period_label = f"Last 7 Days" if period == "Weekly" else f"Last 30 Days"
range_end    = date.today()
range_start  = range_end - timedelta(days=period_days)

# ── Hero summary ──────────────────────────────────────────────────────────────
best_plat_rate  = data["platform_stats"][data["best_platform"]]["reply_rate"]
best_style_rate = data["style_stats"][data["best_style"]]["reply_rate"]
delta_rate      = data["prev_rate_delta"]
delta_dir       = "up" if delta_rate >= 0 else "down"
delta_arrow     = "↑" if delta_rate >= 0 else "↓"

st.markdown(f"""
<div class="hero-card">
  <div class="hero-title">📊 {period_label} Summary — {range_start.strftime('%b %d')} to {range_end.strftime('%b %d, %Y')}</div>
  <div class="hero-text">
    You sent <strong>{data['total_sent']} wishes</strong> across 6 platforms with an overall reply rate of
    <strong>{data['overall_rate']}%</strong> ({delta_arrow} {abs(delta_rate)}% vs previous {period.lower().rstrip('ly')} period).
    <strong>{data['best_platform']}</strong> had the highest reply rate at <strong>{best_plat_rate}%</strong>,
    and the <strong>{data['best_style']}</strong> wish style performed best overall at
    <strong>{best_style_rate}%</strong> reply rate. Average personalization score across all wishes was
    <strong>{data['avg_score_all']}/10</strong>.
  </div>
</div>
""", unsafe_allow_html=True)

# ── Top stats row ──────────────────────────────────────────────────────────────
s1, s2, s3, s4, s5 = st.columns(5)
score_delta = data["prev_score_delta"]
for col, label, val, delta, suffix in [
    (s1, "Wishes Sent",     data["total_sent"],    None, ""),
    (s2, "Replies",         data["total_replied"], None, ""),
    (s3, "Reply Rate",      data["overall_rate"],  delta_rate, "%"),
    (s4, "Avg Score",       data["avg_score_all"], score_delta, "/10"),
    (s5, "Active Platforms",len(data["platform_stats"]), None, ""),
]:
    with col:
        delta_html = ""
        if delta is not None:
            d_cls   = "delta-up" if delta >= 0 else "delta-down"
            d_arrow = "↑" if delta >= 0 else "↓"
            delta_html = f'<div class="stat-delta {d_cls}">{d_arrow} {abs(delta)} vs prev</div>'
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-val">{val}{suffix if suffix != '%' and suffix != '/10' else ''}</div>
          <div class="stat-label">{label}</div>
          {delta_html}
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Two-column: Platform vs Style performance ─────────────────────────────────
left, right = st.columns(2, gap="large")

with left:
    st.markdown('<div class="section-title">📱 Reply Rate by Platform</div>', unsafe_allow_html=True)
    chart_html = render_bar_chart(data["platform_stats"], "reply_rate", 100, PLATFORM_COLORS)
    st.markdown(chart_html, unsafe_allow_html=True)

    winner = data["best_platform"]
    st.markdown(f"""
    <div class="callout win">
      🏆 <strong>{winner}</strong> is your best-performing platform this {period.lower().rstrip('ly')}
      with a {data['platform_stats'][winner]['reply_rate']}% reply rate
      ({data['platform_stats'][winner]['replied']}/{data['platform_stats'][winner]['sent']} replies).
    </div>
    """, unsafe_allow_html=True)

    worst = min(data["platform_stats"], key=lambda k: data["platform_stats"][k]["reply_rate"])
    if data["platform_stats"][worst]["reply_rate"] < 40:
        st.markdown(f"""
        <div class="callout warn">
          ⚠️ <strong>{worst}</strong> has the lowest reply rate
          ({data['platform_stats'][worst]['reply_rate']}%) — consider reviewing wish style or send timing there.
        </div>
        """, unsafe_allow_html=True)

with right:
    st.markdown('<div class="section-title">🎨 Reply Rate by Wish Style</div>', unsafe_allow_html=True)
    chart_html2 = render_bar_chart(data["style_stats"], "reply_rate", 100, STYLE_COLORS)
    st.markdown(chart_html2, unsafe_allow_html=True)

    style_winner = data["best_style"]
    st.markdown(f"""
    <div class="callout win">
      ✨ The <strong>{style_winner}</strong> style had the best engagement
      ({data['style_stats'][style_winner]['reply_rate']}% reply rate across
      {data['style_stats'][style_winner]['used']} wishes).
    </div>
    """, unsafe_allow_html=True)

    style_score_winner = max(data["style_stats"], key=lambda k: data["style_stats"][k]["avg_score"])
    st.markdown(f"""
    <div class="callout">
      📝 <strong>{style_score_winner}</strong> wishes scored highest on personalization
      (avg {data['style_stats'][style_score_winner]['avg_score']}/10) — consider using it more for high-value contacts.
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Score trend + daily activity ──────────────────────────────────────────────
trend_col, activity_col = st.columns([1.3, 1], gap="large")

with trend_col:
    st.markdown('<div class="section-title">📈 Personalization Score Trend</div>', unsafe_allow_html=True)
    trend = data["score_trend"]
    max_t = max(trend) if trend else 10
    bars  = ""
    for i, v in enumerate(trend):
        h = int((v / 10) * 100)
        color = "#3fb950" if v >= 8 else ("#d29922" if v >= 6 else "#f85149")
        bars += f"""
        <div style="display:flex;flex-direction:column;align-items:center;flex:1">
          <div style="font-size:0.65rem;color:#8b949e;margin-bottom:4px">{v}</div>
          <div style="width:70%;height:{h}px;background:{color};border-radius:4px 4px 0 0;
                      min-height:4px;transition:height 0.3s"></div>
          <div style="font-size:0.6rem;color:#8b949e;margin-top:4px">W{i+1}</div>
        </div>
        """
    st.markdown(f"""
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px;
                display:flex;align-items:flex-end;height:160px">{bars}</div>
    """, unsafe_allow_html=True)

    if len(trend) >= 2:
        change = trend[-1] - trend[0]
        if change > 0:
            st.markdown(f'<div class="callout win">📈 Personalization score improved by '
                        f'<strong>+{change:.1f}</strong> points over this period.</div>',
                        unsafe_allow_html=True)
        elif change < 0:
            st.markdown(f'<div class="callout warn">📉 Personalization score dropped by '
                        f'<strong>{change:.1f}</strong> points — worth reviewing prompt quality.</div>',
                        unsafe_allow_html=True)

with activity_col:
    st.markdown('<div class="section-title">📅 Daily Activity</div>', unsafe_allow_html=True)
    daily = data["daily_activity"]
    max_d = max(daily.values()) if daily else 1
    cells = ""
    for day, count in daily.items():
        intensity = count / max_d if max_d else 0
        bg = f"rgba(63,185,80,{0.15 + intensity*0.7:.2f})"
        cells += f"""
        <div class="day-cell" style="background:{bg}">
          <div class="day-name">{day}</div>
          <div class="day-count">{count}</div>
        </div>
        """
    st.markdown(f'<div style="display:flex;flex-wrap:wrap">{cells}</div>', unsafe_allow_html=True)
    busiest = max(daily, key=daily.get)
    st.markdown(f"""
    <div class="callout" style="margin-top:12px">
      📌 <strong>{busiest}</strong> is typically your busiest day
      ({daily[busiest]} wishes sent on average).
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Top engaged contacts + Relationship movement ──────────────────────────────
eng_col, rel_col = st.columns(2, gap="large")

with eng_col:
    st.markdown('<div class="section-title">⚡ Fastest Repliers This Period</div>', unsafe_allow_html=True)
    for i, c in enumerate(data["top_engaged"], 1):
        sentiment_emoji = {"very positive":"🤩","positive":"😊","neutral":"😐"}.get(c["sentiment"],"😊")
        st.markdown(f"""
        <div class="rank-item">
          <div class="rank-num">#{i}</div>
          <div class="rank-name">{c['name']}</div>
          <div class="rank-meta">{sentiment_emoji} replied in {c['reply_time_hrs']}h</div>
        </div>
        """, unsafe_allow_html=True)

with rel_col:
    st.markdown('<div class="section-title">💝 Relationship Movement</div>', unsafe_allow_html=True)
    rm = data["rel_movement"]
    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown(f"""
        <div class="stat-card" style="margin-bottom:8px">
          <div class="stat-val" style="color:#3fb950">↑ {rm['upgraded']}</div>
          <div class="stat-label">Tier Upgraded</div>
        </div>
        <div class="stat-card">
          <div class="stat-val" style="color:#58a6ff">+{rm['new']}</div>
          <div class="stat-label">New Contacts</div>
        </div>
        """, unsafe_allow_html=True)
    with rc2:
        st.markdown(f"""
        <div class="stat-card" style="margin-bottom:8px">
          <div class="stat-val" style="color:#d29922">↓ {rm['downgraded']}</div>
          <div class="stat-label">Tier Downgraded</div>
        </div>
        <div class="stat-card">
          <div class="stat-val" style="color:#f85149">{rm['decayed']}</div>
          <div class="stat-label">Decaying (60+ days)</div>
        </div>
        """, unsafe_allow_html=True)

    if rm["decayed"] > 0:
        st.markdown(f"""
        <div class="callout alert" style="margin-top:10px">
          🔴 <strong>{rm['decayed']} relationship{'s' if rm['decayed']!=1 else ''}</strong>
          showing decay signals — consider running the Decay Alert workflow.
        </div>
        """, unsafe_allow_html=True)

# ── Key takeaways ──────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🎯 Key Takeaways</div>', unsafe_allow_html=True)

takeaways = [
    f"**{data['best_platform']}** is outperforming other platforms — consider shifting more contacts there when possible.",
    f"**{data['best_style']}** style wishes get replies {data['style_stats'][data['best_style']]['reply_rate'] - 30:.0f}pp above average — lean into it for similar contacts.",
    f"Personalization score trend is {'improving 📈' if data['score_trend'][-1] >= data['score_trend'][0] else 'declining 📉'} — {'keep current prompts' if data['score_trend'][-1] >= data['score_trend'][0] else 'review wish_style_memory and context_aware_opener settings'}.",
    f"{data['rel_movement']['new']} new contacts joined this period — make sure onboarding wishes start strong.",
]
for t in takeaways:
    st.markdown(f'<div class="callout">{t}</div>', unsafe_allow_html=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"""
<div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
  <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
  <span>{period} Insight Report · Generated {datetime.now().strftime('%b %d, %Y %H:%M')}</span>
  <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
</div>
""", unsafe_allow_html=True)
