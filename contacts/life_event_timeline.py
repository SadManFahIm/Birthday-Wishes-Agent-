"""
Life Event Timeline Merge — Birthday Wishes Agent v8.0
Builds a unified "important dates" calendar per contact by merging
birthday, promotion, job change, work anniversary, graduation, and
any other life events into one chronological timeline.

The agent checks this calendar daily and queues the right action
(wish / congratulation / check-in) for each upcoming event.

Integrates with: detection/job_change_detector.py,
                 detection/work_anniversary_detector.py,
                 automation/auto_timezone_scheduler.py, agent.py
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Optional

DB_PATH = Path("agent_history.db")

# ── Event type catalogue ──────────────────────────────────────────────────────

EVENT_TYPES = {
    "birthday":         {"label": "Birthday",          "icon": "🎂", "color": "#f78166", "priority": 5},
    "promotion":        {"label": "Promotion",         "icon": "🚀", "color": "#3fb950", "priority": 4},
    "job_change":       {"label": "New Job",           "icon": "💼", "color": "#58a6ff", "priority": 4},
    "work_anniversary": {"label": "Work Anniversary",  "icon": "🏆", "color": "#d29922", "priority": 3},
    "graduation":       {"label": "Graduation",        "icon": "🎓", "color": "#bc8cff", "priority": 4},
    "engagement":       {"label": "Engagement",        "icon": "💍", "color": "#f78166", "priority": 4},
    "marriage":         {"label": "Marriage",          "icon": "💒", "color": "#f78166", "priority": 5},
    "new_baby":         {"label": "New Baby",          "icon": "👶", "color": "#4fc3f7", "priority": 4},
    "business_launch":  {"label": "Business Launch",   "icon": "🏢", "color": "#3fb950", "priority": 3},
    "award":            {"label": "Award/Recognition", "icon": "🏅", "color": "#d29922", "priority": 3},
    "relocation":       {"label": "Relocation",        "icon": "🌍", "color": "#58a6ff", "priority": 2},
    "custom":           {"label": "Custom Event",      "icon": "📅", "color": "#8b949e", "priority": 1},
}

ACTION_MAP = {
    "birthday":         "send_birthday_wish",
    "promotion":        "send_congratulations",
    "job_change":       "send_congratulations",
    "work_anniversary": "send_anniversary_wish",
    "graduation":       "send_congratulations",
    "engagement":       "send_congratulations",
    "marriage":         "send_congratulations",
    "new_baby":         "send_congratulations",
    "business_launch":  "send_congratulations",
    "award":            "send_congratulations",
    "relocation":       "send_checkin",
    "custom":           "send_checkin",
}

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_timeline_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_life_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            event_date      TEXT NOT NULL,
            event_year      INTEGER,
            title           TEXT,
            description     TEXT,
            platform        TEXT,
            source          TEXT NOT NULL DEFAULT 'manual',
            actioned        INTEGER NOT NULL DEFAULT 0,
            action_type     TEXT,
            created_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_action_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            event_date      TEXT NOT NULL,
            action_taken    TEXT NOT NULL,
            actioned_at     TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Event CRUD ────────────────────────────────────────────────────────────────

def add_event(
    contact_id:   str,
    contact_name: str,
    event_type:   str,
    event_date:   str,
    title:        str = "",
    description:  str = "",
    platform:     str = "",
    source:       str = "manual",
) -> int:
    """
    Add one life event for a contact.

    Args:
        event_date: ISO format — YYYY-MM-DD (recurring yearly if no year needed)
                    or YYYY-MM-DD for one-time events like job changes.
    Returns:
        Inserted row ID.
    """
    init_timeline_tables()
    try:
        year = int(event_date[:4])
    except Exception:
        year = None
    action = ACTION_MAP.get(event_type, "send_checkin")
    conn   = sqlite3.connect(DB_PATH)
    cur    = conn.execute("""
        INSERT INTO contact_life_events
            (contact_id, contact_name, event_type, event_date, event_year,
             title, description, platform, source, action_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, event_type, event_date, year,
          title, description, platform, source, action,
          datetime.now().isoformat()))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_contact_timeline(contact_id: str) -> list[dict]:
    """Return all life events for a contact, newest first."""
    init_timeline_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT event_type, event_date, event_year, title, description,
               platform, source, actioned, action_type, id
        FROM contact_life_events
        WHERE contact_id = ?
        ORDER BY event_date DESC
    """, (contact_id,)).fetchall()
    conn.close()
    return [{
        "id": r[9], "event_type": r[0], "event_date": r[1], "year": r[2],
        "title": r[3] or "", "description": r[4] or "",
        "platform": r[5] or "", "source": r[6],
        "actioned": bool(r[7]), "action_type": r[8],
        "icon":  EVENT_TYPES.get(r[0], {}).get("icon",  "📅"),
        "label": EVENT_TYPES.get(r[0], {}).get("label", r[0]),
        "color": EVENT_TYPES.get(r[0], {}).get("color", "#8b949e"),
    } for r in rows]


def get_upcoming_events(days_ahead: int = 14) -> list[dict]:
    """
    Return all events across all contacts falling within the next N days.
    For recurring events (birthday, work_anniversary) compares MM-DD only.
    Sorted by how soon they occur.
    """
    init_timeline_tables()
    today     = date.today()
    upcoming  = []
    conn      = sqlite3.connect(DB_PATH)
    rows      = conn.execute("""
        SELECT contact_id, contact_name, event_type, event_date,
               title, platform, action_type, actioned, id
        FROM contact_life_events
        ORDER BY event_date ASC
    """).fetchall()
    conn.close()

    recurring = {"birthday", "work_anniversary"}

    for r in rows:
        cid, cname, etype, edate = r[0], r[1], r[2], r[3]
        actioned = bool(r[7])

        try:
            if etype in recurring:
                # Match MM-DD this year or next
                md = edate[5:10]
                for yr_offset in [0, 1]:
                    candidate = date.fromisoformat(f"{today.year + yr_offset}-{md}")
                    delta     = (candidate - today).days
                    if 0 <= delta <= days_ahead:
                        upcoming.append({
                            "id": r[8], "contact_id": cid, "contact_name": cname,
                            "event_type": etype, "event_date": str(candidate),
                            "days_away": delta, "title": r[4] or "",
                            "platform": r[5] or "", "action_type": r[6],
                            "actioned": actioned,
                            "icon":  EVENT_TYPES.get(etype, {}).get("icon",  "📅"),
                            "label": EVENT_TYPES.get(etype, {}).get("label", etype),
                            "color": EVENT_TYPES.get(etype, {}).get("color", "#8b949e"),
                            "priority": EVENT_TYPES.get(etype, {}).get("priority", 1),
                        })
                        break
            else:
                ev_date = date.fromisoformat(edate)
                delta   = (ev_date - today).days
                if 0 <= delta <= days_ahead and not actioned:
                    upcoming.append({
                        "id": r[8], "contact_id": cid, "contact_name": cname,
                        "event_type": etype, "event_date": edate,
                        "days_away": delta, "title": r[4] or "",
                        "platform": r[5] or "", "action_type": r[6],
                        "actioned": actioned,
                        "icon":  EVENT_TYPES.get(etype, {}).get("icon",  "📅"),
                        "label": EVENT_TYPES.get(etype, {}).get("label", etype),
                        "color": EVENT_TYPES.get(etype, {}).get("color", "#8b949e"),
                        "priority": EVENT_TYPES.get(etype, {}).get("priority", 1),
                    })
        except ValueError:
            continue

    upcoming.sort(key=lambda x: (x["days_away"], -x["priority"]))
    return upcoming


def mark_actioned(event_id: int, action_taken: str):
    """Mark an event as actioned after the wish/congratulation is sent."""
    init_timeline_tables()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute(
        "SELECT contact_id, contact_name, event_type, event_date "
        "FROM contact_life_events WHERE id=?", (event_id,)
    ).fetchone()
    if row:
        conn.execute("UPDATE contact_life_events SET actioned=1 WHERE id=?", (event_id,))
        conn.execute("""
            INSERT INTO event_action_log
                (contact_id, contact_name, event_type, event_date, action_taken, actioned_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (row[0], row[1], row[2], row[3], action_taken, datetime.now().isoformat()))
        conn.commit()
    conn.close()


def get_all_contact_summaries() -> list[dict]:
    """Return one summary per contact: name, event count, next upcoming."""
    init_timeline_tables()
    conn = sqlite3.connect(DB_PATH)
    ids  = conn.execute(
        "SELECT DISTINCT contact_id, contact_name FROM contact_life_events"
    ).fetchall()
    conn.close()
    result = []
    for cid, cname in ids:
        events = get_contact_timeline(cid)
        result.append({
            "contact_id":   cid, "contact_name": cname,
            "event_count":  len(events),
            "event_types":  list({e["event_type"] for e in events}),
        })
    return result


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_timeline_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM contact_life_events").fetchone()[0]
    conn.close()
    if count > 0:
        return

    today = date.today()
    demo  = [
        ("urn_rakib_001","Rakib Hossain","LinkedIn",[
            ("birthday",        f"{today.year}-06-18", "Birthday"),
            ("work_anniversary",f"{today.year}-03-01", "3 years at Pathao"),
            ("promotion",       f"{today.year - 1}-11-15", "Promoted to Senior Engineer"),
        ]),
        ("urn_nadia_002","Nadia Islam","WhatsApp",[
            ("birthday",        f"{today.year}-06-20", "Birthday"),
            ("job_change",      f"{today.year}-01-10", "Joined bKash as Product Designer"),
            ("award",           f"{today.year - 1}-08-22", "Best UX Design Award"),
        ]),
        ("urn_tanvir_003","Tanvir Ahmed","LinkedIn",[
            ("birthday",        f"{today.year}-05-30", "Birthday"),
            ("business_launch", f"{today.year - 1}-04-05", "Launched ShopUp v2"),
            ("work_anniversary",f"{today.year}-04-05", "5 years at ShopUp"),
        ]),
        ("urn_mim_004","Mim Chowdhury","WhatsApp",[
            ("birthday",        f"{today.year}-06-21", "Birthday"),
            ("graduation",      f"{today.year - 2}-12-01", "MSc Data Science"),
            ("job_change",      f"{today.year - 1}-02-14", "Joined Brain Station 23"),
        ]),
    ]
    for cid, cname, plat, events in demo:
        for etype, edate, title in events:
            add_event(cid, cname, etype, edate, title=title,
                      platform=plat, source="demo")


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Life Event Timeline", page_icon="📅",
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
    .ev-card{background:var(--surface);border:1px solid var(--border);
             border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .ev-row{display:flex;align-items:center;gap:10px;margin-bottom:4px;}
    .ev-icon{font-size:1.2rem;flex-shrink:0;}
    .ev-title{font-weight:700;font-size:0.86rem;}
    .ev-meta{font-size:0.68rem;color:var(--muted);}
    .day-pill{display:inline-flex;font-size:0.65rem;font-weight:700;
              padding:2px 8px;border-radius:20px;text-transform:uppercase;
              letter-spacing:0.05em;}
    .tl-item{position:relative;padding-left:26px;margin-bottom:14px;}
    .tl-dot{position:absolute;left:0;top:4px;width:14px;height:14px;
            border-radius:50%;border:2px solid var(--bg);}
    .tl-line{position:absolute;left:6px;top:18px;bottom:-14px;
             width:2px;background:var(--border);}
    .c-card{background:var(--surface);border:1px solid var(--border);
            border-radius:9px;padding:10px 13px;margin-bottom:6px;cursor:pointer;}
    .c-card.sel{border-color:var(--accent);background:#1c1410;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:var(--blue);background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);
        border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📅</span>
      <h1>Life Event Timeline</h1>
      <span class="cc-badge">v8.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    if "sel_cid" not in st.session_state:
        st.session_state.sel_cid  = "urn_rakib_001"
        st.session_state.sel_name = "Rakib Hossain"

    top_left, top_right = st.columns([1, 1], gap="large")

    # ── Upcoming events strip ──────────────────────────────────────────────────
    with top_left:
        days_ahead = st.slider("Upcoming window (days)", 7, 60, 14,
                               label_visibility="collapsed")
        st.markdown(f'<div class="section-title">Upcoming — next {days_ahead} days</div>',
                    unsafe_allow_html=True)
        upcoming = get_upcoming_events(days_ahead)
        if not upcoming:
            st.info("No events in this window.")
        for ev in upcoming:
            d = ev["days_away"]
            if d == 0:
                day_str, day_color = "Today",    "#f78166"
            elif d == 1:
                day_str, day_color = "Tomorrow", "#d29922"
            else:
                day_str, day_color = f"In {d}d", "#58a6ff"

            done_tag = ' <span style="font-size:0.6rem;color:#8b949e">(actioned)</span>' \
                       if ev["actioned"] else ""
            st.markdown(f"""
            <div class="ev-card">
              <div class="ev-row">
                <span class="ev-icon">{ev['icon']}</span>
                <div style="flex:1">
                  <div class="ev-title">{ev['contact_name']}{done_tag}</div>
                  <div class="ev-meta">{ev['label']} · {ev['event_date']}</div>
                </div>
                <span class="day-pill"
                      style="background:{day_color}22;color:{day_color};
                             border:1px solid {day_color}55">{day_str}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)
            if not ev["actioned"]:
                if st.button(f"✅ Mark actioned", key=f"act_{ev['id']}",
                             use_container_width=True):
                    mark_actioned(ev["id"], ev["action_type"])
                    st.rerun()

    # ── Add event form ─────────────────────────────────────────────────────────
    with top_right:
        st.markdown('<div class="section-title">Add Event</div>', unsafe_allow_html=True)
        contacts = get_all_contact_summaries()
        names    = [c["contact_name"] for c in contacts]
        sel_name = st.selectbox("Contact", names, label_visibility="collapsed",
                                key="add_contact")
        sel_c    = next(c for c in contacts if c["contact_name"] == sel_name)
        ev_type  = st.selectbox("Event type", list(EVENT_TYPES.keys()),
                                label_visibility="collapsed", key="add_type")
        ev_date  = st.date_input("Date", label_visibility="collapsed", key="add_date")
        ev_title = st.text_input("Title (optional)", label_visibility="collapsed",
                                 key="add_title", placeholder="e.g. Promoted to Lead")
        if st.button("➕ Add to Timeline", type="primary", use_container_width=True):
            add_event(sel_c["contact_id"], sel_name, ev_type,
                      str(ev_date), title=ev_title, source="manual")
            st.success(f"Event added ✅")
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 2], gap="large")

    # ── Contact list ──────────────────────────────────────────────────────────
    with left:
        st.markdown('<div class="section-title">Contacts</div>', unsafe_allow_html=True)
        for c in contacts:
            icons = " ".join(
                EVENT_TYPES.get(et, {}).get("icon", "")
                for et in c["event_types"]
            )
            sel = c["contact_id"] == st.session_state.sel_cid
            st.markdown(f"""
            <div class="c-card {'sel' if sel else ''}">
              <div style="font-weight:700;font-size:0.85rem">{c['contact_name']}</div>
              <div style="font-size:0.68rem;color:#8b949e">
                {c['event_count']} event{'s' if c['event_count']!=1 else ''} · {icons}
              </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("View", key=f"sel_{c['contact_id']}", use_container_width=True):
                st.session_state.sel_cid  = c["contact_id"]
                st.session_state.sel_name = c["contact_name"]
                st.rerun()

    # ── Per-contact timeline ──────────────────────────────────────────────────
    with right:
        cid   = st.session_state.sel_cid
        cname = st.session_state.sel_name
        st.markdown(f'<div class="section-title">{cname} — Timeline</div>',
                    unsafe_allow_html=True)

        events = get_contact_timeline(cid)
        if not events:
            st.info("No events recorded yet.")
        else:
            for i, ev in enumerate(events):
                is_last  = i == len(events) - 1
                line_html = "" if is_last else '<div class="tl-line"></div>'
                done_tag  = ' <span style="font-size:0.62rem;color:#8b949e">✓ actioned</span>' \
                            if ev["actioned"] else ""
                st.markdown(f"""
                <div class="tl-item">
                  <div class="tl-dot" style="background:{ev['color']}"></div>
                  {line_html}
                  <div class="ev-card" style="margin-bottom:0">
                    <div class="ev-row">
                      <span class="ev-icon">{ev['icon']}</span>
                      <div style="flex:1">
                        <div class="ev-title">
                          {ev['title'] or ev['label']}{done_tag}
                        </div>
                        <div class="ev-meta">
                          {ev['label']} · {ev['event_date']}
                          {f' · {ev["platform"]}' if ev.get('platform') else ''}
                        </div>
                        {f'<div style="font-size:0.73rem;color:#c9d1d9;margin-top:4px">{ev["description"]}</div>' if ev.get("description") else ''}
                      </div>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">8.0</code></span>
      <span>Life Event Timeline Merge</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_timeline_tables()
    _seed_demo()
    print("=== Life Event Timeline Merge — self test ===\n")
    contacts = get_all_contact_summaries()
    print(f"{len(contacts)} contacts loaded:")
    for c in contacts:
        icons = " ".join(EVENT_TYPES.get(et, {}).get("icon", "") for et in c["event_types"])
        print(f"  {c['contact_name']:<22} {c['event_count']} events  {icons}")
    upcoming = get_upcoming_events(90)
    print(f"\nUpcoming (90 days): {len(upcoming)} events")
    for ev in upcoming[:5]:
        print(f"  {ev['icon']} {ev['contact_name']:<18} {ev['label']:<20} in {ev['days_away']}d")
else:
    render_dashboard()
