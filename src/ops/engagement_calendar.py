"""
Engagement Heat Calendar -- Birthday Wishes Agent v10.0
Analyzes reply timestamps to find the best day and time to reach
each contact, then visualises as an interactive heatmap.

How it works:
  1. Pull reply timestamps from wish_outcome_log
  2. Bucket into day-of-week × hour-of-day (7 × 24 = 168 cells)
  3. Score each cell: replies / total_sent in that slot
  4. Return best slot + full heatmap matrix for visualisation

Also provides:
  - Global network-wide heatmap (best time to send to anyone)
  - Per-platform breakdown
  - "Next best send window" within the next 7 days

Integrates with: automation/smart_send_time_optimizer.py,
                 autonomous_agent.py, langgraph_workflow.py
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

DAYS   = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
HOURS  = list(range(24))

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_calendar_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engagement_heat (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id  TEXT NOT NULL,
            platform    TEXT NOT NULL,
            day_of_week INTEGER NOT NULL,
            hour_of_day INTEGER NOT NULL,
            sends       INTEGER NOT NULL DEFAULT 0,
            replies     INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT NOT NULL
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


# ── Data extraction ───────────────────────────────────────────────────────────

def compute_heatmap(
    contact_id: Optional[str] = None,
    platform:   Optional[str] = None,
    days_back:  int = 365,
) -> dict:
    """
    Compute engagement heatmap from historical send/reply data.

    Args:
        contact_id: Single contact (None = all contacts / global).
        platform:   Filter by platform (None = all platforms).
        days_back:  Lookback window in days.

    Returns:
        {
          matrix:    7×24 float grid (0-1, reply rate per slot),
          best_day:  int (0=Mon … 6=Sun),
          best_hour: int (0-23),
          best_slot: str (e.g. "Wednesday 09:00"),
          total_sends, total_replies, reply_rate,
          by_day:    [7 floats], by_hour: [24 floats]
        }
    """
    conn   = _db()
    matrix = [[0.0] * 24 for _ in range(7)]   # [day][hour] → reply_rate
    sends  = [[0]   * 24 for _ in range(7)]
    replies= [[0]   * 24 for _ in range(7)]

    if not _table_exists(conn, "wish_outcome_log"):
        conn.close()
        return _empty_heatmap()

    cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
    sql    = "SELECT sent_at, replied_at, replied FROM wish_outcome_log WHERE sent_at >= ?"
    params = [cutoff]
    if contact_id:
        sql   += " AND contact_id=?"
        params.append(contact_id)
    if platform:
        sql   += " AND platform=?"
        params.append(platform)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    for r in rows:
        try:
            sent_dt = datetime.fromisoformat(r["sent_at"])
        except (ValueError, TypeError):
            continue
        dow  = sent_dt.weekday()     # 0=Mon … 6=Sun
        hour = sent_dt.hour
        sends[dow][hour]  += 1
        if r["replied"]:
            replies[dow][hour] += 1

    # Compute reply rates
    total_sends   = sum(sum(row) for row in sends)
    total_replies = sum(sum(row) for row in replies)

    best_score = -1
    best_day   = 1    # default: Tuesday
    best_hour  = 9    # default: 9 AM

    for d in range(7):
        for h in range(24):
            s = sends[d][h]
            r = replies[d][h]
            rate = (r / s) if s > 0 else 0.0
            matrix[d][h] = round(rate, 3)
            if rate > best_score and s > 0:
                best_score = rate
                best_day   = d
                best_hour  = h

    # Marginal distributions
    by_day  = [round(sum(replies[d]) / max(sum(sends[d]),1), 3) for d in range(7)]
    by_hour = []
    for h in range(24):
        s = sum(sends[d][h] for d in range(7))
        r = sum(replies[d][h] for d in range(7))
        by_hour.append(round(r / max(s,1), 3))

    best_slot = f"{DAYS[best_day]} {best_hour:02d}:00"

    return {
        "matrix":        matrix,
        "best_day":      best_day,
        "best_hour":     best_hour,
        "best_slot":     best_slot,
        "total_sends":   total_sends,
        "total_replies": total_replies,
        "reply_rate":    round(total_replies / max(total_sends,1), 3),
        "by_day":        by_day,
        "by_hour":       by_hour,
        "contact_id":    contact_id or "all",
        "platform":      platform or "all",
        "days_back":     days_back,
    }


def _empty_heatmap():
    """Return a heatmap with synthetic defaults when no real data exists."""
    matrix = [[0.0] * 24 for _ in range(7)]
    # Typical engagement pattern: Tue-Thu, 9-11 AM and 2-4 PM
    peaks = [(1,9),(1,10),(2,9),(2,10),(2,14),(3,10),(3,15),(4,11)]
    for d, h in peaks:
        matrix[d][h] = round(0.3 + 0.1 * (peaks.index((d,h)) % 4), 3)
    by_day  = [0.15, 0.38, 0.35, 0.30, 0.22, 0.10, 0.08]
    by_hour = [0.0]*7 + [0.1,0.3,0.4,0.35,0.15,0.1] + \
              [0.05]*3 + [0.2,0.32,0.28,0.1] + [0.05]*5
    return {
        "matrix": matrix, "best_day": 2, "best_hour": 9,
        "best_slot": "Wed 09:00",
        "total_sends": 0, "total_replies": 0, "reply_rate": 0.0,
        "by_day": by_day, "by_hour": by_hour[:24],
        "contact_id": "all", "platform": "all", "days_back": 365,
        "synthetic": True,
    }


# ── Next best send window ─────────────────────────────────────────────────────

def next_send_window(
    contact_id: Optional[str] = None,
    platform:   Optional[str] = None,
    within_days:int = 7,
) -> dict:
    """
    Return the next calendar slot (within N days) that matches
    the contact's historically best engagement time.

    Returns:
        { datetime_str, day_label, hour, iso, hours_from_now }
    """
    hm   = compute_heatmap(contact_id, platform)
    bd   = hm["best_day"]
    bh   = hm["best_hour"]
    now  = datetime.now()

    # Find the next occurrence of best_day/hour
    for offset in range(within_days * 24):
        candidate = now + timedelta(hours=offset)
        if candidate.weekday() == bd and candidate.hour == bh:
            return {
                "datetime_str":  candidate.strftime("%Y-%m-%d %H:%M"),
                "day_label":     DAYS[bd],
                "hour":          bh,
                "iso":           candidate.isoformat(),
                "hours_from_now":offset,
            }
    # Fallback
    fallback = now + timedelta(days=1)
    return {
        "datetime_str":  fallback.strftime("%Y-%m-%d %H:%M"),
        "day_label":     DAYS[fallback.weekday()],
        "hour":          bh,
        "iso":           fallback.isoformat(),
        "hours_from_now":24,
    }


# ── Per-contact best slots ────────────────────────────────────────────────────

def get_best_slots_for_contacts(
    contact_ids: list[str],
) -> dict[str, dict]:
    """
    Compute best send slot for a list of contacts in one pass.
    Returns: { contact_id: { best_slot, hours_from_now } }
    """
    return {cid: next_send_window(cid) for cid in contact_ids}


# ── Platform comparison ───────────────────────────────────────────────────────

def platform_heatmap_comparison(days_back: int = 90) -> dict:
    """Compare engagement patterns across platforms."""
    platforms = ["LinkedIn","WhatsApp","Telegram","Discord","Facebook","Slack"]
    result    = {}
    for plat in platforms:
        hm = compute_heatmap(platform=plat, days_back=days_back)
        if hm.get("total_sends", 0) > 0 or hm.get("synthetic"):
            result[plat] = {
                "best_slot":   hm["best_slot"],
                "reply_rate":  hm["reply_rate"],
                "total_sends": hm["total_sends"],
                "by_day":      hm["by_day"],
            }
    return result


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    """Inject synthetic send/reply records for dashboard demo."""
    conn  = _db()
    if not _table_exists(conn, "wish_outcome_log"):
        conn.close()
        return
    count = conn.execute(
        "SELECT COUNT(*) FROM wish_outcome_log").fetchone()[0]
    conn.close()
    if count > 0:
        return

    import random as _r
    _r.seed(99)
    contacts = [
        ("urn_rakib_001","Rakib Hossain","LinkedIn"),
        ("urn_nadia_002","Nadia Islam",  "WhatsApp"),
        ("urn_mim_004",  "Mim Chowdhury","WhatsApp"),
        ("urn_tanvir_003","Tanvir Ahmed","LinkedIn"),
    ]
    now  = datetime.now()
    rows = []
    for cid, cname, plat in contacts:
        for _ in range(20):
            days_ago = _r.randint(1,180)
            # Bias toward Tue-Thu 9-11 AM
            dow  = _r.choices([0,1,2,3,4,5,6],
                              weights=[1,4,4,3,2,1,1])[0]
            hour = _r.choices(list(range(24)),
                              weights=[0]*7+[1,3,5,4,2,1]+[0]*3+
                              [1,3,3,2,1]+[0]*5)[0]
            sent_dt  = now - timedelta(days=days_ago,
                                       hours=23-hour, minutes=_r.randint(0,59))
            replied  = _r.random() < (0.5 if 9<=hour<=11 else 0.2)
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                INSERT OR IGNORE INTO wish_outcome_log
                    (contact_id, contact_name, platform, prompt_version,
                     wish_style, personalization_score, replied, sent_at,
                     replied_at)
                VALUES (?, ?, ?, 'v1.0', 'warm', 7, ?, ?, ?)
            """, (cid, cname, plat, 1 if replied else 0,
                  sent_dt.isoformat(),
                  (sent_dt + timedelta(hours=_r.randint(1,8))).isoformat()
                  if replied else None))
            conn.commit()
            conn.close()


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
        import streamlit.components.v1 as components
    except ImportError:
        return

    st.set_page_config(page_title="Engagement Calendar", page_icon="📅",
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

    init_calendar_tables()
    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📅</span>
      <h1>Engagement Heat Calendar</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    # Controls
    left_ctrl, right_ctrl = st.columns([2, 1])
    with left_ctrl:
        view  = st.radio("View", ["Global Network","Per Contact","Per Platform"],
                         horizontal=True, label_visibility="collapsed")
    with right_ctrl:
        days_back = st.select_slider("Lookback", [30,60,90,180,365],
                                     value=180, label_visibility="collapsed")

    contact_id = None
    platform   = None

    if view == "Per Contact":
        contact_id = st.text_input("Contact ID", placeholder="urn_rakib_001",
                                   label_visibility="collapsed")

    if view == "Per Platform":
        platform = st.selectbox("Platform",
                                ["LinkedIn","WhatsApp","Telegram","Discord"],
                                label_visibility="collapsed")

    hm = compute_heatmap(contact_id or None, platform, days_back)

    # Stats row
    nsw = next_send_window(contact_id or None, platform)
    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Best Slot",     hm["best_slot"],            "#f78166"),
        (m2, "Reply Rate",    f"{hm['reply_rate']:.0%}",  "#3fb950"),
        (m3, "Next Window",   nsw["datetime_str"],         "#58a6ff"),
        (m4, "Hours Away",    f"{nsw['hours_from_now']}h", "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" '
                        f'style="color:{color};font-size:1rem">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── D3 heatmap ────────────────────────────────────────────────────────────
    matrix_json = json.dumps(hm["matrix"])
    by_day_json = json.dumps(hm["by_day"])
    by_hr_json  = json.dumps(hm["by_hour"])
    best_d      = hm["best_day"]
    best_h      = hm["best_hour"]
    days_json   = json.dumps(DAYS)

    heatmap_html = f"""
<!DOCTYPE html><html><head>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
  body{{background:#0d1117;margin:0;font-family:'Inter',sans-serif;color:#e6edf3;}}
  .cell{{rx:3;cursor:pointer;}}
  .label{{font-size:10px;fill:#8b949e;}}
  .best-label{{font-size:11px;fill:#f78166;font-weight:700;}}
  .tooltip{{position:absolute;background:#161b22;border:1px solid #30363d;
            border-radius:6px;padding:8px 12px;font-size:11px;
            pointer-events:none;opacity:0;transition:opacity 0.1s;}}
  .legend-label{{font-size:10px;fill:#8b949e;}}
</style></head><body>
<div class="tooltip" id="tt"></div>
<svg id="hm"></svg>
<script>
const matrix  = {matrix_json};
const byDay   = {by_day_json};
const byHour  = {by_hr_json};
const DAYS    = {days_json};
const bestD   = {best_d};
const bestH   = {best_h};
const W       = window.innerWidth;
const MARGIN  = {{top:30,right:60,bottom:50,left:44}};
const cellW   = Math.max(14, Math.floor((W - MARGIN.left - MARGIN.right - 80) / 24));
const cellH   = 28;
const gridW   = 24 * cellW;
const gridH   = 7  * cellH;
const svgW    = gridW + MARGIN.left + MARGIN.right + 80;
const svgH    = gridH + MARGIN.top  + MARGIN.bottom + 60;

const svg = d3.select("#hm").attr("width",svgW).attr("height",svgH);
const g   = svg.append("g").attr("transform",`translate(${{MARGIN.left}},${{MARGIN.top}})`);

const color = d3.scaleSequential(d3.interpolateRgb("#161b22","#f78166"))
  .domain([0, d3.max(matrix.flat()) || 0.5]);

// Hour labels
for(let h=0;h<24;h+=2){{
  g.append("text").attr("class","label")
   .attr("x", h*cellW + cellW/2).attr("y",-8)
   .attr("text-anchor","middle").text(`${{h}}h`);
}}
// Day labels
DAYS.forEach((d,i)=>{{
  g.append("text").attr("class","label")
   .attr("x",-6).attr("y", i*cellH + cellH*0.65)
   .attr("text-anchor","end").text(d);
}});

// Cells
const tt = d3.select("#tt");
matrix.forEach((row,di)=>{{
  row.forEach((val,hi)=>{{
    const isBest = di===bestD && hi===bestH;
    const rect = g.append("rect").attr("class","cell")
      .attr("x", hi*cellW + 1).attr("y", di*cellH + 1)
      .attr("width", cellW-2).attr("height", cellH-2)
      .attr("fill", val===0 ? "#21262d" : color(val))
      .attr("stroke", isBest ? "#f78166" : "none")
      .attr("stroke-width", isBest ? 2 : 0);

    rect.on("mouseover",(e)=>{{
      tt.style("opacity",1)
        .html(`<strong>${{DAYS[di]}} ${{hi.toString().padStart(2,"0")}}:00</strong><br>`+
              `Reply rate: ${{(val*100).toFixed(0)}}%`)
        .style("left",(e.pageX+12)+"px").style("top",(e.pageY-10)+"px");
    }}).on("mouseout",()=>tt.style("opacity",0));
  }});
}});

// Best slot marker
g.append("text").attr("class","best-label")
 .attr("x", bestH*cellW + cellW/2)
 .attr("y", bestD*cellH - 4)
 .attr("text-anchor","middle")
 .text("▼ best");

// By-day bar chart (right side)
const barX = gridW + 20;
const maxD  = d3.max(byDay) || 0.01;
DAYS.forEach((d,i)=>{{
  const barLen = (byDay[i]/maxD) * 55;
  g.append("rect")
   .attr("x",barX).attr("y",i*cellH+3)
   .attr("width",Math.max(2,barLen)).attr("height",cellH-6)
   .attr("fill","#58a6ff").attr("rx",2).attr("opacity",0.7);
  g.append("text").attr("class","label")
   .attr("x",barX+barLen+3).attr("y",i*cellH+cellH*0.65)
   .text(`${{(byDay[i]*100).toFixed(0)}}%`);
}});
g.append("text").attr("class","label")
 .attr("x",barX+27).attr("y",-8).attr("text-anchor","middle")
 .text("by day");

// By-hour bar chart (bottom)
const barY  = gridH + 12;
const maxH  = d3.max(byHour) || 0.01;
for(let h=0;h<24;h++){{
  const barLen = (byHour[h]/maxH)*26;
  g.append("rect")
   .attr("x",h*cellW+1).attr("y",barY)
   .attr("width",cellW-2).attr("height",Math.max(2,barLen))
   .attr("fill","#3fb950").attr("rx",2).attr("opacity",0.7);
}}
g.append("text").attr("class","label")
 .attr("x",gridW/2).attr("y",barY+38).attr("text-anchor","middle")
 .text("reply rate by hour →");

// Legend
const lg = svg.append("g")
  .attr("transform",`translate(${{MARGIN.left}},${{svgH-14}})`);
const lgScale = d3.scaleSequential(d3.interpolateRgb("#161b22","#f78166"))
  .domain([0,1]);
for(let i=0;i<50;i++){{
  lg.append("rect").attr("x",i*4).attr("y",0)
    .attr("width",4).attr("height",10)
    .attr("fill",lgScale(i/50));
}}
lg.append("text").attr("class","legend-label")
  .attr("x",-2).attr("y",9).attr("text-anchor","end").text("0%");
lg.append("text").attr("class","legend-label")
  .attr("x",202).attr("y",9).text("high");
</script></body></html>"""

    components.html(heatmap_html, height=380, scrolling=False)

    # Per-platform comparison
    if view != "Per Platform":
        st.markdown('<div class="section-title">Platform Best Slots</div>',
                    unsafe_allow_html=True)
        comparison = platform_heatmap_comparison(days_back)
        if comparison:
            cols = st.columns(len(comparison))
            for col, (plat, data) in zip(cols, comparison.items()):
                with col:
                    st.markdown(f"""
                    <div class="mini">
                      <div class="mini-val" style="font-size:0.9rem;color:#f78166">
                        {data['best_slot']}
                      </div>
                      <div class="mini-lbl">{plat}</div>
                      <div style="font-size:0.65rem;color:#3fb950;margin-top:3px">
                        {data['reply_rate']:.0%} reply rate
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Engagement Heat Calendar</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_calendar_tables()
    _seed_demo()
    print("=== Engagement Heat Calendar -- self test ===\n")

    hm = compute_heatmap()
    print(f"Global heatmap:")
    print(f"  Best slot  : {hm['best_slot']}")
    print(f"  Reply rate : {hm['reply_rate']:.0%}")
    print(f"  Sends      : {hm['total_sends']}")
    print(f"  Synthetic  : {hm.get('synthetic', False)}")

    nsw = next_send_window()
    print(f"\nNext send window:")
    print(f"  {nsw['datetime_str']}  ({nsw['hours_from_now']}h from now)")

    print("\nPer-day reply rates:")
    for i, (day, rate) in enumerate(zip(DAYS, hm["by_day"])):
        bar = "█" * int(rate * 30)
        print(f"  {day}: {bar:<30} {rate:.0%}")

    cmp = platform_heatmap_comparison()
    print("\nPlatform best slots:")
    for plat, data in cmp.items():
        print(f"  {plat:<12} → {data['best_slot']}")
else:
    render_dashboard()
