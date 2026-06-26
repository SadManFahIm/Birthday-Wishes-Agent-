"""
Conditional Workflow Builder — Engine (Birthday Wishes Agent v8.0)
Stores, validates, and evaluates custom IF-THEN-ELSE workflow rules.
Rules are plain dicts persisted in SQLite — no code changes needed
to add new automation logic.

Rule schema:
    {
        "id":          str,   # UUID
        "name":        str,   # human-readable
        "enabled":     bool,
        "trigger":     { "event": str, "platform": str, "conditions": [...] },
        "actions":     [ { "type": str, "params": {...} }, ... ],
        "else_actions":[ { "type": str, "params": {...} }, ... ],  # optional
        "created_at":  str,
        "last_run":    str | None,
        "run_count":   int,
    }

Integrates with: agent.py, command_center.py
"""

import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

# ── Available triggers ────────────────────────────────────────────────────────
TRIGGERS = {
    "wish_sent":          "After a birthday wish is sent",
    "reply_received":     "When the contact replies",
    "no_reply":           "If no reply is received within N days",
    "followup_sent":      "After a follow-up message is sent",
    "no_reply_followup":  "If no reply to follow-up within N days",
    "birthday_missed":    "If a birthday was missed entirely",
    "relationship_decay": "When relationship score drops below threshold",
    "wish_score_low":     "If personalization score is below threshold",
    "new_contact":        "When a new contact is detected",
    "scheduler_daily":    "Every day at scheduled time",
}

# ── Available conditions ──────────────────────────────────────────────────────
CONDITIONS = {
    "platform_is":         {"label": "Platform is",              "param": "platform",   "type": "select",  "options": ["LinkedIn","WhatsApp","Facebook","Instagram","Twitter/X","Slack"]},
    "days_since_wish":     {"label": "Days since wish sent >=",  "param": "days",       "type": "number"},
    "days_since_reply":    {"label": "Days since last reply >=", "param": "days",       "type": "number"},
    "relationship_type":   {"label": "Relationship type is",     "param": "rel_type",   "type": "select",  "options": ["Close Friend","Colleague","Acquaintance"]},
    "wish_score_below":    {"label": "Wish score below",         "param": "threshold",  "type": "number"},
    "contact_has_tag":     {"label": "Contact has tag",          "param": "tag",        "type": "text"},
    "reply_sentiment_is":  {"label": "Reply sentiment is",       "param": "sentiment",  "type": "select",  "options": ["positive","neutral","negative","sad","stressed"]},
    "decay_days_over":     {"label": "No interaction for >= days","param": "days",      "type": "number"},
}

# ── Available actions ─────────────────────────────────────────────────────────
ACTIONS = {
    "send_followup":       {"label": "Send follow-up message",          "params": {"delay_hours": 72, "platform": "same"}},
    "send_decay_checkin":  {"label": "Send relationship check-in",      "params": {"message_tone": "warm"}},
    "send_late_wish":      {"label": "Send late birthday wish",         "params": {}},
    "send_voice_note":     {"label": "Send voice note",                 "params": {"engine": "gtts"}},
    "trigger_ai_retry":    {"label": "Retry AI wish with better prompt","params": {"min_score": 8}},
    "alert_dashboard":     {"label": "Show alert in Command Center",    "params": {"priority": "medium"}},
    "send_telegram_alert": {"label": "Send Telegram alert",             "params": {}},
    "send_email_alert":    {"label": "Send email alert",               "params": {}},
    "update_relationship": {"label": "Update relationship tier",        "params": {"direction": "down"}},
    "add_contact_tag":     {"label": "Add tag to contact",             "params": {"tag": "needs_attention"}},
    "pause_contact":       {"label": "Pause all automation for contact","params": {"days": 30}},
    "log_only":            {"label": "Log event only (no action)",      "params": {}},
}

# ── Built-in starter workflows ─────────────────────────────────────────────────
BUILTIN_WORKFLOWS = [
    {
        "name": "Smart Follow-up Chain",
        "trigger": {"event": "wish_sent", "platform": "all", "conditions": []},
        "actions": [{"type": "send_followup", "params": {"delay_hours": 72, "platform": "same"}}],
        "else_actions": [],
        "description": "If wish is sent and no reply in 3 days → send a warm follow-up automatically.",
    },
    {
        "name": "Missed Birthday Recovery",
        "trigger": {"event": "birthday_missed", "platform": "all", "conditions": []},
        "actions": [
            {"type": "send_late_wish",    "params": {}},
            {"type": "alert_dashboard",   "params": {"priority": "high"}},
        ],
        "else_actions": [],
        "description": "If a birthday was missed → send late wish + alert the Command Center dashboard.",
    },
    {
        "name": "Low Score Auto-Retry",
        "trigger": {"event": "wish_score_low", "platform": "all", "conditions": [
            {"type": "wish_score_below", "params": {"threshold": 6}},
        ]},
        "actions": [{"type": "trigger_ai_retry", "params": {"min_score": 8}}],
        "else_actions": [{"type": "log_only", "params": {}}],
        "description": "If personalization score < 6 → regenerate wish with a stronger AI prompt.",
    },
    {
        "name": "Relationship Decay Alert",
        "trigger": {"event": "relationship_decay", "platform": "all", "conditions": [
            {"type": "decay_days_over", "params": {"days": 60}},
        ]},
        "actions": [
            {"type": "send_decay_checkin",  "params": {"message_tone": "warm"}},
            {"type": "send_telegram_alert", "params": {}},
        ],
        "else_actions": [],
        "description": "If no contact interaction in 60+ days → send a check-in message and Telegram alert.",
    },
]

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_workflow_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 1,
            trigger_json TEXT NOT NULL,
            actions_json TEXT NOT NULL,
            else_json    TEXT NOT NULL DEFAULT '[]',
            description  TEXT,
            created_at  TEXT NOT NULL,
            last_run    TEXT,
            run_count   INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_run_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id  TEXT NOT NULL,
            contact_id   TEXT,
            contact_name TEXT,
            result       TEXT NOT NULL,
            actions_taken TEXT,
            ran_at       TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def seed_builtin_workflows():
    """Insert built-in starter workflows if the table is empty."""
    init_workflow_tables()
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
    if count == 0:
        for w in BUILTIN_WORKFLOWS:
            conn.execute("""
                INSERT INTO workflows (id, name, enabled, trigger_json, actions_json, else_json, description, created_at)
                VALUES (?, ?, 1, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                w["name"],
                json.dumps(w["trigger"]),
                json.dumps(w["actions"]),
                json.dumps(w["else_actions"]),
                w.get("description", ""),
                datetime.now().isoformat(),
            ))
    conn.commit()
    conn.close()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def save_workflow(workflow: dict) -> str:
    """Insert or update a workflow. Returns the workflow ID."""
    init_workflow_tables()
    wid = workflow.get("id") or str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO workflows (id, name, enabled, trigger_json, actions_json, else_json, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name         = excluded.name,
            enabled      = excluded.enabled,
            trigger_json = excluded.trigger_json,
            actions_json = excluded.actions_json,
            else_json    = excluded.else_json,
            description  = excluded.description
    """, (
        wid,
        workflow["name"],
        int(workflow.get("enabled", True)),
        json.dumps(workflow.get("trigger", {})),
        json.dumps(workflow.get("actions", [])),
        json.dumps(workflow.get("else_actions", [])),
        workflow.get("description", ""),
        workflow.get("created_at", datetime.now().isoformat()),
    ))
    conn.commit()
    conn.close()
    return wid


def load_all_workflows() -> list[dict]:
    """Return all workflows ordered by creation date."""
    init_workflow_tables()
    seed_builtin_workflows()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, name, enabled, trigger_json, actions_json, else_json, "
        "description, created_at, last_run, run_count FROM workflows ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            "id":           r[0], "name":        r[1], "enabled":   bool(r[2]),
            "trigger":      json.loads(r[3]),
            "actions":      json.loads(r[4]),
            "else_actions": json.loads(r[5]),
            "description":  r[6] or "",
            "created_at":   r[7], "last_run":    r[8], "run_count": r[9],
        })
    return result


def delete_workflow(workflow_id: str):
    init_workflow_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
    conn.commit()
    conn.close()


def toggle_workflow(workflow_id: str, enabled: bool):
    init_workflow_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE workflows SET enabled = ? WHERE id = ?", (int(enabled), workflow_id))
    conn.commit()
    conn.close()


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate_condition(condition: dict, context: dict) -> bool:
    """
    Evaluate a single condition against a runtime context dict.

    Context keys (all optional):
        platform, days_since_wish, days_since_reply, relationship_type,
        wish_score, tags (list), reply_sentiment, decay_days
    """
    ctype  = condition.get("type", "")
    params = condition.get("params", {})

    if ctype == "platform_is":
        return context.get("platform", "") == params.get("platform", "")
    if ctype == "days_since_wish":
        return context.get("days_since_wish", 0) >= int(params.get("days", 3))
    if ctype == "days_since_reply":
        return context.get("days_since_reply", 0) >= int(params.get("days", 3))
    if ctype == "relationship_type":
        return context.get("relationship_type", "") == params.get("rel_type", "")
    if ctype == "wish_score_below":
        return context.get("wish_score", 10) < int(params.get("threshold", 6))
    if ctype == "contact_has_tag":
        return params.get("tag", "") in context.get("tags", [])
    if ctype == "reply_sentiment_is":
        return context.get("reply_sentiment", "") == params.get("sentiment", "")
    if ctype == "decay_days_over":
        return context.get("decay_days", 0) >= int(params.get("days", 30))
    return True   # unknown condition → pass


def evaluate_workflow(workflow: dict, context: dict) -> dict:
    """
    Evaluate all conditions in a workflow against context.

    Returns:
        { "should_run": bool, "branch": "actions"|"else_actions",
          "passed": [...], "failed": [...] }
    """
    conditions = workflow.get("trigger", {}).get("conditions", [])
    passed, failed = [], []

    for cond in conditions:
        result = evaluate_condition(cond, context)
        (passed if result else failed).append(cond)

    all_passed = len(failed) == 0
    return {
        "should_run": all_passed or len(conditions) == 0,
        "branch":     "actions" if all_passed else "else_actions",
        "passed":     passed,
        "failed":     failed,
    }


def run_workflow(workflow: dict, context: dict, dry_run: bool = True) -> dict:
    """
    Evaluate and execute a workflow for a given context.

    Args:
        workflow: Workflow dict (from load_all_workflows).
        context:  Runtime context for condition evaluation.
        dry_run:  If True, log what would happen without executing.

    Returns:
        { "workflow_id", "workflow_name", "result", "actions_taken", "branch", "dry_run" }
    """
    if not workflow.get("enabled", True):
        return {"result": "skipped", "reason": "workflow disabled"}

    evaluation   = evaluate_workflow(workflow, context)
    branch       = evaluation["branch"]
    actions      = workflow.get(branch, [])
    actions_taken = []
    mode          = "[DRY RUN]" if dry_run else "[LIVE]"

    for action in actions:
        atype  = action.get("type", "")
        params = action.get("params", {})
        label  = ACTIONS.get(atype, {}).get("label", atype)
        log_line = f"{mode} {label} — {json.dumps(params)}"
        actions_taken.append(log_line)
        if not dry_run:
            _execute_action(atype, params, context)

    # Persist run log
    _log_run(workflow["id"], context, "ok" if actions_taken else "no_actions", actions_taken)

    return {
        "workflow_id":    workflow["id"],
        "workflow_name":  workflow["name"],
        "result":         "ok",
        "branch":         branch,
        "actions_taken":  actions_taken,
        "dry_run":        dry_run,
        "evaluation":     evaluation,
    }


def _execute_action(action_type: str, params: dict, context: dict):
    """
    Dispatch table for real action execution.
    Swap each stub with the actual module call in your agent.py integration.
    """
    dispatch = {
        "send_followup":      lambda: print(f"  → Sending follow-up to {context.get('contact_name')} via {params.get('platform','same')}"),
        "send_decay_checkin": lambda: print(f"  → Sending decay check-in (tone: {params.get('message_tone','warm')})"),
        "send_late_wish":     lambda: print(f"  → Sending late birthday wish to {context.get('contact_name')}"),
        "send_voice_note":    lambda: print(f"  → Sending voice note ({params.get('engine','gtts')})"),
        "trigger_ai_retry":   lambda: print(f"  → Retrying AI wish (target score ≥ {params.get('min_score',8)})"),
        "alert_dashboard":    lambda: print(f"  → Dashboard alert (priority: {params.get('priority','medium')})"),
        "send_telegram_alert":lambda: print(f"  → Telegram alert sent"),
        "send_email_alert":   lambda: print(f"  → Email alert sent"),
        "update_relationship":lambda: print(f"  → Relationship tier updated ({params.get('direction','down')})"),
        "add_contact_tag":    lambda: print(f"  → Tag added: {params.get('tag','')}"),
        "pause_contact":      lambda: print(f"  → Contact paused for {params.get('days',30)} days"),
        "log_only":           lambda: print(f"  → Logged (no action taken)"),
    }
    fn = dispatch.get(action_type)
    if fn:
        fn()


def _log_run(workflow_id: str, context: dict, result: str, actions_taken: list):
    init_workflow_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE workflows SET last_run = ?, run_count = run_count + 1 WHERE id = ?",
        (datetime.now().isoformat(), workflow_id),
    )
    conn.execute("""
        INSERT INTO workflow_run_log (workflow_id, contact_id, contact_name, result, actions_taken, ran_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        workflow_id,
        context.get("contact_id", ""),
        context.get("contact_name", ""),
        result,
        json.dumps(actions_taken),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


def get_run_log(workflow_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Return recent run log entries, optionally filtered by workflow."""
    init_workflow_tables()
    conn = sqlite3.connect(DB_PATH)
    if workflow_id:
        rows = conn.execute(
            "SELECT workflow_id, contact_name, result, actions_taken, ran_at "
            "FROM workflow_run_log WHERE workflow_id = ? ORDER BY ran_at DESC LIMIT ?",
            (workflow_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT workflow_id, contact_name, result, actions_taken, ran_at "
            "FROM workflow_run_log ORDER BY ran_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [
        {"workflow_id": r[0], "contact_name": r[1], "result": r[2],
         "actions_taken": json.loads(r[3]), "ran_at": r[4]}
        for r in rows
    ]


# ── CLI self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_workflow_tables()
    seed_builtin_workflows()

    print("=== Conditional Workflow Builder — engine self test ===\n")

    workflows = load_all_workflows()
    print(f"Loaded {len(workflows)} workflows:\n")
    for w in workflows:
        print(f"  [{('✅' if w['enabled'] else '⏸')}] {w['name']}")
        print(f"       Trigger: {w['trigger'].get('event','?')} | "
              f"Actions: {len(w['actions'])} | Else: {len(w['else_actions'])}")

    print("\n--- Evaluating 'Smart Follow-up Chain' against a test context ---\n")
    test_context = {
        "contact_id":       "urn_rakib_001",
        "contact_name":     "Rakib Hossain",
        "platform":         "LinkedIn",
        "days_since_wish":  4,
        "days_since_reply": 4,
        "relationship_type":"Colleague",
        "wish_score":       7,
        "tags":             [],
        "decay_days":       0,
    }

    followup_wf = next((w for w in workflows if "Follow-up" in w["name"]), workflows[0])
    result = run_workflow(followup_wf, test_context, dry_run=True)

    print(f"\nResult:  {result['result']}")
    print(f"Branch:  {result['branch']}")
    print("Actions:")
    for a in result["actions_taken"]:
        print(f"  {a}")

    print("\n--- Low Score workflow (score=4 → should retry) ---\n")
    low_score_ctx = {**test_context, "wish_score": 4}
    low_wf = next((w for w in workflows if "Low Score" in w["name"]), None)
    if low_wf:
        r2 = run_workflow(low_wf, low_score_ctx, dry_run=True)
        print(f"Branch: {r2['branch']} | Actions: {r2['actions_taken']}")
