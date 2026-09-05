"""
PostgreSQL Migration -- Birthday Wishes Agent v9.0
Migrates all SQLite tables to PostgreSQL for production use.
Provides a unified DB client that switches between SQLite (dev)
and PostgreSQL (prod) based on DATABASE_URL env variable.

Usage:
  # Dev (SQLite -- default, no config needed)
  python agent.py

  # Prod (PostgreSQL)
  export DATABASE_URL=postgresql://user:pass@localhost:5432/birthday_agent
  python postgres_migration.py migrate   # one-time migration
  python agent.py                        # now uses PostgreSQL

Requires (prod only):
  pip install psycopg2-binary sqlalchemy

Integrates with: all v8/v9 modules via db.py drop-in replacement
"""

import sqlite3
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

SQLITE_PATH  = Path("agent_history.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")
IS_POSTGRES  = DATABASE_URL.startswith("postgresql")

# ── Tables to migrate (in dependency order) ───────────────────────────────────

TABLES_ORDER = [
    "wish_queue",
    "contact_tier",
    "tier_change_log",
    "interaction_signal",
    "contact_life_events",
    "event_action_log",
    "vip_contacts",
    "vip_wish_log",
    "reply_sentiment_log",
    "contact_sentiment_profile",
    "wish_score_history",
    "platform_roi_snapshot",
    "agent_error_log",
    "agent_pause_state",
    "anomaly_history",
    "session_task_log",
    "session_registry",
    "agent_learnings",
    "prompt_versions",
    "wish_outcome_log",
    "tuning_history",
    "consensus_log",
    "mutual_insights",
    "wish_mention_log",
    "graph_nodes",
    "graph_edges",
    "revenue_attributions",
    "revenue_contacts",
    "network_health_snapshots",
    "telegram_contacts",
    "telegram_message_log",
    "wa_message_log",
    "wa_templates",
    "wa_webhook_events",
    "asian_platform_contacts",
    "asian_message_log",
    "discord_members",
    "discord_message_log",
]

# SQLite → PostgreSQL type mapping
TYPE_MAP = {
    "INTEGER":  "BIGINT",
    "TEXT":     "TEXT",
    "REAL":     "DOUBLE PRECISION",
    "BLOB":     "BYTEA",
    "NUMERIC":  "NUMERIC",
    "BOOLEAN":  "BOOLEAN",
    "":         "TEXT",
}


# ── Unified DB client ─────────────────────────────────────────────────────────

class DBClient:
    """
    Drop-in replacement for sqlite3.connect() that transparently
    switches to PostgreSQL when DATABASE_URL is set.

    Usage (same as sqlite3):
        from postgres_migration import get_db
        conn = get_db()
        conn.execute("SELECT ...")
        conn.commit()
        conn.close()
    """

    def __init__(self):
        self._pg_pool = None

    def connect(self) -> Any:
        if IS_POSTGRES:
            return self._pg_connect()
        return sqlite3.connect(SQLITE_PATH)

    def _pg_connect(self):
        try:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False
            return _PGWrapper(conn)
        except ImportError:
            raise ImportError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            )


class _PGWrapper:
    """
    Thin wrapper around psycopg2 connection that mimics sqlite3 interface
    so existing module code works without modification.
    """
    def __init__(self, conn):
        self._conn   = conn
        self._cursor = None

    def execute(self, sql: str, params=()) -> "_PGWrapper":
        sql = _adapt_sql(sql)
        cur = self._conn.cursor()
        cur.execute(sql, params)
        self._cursor = cur
        return self

    def executemany(self, sql: str, seq):
        sql = _adapt_sql(sql)
        cur = self._conn.cursor()
        cur.executemany(sql, seq)
        self._cursor = cur
        return self

    def fetchone(self):
        if self._cursor:
            return self._cursor.fetchone()
        return None

    def fetchall(self):
        if self._cursor:
            return self._cursor.fetchall()
        return []

    @property
    def lastrowid(self):
        if self._cursor:
            return self._cursor.fetchone()[0] if self._cursor.rowcount else None
        return None

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.commit()
        self.close()


def _adapt_sql(sql: str) -> str:
    """Convert SQLite-style ? placeholders to PostgreSQL %s."""
    result = []
    in_str = False
    for ch in sql:
        if ch == "'" and not in_str:
            in_str = True
            result.append(ch)
        elif ch == "'" and in_str:
            in_str = False
            result.append(ch)
        elif ch == "?" and not in_str:
            result.append("%s")
        else:
            result.append(ch)
    # Also replace AUTOINCREMENT with SERIAL handled in schema creation
    out = "".join(result)
    out = out.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    out = out.replace("autoincrement", "")
    return out


# Singleton client
_client = DBClient()


def get_db():
    """Return a new DB connection (SQLite or PostgreSQL)."""
    return _client.connect()


# ── Schema introspection ──────────────────────────────────────────────────────

def get_sqlite_schema(table: str) -> Optional[str]:
    """Return CREATE TABLE SQL from SQLite."""
    if not SQLITE_PATH.exists():
        return None
    conn = sqlite3.connect(SQLITE_PATH)
    row  = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def sqlite_to_pg_ddl(sqlite_sql: str, table: str) -> str:
    """
    Convert SQLite CREATE TABLE statement to PostgreSQL DDL.
    Handles: AUTOINCREMENT → SERIAL, type mapping, constraint syntax.
    """
    # Replace AUTOINCREMENT
    sql = sqlite_sql.replace("AUTOINCREMENT", "")

    # Replace INTEGER PRIMARY KEY (SQLite rowid) with BIGSERIAL
    import re
    sql = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\b",
        "BIGSERIAL PRIMARY KEY",
        sql, flags=re.IGNORECASE
    )

    # Type replacements
    for sqlite_t, pg_t in TYPE_MAP.items():
        if sqlite_t:
            sql = re.sub(rf"\b{sqlite_t}\b", pg_t, sql, flags=re.IGNORECASE)

    # IF NOT EXISTS
    sql = re.sub(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
        f"CREATE TABLE IF NOT EXISTS ",
        sql, flags=re.IGNORECASE
    )

    # Remove SQLite-specific CHECK(id = 1) style constraints if needed
    return sql.strip()


# ── Migration ─────────────────────────────────────────────────────────────────

def migrate(verbose: bool = True) -> dict:
    """
    One-time migration: copy all SQLite tables to PostgreSQL.

    Steps:
      1. Read each table schema from SQLite
      2. Create equivalent table in PostgreSQL
      3. Copy all rows
      4. Log result

    Returns:
        { tables_migrated, rows_copied, errors }
    """
    if not IS_POSTGRES:
        print("[Migration] DATABASE_URL not set or not PostgreSQL.")
        print("  Set DATABASE_URL=postgresql://user:pass@host/db and retry.")
        return {"tables_migrated": 0, "rows_copied": 0, "errors": ["No DATABASE_URL"]}

    if not SQLITE_PATH.exists():
        print(f"[Migration] SQLite DB not found at {SQLITE_PATH}")
        return {"tables_migrated": 0, "rows_copied": 0, "errors": ["SQLite not found"]}

    try:
        import psycopg2
    except ImportError:
        return {"tables_migrated": 0, "rows_copied": 0,
                "errors": ["psycopg2 not installed: pip install psycopg2-binary"]}

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn     = psycopg2.connect(DATABASE_URL)
    pg_cur      = pg_conn.cursor()

    results = {"tables_migrated": 0, "rows_copied": 0, "errors": []}

    for table in TABLES_ORDER:
        # Check if table exists in SQLite
        schema = get_sqlite_schema(table)
        if not schema:
            continue

        try:
            # Create table in PostgreSQL
            pg_ddl = sqlite_to_pg_ddl(schema, table)
            pg_cur.execute(pg_ddl)
            pg_conn.commit()

            # Copy rows
            rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
            if rows:
                cols = [d[0] for d in sqlite_conn.execute(
                    f"SELECT * FROM {table} LIMIT 0"
                ).description]
                placeholders = ", ".join(["%s"] * len(cols))
                col_list     = ", ".join(cols)
                pg_cur.executemany(
                    f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
                    f" ON CONFLICT DO NOTHING",
                    [tuple(r) for r in rows]
                )
                pg_conn.commit()

            results["tables_migrated"] += 1
            results["rows_copied"]     += len(rows) if rows else 0
            if verbose:
                print(f"  ✅ {table:<40} {len(rows) if rows else 0} rows")

        except Exception as exc:
            pg_conn.rollback()
            results["errors"].append(f"{table}: {exc}")
            if verbose:
                print(f"  ❌ {table}: {exc}")

    sqlite_conn.close()
    pg_conn.close()

    if verbose:
        print(f"\n[Migration] Done: {results['tables_migrated']} tables, "
              f"{results['rows_copied']} rows, "
              f"{len(results['errors'])} errors")
    return results


def verify_migration() -> dict:
    """Compare row counts between SQLite and PostgreSQL."""
    if not IS_POSTGRES or not SQLITE_PATH.exists():
        return {"status": "skipped", "mismatches": []}

    try:
        import psycopg2
        sqlite_conn = sqlite3.connect(SQLITE_PATH)
        pg_conn     = psycopg2.connect(DATABASE_URL)
        pg_cur      = pg_conn.cursor()
        mismatches  = []

        for table in TABLES_ORDER:
            row = sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            ).fetchone()
            if not row:
                continue
            sqlite_count = sqlite_conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            try:
                pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
                pg_count = pg_cur.fetchone()[0]
                if sqlite_count != pg_count:
                    mismatches.append({
                        "table":    table,
                        "sqlite":   sqlite_count,
                        "postgres": pg_count,
                    })
            except Exception:
                mismatches.append({
                    "table": table, "sqlite": sqlite_count,
                    "postgres": "ERROR"
                })

        sqlite_conn.close()
        pg_conn.close()
        return {"status": "ok" if not mismatches else "mismatch",
                "mismatches": mismatches}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "mismatches": []}


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="PostgreSQL Migration", page_icon="🐘",
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
    .cc-badge{background:#336791;color:#fff;font-size:0.65rem;font-weight:700;
              padding:2px 8px;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;}
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);
                font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:var(--muted);margin:22px 0 10px;
                   display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .code-box{background:#010409;border:1px solid var(--border);border-radius:8px;
              padding:12px 14px;font-family:'JetBrains Mono',monospace;
              font-size:0.76rem;color:#7ee787;white-space:pre;}
    .stat{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .stat-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .stat-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:#336791;
        border-color:#336791;color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🐘</span>
      <h1>PostgreSQL Migration</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    db_url = os.getenv("DATABASE_URL", "")
    is_pg  = db_url.startswith("postgresql")

    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(f'<div class="stat"><div class="stat-val" style="color:'
                    f'{"#3fb950" if is_pg else "#d29922"}">'
                    f'{"PostgreSQL" if is_pg else "SQLite"}</div>'
                    f'<div class="stat-lbl">Active DB</div></div>',
                    unsafe_allow_html=True)
    with m2:
        sqlite_ok = SQLITE_PATH.exists()
        st.markdown(f'<div class="stat"><div class="stat-val" '
                    f'style="color:{"#3fb950" if sqlite_ok else "#f85149"}">'
                    f'{"Found" if sqlite_ok else "Missing"}</div>'
                    f'<div class="stat-lbl">SQLite File</div></div>',
                    unsafe_allow_html=True)
    with m3:
        st.markdown(f'<div class="stat"><div class="stat-val">'
                    f'{len(TABLES_ORDER)}</div>'
                    f'<div class="stat-lbl">Tables</div></div>',
                    unsafe_allow_html=True)

    if not is_pg:
        st.markdown("""
        <div style="background:#1a1500;border-left:4px solid #d29922;
                    border-radius:8px;padding:12px 16px;margin:16px 0;">
          <div style="color:#d29922;font-weight:700">DATABASE_URL not set</div>
          <div style="font-size:0.78rem;color:#c9d1d9;margin-top:4px">
            Set DATABASE_URL to enable migration.
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Setup</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="code-box">pip install psycopg2-binary

# .env
DATABASE_URL=postgresql://user:pass@localhost:5432/birthday_agent

# Run migration (one-time)
python postgres_migration.py migrate

# Verify
python postgres_migration.py verify</div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Migration</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🐘 Run Migration", type="primary",
                     use_container_width=True, disabled=not is_pg):
            with st.spinner("Migrating..."):
                result = migrate(verbose=False)
            if not result["errors"]:
                st.success(f"Done! {result['tables_migrated']} tables, "
                           f"{result['rows_copied']} rows")
            else:
                st.error(f"{len(result['errors'])} errors")
                for e in result["errors"][:5]:
                    st.code(e)
    with c2:
        if st.button("🔍 Verify", use_container_width=True, disabled=not is_pg):
            result = verify_migration()
            if result["status"] == "ok":
                st.success("Row counts match ✅")
            elif result["mismatches"]:
                st.warning(f"{len(result['mismatches'])} mismatches")
                for m in result["mismatches"][:5]:
                    st.code(json.dumps(m))
            else:
                st.error(result.get("error","Unknown error"))

    st.markdown('<div class="section-title">Tables to Migrate</div>',
                unsafe_allow_html=True)
    cols = st.columns(3)
    for i, t in enumerate(TABLES_ORDER):
        with cols[i % 3]:
            exists = bool(get_sqlite_schema(t))
            color  = "#3fb950" if exists else "#30363d"
            st.markdown(
                f'<div style="font-size:0.72rem;font-family:monospace;'
                f'color:{color};padding:2px 0">'
                f'{"✓" if exists else "○"} {t}</div>',
                unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>PostgreSQL Migration</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "migrate":
        print("=== PostgreSQL Migration ===\n")
        result = migrate(verbose=True)
        print(f"\nResult: {result}")

    elif cmd == "verify":
        print("=== Verifying Migration ===\n")
        result = verify_migration()
        print(f"Status: {result['status']}")
        if result.get("mismatches"):
            for m in result["mismatches"]:
                print(f"  MISMATCH: {m}")

    elif cmd == "status":
        print("=== DB Status ===")
        print(f"  Mode      : {'PostgreSQL' if IS_POSTGRES else 'SQLite (dev)'}")
        print(f"  SQLite    : {'found' if SQLITE_PATH.exists() else 'not found'}")
        print(f"  Tables    : {len(TABLES_ORDER)} defined")
        if SQLITE_PATH.exists():
            conn = sqlite3.connect(SQLITE_PATH)
            existing = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            conn.close()
            print(f"  In SQLite : {len(existing)} tables")
        print(f"\nUsage:")
        print(f"  python postgres_migration.py migrate  # copy SQLite → PostgreSQL")
        print(f"  python postgres_migration.py verify   # compare row counts")
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python postgres_migration.py [migrate|verify|status]")
else:
    render_dashboard()
