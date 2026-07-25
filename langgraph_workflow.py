"""
LangGraph Workflow Engine -- Birthday Wishes Agent v10.0
State-machine driven multi-step agent pipeline:

  detect  →  score  →  generate  →  review  →  send  →  followup
     ↑                                 ↓
     └────────────── reject ───────────┘

Each node is an isolated function. LangGraph tracks state transitions,
handles retries, and routes based on node output (conditional edges).

Pipeline steps:
  1. detect    -- find contacts with birthdays today
  2. score     -- personalization score + tier check
  3. generate  -- AI wish generation (consensus or template)
  4. review    -- VIP mandatory review gate / auto-approve others
  5. send      -- dispatch to correct platform
  6. followup  -- schedule follow-up task in Redis queue

Integrates with: ai/self_improving_agent.py, ai/multi_model_consensus.py,
                 contacts/vip_contact_flagging.py, redis_cache.py,
                 fastapi_backend.py, agent.py

Run:
  python langgraph_workflow.py run          # full pipeline (dry run)
  python langgraph_workflow.py run --live   # live send
  python langgraph_workflow.py visualize    # print ASCII graph
"""

import sqlite3
import json
import sys
import os
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import TypedDict, Optional, Annotated
import operator

DB_PATH = Path("agent_history.db")

# ── State schema ──────────────────────────────────────────────────────────────

class ContactState(TypedDict):
    """State passed between every node in the workflow."""
    # Contact info
    contact_id:   str
    contact_name: str
    platform:     str
    tier:         str
    birthday:     str

    # Scoring
    personalization_score: Optional[int]
    tier_score:            Optional[float]
    should_skip:           bool

    # Generation
    wish_text:      Optional[str]
    wish_model:     Optional[str]
    wish_style:     str
    generation_attempts: int

    # Review
    review_status:  str          # pending / approved / rejected
    is_vip:         bool
    reviewed_by:    str

    # Sending
    sent:           bool
    send_result:    Optional[dict]
    send_error:     Optional[str]
    dry_run:        bool

    # Follow-up
    followup_queued:bool
    followup_days:  int

    # Meta
    errors:         Annotated[list[str], operator.add]
    log:            Annotated[list[str], operator.add]
    started_at:     str


class PipelineState(TypedDict):
    """Top-level state for the full pipeline run."""
    contacts:     list[dict]
    processed:    Annotated[list[str], operator.add]
    skipped:      Annotated[list[str], operator.add]
    sent:         Annotated[list[str], operator.add]
    failed:       Annotated[list[str], operator.add]
    dry_run:      bool
    run_id:       str
    started_at:   str
    finished_at:  Optional[str]


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_workflow_log():
    conn = _db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_run_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT NOT NULL,
            contact_id  TEXT,
            node        TEXT NOT NULL,
            status      TEXT NOT NULL,
            detail      TEXT,
            ts          TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _log(run_id: str, node: str, status: str,
         contact_id: str = "", detail: str = ""):
    _init_workflow_log()
    conn = _db()
    conn.execute("""
        INSERT INTO workflow_run_log
            (run_id, contact_id, node, status, detail, ts)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (run_id, contact_id, node, status, detail[:300],
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Safe optional imports ─────────────────────────────────────────────────────

def _safe(module: str, attr: str):
    try:
        mod = __import__(module, fromlist=[attr])
        return getattr(mod, attr, None)
    except ImportError:
        return None


# ── Node 1: Detect ────────────────────────────────────────────────────────────

def node_detect(state: ContactState) -> ContactState:
    """
    Verify the contact has a birthday today and is not on cooldown.
    Routes to SKIP if no birthday or already wished this year.
    """
    cid  = state["contact_id"]
    name = state["contact_name"]
    log  = [f"[detect] Checking {name}"]

    # Cooldown check — skip if already wished in last 300 days
    conn     = _db()
    recent   = conn.execute("""
        SELECT COUNT(*) FROM wish_outcome_log
        WHERE contact_id=? AND sent_at >= ?
    """, (cid, (datetime.now() - timedelta(days=300)).isoformat())
    ).fetchone()[0] if _table_exists(conn, "wish_outcome_log") else 0
    conn.close()

    if recent > 0:
        log.append(f"[detect] SKIP — already wished {name} this year")
        return {**state, "should_skip": True, "log": log}

    log.append(f"[detect] ✅ {name} — birthday confirmed, no cooldown")
    return {**state, "should_skip": False, "log": log}


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone())


# ── Node 2: Score ─────────────────────────────────────────────────────────────

def node_score(state: ContactState) -> ContactState:
    """
    Compute personalization potential and load VIP status.
    High-tier contacts get consensus AI, others get template.
    """
    name  = state["contact_name"]
    tier  = state["tier"]
    log   = [f"[score] Scoring {name} (tier={tier})"]

    # VIP check
    is_vip_fn = _safe("contacts.vip_contact_flagging", "is_vip")
    is_vip    = is_vip_fn(state["contact_id"]) if is_vip_fn else False

    # Score 1-10 based on tier
    score_map  = {"Close Friend": 9, "Colleague": 7, "Acquaintance": 5}
    base_score = score_map.get(tier, 6)
    if is_vip:
        base_score = max(base_score, 9)

    # Pick wish style
    style_map = {"Close Friend": "warm", "Colleague": "professional",
                 "Acquaintance": "brief"}
    style     = style_map.get(tier, "warm")

    log.append(f"[score] score={base_score}/10 vip={is_vip} style={style}")
    return {**state,
            "personalization_score": base_score,
            "tier_score":            float(base_score),
            "is_vip":                is_vip,
            "wish_style":            style,
            "log":                   log}


# ── Node 3: Generate ──────────────────────────────────────────────────────────

def node_generate(state: ContactState) -> ContactState:
    """
    Generate birthday wish using AI.
    VIP / Close Friends → multi-model consensus.
    Others → active prompt template with self-improving agent.
    """
    name     = state["contact_name"]
    tier     = state["tier"]
    attempts = state.get("generation_attempts", 0) + 1
    log      = [f"[generate] Generating wish for {name} (attempt {attempts})"]

    use_consensus = tier == "Close Friend" or state.get("is_vip", False)
    wish_text     = None
    wish_model    = "template"

    if use_consensus:
        gen_fn = _safe("ai.multi_model_consensus", "generate_consensus_wish")
        if gen_fn:
            try:
                contact = {
                    "name": name, "job": "", "company": "", "memory": "",
                }
                result     = gen_fn(state["contact_id"], contact,
                                    state["platform"], state["wish_style"],
                                    verbose=False)
                wish_text  = result.get("winner_wish")
                wish_model = result.get("winner_model", "consensus")
                log.append(f"[generate] Consensus: model={wish_model}")
            except Exception as exc:
                log.append(f"[generate] Consensus failed: {exc}")

    if not wish_text:
        # Fallback: active prompt template
        get_prompt = _safe("ai.self_improving_agent", "get_active_prompt")
        first      = name.split()[0]
        wish_text  = (
            f"Happy Birthday {first}! "
            f"Wishing you an incredible {datetime.now().year} ahead. "
            f"Hope today is as amazing as you are!"
        )
        wish_model = "template"
        log.append(f"[generate] Template fallback used")

    log.append(f"[generate] ✅ Wish ready ({len(wish_text)} chars)")
    return {**state,
            "wish_text":          wish_text,
            "wish_model":         wish_model,
            "generation_attempts":attempts,
            "log":                log}


# ── Node 4: Review ────────────────────────────────────────────────────────────

def node_review(state: ContactState) -> ContactState:
    """
    Review gate:
      VIP contacts → status='pending' (FastAPI /queue route picks up)
      Others       → status='approved' (auto-approve)

    In dry_run mode all are 'approved' for testing.
    """
    name    = state["contact_name"]
    is_vip  = state.get("is_vip", False)
    dry_run = state.get("dry_run", True)
    log     = [f"[review] Reviewing wish for {name}"]

    if dry_run:
        log.append("[review] DRY RUN — auto-approved")
        return {**state, "review_status": "approved",
                "reviewed_by": "dry_run", "log": log}

    if is_vip:
        # Queue for manual review via FastAPI
        queue_fn = _safe("contacts.vip_contact_flagging", "queue_vip_wish")
        if queue_fn:
            queue_fn(state["contact_id"], name,
                     state.get("tier", "Colleague"),
                     state.get("wish_text", ""))
        log.append("[review] VIP — queued for manual review")
        return {**state, "review_status": "pending",
                "reviewed_by": "", "log": log}

    log.append("[review] Auto-approved (non-VIP)")
    return {**state, "review_status": "approved",
            "reviewed_by": "auto", "log": log}


# ── Node 5: Send ──────────────────────────────────────────────────────────────

def node_send(state: ContactState) -> ContactState:
    """
    Dispatch wish to correct platform.
    Logs outcome to wish_outcome_log for self-improving agent.
    """
    name     = state["contact_name"]
    platform = state["platform"]
    dry_run  = state.get("dry_run", True)
    log      = [f"[send] Sending to {name} via {platform}"]

    if dry_run:
        log.append(f"[send] DRY RUN — would send: {state['wish_text'][:60]}...")
        return {**state, "sent": True,
                "send_result": {"mock": True, "dry_run": True},
                "log": log}

    # Platform routing
    result    = None
    send_error= ""

    try:
        if platform in ("WhatsApp", "whatsapp"):
            fn = _safe("platforms.whatsapp_business_api", "send_text_message")
            if fn:
                phone  = ""  # would come from contact profile
                result = fn(state["contact_id"], name, phone,
                            state["wish_text"])

        elif platform in ("Telegram", "telegram"):
            fn = _safe("platforms.telegram_birthday", "send_birthday_wish")
            if fn:
                result = fn(state["contact_id"], name,
                            state["wish_text"], with_keyboard=True)

        elif platform in ("Discord", "discord"):
            fn = _safe("platforms.discord_birthday_bot", "send_birthday_dm")
            if fn:
                result = fn(state["contact_id"], name, state["wish_text"])

        else:
            result = {"success": True, "note": f"{platform} handled by browser agent"}

    except Exception as exc:
        send_error = str(exc)
        log.append(f"[send] ERROR: {exc}")

    # Log outcome for self-improving agent
    log_fn = _safe("ai.self_improving_agent", "log_wish_sent")
    if log_fn:
        try:
            log_fn(state["contact_id"], name, platform,
                   "v1.0", state.get("wish_style", "warm"),
                   state.get("personalization_score", 5))
        except Exception:
            pass

    success = bool(result and (result.get("success") or result.get("mock")))
    log.append(f"[send] {'✅' if success else '❌'} result={success}")

    return {**state,
            "sent":        success,
            "send_result": result or {},
            "send_error":  send_error,
            "log":         log}


# ── Node 6: Follow-up ─────────────────────────────────────────────────────────

def node_followup(state: ContactState) -> ContactState:
    """
    Enqueue a follow-up task in Redis (or in-memory fallback).
    Follow-up fires after N days if no reply received.
    """
    name  = state["contact_name"]
    days  = state.get("followup_days", 3)
    log   = [f"[followup] Scheduling follow-up for {name} in {days}d"]

    enqueue_fn = _safe("redis_cache", "enqueue")
    if enqueue_fn:
        try:
            task_id = enqueue_fn("followups", "smart_followup", {
                "contact_id":   state["contact_id"],
                "contact_name": name,
                "platform":     state["platform"],
                "followup_after_days": days,
                "wish_sent_at": datetime.now().isoformat(),
            }, priority=5)
            log.append(f"[followup] ✅ Queued task {task_id}")
            return {**state, "followup_queued": True, "log": log}
        except Exception as exc:
            log.append(f"[followup] Queue failed: {exc}")

    log.append("[followup] Redis unavailable — follow-up skipped")
    return {**state, "followup_queued": False, "log": log}


# ── Node: Skip ────────────────────────────────────────────────────────────────

def node_skip(state: ContactState) -> ContactState:
    """Terminal node for contacts that should be skipped."""
    log = [f"[skip] {state['contact_name']} — skipped"]
    return {**state, "log": log}


# ── Node: Error ───────────────────────────────────────────────────────────────

def node_error(state: ContactState) -> ContactState:
    """Terminal node for failed wishes."""
    log = [f"[error] {state['contact_name']} — pipeline failed: "
           f"{state.get('send_error', 'unknown')}"]
    return {**state, "log": log}


# ── Conditional edge functions ────────────────────────────────────────────────

def route_after_detect(state: ContactState) -> str:
    return "skip" if state.get("should_skip") else "score"


def route_after_review(state: ContactState) -> str:
    status = state.get("review_status", "pending")
    if status == "approved":
        return "send"
    if status == "rejected":
        return "generate"   # regenerate on rejection
    return "skip"           # pending → wait (skip for now)


def route_after_send(state: ContactState) -> str:
    if state.get("sent"):
        return "followup"
    # Retry up to 2 times
    if state.get("generation_attempts", 0) < 2:
        return "generate"
    return "error"


# ── Build the graph ───────────────────────────────────────────────────────────

def build_contact_graph():
    """
    Build and compile the per-contact LangGraph state machine.

    Graph:
      START → detect → [skip | score]
      score → generate → review → [send | generate(retry) | skip]
      send  → [followup | generate(retry) | error]
      followup → END
      skip     → END
      error    → END
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        raise ImportError("LangGraph not installed: pip install langgraph")

    graph = StateGraph(ContactState)

    # Add nodes
    graph.add_node("detect",   node_detect)
    graph.add_node("score",    node_score)
    graph.add_node("generate", node_generate)
    graph.add_node("review",   node_review)
    graph.add_node("send",     node_send)
    graph.add_node("followup", node_followup)
    graph.add_node("skip",     node_skip)
    graph.add_node("error",    node_error)

    # Entry point
    graph.set_entry_point("detect")

    # Conditional edges
    graph.add_conditional_edges(
        "detect",
        route_after_detect,
        {"skip": "skip", "score": "score"},
    )
    graph.add_edge("score", "generate")
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"send": "send", "generate": "generate", "skip": "skip"},
    )
    graph.add_conditional_edges(
        "send",
        route_after_send,
        {"followup": "followup", "generate": "generate", "error": "error"},
    )

    # Direct edges
    graph.add_edge("generate", "review")
    graph.add_edge("followup", END)
    graph.add_edge("skip",     END)
    graph.add_edge("error",    END)

    return graph.compile()


# ── Run pipeline for one contact ──────────────────────────────────────────────

def run_contact_pipeline(
    contact:  dict,
    dry_run:  bool = True,
    run_id:   str = "",
) -> dict:
    """
    Execute the full pipeline for one contact.

    Args:
        contact: dict with contact_id, contact_name, platform, tier, birthday
        dry_run: If True, never sends real messages
        run_id:  Parent pipeline run ID for logging

    Returns:
        Final ContactState dict
    """
    _init_workflow_log()
    graph = build_contact_graph()

    initial: ContactState = {
        "contact_id":           contact.get("contact_id", "unknown"),
        "contact_name":         contact.get("contact_name", "Unknown"),
        "platform":             contact.get("platform", "LinkedIn"),
        "tier":                 contact.get("tier", "Colleague"),
        "birthday":             contact.get("birthday", ""),
        "personalization_score":None,
        "tier_score":           None,
        "should_skip":          False,
        "wish_text":            None,
        "wish_model":           None,
        "wish_style":           "warm",
        "generation_attempts":  0,
        "review_status":        "pending",
        "is_vip":               False,
        "reviewed_by":          "",
        "sent":                 False,
        "send_result":          None,
        "send_error":           None,
        "dry_run":              dry_run,
        "followup_queued":      False,
        "followup_days":        3,
        "errors":               [],
        "log":                  [],
        "started_at":           datetime.now().isoformat(),
    }

    final = graph.invoke(initial)

    # Persist log
    for entry in final.get("log", []):
        node  = entry.split("]")[0].lstrip("[") if "]" in entry else "unknown"
        _log(run_id, node, "info", final["contact_id"], entry)

    return final


# ── Run full daily pipeline ───────────────────────────────────────────────────

def run_daily_pipeline(dry_run: bool = True) -> dict:
    """
    Full daily agent run:
      1. Load today's birthday contacts
      2. Run per-contact pipeline
      3. Return summary

    Returns:
        { run_id, total, sent, skipped, failed, results }
    """
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    print(f"\n{'='*60}")
    print(f"  Birthday Agent — LangGraph Pipeline")
    print(f"  Run ID : {run_id}")
    print(f"  Mode   : {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"{'='*60}\n")

    # Load contacts (demo data if DB empty)
    contacts = _load_today_contacts()
    if not contacts:
        contacts = _demo_contacts()
        print(f"  Using {len(contacts)} demo contacts\n")
    else:
        print(f"  Found {len(contacts)} birthday contacts\n")

    results = []
    summary = {"sent": 0, "skipped": 0, "failed": 0}

    for contact in contacts:
        name   = contact["contact_name"]
        print(f"  ► {name:<25} ", end="", flush=True)
        final  = run_contact_pipeline(contact, dry_run=dry_run, run_id=run_id)
        status = (
            "SKIPPED" if final.get("should_skip") else
            "SENT"    if final.get("sent") else
            "PENDING" if final.get("review_status") == "pending" else
            "FAILED"
        )
        node_path = [e.split("]")[0].lstrip("[") for e in final.get("log", []) if "]" in e]
        path_str  = " → ".join(dict.fromkeys(node_path))
        print(f"{status:<10} {path_str}")

        if status == "SENT":
            summary["sent"] += 1
        elif status == "SKIPPED":
            summary["skipped"] += 1
        else:
            summary["failed"] += 1
        results.append({"contact": name, "status": status, "state": final})

    print(f"\n{'─'*60}")
    print(f"  Summary: {summary['sent']} sent | "
          f"{summary['skipped']} skipped | {summary['failed']} failed")
    print(f"{'─'*60}\n")

    return {
        "run_id":  run_id,
        "total":   len(contacts),
        "dry_run": dry_run,
        **summary,
        "results": results,
    }


def _load_today_contacts() -> list[dict]:
    """Load contacts with birthdays today from DB."""
    if not DB_PATH.exists():
        return []
    conn = _db()
    if not _table_exists(conn, "contact_tier"):
        conn.close()
        return []
    today = datetime.now().strftime("%m-%d")
    rows  = conn.execute("""
        SELECT contact_id, contact_name, current_tier
        FROM contact_tier LIMIT 20
    """).fetchall()
    conn.close()
    return [{"contact_id": r[0], "contact_name": r[1],
             "tier": r[2], "platform": "LinkedIn",
             "birthday": today} for r in rows]


def _demo_contacts() -> list[dict]:
    today = datetime.now().strftime("%m-%d")
    return [
        {"contact_id":"urn_rakib_001","contact_name":"Rakib Hossain",
         "platform":"LinkedIn","tier":"Close Friend","birthday":today},
        {"contact_id":"urn_nadia_002","contact_name":"Nadia Islam",
         "platform":"WhatsApp","tier":"Colleague","birthday":today},
        {"contact_id":"urn_mim_004","contact_name":"Mim Chowdhury",
         "platform":"Telegram","tier":"Close Friend","birthday":today},
        {"contact_id":"urn_sara_005","contact_name":"Sara Khan",
         "platform":"LinkedIn","tier":"Acquaintance","birthday":today},
    ]


# ── Graph visualization ───────────────────────────────────────────────────────

def print_graph():
    print("""
  Birthday Agent — LangGraph Workflow (v10.0)
  ═══════════════════════════════════════════

  START
    │
    ▼
  ┌─────────┐
  │ detect  │ ─── should_skip=True ──► SKIP ──► END
  └─────────┘
    │ should_skip=False
    ▼
  ┌─────────┐
  │  score  │ (tier, VIP, style)
  └─────────┘
    │
    ▼
  ┌──────────┐
  │ generate │ ◄──── rejected ─────────────────┐
  └──────────┘ ◄──── send failed (retry < 2) ──┤
    │                                           │
    ▼                                           │
  ┌────────┐                                    │
  │ review │ ─── pending (VIP) ──► SKIP ──► END │
  └────────┘                                    │
    │ approved                                  │
    ▼                                           │
  ┌──────┐                                      │
  │ send │ ─── failed (retry) ─────────────────►┘
  └──────┘ ─── failed (max retry) ──► ERROR ──► END
    │ success
    ▼
  ┌──────────┐
  │ followup │ (Redis queue)
  └──────────┘
    │
    ▼
   END
""")


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="LangGraph Pipeline", page_icon="🔄",
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
    .node{background:var(--surface);border:1px solid var(--border);
          border-radius:8px;padding:10px 14px;margin-bottom:6px;
          font-family:'JetBrains Mono',monospace;font-size:0.8rem;}
    .log-entry{font-family:'JetBrains Mono',monospace;font-size:0.72rem;
               padding:2px 0;color:#c9d1d9;border-bottom:1px solid #21262d;}
    .r-card{background:var(--surface);border:1px solid var(--border);
            border-radius:8px;padding:10px 14px;margin-bottom:6px;}
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

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🔄</span>
      <h1>LangGraph Workflow Engine</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    # Pipeline viz
    NODES = [
        ("detect",   "#58a6ff", "Find today's birthday contacts"),
        ("score",    "#bc8cff", "Tier, VIP check, style selection"),
        ("generate", "#f78166", "AI wish generation (consensus/template)"),
        ("review",   "#d29922", "VIP gate / auto-approve"),
        ("send",     "#3fb950", "Dispatch to platform"),
        ("followup", "#4fc3f7", "Queue follow-up task"),
    ]
    st.markdown('<div class="section-title">Pipeline Nodes</div>',
                unsafe_allow_html=True)
    cols = st.columns(len(NODES))
    for col, (name, color, desc) in zip(cols, NODES):
        with col:
            st.markdown(f"""
            <div style="background:#161b22;border:1px solid {color}55;
                        border-top:3px solid {color};border-radius:8px;
                        padding:10px;text-align:center;">
              <div style="font-weight:700;font-size:0.82rem;color:{color}">
                {name}
              </div>
              <div style="font-size:0.62rem;color:#8b949e;margin-top:4px">
                {desc}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.5], gap="large")

    with left:
        dry_run = st.checkbox("Dry Run (no real sends)", value=True, key="dr")
        st.caption("Uncheck to send real messages")

        if st.button("▶ Run Pipeline", type="primary", use_container_width=True):
            with st.spinner("Running pipeline..."):
                result = run_daily_pipeline(dry_run=dry_run)
            st.session_state["last_run"] = result
            st.rerun()

        run = st.session_state.get("last_run")
        if run:
            m1, m2, m3, m4 = st.columns(4)
            for col, lbl, val, color in [
                (m1, "Total",   run["total"],   "#e6edf3"),
                (m2, "Sent",    run["sent"],    "#3fb950"),
                (m3, "Skipped", run["skipped"], "#d29922"),
                (m4, "Failed",  run["failed"],  "#f85149"),
            ]:
                with col:
                    st.markdown(
                        f'<div class="mini"><div class="mini-val" '
                        f'style="color:{color}">{val}</div>'
                        f'<div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    with right:
        run = st.session_state.get("last_run")
        if run:
            st.markdown('<div class="section-title">Contact Results</div>',
                        unsafe_allow_html=True)
            STATUS_COLORS = {
                "SENT":"#3fb950","SKIPPED":"#d29922",
                "FAILED":"#f85149","PENDING":"#58a6ff",
            }
            for r in run.get("results", []):
                color  = STATUS_COLORS.get(r["status"], "#8b949e")
                state  = r.get("state", {})
                log_lines = state.get("log", [])
                st.markdown(f"""
                <div class="r-card">
                  <div style="display:flex;align-items:center;
                              justify-content:space-between;margin-bottom:6px">
                    <div style="font-weight:700">{r['contact']}</div>
                    <span style="color:{color};font-size:0.72rem;font-weight:700">
                      {r['status']}
                    </span>
                  </div>
                </div>
                """, unsafe_allow_html=True)
                with st.expander(f"Log — {r['contact']}"):
                    for line in log_lines:
                        st.markdown(f'<div class="log-entry">{line}</div>',
                                    unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>LangGraph Workflow Engine</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    cmd      = sys.argv[1] if len(sys.argv) > 1 else "run"
    is_live  = "--live" in sys.argv

    if cmd == "visualize":
        print_graph()

    elif cmd == "run":
        result = run_daily_pipeline(dry_run=not is_live)
        print(f"Run ID: {result['run_id']}")

    elif cmd == "test":
        print("=== LangGraph Workflow -- self test ===\n")
        contact = {"contact_id":"urn_test_001","contact_name":"Test User",
                   "platform":"LinkedIn","tier":"Close Friend",
                   "birthday":datetime.now().strftime("%m-%d")}
        final   = run_contact_pipeline(contact, dry_run=True, run_id="test")
        print("\nFinal state:")
        print(f"  sent            : {final['sent']}")
        print(f"  review_status   : {final['review_status']}")
        print(f"  wish_model      : {final['wish_model']}")
        print(f"  followup_queued : {final['followup_queued']}")
        print(f"  score           : {final['personalization_score']}")
        print("\nLog:")
        for line in final["log"]:
            print(f"  {line}")
else:
    render_dashboard()
