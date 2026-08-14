"""
GDPR Compliance Module — Birthday Wishes Agent v10.0
=====================================================
Data retention, right-to-forget, consent tracking, audit logging,
and data portability (JSON export) for GDPR/privacy compliance.

Author: Fahim (SadManFahIm)
Branch: 10.0
"""

import sqlite3
import json
import os
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = os.getenv("BWA_DB_PATH", "agent_history.db")

DEFAULT_RETENTION_DAYS = 365  # 1 year default

# Every table that stores per-contact data — right-to-forget must purge ALL.
CONTACT_TABLES = [
    "wish_outcome_log",
    "contact_tier",
    "tier_change_log",
    "vip_contacts",
    "reply_sentiment_log",
    "conversation_notes",
    "conversation_summaries",
    "interest_signals",
    "interest_profiles",
    "vector_memories",
    "churn_predictions",
    "roi_forecasts",
    "wish_predictions",
    "revenue_attributions",
    "revenue_contacts",
    "calendar_sync_log",
    "notion_sync_log",
    "email_outreach_log",
    "wa_status_log",
    "graph_nodes",
    "graph_edges",
    "autonomous_decisions",
]

# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------


def _ensure_gdpr_tables(conn: sqlite3.Connection) -> None:
    """Create GDPR-specific tables if they don't exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gdpr_consent (
            id              TEXT PRIMARY KEY,
            contact_id      TEXT NOT NULL,
            consent_type    TEXT NOT NULL DEFAULT 'birthday_wish',
            granted         INTEGER NOT NULL DEFAULT 0,
            granted_at      TEXT,
            revoked_at      TEXT,
            source          TEXT DEFAULT 'manual',
            ip_hash         TEXT,
            notes           TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_consent_contact
            ON gdpr_consent(contact_id);
        CREATE INDEX IF NOT EXISTS idx_consent_type
            ON gdpr_consent(contact_id, consent_type);

        CREATE TABLE IF NOT EXISTS gdpr_audit_log (
            id              TEXT PRIMARY KEY,
            timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
            action          TEXT NOT NULL,
            entity_type     TEXT NOT NULL,
            entity_id       TEXT,
            contact_id      TEXT,
            actor           TEXT DEFAULT 'system',
            details         TEXT,
            checksum        TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON gdpr_audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_contact
            ON gdpr_audit_log(contact_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action
            ON gdpr_audit_log(action);

        CREATE TABLE IF NOT EXISTS gdpr_retention_policy (
            id              TEXT PRIMARY KEY,
            table_name      TEXT NOT NULL,
            retention_days  INTEGER NOT NULL DEFAULT 365,
            enabled         INTEGER NOT NULL DEFAULT 1,
            last_purge_at   TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_retention_table
            ON gdpr_retention_policy(table_name);

        CREATE TABLE IF NOT EXISTS gdpr_data_export_log (
            id              TEXT PRIMARY KEY,
            contact_id      TEXT NOT NULL,
            requested_at    TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at    TEXT,
            file_path       TEXT,
            file_hash       TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            actor           TEXT DEFAULT 'system'
        );

        CREATE INDEX IF NOT EXISTS idx_export_contact
            ON gdpr_data_export_log(contact_id);
        """
    )
    conn.commit()


def _get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Return a connection with WAL mode and GDPR tables guaranteed."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_gdpr_tables(conn)
    return conn


# ---------------------------------------------------------------------------
# Audit logging (tamper-evident)
# ---------------------------------------------------------------------------


def _checksum(action: str, entity_type: str, entity_id: str,
              contact_id: str, actor: str, details: str,
              timestamp: str) -> str:
    """SHA-256 checksum for tamper detection on audit rows."""
    payload = f"{timestamp}|{action}|{entity_type}|{entity_id}|{contact_id}|{actor}|{details}"
    return hashlib.sha256(payload.encode()).hexdigest()


def log_audit(conn: sqlite3.Connection, action: str, entity_type: str,
              entity_id: str = "", contact_id: str = "",
              actor: str = "system", details: str = "") -> str:
    """Insert a tamper-evident audit row. Returns the audit id."""
    audit_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    chk = _checksum(action, entity_type, entity_id, contact_id, actor,
                    details, ts)
    conn.execute(
        """INSERT INTO gdpr_audit_log
           (id, timestamp, action, entity_type, entity_id,
            contact_id, actor, details, checksum)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (audit_id, ts, action, entity_type, entity_id,
         contact_id, actor, details, chk),
    )
    conn.commit()
    return audit_id


def verify_audit_integrity(conn: sqlite3.Connection) -> dict:
    """Verify every audit row's checksum. Returns stats dict."""
    rows = conn.execute(
        "SELECT * FROM gdpr_audit_log ORDER BY timestamp"
    ).fetchall()
    total = len(rows)
    valid = 0
    tampered = []
    for r in rows:
        expected = _checksum(
            r["action"], r["entity_type"], r["entity_id"] or "",
            r["contact_id"] or "", r["actor"] or "system",
            r["details"] or "", r["timestamp"],
        )
        if expected == r["checksum"]:
            valid += 1
        else:
            tampered.append(r["id"])
    return {"total": total, "valid": valid, "tampered_ids": tampered}


# ---------------------------------------------------------------------------
# Consent management
# ---------------------------------------------------------------------------


def record_consent(conn: sqlite3.Connection, contact_id: str,
                   consent_type: str = "birthday_wish",
                   granted: bool = True, source: str = "manual",
                   ip_hash: str = "", notes: str = "",
                   actor: str = "system") -> str:
    """Record or update consent for a contact. Returns consent id."""
    # Check existing
    existing = conn.execute(
        "SELECT id FROM gdpr_consent WHERE contact_id=? AND consent_type=?",
        (contact_id, consent_type),
    ).fetchone()

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        consent_id = existing["id"]
        if granted:
            conn.execute(
                """UPDATE gdpr_consent
                   SET granted=1, granted_at=?, revoked_at=NULL,
                       source=?, ip_hash=?, notes=?, updated_at=?
                   WHERE id=?""",
                (now, source, ip_hash, notes, now, consent_id),
            )
        else:
            conn.execute(
                """UPDATE gdpr_consent
                   SET granted=0, revoked_at=?, source=?,
                       ip_hash=?, notes=?, updated_at=?
                   WHERE id=?""",
                (now, source, ip_hash, notes, now, consent_id),
            )
    else:
        consent_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO gdpr_consent
               (id, contact_id, consent_type, granted, granted_at,
                revoked_at, source, ip_hash, notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (consent_id, contact_id, consent_type,
             1 if granted else 0,
             now if granted else None,
             None if granted else now,
             source, ip_hash, notes, now, now),
        )
    conn.commit()

    log_audit(conn, "consent_recorded", "gdpr_consent", consent_id,
              contact_id, actor,
              json.dumps({"type": consent_type, "granted": granted,
                          "source": source}))
    return consent_id


def check_consent(conn: sqlite3.Connection, contact_id: str,
                  consent_type: str = "birthday_wish") -> bool:
    """Return True if the contact has active consent for the given type."""
    row = conn.execute(
        """SELECT granted FROM gdpr_consent
           WHERE contact_id=? AND consent_type=?
           ORDER BY updated_at DESC LIMIT 1""",
        (contact_id, consent_type),
    ).fetchone()
    return bool(row and row["granted"])


def get_consent_history(conn: sqlite3.Connection,
                        contact_id: str) -> list[dict]:
    """Return full consent history for a contact."""
    rows = conn.execute(
        """SELECT * FROM gdpr_consent
           WHERE contact_id=? ORDER BY updated_at DESC""",
        (contact_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Right to forget (erasure)
# ---------------------------------------------------------------------------


def _table_has_column(conn: sqlite3.Connection, table: str,
                      column: str) -> bool:
    """Check if a table exists and has the given column."""
    try:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(col["name"] == column for col in info)
    except Exception:
        return False


def right_to_forget(conn: sqlite3.Connection, contact_id: str,
                    actor: str = "system",
                    dry_run: bool = False) -> dict:
    """
    Delete ALL data for a contact across every known table.
    Returns a summary of rows deleted per table.

    If dry_run=True, counts rows but doesn't delete.
    """
    summary: dict[str, int] = {}
    total_deleted = 0

    for table in CONTACT_TABLES:
        if not _table_has_column(conn, table, "contact_id"):
            summary[table] = -1  # table missing or no contact_id col
            continue

        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM {table} WHERE contact_id=?",
            (contact_id,),
        ).fetchone()
        count = count_row["cnt"] if count_row else 0

        if not dry_run and count > 0:
            conn.execute(
                f"DELETE FROM {table} WHERE contact_id=?",
                (contact_id,),
            )
        summary[table] = count
        total_deleted += max(count, 0)

    # Also purge from GDPR's own consent table
    consent_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM gdpr_consent WHERE contact_id=?",
        (contact_id,),
    ).fetchone()["cnt"]
    if not dry_run and consent_count > 0:
        conn.execute(
            "DELETE FROM gdpr_consent WHERE contact_id=?", (contact_id,)
        )
    summary["gdpr_consent"] = consent_count
    total_deleted += consent_count

    if not dry_run:
        conn.commit()

    # Audit (always logged, even dry-run)
    log_audit(
        conn, "right_to_forget" if not dry_run else "right_to_forget_dryrun",
        "contact", contact_id, contact_id, actor,
        json.dumps({"rows_affected": total_deleted, "breakdown": summary,
                     "dry_run": dry_run}),
    )
    return {"contact_id": contact_id, "total_deleted": total_deleted,
            "dry_run": dry_run, "tables": summary}


# ---------------------------------------------------------------------------
# Data retention policy
# ---------------------------------------------------------------------------


def set_retention_policy(conn: sqlite3.Connection, table_name: str,
                         retention_days: int = DEFAULT_RETENTION_DAYS,
                         enabled: bool = True,
                         actor: str = "system") -> str:
    """Create or update a retention policy for a table."""
    existing = conn.execute(
        "SELECT id FROM gdpr_retention_policy WHERE table_name=?",
        (table_name,),
    ).fetchone()

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        policy_id = existing["id"]
        conn.execute(
            """UPDATE gdpr_retention_policy
               SET retention_days=?, enabled=?, updated_at=?
               WHERE id=?""",
            (retention_days, 1 if enabled else 0, now, policy_id),
        )
    else:
        policy_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO gdpr_retention_policy
               (id, table_name, retention_days, enabled, created_at, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (policy_id, table_name, retention_days,
             1 if enabled else 0, now, now),
        )
    conn.commit()

    log_audit(conn, "retention_policy_set", "gdpr_retention_policy",
              policy_id, "", actor,
              json.dumps({"table": table_name, "days": retention_days,
                          "enabled": enabled}))
    return policy_id


def get_retention_policies(conn: sqlite3.Connection) -> list[dict]:
    """Return all retention policies."""
    rows = conn.execute(
        "SELECT * FROM gdpr_retention_policy ORDER BY table_name"
    ).fetchall()
    return [dict(r) for r in rows]


def enforce_retention(conn: sqlite3.Connection,
                      actor: str = "system") -> dict:
    """
    Purge rows older than each table's retention window.
    Looks for a 'created_at' column in each target table.
    Returns summary of purged counts.
    """
    policies = conn.execute(
        "SELECT * FROM gdpr_retention_policy WHERE enabled=1"
    ).fetchall()

    results: dict[str, int] = {}
    total = 0

    for pol in policies:
        tbl = pol["table_name"]
        days = pol["retention_days"]

        if not _table_has_column(conn, tbl, "created_at"):
            results[tbl] = -1
            continue

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM {tbl} WHERE created_at < ?",
            (cutoff,),
        ).fetchone()
        count = count_row["cnt"] if count_row else 0

        if count > 0:
            conn.execute(
                f"DELETE FROM {tbl} WHERE created_at < ?", (cutoff,)
            )
        results[tbl] = count
        total += count

        # Update last_purge_at
        conn.execute(
            """UPDATE gdpr_retention_policy
               SET last_purge_at=?, updated_at=? WHERE id=?""",
            (datetime.now(timezone.utc).isoformat(),
             datetime.now(timezone.utc).isoformat(), pol["id"]),
        )

    conn.commit()
    log_audit(conn, "retention_enforced", "gdpr_retention_policy",
              "", "", actor,
              json.dumps({"total_purged": total, "breakdown": results}))
    return {"total_purged": total, "tables": results}


# ---------------------------------------------------------------------------
# Data portability — export contact data as JSON
# ---------------------------------------------------------------------------


def export_contact_data(conn: sqlite3.Connection, contact_id: str,
                        output_dir: str = "exports",
                        actor: str = "system") -> dict:
    """
    Export ALL data for a contact as a JSON file.
    Returns metadata dict with file path and hash.
    """
    export_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Log pending export
    conn.execute(
        """INSERT INTO gdpr_data_export_log
           (id, contact_id, requested_at, status, actor)
           VALUES (?,?,?,?,?)""",
        (export_id, contact_id, now, "pending", actor),
    )
    conn.commit()

    payload: dict = {
        "export_id": export_id,
        "contact_id": contact_id,
        "exported_at": now,
        "tables": {},
    }

    for table in CONTACT_TABLES:
        if not _table_has_column(conn, table, "contact_id"):
            continue
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE contact_id=?",
            (contact_id,),
        ).fetchall()
        payload["tables"][table] = [dict(r) for r in rows]

    # Include consent records
    consent_rows = conn.execute(
        "SELECT * FROM gdpr_consent WHERE contact_id=?",
        (contact_id,),
    ).fetchall()
    payload["tables"]["gdpr_consent"] = [dict(r) for r in consent_rows]

    # Write file
    os.makedirs(output_dir, exist_ok=True)
    filename = f"gdpr_export_{contact_id}_{now.replace(':', '-')}.json"
    filepath = os.path.join(output_dir, filename)

    json_bytes = json.dumps(payload, indent=2, default=str).encode()
    file_hash = hashlib.sha256(json_bytes).hexdigest()
    with open(filepath, "w") as f:
        f.write(json_bytes.decode())

    # Update export log
    conn.execute(
        """UPDATE gdpr_data_export_log
           SET completed_at=?, file_path=?, file_hash=?, status=?
           WHERE id=?""",
        (datetime.now(timezone.utc).isoformat(), filepath, file_hash,
         "completed", export_id),
    )
    conn.commit()

    log_audit(conn, "data_exported", "contact", export_id,
              contact_id, actor,
              json.dumps({"file": filepath, "hash": file_hash}))

    return {"export_id": export_id, "contact_id": contact_id,
            "file_path": filepath, "file_hash": file_hash,
            "status": "completed",
            "record_count": sum(
                len(v) for v in payload["tables"].values())}


def get_export_history(conn: sqlite3.Connection,
                       contact_id: Optional[str] = None) -> list[dict]:
    """Return export history, optionally filtered by contact."""
    if contact_id:
        rows = conn.execute(
            """SELECT * FROM gdpr_data_export_log
               WHERE contact_id=? ORDER BY requested_at DESC""",
            (contact_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM gdpr_data_export_log ORDER BY requested_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats & helpers
# ---------------------------------------------------------------------------


def get_gdpr_stats(conn: sqlite3.Connection) -> dict:
    """Aggregate GDPR compliance stats for the dashboard."""
    consent_total = conn.execute(
        "SELECT COUNT(*) as cnt FROM gdpr_consent"
    ).fetchone()["cnt"]
    consent_active = conn.execute(
        "SELECT COUNT(*) as cnt FROM gdpr_consent WHERE granted=1"
    ).fetchone()["cnt"]
    consent_revoked = conn.execute(
        "SELECT COUNT(*) as cnt FROM gdpr_consent WHERE granted=0"
    ).fetchone()["cnt"]

    audit_total = conn.execute(
        "SELECT COUNT(*) as cnt FROM gdpr_audit_log"
    ).fetchone()["cnt"]

    recent_audits = conn.execute(
        """SELECT action, COUNT(*) as cnt FROM gdpr_audit_log
           WHERE timestamp > datetime('now', '-30 days')
           GROUP BY action ORDER BY cnt DESC"""
    ).fetchall()

    policies = conn.execute(
        "SELECT COUNT(*) as cnt FROM gdpr_retention_policy WHERE enabled=1"
    ).fetchone()["cnt"]

    exports = conn.execute(
        "SELECT COUNT(*) as cnt FROM gdpr_data_export_log WHERE status='completed'"
    ).fetchone()["cnt"]

    erasures = conn.execute(
        """SELECT COUNT(*) as cnt FROM gdpr_audit_log
           WHERE action='right_to_forget'"""
    ).fetchone()["cnt"]

    return {
        "consent": {
            "total": consent_total,
            "active": consent_active,
            "revoked": consent_revoked,
        },
        "audit": {
            "total_entries": audit_total,
            "recent_30d": [dict(r) for r in recent_audits],
        },
        "retention_policies_active": policies,
        "exports_completed": exports,
        "erasures_completed": erasures,
    }


def get_audit_log(conn: sqlite3.Connection,
                  limit: int = 50,
                  contact_id: Optional[str] = None,
                  action_filter: Optional[str] = None) -> list[dict]:
    """Return audit log entries with optional filters."""
    query = "SELECT * FROM gdpr_audit_log WHERE 1=1"
    params: list = []
    if contact_id:
        query += " AND contact_id=?"
        params.append(contact_id)
    if action_filter:
        query += " AND action=?"
        params.append(action_filter)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Streamlit Dashboard
# ---------------------------------------------------------------------------


def render_dashboard():
    """Streamlit GDPR compliance dashboard with dark theme."""
    import streamlit as st

    st.set_page_config(
        page_title="GDPR Compliance — Birthday Wishes Agent",
        page_icon="🔒",
        layout="wide",
    )

    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        :root {
            --bg: #0d1117;
            --surface: #161b22;
            --accent: #f78166;
            --accent-dim: rgba(247,129,102,0.15);
            --text: #c9d1d9;
            --text-muted: #8b949e;
            --border: #30363d;
            --green: #3fb950;
            --red: #f85149;
            --yellow: #d29922;
            --blue: #58a6ff;
        }
        .stApp { background: var(--bg) !important; font-family: 'Inter', sans-serif; }
        section[data-testid="stSidebar"] {
            background: var(--surface) !important;
            border-right: 1px solid var(--border);
        }
        h1,h2,h3,h4,h5,h6,p,span,div,label { color: var(--text) !important; }
        .stSelectbox label, .stTextInput label, .stNumberInput label {
            color: var(--text-muted) !important;
        }
        div[data-testid="stMetricValue"] { color: var(--accent) !important; font-weight: 700; }
        div[data-testid="stMetricLabel"] { color: var(--text-muted) !important; }
        .stDataFrame { border: 1px solid var(--border); border-radius: 8px; }
        .stButton > button {
            background: var(--accent) !important;
            color: #0d1117 !important;
            border: none; border-radius: 6px;
            font-weight: 600; padding: 0.5rem 1.2rem;
        }
        .stButton > button:hover { opacity: 0.85; }
        div.stTabs [data-baseweb="tab-list"] {
            gap: 0; border-bottom: 1px solid var(--border);
        }
        div.stTabs [data-baseweb="tab"] {
            color: var(--text-muted) !important;
            background: transparent !important;
            border-bottom: 2px solid transparent;
            padding: 0.5rem 1rem;
        }
        div.stTabs [aria-selected="true"] {
            color: var(--accent) !important;
            border-bottom: 2px solid var(--accent) !important;
        }
        .gdpr-card {
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem;
        }
        .gdpr-badge-ok {
            background: rgba(63,185,80,0.15); color: var(--green);
            padding: 2px 8px; border-radius: 12px; font-size: 0.8rem;
            font-weight: 600;
        }
        .gdpr-badge-warn {
            background: rgba(210,153,34,0.15); color: var(--yellow);
            padding: 2px 8px; border-radius: 12px; font-size: 0.8rem;
            font-weight: 600;
        }
        .gdpr-badge-err {
            background: rgba(248,81,73,0.15); color: var(--red);
            padding: 2px 8px; border-radius: 12px; font-size: 0.8rem;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    conn = _get_conn()
    stats = get_gdpr_stats(conn)

    # Header
    st.markdown(
        """
        <div style="display:flex; align-items:center; gap:12px;
                    margin-bottom:1.5rem;">
            <span style="font-size:2rem;">🔒</span>
            <div>
                <h1 style="margin:0; font-size:1.6rem; font-weight:700;">
                    GDPR Compliance Center
                </h1>
                <p style="margin:0; color:var(--text-muted) !important;
                          font-size:0.85rem;">
                    Birthday Wishes Agent v10.0 — Data privacy dashboard
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # KPI row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Active Consents", stats["consent"]["active"])
    c2.metric("Revoked", stats["consent"]["revoked"])
    c3.metric("Erasures Done", stats["erasures_completed"])
    c4.metric("Exports Done", stats["exports_completed"])
    c5.metric("Audit Entries", stats["audit"]["total_entries"])

    # Tabs
    tabs = st.tabs([
        "🛡 Consent", "🗑 Right to Forget", "📦 Data Export",
        "⏳ Retention", "📋 Audit Log", "✅ Integrity Check",
    ])

    # -- Tab 0: Consent Management -------------------------------------------
    with tabs[0]:
        st.subheader("Manage Contact Consent")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="gdpr-card">', unsafe_allow_html=True)
            cid = st.text_input("Contact ID", key="consent_cid")
            ctype = st.selectbox(
                "Consent Type",
                ["birthday_wish", "marketing", "analytics", "data_sharing"],
                key="consent_type",
            )
            csource = st.selectbox(
                "Source", ["manual", "web_form", "api", "import"],
                key="consent_src",
            )
            gc1, gc2 = st.columns(2)
            with gc1:
                if st.button("✅ Grant Consent", key="btn_grant"):
                    if cid.strip():
                        record_consent(conn, cid.strip(), ctype,
                                       True, csource)
                        st.success(f"Consent granted for {cid}")
                        st.rerun()
            with gc2:
                if st.button("❌ Revoke Consent", key="btn_revoke"):
                    if cid.strip():
                        record_consent(conn, cid.strip(), ctype,
                                       False, csource)
                        st.warning(f"Consent revoked for {cid}")
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        with col_b:
            st.markdown('<div class="gdpr-card">', unsafe_allow_html=True)
            st.markdown("**Quick Check**")
            check_id = st.text_input("Contact ID to check", key="chk_cid")
            if check_id.strip():
                for ct in ["birthday_wish", "marketing",
                           "analytics", "data_sharing"]:
                    has = check_consent(conn, check_id.strip(), ct)
                    badge = "gdpr-badge-ok" if has else "gdpr-badge-err"
                    label = "Granted" if has else "Not granted"
                    st.markdown(
                        f'<span class="{badge}">{label}</span> {ct}',
                        unsafe_allow_html=True,
                    )
            st.markdown('</div>', unsafe_allow_html=True)

        # Consent history
        if cid and cid.strip():
            history = get_consent_history(conn, cid.strip())
            if history:
                st.markdown("**Consent History**")
                import pandas as pd
                st.dataframe(pd.DataFrame(history), use_container_width=True)

    # -- Tab 1: Right to Forget -----------------------------------------------
    with tabs[1]:
        st.subheader("Right to Erasure (Article 17)")
        st.markdown(
            '<div class="gdpr-card">', unsafe_allow_html=True
        )
        forget_id = st.text_input(
            "Contact ID to erase", key="forget_cid"
        )
        fc1, fc2 = st.columns(2)
        with fc1:
            if st.button("🔍 Dry Run (preview)", key="btn_dryrun"):
                if forget_id.strip():
                    result = right_to_forget(conn, forget_id.strip(),
                                             dry_run=True)
                    st.json(result)
        with fc2:
            if st.button("🗑️ Erase All Data", key="btn_erase",
                         type="primary"):
                if forget_id.strip():
                    result = right_to_forget(conn, forget_id.strip())
                    st.success(
                        f"Erased {result['total_deleted']} rows "
                        f"for contact {forget_id}"
                    )
                    st.json(result)
        st.markdown(
            f"<p style='color:var(--text-muted); font-size:0.8rem;'>"
            f"Scans {len(CONTACT_TABLES)} tables + gdpr_consent</p>",
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

    # -- Tab 2: Data Export ---------------------------------------------------
    with tabs[2]:
        st.subheader("Data Portability (Article 20)")
        st.markdown('<div class="gdpr-card">', unsafe_allow_html=True)
        export_cid = st.text_input(
            "Contact ID to export", key="export_cid"
        )
        if st.button("📦 Export as JSON", key="btn_export"):
            if export_cid.strip():
                result = export_contact_data(conn, export_cid.strip())
                st.success(
                    f"Exported {result['record_count']} records → "
                    f"{result['file_path']}"
                )
                st.json(result)
        st.markdown('</div>', unsafe_allow_html=True)

        # Export history
        exports = get_export_history(conn)
        if exports:
            st.markdown("**Export History**")
            import pandas as pd
            st.dataframe(pd.DataFrame(exports), use_container_width=True)

    # -- Tab 3: Retention Policy -----------------------------------------------
    with tabs[3]:
        st.subheader("Data Retention Policies")
        col_r1, col_r2 = st.columns([1, 2])
        with col_r1:
            st.markdown('<div class="gdpr-card">', unsafe_allow_html=True)
            ret_table = st.selectbox(
                "Table", CONTACT_TABLES, key="ret_table"
            )
            ret_days = st.number_input(
                "Retention (days)", min_value=1, max_value=3650,
                value=DEFAULT_RETENTION_DAYS, key="ret_days",
            )
            if st.button("💾 Set Policy", key="btn_retpol"):
                set_retention_policy(conn, ret_table, ret_days)
                st.success(f"Policy set: {ret_table} → {ret_days} days")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="gdpr-card">', unsafe_allow_html=True)
            if st.button("🧹 Enforce All Policies Now", key="btn_enforce"):
                result = enforce_retention(conn)
                st.success(f"Purged {result['total_purged']} old rows")
                st.json(result)
            st.markdown('</div>', unsafe_allow_html=True)

        with col_r2:
            policies = get_retention_policies(conn)
            if policies:
                import pandas as pd
                df = pd.DataFrame(policies)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No retention policies configured yet.")

    # -- Tab 4: Audit Log ----------------------------------------------------
    with tabs[4]:
        st.subheader("Audit Trail")
        al1, al2, al3 = st.columns(3)
        with al1:
            audit_cid = st.text_input(
                "Filter by Contact ID", key="audit_cid"
            )
        with al2:
            audit_action = st.selectbox(
                "Filter by Action",
                ["", "consent_recorded", "right_to_forget",
                 "right_to_forget_dryrun", "retention_policy_set",
                 "retention_enforced", "data_exported"],
                key="audit_action",
            )
        with al3:
            audit_limit = st.number_input(
                "Rows", min_value=10, max_value=500,
                value=50, key="audit_limit",
            )

        logs = get_audit_log(
            conn, limit=audit_limit,
            contact_id=audit_cid.strip() or None,
            action_filter=audit_action or None,
        )
        if logs:
            import pandas as pd
            df = pd.DataFrame(logs)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No audit entries match the filters.")

    # -- Tab 5: Integrity Check -----------------------------------------------
    with tabs[5]:
        st.subheader("Audit Log Integrity Verification")
        st.markdown('<div class="gdpr-card">', unsafe_allow_html=True)
        if st.button("🔐 Verify Checksums", key="btn_verify"):
            result = verify_audit_integrity(conn)
            if not result["tampered_ids"]:
                st.markdown(
                    f'<span class="gdpr-badge-ok">ALL {result["valid"]} '
                    f'entries verified ✓</span>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<span class="gdpr-badge-err">'
                    f'{len(result["tampered_ids"])} TAMPERED entries '
                    f'detected!</span>',
                    unsafe_allow_html=True,
                )
                st.json(result["tampered_ids"])
        st.markdown('</div>', unsafe_allow_html=True)

    conn.close()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _self_test():
    """Comprehensive self-test for all GDPR functions."""
    import tempfile

    print("=" * 60)
    print("GDPR Compliance Module — Self-Test")
    print("=" * 60)

    # Use temp DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    test_db = tmp.name

    try:
        conn = _get_conn(test_db)

        # Create dummy contact tables for testing
        for tbl in CONTACT_TABLES:
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {tbl} (
                    id TEXT PRIMARY KEY,
                    contact_id TEXT,
                    data TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )"""
            )
        conn.commit()

        test_contact = "test-contact-001"

        # Insert test data into a few tables
        for tbl in CONTACT_TABLES[:5]:
            for i in range(3):
                conn.execute(
                    f"INSERT INTO {tbl} (id, contact_id, data) VALUES (?,?,?)",
                    (f"{tbl}-{i}", test_contact, f"test data {i}"),
                )
        conn.commit()

        # 1. Consent tests
        print("\n[1/7] Consent — Grant ...")
        cid = record_consent(conn, test_contact, "birthday_wish", True)
        assert cid, "Failed to record consent"
        assert check_consent(conn, test_contact, "birthday_wish")
        print("      ✅ Consent granted and verified")

        print("[2/7] Consent — Revoke ...")
        record_consent(conn, test_contact, "birthday_wish", False)
        assert not check_consent(conn, test_contact, "birthday_wish")
        print("      ✅ Consent revoked and verified")

        print("[3/7] Consent — History ...")
        history = get_consent_history(conn, test_contact)
        assert len(history) >= 1
        print(f"      ✅ {len(history)} history record(s)")

        # 2. Right to forget dry run
        print("[4/7] Right-to-Forget — Dry run ...")
        dr = right_to_forget(conn, test_contact, dry_run=True)
        assert dr["dry_run"] is True
        assert dr["total_deleted"] > 0
        print(f"      ✅ Would delete {dr['total_deleted']} rows")

        # 3. Data export
        print("[5/7] Data Export ...")
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = export_contact_data(conn, test_contact,
                                      output_dir=tmpdir)
            assert exp["status"] == "completed"
            assert os.path.exists(exp["file_path"])
            with open(exp["file_path"]) as f:
                data = json.load(f)
            assert data["contact_id"] == test_contact
            print(f"      ✅ Exported {exp['record_count']} records "
                  f"→ {exp['file_path']}")

        # 4. Right to forget (real)
        # Re-grant consent so there's something to delete
        record_consent(conn, test_contact, "birthday_wish", True)
        print("[6/7] Right-to-Forget — Execute ...")
        result = right_to_forget(conn, test_contact)
        assert result["dry_run"] is False
        assert result["total_deleted"] > 0
        # Verify data is gone
        for tbl in CONTACT_TABLES[:5]:
            cnt = conn.execute(
                f"SELECT COUNT(*) as cnt FROM {tbl} "
                f"WHERE contact_id=?",
                (test_contact,),
            ).fetchone()["cnt"]
            assert cnt == 0, f"Table {tbl} still has data!"
        print(f"      ✅ Erased {result['total_deleted']} rows across "
              f"{len(result['tables'])} tables")

        # 5. Retention policy
        print("[7/7] Retention Policy ...")
        set_retention_policy(conn, "wish_outcome_log", 30)
        pols = get_retention_policies(conn)
        assert len(pols) >= 1
        er = enforce_retention(conn)
        print(f"      ✅ Policy set, enforcement purged "
              f"{er['total_purged']} rows")

        # 6. Audit integrity
        integrity = verify_audit_integrity(conn)
        assert len(integrity["tampered_ids"]) == 0
        print(f"\n[Bonus] Audit integrity: {integrity['valid']}/"
              f"{integrity['total']} entries verified ✓")

        # Stats
        stats = get_gdpr_stats(conn)
        print(f"\n📊 Stats: {json.dumps(stats, indent=2)}")

        conn.close()
        print("\n" + "=" * 60)
        print("✅ ALL GDPR SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(test_db)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _self_test()
else:
    try:
        import streamlit  # noqa: F401
        render_dashboard()
    except ImportError:
        pass
