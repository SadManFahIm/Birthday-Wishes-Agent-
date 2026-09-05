"""
Relationship Graph Visualization -- Birthday Wishes Agent v9.0
Interactive force-directed graph showing who is connected to whom,
connection strength, and which relationships are fading.

Node states:
  strong   -- replied recently, high sentiment (green)
  neutral  -- moderate interaction (blue)
  fading   -- no interaction in 60+ days (yellow)
  dormant  -- no interaction in 120+ days (red)

Edge weight = connection strength (1-10 from connection_tracker)

Integrates with: contacts/connection_tracker.py,
                 contacts/reply_sentiment_trend.py,
                 contacts/relationship_tiering.py, agent.py
"""

import sqlite3
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

NODE_STATES = {
    "strong":  {"color": "#3fb950", "label": "Strong",  "days_threshold": 30},
    "neutral": {"color": "#58a6ff", "label": "Neutral", "days_threshold": 60},
    "fading":  {"color": "#d29922", "label": "Fading",  "days_threshold": 120},
    "dormant": {"color": "#f85149", "label": "Dormant", "days_threshold": 9999},
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_graph_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS graph_nodes (
            contact_id      TEXT PRIMARY KEY,
            contact_name    TEXT NOT NULL,
            platform        TEXT,
            tier            TEXT DEFAULT 'Acquaintance',
            strength        REAL DEFAULT 5.0,
            last_interaction TEXT,
            node_state      TEXT DEFAULT 'neutral',
            wishes_sent     INTEGER DEFAULT 0,
            replies_received INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS graph_edges (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id       TEXT NOT NULL,
            target_id       TEXT NOT NULL,
            edge_type       TEXT NOT NULL DEFAULT 'mutual_connection',
            weight          REAL DEFAULT 5.0,
            label           TEXT,
            UNIQUE(source_id, target_id)
        )
    """)
    conn.commit()
    conn.close()


# ── Node & edge management ────────────────────────────────────────────────────

def upsert_node(
    contact_id:       str,
    contact_name:     str,
    platform:         str = "LinkedIn",
    tier:             str = "Acquaintance",
    strength:         float = 5.0,
    last_interaction: Optional[str] = None,
    wishes_sent:      int = 0,
    replies_received: int = 0,
) -> None:
    """
    Add or update a contact node in the graph.
    Call after any interaction or tiering change.
    """
    init_graph_tables()
    state = _classify_node_state(last_interaction, strength)
    conn  = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO graph_nodes
            (contact_id, contact_name, platform, tier, strength,
             last_interaction, node_state, wishes_sent, replies_received)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id) DO UPDATE SET
            contact_name     = excluded.contact_name,
            platform         = excluded.platform,
            tier             = excluded.tier,
            strength         = excluded.strength,
            last_interaction = excluded.last_interaction,
            node_state       = excluded.node_state,
            wishes_sent      = excluded.wishes_sent,
            replies_received = excluded.replies_received
    """, (contact_id, contact_name, platform, tier, strength,
          last_interaction or datetime.now().isoformat(),
          state, wishes_sent, replies_received))
    conn.commit()
    conn.close()


def add_edge(
    source_id: str,
    target_id: str,
    edge_type: str = "mutual_connection",
    weight:    float = 5.0,
    label:     str = "",
) -> None:
    """
    Add a connection edge between two contacts.
    source_id is typically 'ME' (the agent owner).
    """
    init_graph_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO graph_edges (source_id, target_id, edge_type, weight, label)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_id, target_id) DO UPDATE SET
            weight = excluded.weight,
            label  = excluded.label
    """, (source_id, target_id, edge_type, weight, label))
    conn.commit()
    conn.close()


def _classify_node_state(last_interaction: Optional[str], strength: float) -> str:
    if not last_interaction:
        return "neutral"
    try:
        last_dt  = datetime.fromisoformat(last_interaction)
        days_ago = (datetime.now() - last_dt).days
    except ValueError:
        return "neutral"

    if days_ago <= 30 and strength >= 6:
        return "strong"
    if days_ago <= 60:
        return "neutral"
    if days_ago <= 120:
        return "fading"
    return "dormant"


# ── Graph data retrieval ──────────────────────────────────────────────────────

def get_graph_data() -> dict:
    """
    Return nodes and edges as JSON-serializable dicts for D3 rendering.

    Returns:
        {
          nodes: [{id, label, platform, tier, strength, state, color,
                   wishes_sent, replies_received}],
          edges: [{source, target, weight, type}],
          stats: {total, strong, neutral, fading, dormant}
        }
    """
    init_graph_tables()
    conn = sqlite3.connect(DB_PATH)
    node_rows = conn.execute("""
        SELECT contact_id, contact_name, platform, tier, strength,
               last_interaction, node_state, wishes_sent, replies_received
        FROM graph_nodes
    """).fetchall()
    edge_rows = conn.execute("""
        SELECT source_id, target_id, weight, edge_type, label
        FROM graph_edges
    """).fetchall()
    conn.close()

    nodes = []
    state_counts = {s: 0 for s in NODE_STATES}
    for r in node_rows:
        state = r[6] or "neutral"
        color = NODE_STATES.get(state, NODE_STATES["neutral"])["color"]
        state_counts[state] = state_counts.get(state, 0) + 1
        nodes.append({
            "id":               r[0],
            "label":            r[1],
            "platform":         r[2] or "LinkedIn",
            "tier":             r[3] or "Acquaintance",
            "strength":         r[4] or 5.0,
            "last_interaction": (r[5] or "")[:10],
            "state":            state,
            "color":            color,
            "wishes_sent":      r[7] or 0,
            "replies_received": r[8] or 0,
            "reply_rate":       round((r[8] or 0) / (r[7] or 1), 2),
        })

    # Add ME node (center)
    nodes.insert(0, {
        "id": "ME", "label": "You", "platform": "all",
        "tier": "self", "strength": 10, "state": "strong",
        "color": "#f78166", "wishes_sent": 0,
        "replies_received": 0, "reply_rate": 0,
        "last_interaction": datetime.now().date().isoformat(),
    })

    edges = [{
        "source": r[0], "target": r[1],
        "weight": r[2] or 5.0, "type": r[3] or "mutual_connection",
        "label": r[4] or "",
    } for r in edge_rows]

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {**state_counts, "total": len(nodes) - 1},
    }


def get_fading_contacts(days_threshold: int = 60) -> list[dict]:
    """Return contacts that haven't been interacted with recently."""
    init_graph_tables()
    cutoff = (datetime.now() - timedelta(days=days_threshold)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    rows   = conn.execute("""
        SELECT contact_id, contact_name, platform, tier,
               strength, last_interaction, node_state
        FROM graph_nodes
        WHERE last_interaction < ? OR node_state IN ('fading','dormant')
        ORDER BY last_interaction ASC
    """, (cutoff,)).fetchall()
    conn.close()
    return [{
        "contact_id": r[0], "contact_name": r[1], "platform": r[2],
        "tier": r[3], "strength": r[4],
        "last_interaction": (r[5] or "")[:10],
        "state": r[6],
        "color": NODE_STATES.get(r[6], NODE_STATES["neutral"])["color"],
        "days_ago": (datetime.now() -
                     datetime.fromisoformat(r[5] or datetime.now().isoformat())).days
                    if r[5] else 999,
    } for r in rows]


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_graph_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
    conn.close()
    if count > 0:
        return

    now = datetime.now()
    contacts = [
        ("urn_rakib_001","Rakib Hossain","LinkedIn","Close Friend",  8.5,  5, 5,4),
        ("urn_nadia_002","Nadia Islam",  "WhatsApp","Close Friend",  7.8, 12, 3,3),
        ("urn_tanvir_003","Tanvir Ahmed","LinkedIn","Colleague",     5.2, 75, 4,1),
        ("urn_mim_004","Mim Chowdhury", "WhatsApp","Close Friend",  9.1,  3, 6,6),
        ("urn_sara_005","Sara Khan",    "LinkedIn","Colleague",      4.5, 90, 3,1),
        ("urn_imran_006","Imran Hossain","Slack",  "Colleague",      6.3, 20, 5,4),
        ("urn_farah_007","Farah Akter", "LinkedIn","Acquaintance",   2.1,150, 2,0),
        ("urn_arif_008","Arif Hossain", "LinkedIn","Acquaintance",   3.4,130, 3,0),
        ("urn_rafi_009","Rafi Islam",   "WhatsApp","Colleague",      5.8, 45, 4,2),
        ("urn_luna_010","Luna Chowdhury","LinkedIn","Colleague",     6.0, 18, 5,3),
    ]
    for cid, cname, plat, tier, strength, days_ago, ws, rr in contacts:
        last = (now - timedelta(days=days_ago)).isoformat()
        upsert_node(cid, cname, plat, tier, strength, last, ws, rr)
        add_edge("ME", cid, "direct", strength,
                 f"{strength:.0f}/10 strength")

    # Mutual connections (edges between contacts)
    mutual = [
        ("urn_rakib_001","urn_nadia_002", 6.0, "mutual_connection"),
        ("urn_rakib_001","urn_mim_004",   7.0, "close_friends"),
        ("urn_tanvir_003","urn_sara_005", 5.0, "colleagues"),
        ("urn_imran_006","urn_rafi_009",  6.5, "mutual_connection"),
        ("urn_nadia_002","urn_luna_010",  5.5, "colleagues"),
    ]
    for src, tgt, w, etype in mutual:
        add_edge(src, tgt, etype, w)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
        import streamlit.components.v1 as components
    except ImportError:
        return

    st.set_page_config(page_title="Relationship Graph", page_icon="🕸️",
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
    .mini-lbl{font-size:0.6rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    .f-row{background:var(--surface);border:1px solid var(--border);
           border-radius:8px;padding:10px 14px;margin-bottom:6px;}
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

    init_graph_tables()
    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🕸️</span>
      <h1>Relationship Graph</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    graph    = get_graph_data()
    stats    = graph["stats"]
    fading   = get_fading_contacts(60)

    m1,m2,m3,m4,m5 = st.columns(5)
    for col, lbl, val, color in [
        (m1,"Total Contacts", stats["total"],    "#e6edf3"),
        (m2,"Strong",         stats["strong"],   "#3fb950"),
        (m3,"Neutral",        stats["neutral"],  "#58a6ff"),
        (m4,"Fading",         stats["fading"],   "#d29922"),
        (m5,"Dormant",        stats["dormant"],  "#f85149"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── D3 force graph ────────────────────────────────────────────────────────
    nodes_json = json.dumps(graph["nodes"])
    edges_json = json.dumps(graph["edges"])

    graph_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
  body {{ background:#0d1117; margin:0; overflow:hidden; font-family:'Inter',sans-serif; }}
  svg {{ width:100%; height:100%; }}
  .node circle {{ cursor:pointer; stroke:#0d1117; stroke-width:2px; }}
  .node text {{ font-size:11px; fill:#c9d1d9; pointer-events:none; }}
  .link {{ stroke-opacity:0.35; }}
  .tooltip {{
    position:absolute; background:#161b22; border:1px solid #30363d;
    border-radius:8px; padding:10px 14px; font-size:12px; color:#e6edf3;
    pointer-events:none; opacity:0; transition:opacity 0.15s;
    max-width:200px; line-height:1.6;
  }}
  #legend {{
    position:absolute; bottom:14px; left:14px;
    background:#161b22cc; border:1px solid #30363d;
    border-radius:8px; padding:10px 14px; font-size:11px;
  }}
  .legend-item {{ display:flex; align-items:center; gap:8px; margin-bottom:4px; }}
  .legend-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
</style>
</head>
<body>
<div class="tooltip" id="tooltip"></div>
<svg id="graph"></svg>
<div id="legend">
  <div class="legend-item"><div class="legend-dot" style="background:#f78166"></div>You</div>
  <div class="legend-item"><div class="legend-dot" style="background:#3fb950"></div>Strong</div>
  <div class="legend-item"><div class="legend-dot" style="background:#58a6ff"></div>Neutral</div>
  <div class="legend-item"><div class="legend-dot" style="background:#d29922"></div>Fading</div>
  <div class="legend-item"><div class="legend-dot" style="background:#f85149"></div>Dormant</div>
</svg>
<script>
const W = window.innerWidth, H = window.innerHeight;
const svg = d3.select("#graph").attr("width",W).attr("height",H);
const g   = svg.append("g");

const rawNodes = {nodes_json};
const rawEdges = {edges_json};

const nodeMap = {{}};
rawNodes.forEach(n => nodeMap[n.id] = n);

const links = rawEdges.map(e => ({{
  source: e.source, target: e.target,
  weight: e.weight, type: e.type, label: e.label,
}}));

const nodes = rawNodes.map(n => ({{...n}}));

const sim = d3.forceSimulation(nodes)
  .force("link",   d3.forceLink(links).id(d => d.id)
                     .distance(d => 120 - d.weight * 6)
                     .strength(0.4))
  .force("charge", d3.forceManyBody().strength(-280))
  .force("center", d3.forceCenter(W/2, H/2))
  .force("collision", d3.forceCollide(38));

// Edges
const link = g.append("g").selectAll("line")
  .data(links).join("line")
  .attr("class","link")
  .attr("stroke", d => d.type === "close_friends" ? "#3fb95066" : "#30363d")
  .attr("stroke-width", d => Math.max(1, d.weight / 3));

// Nodes
const node = g.append("g").selectAll("g")
  .data(nodes).join("g")
  .attr("class","node")
  .call(d3.drag()
    .on("start", (e,d) => {{ if(!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; }})
    .on("drag",  (e,d) => {{ d.fx=e.x; d.fy=e.y; }})
    .on("end",   (e,d) => {{ if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }}));

node.append("circle")
  .attr("r",      d => d.id === "ME" ? 22 : 8 + d.strength * 1.2)
  .attr("fill",   d => d.color)
  .attr("fill-opacity", d => d.id === "ME" ? 1 : 0.85)
  .on("mouseover", (e,d) => {{
    const t = document.getElementById("tooltip");
    t.style.opacity = 1;
    t.style.left    = (e.pageX+14)+"px";
    t.style.top     = (e.pageY-10)+"px";
    if(d.id === "ME") {{
      t.innerHTML = "<strong>You</strong><br>Center of your network";
    }} else {{
      t.innerHTML =
        "<strong>"+d.label+"</strong><br>"+
        "Platform: "+d.platform+"<br>"+
        "Tier: "+d.tier+"<br>"+
        "Strength: "+d.strength.toFixed(1)+"/10<br>"+
        "State: "+d.state+"<br>"+
        "Wishes sent: "+d.wishes_sent+"<br>"+
        "Replies: "+d.replies_received+
        (d.last_interaction ? "<br>Last: "+d.last_interaction : "");
    }}
  }})
  .on("mousemove", e => {{
    document.getElementById("tooltip").style.left=(e.pageX+14)+"px";
    document.getElementById("tooltip").style.top=(e.pageY-10)+"px";
  }})
  .on("mouseout", () => document.getElementById("tooltip").style.opacity=0);

node.append("text")
  .attr("dy", d => (d.id === "ME" ? 22 : 8 + d.strength * 1.2) + 14)
  .attr("text-anchor","middle")
  .text(d => d.id === "ME" ? "You" : d.label.split(" ")[0]);

// Pulse animation for fading/dormant
node.filter(d => d.state === "fading" || d.state === "dormant")
  .append("circle")
  .attr("r",      d => 8 + d.strength * 1.2)
  .attr("fill",   "none")
  .attr("stroke", d => d.color)
  .attr("stroke-width", 1.5)
  .attr("opacity", 0.5)
  .each(function pulse(d) {{
    d3.select(this)
      .transition().duration(1400)
      .attr("r", (8 + d.strength*1.2)*1.7).attr("opacity",0)
      .transition().duration(0).attr("r", 8 + d.strength*1.2).attr("opacity",0.5)
      .on("end", function(){{ pulse.call(this,d); }});
  }});

// Zoom
svg.call(d3.zoom()
  .scaleExtent([0.3,4])
  .on("zoom", e => g.attr("transform", e.transform)));

sim.on("tick", () => {{
  link
    .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});
</script>
</body>
</html>"""

    components.html(graph_html, height=550, scrolling=False)

    # ── Fading contacts panel ─────────────────────────────────────────────────
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Fading Relationships</div>',
                    unsafe_allow_html=True)
        fading_list = [c for c in fading if c["state"] in ("fading","dormant")]
        if not fading_list:
            st.markdown('<div style="color:#3fb950;font-size:0.82rem">✅ All relationships healthy</div>',
                        unsafe_allow_html=True)
        for c in fading_list[:8]:
            st.markdown(f"""
            <div class="f-row">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <div style="font-weight:700;font-size:0.84rem">{c['contact_name']}</div>
                <span style="color:{c['color']};font-size:0.7rem;font-weight:700">
                  {c['state'].upper()} — {c['days_ago']}d ago
                </span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:2px">
                {c['platform']} · {c['tier']} · strength {c['strength']:.1f}/10
              </div>
            </div>
            """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Network Summary</div>',
                    unsafe_allow_html=True)
        nodes = graph["nodes"][1:]  # exclude ME

        # Platform breakdown
        plat_counts: dict = {}
        for n in nodes:
            p = n.get("platform","Unknown")
            plat_counts[p] = plat_counts.get(p, 0) + 1

        PLAT_COLORS = {"LinkedIn":"#58a6ff","WhatsApp":"#3fb950",
                       "Slack":"#4fc3f7","Facebook":"#bc8cff",
                       "Instagram":"#f78166","Twitter/X":"#d29922"}
        total_nodes = len(nodes) or 1
        for plat, count in sorted(plat_counts.items(),
                                   key=lambda x: x[1], reverse=True):
            pct   = int(count / total_nodes * 100)
            color = PLAT_COLORS.get(plat, "#8b949e")
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              <div style="width:90px;font-size:0.76rem">{plat}</div>
              <div style="flex:1;background:#0d1117;border-radius:4px;
                          height:18px;overflow:hidden">
                <div style="width:{pct}%;height:100%;background:{color};
                            border-radius:4px"></div>
              </div>
              <div style="width:28px;font-size:0.72rem;color:#8b949e">{count}</div>
            </div>
            """, unsafe_allow_html=True)

        # Avg strength per tier
        st.markdown('<div class="section-title">Avg Strength by Tier</div>',
                    unsafe_allow_html=True)
        tier_data: dict = {}
        for n in nodes:
            tier = n.get("tier","Acquaintance")
            if tier not in tier_data:
                tier_data[tier] = []
            tier_data[tier].append(n.get("strength",5))

        TIER_COLORS = {"Close Friend":"#3fb950","Colleague":"#58a6ff",
                       "Acquaintance":"#8b949e"}
        for tier, strengths in sorted(tier_data.items(),
                                       key=lambda x: -sum(x[1])/len(x[1])):
            avg   = sum(strengths) / len(strengths)
            pct   = int(avg / 10 * 100)
            color = TIER_COLORS.get(tier, "#8b949e")
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              <div style="width:110px;font-size:0.76rem">{tier}</div>
              <div style="flex:1;background:#0d1117;border-radius:4px;
                          height:18px;overflow:hidden">
                <div style="width:{pct}%;height:100%;background:{color};
                            border-radius:4px"></div>
              </div>
              <div style="width:36px;font-size:0.72rem;color:#8b949e">
                {avg:.1f}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>Relationship Graph Visualization</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_graph_tables()
    _seed_demo()
    print("=== Relationship Graph -- self test ===\n")
    graph = get_graph_data()
    print(f"Nodes : {len(graph['nodes'])-1} contacts + ME")
    print(f"Edges : {len(graph['edges'])}")
    print(f"Stats : {graph['stats']}")
    fading = get_fading_contacts(60)
    print(f"\nFading/Dormant contacts: {len(fading)}")
    for c in fading:
        print(f"  {c['state']:<8} {c['contact_name']:<22} {c['days_ago']}d ago")
else:
    render_dashboard()
