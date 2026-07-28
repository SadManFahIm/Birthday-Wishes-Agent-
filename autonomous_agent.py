"""
Autonomous Agent Mode -- Birthday Wishes Agent v10.0
The agent runs its full daily cycle independently — deciding
who to contact, what to send, when to send it, and whether
to follow up — with zero human intervention required.

Decision engine:
  For each contact in the network, the agent scores:
    - urgency    (is birthday today / in N days?)
    - priority   (tier, VIP status, last interaction)
    - channel    (best platform based on past reply rates)
    - timing     (optimal send time from smart_send_time_optimizer)
    - action     (wish / follow-up / check-in / decay alert / skip)

  Decisions are logged, explainable, and overridable.

Safety rails:
  - Pause if error rate > 40% (auto_pause_on_anomaly)
  - Never send to same contact twice in 300 days
  - Daily send cap per platform (rate limiter)
  - Dry-run mode always available

Run:
  python autonomous_agent.py run                # dry run
  python autonomous_agent.py run --live         # live sends
  python autonomous_agent.py decide             # print decisions only
  python autonomous_agent.py status             # show last run summary

Integrates with: langgraph_workflow.py, model_config.py,
                 redis_cache.py, fastapi_backend.py, agent.py
"""

import sqlite3
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

# ── Constants ─────────────────────────────────────────────────────────────────

ACTIONS = {
    "birthday_wish": {
        "label":    "Birthday Wish",
        "icon":     "🎂",
        "priority": 10,
        "color":    "#f78166",
    },
    "followup": {
        "label":    "Follow-up",
        "icon":     "💬",
        "priority": 7,
        "color":    "#58a6ff",
    },
    "checkin": {
        "label":    "Check-in",
        "icon":     "👋",
        "priority": 5,
        "color":    "#3fb950",
    },
    "decay_alert": {
        "label":    "Decay Alert",
        "icon":     "⚠️",
        "priority": 6,
        "color":    "#d29922",
    },
    "skip": {
        "label":    "Skip",
        "icon":     "⏭",
        "priority": 0,
        "color":    "#8b949e",
    },
}

PLATFORM_DAILY_CAPS = {
    "LinkedIn":  20,
    "WhatsApp":  50,
    "Telegram":  100,
    "Discord":   30,
    "Facebook":  15,
    "Slack":     25,
}

COOLDOWN_DAYS = 300   # don't re-contact same person within this period


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_autonomous_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_decisions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT NOT NULL,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            action          TEXT NOT NULL,
            platform        TEXT NOT NULL,
            score           REAL NOT NULL,
            reason          TEXT,
            executed        INTEGER NOT NULL DEFAULT 0,
            execution_result TEXT,
            dry_run         INTEGER NOT NULL DEFAULT 1,
            decided_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_run_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT NOT NULL UNIQUE,
            mode            TEXT NOT NULL,
            total_contacts  INTEGER NOT NULL DEFAULT 0,
            decisions_made  INTEGER NOT NULL DEFAULT 0,
            actions_taken   INTEGER NOT NULL DEFAULT 0,
            skipped         INTEGER NOT NULL DEFAULT 0,
            errors          INTEGER NOT NULL DEFAULT 0,
            dry_run         INTEGER NOT NULL DEFAULT 1,
            summary_json    TEXT,
            started_at      TEXT NOT NULL,
            finished_at     TEXT
        )
    """)
    conn.commit()
    conn.close()


def _db() -> sqlite3.Connection:
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


# ── Contact loader ────────────────────────────────────────────────────────────

def load_all_contacts() -> list[dict]:
    """Load every contact the agent knows about."""
    if not DB_PATH.exists():
        return _demo_contacts()

    conn     = _db()
    contacts = []

    # Try contact_tier first (v8+)
    if _table_exists(conn, "contact_tier"):
        rows = conn.execute("""
            SELECT contact_id, contact_name, current_tier, tier_score
            FROM contact_tier ORDER BY tier_score DESC
        """).fetchall()
        for r in rows:
            contacts.append({
                "contact_id":   r["contact_id"],
                "contact_name": r["contact_name"],
                "tier":         r["current_tier"],
                "tier_score":   r["tier_score"] or 5.0,
                "platform":     "LinkedIn",
            })

    # Supplement from graph_nodes (platform info)
    if _table_exists(conn, "graph_nodes"):
        plat_map = {r["contact_id"]: r["platform"] for r in
                    conn.execute("SELECT contact_id, platform FROM graph_nodes").fetchall()}
        for c in contacts:
            if c["contact_id"] in plat_map:
                c["platform"] = plat_map[c["contact_id"]]

    conn.close()
    return contacts if contacts else _demo_contacts()


def _demo_contacts() -> list[dict]:
    today = datetime.now().strftime("%m-%d")
    return [
        {"contact_id":"urn_rakib_001","contact_name":"Rakib Hossain",
         "tier":"Close Friend","tier_score":9.0,"platform":"LinkedIn",
         "birthday":today},
        {"contact_id":"urn_nadia_002","contact_name":"Nadia Islam",
         "tier":"Colleague","tier_score":7.0,"platform":"WhatsApp"},
        {"contact_id":"urn_tanvir_003","contact_name":"Tanvir Ahmed",
         "tier":"Colleague","tier_score":5.0,"platform":"LinkedIn"},
        {"contact_id":"urn_mim_004","contact_name":"Mim Chowdhury",
         "tier":"Close Friend","tier_score":9.5,"platform":"WhatsApp",
         "birthday":today},
        {"contact_id":"urn_sara_005","contact_name":"Sara Khan",
         "tier":"Acquaintance","tier_score":3.0,"platform":"LinkedIn"},
        {"contact_id":"urn_farah_007","contact_name":"Farah Akter",
         "tier":"Acquaintance","tier_score":2.0,"platform":"LinkedIn"},
    ]


# ── Decision engine ───────────────────────────────────────────────────────────

def _days_since_last_contact(contact_id: str) -> Optional[int]:
    """Return days since last outreach, or None if never."""
    conn = _db()
    if not _table_exists(conn, "wish_outcome_log"):
        conn.close()
        return None
    row = conn.execute("""
        SELECT sent_at FROM wish_outcome_log
        WHERE contact_id=? ORDER BY sent_at DESC LIMIT 1
    """, (contact_id,)).fetchone()
    conn.close()
    if not row:
        return None
    try:
        last = datetime.fromisoformat(row["sent_at"])
        return (datetime.now() - last).days
    except ValueError:
        return None


def _has_birthday_today(contact: dict) -> bool:
    """Check if contact has a birthday today."""
    today = datetime.now().strftime("%m-%d")
    if contact.get("birthday") and contact["birthday"][5:] == today:
        return True
    # Check life events table
    conn = _db()
    if not _table_exists(conn, "contact_life_events"):
        conn.close()
        return False
    row = conn.execute("""
        SELECT id FROM contact_life_events
        WHERE contact_id=? AND event_type='birthday'
          AND substr(event_date, 6, 5) = ?
    """, (contact["contact_id"], today)).fetchone()
    conn.close()
    return bool(row)


def _needs_followup(contact_id: str) -> bool:
    """Check if a wish was sent 3 days ago with no reply."""
    conn = _db()
    if not _table_exists(conn, "wish_outcome_log"):
        conn.close()
        return False
    cutoff = (datetime.now() - timedelta(days=6)).isoformat()
    since  = (datetime.now() - timedelta(days=3)).isoformat()
    row    = conn.execute("""
        SELECT COUNT(*) FROM wish_outcome_log
        WHERE contact_id=? AND sent_at BETWEEN ? AND ?
          AND replied=0
    """, (contact_id, cutoff, since)).fetchone()
    conn.close()
    return (row[0] or 0) > 0


def _is_fading(contact: dict) -> bool:
    """Contact fading if no contact in 60-120 days."""
    conn = _db()
    if _table_exists(conn, "graph_nodes"):
        row = conn.execute("""
            SELECT node_state FROM graph_nodes WHERE contact_id=?
        """, (contact["contact_id"],)).fetchone()
        conn.close()
        return bool(row and row[0] in ("fading", "dormant"))
    conn.close()
    days = _days_since_last_contact(contact["contact_id"])
    return days is not None and 60 <= days <= 180


def _vip_check(contact_id: str) -> bool:
    is_vip_fn = _safe("contacts.vip_contact_flagging", "is_vip")
    if is_vip_fn:
        try:
            return is_vip_fn(contact_id)
        except Exception:
            pass
    return False


def _on_cooldown(contact_id: str) -> bool:
    days = _days_since_last_contact(contact_id)
    return days is not None and days < COOLDOWN_DAYS


def decide_action(contact: dict) -> dict:
    """
    Core decision function. For one contact, decide:
      - what action to take (birthday_wish / followup / checkin / decay_alert / skip)
      - why (reason string)
      - score (0-10, higher = more urgent)

    Returns:
        { action, platform, score, reason, contact_id, contact_name }
    """
    cid   = contact["contact_id"]
    cname = contact["contact_name"]
    tier  = contact.get("tier", "Acquaintance")

    # Rule 1: cooldown
    if _on_cooldown(cid):
        return _decision(contact, "skip", 0,
                         f"Already contacted in last {COOLDOWN_DAYS}d")

    # Rule 2: birthday today → highest priority
    if _has_birthday_today(contact):
        is_vip = _vip_check(cid)
        score  = 10 if is_vip or tier == "Close Friend" else 8
        return _decision(contact, "birthday_wish", score,
                         f"Birthday today — {tier}"
                         + (" (VIP)" if is_vip else ""))

    # Rule 3: follow-up needed
    if _needs_followup(cid):
        score = {"Close Friend": 7, "Colleague": 5, "Acquaintance": 3}.get(tier, 4)
        return _decision(contact, "followup", score,
                         "Wish sent 3d ago, no reply yet")

    # Rule 4: fading relationship
    if _is_fading(contact):
        score = {"Close Friend": 6, "Colleague": 4, "Acquaintance": 2}.get(tier, 3)
        return _decision(contact, "decay_alert", score,
                         "No interaction in 60-180 days")

    # Rule 5: skip — nothing actionable
    return _decision(contact, "skip", 0, "No action needed today")


def _decision(contact: dict, action: str, score: float, reason: str) -> dict:
    return {
        "contact_id":   contact["contact_id"],
        "contact_name": contact["contact_name"],
        "tier":         contact.get("tier", "Acquaintance"),
        "platform":     contact.get("platform", "LinkedIn"),
        "action":       action,
        "score":        score,
        "reason":       reason,
        "icon":         ACTIONS.get(action, {}).get("icon", "?"),
        "color":        ACTIONS.get(action, {}).get("color", "#8b949e"),
    }


# ── Execution ─────────────────────────────────────────────────────────────────

def execute_decision(decision: dict, dry_run: bool = True) -> dict:
    """
    Execute a single agent decision.
    Returns result dict with success, output, method.
    """
    action  = decision["action"]
    cid     = decision["contact_id"]
    cname   = decision["contact_name"]
    platform= decision["platform"]

    if action == "skip":
        return {"success": True, "action": "skip", "output": "skipped"}

    if dry_run:
        return {"success": True, "action": action,
                "output": f"DRY RUN — {action} to {cname} via {platform}",
                "dry_run": True}

    # Route to LangGraph pipeline for birthday wishes
    if action == "birthday_wish":
        run_fn = _safe("langgraph_workflow", "run_contact_pipeline")
        if run_fn:
            try:
                contact = {
                    "contact_id":   cid,
                    "contact_name": cname,
                    "platform":     platform,
                    "tier":         decision["tier"],
                    "birthday":     datetime.now().strftime("%m-%d"),
                }
                final = run_fn(contact, dry_run=False, run_id="autonomous")
                return {"success": final.get("sent", False),
                        "action": action,
                        "output": final.get("wish_text", "")[:100]}
            except Exception as exc:
                return {"success": False, "action": action, "error": str(exc)}

    # Follow-up: enqueue via Redis
    if action in ("followup", "checkin", "decay_alert"):
        enqueue_fn = _safe("redis_cache", "enqueue")
        if enqueue_fn:
            try:
                tid = enqueue_fn("followups", action, {
                    "contact_id":   cid,
                    "contact_name": cname,
                    "platform":     platform,
                }, priority=decision["score"])
                return {"success": True, "action": action,
                        "output": f"Queued task {tid}"}
            except Exception as exc:
                return {"success": False, "action": action, "error": str(exc)}

    return {"success": True, "action": action, "output": "executed"}


def _log_decision(run_id: str, decision: dict, result: dict, dry_run: bool):
    init_autonomous_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO autonomous_decisions
            (run_id, contact_id, contact_name, action, platform,
             score, reason, executed, execution_result, dry_run, decided_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, decision["contact_id"], decision["contact_name"],
          decision["action"], decision["platform"],
          decision["score"], decision["reason"],
          1 if result else 0,
          json.dumps(result or {}),
          1 if dry_run else 0,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Rate limit guard ──────────────────────────────────────────────────────────

class PlatformCapTracker:
    """In-memory daily send cap per platform."""
    def __init__(self):
        self._counts: dict[str, int] = {}

    def can_send(self, platform: str) -> bool:
        cap = PLATFORM_DAILY_CAPS.get(platform, 20)
        return self._counts.get(platform, 0) < cap

    def record(self, platform: str):
        self._counts[platform] = self._counts.get(platform, 0) + 1

    def summary(self) -> dict:
        return dict(self._counts)


# ── Main autonomous run ───────────────────────────────────────────────────────

def run_autonomous(
    dry_run:    bool = True,
    max_actions:int = 50,
    verbose:    bool = True,
) -> dict:
    """
    Full autonomous daily run.

    Steps:
      1. Load all contacts
      2. Decide action for each
      3. Sort by score (most urgent first)
      4. Execute up to max_actions
      5. Log everything

    Args:
        dry_run:     If True, never sends real messages.
        max_actions: Cap on total actions per run.
        verbose:     Print progress to console.

    Returns:
        Run summary dict.
    """
    init_autonomous_tables()
    run_id = datetime.now().strftime("auto_%Y%m%d_%H%M%S")

    if verbose:
        print(f"\n{'='*62}")
        print(f"  Birthday Agent — Autonomous Mode")
        print(f"  Run ID : {run_id}")
        print(f"  Mode   : {'DRY RUN' if dry_run else '⚡ LIVE'}")
        print(f"{'='*62}\n")

    # Safety check — pause if anomaly detected
    is_paused_fn = _safe("automation.auto_pause_on_anomaly", "is_paused")
    if is_paused_fn and is_paused_fn():
        msg = "Agent is paused (anomaly detected). Resume before running."
        if verbose:
            print(f"  ⛔ {msg}")
        return {"run_id": run_id, "status": "paused", "message": msg}

    # 1. Load contacts
    contacts = load_all_contacts()
    if verbose:
        print(f"  Contacts loaded: {len(contacts)}\n")

    # 2. Decide for each
    decisions = []
    for c in contacts:
        d = decide_action(c)
        decisions.append(d)

    # 3. Sort by score descending, skip last
    decisions.sort(key=lambda x: -x["score"])
    actionable = [d for d in decisions if d["action"] != "skip"]
    skipped    = [d for d in decisions if d["action"] == "skip"]

    # 4. Execute (with platform cap)
    cap_tracker = PlatformCapTracker()
    results     = {"sent": 0, "queued": 0, "capped": 0,
                   "errors": 0, "skipped": len(skipped)}
    exec_log    = []

    if verbose:
        print(f"  {'Contact':<22} {'Action':<16} {'Score':<7} {'Reason'}")
        print(f"  {'─'*22} {'─'*16} {'─'*7} {'─'*30}")

    for decision in actionable[:max_actions]:
        plat = decision["platform"]

        if not cap_tracker.can_send(plat):
            results["capped"] += 1
            if verbose:
                print(f"  {decision['contact_name']:<22} {'CAPPED':<16} "
                      f"{decision['score']:<7} {plat} daily cap reached")
            continue

        result = execute_decision(decision, dry_run=dry_run)
        _log_decision(run_id, decision, result, dry_run)

        if result.get("success"):
            cap_tracker.record(plat)
            if decision["action"] == "birthday_wish":
                results["sent"] += 1
            else:
                results["queued"] += 1
        else:
            results["errors"] += 1

        exec_log.append({**decision, "result": result})

        if verbose:
            icon   = ACTIONS.get(decision["action"], {}).get("icon", "?")
            status = "OK" if result.get("success") else "FAIL"
            print(f"  {decision['contact_name']:<22} "
                  f"{icon} {decision['action']:<14} "
                  f"{decision['score']:<7.0f} {decision['reason'][:35]}"
                  f"  [{status}]")

    # Log skipped (no action needed) — compact
    for d in skipped:
        _log_decision(run_id, d, {"skipped": True}, dry_run)

    # 5. Persist run log
    summary = {**results, "platform_caps": cap_tracker.summary(),
               "decisions": len(actionable)}
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR IGNORE INTO autonomous_run_log
            (run_id, mode, total_contacts, decisions_made,
             actions_taken, skipped, errors, dry_run,
             summary_json, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id,
          "dry_run" if dry_run else "live",
          len(contacts),
          len(actionable),
          results["sent"] + results["queued"],
          results["skipped"],
          results["errors"],
          1 if dry_run else 0,
          json.dumps(summary),
          run_id[5:],   # timestamp part
          datetime.now().isoformat()))
    conn.commit()
    conn.close()

    if verbose:
        print(f"\n  {'─'*62}")
        print(f"  Wishes sent : {results['sent']}")
        print(f"  Tasks queued: {results['queued']}")
        print(f"  Skipped     : {results['skipped']}")
        print(f"  Capped      : {results['capped']}")
        print(f"  Errors      : {results['errors']}")
        print(f"  {'─'*62}\n")

    return {"run_id": run_id, "dry_run": dry_run, **results,
            "total_contacts": len(contacts), "exec_log": exec_log}


def show_decisions(verbose: bool = True) -> list[dict]:
    """Print what the agent would do today without executing."""
    contacts  = load_all_contacts()
    decisions = sorted([decide_action(c) for c in contacts],
                       key=lambda x: -x["score"])
    if verbose:
        print(f"\n  Autonomous Decisions for {datetime.now().strftime('%Y-%m-%d')}")
        print(f"  {'Contact':<22} {'Action':<16} {'Score':<7} Reason")
        print(f"  {'─'*22} {'─'*16} {'─'*7} {'─'*30}")
        for d in decisions:
            icon = ACTIONS.get(d["action"], {}).get("icon","?")
            print(f"  {d['contact_name']:<22} {icon} {d['action']:<14} "
                  f"{d['score']:<7.0f} {d['reason']}")
    return decisions


def get_run_history(limit: int = 10) -> list[dict]:
    """Return recent autonomous run summaries."""
    init_autonomous_tables()
    conn = _db()
    rows = conn.execute("""
        SELECT run_id, mode, total_contacts, actions_taken,
               skipped, errors, dry_run, finished_at
        FROM autonomous_run_log ORDER BY started_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Autonomous Agent", page_icon="🤖",
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
    .d-row{background:var(--surface);border:1px solid var(--border);
           border-radius:8px;padding:10px 14px;margin-bottom:6px;}
    .r-row{background:var(--surface);border:1px solid var(--border);
           border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:0.78rem;}
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

    init_autonomous_tables()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🤖</span>
      <h1>Autonomous Agent Mode</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    decisions = show_decisions(verbose=False)
    actionable = [d for d in decisions if d["action"] != "skip"]
    history    = get_run_history(10)

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Contacts", len(decisions), "#e6edf3"),
        (m2, "Actions Today", len(actionable), "#f78166"),
        (m3, "Skipped", len(decisions)-len(actionable), "#8b949e"),
        (m4, "Past Runs", len(history), "#58a6ff"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Today\'s Decisions</div>',
                    unsafe_allow_html=True)
        for d in decisions:
            color = d["color"]
            skip  = d["action"] == "skip"
            st.markdown(f"""
            <div class="d-row" style="{'opacity:0.4;' if skip else ''}
                 border-left:3px solid {color}">
              <div style="display:flex;align-items:center;
                          justify-content:space-between">
                <div>
                  <span style="font-weight:700;font-size:0.85rem">
                    {d['icon']} {d['contact_name']}
                  </span>
                  <span style="font-size:0.68rem;color:#8b949e;margin-left:8px">
                    {d['tier']} · {d['platform']}
                  </span>
                </div>
                <span style="font-size:0.68rem;font-weight:700;color:{color}">
                  score {d['score']:.0f}
                </span>
              </div>
              <div style="font-size:0.70rem;color:#8b949e;margin-top:4px">
                {d['reason']}
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Run controls
        st.markdown('<div class="section-title">Run Controls</div>',
                    unsafe_allow_html=True)
        dry_run  = st.checkbox("Dry Run", value=True, key="dr")
        max_acts = st.slider("Max actions", 1, 50, 20, key="max")

        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("▶ Run Autonomous", type="primary",
                         use_container_width=True):
                with st.spinner("Running..."):
                    result = run_autonomous(dry_run=dry_run,
                                            max_actions=max_acts,
                                            verbose=False)
                st.session_state["last_run"] = result
                st.rerun()
        with bc2:
            if st.button("🔍 Preview Only",
                         use_container_width=True):
                st.session_state["preview"] = show_decisions(verbose=False)
                st.rerun()

        run = st.session_state.get("last_run")
        if run:
            m1, m2, m3 = st.columns(3)
            for col, lbl, val, color in [
                (m1,"Sent",    run.get("sent",0),   "#3fb950"),
                (m2,"Queued",  run.get("queued",0), "#58a6ff"),
                (m3,"Errors",  run.get("errors",0), "#f85149"),
            ]:
                with col:
                    st.markdown(
                        f'<div class="mini"><div class="mini-val" '
                        f'style="color:{color}">{val}</div>'
                        f'<div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Run History</div>',
                    unsafe_allow_html=True)
        if not history:
            st.caption("No runs yet — click Run Autonomous to start.")
        for h in history:
            mode_color = "#d29922" if h["dry_run"] else "#f85149"
            mode_lbl   = "DRY RUN" if h["dry_run"] else "LIVE"
            st.markdown(f"""
            <div class="r-row">
              <div style="display:flex;justify-content:space-between">
                <div style="font-weight:700;font-family:'JetBrains Mono',monospace">
                  {h['run_id']}
                </div>
                <span style="color:{mode_color};font-size:0.65rem;font-weight:700">
                  {mode_lbl}
                </span>
              </div>
              <div style="color:#8b949e;margin-top:3px">
                {h['total_contacts']} contacts ·
                {h['actions_taken']} actions ·
                {h['skipped']} skipped ·
                {h['errors']} errors
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Action breakdown
        st.markdown('<div class="section-title">Action Breakdown</div>',
                    unsafe_allow_html=True)
        action_counts: dict = {}
        for d in decisions:
            a = d["action"]
            action_counts[a] = action_counts.get(a, 0) + 1
        for action, count in sorted(action_counts.items(),
                                     key=lambda x: -x[1]):
            meta  = ACTIONS.get(action, {})
            color = meta.get("color", "#8b949e")
            icon  = meta.get("icon", "?")
            pct   = int(count / len(decisions) * 100)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
              <div style="width:100px;font-size:0.76rem">{icon} {action}</div>
              <div style="flex:1;background:#0d1117;border-radius:4px;height:18px">
                <div style="width:{pct}%;height:100%;background:{color};
                            border-radius:4px"></div>
              </div>
              <div style="width:24px;text-align:right;font-size:0.72rem;
                          color:#8b949e">{count}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Autonomous Agent Mode</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    cmd     = sys.argv[1] if len(sys.argv) > 1 else "run"
    is_live = "--live" in sys.argv

    if cmd == "decide":
        show_decisions(verbose=True)

    elif cmd == "status":
        history = get_run_history(5)
        print(f"\nLast {len(history)} runs:")
        for h in history:
            mode = "LIVE" if not h["dry_run"] else "DRY"
            print(f"  {h['run_id']}  [{mode}]  "
                  f"actions={h['actions_taken']}  errors={h['errors']}")

    elif cmd == "run":
        print("=== Autonomous Agent -- self test ===")
        result = run_autonomous(dry_run=not is_live,
                                max_actions=20, verbose=True)
        print(f"Run ID : {result['run_id']}")
        print(f"Status : {'LIVE' if not result.get('dry_run') else 'DRY RUN'}")
else:
    render_dashboard()
