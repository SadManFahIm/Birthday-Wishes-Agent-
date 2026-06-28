"""
Smart Send-Time Optimizer — Birthday Wishes Agent v8.0
Tracks each contact's platform-specific activity patterns from reply timestamps,
then predicts the optimal send window so wishes arrive when the contact is
most likely online — not just in their timezone, but in their active hours.

Per-platform, per-contact:
  • Learns from past reply timestamps (when they actually responded)
  • Builds an hour-of-day activity histogram
  • Picks the peak active window for the next occurrence
  • Falls back to timezone-aware 9 AM if no data

Integrates with: agent.py, batch_approve_queue.py, workflow_builder.py
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta, date, time
from collections import Counter
from typing import Optional
import math

DB_PATH = Path("agent_history.db")

# ── Platform-specific defaults (fallback when no data) ────────────────────────
PLATFORM_DEFAULTS = {
    "LinkedIn":  {"peak_hours": [8, 9, 12, 17, 18], "label": "Morning commute / lunch / end of workday"},
    "WhatsApp":  {"peak_hours": [9, 13, 20, 21],    "label": "Morning / after lunch / evening"},
    "Facebook":  {"peak_hours": [12, 13, 20, 21],   "label": "Lunch / evening browse"},
    "Instagram": {"peak_hours": [11, 13, 19, 20, 21],"label": "Late morning / evening scroll"},
    "Twitter/X": {"peak_hours": [8, 9, 12, 17, 18], "label": "News hours"},
    "Slack":     {"peak_hours": [9, 10, 14, 15],    "label": "Work hours"},
}

# Quality tiers for confidence
CONFIDENCE_TIERS = {
    "high":   {"min_samples": 10, "label": "High confidence", "color": "#3fb950"},
    "medium": {"min_samples": 4,  "label": "Medium confidence","color": "#d29922"},
    "low":    {"min_samples": 1,  "label": "Low confidence",   "color": "#f85149"},
    "default":{"min_samples": 0,  "label": "Platform default", "color": "#8b949e"},
}

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_optimizer_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contact_activity_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id   TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            platform     TEXT NOT NULL,
            event_type   TEXT NOT NULL DEFAULT 'reply',
            event_hour   INTEGER NOT NULL,
            event_dow    INTEGER NOT NULL,
            event_ts     TEXT NOT NULL,
            logged_at    TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS send_time_profile (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            platform        TEXT NOT NULL,
            peak_hours_json TEXT NOT NULL,
            sample_count    INTEGER NOT NULL DEFAULT 0,
            confidence      TEXT NOT NULL DEFAULT 'default',
            last_updated    TEXT NOT NULL,
            UNIQUE(contact_id, platform)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_sends (
            id           TEXT PRIMARY KEY,
            contact_id   TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            platform     TEXT NOT NULL,
            wish_text    TEXT NOT NULL,
            scheduled_ts TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'scheduled',
            created_at   TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Activity logging ──────────────────────────────────────────────────────────

def log_activity(
    contact_id:   str,
    contact_name: str,
    platform:     str,
    event_type:   str = "reply",
    event_ts:     Optional[datetime] = None,
):
    """
    Record a contact activity event (reply, reaction, view).
    Call this whenever the agent receives a reply or detects engagement.

    Args:
        contact_id:   Unique contact identifier.
        contact_name: Human-readable name.
        platform:     LinkedIn / WhatsApp / etc.
        event_type:   reply | reaction | message_open | post_like
        event_ts:     Timestamp of the event. Defaults to now.
    """
    init_optimizer_tables()
    ts  = event_ts or datetime.now()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO contact_activity_log
            (contact_id, contact_name, platform, event_type, event_hour, event_dow, event_ts, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        contact_id, contact_name, platform, event_type,
        ts.hour, ts.weekday(),
        ts.isoformat(), datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()
    _update_profile(contact_id, platform)


def _update_profile(contact_id: str, platform: str):
    """Recompute and cache the send-time profile after each new activity log."""
    init_optimizer_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT event_hour FROM contact_activity_log WHERE contact_id=? AND platform=?",
        (contact_id, platform),
    ).fetchall()
    hours = [r[0] for r in rows]

    if not hours:
        conn.close()
        return

    peak_hours = _compute_peak_hours(hours)
    n          = len(hours)
    confidence = _confidence_tier(n)

    conn.execute("""
        INSERT INTO send_time_profile
            (contact_id, platform, peak_hours_json, sample_count, confidence, last_updated)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id, platform) DO UPDATE SET
            peak_hours_json = excluded.peak_hours_json,
            sample_count    = excluded.sample_count,
            confidence      = excluded.confidence,
            last_updated    = excluded.last_updated
    """, (contact_id, platform, json.dumps(peak_hours), n, confidence, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def _compute_peak_hours(hours: list[int], top_n: int = 3) -> list[int]:
    """
    From a list of activity hours, return the top N peak hours.
    Uses a smoothed histogram (each hour contributes ±1 adjacent hours at half weight)
    to avoid gaps from sparse data.
    """
    if not hours:
        return [9]

    raw = Counter(hours)

    # Smooth: spread weight to adjacent hours
    smoothed = Counter()
    for h, count in raw.items():
        smoothed[h] += count
        smoothed[(h - 1) % 24] += count * 0.5
        smoothed[(h + 1) % 24] += count * 0.5

    return [h for h, _ in smoothed.most_common(top_n)]


def _confidence_tier(sample_count: int) -> str:
    if sample_count >= CONFIDENCE_TIERS["high"]["min_samples"]:
        return "high"
    if sample_count >= CONFIDENCE_TIERS["medium"]["min_samples"]:
        return "medium"
    if sample_count >= CONFIDENCE_TIERS["low"]["min_samples"]:
        return "low"
    return "default"


# ── Profile loading ───────────────────────────────────────────────────────────

def load_send_time_profile(contact_id: str, platform: str) -> dict:
    """
    Load cached send-time profile for a contact+platform.
    Falls back to platform defaults if no data.
    """
    init_optimizer_tables()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute(
        "SELECT peak_hours_json, sample_count, confidence, last_updated "
        "FROM send_time_profile WHERE contact_id=? AND platform=?",
        (contact_id, platform),
    ).fetchone()
    conn.close()

    if row:
        return {
            "peak_hours":  json.loads(row[0]),
            "sample_count":row[1],
            "confidence":  row[2],
            "last_updated":row[3],
            "source":      "learned",
        }

    # Platform default fallback
    defaults = PLATFORM_DEFAULTS.get(platform, PLATFORM_DEFAULTS["LinkedIn"])
    return {
        "peak_hours":  defaults["peak_hours"],
        "sample_count":0,
        "confidence":  "default",
        "last_updated":None,
        "source":      "default",
    }


# ── Optimal send-time computation ─────────────────────────────────────────────

def get_optimal_send_time(
    contact_id:       str,
    contact_name:     str,
    platform:         str,
    target_date:      Optional[date] = None,
    timezone_offset:  int = 0,
    verbose:          bool = True,
) -> dict:
    """
    Compute the optimal datetime to send a wish to this contact on this platform.

    Args:
        contact_id:      Unique contact identifier.
        contact_name:    Human-readable name (for logging).
        platform:        Target platform.
        target_date:     Date to send on. Defaults to today.
        timezone_offset: Contact's UTC offset in hours (e.g. +6 for Bangladesh).
        verbose:         Print result to console.

    Returns:
        {
          optimal_utc:    datetime — best send time in UTC,
          optimal_local:  datetime — in contact's local time,
          peak_hours:     list[int],
          confidence:     str,
          sample_count:   int,
          source:         str,
          explanation:    str,
        }
    """
    init_optimizer_tables()
    target      = target_date or date.today()
    profile     = load_send_time_profile(contact_id, platform)
    peak_hours  = sorted(profile["peak_hours"])
    confidence  = profile["confidence"]

    # Pick the earliest peak hour that's still in the future (local time)
    now_local   = datetime.utcnow() + timedelta(hours=timezone_offset)
    chosen_hour = None

    for h in peak_hours:
        candidate = datetime(target.year, target.month, target.day, h, 0, 0)
        if candidate > now_local:
            chosen_hour = h
            break

    # All peak hours already passed today → use first peak tomorrow
    if chosen_hour is None:
        tomorrow    = target + timedelta(days=1)
        chosen_hour = peak_hours[0]
        target      = tomorrow

    local_dt = datetime(target.year, target.month, target.day, chosen_hour, 0, 0)
    utc_dt   = local_dt - timedelta(hours=timezone_offset)

    tier_info = CONFIDENCE_TIERS.get(confidence, CONFIDENCE_TIERS["default"])
    explanation = (
        f"Sending at {local_dt.strftime('%H:%M')} local time "
        f"({tier_info['label']}, {profile['sample_count']} activity samples). "
        f"Peak hours for {platform}: {[f'{h:02d}:00' for h in peak_hours]}."
    )

    if verbose:
        print(f"[SendTimeOptimizer] {contact_name} on {platform}")
        print(f"  Confidence:   {confidence} ({profile['sample_count']} samples)")
        print(f"  Peak hours:   {peak_hours}")
        print(f"  Optimal UTC:  {utc_dt.strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"  Optimal local:{local_dt.strftime('%Y-%m-%d %H:%M')} (UTC{timezone_offset:+d})")

    return {
        "optimal_utc":   utc_dt,
        "optimal_local": local_dt,
        "peak_hours":    peak_hours,
        "confidence":    confidence,
        "confidence_color": tier_info["color"],
        "sample_count":  profile["sample_count"],
        "source":        profile["source"],
        "explanation":   explanation,
    }


# ── Schedule a send ───────────────────────────────────────────────────────────

def schedule_wish(
    contact_id:   str,
    contact_name: str,
    platform:     str,
    wish_text:    str,
    scheduled_ts: datetime,
) -> str:
    """Persist a scheduled wish. Returns the schedule ID."""
    import uuid as _uuid
    init_optimizer_tables()
    sid  = str(_uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO scheduled_sends
            (id, contact_id, contact_name, platform, wish_text, scheduled_ts, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?)
    """, (sid, contact_id, contact_name, platform, wish_text,
          scheduled_ts.isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return sid


def get_pending_scheduled(cutoff_minutes: int = 5) -> list[dict]:
    """Return scheduled wishes whose send time is within `cutoff_minutes` from now."""
    init_optimizer_tables()
    now  = datetime.utcnow()
    soon = now + timedelta(minutes=cutoff_minutes)
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, contact_id, contact_name, platform, wish_text, scheduled_ts
        FROM scheduled_sends
        WHERE status='scheduled' AND scheduled_ts <= ?
        ORDER BY scheduled_ts ASC
    """, (soon.isoformat(),)).fetchall()
    conn.close()
    return [{
        "id": r[0], "contact_id": r[1], "contact_name": r[2],
        "platform": r[3], "wish_text": r[4], "scheduled_ts": r[5],
    } for r in rows]


def mark_scheduled_sent(schedule_id: str):
    init_optimizer_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE scheduled_sends SET status='sent' WHERE id=?", (schedule_id,))
    conn.commit()
    conn.close()


# ── Bulk optimizer (for agent.py daily run) ───────────────────────────────────

def optimize_batch(
    contacts: list[dict],
    dry_run:  bool = True,
    verbose:  bool = True,
) -> list[dict]:
    """
    For a list of contacts (each with id, name, platform, timezone_offset, wish_text),
    compute optimal send times and return a schedule plan.

    Args:
        contacts: List of dicts with keys:
                  contact_id, contact_name, platform, timezone_offset, wish_text
        dry_run:  If True, compute but don't persist schedules.
        verbose:  Print schedule to console.

    Returns:
        List of schedule dicts sorted by optimal_utc ascending.
    """
    init_optimizer_tables()
    schedule = []

    for c in contacts:
        result = get_optimal_send_time(
            c["contact_id"], c["contact_name"],
            c["platform"], timezone_offset=c.get("timezone_offset", 0),
            verbose=verbose,
        )
        entry = {
            "contact_id":   c["contact_id"],
            "contact_name": c["contact_name"],
            "platform":     c["platform"],
            "wish_text":    c.get("wish_text", ""),
            "optimal_utc":  result["optimal_utc"],
            "optimal_local":result["optimal_local"],
            "confidence":   result["confidence"],
            "explanation":  result["explanation"],
        }
        if not dry_run:
            entry["schedule_id"] = schedule_wish(
                c["contact_id"], c["contact_name"], c["platform"],
                c.get("wish_text",""), result["optimal_utc"],
            )
        schedule.append(entry)

    schedule.sort(key=lambda x: x["optimal_utc"])

    if verbose:
        print(f"\n[SendTimeOptimizer] Batch schedule ({len(schedule)} contacts):")
        for s in schedule:
            print(f"  {s['optimal_local'].strftime('%H:%M')} — {s['contact_name']} via {s['platform']} ({s['confidence']})")

    return schedule


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_optimizer_dashboard():
    """
    Full Streamlit page — run via:
        streamlit run smart_send_time_optimizer.py
    """
    try:
        import streamlit as st
    except ImportError:
        print("Streamlit not available.")
        return

    st.set_page_config(page_title="Send-Time Optimizer", page_icon="⏰", layout="wide",
                       initial_sidebar_state="collapsed")

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    :root { --bg:#0d1117;--surface:#161b22;--border:#30363d;--accent:#f78166;
            --green:#3fb950;--yellow:#d29922;--red:#f85149;--blue:#58a6ff;
            --muted:#8b949e;--text:#e6edf3; }
    .stApp { background:var(--bg); color:var(--text); }
    .cc-header { display:flex;align-items:center;gap:14px;padding:18px 0 10px;
                 border-bottom:1px solid var(--border);margin-bottom:24px; }
    .cc-header h1 { font-size:1.4rem;font-weight:700;letter-spacing:-0.02em;margin:0; }
    .cc-badge { background:var(--accent);color:#fff;font-size:0.65rem;font-weight:700;
                padding:2px 8px;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase; }
    .cc-version { margin-left:auto;font-size:0.75rem;color:var(--muted);font-family:'JetBrains Mono',monospace; }
    .section-title { font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;
                     color:var(--muted);margin:22px 0 10px;display:flex;align-items:center;gap:8px; }
    .section-title::after { content:'';flex:1;height:1px;background:var(--border); }
    .sched-row { background:var(--surface);border:1px solid var(--border);border-radius:10px;
                 padding:14px 16px;margin-bottom:8px; }
    .sched-name { font-weight:700;font-size:0.88rem; }
    .sched-meta { font-size:0.72rem;color:var(--muted);margin-top:2px; }
    .conf-chip { display:inline-flex;font-size:0.65rem;font-weight:700;padding:2px 8px;
                 border-radius:20px;text-transform:uppercase;letter-spacing:0.06em; }
    .heat-cell { display:inline-block;width:28px;height:28px;border-radius:4px;
                 font-size:0.6rem;text-align:center;line-height:28px;
                 font-family:'JetBrains Mono',monospace;margin:1px; }
    div[data-testid="stButton"] > button { background:var(--surface);border:1px solid var(--border);
        color:var(--text);border-radius:8px;font-size:0.8rem;font-weight:500;transition:all 0.15s; }
    div[data-testid="stButton"] > button:hover { border-color:var(--blue);background:#1c2128; }
    div[data-testid="stButton"] > button[kind="primary"] { background:var(--accent);border-color:var(--accent);color:#fff; }
    ::-webkit-scrollbar { width:6px; } ::-webkit-scrollbar-track { background:var(--bg); }
    ::-webkit-scrollbar-thumb { background:var(--border);border-radius:3px; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">⏰</span>
      <h1>Smart Send-Time Optimizer</h1>
      <span class="cc-badge">v8.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Demo contacts ─────────────────────────────────────────────────────────
    DEMO = [
        {"contact_id":"urn_rakib_001","contact_name":"Rakib Hossain","platform":"LinkedIn",
         "timezone_offset":6,"wish_text":"Happy Birthday Rakib! 🎉"},
        {"contact_id":"urn_nadia_002","contact_name":"Nadia Islam","platform":"WhatsApp",
         "timezone_offset":6,"wish_text":"Happy Birthday Nadia! 😊"},
        {"contact_id":"urn_tanvir_003","contact_name":"Tanvir Ahmed","platform":"LinkedIn",
         "timezone_offset":6,"wish_text":"Happy Birthday Tanvir."},
        {"contact_id":"urn_imran_006","contact_name":"Imran Hossain","platform":"Slack",
         "timezone_offset":0,"wish_text":"Happy Birthday Imran! 🚀"},
    ]

    # Seed some demo activity
    _seed_demo_activity()

    left, right = st.columns([1.5, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Today\'s Send Schedule</div>', unsafe_allow_html=True)

        if "schedule" not in st.session_state:
            st.session_state.schedule = []

        c1, c2 = st.columns(2)
        with c1:
            if st.button("⚡ Compute Optimal Schedule", type="primary", use_container_width=True):
                import time as _time
                with st.spinner("Analyzing activity patterns..."):
                    _time.sleep(0.5)
                    st.session_state.schedule = optimize_batch(DEMO, dry_run=True, verbose=False)
                st.rerun()
        with c2:
            if st.button("📅 Schedule All", use_container_width=True,
                         disabled=not st.session_state.schedule):
                optimize_batch(DEMO, dry_run=False, verbose=False)
                st.success("All wishes scheduled! ✅")

        if not st.session_state.schedule:
            st.markdown('<div style="color:#8b949e;font-size:0.82rem;padding:20px 0">'
                        'Click "Compute Optimal Schedule" to see send times.</div>',
                        unsafe_allow_html=True)
        else:
            for s in st.session_state.schedule:
                tier   = CONFIDENCE_TIERS.get(s["confidence"], CONFIDENCE_TIERS["default"])
                plat_icon = {"LinkedIn":"💼","WhatsApp":"💬","Slack":"⚡","Facebook":"📘",
                             "Instagram":"📸","Twitter/X":"🐦"}.get(s["platform"],"📱")
                st.markdown(f"""
                <div class="sched-row">
                  <div style="display:flex;align-items:baseline;justify-content:space-between">
                    <div class="sched-name">{s['contact_name']}</div>
                    <div style="font-size:1.1rem;font-weight:700;color:{tier['color']}">
                      {s['optimal_local'].strftime('%H:%M')}
                      <span style="font-size:0.7rem;color:#8b949e;font-weight:400">
                        local · {s['optimal_utc'].strftime('%H:%M')} UTC
                      </span>
                    </div>
                  </div>
                  <div class="sched-meta">
                    {plat_icon} {s['platform']} ·
                    <span class="conf-chip" style="background:{tier['color']}22;color:{tier['color']};
                          border:1px solid {tier['color']}44">{tier['label']}</span>
                  </div>
                  <div style="font-size:0.72rem;color:#8b949e;margin-top:6px">{s['explanation']}</div>
                </div>
                """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Activity Heatmap</div>', unsafe_allow_html=True)

        contact_names = [d["contact_name"] for d in DEMO]
        selected_name = st.selectbox("Contact", contact_names, label_visibility="collapsed")
        selected      = next(d for d in DEMO if d["contact_name"] == selected_name)

        _render_heatmap(selected["contact_id"], selected["platform"])

        st.markdown('<div class="section-title">Log Activity (simulate reply)</div>', unsafe_allow_html=True)
        plat_opts = list(PLATFORM_DEFAULTS.keys())
        log_plat  = st.selectbox("Platform", plat_opts, label_visibility="collapsed",
                                 key="log_plat")
        log_hour  = st.slider("Reply hour (local)", 0, 23, 9)
        if st.button("📥 Log Reply", use_container_width=True):
            ts = datetime.now().replace(hour=log_hour, minute=0, second=0)
            log_activity(selected["contact_id"], selected["contact_name"], log_plat,
                         event_type="reply", event_ts=ts)
            st.success(f"Logged reply at {log_hour:02d}:00 for {selected['contact_name']} on {log_plat}")
            st.rerun()

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;padding:1px 5px;border-radius:4px">8.0</code></span>
      <span>Smart Send-Time Optimizer</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


def _render_heatmap(contact_id: str, platform: str):
    """Render a 24-hour activity heatmap for a contact+platform."""
    try:
        import streamlit as st
    except ImportError:
        return

    init_optimizer_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT event_hour, COUNT(*) as cnt FROM contact_activity_log "
        "WHERE contact_id=? AND platform=? GROUP BY event_hour",
        (contact_id, platform),
    ).fetchall()
    conn.close()

    hour_counts = {r[0]: r[1] for r in rows}
    max_cnt     = max(hour_counts.values()) if hour_counts else 1
    profile     = load_send_time_profile(contact_id, platform)
    peak_set    = set(profile["peak_hours"])

    cells = ""
    for h in range(24):
        cnt     = hour_counts.get(h, 0)
        opacity = 0.15 + (cnt / max_cnt) * 0.85 if max_cnt > 0 else 0.15
        is_peak = h in peak_set
        bg      = f"rgba(63,185,80,{opacity:.2f})" if cnt > 0 else "#21262d"
        border  = "2px solid #f78166" if is_peak else "1px solid #30363d"
        label   = f"{h:02d}"
        cells  += (f'<div class="heat-cell" style="background:{bg};border:{border};'
                   f'color:{"#e6edf3" if cnt>0 else "#8b949e"}" title="{cnt} replies at {h:02d}:00">'
                   f'{label}</div>')

    st.markdown(f"""
    <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px;">
      <div style="font-size:0.7rem;color:#8b949e;margin-bottom:8px">
        Hour-of-day activity · {profile['sample_count']} samples ·
        <span style="color:#f78166">■</span> peak hours
      </div>
      <div>{cells}</div>
      <div style="font-size:0.68rem;color:#8b949e;margin-top:8px">
        Peak hours: {', '.join(f'{h:02d}:00' for h in sorted(profile['peak_hours']))}
        ({CONFIDENCE_TIERS.get(profile['confidence'],CONFIDENCE_TIERS['default'])['label']})
      </div>
    </div>
    """, unsafe_allow_html=True)


def _seed_demo_activity():
    """Seed realistic demo activity if table is empty."""
    init_optimizer_tables()
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM contact_activity_log").fetchone()[0]
    conn.close()
    if count > 0:
        return

    import random as _random
    demo_replies = [
        ("urn_rakib_001","Rakib Hossain","LinkedIn",  [8,9,8,17,18,9,12,17,8,9,12,18]),
        ("urn_nadia_002","Nadia Islam",  "WhatsApp",  [20,21,9,20,21,13,21,20,9,21]),
        ("urn_tanvir_003","Tanvir Ahmed","LinkedIn",  [12,13,12,17,12]),
        ("urn_imran_006","Imran Hossain","Slack",     [10,9,14,10,15,9,10,14]),
    ]
    now = datetime.now()
    for cid, cname, plat, hours in demo_replies:
        for i, h in enumerate(hours):
            ts = now - timedelta(days=_random.randint(1,90), hours=_random.randint(0,2))
            ts = ts.replace(hour=h, minute=_random.randint(0,59))
            log_activity(cid, cname, plat, event_ts=ts)


# ── CLI self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_optimizer_tables()
    _seed_demo_activity()

    print("=== Smart Send-Time Optimizer — self test ===\n")

    contacts = [
        {"contact_id":"urn_rakib_001","contact_name":"Rakib Hossain",
         "platform":"LinkedIn","timezone_offset":6,"wish_text":"Happy Birthday Rakib!"},
        {"contact_id":"urn_nadia_002","contact_name":"Nadia Islam",
         "platform":"WhatsApp","timezone_offset":6,"wish_text":"Happy Birthday Nadia!"},
        {"contact_id":"urn_imran_006","contact_name":"Imran Hossain",
         "platform":"Slack","timezone_offset":0,"wish_text":"Happy Birthday Imran!"},
        {"contact_id":"urn_new_000","contact_name":"New Contact (no history)",
         "platform":"LinkedIn","timezone_offset":6,"wish_text":"Happy Birthday!"},
    ]

    schedule = optimize_batch(contacts, dry_run=True)

    print("\n── Final Schedule ──")
    for s in schedule:
        tier = CONFIDENCE_TIERS.get(s["confidence"], CONFIDENCE_TIERS["default"])
        print(f"  {s['optimal_local'].strftime('%H:%M')} local │ "
              f"{s['contact_name']:<22} │ {s['platform']:<10} │ {tier['label']}")

# Entry point for `streamlit run smart_send_time_optimizer.py`
else:
    render_optimizer_dashboard()
