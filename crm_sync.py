"""
CRM Sync (HubSpot / Salesforce) -- Birthday Wishes Agent v10.0
Pushes contact data into a real CRM and tracks each relationship as a
deal, so business users can see their outreach pipeline where the rest
of their sales lives -- no separate dashboard required.

What gets pushed:
  - Contacts (name, email, platform, relationship tier, VIP flag,
    personalization score, last wish date) as CRM contacts
  - Deals -- one "relationship deal" per contact, advanced through a
    pipeline stage as engagement changes (wished -> replied -> won)
  - Sync log + deal log persisted locally for auditing and dashboards

Providers (pick one via CRM_PROVIDER):
  - hubspot     -> HubSpot CRM v3 REST API (private-app access token)
  - salesforce  -> Salesforce REST API (OAuth2 username-password flow)

Auth: token / OAuth2 read from environment. When no provider is
      configured the module runs in mock mode (dry run), so it is safe
      to import and test without credentials.

Requires (only for live sending -- mock mode needs nothing extra):
  pip install requests    # already a project dependency

Integrates with: contacts/relationship_tiering.py,
                 contacts/vip_contact_flagging.py,
                 ai/wish_personalization_score.py, agent.py
"""

import os
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH   = Path("agent_history.db")
PROVIDER  = os.getenv("CRM_PROVIDER", "").strip().lower()   # hubspot | salesforce | ""

# ── HubSpot config ─────────────────────────────────────────────────────────────
HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
HUBSPOT_BASE         = "https://api.hubapi.com"

# ── Salesforce config ──────────────────────────────────────────────────────────
SF_CLIENT_ID     = os.getenv("SALESFORCE_CLIENT_ID", "")
SF_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET", "")
SF_USERNAME      = os.getenv("SALESFORCE_USERNAME", "")
SF_PASSWORD      = os.getenv("SALESFORCE_PASSWORD", "")        # password + security token
SF_LOGIN_URL     = os.getenv("SALESFORCE_LOGIN_URL", "https://login.salesforce.com")
SF_API_VERSION   = "v59.0"

# Pipeline stages a relationship deal moves through.
DEAL_STAGES = {
    "identified": {"label": "Identified",   "icon": "🔍"},
    "wished":     {"label": "Wish Sent",     "icon": "🎂"},
    "replied":    {"label": "Replied",       "icon": "💬"},
    "engaged":    {"label": "Engaged",       "icon": "🤝"},
    "won":        {"label": "Relationship Won", "icon": "🏆"},
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_crm_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_sync_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id     TEXT NOT NULL,
            contact_name   TEXT NOT NULL,
            provider       TEXT NOT NULL,
            crm_object     TEXT NOT NULL,      -- contact | deal
            crm_record_id  TEXT,
            action         TEXT NOT NULL,      -- create | update | skip
            synced         INTEGER NOT NULL DEFAULT 0,
            error_msg      TEXT,
            synced_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_deal_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id     TEXT NOT NULL,
            provider       TEXT NOT NULL,
            crm_deal_id    TEXT,
            stage          TEXT NOT NULL,
            amount         REAL NOT NULL DEFAULT 0,
            updated_at     TEXT NOT NULL,
            UNIQUE(contact_id, provider)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_sync_state (
            id             INTEGER PRIMARY KEY CHECK (id = 1),
            provider       TEXT,
            last_full_sync TEXT,
            records_synced INTEGER NOT NULL DEFAULT 0
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


# ── Provider clients ───────────────────────────────────────────────────────────

def _provider_configured() -> bool:
    if PROVIDER == "hubspot":
        return bool(HUBSPOT_ACCESS_TOKEN)
    if PROVIDER == "salesforce":
        return all([SF_CLIENT_ID, SF_CLIENT_SECRET, SF_USERNAME, SF_PASSWORD])
    return False


def _hubspot_headers() -> dict:
    return {"Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
            "Content-Type": "application/json"}


def _salesforce_login() -> Optional[dict]:
    """
    OAuth2 username-password flow. Returns {access_token, instance_url}
    or None if auth fails / requests is unavailable.
    """
    try:
        import requests
    except ImportError:
        return None
    try:
        resp = requests.post(
            f"{SF_LOGIN_URL}/services/oauth2/token",
            data={
                "grant_type":    "password",
                "client_id":     SF_CLIENT_ID,
                "client_secret": SF_CLIENT_SECRET,
                "username":      SF_USERNAME,
                "password":      SF_PASSWORD,
            }, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return {"access_token": data["access_token"],
                "instance_url": data["instance_url"]}
    except Exception as exc:
        print(f"[CRM] Salesforce login failed: {exc}")
        return None


# ── Contact push ───────────────────────────────────────────────────────────────

def _contact_properties(c: dict) -> dict:
    """Map an agent contact dict to a flat property bag both CRMs accept."""
    return {
        "full_name":            c.get("contact_name", ""),
        "email":                c.get("email", ""),
        "platform":             c.get("platform", "linkedin"),
        "relationship_tier":    c.get("tier", "acquaintance"),
        "is_vip":               "true" if c.get("is_vip") else "false",
        "personalization_score": str(c.get("score", 0)),
        "last_wish_date":       c.get("last_wish_date", ""),
        "agent_contact_id":     c.get("contact_id", ""),
    }


def _push_hubspot_contact(c: dict) -> dict:
    import requests
    props = _contact_properties(c)
    # HubSpot uses email as the natural dedup key.
    email = props.get("email") or f"{c['contact_id']}@no-email.agent"
    body  = {"properties": {
        "email":     email,
        "firstname": props["full_name"].split(" ")[0] if props["full_name"] else "",
        "lastname":  " ".join(props["full_name"].split(" ")[1:]),
        "hs_lead_status": "IN_PROGRESS",
        # custom properties (create these once in HubSpot settings)
        "platform":              props["platform"],
        "relationship_tier":     props["relationship_tier"],
        "personalization_score": props["personalization_score"],
        "agent_contact_id":      props["agent_contact_id"],
    }}
    # Upsert by email: try create, fall back to update on 409 conflict.
    r = requests.post(f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
                      headers=_hubspot_headers(), json=body, timeout=20)
    if r.status_code == 409:
        existing_id = r.json().get("message", "").split("ID: ")[-1].strip(" .")
        r = requests.patch(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{existing_id}",
            headers=_hubspot_headers(), json=body, timeout=20)
        r.raise_for_status()
        return {"id": r.json()["id"], "action": "update"}
    r.raise_for_status()
    return {"id": r.json()["id"], "action": "create"}


def _push_salesforce_contact(c: dict, session: dict) -> dict:
    import requests
    props = _contact_properties(c)
    names = props["full_name"].split(" ")
    body  = {
        "LastName":  " ".join(names[1:]) or names[0] or "Unknown",
        "FirstName": names[0] if len(names) > 1 else "",
        "Email":     props["email"] or None,
        "Description": (f"Platform: {props['platform']} | "
                        f"Tier: {props['relationship_tier']} | "
                        f"Score: {props['personalization_score']} | "
                        f"AgentID: {props['agent_contact_id']}"),
    }
    inst = session["instance_url"]
    hdr  = {"Authorization": f"Bearer {session['access_token']}",
            "Content-Type": "application/json"}
    r = requests.post(
        f"{inst}/services/data/{SF_API_VERSION}/sobjects/Contact",
        headers=hdr, json=body, timeout=20)
    r.raise_for_status()
    return {"id": r.json()["id"], "action": "create"}


def push_contact(c: dict, dry_run: bool = True,
                 session: Optional[dict] = None) -> dict:
    """
    Push a single contact into the configured CRM.

    Returns:
        { success, record_id, action, provider, dry_run, error }
    """
    init_crm_tables()
    base = {"provider": PROVIDER or "none", "dry_run": dry_run}

    if dry_run or not _provider_configured():
        action = "skip" if not _provider_configured() and not dry_run else "create"
        result = {**base, "success": bool(dry_run), "record_id": "dry_run_mock",
                  "action": action,
                  "error": "" if dry_run else "CRM not configured"}
        _log_sync(c["contact_id"], c["contact_name"], "contact",
                  result["record_id"], action, result["success"], result["error"])
        return result

    try:
        if PROVIDER == "hubspot":
            res = _push_hubspot_contact(c)
        elif PROVIDER == "salesforce":
            session = session or _salesforce_login()
            if session is None:
                raise RuntimeError("Salesforce auth failed")
            res = _push_salesforce_contact(c, session)
        else:
            raise RuntimeError(f"Unknown CRM_PROVIDER '{PROVIDER}'")

        result = {**base, "success": True, "record_id": res["id"],
                  "action": res["action"], "error": ""}
        _log_sync(c["contact_id"], c["contact_name"], "contact",
                  res["id"], res["action"], True, "")
        return result

    except Exception as exc:
        result = {**base, "success": False, "record_id": None,
                  "action": "create", "error": str(exc)}
        _log_sync(c["contact_id"], c["contact_name"], "contact",
                  None, "create", False, str(exc))
        return result


# ── Deal tracking ──────────────────────────────────────────────────────────────

def _push_hubspot_deal(c: dict, stage: str, amount: float) -> dict:
    import requests
    body = {"properties": {
        "dealname":  f"Relationship — {c['contact_name']}",
        "dealstage": stage,
        "amount":    str(amount),
        "pipeline":  "default",
        "agent_contact_id": c["contact_id"],
    }}
    r = requests.post(f"{HUBSPOT_BASE}/crm/v3/objects/deals",
                      headers=_hubspot_headers(), json=body, timeout=20)
    r.raise_for_status()
    return {"id": r.json()["id"]}


def _push_salesforce_deal(c: dict, stage: str, amount: float,
                          session: dict) -> dict:
    import requests
    inst = session["instance_url"]
    hdr  = {"Authorization": f"Bearer {session['access_token']}",
            "Content-Type": "application/json"}
    body = {
        "Name":      f"Relationship — {c['contact_name']}",
        "StageName": DEAL_STAGES.get(stage, {}).get("label", "Prospecting"),
        "Amount":    amount,
        "CloseDate": datetime.now().strftime("%Y-%m-%d"),
    }
    r = requests.post(
        f"{inst}/services/data/{SF_API_VERSION}/sobjects/Opportunity",
        headers=hdr, json=body, timeout=20)
    r.raise_for_status()
    return {"id": r.json()["id"]}


def track_deal(c: dict, stage: str = "wished", amount: float = 0.0,
               dry_run: bool = True, session: Optional[dict] = None) -> dict:
    """
    Create or advance a relationship deal for a contact.

    Returns:
        { success, deal_id, stage, provider, dry_run, error }
    """
    init_crm_tables()
    if stage not in DEAL_STAGES:
        stage = "wished"
    base = {"provider": PROVIDER or "none", "stage": stage, "dry_run": dry_run}

    if dry_run or not _provider_configured():
        deal_id = "dry_run_deal"
        _record_deal(c["contact_id"], deal_id, stage, amount)
        return {**base, "success": bool(dry_run), "deal_id": deal_id,
                "error": "" if dry_run else "CRM not configured"}

    try:
        if PROVIDER == "hubspot":
            res = _push_hubspot_deal(c, stage, amount)
        elif PROVIDER == "salesforce":
            session = session or _salesforce_login()
            if session is None:
                raise RuntimeError("Salesforce auth failed")
            res = _push_salesforce_deal(c, stage, amount, session)
        else:
            raise RuntimeError(f"Unknown CRM_PROVIDER '{PROVIDER}'")

        _record_deal(c["contact_id"], res["id"], stage, amount)
        _log_sync(c["contact_id"], c["contact_name"], "deal",
                  res["id"], "create", True, "")
        return {**base, "success": True, "deal_id": res["id"], "error": ""}

    except Exception as exc:
        _log_sync(c["contact_id"], c["contact_name"], "deal",
                  None, "create", False, str(exc))
        return {**base, "success": False, "deal_id": None, "error": str(exc)}


def _record_deal(contact_id, deal_id, stage, amount):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO crm_deal_log (contact_id, provider, crm_deal_id,
                                  stage, amount, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id, provider) DO UPDATE SET
            crm_deal_id = excluded.crm_deal_id,
            stage       = excluded.stage,
            amount      = excluded.amount,
            updated_at  = excluded.updated_at
    """, (contact_id, PROVIDER or "none", deal_id, stage, amount,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


def _log_sync(contact_id, contact_name, crm_object, record_id,
              action, synced, error_msg):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO crm_sync_log
            (contact_id, contact_name, provider, crm_object, crm_record_id,
             action, synced, error_msg, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, PROVIDER or "none", crm_object,
          record_id, action, 1 if synced else 0, error_msg,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Batch sync ─────────────────────────────────────────────────────────────────

def sync_all_contacts(dry_run: bool = True, with_deals: bool = True,
                      verbose: bool = True) -> dict:
    """
    Push every known contact into the CRM (and optionally open a deal).

    Returns:
        { total, synced, failed, deals, provider, dry_run }
    """
    init_crm_tables()
    contacts = _load_contacts()

    # Reuse one Salesforce session across the whole batch.
    session = None
    if not dry_run and PROVIDER == "salesforce" and _provider_configured():
        session = _salesforce_login()

    if verbose:
        print(f"[CRM Sync] Provider={PROVIDER or 'none'} · "
              f"{len(contacts)} contacts "
              f"({'DRY RUN' if dry_run else 'LIVE'})\n")

    synced = failed = deals = 0
    for c in contacts:
        res = push_contact(c, dry_run=dry_run, session=session)
        if res["success"]:
            synced += 1
            if verbose:
                print(f"  ✅ {c['contact_name']:<22} {res['action']}")
            if with_deals:
                stage  = "wished" if c.get("last_wish_date") else "identified"
                dres   = track_deal(c, stage=stage, dry_run=dry_run,
                                    session=session)
                deals += 1 if dres["success"] else 0
        else:
            failed += 1
            if verbose:
                print(f"  ❌ {c['contact_name']:<22} {res['error'][:40]}")

    _save_state(synced + deals)
    if verbose:
        print(f"\n[CRM Sync] Done: {synced} contacts, {deals} deals, "
              f"{failed} failed")

    return {"total": len(contacts), "synced": synced, "failed": failed,
            "deals": deals, "provider": PROVIDER or "none", "dry_run": dry_run}


def _save_state(records_synced: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO crm_sync_state (id, provider, last_full_sync, records_synced)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            provider       = excluded.provider,
            last_full_sync = excluded.last_full_sync,
            records_synced = excluded.records_synced
    """, (PROVIDER or "none", datetime.now().isoformat(), records_synced))
    conn.commit()
    conn.close()


def _load_contacts() -> list[dict]:
    """Load contacts from the agent DB, or fall back to demo data."""
    if not DB_PATH.exists():
        return _demo_contacts()

    conn = _db()
    contacts = []
    if _table_exists(conn, "contact_life_events"):
        rows = conn.execute("""
            SELECT DISTINCT contact_id, contact_name
            FROM contact_life_events
        """).fetchall()
        contacts = [{"contact_id": r["contact_id"],
                     "contact_name": r["contact_name"],
                     "platform": "linkedin"} for r in rows]

    # Enrich with VIP flag when available.
    if contacts and _table_exists(conn, "vip_contacts"):
        vip_ids = {r["contact_id"] for r in
                   conn.execute("SELECT contact_id FROM vip_contacts WHERE active=1")}
        for c in contacts:
            c["is_vip"] = c["contact_id"] in vip_ids
    conn.close()

    return contacts if contacts else _demo_contacts()


def _demo_contacts() -> list[dict]:
    return [
        {"contact_id": "urn_rakib_001", "contact_name": "Rakib Hossain",
         "email": "rakib@example.com", "platform": "linkedin",
         "tier": "close_friend", "is_vip": True, "score": 92,
         "last_wish_date": "2026-08-05"},
        {"contact_id": "urn_nadia_002", "contact_name": "Nadia Islam",
         "email": "nadia@example.com", "platform": "whatsapp",
         "tier": "colleague", "is_vip": False, "score": 74,
         "last_wish_date": ""},
        {"contact_id": "urn_mim_004", "contact_name": "Mim Chowdhury",
         "email": "mim@example.com", "platform": "linkedin",
         "tier": "colleague", "is_vip": True, "score": 88,
         "last_wish_date": "2026-07-22"},
    ]


def get_sync_status() -> dict:
    """Return current CRM configuration and last sync info."""
    init_crm_tables()
    conn  = _db()
    state = conn.execute("SELECT * FROM crm_sync_state WHERE id=1").fetchone()
    total = conn.execute(
        "SELECT COUNT(*) FROM crm_sync_log WHERE synced=1").fetchone()[0]
    open_deals = conn.execute(
        "SELECT COUNT(*) FROM crm_deal_log").fetchone()[0]
    conn.close()
    return {
        "provider":       PROVIDER or "none",
        "configured":     _provider_configured(),
        "last_full_sync": state["last_full_sync"] if state else None,
        "records_synced": total,
        "open_deals":     open_deals,
    }


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="CRM Sync", page_icon="🧮",
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
    .cc-badge{background:#ff7a59;color:#fff;font-size:0.65rem;font-weight:700;
              padding:2px 8px;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;}
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
    div[data-testid="stButton"]>button[kind="primary"]{background:#ff7a59;
        border-color:#ff7a59;color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_crm_tables()
    status = get_sync_status()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🧮</span>
      <h1>CRM Sync</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Provider", status["provider"], "#ff7a59"),
        (m2, "Configured", "✓ Yes" if status["configured"] else "✗ No",
         "#3fb950" if status["configured"] else "#f85149"),
        (m3, "Records Synced", status["records_synced"], "#58a6ff"),
        (m4, "Open Deals", status["open_deals"], "#d29922"),
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
            Set <code style="color:#7ee787">CRM_PROVIDER=hubspot</code> (+ token)
            or <code style="color:#7ee787">CRM_PROVIDER=salesforce</code> (+ OAuth
            creds) in your <code>.env</code>. Runs in dry-run mock mode until then.
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Setup</div>',
                    unsafe_allow_html=True)
        st.markdown("""
        <div class="code-box"># HubSpot
CRM_PROVIDER=hubspot
HUBSPOT_ACCESS_TOKEN=pat-xxxxxxxx   # private app token

# Salesforce
CRM_PROVIDER=salesforce
SALESFORCE_CLIENT_ID=...
SALESFORCE_CLIENT_SECRET=...
SALESFORCE_USERNAME=you@company.com
SALESFORCE_PASSWORD=pass+securitytoken

python crm_sync.py sync          # dry run
python crm_sync.py sync --live   # push for real</div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Sync Actions</div>',
                    unsafe_allow_html=True)
        dry_run    = st.checkbox("Dry Run", value=True)
        with_deals = st.checkbox("Also open deals", value=True)
        if st.button("🧮 Sync Now", type="primary", use_container_width=True):
            with st.spinner("Syncing to CRM..."):
                result = sync_all_contacts(dry_run=dry_run,
                                           with_deals=with_deals, verbose=False)
            st.success(f"{result['synced']} contacts · {result['deals']} deals "
                       f"({'dry run' if dry_run else 'live'})")
            st.rerun()

    with right:
        st.markdown('<div class="section-title">Recent Sync Log</div>',
                    unsafe_allow_html=True)
        conn = _db()
        rows = conn.execute("""
            SELECT contact_name, crm_object, action, synced, error_msg, synced_at
            FROM crm_sync_log ORDER BY synced_at DESC LIMIT 15
        """).fetchall()
        conn.close()
        for r in rows:
            ok    = bool(r["synced"])
            color = "#3fb950" if ok else "#f85149"
            icon  = "🤝" if r["crm_object"] == "deal" else "👤"
            st.markdown(f"""
            <div class="e-row">
              <div style="display:flex;justify-content:space-between">
                <span style="font-weight:700;font-size:0.82rem">
                  {icon} {r['contact_name']}
                </span>
                <span style="color:{color};font-size:0.7rem;font-weight:700">
                  {'✅ ' + r['action'] if ok else '❌ failed'}
                </span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:3px">
                {r['crm_object']}
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
      <span>CRM Sync — HubSpot / Salesforce</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "sync":
        is_live = "--live" in sys.argv
        result  = sync_all_contacts(dry_run=not is_live, verbose=True)
        print(f"\nTotal: {result['synced']} contacts, {result['deals']} deals")

    elif cmd == "status":
        print("=== CRM Sync -- self test ===\n")
        status = get_sync_status()
        print(f"Provider     : {status['provider']}")
        print(f"Configured   : {status['configured']}")
        print(f"Last sync    : {status['last_full_sync'] or 'Never'}")
        print(f"Records synced: {status['records_synced']}")
        print(f"Open deals   : {status['open_deals']}")

        print("\nRunning dry-run sync test...")
        result = sync_all_contacts(dry_run=True, verbose=True)
        print(f"\nDry-run result: {result['synced']} contacts, "
              f"{result['deals']} deals would sync")
else:
    render_dashboard()
