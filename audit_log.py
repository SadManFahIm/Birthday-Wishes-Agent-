"""
Audit Log Module — Birthday Wishes Agent v10.0
================================================
Complete, tamper-evident trail of every data operation across
all modules.  Answers "কে কখন কী করেছে" with full before/after
snapshots, hash-chain integrity, search, export, and a Streamlit
analytics dashboard.

Author : Fahim (SadManFahIm)
Branch : feature/audit-log (→ 10.0)
"""

import sqlite3
import json
import csv
import io
import os
import uuid
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

DB_PATH = Path(os.getenv("BWA_DB_PATH", "agent_history.db"))

# Every action category the agent can emit
ACTION_CATEGORIES = {
    "wish":       ["wish_sent", "wish_scheduled", "wish_failed",
                   "wish_cancelled", "wish_retried"],
    "contact":    ["contact_created", "contact_updated",
                   "contact_deleted", "contact_imported",
                   "contact_merged", "contact_exported"],
    "consent":    ["consent_granted", "consent_revoked",
                   "consent_checked"],
    "erasure":    ["erasure_requested", "erasure_completed",
                   "erasure_dryrun"],
    "retention":  ["retention_policy_set", "retention_enforced"],
    "auth":       ["login", "logout", "token_refreshed",
                   "permission_changed"],
    "config":     ["config_updated", "model_changed",
                   "threshold_changed"],
    "system":     ["system_started", "system_stopped",
                   "migration_run", "backup_created"],
    "agent":      ["agent_decision", "agent_override",
                   "agent_escalation"],
    "integration": ["crm_sync", "calendar_sync", "notion_sync",
                    "email_sent", "wa_message_sent"],
    "export":     ["data_exported", "report_generated"],
}

ALL_ACTIONS = [a for acts in ACTION_CATEGORIES.values() for a in acts]

SEVERITY_LEVELS = ["info", "warning", "critical"]

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────


def init_audit_tables(db_path: Path = DB_PATH) -> None:
    """Create audit tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_trail (
            id              TEXT PRIMARY KEY,
            timestamp       TEXT NOT NULL,
            action          TEXT NOT NULL,
            category        TEXT NOT NULL DEFAULT 'system',
            severity        TEXT NOT NULL DEFAULT 'info',
            actor           TEXT NOT NULL DEFAULT 'system',
            actor_type      TEXT NOT NULL DEFAULT 'system',
            entity_type     TEXT,
            entity_id       TEXT,
            contact_id      TEXT,
            session_id      TEXT,
            ip_hash         TEXT,
            module          TEXT,
            summary         TEXT NOT NULL,
            details         TEXT,
            before_snapshot  TEXT,
            after_snapshot   TEXT,
            metadata         TEXT,
            prev_hash       TEXT,
            row_hash        TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_at_timestamp
            ON audit_trail(timestamp);
        CREATE INDEX IF NOT EXISTS idx_at_action
            ON audit_trail(action);
        CREATE INDEX IF NOT EXISTS idx_at_category
            ON audit_trail(category);
        CREATE INDEX IF NOT EXISTS idx_at_actor
            ON audit_trail(actor);
        CREATE INDEX IF NOT EXISTS idx_at_contact
            ON audit_trail(contact_id);
        CREATE INDEX IF NOT EXISTS idx_at_entity
            ON audit_trail(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_at_severity
            ON audit_trail(severity);
        CREATE INDEX IF NOT EXISTS idx_at_session
            ON audit_trail(session_id);
        CREATE INDEX IF NOT EXISTS idx_at_module
            ON audit_trail(module);

        CREATE TABLE IF NOT EXISTS audit_chain_state (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            last_hash   TEXT NOT NULL,
            entry_count INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_archive (
            id              TEXT PRIMARY KEY,
            archived_at     TEXT NOT NULL,
            original_ts     TEXT NOT NULL,
            action          TEXT NOT NULL,
            summary         TEXT NOT NULL,
            actor           TEXT,
            contact_id      TEXT,
            row_hash        TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_aa_original_ts
            ON audit_archive(original_ts);
    """)
    conn.commit()
    conn.close()
    logger.info("Audit tables initialised: %s", db_path)


def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a connection with row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ──────────────────────────────────────────────────────────────
# Hash-chain helpers
# ──────────────────────────────────────────────────────────────


def _compute_hash(entry_id: str, timestamp: str, action: str,
                  actor: str, summary: str, details: str,
                  prev_hash: str) -> str:
    """SHA-256 of entry fields + previous hash → tamper-evident chain."""
    payload = (f"{entry_id}|{timestamp}|{action}|{actor}"
               f"|{summary}|{details}|{prev_hash}")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_last_hash(conn: sqlite3.Connection) -> tuple[str, int]:
    """Return (last_hash, entry_count) from chain state."""
    row = conn.execute(
        "SELECT last_hash, entry_count FROM audit_chain_state WHERE id=1"
    ).fetchone()
    if row:
        return row["last_hash"], row["entry_count"]
    return "genesis", 0


def _update_chain_state(conn: sqlite3.Connection, new_hash: str,
                        new_count: int) -> None:
    """Upsert the chain state row."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO audit_chain_state (id, last_hash, entry_count, updated_at)
           VALUES (1, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE
           SET last_hash=excluded.last_hash,
               entry_count=excluded.entry_count,
               updated_at=excluded.updated_at""",
        (new_hash, new_count, now),
    )


# ──────────────────────────────────────────────────────────────
# Core: record an audit entry
# ──────────────────────────────────────────────────────────────


def record(action: str, summary: str, *,
           actor: str = "system",
           actor_type: str = "system",
           severity: str = "info",
           entity_type: str = "",
           entity_id: str = "",
           contact_id: str = "",
           session_id: str = "",
           ip_hash: str = "",
           module: str = "",
           details: str = "",
           before_snapshot: object = None,
           after_snapshot: object = None,
           metadata: object = None,
           db_path: Path = DB_PATH) -> str:
    """
    Write one tamper-evident audit entry.

    Parameters
    ----------
    action : str        – what happened (e.g. "wish_sent")
    summary : str       – human-readable one-liner
    actor : str         – who did it (user id / "system" / "agent")
    actor_type : str    – "user" | "system" | "agent" | "api"
    severity : str      – "info" | "warning" | "critical"
    entity_type : str   – e.g. "contact", "wish", "config"
    entity_id : str     – PK of affected entity
    contact_id : str    – for contact-scoped actions
    session_id : str    – ties entries to one session
    ip_hash : str       – SHA of client IP (privacy-safe)
    module : str        – originating module name
    details : str       – free-form JSON or text
    before_snapshot     – state before change (serialisable)
    after_snapshot      – state after change (serialisable)
    metadata            – any extra dict
    db_path : Path      – override DB

    Returns the audit entry id.
    """
    entry_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()

    # Resolve category from action
    category = "unknown"
    for cat, actions in ACTION_CATEGORIES.items():
        if action in actions:
            category = cat
            break

    if severity not in SEVERITY_LEVELS:
        severity = "info"

    before_json = (json.dumps(before_snapshot, default=str)
                   if before_snapshot is not None else "")
    after_json = (json.dumps(after_snapshot, default=str)
                  if after_snapshot is not None else "")
    meta_json = (json.dumps(metadata, default=str)
                 if metadata is not None else "")

    conn = _get_conn(db_path)
    try:
        prev_hash, count = _get_last_hash(conn)
        row_hash = _compute_hash(entry_id, ts, action, actor,
                                 summary, details, prev_hash)

        conn.execute(
            """INSERT INTO audit_trail
               (id, timestamp, action, category, severity,
                actor, actor_type, entity_type, entity_id,
                contact_id, session_id, ip_hash, module,
                summary, details, before_snapshot, after_snapshot,
                metadata, prev_hash, row_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (entry_id, ts, action, category, severity,
             actor, actor_type, entity_type, entity_id,
             contact_id, session_id, ip_hash, module,
             summary, details, before_json, after_json,
             meta_json, prev_hash, row_hash),
        )
        _update_chain_state(conn, row_hash, count + 1)
        conn.commit()
    finally:
        conn.close()

    return entry_id


# ──────────────────────────────────────────────────────────────
# Query helpers
# ──────────────────────────────────────────────────────────────


def search(*, action: str = "", category: str = "",
           severity: str = "", actor: str = "",
           contact_id: str = "", entity_type: str = "",
           entity_id: str = "", module: str = "",
           keyword: str = "",
           since: str = "", until: str = "",
           limit: int = 100, offset: int = 0,
           db_path: Path = DB_PATH) -> list[dict]:
    """Flexible filtered search with keyword, time range, pagination."""
    clauses = ["1=1"]
    params: list = []

    if action:
        clauses.append("action=?");           params.append(action)
    if category:
        clauses.append("category=?");         params.append(category)
    if severity:
        clauses.append("severity=?");         params.append(severity)
    if actor:
        clauses.append("actor=?");            params.append(actor)
    if contact_id:
        clauses.append("contact_id=?");       params.append(contact_id)
    if entity_type:
        clauses.append("entity_type=?");      params.append(entity_type)
    if entity_id:
        clauses.append("entity_id=?");        params.append(entity_id)
    if module:
        clauses.append("module=?");           params.append(module)
    if keyword:
        clauses.append("(summary LIKE ? OR details LIKE ?)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if since:
        clauses.append("timestamp>=?");       params.append(since)
    if until:
        clauses.append("timestamp<=?");       params.append(until)

    where = " AND ".join(clauses)
    query = (f"SELECT * FROM audit_trail WHERE {where} "
             f"ORDER BY timestamp DESC LIMIT ? OFFSET ?")
    params += [limit, offset]

    conn = _get_conn(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_entry(entry_id: str, db_path: Path = DB_PATH) -> Optional[dict]:
    """Fetch a single audit entry by id."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM audit_trail WHERE id=?", (entry_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_contact_trail(contact_id: str, limit: int = 200,
                      db_path: Path = DB_PATH) -> list[dict]:
    """Full audit trail for a single contact."""
    return search(contact_id=contact_id, limit=limit, db_path=db_path)


def get_actor_trail(actor: str, limit: int = 200,
                    db_path: Path = DB_PATH) -> list[dict]:
    """Everything a specific actor has done."""
    return search(actor=actor, limit=limit, db_path=db_path)


# ──────────────────────────────────────────────────────────────
# Analytics
# ──────────────────────────────────────────────────────────────


def get_stats(db_path: Path = DB_PATH) -> dict:
    """Aggregate analytics for the dashboard."""
    conn = _get_conn(db_path)
    try:
        total = conn.execute(
            "SELECT COUNT(*) as c FROM audit_trail"
        ).fetchone()["c"]

        by_category = conn.execute(
            """SELECT category, COUNT(*) as c FROM audit_trail
               GROUP BY category ORDER BY c DESC"""
        ).fetchall()

        by_severity = conn.execute(
            """SELECT severity, COUNT(*) as c FROM audit_trail
               GROUP BY severity ORDER BY c DESC"""
        ).fetchall()

        by_actor = conn.execute(
            """SELECT actor, COUNT(*) as c FROM audit_trail
               GROUP BY actor ORDER BY c DESC LIMIT 10"""
        ).fetchall()

        by_action_30d = conn.execute(
            """SELECT action, COUNT(*) as c FROM audit_trail
               WHERE timestamp >= datetime('now', '-30 days')
               GROUP BY action ORDER BY c DESC LIMIT 15"""
        ).fetchall()

        daily_7d = conn.execute(
            """SELECT DATE(timestamp) as day, COUNT(*) as c
               FROM audit_trail
               WHERE timestamp >= datetime('now', '-7 days')
               GROUP BY day ORDER BY day"""
        ).fetchall()

        critical_24h = conn.execute(
            """SELECT COUNT(*) as c FROM audit_trail
               WHERE severity='critical'
               AND timestamp >= datetime('now', '-24 hours')"""
        ).fetchone()["c"]

        chain = conn.execute(
            "SELECT last_hash, entry_count FROM audit_chain_state WHERE id=1"
        ).fetchone()
        chain_info = dict(chain) if chain else {"last_hash": "N/A",
                                                "entry_count": 0}

        modules_active = conn.execute(
            """SELECT DISTINCT module FROM audit_trail
               WHERE module != '' AND module IS NOT NULL"""
        ).fetchall()

        return {
            "total_entries": total,
            "by_category": [dict(r) for r in by_category],
            "by_severity": [dict(r) for r in by_severity],
            "top_actors": [dict(r) for r in by_actor],
            "top_actions_30d": [dict(r) for r in by_action_30d],
            "daily_7d": [dict(r) for r in daily_7d],
            "critical_24h": critical_24h,
            "chain": chain_info,
            "modules": [r["module"] for r in modules_active],
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Integrity verification
# ──────────────────────────────────────────────────────────────


def verify_chain(db_path: Path = DB_PATH) -> dict:
    """
    Walk the full chain and verify every hash link.
    Returns {"total", "valid", "broken_ids", "is_intact"}.
    """
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM audit_trail ORDER BY timestamp, rowid"
        ).fetchall()
        total = len(rows)
        valid = 0
        broken: list[str] = []

        expected_prev = "genesis"
        for r in rows:
            expected = _compute_hash(
                r["id"], r["timestamp"], r["action"], r["actor"],
                r["summary"], r["details"] or "", expected_prev,
            )
            if expected == r["row_hash"] and r["prev_hash"] == expected_prev:
                valid += 1
            else:
                broken.append(r["id"])
            expected_prev = r["row_hash"]

        return {"total": total, "valid": valid,
                "broken_ids": broken, "is_intact": len(broken) == 0}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Export
# ──────────────────────────────────────────────────────────────


def export_json(filepath: str, *, contact_id: str = "",
                since: str = "", until: str = "",
                db_path: Path = DB_PATH) -> dict:
    """Export filtered audit entries to a JSON file."""
    entries = search(contact_id=contact_id, since=since,
                     until=until, limit=100_000, db_path=db_path)
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w") as f:
        json.dump({"exported_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(entries), "entries": entries},
                  f, indent=2, default=str)
    fhash = hashlib.sha256(open(filepath, "rb").read()).hexdigest()

    record("data_exported",
           f"Audit log exported ({len(entries)} entries) → {filepath}",
           module="audit_log", metadata={"file": filepath, "hash": fhash},
           db_path=db_path)
    return {"file": filepath, "count": len(entries), "hash": fhash}


def export_csv(filepath: str, *, contact_id: str = "",
               since: str = "", until: str = "",
               db_path: Path = DB_PATH) -> dict:
    """Export filtered audit entries to a CSV file."""
    entries = search(contact_id=contact_id, since=since,
                     until=until, limit=100_000, db_path=db_path)
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    if not entries:
        with open(filepath, "w") as f:
            f.write("")
        return {"file": filepath, "count": 0}

    fields = list(entries[0].keys())
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(entries)

    fhash = hashlib.sha256(open(filepath, "rb").read()).hexdigest()
    record("data_exported",
           f"Audit CSV exported ({len(entries)} entries) → {filepath}",
           module="audit_log", metadata={"file": filepath, "hash": fhash},
           db_path=db_path)
    return {"file": filepath, "count": len(entries), "hash": fhash}


# ──────────────────────────────────────────────────────────────
# Archival & retention
# ──────────────────────────────────────────────────────────────


def archive_old_entries(days: int = 365,
                        db_path: Path = DB_PATH) -> dict:
    """Move entries older than *days* into audit_archive, then delete."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = _get_conn(db_path)
    try:
        old = conn.execute(
            "SELECT * FROM audit_trail WHERE timestamp < ?", (cutoff,)
        ).fetchall()

        archived = 0
        now = datetime.now(timezone.utc).isoformat()
        for r in old:
            conn.execute(
                """INSERT OR IGNORE INTO audit_archive
                   (id, archived_at, original_ts, action, summary,
                    actor, contact_id, row_hash)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (r["id"], now, r["timestamp"], r["action"],
                 r["summary"], r["actor"], r["contact_id"],
                 r["row_hash"]),
            )
            archived += 1

        if archived:
            conn.execute(
                "DELETE FROM audit_trail WHERE timestamp < ?", (cutoff,)
            )
        conn.commit()
    finally:
        conn.close()

    if archived:
        record("retention_enforced",
               f"Archived {archived} audit entries older than {days}d",
               module="audit_log",
               metadata={"cutoff": cutoff, "archived": archived},
               db_path=db_path)
    return {"archived": archived, "cutoff_days": days}


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """Full-featured audit trail dashboard with dark theme."""
    try:
        import streamlit as st
        import pandas as pd
    except ImportError:
        return

    st.set_page_config(page_title="Audit Trail", page_icon="📋",
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
    .c-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
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
    .sev-info{color:var(--blue);} .sev-warning{color:var(--yellow);}
    .sev-critical{color:var(--red);font-weight:700;}
    .chain-ok{color:var(--green);font-weight:600;}
    .chain-fail{color:var(--red);font-weight:600;}
    .tag{display:inline-block;font-size:0.65rem;padding:1px 7px;border-radius:10px;
         font-weight:600;margin-right:4px;}
    .tag-cat{background:rgba(88,166,255,0.12);color:var(--blue);}
    .tag-sev-info{background:rgba(88,166,255,0.12);color:var(--blue);}
    .tag-sev-warning{background:rgba(210,153,34,0.15);color:var(--yellow);}
    .tag-sev-critical{background:rgba(248,81,73,0.15);color:var(--red);}
    div.stTabs [data-baseweb="tab-list"]{gap:0;border-bottom:1px solid var(--border);}
    div.stTabs [data-baseweb="tab"]{color:var(--muted)!important;background:transparent!important;
        border-bottom:2px solid transparent;padding:0.5rem 1rem;}
    div.stTabs [aria-selected="true"]{color:var(--accent)!important;
        border-bottom:2px solid var(--accent)!important;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    </style>
    """, unsafe_allow_html=True)

    init_audit_tables()

    # ── Header ──
    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📋</span>
      <h1>Audit Trail</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    stats = get_stats()

    # ── KPI row ──
    st.markdown('<div class="section-title">Overview</div>',
                unsafe_allow_html=True)
    k1, k2, k3, k4, k5 = st.columns(5)
    for col, val, lbl in [
        (k1, stats["total_entries"], "Total Entries"),
        (k2, len(stats["by_category"]), "Categories"),
        (k3, len(stats["modules"]), "Active Modules"),
        (k4, stats["critical_24h"], "Critical (24h)"),
        (k5, stats["chain"]["entry_count"], "Chain Length"),
    ]:
        col.markdown(
            f'<div class="mini"><div class="mini-val">{val}</div>'
            f'<div class="mini-lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

    # ── Tabs ──
    tabs = st.tabs(["🔍 Browse", "📊 Analytics", "🔗 Chain Verify",
                     "📦 Export", "🗄 Archive"])

    # ── Tab 0 : Browse ──────────────────────────────────────
    with tabs[0]:
        st.markdown('<div class="section-title">Search &amp; Filter</div>',
                    unsafe_allow_html=True)

        f1, f2, f3, f4 = st.columns(4)
        with f1:
            flt_keyword = st.text_input("🔎 Keyword", key="kw")
        with f2:
            flt_category = st.selectbox(
                "Category", [""] + list(ACTION_CATEGORIES.keys()),
                key="fcat")
        with f3:
            flt_severity = st.selectbox(
                "Severity", [""] + SEVERITY_LEVELS, key="fsev")
        with f4:
            flt_actor = st.text_input("Actor", key="fact")

        f5, f6, f7, f8 = st.columns(4)
        with f5:
            flt_contact = st.text_input("Contact ID", key="fcid")
        with f6:
            flt_module = st.text_input("Module", key="fmod")
        with f7:
            flt_action = st.selectbox(
                "Action", [""] + ALL_ACTIONS, key="faction")
        with f8:
            flt_limit = st.number_input("Limit", 10, 1000, 50, key="flim")

        results = search(
            keyword=flt_keyword, category=flt_category,
            severity=flt_severity, actor=flt_actor,
            contact_id=flt_contact, module=flt_module,
            action=flt_action, limit=flt_limit)

        if results:
            rows_display = []
            for r in results:
                sev = r.get("severity", "info")
                sev_cls = f"tag-sev-{sev}"
                rows_display.append({
                    "Time": r["timestamp"][:19],
                    "Severity": sev.upper(),
                    "Category": r.get("category", ""),
                    "Action": r["action"],
                    "Actor": r["actor"],
                    "Summary": r["summary"][:80],
                    "Contact": r.get("contact_id", "")[:12],
                    "Module": r.get("module", ""),
                })
            df = pd.DataFrame(rows_display)
            st.dataframe(df, use_container_width=True, height=420)

            # Detail expander
            st.markdown('<div class="section-title">Entry Detail</div>',
                        unsafe_allow_html=True)
            sel_idx = st.selectbox(
                "Select row #", range(len(results)),
                format_func=lambda i: (
                    f"{results[i]['timestamp'][:19]} | "
                    f"{results[i]['action']} | "
                    f"{results[i]['summary'][:50]}"),
                key="sel_row")
            sel = results[sel_idx]
            with st.expander("Full entry JSON", expanded=True):
                st.json(sel)

            if sel.get("before_snapshot"):
                with st.expander("Before snapshot"):
                    try:
                        st.json(json.loads(sel["before_snapshot"]))
                    except Exception:
                        st.code(sel["before_snapshot"])
            if sel.get("after_snapshot"):
                with st.expander("After snapshot"):
                    try:
                        st.json(json.loads(sel["after_snapshot"]))
                    except Exception:
                        st.code(sel["after_snapshot"])
        else:
            st.info("No entries match the current filters.")

    # ── Tab 1 : Analytics ───────────────────────────────────
    with tabs[1]:
        st.markdown('<div class="section-title">30-Day Activity</div>',
                    unsafe_allow_html=True)

        # Category breakdown
        cat_col, sev_col = st.columns(2)
        with cat_col:
            st.markdown('<div class="c-card">', unsafe_allow_html=True)
            st.markdown("**By Category**")
            for item in stats["by_category"]:
                pct = (item["c"] / max(stats["total_entries"], 1)) * 100
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;'
                    f'margin:4px 0">'
                    f'<span class="tag tag-cat">{item["category"]}</span>'
                    f'<div style="flex:1;background:#0d1117;border-radius:3px;'
                    f'height:14px">'
                    f'<div style="width:{pct:.0f}%;background:var(--blue);'
                    f'height:14px;border-radius:3px"></div></div>'
                    f'<span style="font-size:0.75rem;color:var(--muted);'
                    f'min-width:36px;text-align:right">{item["c"]}</span>'
                    f'</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with sev_col:
            st.markdown('<div class="c-card">', unsafe_allow_html=True)
            st.markdown("**By Severity**")
            sev_colors = {"info": "--blue", "warning": "--yellow",
                          "critical": "--red"}
            for item in stats["by_severity"]:
                sev = item["severity"]
                color = sev_colors.get(sev, "--muted")
                pct = (item["c"] / max(stats["total_entries"], 1)) * 100
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;'
                    f'margin:4px 0">'
                    f'<span class="tag tag-sev-{sev}">{sev.upper()}</span>'
                    f'<div style="flex:1;background:#0d1117;border-radius:3px;'
                    f'height:14px">'
                    f'<div style="width:{pct:.0f}%;background:var({color});'
                    f'height:14px;border-radius:3px"></div></div>'
                    f'<span style="font-size:0.75rem;color:var(--muted);'
                    f'min-width:36px;text-align:right">{item["c"]}</span>'
                    f'</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        # Top actors
        st.markdown('<div class="section-title">Top Actors</div>',
                    unsafe_allow_html=True)
        if stats["top_actors"]:
            actor_df = pd.DataFrame(stats["top_actors"])
            actor_df.columns = ["Actor", "Actions"]
            st.dataframe(actor_df, use_container_width=True, height=200)

        # Top actions last 30d
        st.markdown('<div class="section-title">Top Actions (30 days)</div>',
                    unsafe_allow_html=True)
        if stats["top_actions_30d"]:
            act_df = pd.DataFrame(stats["top_actions_30d"])
            act_df.columns = ["Action", "Count"]
            st.dataframe(act_df, use_container_width=True, height=280)

        # Daily chart (last 7d)
        st.markdown('<div class="section-title">Daily Volume (7 days)'
                    '</div>', unsafe_allow_html=True)
        if stats["daily_7d"]:
            d7 = pd.DataFrame(stats["daily_7d"])
            d7.columns = ["Date", "Entries"]
            st.bar_chart(d7.set_index("Date"), color="#f78166", height=220)

    # ── Tab 2 : Chain Verify ────────────────────────────────
    with tabs[2]:
        st.markdown('<div class="section-title">Hash-Chain Integrity'
                    '</div>', unsafe_allow_html=True)
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        st.markdown(
            "Every audit entry is SHA-256 linked to the previous one. "
            "Tampering with any row breaks the chain from that point "
            "forward.")

        if st.button("🔐 Verify Full Chain", key="btn_verify"):
            result = verify_chain()
            if result["is_intact"]:
                st.markdown(
                    f'<p class="chain-ok">✅ Chain intact — '
                    f'{result["valid"]}/{result["total"]} entries '
                    f'verified</p>', unsafe_allow_html=True)
            else:
                st.markdown(
                    f'<p class="chain-fail">❌ Chain broken — '
                    f'{len(result["broken_ids"])} tampered entries '
                    f'detected</p>', unsafe_allow_html=True)
                st.json(result["broken_ids"][:20])

        st.markdown(
            f'<p style="font-size:0.75rem;color:var(--muted);margin-top:12px">'
            f'Chain length: {stats["chain"]["entry_count"]} · '
            f'Last hash: <code>{stats["chain"]["last_hash"][:16]}…</code>'
            f'</p>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Tab 3 : Export ──────────────────────────────────────
    with tabs[3]:
        st.markdown('<div class="section-title">Export Audit Data</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="c-card">', unsafe_allow_html=True)

        ex1, ex2 = st.columns(2)
        with ex1:
            ex_contact = st.text_input("Contact ID (optional)",
                                       key="ex_cid")
        with ex2:
            ex_format = st.selectbox("Format", ["JSON", "CSV"],
                                     key="ex_fmt")

        if st.button("📥 Export", key="btn_export"):
            os.makedirs("exports", exist_ok=True)
            ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            ext = "json" if ex_format == "JSON" else "csv"
            fpath = f"exports/audit_export_{ts_slug}.{ext}"

            if ex_format == "JSON":
                result = export_json(fpath, contact_id=ex_contact)
            else:
                result = export_csv(fpath, contact_id=ex_contact)

            st.success(f"Exported {result['count']} entries → {fpath}")
            st.json(result)

        st.markdown('</div>', unsafe_allow_html=True)

    # ── Tab 4 : Archive ─────────────────────────────────────
    with tabs[4]:
        st.markdown('<div class="section-title">Archival &amp; Retention'
                    '</div>', unsafe_allow_html=True)
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        st.markdown(
            "Move old audit entries to a compact archive table "
            "and purge from the active trail.")

        arc_days = st.number_input(
            "Archive entries older than (days)",
            min_value=30, max_value=3650, value=365, key="arc_days")
        if st.button("🗄 Archive Now", key="btn_archive"):
            result = archive_old_entries(arc_days)
            st.success(
                f"Archived {result['archived']} entries "
                f"older than {result['cutoff_days']} days")

        # Show archive stats
        conn = _get_conn()
        arc_count = conn.execute(
            "SELECT COUNT(*) as c FROM audit_archive"
        ).fetchone()["c"]
        conn.close()
        st.markdown(
            f'<p style="font-size:0.75rem;color:var(--muted);margin-top:8px">'
            f'Archived entries: {arc_count}</p>',
            unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Footer ──
    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/audit-log</code> · Audit Trail v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test covering all audit functions."""
    import tempfile

    print("=" * 60)
    print("Audit Log Module — Self-Test")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    try:
        init_audit_tables(tdb)

        # 1. Record entries with different categories
        print("\n[1/8] Recording entries ...")
        ids = []
        test_data = [
            ("wish_sent", "Sent birthday wish to Alice",
             {"actor": "system", "module": "agent",
              "contact_id": "c-001", "severity": "info"}),
            ("contact_created", "New contact Bob imported",
             {"actor": "admin", "actor_type": "user",
              "module": "crm_sync", "contact_id": "c-002",
              "severity": "info",
              "after_snapshot": {"name": "Bob", "phone": "+880"}}),
            ("consent_revoked", "Alice revoked marketing consent",
             {"actor": "alice", "actor_type": "user",
              "module": "gdpr", "contact_id": "c-001",
              "severity": "warning"}),
            ("erasure_completed", "Full erasure for contact c-003",
             {"actor": "admin", "actor_type": "user",
              "module": "gdpr", "contact_id": "c-003",
              "severity": "critical",
              "before_snapshot": {"tables": 22, "rows": 158}}),
            ("config_updated", "Model changed to gpt-4o-mini",
             {"actor": "admin", "module": "model_config",
              "severity": "warning",
              "before_snapshot": {"model": "gpt-4"},
              "after_snapshot": {"model": "gpt-4o-mini"}}),
            ("agent_decision", "Auto-scheduled wish for VIP contact",
             {"actor": "agent", "actor_type": "agent",
              "module": "autonomous_agent", "contact_id": "c-004",
              "severity": "info"}),
            ("crm_sync", "Synced 45 contacts from CRM",
             {"actor": "system", "module": "crm_sync",
              "severity": "info",
              "metadata": {"synced": 45, "errors": 0}}),
        ]
        for action, summary, kwargs in test_data:
            eid = record(action, summary, db_path=tdb, **kwargs)
            ids.append(eid)
        print(f"      ✅ {len(ids)} entries recorded")

        # 2. Search by keyword
        print("[2/8] Keyword search ...")
        hits = search(keyword="Alice", db_path=tdb)
        assert len(hits) >= 2, f"Expected ≥2 hits, got {len(hits)}"
        print(f"      ✅ 'Alice' → {len(hits)} hits")

        # 3. Search by category
        print("[3/8] Category filter ...")
        hits = search(category="consent", db_path=tdb)
        assert len(hits) >= 1
        print(f"      ✅ consent category → {len(hits)} hit(s)")

        # 4. Search by severity
        print("[4/8] Severity filter ...")
        hits = search(severity="critical", db_path=tdb)
        assert len(hits) >= 1
        assert hits[0]["action"] == "erasure_completed"
        print(f"      ✅ critical → {len(hits)} hit(s)")

        # 5. Contact trail
        print("[5/8] Contact trail ...")
        trail = get_contact_trail("c-001", db_path=tdb)
        assert len(trail) >= 2
        print(f"      ✅ c-001 trail → {len(trail)} entries")

        # 6. Single entry retrieval
        print("[6/8] Get single entry ...")
        entry = get_entry(ids[1], db_path=tdb)
        assert entry is not None
        assert entry["action"] == "contact_created"
        after = json.loads(entry["after_snapshot"])
        assert after["name"] == "Bob"
        print(f"      ✅ Entry retrieved with after_snapshot")

        # 7. Chain verification
        print("[7/8] Chain integrity ...")
        result = verify_chain(db_path=tdb)
        assert result["is_intact"], f"Chain broken! IDs: {result['broken_ids']}"
        print(f"      ✅ Chain intact — {result['valid']}/{result['total']}")

        # 8. Export + stats
        print("[8/8] Export & stats ...")
        with tempfile.TemporaryDirectory() as tmpdir:
            jres = export_json(f"{tmpdir}/audit.json", db_path=tdb)
            assert jres["count"] >= 7
            cres = export_csv(f"{tmpdir}/audit.csv", db_path=tdb)
            assert cres["count"] >= 7
            print(f"      ✅ JSON: {jres['count']} rows, "
                  f"CSV: {cres['count']} rows")

        st = get_stats(db_path=tdb)
        assert st["total_entries"] >= 7
        print(f"      ✅ Stats: {st['total_entries']} total, "
              f"{len(st['by_category'])} categories, "
              f"{st['critical_24h']} critical(24h)")

        print("\n" + "=" * 60)
        print("✅ ALL AUDIT LOG SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(tdb)


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_audit_tables()
    print("=== Audit Log -- self test ===\n")
    _self_test()
else:
    render_dashboard()
