"""
Database Migration System — Birthday Wishes Agent v10.0
=========================================================
Lightweight, zero-dependency migration system for SQLite.
Tracks applied migrations, supports up/down rollback,
checksum verification, and a Streamlit status dashboard.

Usage:
  python db_migrations.py                # self-test
  python db_migrations.py status         # show migration status
  python db_migrations.py migrate        # apply pending migrations
  python db_migrations.py rollback 1     # rollback last N migrations

Integration:
  from db_migrations import migrate, status, rollback
  migrate()          # call on startup in production mode

Author : Fahim (SadManFahIm)
Branch : feature/db-migrations (→ 10.0)
"""

import sqlite3
import hashlib
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.getenv("BWA_DB_PATH", "agent_history.db"))

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Migration registry types
# ──────────────────────────────────────────────────────────────


class Migration:
    """A single versioned migration with up() and down()."""

    def __init__(self, version: str, name: str, up_sql: str,
                 down_sql: str):
        self.version = version
        self.name = name
        self.up_sql = up_sql
        self.down_sql = down_sql
        self.checksum = hashlib.sha256(up_sql.encode()).hexdigest()[:16]

    def __repr__(self):
        return f"Migration({self.version}: {self.name})"


# ──────────────────────────────────────────────────────────────
# Migration definitions (M001 – M006)
# ──────────────────────────────────────────────────────────────

MIGRATIONS: list[Migration] = []


# ── M001: Authentication ──────────────────────────────────────

MIGRATIONS.append(Migration(
    version="M001",
    name="auth_tables",
    up_sql="""
CREATE TABLE auth_users (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL DEFAULT '',
    role            TEXT NOT NULL DEFAULT 'viewer',
    is_active       INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    last_login_at   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_auth_username ON auth_users(username);

CREATE TABLE auth_refresh_tokens (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    token_hash      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    revoked         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES auth_users(id)
);
CREATE INDEX idx_refresh_user ON auth_refresh_tokens(user_id);
CREATE INDEX idx_refresh_hash ON auth_refresh_tokens(token_hash);

CREATE TABLE auth_token_blocklist (
    jti             TEXT PRIMARY KEY,
    blocked_at      TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at      TEXT NOT NULL
);
CREATE INDEX idx_blocklist_exp ON auth_token_blocklist(expires_at);

CREATE TABLE auth_password_resets (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    token_hash      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES auth_users(id)
);

CREATE TABLE auth_login_log (
    id              TEXT PRIMARY KEY,
    user_id         TEXT,
    username        TEXT NOT NULL,
    success         INTEGER NOT NULL,
    ip_hash         TEXT,
    user_agent      TEXT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_login_log_user ON auth_login_log(user_id);
CREATE INDEX idx_login_log_ts ON auth_login_log(timestamp);
""",
    down_sql="""
DROP TABLE IF EXISTS auth_login_log;
DROP TABLE IF EXISTS auth_password_resets;
DROP TABLE IF EXISTS auth_token_blocklist;
DROP TABLE IF EXISTS auth_refresh_tokens;
DROP TABLE IF EXISTS auth_users;
""",
))


# ── M002: GDPR Compliance ────────────────────────────────────

MIGRATIONS.append(Migration(
    version="M002",
    name="gdpr_tables",
    up_sql="""
CREATE TABLE gdpr_consent (
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
CREATE INDEX idx_consent_contact ON gdpr_consent(contact_id);
CREATE INDEX idx_consent_type ON gdpr_consent(contact_id, consent_type);

CREATE TABLE gdpr_audit_log (
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
CREATE INDEX idx_audit_timestamp ON gdpr_audit_log(timestamp);
CREATE INDEX idx_audit_contact ON gdpr_audit_log(contact_id);
CREATE INDEX idx_audit_action ON gdpr_audit_log(action);

CREATE TABLE gdpr_retention_policy (
    id              TEXT PRIMARY KEY,
    table_name      TEXT NOT NULL,
    retention_days  INTEGER NOT NULL DEFAULT 365,
    enabled         INTEGER NOT NULL DEFAULT 1,
    last_purge_at   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_retention_table ON gdpr_retention_policy(table_name);

CREATE TABLE gdpr_data_export_log (
    id              TEXT PRIMARY KEY,
    contact_id      TEXT NOT NULL,
    requested_at    TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT,
    file_path       TEXT,
    file_hash       TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    actor           TEXT DEFAULT 'system'
);
CREATE INDEX idx_export_contact ON gdpr_data_export_log(contact_id);
""",
    down_sql="""
DROP TABLE IF EXISTS gdpr_data_export_log;
DROP TABLE IF EXISTS gdpr_retention_policy;
DROP TABLE IF EXISTS gdpr_audit_log;
DROP TABLE IF EXISTS gdpr_consent;
""",
))


# ── M003: Audit Trail ────────────────────────────────────────

MIGRATIONS.append(Migration(
    version="M003",
    name="audit_trail_tables",
    up_sql="""
CREATE TABLE audit_trail (
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
    before_snapshot TEXT,
    after_snapshot  TEXT,
    metadata        TEXT,
    prev_hash       TEXT,
    row_hash        TEXT NOT NULL
);
CREATE INDEX idx_at_timestamp ON audit_trail(timestamp);
CREATE INDEX idx_at_action ON audit_trail(action);
CREATE INDEX idx_at_category ON audit_trail(category);
CREATE INDEX idx_at_actor ON audit_trail(actor);
CREATE INDEX idx_at_contact ON audit_trail(contact_id);
CREATE INDEX idx_at_entity ON audit_trail(entity_type, entity_id);
CREATE INDEX idx_at_severity ON audit_trail(severity);
CREATE INDEX idx_at_session ON audit_trail(session_id);
CREATE INDEX idx_at_module ON audit_trail(module);

CREATE TABLE audit_chain_state (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    last_hash   TEXT NOT NULL,
    entry_count INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL
);

CREATE TABLE audit_archive (
    id              TEXT PRIMARY KEY,
    archived_at     TEXT NOT NULL,
    original_ts     TEXT NOT NULL,
    action          TEXT NOT NULL,
    summary         TEXT NOT NULL,
    actor           TEXT,
    contact_id      TEXT,
    row_hash        TEXT
);
CREATE INDEX idx_aa_original_ts ON audit_archive(original_ts);
""",
    down_sql="""
DROP TABLE IF EXISTS audit_archive;
DROP TABLE IF EXISTS audit_chain_state;
DROP TABLE IF EXISTS audit_trail;
""",
))


# ── M004: Push Notifications ─────────────────────────────────

MIGRATIONS.append(Migration(
    version="M004",
    name="push_notification_tables",
    up_sql="""
CREATE TABLE push_devices (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    fcm_token       TEXT NOT NULL,
    device_name     TEXT DEFAULT '',
    platform        TEXT DEFAULT 'android',
    app_version     TEXT DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1,
    quiet_start     TEXT DEFAULT '23:00',
    quiet_end       TEXT DEFAULT '07:00',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_push_dev_user ON push_devices(user_id);
CREATE UNIQUE INDEX idx_push_dev_token ON push_devices(fcm_token);

CREATE TABLE push_topic_subs (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    device_id       TEXT NOT NULL,
    topic           TEXT NOT NULL,
    subscribed_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_push_topic_key ON push_topic_subs(device_id, topic);
CREATE INDEX idx_push_topic_user ON push_topic_subs(user_id);

CREATE TABLE push_notification_log (
    id              TEXT PRIMARY KEY,
    user_id         TEXT,
    device_id       TEXT,
    category        TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    data_payload    TEXT,
    priority        TEXT NOT NULL DEFAULT 'normal',
    topic           TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    fcm_message_id  TEXT,
    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    sent_at         TEXT,
    delivered_at    TEXT,
    opened_at       TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_push_log_user ON push_notification_log(user_id);
CREATE INDEX idx_push_log_status ON push_notification_log(status);
CREATE INDEX idx_push_log_cat ON push_notification_log(category);
CREATE INDEX idx_push_log_ts ON push_notification_log(created_at);

CREATE TABLE push_preferences (
    user_id         TEXT PRIMARY KEY,
    enabled         INTEGER NOT NULL DEFAULT 1,
    categories      TEXT DEFAULT '{}',
    quiet_hours     INTEGER NOT NULL DEFAULT 1,
    quiet_start     TEXT DEFAULT '23:00',
    quiet_end       TEXT DEFAULT '07:00',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
""",
    down_sql="""
DROP TABLE IF EXISTS push_preferences;
DROP TABLE IF EXISTS push_notification_log;
DROP TABLE IF EXISTS push_topic_subs;
DROP TABLE IF EXISTS push_devices;
""",
))


# ── M005: Rate Limiting ──────────────────────────────────────

MIGRATIONS.append(Migration(
    version="M005",
    name="rate_limit_tables",
    up_sql="""
CREATE TABLE rl_platform_quotas (
    platform        TEXT PRIMARY KEY,
    daily_limit     INTEGER NOT NULL,
    hourly_limit    INTEGER NOT NULL,
    per_minute_limit INTEGER NOT NULL,
    cooldown_days   INTEGER NOT NULL DEFAULT 30,
    is_enabled      INTEGER NOT NULL DEFAULT 1,
    auto_pause      INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE rl_consumption_log (
    id              TEXT PRIMARY KEY,
    platform        TEXT NOT NULL,
    contact_id      TEXT,
    action_type     TEXT NOT NULL DEFAULT 'send',
    timestamp       TEXT NOT NULL,
    window_day      TEXT NOT NULL,
    window_hour     TEXT NOT NULL
);
CREATE INDEX idx_rl_cons_platform ON rl_consumption_log(platform);
CREATE INDEX idx_rl_cons_day ON rl_consumption_log(platform, window_day);
CREATE INDEX idx_rl_cons_hour ON rl_consumption_log(platform, window_hour);
CREATE INDEX idx_rl_cons_ts ON rl_consumption_log(timestamp);
CREATE INDEX idx_rl_cons_contact ON rl_consumption_log(platform, contact_id);

CREATE TABLE rl_throttle_events (
    id              TEXT PRIMARY KEY,
    platform        TEXT NOT NULL,
    limit_type      TEXT NOT NULL,
    limit_value     INTEGER NOT NULL,
    current_count   INTEGER NOT NULL,
    contact_id      TEXT,
    action_taken    TEXT NOT NULL DEFAULT 'blocked',
    timestamp       TEXT NOT NULL
);
CREATE INDEX idx_rl_throttle_platform ON rl_throttle_events(platform);
CREATE INDEX idx_rl_throttle_ts ON rl_throttle_events(timestamp);

CREATE TABLE rl_cooldown_tracker (
    id              TEXT PRIMARY KEY,
    platform        TEXT NOT NULL,
    contact_id      TEXT NOT NULL,
    last_contact_at TEXT NOT NULL,
    cooldown_until  TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_rl_cooldown_key ON rl_cooldown_tracker(platform, contact_id);
""",
    down_sql="""
DROP TABLE IF EXISTS rl_cooldown_tracker;
DROP TABLE IF EXISTS rl_throttle_events;
DROP TABLE IF EXISTS rl_consumption_log;
DROP TABLE IF EXISTS rl_platform_quotas;
""",
))


# ── M006: Morning Briefing ───────────────────────────────────

MIGRATIONS.append(Migration(
    version="M006",
    name="briefing_tables",
    up_sql="""
CREATE TABLE briefing_log (
    id              TEXT PRIMARY KEY,
    briefing_date   TEXT NOT NULL,
    generated_at    TEXT NOT NULL,
    delivered_at    TEXT,
    delivery_method TEXT DEFAULT 'dashboard',
    birthdays_today INTEGER NOT NULL DEFAULT 0,
    birthdays_week  INTEGER NOT NULL DEFAULT 0,
    pending_tasks   INTEGER NOT NULL DEFAULT 0,
    alerts_count    INTEGER NOT NULL DEFAULT 0,
    payload         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'generated'
);
CREATE UNIQUE INDEX idx_brief_date ON briefing_log(briefing_date);

CREATE TABLE briefing_preferences (
    user_id         TEXT PRIMARY KEY,
    enabled         INTEGER NOT NULL DEFAULT 1,
    delivery_hour   INTEGER NOT NULL DEFAULT 7,
    skip_weekends   INTEGER NOT NULL DEFAULT 0,
    include_upcoming INTEGER NOT NULL DEFAULT 1,
    include_tasks   INTEGER NOT NULL DEFAULT 1,
    include_agent   INTEGER NOT NULL DEFAULT 1,
    include_rates   INTEGER NOT NULL DEFAULT 1,
    push_enabled    INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
""",
    down_sql="""
DROP TABLE IF EXISTS briefing_preferences;
DROP TABLE IF EXISTS briefing_log;
""",
))


# ──────────────────────────────────────────────────────────────
# Schema bootstrap (migration tracker table)
# ──────────────────────────────────────────────────────────────


def _init_migration_table(conn: sqlite3.Connection) -> None:
    """Create the migration tracker table."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            version     TEXT NOT NULL UNIQUE,
            name        TEXT NOT NULL,
            checksum    TEXT NOT NULL,
            applied_at  TEXT NOT NULL
        )
    """)
    conn.commit()


def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_migration_table(conn)
    return conn


# ──────────────────────────────────────────────────────────────
# Core operations
# ──────────────────────────────────────────────────────────────


def get_applied(db_path: Path = DB_PATH) -> list[dict]:
    """Return list of applied migrations."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM _migrations ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def status(db_path: Path = DB_PATH) -> dict:
    """Show which migrations are applied vs pending."""
    applied = get_applied(db_path)
    applied_versions = {m["version"] for m in applied}

    pending = [m for m in MIGRATIONS if m.version not in applied_versions]
    applied_list = []
    for m in applied:
        reg = next((r for r in MIGRATIONS if r.version == m["version"]),
                   None)
        checksum_ok = reg.checksum == m["checksum"] if reg else False
        applied_list.append({
            "version": m["version"],
            "name": m["name"],
            "applied_at": m["applied_at"],
            "checksum_ok": checksum_ok,
        })

    return {
        "applied": applied_list,
        "pending": [{"version": m.version, "name": m.name}
                    for m in pending],
        "total_registered": len(MIGRATIONS),
        "total_applied": len(applied),
        "total_pending": len(pending),
        "is_current": len(pending) == 0,
    }


def migrate(db_path: Path = DB_PATH, dry_run: bool = False) -> dict:
    """Apply all pending migrations in order."""
    applied = get_applied(db_path)
    applied_versions = {m["version"] for m in applied}
    pending = [m for m in MIGRATIONS if m.version not in applied_versions]

    if not pending:
        logger.info("No pending migrations.")
        return {"applied": 0, "migrations": []}

    conn = _get_conn(db_path)
    results = []
    try:
        for m in pending:
            if dry_run:
                results.append({"version": m.version, "name": m.name,
                                "status": "would_apply"})
                continue

            try:
                conn.executescript(m.up_sql)
                conn.execute(
                    """INSERT INTO _migrations
                       (version, name, checksum, applied_at)
                       VALUES (?,?,?,?)""",
                    (m.version, m.name, m.checksum,
                     datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                results.append({"version": m.version, "name": m.name,
                                "status": "applied"})
                logger.info("Applied: %s (%s)", m.version, m.name)
            except Exception as exc:
                results.append({"version": m.version, "name": m.name,
                                "status": "failed", "error": str(exc)})
                logger.error("Failed: %s — %s", m.version, exc)
                break  # Stop on first failure
    finally:
        conn.close()

    return {"applied": sum(1 for r in results if r["status"] == "applied"),
            "dry_run": dry_run, "migrations": results}


def rollback(n: int = 1, db_path: Path = DB_PATH) -> dict:
    """Rollback the last N applied migrations (in reverse order)."""
    applied = get_applied(db_path)
    if not applied:
        return {"rolled_back": 0, "migrations": []}

    to_rollback = applied[-n:]
    to_rollback.reverse()

    conn = _get_conn(db_path)
    results = []
    try:
        for m_record in to_rollback:
            reg = next((r for r in MIGRATIONS
                        if r.version == m_record["version"]), None)
            if not reg:
                results.append({"version": m_record["version"],
                                "status": "skipped",
                                "reason": "no_registered_migration"})
                continue

            try:
                conn.executescript(reg.down_sql)
                conn.execute(
                    "DELETE FROM _migrations WHERE version=?",
                    (m_record["version"],),
                )
                conn.commit()
                results.append({"version": reg.version, "name": reg.name,
                                "status": "rolled_back"})
                logger.info("Rolled back: %s (%s)", reg.version, reg.name)
            except Exception as exc:
                results.append({"version": reg.version,
                                "status": "failed", "error": str(exc)})
                logger.error("Rollback failed: %s — %s", reg.version, exc)
                break
    finally:
        conn.close()

    return {"rolled_back": sum(1 for r in results
                               if r["status"] == "rolled_back"),
            "migrations": results}


def verify_checksums(db_path: Path = DB_PATH) -> dict:
    """Verify that applied migration checksums match the registry."""
    applied = get_applied(db_path)
    mismatched = []
    for m in applied:
        reg = next((r for r in MIGRATIONS
                    if r.version == m["version"]), None)
        if reg and reg.checksum != m["checksum"]:
            mismatched.append({
                "version": m["version"],
                "expected": reg.checksum,
                "actual": m["checksum"],
            })
    return {"total_checked": len(applied),
            "mismatched": mismatched,
            "is_valid": len(mismatched) == 0}


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """Migration status dashboard."""
    try:
        import streamlit as st
        import pandas as pd
    except ImportError:
        return

    st.set_page_config(page_title="DB Migrations", page_icon="🗄",
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
        border:1px solid var(--border);color:var(--text);border-radius:8px;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);
        border-color:var(--accent);color:#fff;}
    .mig-applied{border-left:3px solid var(--green);padding-left:12px;margin:6px 0;}
    .mig-pending{border-left:3px solid var(--yellow);padding-left:12px;margin:6px 0;}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🗄</span>
      <h1>Database Migrations</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    s = status()

    # KPIs
    st.markdown('<div class="section-title">Overview</div>',
                unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    for col, val, lbl in [
        (k1, s["total_registered"], "Registered"),
        (k2, s["total_applied"], "Applied"),
        (k3, s["total_pending"], "Pending"),
        (k4, "✅" if s["is_current"] else "⚠️", "Status"),
    ]:
        col.markdown(
            f'<div class="mini"><div class="mini-val">{val}</div>'
            f'<div class="mini-lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

    tabs = st.tabs(["📋 Status", "▶️ Migrate", "⏪ Rollback",
                     "🔐 Verify"])

    # Status tab
    with tabs[0]:
        st.markdown('<div class="section-title">Applied</div>',
                    unsafe_allow_html=True)
        for m in s["applied"]:
            chk = "✅" if m["checksum_ok"] else "❌"
            st.markdown(
                f'<div class="mig-applied">'
                f'<strong>{m["version"]}</strong> · {m["name"]} '
                f'<span style="color:var(--muted);font-size:0.75rem">'
                f'{m["applied_at"][:19]}</span> {chk}</div>',
                unsafe_allow_html=True)

        if s["pending"]:
            st.markdown('<div class="section-title">Pending</div>',
                        unsafe_allow_html=True)
            for m in s["pending"]:
                st.markdown(
                    f'<div class="mig-pending">'
                    f'<strong>{m["version"]}</strong> · {m["name"]}'
                    f'</div>', unsafe_allow_html=True)

    # Migrate tab
    with tabs[1]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        if s["is_current"]:
            st.success("Database is up to date — no pending migrations.")
        else:
            st.warning(f"{s['total_pending']} migration(s) pending.")
            mc1, mc2 = st.columns(2)
            with mc1:
                if st.button("🔍 Dry Run", key="btn_dry"):
                    result = migrate(dry_run=True)
                    st.json(result)
            with mc2:
                if st.button("▶️ Apply All", key="btn_apply",
                             type="primary"):
                    result = migrate()
                    if result["applied"] > 0:
                        st.success(
                            f"Applied {result['applied']} migration(s)")
                    st.json(result)
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # Rollback tab
    with tabs[2]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        rb_n = st.number_input("Rollback last N migrations",
                               1, len(MIGRATIONS), 1, key="rb_n")
        if st.button("⏪ Rollback", key="btn_rb"):
            result = rollback(rb_n)
            st.json(result)
            if result["rolled_back"] > 0:
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # Verify tab
    with tabs[3]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        if st.button("🔐 Verify Checksums", key="btn_verify"):
            result = verify_checksums()
            if result["is_valid"]:
                st.success(f"All {result['total_checked']} checksums valid")
            else:
                st.error(f"{len(result['mismatched'])} mismatched")
                st.json(result["mismatched"])
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/db-migrations</code> · DB Migrations v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test."""
    import tempfile

    print("=" * 60)
    print("Database Migration System — Self-Test")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    try:
        # 1. Registry
        print(f"\n[1/8] Migration registry ...")
        assert len(MIGRATIONS) == 6
        versions = [m.version for m in MIGRATIONS]
        assert versions == ["M001", "M002", "M003", "M004", "M005", "M006"]
        print(f"      ✅ 6 migrations registered (M001–M006)")

        # 2. Status before migration
        print("[2/8] Initial status ...")
        s = status(tdb)
        assert s["total_applied"] == 0
        assert s["total_pending"] == 6
        assert not s["is_current"]
        print(f"      ✅ 0 applied, 6 pending")

        # 3. Dry run
        print("[3/8] Dry run ...")
        result = migrate(tdb, dry_run=True)
        assert result["applied"] == 0
        assert len(result["migrations"]) == 6
        assert all(r["status"] == "would_apply" for r in result["migrations"])
        s = status(tdb)
        assert s["total_applied"] == 0  # nothing changed
        print(f"      ✅ Dry run previewed 6 migrations, nothing applied")

        # 4. Apply all
        print("[4/8] Apply all migrations ...")
        result = migrate(tdb)
        assert result["applied"] == 6
        s = status(tdb)
        assert s["total_applied"] == 6
        assert s["total_pending"] == 0
        assert s["is_current"]
        print(f"      ✅ All 6 applied, DB is current")

        # 5. Verify tables exist
        print("[5/8] Verify tables ...")
        conn = sqlite3.connect(tdb)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]
        expected = [
            "auth_users", "auth_refresh_tokens", "auth_login_log",
            "gdpr_consent", "gdpr_audit_log",
            "audit_trail", "audit_chain_state",
            "push_devices", "push_notification_log",
            "rl_platform_quotas", "rl_consumption_log",
            "briefing_log", "briefing_preferences",
        ]
        for tbl in expected:
            assert tbl in table_names, f"Missing table: {tbl}"
        conn.close()
        print(f"      ✅ All {len(expected)} key tables verified")

        # 6. Idempotency (re-run migrate)
        print("[6/8] Idempotency ...")
        result = migrate(tdb)
        assert result["applied"] == 0
        print(f"      ✅ Re-run applied 0 (idempotent)")

        # 7. Rollback
        print("[7/8] Rollback last 2 ...")
        result = rollback(2, tdb)
        assert result["rolled_back"] == 2
        s = status(tdb)
        assert s["total_applied"] == 4
        assert s["total_pending"] == 2
        # Verify rolled-back tables are gone
        conn = sqlite3.connect(tdb)
        remaining = [t[0] for t in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "briefing_log" not in remaining
        assert "rl_platform_quotas" not in remaining
        assert "audit_trail" in remaining  # M003 still applied
        conn.close()
        print(f"      ✅ Rolled back M006+M005, 4 applied, 2 pending")

        # Re-apply
        result = migrate(tdb)
        assert result["applied"] == 2
        print(f"      ✅ Re-applied 2 after rollback")

        # 8. Checksum verification
        print("[8/8] Checksum verify ...")
        v = verify_checksums(tdb)
        assert v["is_valid"]
        assert v["total_checked"] == 6
        print(f"      ✅ All 6 checksums valid")

        print("\n" + "=" * 60)
        print("✅ ALL DB MIGRATION SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(tdb)


# ──────────────────────────────────────────────────────────────
# CLI + entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            import json
            print(json.dumps(status(), indent=2))
        elif cmd == "migrate":
            result = migrate()
            print(f"Applied {result['applied']} migration(s)")
            for m in result["migrations"]:
                print(f"  {m['version']}: {m['status']}")
        elif cmd == "rollback":
            n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            result = rollback(n)
            print(f"Rolled back {result['rolled_back']} migration(s)")
        elif cmd == "verify":
            import json
            print(json.dumps(verify_checksums(), indent=2))
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python db_migrations.py [status|migrate|rollback N|verify]")
    else:
        print("=== DB Migrations -- self test ===\n")
        _self_test()
else:
    render_dashboard()
