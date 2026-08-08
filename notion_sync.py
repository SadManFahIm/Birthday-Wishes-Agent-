"""
Notion Database Sync -- Birthday Wishes Agent v10.0
Syncs contacts and interaction history to a Notion database,
so the user can browse, filter, and edit relationship data
inside Notion alongside their other workspaces.

What gets synced:
  - Contacts (name, tier, platform, birthday, VIP status, tier score)
  - Interaction log (wish sent, reply received, sentiment, revenue)

Sync direction: one-way (Agent DB → Notion). Notion is a read/browse
layer; edits in Notion are not pulled back (avoids conflict resolution).

Auth: Notion internal integration token (NOTION_API_KEY).
      Create at https://www.notion.so/my-integrations

Requires:
  pip install notion-client

Integrates with: contacts/relationship_tiering.py,
                 contacts/vip_contact_flagging.py,
                 dashboards/revenue_attribution.py, agent.py
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

NOTION_API_KEY       = os.getenv("NOTION_API_KEY", "")
NOTION_CONTACTS_DB_ID = os.getenv("NOTION_CONTACTS_DB_ID", "")
NOTION_LOG_DB_ID      = os.getenv("NOTION_LOG_DB_ID", "")

TIER_COLORS = {
    "Close Friend": "green",
    "Colleague":    "blue",
    "Acquaintance": "gray",
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_notion_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notion_sync_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            sync_type       TEXT NOT NULL,
            notion_page_id  TEXT,
            synced          INTEGER NOT NULL DEFAULT 0,
            error_msg       TEXT,
            synced_at       TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notion_sync_state (
            id              INTEGER PRIMARY KEY CHECK (id = 1),
            contacts_db_id  TEXT,
            log_db_id       TEXT,
            last_full_sync  TEXT,
            contacts_synced INTEGER NOT NULL DEFAULT 0,
            logs_synced     INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table):
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone())


def _safe(module: str, attr: str):
    try:
        mod = __import__(module, fromlist=[attr])
        return getattr(mod, attr, None)
    except ImportError:
        return None


# ── Notion client ──────────────────────────────────────────────────────────────

def _get_notion_client():
    """Return an authenticated Notion client, or None if not configured."""
    if not NOTION_API_KEY:
        return None
    try:
        from notion_client import Client
        return Client(auth=NOTION_API_KEY)
    except ImportError:
        print("[Notion] notion-client not installed: pip install notion-client")
        return None
    except Exception as exc:
        print(f"[Notion] Client init failed: {exc}")
        return None


def create_contacts_database(parent_page_id: str) -> Optional[str]:
    """
    Create the Contacts database in Notion under a parent page.
    Returns the new database ID, or None on failure.
    Only needs to run once — save the returned ID as NOTION_CONTACTS_DB_ID.
    """
    client = _get_notion_client()
    if not client:
        return None
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": "Birthday Agent — Contacts"}}],
            properties={
                "Name":         {"title": {}},
                "Tier":         {"select": {"options": [
                    {"name": "Close Friend", "color": "green"},
                    {"name": "Colleague",    "color": "blue"},
                    {"name": "Acquaintance", "color": "gray"},
                ]}},
                "Platform":     {"select": {"options": [
                    {"name": p, "color": "default"} for p in
                    ["LinkedIn","WhatsApp","Telegram","Discord","Slack","Facebook"]
                ]}},
                "Birthday":     {"rich_text": {}},
                "Tier Score":   {"number": {"format": "number"}},
                "VIP":          {"checkbox": {}},
                "Last Synced":  {"date": {}},
                "Contact ID":   {"rich_text": {}},
            },
        )
        print(f"[Notion] Contacts DB created: {db['id']}")
        return db["id"]
    except Exception as exc:
        print(f"[Notion] DB create failed: {exc}")
        return None


def create_interaction_log_database(parent_page_id: str) -> Optional[str]:
    """Create the Interaction Log database in Notion."""
    client = _get_notion_client()
    if not client:
        return None
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": "Birthday Agent — Interaction Log"}}],
            properties={
                "Contact":      {"title": {}},
                "Platform":     {"select": {"options": [
                    {"name": p, "color": "default"} for p in
                    ["LinkedIn","WhatsApp","Telegram","Discord","Slack"]
                ]}},
                "Wish Sent":    {"date": {}},
                "Replied":      {"checkbox": {}},
                "Sentiment":    {"number": {"format": "number"}},
                "Revenue USD":  {"number": {"format": "dollar"}},
                "Contact ID":   {"rich_text": {}},
            },
        )
        print(f"[Notion] Interaction Log DB created: {db['id']}")
        return db["id"]
    except Exception as exc:
        print(f"[Notion] DB create failed: {exc}")
        return None


# ── Contact sync ───────────────────────────────────────────────────────────────

def _find_existing_page(client, db_id: str, contact_id: str) -> Optional[str]:
    """Search a Notion database for an existing page by Contact ID."""
    try:
        result = client.databases.query(
            database_id=db_id,
            filter={"property": "Contact ID",
                   "rich_text": {"equals": contact_id}},
        )
        pages = result.get("results", [])
        return pages[0]["id"] if pages else None
    except Exception:
        return None


def sync_contact(
    contact_id:   str,
    contact_name: str,
    tier:         str = "Acquaintance",
    tier_score:   float = 5.0,
    platform:     str = "LinkedIn",
    birthday:     str = "",
    is_vip:       bool = False,
    dry_run:      bool = True,
) -> dict:
    """
    Sync one contact to the Notion Contacts database.
    Creates a new page if not found, updates if it exists.

    Returns:
        { success, page_id, dry_run, error }
    """
    init_notion_tables()

    if dry_run:
        result = {"success": True, "page_id": "dry_run_mock", "dry_run": True, "error": ""}
        _log_sync(contact_id, contact_name, "contact", result["page_id"], True, "")
        return result

    client = _get_notion_client()
    if not client or not NOTION_CONTACTS_DB_ID:
        error = "Notion not configured (set NOTION_API_KEY and NOTION_CONTACTS_DB_ID)"
        _log_sync(contact_id, contact_name, "contact", None, False, error)
        return {"success": False, "page_id": None, "dry_run": False, "error": error}

    properties = {
        "Name":        {"title": [{"text": {"content": contact_name}}]},
        "Tier":        {"select": {"name": tier}},
        "Platform":    {"select": {"name": platform}},
        "Birthday":    {"rich_text": [{"text": {"content": birthday}}]},
        "Tier Score":  {"number": tier_score},
        "VIP":         {"checkbox": is_vip},
        "Last Synced": {"date": {"start": datetime.now().isoformat()}},
        "Contact ID":  {"rich_text": [{"text": {"content": contact_id}}]},
    }

    try:
        existing = _find_existing_page(client, NOTION_CONTACTS_DB_ID, contact_id)
        if existing:
            page = client.pages.update(page_id=existing, properties=properties)
        else:
            page = client.pages.create(
                parent={"database_id": NOTION_CONTACTS_DB_ID},
                properties=properties,
            )
        result = {"success": True, "page_id": page["id"], "dry_run": False, "error": ""}
        _log_sync(contact_id, contact_name, "contact", page["id"], True, "")
        return result
    except Exception as exc:
        error = str(exc)
        _log_sync(contact_id, contact_name, "contact", None, False, error)
        return {"success": False, "page_id": None, "dry_run": False, "error": error}


def sync_interaction(
    contact_id:   str,
    contact_name: str,
    platform:     str,
    sent_at:      str,
    replied:      bool = False,
    sentiment:    Optional[float] = None,
    revenue_usd:  float = 0.0,
    dry_run:      bool = True,
) -> dict:
    """
    Log one interaction (wish sent) to the Notion Interaction Log database.
    Always creates a new page (interactions are append-only, not updated).

    Returns:
        { success, page_id, dry_run, error }
    """
    init_notion_tables()

    if dry_run:
        result = {"success": True, "page_id": "dry_run_mock", "dry_run": True, "error": ""}
        _log_sync(contact_id, contact_name, "interaction", result["page_id"], True, "")
        return result

    client = _get_notion_client()
    if not client or not NOTION_LOG_DB_ID:
        error = "Notion not configured (set NOTION_API_KEY and NOTION_LOG_DB_ID)"
        _log_sync(contact_id, contact_name, "interaction", None, False, error)
        return {"success": False, "page_id": None, "dry_run": False, "error": error}

    properties = {
        "Contact":     {"title": [{"text": {"content": contact_name}}]},
        "Platform":    {"select": {"name": platform}},
        "Wish Sent":   {"date": {"start": sent_at}},
        "Replied":     {"checkbox": replied},
        "Revenue USD": {"number": revenue_usd},
        "Contact ID":  {"rich_text": [{"text": {"content": contact_id}}]},
    }
    if sentiment is not None:
        properties["Sentiment"] = {"number": sentiment}

    try:
        page = client.pages.create(
            parent={"database_id": NOTION_LOG_DB_ID},
            properties=properties,
        )
        result = {"success": True, "page_id": page["id"], "dry_run": False, "error": ""}
        _log_sync(contact_id, contact_name, "interaction", page["id"], True, "")
        return result
    except Exception as exc:
        error = str(exc)
        _log_sync(contact_id, contact_name, "interaction", None, False, error)
        return {"success": False, "page_id": None, "dry_run": False, "error": error}


def _log_sync(contact_id, contact_name, sync_type, page_id, synced, error_msg):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO notion_sync_log
            (contact_id, contact_name, sync_type, notion_page_id,
             synced, error_msg, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, sync_type, page_id,
          1 if synced else 0, error_msg, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Batch sync ─────────────────────────────────────────────────────────────────

def sync_all_contacts(dry_run: bool = True, verbose: bool = True) -> dict:
    """
    Sync every contact to the Notion Contacts database.

    Returns:
        { total, synced, failed, dry_run }
    """
    init_notion_tables()
    contacts = _load_contacts()

    if verbose:
        print(f"[Notion Sync] Syncing {len(contacts)} contacts "
              f"({'DRY RUN' if dry_run else 'LIVE'})\n")

    synced = failed = 0
    for c in contacts:
        result = sync_contact(
            c["contact_id"], c["contact_name"], c.get("tier","Acquaintance"),
            c.get("tier_score",5.0), c.get("platform","LinkedIn"),
            c.get("birthday",""), c.get("is_vip",False), dry_run=dry_run)
        if result["success"]:
            synced += 1
            if verbose:
                print(f"  ✅ {c['contact_name']:<22} {c.get('tier','')}")
        else:
            failed += 1
            if verbose:
                print(f"  ❌ {c['contact_name']:<22} {result['error'][:40]}")

    if verbose:
        print(f"\n[Notion Sync] Done: {synced} synced, {failed} failed")

    return {"total": len(contacts), "synced": synced,
            "failed": failed, "dry_run": dry_run}


def sync_recent_interactions(days: int = 7, dry_run: bool = True,
                             verbose: bool = True) -> dict:
    """Sync recent wish_outcome_log entries to Notion Interaction Log."""
    init_notion_tables()
    conn = _db()
    interactions = []
    if _table_exists(conn, "wish_outcome_log"):
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT contact_id, contact_name, platform, sent_at,
                   replied, sentiment_score
            FROM wish_outcome_log WHERE sent_at >= ?
            ORDER BY sent_at DESC LIMIT 50
        """, (cutoff,)).fetchall()
        interactions = [dict(r) for r in rows]
    conn.close()

    if verbose:
        print(f"[Notion Sync] Syncing {len(interactions)} interactions "
              f"({'DRY RUN' if dry_run else 'LIVE'})\n")

    # Get revenue per contact for enrichment
    revenue_map: dict = {}
    get_deals = _safe("dashboards.revenue_attribution", "get_contact_deals")

    synced = 0
    for i in interactions:
        rev = 0.0
        if get_deals:
            try:
                deals = get_deals(i["contact_id"])
                rev   = sum(d.get("value_usd",0) for d in deals)
            except Exception:
                pass
        result = sync_interaction(
            i["contact_id"], i["contact_name"], i["platform"],
            i["sent_at"], bool(i.get("replied")),
            i.get("sentiment_score"), rev, dry_run=dry_run)
        if result["success"]:
            synced += 1
            if verbose:
                print(f"  ✅ {i['contact_name']:<22} {i['platform']}")

    if verbose:
        print(f"\n[Notion Sync] Done: {synced}/{len(interactions)} synced")

    return {"total": len(interactions), "synced": synced, "dry_run": dry_run}


def full_sync(dry_run: bool = True, verbose: bool = True) -> dict:
    """Run a complete sync: all contacts + recent interactions."""
    contact_result = sync_all_contacts(dry_run, verbose)
    if verbose:
        print()
    interaction_result = sync_recent_interactions(7, dry_run, verbose)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO notion_sync_state
            (id, contacts_db_id, log_db_id, last_full_sync,
             contacts_synced, logs_synced)
        VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            last_full_sync  = excluded.last_full_sync,
            contacts_synced = excluded.contacts_synced,
            logs_synced     = excluded.logs_synced
    """, (NOTION_CONTACTS_DB_ID, NOTION_LOG_DB_ID,
          datetime.now().isoformat(),
          contact_result["synced"], interaction_result["synced"]))
    conn.commit()
    conn.close()

    return {
        "contacts":     contact_result,
        "interactions": interaction_result,
        "dry_run":      dry_run,
    }


def _load_contacts() -> list[dict]:
    if not DB_PATH.exists():
        return _demo_contacts()
    conn = _db()
    contacts = []
    if _table_exists(conn, "contact_tier"):
        rows = conn.execute("""
            SELECT contact_id, contact_name, current_tier, tier_score
            FROM contact_tier
        """).fetchall()
        for r in rows:
            contacts.append({"contact_id": r["contact_id"],
                             "contact_name": r["contact_name"],
                             "tier": r["current_tier"],
                             "tier_score": r["tier_score"] or 5.0,
                             "platform": "LinkedIn", "birthday": "",
                             "is_vip": False})
    if contacts and _table_exists(conn, "vip_contacts"):
        vip_ids = {r["contact_id"] for r in
                   conn.execute("SELECT contact_id FROM vip_contacts WHERE active=1")}
        for c in contacts:
            c["is_vip"] = c["contact_id"] in vip_ids
    conn.close()
    return contacts if contacts else _demo_contacts()


def _demo_contacts() -> list[dict]:
    return [
        {"contact_id":"urn_rakib_001","contact_name":"Rakib Hossain",
         "tier":"Close Friend","tier_score":9.0,"platform":"LinkedIn",
         "birthday":"08-04","is_vip":True},
        {"contact_id":"urn_nadia_002","contact_name":"Nadia Islam",
         "tier":"Colleague","tier_score":7.0,"platform":"WhatsApp",
         "birthday":"03-15","is_vip":False},
        {"contact_id":"urn_mim_004","contact_name":"Mim Chowdhury",
         "tier":"Close Friend","tier_score":9.5,"platform":"WhatsApp",
         "birthday":"07-22","is_vip":True},
    ]


def get_sync_status() -> dict:
    """Return current Notion sync configuration and last sync info."""
    init_notion_tables()
    client = _get_notion_client()
    conn   = _db()
    state  = conn.execute(
        "SELECT * FROM notion_sync_state WHERE id=1").fetchone()
    total_synced = conn.execute(
        "SELECT COUNT(*) FROM notion_sync_log WHERE synced=1").fetchone()[0]
    conn.close()
    return {
        "configured":      client is not None and bool(NOTION_CONTACTS_DB_ID),
        "has_api_key":     bool(NOTION_API_KEY),
        "has_contacts_db": bool(NOTION_CONTACTS_DB_ID),
        "has_log_db":      bool(NOTION_LOG_DB_ID),
        "last_full_sync":  state["last_full_sync"] if state else None,
        "total_synced":    total_synced,
    }


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Notion Sync", page_icon="🗂",
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
    .cc-badge{background:#000;color:#fff;font-size:0.65rem;font-weight:700;
              padding:2px 8px;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;
              border:1px solid #444;}
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);
                font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:var(--muted);margin:22px 0 10px;
                   display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .e-row{background:var(--surface);border:1px solid var(--border);
           border-radius:8px;padding:10px 14px;margin-bottom:6px;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.3rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    .code-box{background:#010409;border:1px solid var(--border);border-radius:8px;
              padding:12px 14px;font-family:'JetBrains Mono',monospace;
              font-size:0.76rem;color:#7ee787;white-space:pre;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:#000;
        border-color:#444;color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_notion_tables()
    status = get_sync_status()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🗂</span>
      <h1>Notion Database Sync</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Configured", "✓ Yes" if status["configured"] else "✗ No",
         "#3fb950" if status["configured"] else "#f85149"),
        (m2, "API Key",    "✓ Set" if status["has_api_key"] else "✗ Missing",
         "#3fb950" if status["has_api_key"] else "#f85149"),
        (m3, "Total Synced", status["total_synced"], "#f78166"),
        (m4, "Last Sync",
         (status["last_full_sync"] or "Never")[:16].replace("T"," "),
         "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" '
                        f'style="color:{color};font-size:0.95rem">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    if not status["configured"]:
        st.markdown("""
        <div style="background:#1a1500;border-left:4px solid #d29922;
                    border-radius:8px;padding:12px 16px;margin:16px 0;">
          <div style="color:#d29922;font-weight:700">Not configured</div>
          <div style="font-size:0.78rem;color:#c9d1d9;margin-top:4px">
            Set NOTION_API_KEY and NOTION_CONTACTS_DB_ID to enable syncing.
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Setup</div>',
                    unsafe_allow_html=True)
        st.markdown("""
        <div class="code-box">pip install notion-client

# 1. Create integration: notion.so/my-integrations
# 2. Share your Notion page with the integration
# 3. Get parent page ID from its URL

python notion_sync.py create-dbs &lt;parent_page_id&gt;
# Copy returned DB IDs into .env:
NOTION_API_KEY=secret_xxx
NOTION_CONTACTS_DB_ID=xxx
NOTION_LOG_DB_ID=xxx

python notion_sync.py sync</div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Sync Actions</div>',
                    unsafe_allow_html=True)
        dry_run = st.checkbox("Dry Run", value=True)
        if st.button("🗂 Sync Now", type="primary", use_container_width=True):
            with st.spinner("Syncing..."):
                result = full_sync(dry_run=dry_run, verbose=False)
            total = result["contacts"]["synced"] + result["interactions"]["synced"]
            st.success(f"Synced {total} items "
                       f"({'dry run' if dry_run else 'live'})")
            st.rerun()

    with right:
        st.markdown('<div class="section-title">Recent Sync Log</div>',
                    unsafe_allow_html=True)
        conn = _db()
        rows = conn.execute("""
            SELECT contact_name, sync_type, synced, error_msg, synced_at
            FROM notion_sync_log ORDER BY synced_at DESC LIMIT 15
        """).fetchall()
        conn.close()
        for r in rows:
            ok    = bool(r["synced"])
            color = "#3fb950" if ok else "#f85149"
            icon  = "👤" if r["sync_type"]=="contact" else "💬"
            st.markdown(f"""
            <div class="e-row">
              <div style="display:flex;justify-content:space-between">
                <span style="font-weight:700;font-size:0.82rem">
                  {icon} {r['contact_name']}
                </span>
                <span style="color:{color};font-size:0.7rem;font-weight:700">
                  {'✅ synced' if ok else '❌ failed'}
                </span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:3px">
                {r['sync_type']}
                {f' · {r["error_msg"][:40]}' if r['error_msg'] else ''}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Notion Database Sync</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "create-dbs":
        if len(sys.argv) < 3:
            print("Usage: python notion_sync.py create-dbs <parent_page_id>")
        else:
            parent_id = sys.argv[2]
            cdb = create_contacts_database(parent_id)
            ldb = create_interaction_log_database(parent_id)
            print(f"\nAdd to .env:")
            print(f"NOTION_CONTACTS_DB_ID={cdb}")
            print(f"NOTION_LOG_DB_ID={ldb}")

    elif cmd == "sync":
        is_live = "--live" in sys.argv
        result  = full_sync(dry_run=not is_live, verbose=True)
        total   = result["contacts"]["synced"] + result["interactions"]["synced"]
        print(f"\nTotal synced: {total}")

    elif cmd == "status":
        print("=== Notion Database Sync -- self test ===\n")
        status = get_sync_status()
        print(f"Configured    : {status['configured']}")
        print(f"Has API key   : {status['has_api_key']}")
        print(f"Has contacts DB: {status['has_contacts_db']}")
        print(f"Last sync     : {status['last_full_sync'] or 'Never'}")
        print(f"Total synced  : {status['total_synced']}")

        print("\nRunning dry-run sync test...")
        result = full_sync(dry_run=True, verbose=True)
        total  = result["contacts"]["synced"] + result["interactions"]["synced"]
        print(f"\nDry-run result: {total} items would be synced")
else:
    render_dashboard()
