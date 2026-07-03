"""
Personalization Score Trend — Birthday Wishes Agent v8.0
Tracks wish personalization scores (1-10) over time per contact and in aggregate,
showing whether quality is improving, plateauing, or declining.
"""

import sqlite3
import json
import random
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Optional

DB_PATH = Path("agent_history.db")

SCORE_COMPONENTS = {
    "name_mentioned":  {"label": "Name mentioned",      "max": 2},
    "job_company_ref": {"label": "Job/company ref",     "max": 2},
    "industry_ref":    {"label": "Industry ref",        "max": 1},
    "memory_context":  {"label": "Memory/past context", "max": 2},
    "unique_language": {"label": "Unique language",     "max": 1},
    "right_length":    {"label": "Right length",        "max": 1},
    "warm_tone":       {"label": "Warm tone",           "max": 1},
}
MAX_SCORE = sum(v["max"] for v in SCORE_COMPONENTS.values())  # 10

TREND_LABELS = {
    "improving": {"icon": "📈", "color": "#3fb950", "label": "Improving"},
    "stable":    {"icon": "➡️", "color": "#58a6ff", "label": "Stable"},
    "declining": {"icon": "📉", "color": "#f85149", "label": "Declining"},
    "plateau":   {"icon": "〰️", "color": "#d29922", "label": "Plateau"},
    "no_data":   {"icon": "—",  "color": "#8b949e", "label": "No data"},
}

PLAT_COLORS  = {"LinkedIn":"#58a6ff","WhatsApp":"#3fb950","Facebook":"#bc8cff",
                "Instagram":"#f78166","Twitter/X":"#d29922","Slack":"#4fc3f7"}
STYLE_COLORS = {"funny":"#d29922","formal":"#58a6ff","poetic":"#bc8cff",
                "warm":"#f78166","motivational":"#4fc3f7","nostalgic":"#3fb950","casual":"#3fb950"}

# ── DB ────────────────────────────────────────────────────────────────────────

def init_score_trend_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wish_score_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            platform        TEXT NOT NULL,
            style           TEXT,
            total_score     INTEGER NOT NULL,
            components_json TEXT,
            wish_date       TEXT NOT NULL,
            logged_at       TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ── Public API ────────────────────────────────────────────────────────────────

def log_wish_score(contact_id, contact_name, platform, total_score,
                   components=None, style=None, wish_date=None):
    init_score_trend_table()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO wish_score_history
            (contact_id, contact_name, platform, style, total_score,
             components_json, wish_date, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, platform, style,
          min(MAX_SCORE, max(0, total_score)),
          json.dumps(components or {}),
          wish_date or date.today().isoformat(),
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_aggregate_trend(period_days=90, bucket="month"):
    init_score_trend_table()
    cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
    fmt    = "%Y-W%W" if bucket == "week" else "%Y-%m"
    conn   = sqlite3.connect(DB_PATH)
    rows   = conn.execute(f"""
        SELECT strftime('{fmt}', wish_date) as b,
               AVG(total_score), COUNT(*), MIN(total_score), MAX(total_score)
        FROM wish_score_history WHERE logged_at >= ?
        GROUP BY b ORDER BY b ASC
    """, (cutoff,)).fetchall()
    conn.close()
    return [{"bucket": r[0], "avg_score": round(r[1],2),
             "count": r[2], "min": r[3], "max": r[4]} for r in rows]


def get_contact_trend(contact_id, limit=12):
    init_score_trend_table()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT total_score, style, platform, components_json, wish_date
        FROM wish_score_history WHERE contact_id = ?
        ORDER BY wish_date ASC LIMIT ?
    """, (contact_id, limit)).fetchall()
    conn.close()
    return [{"score": r[0], "style": r[1], "platform": r[2],
             "components": json.loads(r[3] or "{}"), "wish_date": r[4]} for r in rows]


def get_by_platform(period_days=90):
    init_score_trend_table()
    cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    rows   = conn.execute("""
        SELECT platform, AVG(total_score), COUNT(*)
        FROM wish_score_history WHERE logged_at >= ?
        GROUP BY platform ORDER BY AVG(total_score) DESC
    """, (cutoff,)).fetchall()
    conn.close()
    return {r[0]: {"avg": round(r[1],2), "count": r[2]} for r in rows}


def get_by_style(period_days=90):
    init_score_trend_table()
    cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    rows   = conn.execute("""
        SELECT style, AVG(total_score), COUNT(*)
        FROM wish_score_history
        WHERE logged_at >= ? AND style IS NOT NULL
        GROUP BY style ORDER BY AVG(total_score) DESC
    """, (cutoff,)).fetchall()
    conn.close()
    return {r[0]: {"avg": round(r[1],2), "count": r[2]} for r in rows}


def get_component_breakdown(period_days=90):
    init_score_trend_table()
    cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    rows   = conn.execute("""
        SELECT components_json FROM wish_score_history
        WHERE logged_at >= ? AND components_json != '{}'
    """, (cutoff,)).fetchall()
    conn.close()
    totals = {k: 0 for k in SCORE_COMPONENTS}
    count  = 0
    for (raw,) in rows:
        try:
            comp = json.loads(raw)
            for k in SCORE_COMPONENTS:
                totals[k] += comp.get(k, 0)
            count += 1
        except Exception:
            pass
    if count == 0:
        return {k: 0.0 for k in SCORE_COMPONENTS}
    return {k: round(totals[k]/count, 2) for k in SCORE_COMPONENTS}


def classify_trend(scores):
    if len(scores) < 2:
        return "no_data"
    delta    = scores[-1] - scores[0]
    variance = max(scores) - min(scores)
    if abs(delta) < 0.3 and variance < 0.8:
        return "plateau"
    if delta > 0.5:
        return "improving"
    if delta < -0.5:
        return "declining"
    return "stable"


def get_all_contact_summaries():
    init_score_trend_table()
    conn = sqlite3.connect(DB_PATH)
    ids  = conn.execute(
        "SELECT DISTINCT contact_id, contact_name FROM wish_score_history"
    ).fetchall()
    conn.close()
    result = []
    for cid, cname in ids:
        history = get_contact_trend(cid, limit=8)
        scores  = [h["score"] for h in history]
        trend   = classify_trend(scores)
        result.append({
            "contact_id":   cid, "contact_name": cname,
            "latest_score": scores[-1] if scores else 0,
            "avg_score":    round(sum(scores)/len(scores),1) if scores else 0,
            "wish_count":   len(scores), "trend": trend,
        })
    result.sort(key=lambda x: x["avg_score"], reverse=True)
    return result

# ── Demo seeder ───────────────────────────────────────────────────────────────

def seed_demo_scores():
    init_score_trend_table()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM wish_score_history").fetchone()[0]
    conn.close()
    if count > 0:
        return
    random.seed(99)
    contacts = [
        ("urn_rakib_001","Rakib Hossain","LinkedIn","casual"),
        ("urn_nadia_002","Nadia Islam","WhatsApp","warm"),
        ("urn_tanvir_003","Tanvir Ahmed","LinkedIn","formal"),
        ("urn_mim_004","Mim Chowdhury","WhatsApp","funny"),
        ("urn_imran_006","Imran Hossain","Slack","motivational"),
        ("urn_sara_005","Sara Khan","LinkedIn","poetic"),
    ]
    styles    = list(STYLE_COLORS.keys())
    platforms = list(PLAT_COLORS.keys())
    now       = datetime.now()
    for cid, cname, plat, base_style in contacts:
        base = random.uniform(5.0, 7.5)
        for mo in range(11, -1, -1):
            base      += random.uniform(-0.3, 0.6)
            base       = max(3.0, min(10.0, base))
            score      = round(base)
            wish_date  = (now - timedelta(days=mo*30)).date().isoformat()
            logged_at  = (now - timedelta(days=mo*30)).isoformat()
            comps, rem = {}, score
            for k, m in SCORE_COMPONENTS.items():
                pts = min(m["max"], rem)
                comps[k] = pts
                rem -= pts
                if rem <= 0:
                    break
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                INSERT INTO wish_score_history
                    (contact_id,contact_name,platform,style,total_score,
                     components_json,wish_date,logged_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (cid, cname,
                  random.choice(platforms) if mo%3==0 else plat,
                  random.choice(styles)    if mo%4==0 else base_style,
                  score, json.dumps(comps), wish_date, logged_at))
            conn.commit()
            conn.close()

# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Score Trend", page_icon="📈",
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
    .chart-wrap{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:16px 14px;position:relative;}
    .chart-area{display:flex;align-items:flex-end;gap:4px;height:120px;}
    .chart-col{flex:1;display:flex;flex-direction:column;align-items:center;}
    .chart-bar{width:100%;border-radius:4px 4px 0 0;min-height:3px;}
    .chart-label{font-size:0.55rem;color:#8b949e;margin-top:3px;text-align:center;}
    .chart-val{font-size:0.58rem;color:#8b949e;margin-bottom:2px;}
    .c-card{background:var(--surface);border:1px solid var(--border);border-radius:9px;
            padding:10px 13px;margin-bottom:6px;}
    .c-name{font-weight:700;font-size:0.84rem;display:flex;align-items:center;gap:6px;}
    .c-meta{font-size:0.68rem;color:var(--muted);margin-top:2px;}
    .trend-chip{display:inline-flex;align-items:center;gap:4px;font-size:0.62rem;
                font-weight:700;padding:2px 7px;border-radius:20px;text-transform:uppercase;letter-spacing:0.06em;}
    .spark{display:inline-flex;align-items:flex-end;gap:2px;height:22px;vertical-align:middle;margin-left:6px;}
    .spark-bar{width:5px;border-radius:2px 2px 0 0;min-height:2px;}
    .comp-row{display:flex;align-items:center;gap:8px;margin-bottom:7px;}
    .comp-label{width:128px;font-size:0.72rem;flex-shrink:0;}
    .comp-track{flex:1;background:#0d1117;border-radius:4px;height:16px;overflow:hidden;}
    .comp-fill{height:100%;border-radius:4px;}
    .comp-val{width:36px;text-align:right;font-size:0.68rem;font-family:'JetBrains Mono',monospace;color:var(--muted);}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:10px 14px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.07em;margin-top:3px;}
    .callout{background:#0a1a2a;border-left:3px solid var(--blue);border-radius:7px;
             padding:9px 13px;margin-bottom:7px;font-size:0.79rem;color:#c9d1d9;}
    .callout.win{background:#051a09;border-left-color:var(--green);}
    .callout.warn{background:#1a1500;border-left-color:var(--yellow);}
    .callout.alert{background:#1a0505;border-left-color:var(--red);}
    div[data-testid="stButton"]>button{background:var(--surface);border:1px solid var(--border);
        color:var(--text);border-radius:8px;font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:var(--blue);background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    seed_demo_scores()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📈</span>
      <h1>Personalization Score Trend</h1>
      <span class="cc-badge">v8.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    cc1, cc2 = st.columns([1, 1])
    with cc1:
        period_opt = st.selectbox("Period", ["3 months","6 months","12 months"],
                                  index=2, label_visibility="collapsed")
    with cc2:
        bucket = st.selectbox("Bucket", ["week","month"], index=1, label_visibility="collapsed")
    period_map = {"3 months":90,"6 months":180,"12 months":365}
    period_days = period_map[period_opt]

    agg_trend   = get_aggregate_trend(period_days, bucket)
    by_platform = get_by_platform(period_days)
    by_style    = get_by_style(period_days)
    components  = get_component_breakdown(period_days)
    contacts    = get_all_contact_summaries()

    avg_scores  = [b["avg_score"] for b in agg_trend]
    overall_avg = round(sum(avg_scores)/len(avg_scores),1) if avg_scores else 0
    trend_lbl   = classify_trend(avg_scores)
    tmeta       = TREND_LABELS[trend_lbl]
    last_score  = avg_scores[-1] if avg_scores else 0
    first_score = avg_scores[0]  if avg_scores else 0
    delta       = round(last_score - first_score, 1)

    # Stats row
    m1,m2,m3,m4,m5 = st.columns(5)
    for col, lbl, val, color in [
        (m1,"Overall Avg",   f"{overall_avg}/10", "#e6edf3"),
        (m2,"Latest Score",  f"{last_score}/10",  "#3fb950" if last_score>=7 else "#d29922"),
        (m3,"Period Delta",  f"{'+' if delta>=0 else ''}{delta}", "#3fb950" if delta>=0 else "#f85149"),
        (m4,"Trend",         tmeta["icon"]+" "+tmeta["label"], tmeta["color"]),
        (m5,"Wishes Tracked",sum(b["count"] for b in agg_trend), "#58a6ff"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.6, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Aggregate Score Trend</div>',
                    unsafe_allow_html=True)
        if not agg_trend:
            st.info("No score history yet.")
        else:
            cols_html = ""
            for b in agg_trend:
                h_px  = int(b["avg_score"]/10*110)
                color = "#3fb950" if b["avg_score"]>=7.5 else (
                        "#58a6ff" if b["avg_score"]>=6 else (
                        "#d29922" if b["avg_score"]>=4 else "#f85149"))
                lbl = b["bucket"][5:]
                cols_html += f"""
                <div class="chart-col">
                  <div class="chart-val">{b['avg_score']}</div>
                  <div class="chart-bar" style="height:{h_px}px;background:{color}"></div>
                  <div class="chart-label">{lbl}</div>
                </div>"""
            st.markdown(f"""
            <div class="chart-wrap">
              <div style="position:absolute;top:10px;right:12px;font-size:0.68rem;
                          color:{tmeta['color']};font-weight:700">{tmeta['icon']} {tmeta['label']}</div>
              <div style="position:absolute;left:14px;top:38px;right:40px;height:1px;
                          border-top:1px dashed #30363d"></div>
              <div style="position:absolute;left:14px;top:68px;right:40px;height:1px;
                          border-top:1px dashed #21262d"></div>
              <div class="chart-area">{cols_html}</div>
            </div>""", unsafe_allow_html=True)

            if delta > 0.5:
                st.markdown(f'<div class="callout win" style="margin-top:10px">'
                            f'📈 Improved <strong>+{delta}</strong> pts over {period_opt}. '
                            f'Current avg: <strong>{last_score}/10</strong>.</div>',
                            unsafe_allow_html=True)
            elif delta < -0.5:
                st.markdown(f'<div class="callout alert" style="margin-top:10px">'
                            f'📉 Dropped <strong>{delta}</strong> pts. Review wish prompts and '
                            f'context_aware_opener settings.</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="callout" style="margin-top:10px">'
                            f'➡️ Stable around <strong>{overall_avg}/10</strong>.</div>',
                            unsafe_allow_html=True)

        # Per-contact list
        st.markdown('<div class="section-title">Per-Contact Trend</div>',
                    unsafe_allow_html=True)
        if "sel_contact" not in st.session_state:
            st.session_state.sel_contact = contacts[0]["contact_id"] if contacts else None

        for c in contacts:
            hist   = get_contact_trend(c["contact_id"], limit=6)
            scores = [h["score"] for h in hist]
            cm     = TREND_LABELS[c["trend"]]
            spark  = '<div class="spark">' + "".join(
                f'<div class="spark-bar" style="height:{int(s/10*20)}px;background:'
                f'{"#3fb950" if s>=7 else ("#d29922" if s>=5 else "#f85149")}"></div>'
                for s in scores) + "</div>"
            st.markdown(f"""
            <div class="c-card">
              <div class="c-name">
                {c['contact_name']}
                <span class="trend-chip" style="background:{cm['color']}22;
                      color:{cm['color']};border:1px solid {cm['color']}44">
                  {cm['icon']} {cm['label']}
                </span>{spark}
              </div>
              <div class="c-meta">Latest: {c['latest_score']}/10 · Avg: {c['avg_score']}/10 · {c['wish_count']} wishes</div>
            </div>""", unsafe_allow_html=True)
            if st.button("Drill down", key=f"dd_{c['contact_id']}", use_container_width=True):
                st.session_state.sel_contact = c["contact_id"]
                st.rerun()

    with right:
        # Drill-down chart
        sel = next((c for c in contacts
                    if c["contact_id"] == st.session_state.sel_contact), None)
        if sel:
            hist = get_contact_trend(sel["contact_id"], limit=12)
            st.markdown(f'<div class="section-title">{sel["contact_name"]}</div>',
                        unsafe_allow_html=True)
            if hist:
                dd_html = ""
                for h in hist:
                    h_px  = int(h["score"]/10*80)
                    color = "#3fb950" if h["score"]>=7 else ("#d29922" if h["score"]>=5 else "#f85149")
                    lbl   = h["wish_date"][2:7] if h.get("wish_date") else ""
                    dd_html += f"""<div class="chart-col">
                      <div class="chart-val">{h['score']}</div>
                      <div class="chart-bar" style="height:{h_px}px;background:{color}"></div>
                      <div class="chart-label">{lbl}</div>
                    </div>"""
                st.markdown(f'<div class="chart-wrap"><div class="chart-area" '
                            f'style="height:90px">{dd_html}</div></div>',
                            unsafe_allow_html=True)
                # Component breakdown
                all_c = {k: [] for k in SCORE_COMPONENTS}
                for h in hist:
                    for k in SCORE_COMPONENTS:
                        all_c[k].append(h["components"].get(k, 0))
                st.markdown('<div class="section-title">Avg Component Scores</div>',
                            unsafe_allow_html=True)
                for k, meta in SCORE_COMPONENTS.items():
                    avg  = round(sum(all_c[k])/len(all_c[k]),1) if all_c[k] else 0
                    pct  = int(avg/meta["max"]*100) if meta["max"] else 0
                    col  = "#3fb950" if pct>=75 else ("#d29922" if pct>=40 else "#f85149")
                    st.markdown(f"""<div class="comp-row">
                      <div class="comp-label">{meta['label']}</div>
                      <div class="comp-track">
                        <div class="comp-fill" style="width:{pct}%;background:{col}"></div>
                      </div>
                      <div class="comp-val">{avg}/{meta['max']}</div>
                    </div>""", unsafe_allow_html=True)

        # Platform & style bars
        st.markdown('<div class="section-title">Avg by Platform</div>', unsafe_allow_html=True)
        for plat, stats in by_platform.items():
            pct = int(stats["avg"]/10*100)
            col = PLAT_COLORS.get(plat,"#58a6ff")
            st.markdown(f"""<div class="comp-row">
              <div class="comp-label">{plat}</div>
              <div class="comp-track">
                <div class="comp-fill" style="width:{pct}%;background:{col}"></div>
              </div>
              <div class="comp-val">{stats['avg']}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown('<div class="section-title">Avg by Style</div>', unsafe_allow_html=True)
        for style, stats in by_style.items():
            pct = int(stats["avg"]/10*100)
            col = STYLE_COLORS.get(style,"#58a6ff")
            st.markdown(f"""<div class="comp-row">
              <div class="comp-label">{style}</div>
              <div class="comp-track">
                <div class="comp-fill" style="width:{pct}%;background:{col}"></div>
              </div>
              <div class="comp-val">{stats['avg']}</div>
            </div>""", unsafe_allow_html=True)

        # Weakest components
        st.markdown('<div class="section-title">Weakest Components</div>', unsafe_allow_html=True)
        sorted_comp = sorted(components.items(),
                             key=lambda x: x[1]/SCORE_COMPONENTS[x[0]]["max"])
        for k, avg_pts in sorted_comp[:3]:
            meta = SCORE_COMPONENTS[k]
            pct  = int(avg_pts/meta["max"]*100) if meta["max"] else 0
            cls  = "alert" if pct < 40 else "warn"
            st.markdown(f'<div class="callout {cls}"><strong>{meta["label"]}</strong> '
                        f'avg {avg_pts:.1f}/{meta["max"]} ({pct}%) — focus prompts here.</div>',
                        unsafe_allow_html=True)

    # Log a test score
    with st.expander("📥 Log a test score entry"):
        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            t_contact = st.selectbox("Contact", [c["contact_name"] for c in contacts],
                                     label_visibility="collapsed", key="t_contact")
        with tc2:
            t_score = st.number_input("Score (0-10)", 0, 10, 7, key="t_score")
        with tc3:
            t_style = st.selectbox("Style", list(STYLE_COLORS.keys()),
                                   label_visibility="collapsed", key="t_style")
        if st.button("Log Score", type="primary"):
            sel_c = next(c for c in contacts if c["contact_name"] == t_contact)
            log_wish_score(sel_c["contact_id"], t_contact, "LinkedIn", t_score, style=t_style)
            st.success(f"Logged {t_score}/10 for {t_contact} ✅")
            st.rerun()

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
      <span>Personalization Score Trend · {period_opt}</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    init_score_trend_table()
    seed_demo_scores()
    print("=== Personalization Score Trend — self test ===\n")
    agg = get_aggregate_trend(365, "month")
    print(f"Aggregate trend ({len(agg)} months):")
    for b in agg:
        print(f"  {b['bucket']}  {b['avg_score']:4.1f}/10  {'█'*int(b['avg_score'])}")
    contacts = get_all_contact_summaries()
    print(f"\n{len(contacts)} contacts tracked:")
    for c in contacts:
        t = TREND_LABELS[c["trend"]]
        print(f"  {t['icon']} {c['contact_name']:<22} avg={c['avg_score']}/10  {t['label']}")
    comps = get_component_breakdown(365)
    weakest = min(comps, key=lambda k: comps[k]/SCORE_COMPONENTS[k]["max"])
    print(f"\nWeakest component: {SCORE_COMPONENTS[weakest]['label']} ({comps[weakest]:.2f})")
else:
    render_dashboard()
