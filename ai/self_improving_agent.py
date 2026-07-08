"""
Self-Improving Agent -- Birthday Wishes Agent v9.0
Monitors reply rates per prompt style and automatically tunes
the AI prompt when performance drops below threshold.
"""

import sqlite3
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path("agent_history.db")

MIN_REPLY_RATE  = 0.35
MIN_SAMPLE_SIZE = 10
TRIAL_WISHES    = 15
IMPROVEMENT_CYCLES = 5

TUNE_REASONS = {
    "low_reply_rate": "Reply rate dropped below threshold",
    "manual":         "Manually triggered by user",
}

DEFAULT_PROMPT = (
    "You are generating a personalized birthday wish for {contact_name}, "
    "who works as {job} at {company}.\n\n"
    "Requirements:\n"
    "- Mention their name naturally\n"
    "- Reference their role or company\n"
    "- Include a memory or shared context if available: {memory}\n"
    "- Match this tone: {style}\n"
    "- Length: 2-4 sentences\n"
    "- No generic phrases like 'have a great day'\n\n"
    "Generate ONLY the wish text, nothing else."
)


def init_self_improve_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            version_tag     TEXT NOT NULL UNIQUE,
            prompt_text     TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'active',
            reply_rate      REAL,
            avg_score       REAL,
            total_sends     INTEGER NOT NULL DEFAULT 0,
            total_replies   INTEGER NOT NULL DEFAULT 0,
            tune_reason     TEXT,
            parent_version  TEXT,
            created_at      TEXT NOT NULL,
            promoted_at     TEXT,
            retired_at      TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wish_outcome_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            platform        TEXT NOT NULL,
            prompt_version  TEXT NOT NULL,
            wish_style      TEXT,
            personalization_score INTEGER,
            replied         INTEGER NOT NULL DEFAULT 0,
            reply_delay_hrs REAL,
            sentiment_score REAL,
            sent_at         TEXT NOT NULL,
            replied_at      TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tuning_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            triggered_by    TEXT NOT NULL,
            old_version     TEXT NOT NULL,
            new_version     TEXT NOT NULL,
            old_reply_rate  REAL,
            improvement     REAL,
            trial_sends     INTEGER,
            promoted        INTEGER NOT NULL DEFAULT 0,
            notes           TEXT,
            tuned_at        TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def seed_default_prompt():
    init_self_improve_tables()
    conn = sqlite3.connect(DB_PATH)
    exists = conn.execute(
        "SELECT id FROM prompt_versions WHERE version_tag='v1.0'"
    ).fetchone()
    if not exists:
        conn.execute("""
            INSERT INTO prompt_versions
                (version_tag, prompt_text, status, created_at)
            VALUES ('v1.0', ?, 'active', ?)
        """, (DEFAULT_PROMPT, datetime.now().isoformat()))
        conn.commit()
    conn.close()


def get_active_prompt():
    init_self_improve_tables()
    seed_default_prompt()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("""
        SELECT version_tag, prompt_text, reply_rate, avg_score, total_sends
        FROM prompt_versions WHERE status='active'
        ORDER BY created_at DESC LIMIT 1
    """).fetchone()
    conn.close()
    if not row:
        return {"version_tag": "v1.0", "prompt_text": DEFAULT_PROMPT,
                "reply_rate": None, "avg_score": None, "total_sends": 0}
    return {"version_tag": row[0], "prompt_text": row[1],
            "reply_rate": row[2], "avg_score": row[3], "total_sends": row[4]}


def get_all_versions():
    init_self_improve_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT version_tag, status, reply_rate, avg_score,
               total_sends, total_replies, tune_reason, created_at
        FROM prompt_versions ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [{"version_tag": r[0], "status": r[1], "reply_rate": r[2],
             "avg_score": r[3], "total_sends": r[4], "total_replies": r[5],
             "tune_reason": r[6], "created_at": r[7]} for r in rows]


def log_wish_sent(contact_id, contact_name, platform, prompt_version,
                  wish_style="", personalization_score=0):
    init_self_improve_tables()
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute("""
        INSERT INTO wish_outcome_log
            (contact_id, contact_name, platform, prompt_version,
             wish_style, personalization_score, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, platform, prompt_version,
          wish_style, personalization_score, datetime.now().isoformat()))
    row_id = cur.lastrowid
    conn.execute(
        "UPDATE prompt_versions SET total_sends = total_sends + 1 WHERE version_tag=?",
        (prompt_version,))
    conn.commit()
    conn.close()
    return row_id


def log_reply_received(outcome_id, reply_delay_hrs, sentiment_score=3.0):
    init_self_improve_tables()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute(
        "SELECT prompt_version FROM wish_outcome_log WHERE id=?", (outcome_id,)
    ).fetchone()
    conn.execute("""
        UPDATE wish_outcome_log SET
            replied=1, reply_delay_hrs=?, sentiment_score=?, replied_at=?
        WHERE id=?
    """, (reply_delay_hrs, sentiment_score, datetime.now().isoformat(), outcome_id))
    if row:
        conn.execute(
            "UPDATE prompt_versions SET total_replies = total_replies + 1 WHERE version_tag=?",
            (row[0],))
    conn.commit()
    conn.close()
    if row:
        _refresh_stats(row[0])


def _refresh_stats(version_tag):
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("""
        SELECT COUNT(*), SUM(replied), AVG(personalization_score)
        FROM wish_outcome_log WHERE prompt_version=?
    """, (version_tag,)).fetchone()
    if row and row[0]:
        rate  = round((row[1] or 0) / row[0], 3)
        score = round(row[2] or 0, 1)
        conn.execute(
            "UPDATE prompt_versions SET reply_rate=?, avg_score=? WHERE version_tag=?",
            (rate, score, version_tag))
    conn.commit()
    conn.close()


def should_tune(verbose=True):
    active = get_active_prompt()
    sends  = active["total_sends"] or 0
    rate   = active["reply_rate"]

    if sends < MIN_SAMPLE_SIZE:
        result = {"needs_tuning": False,
                  "reason": f"Insufficient data ({sends}/{MIN_SAMPLE_SIZE} sends)",
                  "current_rate": rate, "sample_size": sends}
    elif rate is None or rate < MIN_REPLY_RATE:
        result = {"needs_tuning": True,
                  "reason": TUNE_REASONS["low_reply_rate"],
                  "current_rate": rate or 0.0, "sample_size": sends}
    else:
        result = {"needs_tuning": False,
                  "reason": f"Rate {rate:.0%} above threshold {MIN_REPLY_RATE:.0%}",
                  "current_rate": rate, "sample_size": sends}

    if verbose:
        status = "TUNING NEEDED" if result["needs_tuning"] else "OK"
        print(f"[SelfImprove] {active['version_tag']}: "
              f"rate={rate or 0:.0%} sends={sends} -> {status}")
    return result


def _generate_improved_prompt(current_prompt, current_rate, avg_score):
    tips = [
        "Start with a specific observation about their recent work.",
        "Reference the year they started at the company.",
        "End with one forward-looking sentence about the year ahead.",
        "Open with an unusual angle -- not 'Happy Birthday' as first words.",
        "Use the contact's first name exactly twice.",
    ]
    chosen = random.choice(tips)
    return (
        f"{current_prompt}\n\n"
        f"IMPROVEMENT (auto-tuner, rate was {current_rate:.0%}):\n{chosen}"
    )


def generate_improved_prompt(verbose=True):
    init_self_improve_tables()
    conn = sqlite3.connect(DB_PATH)
    cycle_count = conn.execute("SELECT COUNT(*) FROM tuning_history").fetchone()[0]
    conn.close()

    if cycle_count >= IMPROVEMENT_CYCLES:
        if verbose:
            print(f"[SelfImprove] Max cycles ({IMPROVEMENT_CYCLES}) reached.")
        return None

    active   = get_active_prompt()
    versions = get_all_versions()
    new_tag  = f"v{len(versions) + 1}.0-auto"
    new_text = _generate_improved_prompt(
        active["prompt_text"], active["reply_rate"] or 0.0, active["avg_score"] or 0.0)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO prompt_versions
            (version_tag, prompt_text, status, tune_reason, parent_version, created_at)
        VALUES (?, ?, 'trial', ?, ?, ?)
    """, (new_tag, new_text, TUNE_REASONS["low_reply_rate"],
          active["version_tag"], datetime.now().isoformat()))
    conn.execute("""
        INSERT INTO tuning_history
            (triggered_by, old_version, new_version, old_reply_rate, tuned_at)
        VALUES ('auto', ?, ?, ?, ?)
    """, (active["version_tag"], new_tag,
          active["reply_rate"] or 0.0, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    if verbose:
        print(f"[SelfImprove] New trial: {new_tag} "
              f"(parent={active['version_tag']})")
    return {"new_version_tag": new_tag, "prompt_text": new_text}


def evaluate_and_promote(verbose=True):
    init_self_improve_tables()
    conn  = sqlite3.connect(DB_PATH)
    trial = conn.execute("""
        SELECT version_tag, reply_rate, total_sends
        FROM prompt_versions WHERE status='trial'
        ORDER BY created_at DESC LIMIT 1
    """).fetchone()
    conn.close()

    if not trial:
        return {"action": "no_trial", "winner": None, "loser": None, "improvement": 0}

    trial_tag, trial_rate, trial_sends = trial[0], trial[1] or 0.0, trial[2] or 0

    if trial_sends < TRIAL_WISHES:
        if verbose:
            print(f"[SelfImprove] Trial {trial_tag}: "
                  f"{trial_sends}/{TRIAL_WISHES} sends")
        return {"action": "waiting", "trial_sends": trial_sends,
                "winner": None, "loser": None, "improvement": 0}

    active      = get_active_prompt()
    active_rate = active["reply_rate"] or 0.0
    improvement = round(trial_rate - active_rate, 3)
    now         = datetime.now().isoformat()
    conn        = sqlite3.connect(DB_PATH)

    if trial_rate > active_rate:
        conn.execute(
            "UPDATE prompt_versions SET status='active', promoted_at=? WHERE version_tag=?",
            (now, trial_tag))
        conn.execute(
            "UPDATE prompt_versions SET status='retired', retired_at=? WHERE version_tag=?",
            (now, active["version_tag"]))
        conn.execute(
            "UPDATE tuning_history SET promoted=1, improvement=? WHERE new_version=?",
            (improvement, trial_tag))
        action, winner, loser = "promoted", trial_tag, active["version_tag"]
        if verbose:
            print(f"[SelfImprove] Promoted {trial_tag} (+{improvement:.1%})")
    else:
        conn.execute(
            "UPDATE prompt_versions SET status='retired', retired_at=? WHERE version_tag=?",
            (now, trial_tag))
        conn.execute(
            "UPDATE tuning_history SET promoted=0, improvement=? WHERE new_version=?",
            (improvement, trial_tag))
        action, winner, loser = "retired", active["version_tag"], trial_tag
        if verbose:
            print(f"[SelfImprove] Retired {trial_tag} (did not improve)")

    conn.commit()
    conn.close()
    return {"action": action, "winner": winner,
            "loser": loser, "improvement": improvement}


def run_auto_tune_cycle(verbose=True):
    """Main entry -- call from agent.py daily scheduler."""
    init_self_improve_tables()
    seed_default_prompt()
    eval_result = evaluate_and_promote(verbose=verbose)
    check       = should_tune(verbose=verbose)
    new_prompt  = None
    if check["needs_tuning"] and eval_result["action"] not in ("waiting",):
        new_prompt = generate_improved_prompt(verbose=verbose)
    return {
        "eval_result":  eval_result,
        "needs_tuning": check["needs_tuning"],
        "current_rate": check["current_rate"],
        "new_trial":    new_prompt["new_version_tag"] if new_prompt else None,
    }


def _seed_demo():
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM wish_outcome_log").fetchone()[0]
    conn.close()
    if count > 0:
        return
    contacts = [
        ("urn_rakib_001","Rakib Hossain","LinkedIn"),
        ("urn_nadia_002","Nadia Islam","WhatsApp"),
        ("urn_tanvir_003","Tanvir Ahmed","LinkedIn"),
        ("urn_mim_004","Mim Chowdhury","WhatsApp"),
    ]
    for i in range(12):
        cid, cname, plat = contacts[i % len(contacts)]
        oid = log_wish_sent(cid, cname, plat, "v1.0",
                            random.choice(["warm","formal","funny"]),
                            random.randint(5, 9))
        if random.random() < 0.30:
            log_reply_received(oid, round(random.uniform(1, 48), 1), 4.0)


def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Self-Improving Agent", page_icon="🧬",
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
    .v-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .sp-active{background:#051a09;color:#3fb950;border:1px solid #3fb950;
               display:inline-flex;font-size:0.65rem;font-weight:700;padding:2px 8px;
               border-radius:20px;text-transform:uppercase;}
    .sp-trial{background:#1a1500;color:#d29922;border:1px solid #d29922;
              display:inline-flex;font-size:0.65rem;font-weight:700;padding:2px 8px;
              border-radius:20px;text-transform:uppercase;}
    .sp-retired{background:#21262d;color:#8b949e;border:1px solid #30363d;
                display:inline-flex;font-size:0.65rem;font-weight:700;padding:2px 8px;
                border-radius:20px;text-transform:uppercase;}
    .rate-bar{background:#0d1117;border-radius:4px;height:8px;overflow:hidden;margin-top:6px;}
    .rate-fill{height:100%;border-radius:4px;}
    .prompt-box{background:#010409;border:1px solid #30363d;border-radius:8px;
                padding:12px 14px;font-size:0.72rem;font-family:'JetBrains Mono',monospace;
                color:#7ee787;line-height:1.6;white-space:pre-wrap;
                max-height:200px;overflow-y:auto;}
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

    init_self_improve_tables()
    seed_default_prompt()
    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🧬</span>
      <h1>Self-Improving Agent</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    active   = get_active_prompt()
    versions = get_all_versions()
    check    = should_tune(verbose=False)
    rate     = active["reply_rate"] or 0

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Active Prompt",   active["version_tag"], "#e6edf3"),
        (m2, "Reply Rate",      f"{rate:.0%}",
         "#3fb950" if rate >= MIN_REPLY_RATE else "#f85149"),
        (m3, "Total Sends",     active["total_sends"],    "#58a6ff"),
        (m4, "Versions",        len(versions),            "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if check["needs_tuning"]:
        st.markdown(f"""
        <div style="background:#1a0505;border-left:4px solid #f85149;
                    border-radius:8px;padding:12px 16px;margin-bottom:14px;">
          <div style="font-weight:700;color:#f85149">Warning: Auto-Tune Triggered</div>
          <div style="font-size:0.78rem;color:#c9d1d9;margin-top:4px">
            {check['reason']}
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background:#051a09;border-left:4px solid #3fb950;
                    border-radius:8px;padding:12px 16px;margin-bottom:14px;">
          <div style="font-weight:700;color:#3fb950">Prompt Performing Well</div>
          <div style="font-size:0.78rem;color:#c9d1d9;margin-top:4px">
            {check['reason']}
          </div>
        </div>
        """, unsafe_allow_html=True)

    left, right = st.columns([1.2, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Prompt Versions</div>',
                    unsafe_allow_html=True)
        for v in versions:
            rv   = v["reply_rate"] or 0
            pill = {"active": "sp-active", "trial": "sp-trial",
                    "retired": "sp-retired"}.get(v["status"], "sp-retired")
            col  = "#3fb950" if rv >= MIN_REPLY_RATE else "#f85149" if rv > 0 else "#8b949e"
            pct  = int(rv * 100)
            st.markdown(f"""
            <div class="v-card">
              <div style="display:flex;align-items:center;justify-content:space-between;
                          margin-bottom:6px">
                <div style="font-weight:700;font-size:0.86rem;
                            font-family:'JetBrains Mono',monospace">{v['version_tag']}</div>
                <span class="{pill}">{v['status']}</span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e">
                Sends: {v['total_sends']} | Replies: {v['total_replies']} | Rate: {rv:.0%}
              </div>
              <div class="rate-bar">
                <div class="rate-fill" style="width:{pct}%;background:{col}"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Controls</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Run Tune Cycle", type="primary", use_container_width=True):
                result = run_auto_tune_cycle(verbose=False)
                if result["new_trial"]:
                    st.success(f"New trial: {result['new_trial']}")
                elif result["needs_tuning"]:
                    st.warning("Max cycles reached")
                else:
                    st.info("No tuning needed")
                st.rerun()
        with c2:
            if st.button("Evaluate Trial", use_container_width=True):
                res = evaluate_and_promote(verbose=False)
                if res["action"] == "promoted":
                    st.success(f"Promoted {res['winner']}")
                elif res["action"] == "retired":
                    st.warning("Trial retired")
                elif res["action"] == "waiting":
                    st.info("Trial still collecting data")
                else:
                    st.info("No trial running")
                st.rerun()

        with st.expander("Simulate outcome (testing)"):
            sim_ver     = st.selectbox("Version", [v["version_tag"] for v in versions],
                                       label_visibility="collapsed", key="sim_ver")
            sim_replied = st.checkbox("Replied", value=True, key="sim_rep")
            if st.button("Log outcome", use_container_width=True):
                oid = log_wish_sent("test_001","Test Contact","LinkedIn",
                                    sim_ver,"warm",7)
                if sim_replied:
                    log_reply_received(oid, round(random.uniform(0.5, 24), 1), 4.0)
                st.success("Logged")
                st.rerun()

    with right:
        st.markdown('<div class="section-title">Active Prompt</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="prompt-box">{active["prompt_text"]}</div>',
                    unsafe_allow_html=True)

        st.markdown('<div class="section-title">Tuning History</div>',
                    unsafe_allow_html=True)
        conn = sqlite3.connect(DB_PATH)
        hist = conn.execute("""
            SELECT old_version, new_version, old_reply_rate,
                   improvement, promoted, tuned_at
            FROM tuning_history ORDER BY tuned_at DESC
        """).fetchall()
        conn.close()
        if not hist:
            st.caption("No tuning cycles yet.")
        for h in hist:
            icon = "Promoted" if h[4] else "Not promoted"
            impr = h[3] or 0
            st.markdown(f"""
            <div class="v-card">
              <div style="font-weight:700;font-size:0.82rem">
                {h[0]} to {h[1]}
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:3px">
                Old rate: {h[2] or 0:.0%} | Delta: {impr:+.1%} |
                {icon} | {h[5][:10]}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>Self-Improving Agent</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_self_improve_tables()
    seed_default_prompt()
    _seed_demo()
    print("=== Self-Improving Agent -- self test ===\n")
    active = get_active_prompt()
    print(f"Active: {active['version_tag']} | "
          f"rate={active['reply_rate'] or 0:.0%} | sends={active['total_sends']}")
    result = run_auto_tune_cycle(verbose=True)
    print(f"\nCycle: needs_tuning={result['needs_tuning']} "
          f"new_trial={result['new_trial']}")
    versions = get_all_versions()
    print(f"\nVersions ({len(versions)}):")
    for v in versions:
        print(f"  [{v['status']:<8}] {v['version_tag']:<15} "
              f"rate={v['reply_rate'] or 0:.0%} sends={v['total_sends']}")
else:
    render_dashboard()
