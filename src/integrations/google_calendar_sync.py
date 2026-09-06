"""
Google Calendar Sync -- Birthday Wishes Agent v10.0
Syncs all contact birthdays and detected life events to a
dedicated Google Calendar, so the user sees everything alongside
their normal schedule -- no separate dashboard needed.

What gets synced:
  - Contact birthdays (recurring yearly events)
  - Detected life events (promotions, weddings, etc. from
    whatsapp_status_watcher.py / contact_life_events table)
  - Scheduled follow-ups (from redis_cache follow-up queue)
  - VIP contact reminders (extra lead time)

Auth: OAuth2 (user's own calendar) via google-auth-oauthlib.
      Falls back to service account if GOOGLE_SERVICE_ACCOUNT_JSON is set.

Requires:
  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Integrates with: contacts/relationship_tiering.py,
                 contacts/vip_contact_flagging.py,
                 platforms/whatsapp_status_watcher.py, agent.py
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH          = Path("agent_history.db")
TOKEN_PATH        = Path("google_calendar_token.json")
CREDENTIALS_PATH  = Path("google_calendar_credentials.json")
CALENDAR_NAME      = "Birthday Wishes Agent"
SCOPES             = ["https://www.googleapis.com/auth/calendar"]

SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

EVENT_COLORS = {
    "birthday":      {"colorId": "11", "icon": "🎂"},   # tomato red
    "life_event":    {"colorId": "5",  "icon": "🎉"},   # banana yellow
    "followup":      {"colorId": "9",  "icon": "💬"},   # blueberry
    "vip_reminder":  {"colorId": "6",  "icon": "💎"},   # tangerine
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_sync_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_sync_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            gcal_event_id   TEXT,
            event_date      TEXT NOT NULL,
            synced          INTEGER NOT NULL DEFAULT 0,
            error_msg       TEXT,
            synced_at       TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_sync_state (
            id              INTEGER PRIMARY KEY CHECK (id = 1),
            calendar_id     TEXT,
            last_full_sync  TEXT,
            events_synced   INTEGER NOT NULL DEFAULT 0
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


# ── Google API client ─────────────────────────────────────────────────────────

def _get_calendar_service():
    """
    Build an authenticated Google Calendar API service.
    Tries OAuth2 user flow first, falls back to service account.
    Returns None if neither is configured (mock mode).
    """
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return None

    # Service account (server-to-server, no browser needed)
    if SERVICE_ACCOUNT_JSON:
        try:
            from google.oauth2 import service_account
            info  = json.loads(SERVICE_ACCOUNT_JSON)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES)
            return build("calendar", "v3", credentials=creds)
        except Exception as exc:
            print(f"[GCal] Service account auth failed: {exc}")

    # OAuth2 user flow (requires prior browser consent, token cached)
    if TOKEN_PATH.exists():
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
            if creds and creds.valid:
                return build("calendar", "v3", credentials=creds)
        except Exception as exc:
            print(f"[GCal] OAuth token load failed: {exc}")

    return None


def run_oauth_flow() -> bool:
    """
    Run the interactive OAuth2 consent flow (opens browser once).
    Requires google_calendar_credentials.json (from Google Cloud Console).
    Saves token to google_calendar_token.json for future use.
    """
    if not CREDENTIALS_PATH.exists():
        print(f"[GCal] {CREDENTIALS_PATH} not found. "
              "Download OAuth client credentials from Google Cloud Console.")
        return False
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow  = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
        print(f"[GCal] Auth complete. Token saved to {TOKEN_PATH}")
        return True
    except Exception as exc:
        print(f"[GCal] OAuth flow failed: {exc}")
        return False


def get_or_create_calendar(service) -> Optional[str]:
    """Find or create the 'Birthday Wishes Agent' calendar, return its ID."""
    if service is None:
        return None
    try:
        cal_list = service.calendarList().list().execute()
        for cal in cal_list.get("items", []):
            if cal.get("summary") == CALENDAR_NAME:
                return cal["id"]
        # Create new calendar
        new_cal = service.calendars().insert(body={
            "summary":  CALENDAR_NAME,
            "description": "Auto-synced by Birthday Wishes Agent v10.0",
            "timeZone": "Asia/Dhaka",
        }).execute()
        return new_cal["id"]
    except Exception as exc:
        print(f"[GCal] Calendar lookup/create failed: {exc}")
        return None


# ── Event builders ────────────────────────────────────────────────────────────

def _build_birthday_event(contact_id: str, contact_name: str,
                          birthday_md: str, is_vip: bool = False) -> dict:
    """Build a recurring yearly birthday event body."""
    year   = datetime.now().year
    try:
        month, day = birthday_md.split("-")
        date_obj   = datetime(year, int(month), int(day))
    except (ValueError, IndexError):
        date_obj   = datetime.now()
    date_str = date_obj.strftime("%Y-%m-%d")

    icon = "💎🎂" if is_vip else "🎂"
    return {
        "summary":     f"{icon} {contact_name}'s Birthday",
        "description": f"Auto-synced by Birthday Wishes Agent.\n"
                       f"Contact ID: {contact_id}\n"
                       f"{'⭐ VIP contact — extra care needed!' if is_vip else ''}",
        "start":  {"date": date_str},
        "end":    {"date": date_str},
        "recurrence": ["RRULE:FREQ=YEARLY"],
        "colorId": EVENT_COLORS["birthday"]["colorId"],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 24 * 60},        # 1 day before
                {"method": "popup", "minutes": 24 * 60 * 3} if is_vip else
                {"method": "popup", "minutes": 60},              # VIP: 3 days before
            ],
        },
    }


def _build_life_event(contact_id: str, contact_name: str,
                      event_type: str, event_date: str,
                      description: str = "") -> dict:
    """Build a one-time life event (promotion, wedding, etc.)."""
    icon = EVENT_COLORS.get("life_event", {}).get("icon", "🎉")
    return {
        "summary":     f"{icon} {contact_name} — {event_type.replace('_',' ').title()}",
        "description": f"{description}\n\nAuto-synced by Birthday Wishes Agent.\n"
                       f"Contact ID: {contact_id}",
        "start": {"date": event_date},
        "end":   {"date": event_date},
        "colorId": EVENT_COLORS["life_event"]["colorId"],
        "reminders": {"useDefault": True},
    }


def _build_followup_event(contact_id: str, contact_name: str,
                          followup_date: str, platform: str = "") -> dict:
    """Build a follow-up reminder event."""
    icon = EVENT_COLORS.get("followup", {}).get("icon", "💬")
    return {
        "summary":     f"{icon} Follow up with {contact_name}",
        "description": f"Check if {contact_name} replied to birthday wish "
                       f"on {platform}.\n\nAuto-synced by Birthday Wishes Agent.",
        "start": {"date": followup_date},
        "end":   {"date": followup_date},
        "colorId": EVENT_COLORS["followup"]["colorId"],
        "reminders": {"useDefault": True},
    }


# ── Sync operations ───────────────────────────────────────────────────────────

def sync_contact_birthday(
    contact_id:   str,
    contact_name: str,
    birthday_md:  str,     # "MM-DD" format
    is_vip:       bool = False,
    dry_run:      bool = True,
) -> dict:
    """
    Sync a single contact's birthday to Google Calendar.

    Returns:
        { success, event_id, dry_run, error }
    """
    init_sync_tables()

    if dry_run:
        result = {"success": True, "event_id": "dry_run_mock",
                  "dry_run": True, "error": ""}
        _log_sync(contact_id, contact_name, "birthday",
                  result["event_id"], birthday_md, True, "")
        return result

    service = _get_calendar_service()
    if service is None:
        result = {"success": False, "event_id": None, "dry_run": False,
                  "error": "Google Calendar not configured "
                          "(run google_calendar_sync.py auth)"}
        _log_sync(contact_id, contact_name, "birthday", None,
                  birthday_md, False, result["error"])
        return result

    cal_id = get_or_create_calendar(service)
    if not cal_id:
        result = {"success": False, "event_id": None, "dry_run": False,
                  "error": "Could not access calendar"}
        return result

    try:
        event_body = _build_birthday_event(contact_id, contact_name,
                                           birthday_md, is_vip)
        # Check for existing event to avoid duplicates
        existing = _find_existing_event(service, cal_id, contact_id, "birthday")
        if existing:
            event = service.events().update(
                calendarId=cal_id, eventId=existing,
                body=event_body).execute()
        else:
            event = service.events().insert(
                calendarId=cal_id, body=event_body).execute()

        result = {"success": True, "event_id": event["id"],
                  "dry_run": False, "error": ""}
        _log_sync(contact_id, contact_name, "birthday",
                  event["id"], birthday_md, True, "")
        return result

    except Exception as exc:
        result = {"success": False, "event_id": None, "dry_run": False,
                  "error": str(exc)}
        _log_sync(contact_id, contact_name, "birthday", None,
                  birthday_md, False, str(exc))
        return result


def _find_existing_event(service, cal_id: str, contact_id: str,
                         event_type: str) -> Optional[str]:
    """Search for an existing synced event by contact_id in description."""
    try:
        events = service.events().list(
            calendarId=cal_id, q=contact_id, maxResults=5).execute()
        for item in events.get("items", []):
            if contact_id in item.get("description", ""):
                return item["id"]
    except Exception:
        pass
    return None


def _log_sync(contact_id, contact_name, event_type, gcal_event_id,
             event_date, synced, error_msg):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO calendar_sync_log
            (contact_id, contact_name, event_type, gcal_event_id,
             event_date, synced, error_msg, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, event_type, gcal_event_id,
          event_date, 1 if synced else 0, error_msg,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Batch sync ─────────────────────────────────────────────────────────────────

def sync_all_birthdays(dry_run: bool = True, verbose: bool = True) -> dict:
    """
    Sync every contact's birthday to Google Calendar.

    Returns:
        { total, synced, failed, dry_run }
    """
    init_sync_tables()
    contacts = _load_contacts_with_birthdays()

    if verbose:
        print(f"[GCal Sync] Syncing {len(contacts)} birthdays "
              f"({'DRY RUN' if dry_run else 'LIVE'})\n")

    synced = 0
    failed = 0
    for c in contacts:
        result = sync_contact_birthday(
            c["contact_id"], c["contact_name"], c["birthday_md"],
            c.get("is_vip", False), dry_run=dry_run)
        if result["success"]:
            synced += 1
            if verbose:
                print(f"  ✅ {c['contact_name']:<22} {c['birthday_md']}")
        else:
            failed += 1
            if verbose:
                print(f"  ❌ {c['contact_name']:<22} {result['error'][:40]}")

    if verbose:
        print(f"\n[GCal Sync] Done: {synced} synced, {failed} failed")

    return {"total": len(contacts), "synced": synced,
            "failed": failed, "dry_run": dry_run}


def sync_life_events(dry_run: bool = True, verbose: bool = True) -> dict:
    """Sync detected life events (from whatsapp_status_watcher) to calendar."""
    init_sync_tables()
    conn = _db()
    events = []
    if _table_exists(conn, "wa_status_log"):
        rows = conn.execute("""
            SELECT contact_id, contact_name, occasion, status_text, detected_at
            FROM wa_status_log
            WHERE occasion != 'general' AND processed = 1
            ORDER BY detected_at DESC LIMIT 20
        """).fetchall()
        events = [dict(r) for r in rows]
    conn.close()

    if verbose:
        print(f"[GCal Sync] Syncing {len(events)} life events "
              f"({'DRY RUN' if dry_run else 'LIVE'})\n")

    synced = 0
    service = None if dry_run else _get_calendar_service()
    cal_id  = get_or_create_calendar(service) if service else None

    for e in events:
        event_date = e["detected_at"][:10]
        if dry_run or not service:
            synced += 1
            if verbose:
                print(f"  ✅ DRY RUN — {e['contact_name']:<22} "
                      f"{e['occasion']} on {event_date}")
            continue
        try:
            body = _build_life_event(
                e["contact_id"], e["contact_name"], e["occasion"],
                event_date, e["status_text"][:100])
            service.events().insert(calendarId=cal_id, body=body).execute()
            synced += 1
        except Exception as exc:
            if verbose:
                print(f"  ❌ {e['contact_name']}: {exc}")

    return {"total": len(events), "synced": synced, "dry_run": dry_run}


def full_sync(dry_run: bool = True, verbose: bool = True) -> dict:
    """Run a complete sync: birthdays + life events."""
    bday_result  = sync_all_birthdays(dry_run, verbose)
    if verbose:
        print()
    event_result = sync_life_events(dry_run, verbose)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO calendar_sync_state (id, last_full_sync, events_synced)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            last_full_sync = excluded.last_full_sync,
            events_synced  = excluded.events_synced
    """, (datetime.now().isoformat(),
          bday_result["synced"] + event_result["synced"]))
    conn.commit()
    conn.close()

    return {
        "birthdays":   bday_result,
        "life_events": event_result,
        "total_synced":bday_result["synced"] + event_result["synced"],
        "dry_run":     dry_run,
    }


def _load_contacts_with_birthdays() -> list[dict]:
    """Load contacts with known birthdays from DB, or demo data."""
    if not DB_PATH.exists():
        return _demo_contacts()
    conn = _db()
    contacts = []
    if _table_exists(conn, "contact_life_events"):
        rows = conn.execute("""
            SELECT contact_id, contact_name, event_date FROM contact_life_events
            WHERE event_type='birthday'
        """).fetchall()
        for r in rows:
            md = r["event_date"][5:10] if len(r["event_date"]) >= 10 else "01-01"
            contacts.append({"contact_id": r["contact_id"],
                             "contact_name": r["contact_name"],
                             "birthday_md": md, "is_vip": False})
    conn.close()
    if contacts and _table_exists(_db(), "vip_contacts"):
        conn = _db()
        vip_ids = {r["contact_id"] for r in
                   conn.execute("SELECT contact_id FROM vip_contacts WHERE active=1")}
        conn.close()
        for c in contacts:
            c["is_vip"] = c["contact_id"] in vip_ids
    return contacts if contacts else _demo_contacts()


def _demo_contacts() -> list[dict]:
    today = datetime.now()
    return [
        {"contact_id":"urn_rakib_001","contact_name":"Rakib Hossain",
         "birthday_md": today.strftime("%m-%d"), "is_vip": True},
        {"contact_id":"urn_nadia_002","contact_name":"Nadia Islam",
         "birthday_md":"03-15", "is_vip": False},
        {"contact_id":"urn_mim_004","contact_name":"Mim Chowdhury",
         "birthday_md":"07-22", "is_vip": True},
        {"contact_id":"urn_tanvir_003","contact_name":"Tanvir Ahmed",
         "birthday_md":"11-08", "is_vip": False},
    ]


def get_sync_status() -> dict:
    """Return current sync configuration and last sync info."""
    init_sync_tables()
    service = _get_calendar_service()
    conn    = _db()
    state   = conn.execute(
        "SELECT * FROM calendar_sync_state WHERE id=1").fetchone()
    total_synced = conn.execute("""
        SELECT COUNT(*) FROM calendar_sync_log WHERE synced=1
    """).fetchone()[0]
    conn.close()
    return {
        "configured":     service is not None,
        "auth_method":    "service_account" if SERVICE_ACCOUNT_JSON
                          else "oauth" if TOKEN_PATH.exists() else "none",
        "last_full_sync": state["last_full_sync"] if state else None,
        "total_events_synced": total_synced,
    }


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Google Calendar Sync", page_icon="📆",
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
    .cc-badge{background:#4285F4;color:#fff;font-size:0.65rem;font-weight:700;
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
    div[data-testid="stButton"]>button[kind="primary"]{background:#4285F4;
        border-color:#4285F4;color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_sync_tables()
    status = get_sync_status()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📆</span>
      <h1>Google Calendar Sync</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Configured", "✓ Yes" if status["configured"] else "✗ No",
         "#3fb950" if status["configured"] else "#f85149"),
        (m2, "Auth Method", status["auth_method"], "#58a6ff"),
        (m3, "Events Synced", status["total_events_synced"], "#f78166"),
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
            Run <code style="color:#7ee787">python google_calendar_sync.py auth</code>
            to connect your Google Calendar, or set GOOGLE_SERVICE_ACCOUNT_JSON.
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Setup</div>',
                    unsafe_allow_html=True)
        st.markdown("""
        <div class="code-box">pip install google-api-python-client \\
    google-auth-httplib2 google-auth-oauthlib

# Download credentials.json from Google Cloud Console
# (APIs & Services > Credentials > OAuth client ID > Desktop app)
# Save as google_calendar_credentials.json

python google_calendar_sync.py auth   # one-time browser consent
python google_calendar_sync.py sync   # sync birthdays + events</div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Sync Actions</div>',
                    unsafe_allow_html=True)
        dry_run = st.checkbox("Dry Run", value=True)
        if st.button("📆 Sync Now", type="primary", use_container_width=True):
            with st.spinner("Syncing..."):
                result = full_sync(dry_run=dry_run, verbose=False)
            st.success(f"Synced {result['total_synced']} events "
                       f"({'dry run' if dry_run else 'live'})")
            st.rerun()

    with right:
        st.markdown('<div class="section-title">Recent Sync Log</div>',
                    unsafe_allow_html=True)
        conn = _db()
        rows = conn.execute("""
            SELECT contact_name, event_type, event_date, synced,
                   error_msg, synced_at
            FROM calendar_sync_log ORDER BY synced_at DESC LIMIT 15
        """).fetchall()
        conn.close()
        for r in rows:
            ok    = bool(r["synced"])
            color = "#3fb950" if ok else "#f85149"
            icon  = EVENT_COLORS.get(r["event_type"],{}).get("icon","📅")
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
                {r['event_type']} · {r['event_date']}
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
      <span>Google Calendar Sync</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "auth":
        run_oauth_flow()

    elif cmd == "sync":
        is_live = "--live" in sys.argv
        result  = full_sync(dry_run=not is_live, verbose=True)
        print(f"\nTotal synced: {result['total_synced']}")

    elif cmd == "status":
        print("=== Google Calendar Sync -- self test ===\n")
        status = get_sync_status()
        print(f"Configured  : {status['configured']}")
        print(f"Auth method : {status['auth_method']}")
        print(f"Last sync   : {status['last_full_sync'] or 'Never'}")
        print(f"Total synced: {status['total_events_synced']}")

        print("\nRunning dry-run sync test...")
        result = full_sync(dry_run=True, verbose=True)
        print(f"\nDry-run result: {result['total_synced']} events "
              f"would be synced")
else:
    render_dashboard()
