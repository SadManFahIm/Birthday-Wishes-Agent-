"""
Revenue Attribution -- Birthday Wishes Agent v9.0
Tracks which contacts led to business opportunities, deals, or referrals
after receiving a birthday wish or congratulation.

Attribution models:
  direct     -- contact themselves became a client
  referral   -- contact referred someone who became a client
  intro      -- contact made an intro that led to a deal
  partnership-- contact became a business partner

Integrates with: contacts/relationship_tiering.py,
                 contacts/life_event_timeline.py, agent.py
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

ATTRIBUTION_TYPES = {
    "direct":      {"label": "Direct Client",   "icon": "💰", "color": "#3fb950"},
    "referral":    {"label": "Referral",         "icon": "🤝", "color": "#58a6ff"},
    "intro":       {"label": "Intro/Connection", "icon": "🔗", "color": "#d29922"},
    "partnership": {"label": "Partnership",      "icon": "🏢", "color": "#bc8cff"},
    "other":       {"label": "Other",            "icon": "📌", "color": "#8b949e"},
}

CURRENCIES = ["BDT", "USD", "EUR", "GBP", "JPY", "CNY"]


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_revenue_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS revenue_attributions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id          TEXT NOT NULL,
            contact_name        TEXT NOT NULL,
            attribution_type    TEXT NOT NULL DEFAULT 'direct',
            deal_name           TEXT NOT NULL,
            deal_value          REAL NOT NULL DEFAULT 0,
            currency            TEXT NOT NULL DEFAULT 'BDT',
            deal_value_usd      REAL,
            wish_sent_date      TEXT,
            deal_closed_date    TEXT NOT NULL,
            days_to_close       INTEGER,
            platform            TEXT,
            notes               TEXT,
            logged_at           TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS revenue_contacts (
            contact_id          TEXT PRIMARY KEY,
            contact_name        TEXT NOT NULL,
            total_attributed    REAL NOT NULL DEFAULT 0,
            total_attributed_usd REAL NOT NULL DEFAULT 0,
            deal_count          INTEGER NOT NULL DEFAULT 0,
            last_deal_date      TEXT,
            best_attribution    TEXT
        )
    """)
    conn.commit()
    conn.close()


# ── Log attribution ────────────────────────────────────────────────────────────

def log_attribution(
    contact_id:       str,
    contact_name:     str,
    deal_name:        str,
    deal_value:       float,
    attribution_type: str = "direct",
    currency:         str = "BDT",
    deal_closed_date: Optional[str] = None,
    wish_sent_date:   Optional[str] = None,
    platform:         str = "",
    notes:            str = "",
) -> int:
    """
    Log a revenue attribution to a contact.

    Args:
        contact_id:       Unique contact identifier.
        deal_name:        Name of the deal / project.
        deal_value:       Value in the given currency.
        attribution_type: direct / referral / intro / partnership / other
        currency:         Currency code (default BDT).
        deal_closed_date: ISO date when deal closed. Defaults to today.
        wish_sent_date:   ISO date when birthday wish was sent (for ROI calc).

    Returns:
        Inserted row ID.
    """
    init_revenue_tables()
    closed    = deal_closed_date or datetime.now().date().isoformat()
    usd_rates = {"BDT": 0.0091, "USD": 1.0, "EUR": 1.09,
                 "GBP": 1.27, "JPY": 0.0067, "CNY": 0.14}
    value_usd = round(deal_value * usd_rates.get(currency, 1.0), 2)

    days_close = None
    if wish_sent_date:
        try:
            d1 = datetime.fromisoformat(wish_sent_date)
            d2 = datetime.fromisoformat(closed)
            days_close = (d2 - d1).days
        except ValueError:
            pass

    conn   = sqlite3.connect(DB_PATH)
    cur    = conn.execute("""
        INSERT INTO revenue_attributions
            (contact_id, contact_name, attribution_type, deal_name,
             deal_value, currency, deal_value_usd, wish_sent_date,
             deal_closed_date, days_to_close, platform, notes, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, attribution_type, deal_name,
          deal_value, currency, value_usd, wish_sent_date,
          closed, days_close, platform, notes, datetime.now().isoformat()))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()

    _refresh_contact_revenue(contact_id, contact_name)
    return row_id


def _refresh_contact_revenue(contact_id: str, contact_name: str):
    """Recompute totals for a contact's revenue profile."""
    conn  = sqlite3.connect(DB_PATH)
    rows  = conn.execute("""
        SELECT SUM(deal_value_usd), COUNT(*), MAX(deal_closed_date),
               attribution_type
        FROM revenue_attributions
        WHERE contact_id=?
        GROUP BY attribution_type
        ORDER BY SUM(deal_value_usd) DESC
    """, (contact_id,)).fetchall()

    total_usd  = sum(r[0] or 0 for r in rows)
    total_cnt  = sum(r[1] or 0 for r in rows)
    last_date  = max((r[2] or "" for r in rows), default="")
    best_type  = rows[0][3] if rows else "other"

    raw = conn.execute("""
        SELECT SUM(deal_value), currency FROM revenue_attributions
        WHERE contact_id=? GROUP BY currency ORDER BY SUM(deal_value) DESC LIMIT 1
    """, (contact_id,)).fetchone()
    total_local = raw[0] if raw else 0

    conn.execute("""
        INSERT INTO revenue_contacts
            (contact_id, contact_name, total_attributed, total_attributed_usd,
             deal_count, last_deal_date, best_attribution)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id) DO UPDATE SET
            contact_name         = excluded.contact_name,
            total_attributed     = excluded.total_attributed,
            total_attributed_usd = excluded.total_attributed_usd,
            deal_count           = excluded.deal_count,
            last_deal_date       = excluded.last_deal_date,
            best_attribution     = excluded.best_attribution
    """, (contact_id, contact_name, total_local, total_usd,
          total_cnt, last_date, best_type))
    conn.commit()
    conn.close()


# ── Queries ────────────────────────────────────────────────────────────────────

def get_top_contacts(limit: int = 10) -> list[dict]:
    """Return contacts sorted by total attributed revenue (USD)."""
    init_revenue_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_id, contact_name, total_attributed_usd,
               deal_count, last_deal_date, best_attribution
        FROM revenue_contacts
        ORDER BY total_attributed_usd DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{
        "contact_id":   r[0], "contact_name":  r[1],
        "total_usd":    round(r[2] or 0, 2),
        "deal_count":   r[3] or 0,
        "last_deal":    (r[4] or "")[:10],
        "best_type":    r[5] or "other",
        "icon":         ATTRIBUTION_TYPES.get(r[5] or "other", {}).get("icon","💰"),
        "color":        ATTRIBUTION_TYPES.get(r[5] or "other", {}).get("color","#8b949e"),
    } for r in rows]


def get_contact_deals(contact_id: str) -> list[dict]:
    """Return all deals attributed to one contact."""
    init_revenue_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT deal_name, deal_value, currency, deal_value_usd,
               attribution_type, deal_closed_date, days_to_close, notes
        FROM revenue_attributions WHERE contact_id=?
        ORDER BY deal_closed_date DESC
    """, (contact_id,)).fetchall()
    conn.close()
    return [{
        "deal_name":       r[0], "deal_value":    r[1],
        "currency":        r[2], "value_usd":     round(r[3] or 0, 2),
        "type":            r[4], "closed_date":   r[5],
        "days_to_close":   r[6], "notes":         r[7] or "",
        "icon":  ATTRIBUTION_TYPES.get(r[4], {}).get("icon", "💰"),
        "color": ATTRIBUTION_TYPES.get(r[4], {}).get("color","#8b949e"),
    } for r in rows]


def get_summary_stats(days: int = 365) -> dict:
    """Overall revenue stats for the last N days."""
    init_revenue_tables()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn   = sqlite3.connect(DB_PATH)

    total = conn.execute("""
        SELECT SUM(deal_value_usd), COUNT(*), AVG(days_to_close)
        FROM revenue_attributions WHERE logged_at >= ?
    """, (cutoff,)).fetchone()

    by_type = conn.execute("""
        SELECT attribution_type, SUM(deal_value_usd), COUNT(*)
        FROM revenue_attributions WHERE logged_at >= ?
        GROUP BY attribution_type ORDER BY SUM(deal_value_usd) DESC
    """, (cutoff,)).fetchall()

    conn.close()
    return {
        "total_usd":      round(total[0] or 0, 2),
        "deal_count":     total[1] or 0,
        "avg_days_close": round(total[2] or 0, 1) if total[2] else None,
        "by_type": [{
            "type":      r[0],
            "total_usd": round(r[1] or 0, 2),
            "count":     r[2],
            "icon":  ATTRIBUTION_TYPES.get(r[0], {}).get("icon","💰"),
            "color": ATTRIBUTION_TYPES.get(r[0], {}).get("color","#8b949e"),
        } for r in by_type],
    }


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_revenue_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM revenue_attributions").fetchone()[0]
    conn.close()
    if count > 0:
        return

    deals = [
        ("urn_rakib_001","Rakib Hossain","direct","LinkedIn","Backend Dev Contract",
         480000,"BDT","2026-03-15","2026-01-18",
         "Rakib reached out after birthday wish, converted to 3-month contract"),
        ("urn_nadia_002","Nadia Islam","referral","WhatsApp","UI/UX Project via Nadia",
         250000,"BDT","2026-04-20","2026-02-14",
         "Nadia referred her colleague at bKash for a redesign project"),
        ("urn_mim_004","Mim Chowdhury","intro","WhatsApp","Data Science Consulting",
         1200,"USD","2026-05-10","2026-03-01",
         "Mim introduced us to a Singapore-based startup"),
        ("urn_rakib_001","Rakib Hossain","referral","LinkedIn","SaaS Integration Work",
         320000,"BDT","2026-06-01","2026-01-18",
         "Second deal via Rakib referral to his ex-colleague"),
        ("urn_imran_006","Imran Hossain","partnership","Slack","Joint Venture Project",
         900,"USD","2026-05-25","2026-04-05",
         "Imran co-founded a project with us after reconnecting"),
    ]
    for cid, cname, atype, plat, dname, val, cur, closed, wish, notes in deals:
        log_attribution(cid, cname, dname, val, atype, cur, closed, wish, plat, notes)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Revenue Attribution", page_icon="💰",
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
    .contact-card{background:var(--surface);border:1px solid var(--border);
                  border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .deal-row{background:var(--surface);border:1px solid var(--border);
              border-radius:8px;padding:10px 14px;margin-bottom:6px;}
    .type-pill{display:inline-flex;align-items:center;gap:4px;font-size:0.63rem;
               font-weight:700;padding:2px 8px;border-radius:20px;
               text-transform:uppercase;letter-spacing:0.05em;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:12px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    .bar-wrap{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
    .bar-label{width:110px;font-size:0.74rem;flex-shrink:0;}
    .bar-track{flex:1;background:#0d1117;border-radius:4px;height:20px;overflow:hidden;}
    .bar-fill{height:100%;border-radius:4px;}
    .bar-val{width:60px;text-align:right;font-size:0.7rem;
             font-family:'JetBrains Mono',monospace;color:#8b949e;}
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

    init_revenue_tables()
    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">💰</span>
      <h1>Revenue Attribution</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    if "sel_cid" not in st.session_state:
        st.session_state.sel_cid  = None
        st.session_state.sel_name = ""

    stats = get_summary_stats(365)
    top   = get_top_contacts(limit=10)

    # Stats row
    m1, m2, m3, m4 = st.columns(4)
    avg_close = f"{stats['avg_days_close']}d" if stats["avg_days_close"] else "N/A"
    for col, lbl, val, color in [
        (m1, "Total Revenue (USD)", f"${stats['total_usd']:,.0f}", "#3fb950"),
        (m2, "Total Deals",         stats["deal_count"],           "#58a6ff"),
        (m3, "Avg Days to Close",   avg_close,                     "#d29922"),
        (m4, "Top Contributors",    len(top),                      "#f78166"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.2, 1], gap="large")

    with left:
        # Top contacts
        st.markdown('<div class="section-title">Top Revenue Contacts</div>',
                    unsafe_allow_html=True)
        max_usd = max((c["total_usd"] for c in top), default=1)
        for c in top:
            pct = int(c["total_usd"] / max_usd * 100) if max_usd else 0
            sel = c["contact_id"] == st.session_state.sel_cid
            st.markdown(f"""
            <div class="contact-card"
                 style="{'border-color:var(--accent);background:#1c1410' if sel else ''}">
              <div style="display:flex;align-items:center;justify-content:space-between;
                          margin-bottom:8px">
                <div style="font-weight:700;font-size:0.88rem">
                  {c['icon']} {c['contact_name']}
                </div>
                <div style="font-size:1rem;font-weight:700;color:#3fb950;
                            font-family:'JetBrains Mono',monospace">
                  ${c['total_usd']:,.0f}
                </div>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-bottom:6px">
                {c['deal_count']} deal{'s' if c['deal_count']!=1 else ''} ·
                Last: {c['last_deal'] or 'N/A'} ·
                <span style="color:{c['color']}">{ATTRIBUTION_TYPES.get(c['best_type'],{}).get('label','')}</span>
              </div>
              <div style="background:#0d1117;border-radius:4px;height:5px;overflow:hidden">
                <div style="width:{pct}%;height:100%;background:#3fb950;border-radius:4px">
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("View deals", key=f"vd_{c['contact_id']}",
                         use_container_width=True):
                st.session_state.sel_cid  = c["contact_id"]
                st.session_state.sel_name = c["contact_name"]
                st.rerun()

        # Attribution type breakdown
        st.markdown('<div class="section-title">By Attribution Type</div>',
                    unsafe_allow_html=True)
        max_type_usd = max((b["total_usd"] for b in stats["by_type"]), default=1)
        for b in stats["by_type"]:
            pct = int(b["total_usd"] / max_type_usd * 100) if max_type_usd else 0
            st.markdown(f"""
            <div class="bar-wrap">
              <div class="bar-label">{b['icon']} {ATTRIBUTION_TYPES.get(b['type'],{}).get('label',b['type'])}</div>
              <div class="bar-track">
                <div class="bar-fill" style="width:{pct}%;background:{b['color']}"></div>
              </div>
              <div class="bar-val">${b['total_usd']:,.0f}</div>
            </div>
            """, unsafe_allow_html=True)

    with right:
        # Deal detail for selected contact
        if st.session_state.sel_cid:
            st.markdown(f'<div class="section-title">'
                        f'{st.session_state.sel_name} — Deals</div>',
                        unsafe_allow_html=True)
            deals = get_contact_deals(st.session_state.sel_cid)
            for d in deals:
                close_str = f"{d['days_to_close']}d to close" \
                            if d["days_to_close"] is not None else ""
                st.markdown(f"""
                <div class="deal-row">
                  <div style="display:flex;align-items:center;
                              justify-content:space-between;margin-bottom:4px">
                    <div style="font-weight:700;font-size:0.84rem">{d['deal_name']}</div>
                    <div style="font-family:'JetBrains Mono',monospace;
                                font-weight:700;color:#3fb950;font-size:0.86rem">
                      ${d['value_usd']:,.0f}
                    </div>
                  </div>
                  <div style="font-size:0.68rem;color:#8b949e">
                    <span class="type-pill"
                          style="background:{d['color']}22;color:{d['color']};
                                 border:1px solid {d['color']}55">
                      {d['icon']} {ATTRIBUTION_TYPES.get(d['type'],{}).get('label','')}
                    </span>
                    · {d['deal_value']:,.0f} {d['currency']}
                    · {d['closed_date']}
                    {f'· {close_str}' if close_str else ''}
                  </div>
                  {f'<div style="font-size:0.72rem;color:#c9d1d9;margin-top:4px">{d["notes"]}</div>' if d["notes"] else ''}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Click a contact on the left to see their deals.")

        # Log new deal
        st.markdown('<div class="section-title" style="margin-top:20px">'
                    'Log New Deal</div>', unsafe_allow_html=True)
        with st.expander("Add attribution"):
            all_top  = get_top_contacts(100)
            all_names = [c["contact_name"] for c in all_top]
            lc1, lc2 = st.columns(2)
            with lc1:
                l_name  = st.selectbox("Contact",
                                       all_names if all_names else ["(none)"],
                                       label_visibility="collapsed", key="l_name")
                l_deal  = st.text_input("Deal name", label_visibility="collapsed",
                                        key="l_deal", placeholder="Project name")
            with lc2:
                l_val   = st.number_input("Value", min_value=0.0, value=100000.0,
                                          label_visibility="collapsed", key="l_val")
                l_cur   = st.selectbox("Currency", CURRENCIES,
                                       label_visibility="collapsed", key="l_cur")
            l_type  = st.selectbox("Type", list(ATTRIBUTION_TYPES.keys()),
                                   label_visibility="collapsed", key="l_type")
            l_notes = st.text_input("Notes (optional)",
                                    label_visibility="collapsed", key="l_notes")
            if st.button("Log Deal", type="primary", use_container_width=True):
                sel_c = next((c for c in all_top if c["contact_name"] == l_name),
                             None)
                if sel_c and l_deal:
                    log_attribution(
                        sel_c["contact_id"], l_name,
                        l_deal, l_val, l_type, l_cur,
                        notes=l_notes)
                    st.success(f"Deal logged ✅")
                    st.rerun()

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>Revenue Attribution</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_revenue_tables()
    _seed_demo()
    print("=== Revenue Attribution -- self test ===\n")
    stats = get_summary_stats(365)
    print(f"Total revenue : ${stats['total_usd']:,.2f} USD")
    print(f"Total deals   : {stats['deal_count']}")
    print(f"Avg to close  : {stats['avg_days_close']}d\n")
    print("By type:")
    for b in stats["by_type"]:
        print(f"  {b['icon']} {b['type']:<12} ${b['total_usd']:>8,.2f}  ({b['count']} deals)")
    print("\nTop contacts:")
    for c in get_top_contacts(5):
        print(f"  {c['icon']} {c['contact_name']:<22} ${c['total_usd']:>8,.2f}  "
              f"({c['deal_count']} deals)")
else:
    render_dashboard()
