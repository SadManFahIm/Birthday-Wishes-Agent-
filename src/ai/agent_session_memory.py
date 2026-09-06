"""
Agent Session Memory -- Birthday Wishes Agent v9.0
Persistent cross-session memory for the agent itself.
Tracks what worked, what failed, and what was learned --
so every restart begins smarter than the last.

Stores:
  - Task outcomes (success / failure / skipped)
  - Platform-specific learnings (rate limits, best times, error patterns)
  - Contact-level learnings (what style worked, what flopped)
  - Global heuristics (auto-updated rules the agent follows)

Integrates with: ai/self_improving_agent.py,
                 automation/auto_pause_on_anomaly.py, agent.py
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

TASK_TYPES = [
    "birthday_detection", "ai_wish", "send_wish",
    "linkedin_reply", "whatsapp_reply", "followup",
    "decay_alert", "miss_tracker", "auto_connect",
]

LEARNING_CATEGORIES = {
    "platform_timing":    "Best/worst times to run on each platform",
    "style_performance":  "Which wish styles get replies",
    "error_pattern":      "Recurring errors and how they were resolved",
    "contact_preference": "What individual contacts respond to",
    "scheduler_rule":     "Auto-derived scheduling rules",
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_memory_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_task_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            task            TEXT NOT NULL,
            platform        TEXT,
            outcome         TEXT NOT NULL,
            duration_ms     INTEGER,
            error_msg       TEXT,
            meta_json       TEXT,
            logged_at       TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_learnings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            category        TEXT NOT NULL,
            key             TEXT NOT NULL,
            value_json      TEXT NOT NULL,
            confidence      REAL NOT NULL DEFAULT 0.5,
            source          TEXT,
            times_applied   INTEGER NOT NULL DEFAULT 0,
            times_helpful   INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            UNIQUE(category, key)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_registry (
            session_id      TEXT PRIMARY KEY,
            started_at      TEXT NOT NULL,
            ended_at        TEXT,
            tasks_run       INTEGER NOT NULL DEFAULT 0,
            tasks_ok        INTEGER NOT NULL DEFAULT 0,
            tasks_failed    INTEGER NOT NULL DEFAULT 0,
            summary         TEXT
        )
    """)
    conn.commit()
    conn.close()


# ── Session management ────────────────────────────────────────────────────────

def start_session() -> str:
    """
    Create a new agent session. Call at the top of agent.py main().
    Returns the session_id to pass to log_task_outcome().
    """
    init_memory_tables()
    session_id = datetime.now().strftime("s_%Y%m%d_%H%M%S")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR IGNORE INTO session_registry
            (session_id, started_at) VALUES (?, ?)
    """, (session_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    _apply_learnings_to_context(session_id)
    return session_id


def end_session(session_id: str, summary: str = "") -> None:
    """
    Close a session and trigger learning extraction.
    Call at the bottom of agent.py main().
    """
    init_memory_tables()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("""
        SELECT COUNT(*) FILTER (WHERE outcome='ok') as ok,
               COUNT(*) FILTER (WHERE outcome='error') as err,
               COUNT(*) as total
        FROM session_task_log WHERE session_id=?
    """, (session_id,)).fetchone()
    ok, err, total = (row[0] or 0), (row[1] or 0), (row[2] or 0)
    conn.execute("""
        UPDATE session_registry SET
            ended_at=?, tasks_run=?, tasks_ok=?, tasks_failed=?, summary=?
        WHERE session_id=?
    """, (datetime.now().isoformat(), total, ok, err,
          summary or f"{ok}/{total} tasks succeeded", session_id))
    conn.commit()
    conn.close()
    extract_learnings(session_id)


# ── Task outcome logging ──────────────────────────────────────────────────────

def log_task_outcome(
    session_id:  str,
    task:        str,
    outcome:     str,
    platform:    str = "",
    duration_ms: int = 0,
    error_msg:   str = "",
    meta:        Optional[dict] = None,
) -> None:
    """
    Log one task execution result.

    Args:
        session_id: From start_session().
        task:       Task name (e.g. "birthday_detection").
        outcome:    ok | error | skipped | rate_limited
        platform:   LinkedIn / WhatsApp / etc.
        duration_ms:How long the task took.
        error_msg:  Error string if outcome != ok.
        meta:       Any extra context (wish_score, contact_id, etc.)
    """
    init_memory_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO session_task_log
            (session_id, task, platform, outcome, duration_ms,
             error_msg, meta_json, logged_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, task, platform, outcome, duration_ms,
          error_msg[:300] if error_msg else "",
          json.dumps(meta or {}), datetime.now().isoformat()))
    conn.execute("""
        UPDATE session_registry SET tasks_run = tasks_run + 1 WHERE session_id=?
    """, (session_id,))
    conn.commit()
    conn.close()


# ── Learning extraction ───────────────────────────────────────────────────────

def extract_learnings(session_id: str, verbose: bool = True) -> list[dict]:
    """
    Analyze the session log and extract reusable learnings.
    Called automatically by end_session().

    Learning types extracted:
      - platform error rate → scheduler_rule (avoid platform if error rate > 50%)
      - task duration → platform_timing (avg duration per task/platform)
      - error patterns → error_pattern (recurring error messages)
    """
    init_memory_tables()
    conn    = sqlite3.connect(DB_PATH)
    rows    = conn.execute("""
        SELECT task, platform, outcome, duration_ms, error_msg
        FROM session_task_log WHERE session_id=?
    """, (session_id,)).fetchall()
    conn.close()

    if not rows:
        return []

    learnings_added = []

    # 1. Platform error rate
    plat_stats: dict = {}
    for r in rows:
        plat = r[1] or "unknown"
        if plat not in plat_stats:
            plat_stats[plat] = {"ok": 0, "error": 0, "durations": []}
        if r[2] == "ok":
            plat_stats[plat]["ok"] += 1
        elif r[2] in ("error", "rate_limited"):
            plat_stats[plat]["error"] += 1
        if r[3]:
            plat_stats[plat]["durations"].append(r[3])

    for plat, stats in plat_stats.items():
        if not plat or plat == "unknown":
            continue
        total = stats["ok"] + stats["error"]
        if total < 2:
            continue
        err_rate  = stats["error"] / total
        avg_dur   = int(sum(stats["durations"]) / len(stats["durations"])) if stats["durations"] else 0
        confidence = min(0.9, 0.5 + (total * 0.05))

        _upsert_learning(
            "platform_timing", f"{plat}_error_rate",
            {"error_rate": round(err_rate, 2), "avg_duration_ms": avg_dur,
             "sample_size": total, "session": session_id},
            confidence, source=session_id,
        )
        learnings_added.append(f"platform_timing:{plat}_error_rate={err_rate:.0%}")

        if err_rate > 0.5:
            _upsert_learning(
                "scheduler_rule", f"avoid_{plat}_if_errors",
                {"rule": f"Skip {plat} if error rate > 50% in session",
                 "triggered": True, "platform": plat},
                confidence, source=session_id,
            )
            learnings_added.append(f"scheduler_rule:avoid_{plat}")
            if verbose:
                print(f"[AgentMemory] Learned: {plat} error rate {err_rate:.0%} "
                      f"-> avoid rule set")

    # 2. Recurring error patterns
    error_freq: dict = {}
    for r in rows:
        if r[2] == "error" and r[4]:
            key = r[4][:60]
            error_freq[key] = error_freq.get(key, 0) + 1

    for err_msg, count in error_freq.items():
        if count >= 2:
            _upsert_learning(
                "error_pattern", err_msg[:40].replace(" ", "_"),
                {"message": err_msg, "occurrences": count,
                 "session": session_id},
                min(0.9, 0.4 + count * 0.1), source=session_id,
            )
            learnings_added.append(f"error_pattern:{err_msg[:30]}")
            if verbose:
                print(f"[AgentMemory] Recurring error ({count}x): {err_msg[:50]}")

    if verbose and learnings_added:
        print(f"[AgentMemory] Session {session_id}: "
              f"{len(learnings_added)} learnings extracted")
    return learnings_added


def _upsert_learning(category, key, value, confidence, source=""):
    conn = sqlite3.connect(DB_PATH)
    now  = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO agent_learnings
            (category, key, value_json, confidence, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(category, key) DO UPDATE SET
            value_json = excluded.value_json,
            confidence = excluded.confidence,
            source     = excluded.source,
            updated_at = excluded.updated_at
    """, (category, key, json.dumps(value), confidence, source, now, now))
    conn.commit()
    conn.close()


# ── Learning retrieval ────────────────────────────────────────────────────────

def get_learnings(category: Optional[str] = None) -> list[dict]:
    """Return all learnings, optionally filtered by category."""
    init_memory_tables()
    conn = sqlite3.connect(DB_PATH)
    if category:
        rows = conn.execute("""
            SELECT category, key, value_json, confidence, times_applied,
                   times_helpful, updated_at
            FROM agent_learnings WHERE category=?
            ORDER BY confidence DESC
        """, (category,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT category, key, value_json, confidence, times_applied,
                   times_helpful, updated_at
            FROM agent_learnings ORDER BY confidence DESC
        """).fetchall()
    conn.close()
    return [{"category": r[0], "key": r[1],
             "value": json.loads(r[2]), "confidence": r[3],
             "times_applied": r[4], "times_helpful": r[5],
             "updated_at": r[6]} for r in rows]


def should_skip_platform(platform: str) -> bool:
    """
    Check if the agent has learned to avoid a platform.
    Call before running any platform-specific task.
    """
    learnings = get_learnings("scheduler_rule")
    for l in learnings:
        if l["key"] == f"avoid_{platform}_if_errors":
            val = l["value"]
            if val.get("triggered") and l["confidence"] > 0.6:
                return True
    return False


def mark_learning_helpful(category: str, key: str, helpful: bool = True) -> None:
    """Feedback loop: mark a learning as helpful or not."""
    init_memory_tables()
    col = "times_helpful" if helpful else "times_applied"
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"""
        UPDATE agent_learnings SET
            times_applied = times_applied + 1,
            {col} = {col} + 1,
            confidence = MIN(0.95, confidence + ?)
        WHERE category=? AND key=?
    """, (0.05 if helpful else -0.05, category, key))
    conn.commit()
    conn.close()


def _apply_learnings_to_context(session_id: str) -> None:
    """Print active learnings at session start for transparency."""
    rules = get_learnings("scheduler_rule")
    if rules:
        print(f"[AgentMemory] Session {session_id} starting with "
              f"{len(rules)} active rule(s):")
        for r in rules:
            print(f"  [{r['confidence']:.0%}] {r['value'].get('rule','?')}")


def get_session_history(limit: int = 10) -> list[dict]:
    """Return recent session summaries."""
    init_memory_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT session_id, started_at, ended_at,
               tasks_run, tasks_ok, tasks_failed, summary
        FROM session_registry ORDER BY started_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"session_id": r[0], "started_at": r[1], "ended_at": r[2],
             "tasks_run": r[3], "tasks_ok": r[4], "tasks_failed": r[5],
             "summary": r[6]} for r in rows]


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Agent Memory", page_icon="🧠",
                       layout="wide", initial_sidebar_state="collapsed")

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains Mono:wght@400;500&display=swap');
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
    .l-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:12px 14px;margin-bottom:8px;}
    .s-card{background:var(--surface);border:1px solid var(--border);
            border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:0.78rem;}
    .conf-bar{background:#0d1117;border-radius:3px;height:5px;overflow:hidden;margin-top:5px;}
    .conf-fill{height:100%;border-radius:3px;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.6rem;color:#8b949e;text-transform:uppercase;
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

    init_memory_tables()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🧠</span>
      <h1>Agent Session Memory</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    # Seed demo if empty
    _seed_demo()

    learnings = get_learnings()
    sessions  = get_session_history()
    total_l   = len(learnings)
    rules     = [l for l in learnings if l["category"] == "scheduler_rule"]
    errors    = [l for l in learnings if l["category"] == "error_pattern"]

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Total Learnings",  total_l,    "#e6edf3"),
        (m2, "Active Rules",     len(rules), "#d29922"),
        (m3, "Error Patterns",   len(errors),"#f85149"),
        (m4, "Sessions Logged",  len(sessions),"#58a6ff"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Agent Learnings</div>',
                    unsafe_allow_html=True)
        cat_filter = st.selectbox(
            "Filter", ["All"] + list(LEARNING_CATEGORIES.keys()),
            label_visibility="collapsed", key="cat_f")
        filtered = learnings if cat_filter == "All" else [
            l for l in learnings if l["category"] == cat_filter]

        for l in filtered:
            conf  = l["confidence"]
            color = "#3fb950" if conf > 0.7 else "#d29922" if conf > 0.4 else "#f85149"
            val   = l["value"]
            desc  = (val.get("rule") or val.get("message") or
                     str(val)[:60])
            st.markdown(f"""
            <div class="l-card">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <div style="font-weight:700;font-size:0.82rem">{l['key']}</div>
                <div style="font-size:0.68rem;color:{color};font-weight:700">
                  {conf:.0%} conf
                </div>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin:3px 0">
                {l['category']} · applied {l['times_applied']}x ·
                helpful {l['times_helpful']}x
              </div>
              <div style="font-size:0.75rem;color:#c9d1d9">{desc}</div>
              <div class="conf-bar">
                <div class="conf-fill"
                     style="width:{int(conf*100)}%;background:{color}"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            hc1, hc2 = st.columns(2)
            with hc1:
                if st.button("Helpful", key=f"h_{l['category']}_{l['key']}",
                             use_container_width=True):
                    mark_learning_helpful(l["category"], l["key"], True)
                    st.rerun()
            with hc2:
                if st.button("Not helpful", key=f"n_{l['category']}_{l['key']}",
                             use_container_width=True):
                    mark_learning_helpful(l["category"], l["key"], False)
                    st.rerun()

        # Simulate session
        st.markdown('<div class="section-title" style="margin-top:20px">'
                    'Simulate Session</div>', unsafe_allow_html=True)
        platforms = ["LinkedIn","WhatsApp","Slack","Facebook"]
        sim_plat  = st.selectbox("Platform", platforms,
                                 label_visibility="collapsed", key="sim_p")
        sim_outcome = st.selectbox("Outcome",
                                   ["ok","error","rate_limited","skipped"],
                                   label_visibility="collapsed", key="sim_o")
        sim_task = st.selectbox("Task", TASK_TYPES,
                                label_visibility="collapsed", key="sim_t")
        if st.button("Log & Learn", type="primary", use_container_width=True):
            sid = start_session()
            for _ in range(3):
                log_task_outcome(sid, sim_task, sim_outcome, sim_plat, 1200)
            end_session(sid, f"Simulated {sim_outcome} on {sim_plat}")
            st.success("Session logged + learnings extracted")
            st.rerun()

    with right:
        st.markdown('<div class="section-title">Session History</div>',
                    unsafe_allow_html=True)
        for s in sessions:
            ok    = s["tasks_ok"] or 0
            total = s["tasks_run"] or 0
            rate  = f"{ok}/{total}"
            color = "#3fb950" if total and ok == total else (
                    "#d29922" if total and ok > total // 2 else "#f85149")
            ts    = (s["started_at"] or "")[:16].replace("T", " ")
            st.markdown(f"""
            <div class="s-card">
              <div style="font-weight:700;font-family:'JetBrains Mono',monospace;
                          font-size:0.8rem">{s['session_id']}</div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:2px">
                {ts} | Tasks: <span style="color:{color}">{rate}</span> ok |
                {s.get('summary','') or ''}
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Platform Check</div>',
                    unsafe_allow_html=True)
        for plat in ["LinkedIn", "WhatsApp", "Slack", "Facebook"]:
            skip  = should_skip_platform(plat)
            icon  = "🔴 Skip" if skip else "🟢 OK"
            color = "#f85149" if skip else "#3fb950"
            st.markdown(f"""
            <div style="display:flex;align-items:center;justify-content:space-between;
                        padding:6px 0;border-bottom:1px solid #21262d;">
              <span style="font-size:0.82rem">{plat}</span>
              <span style="color:{color};font-size:0.75rem;font-weight:700">{icon}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>Agent Session Memory</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


def _seed_demo():
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM session_registry").fetchone()[0]
    conn.close()
    if count > 0:
        return

    import time as _time
    sessions = [
        ("s_20260601_090000", [
            ("birthday_detection","LinkedIn","ok",1200),
            ("ai_wish","LinkedIn","ok",3400),
            ("send_wish","LinkedIn","ok",800),
            ("linkedin_reply","LinkedIn","ok",900),
            ("birthday_detection","WhatsApp","ok",1100),
            ("send_wish","WhatsApp","error",0),
            ("send_wish","WhatsApp","error",0),
        ]),
        ("s_20260610_090000", [
            ("birthday_detection","LinkedIn","ok",1300),
            ("ai_wish","LinkedIn","ok",2900),
            ("send_wish","LinkedIn","rate_limited",0),
            ("send_wish","LinkedIn","rate_limited",0),
            ("send_wish","LinkedIn","rate_limited",0),
        ]),
    ]
    for sid, tasks in sessions:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT OR IGNORE INTO session_registry (session_id, started_at)
            VALUES (?, ?)
        """, (sid, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        for task, plat, outcome, dur in tasks:
            err = "Connection timeout" if outcome == "error" else (
                  "429 rate limit" if outcome == "rate_limited" else "")
            log_task_outcome(sid, task, outcome, plat, dur, err)
        end_session(sid)


if __name__ == "__main__":
    init_memory_tables()
    print("=== Agent Session Memory -- self test ===\n")
    _seed_demo()

    sid = start_session()
    tasks = [
        ("birthday_detection","LinkedIn","ok",1200),
        ("ai_wish","LinkedIn","ok",2800),
        ("send_wish","LinkedIn","ok",750),
        ("birthday_detection","WhatsApp","error",0),
        ("send_wish","WhatsApp","error",0),
        ("send_wish","WhatsApp","error",0),
    ]
    for task, plat, outcome, dur in tasks:
        log_task_outcome(sid, task, outcome, plat, dur,
                         "Timeout" if outcome == "error" else "")
    end_session(sid, "Self-test session")

    learnings = get_learnings()
    print(f"\n{len(learnings)} total learnings:")
    for l in learnings:
        val = l["value"]
        desc = val.get("rule") or val.get("message","")[:40] or str(val)[:40]
        print(f"  [{l['confidence']:.0%}] {l['category']}/{l['key']}: {desc}")

    print(f"\nPlatform checks:")
    for plat in ["LinkedIn","WhatsApp","Slack"]:
        status = "SKIP" if should_skip_platform(plat) else "OK"
        print(f"  {plat}: {status}")
else:
    render_dashboard()
