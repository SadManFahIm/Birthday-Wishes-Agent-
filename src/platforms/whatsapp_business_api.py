"""
WhatsApp Business API -- Birthday Wishes Agent v9.0
Sends birthday wishes and follow-ups via the official WhatsApp Business API
(Meta Cloud API) -- no browser automation, no session management, no fragility.

Requires:
  WHATSAPP_PHONE_ID      -- Phone Number ID from Meta Business Manager
  WHATSAPP_ACCESS_TOKEN  -- Permanent system user token
  WHATSAPP_BUSINESS_ID   -- WhatsApp Business Account ID (optional, for stats)

Supports:
  - Text messages
  - Template messages (pre-approved by Meta)
  - Media messages (image, audio/voice note)
  - Message status webhooks (delivered / read / replied)

Integrates with: platforms/whatsapp.py (legacy fallback),
                 automation/smart_followup.py, agent.py
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path("agent_history.db")

# ── Config ────────────────────────────────────────────────────────────────────

API_BASE = "https://graph.facebook.com/v19.0"

MESSAGE_TYPES = {
    "text":     "Plain text birthday wish",
    "template": "Pre-approved Meta template",
    "image":    "Image with caption",
    "audio":    "Voice note (mp3/ogg)",
}

STATUS_MAP = {
    "sent":      {"label": "Sent",      "color": "#8b949e"},
    "delivered": {"label": "Delivered", "color": "#58a6ff"},
    "read":      {"label": "Read",      "color": "#3fb950"},
    "failed":    {"label": "Failed",    "color": "#f85149"},
    "replied":   {"label": "Replied",   "color": "#f78166"},
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_wa_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wa_message_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            phone_number    TEXT NOT NULL,
            message_type    TEXT NOT NULL,
            message_text    TEXT,
            template_name   TEXT,
            wa_message_id   TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            delivered_at    TEXT,
            read_at         TEXT,
            replied_at      TEXT,
            error_msg       TEXT,
            sent_at         TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wa_templates (
            name            TEXT PRIMARY KEY,
            language        TEXT NOT NULL DEFAULT 'en_US',
            category        TEXT NOT NULL DEFAULT 'UTILITY',
            body_text       TEXT NOT NULL,
            variables       TEXT,
            approved        INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wa_webhook_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_message_id   TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            payload_json    TEXT,
            received_at     TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── API caller ────────────────────────────────────────────────────────────────

def _get_credentials():
    return {
        "phone_id":    os.getenv("WHATSAPP_PHONE_ID", ""),
        "token":       os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
        "business_id": os.getenv("WHATSAPP_BUSINESS_ID", ""),
    }


def _post_message(payload: dict) -> dict:
    """
    POST to WhatsApp Cloud API.
    Returns API response dict or {"error": str} on failure.
    """
    creds = _get_credentials()
    if not creds["phone_id"] or not creds["token"]:
        return {"mock": True, "messages": [{"id": f"wamid.mock_{datetime.now().timestamp():.0f}"}]}

    try:
        import urllib.request
        url  = f"{API_BASE}/{creds['phone_id']}/messages"
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            url, data=data,
            headers={
                "Authorization": f"Bearer {creds['token']}",
                "Content-Type":  "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        return {"error": str(exc)}


# ── Message senders ───────────────────────────────────────────────────────────

def send_text_message(
    contact_id:   str,
    contact_name: str,
    phone_number: str,
    message_text: str,
    preview_url:  bool = False,
) -> dict:
    """
    Send a plain text birthday wish via WhatsApp Business API.

    Args:
        phone_number: E.164 format — e.g. "+8801711234567"
        message_text: The wish text (max 4096 chars)
        preview_url:  Whether to show link previews

    Returns:
        { success, wa_message_id, log_id, mock }
    """
    init_wa_tables()
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                phone_number,
        "type":              "text",
        "text": {
            "preview_url": preview_url,
            "body":        message_text[:4096],
        },
    }
    response   = _post_message(payload)
    is_mock    = response.get("mock", False)
    wa_msg_id  = None
    success    = False
    error_msg  = ""

    if "messages" in response:
        wa_msg_id = response["messages"][0].get("id")
        success   = True
    elif "error" in response:
        error_msg = str(response["error"])[:300]

    log_id = _log_message(contact_id, contact_name, phone_number,
                          "text", message_text, None, wa_msg_id,
                          "sent" if success else "failed", error_msg)

    return {"success": success, "wa_message_id": wa_msg_id,
            "log_id": log_id, "mock": is_mock, "error": error_msg}


def send_template_message(
    contact_id:    str,
    contact_name:  str,
    phone_number:  str,
    template_name: str,
    variables:     Optional[list] = None,
    language:      str = "en_US",
) -> dict:
    """
    Send a pre-approved WhatsApp template message.
    Templates must be approved by Meta before use.

    Args:
        template_name: Approved template name (e.g. "birthday_wish_v1")
        variables:     List of variable values for {{1}}, {{2}}, etc.
        language:      Language code (en_US, bn, etc.)
    """
    init_wa_tables()
    components = []
    if variables:
        params = [{"type": "text", "text": str(v)} for v in variables]
        components = [{"type": "body", "parameters": params}]

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                phone_number,
        "type":              "template",
        "template": {
            "name":       template_name,
            "language":   {"code": language},
            "components": components,
        },
    }
    response  = _post_message(payload)
    is_mock   = response.get("mock", False)
    wa_msg_id = None
    success   = False
    error_msg = ""

    if "messages" in response:
        wa_msg_id = response["messages"][0].get("id")
        success   = True
    elif "error" in response:
        error_msg = str(response["error"])[:300]

    log_id = _log_message(contact_id, contact_name, phone_number,
                          "template", None, template_name, wa_msg_id,
                          "sent" if success else "failed", error_msg)

    return {"success": success, "wa_message_id": wa_msg_id,
            "log_id": log_id, "mock": is_mock, "error": error_msg}


def send_audio_message(
    contact_id:   str,
    contact_name: str,
    phone_number: str,
    audio_url:    str,
) -> dict:
    """
    Send a voice note (audio file hosted at audio_url).
    Supported formats: mp3, ogg, m4a, aac.
    """
    init_wa_tables()
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                phone_number,
        "type":              "audio",
        "audio":             {"link": audio_url},
    }
    response  = _post_message(payload)
    is_mock   = response.get("mock", False)
    wa_msg_id = None
    success   = False
    error_msg = ""

    if "messages" in response:
        wa_msg_id = response["messages"][0].get("id")
        success   = True
    elif "error" in response:
        error_msg = str(response["error"])[:300]

    log_id = _log_message(contact_id, contact_name, phone_number,
                          "audio", f"[voice note: {audio_url}]", None,
                          wa_msg_id, "sent" if success else "failed", error_msg)

    return {"success": success, "wa_message_id": wa_msg_id,
            "log_id": log_id, "mock": is_mock, "error": error_msg}


# ── Webhook handler ───────────────────────────────────────────────────────────

def handle_webhook(payload: dict) -> list[dict]:
    """
    Process incoming WhatsApp webhook events.
    Wire this to your FastAPI/Flask webhook endpoint.

    Updates message status (delivered/read) and logs replies.
    Returns list of processed events.

    Usage in FastAPI:
        @app.post("/webhook/whatsapp")
        async def whatsapp_webhook(request: Request):
            body = await request.json()
            events = handle_webhook(body)
            return {"status": "ok"}
    """
    init_wa_tables()
    processed = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            # Status updates
            for status in value.get("statuses", []):
                wa_id  = status.get("id")
                etype  = status.get("status")
                ts     = datetime.now().isoformat()
                _update_message_status(wa_id, etype, ts)
                _log_webhook_event(wa_id, etype, status)
                processed.append({"type": "status", "wa_id": wa_id, "status": etype})

            # Incoming messages (replies)
            for msg in value.get("messages", []):
                wa_id  = msg.get("id")
                sender = msg.get("from")
                mtype  = msg.get("type")
                text   = ""
                if mtype == "text":
                    text = msg.get("text", {}).get("body", "")
                _log_webhook_event(wa_id, "reply", msg)
                _mark_replied(sender)
                processed.append({"type": "reply", "from": sender, "text": text})

    return processed


def _update_message_status(wa_message_id: str, status: str, ts: str):
    conn = sqlite3.connect(DB_PATH)
    if status == "delivered":
        conn.execute(
            "UPDATE wa_message_log SET status='delivered', delivered_at=? WHERE wa_message_id=?",
            (ts, wa_message_id))
    elif status == "read":
        conn.execute(
            "UPDATE wa_message_log SET status='read', read_at=? WHERE wa_message_id=?",
            (ts, wa_message_id))
    elif status == "failed":
        conn.execute(
            "UPDATE wa_message_log SET status='failed' WHERE wa_message_id=?",
            (wa_message_id,))
    conn.commit()
    conn.close()


def _mark_replied(phone_number: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE wa_message_log SET status='replied', replied_at=?
        WHERE phone_number=? AND status IN ('sent','delivered','read')
        ORDER BY sent_at DESC LIMIT 1
    """, (datetime.now().isoformat(), phone_number))
    conn.commit()
    conn.close()


def _log_webhook_event(wa_message_id: str, event_type: str, payload: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO wa_webhook_events
            (wa_message_id, event_type, payload_json, received_at)
        VALUES (?, ?, ?, ?)
    """, (wa_message_id, event_type, json.dumps(payload), datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Template management ────────────────────────────────────────────────────────

def register_template(
    name:      str,
    body_text: str,
    language:  str = "en_US",
    category:  str = "UTILITY",
    variables: Optional[list] = None,
) -> None:
    """
    Save a template definition locally. Templates must still be
    submitted to Meta Business Manager for approval before use.
    """
    init_wa_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO wa_templates (name, language, category, body_text, variables, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            body_text  = excluded.body_text,
            variables  = excluded.variables
    """, (name, language, category, body_text,
          json.dumps(variables or []), datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_templates() -> list[dict]:
    init_wa_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT name, language, category, body_text, approved FROM wa_templates"
    ).fetchall()
    conn.close()
    return [{"name": r[0], "language": r[1], "category": r[2],
             "body_text": r[3], "approved": bool(r[4])} for r in rows]


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_delivery_stats(days: int = 30) -> dict:
    """Return delivery and read rates for the last N days."""
    init_wa_tables()
    cutoff = (datetime.now() - __import__("datetime").timedelta(days=days)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    rows   = conn.execute("""
        SELECT status, COUNT(*) FROM wa_message_log
        WHERE sent_at >= ? GROUP BY status
    """, (cutoff,)).fetchall()
    conn.close()
    stats  = {r[0]: r[1] for r in rows}
    total  = sum(stats.values())
    return {
        "total":          total,
        "sent":           stats.get("sent", 0),
        "delivered":      stats.get("delivered", 0),
        "read":           stats.get("read", 0),
        "replied":        stats.get("replied", 0),
        "failed":         stats.get("failed", 0),
        "delivery_rate":  round(stats.get("delivered", 0) / total, 2) if total else 0,
        "read_rate":      round(stats.get("read", 0) / total, 2) if total else 0,
        "reply_rate":     round(stats.get("replied", 0) / total, 2) if total else 0,
    }


def get_message_log(limit: int = 20) -> list[dict]:
    init_wa_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_name, phone_number, message_type, message_text,
               status, sent_at, delivered_at, read_at, replied_at
        FROM wa_message_log ORDER BY sent_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{
        "contact_name":  r[0], "phone":        r[1],
        "message_type":  r[2], "message_text": (r[3] or "")[:80],
        "status":        r[4], "sent_at":      r[5],
        "delivered_at":  r[6], "read_at":      r[7], "replied_at": r[8],
    } for r in rows]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _log_message(contact_id, contact_name, phone, mtype,
                 text, template, wa_id, status, error):
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute("""
        INSERT INTO wa_message_log
            (contact_id, contact_name, phone_number, message_type,
             message_text, template_name, wa_message_id, status, error_msg, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, phone, mtype,
          text, template, wa_id, status, error, datetime.now().isoformat()))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()
    return log_id


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_wa_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM wa_message_log").fetchone()[0]
    conn.close()
    if count > 0:
        return

    register_template(
        "birthday_wish_v1",
        "Happy Birthday {{1}}! Wishing you a fantastic day. {{2}}",
        variables=["contact_name", "wish_text"],
    )
    register_template(
        "followup_v1",
        "Hey {{1}}, just following up on my birthday wish! Hope you're doing well.",
        variables=["contact_name"],
    )
    demo = [
        ("urn_rakib_001","Rakib Hossain","+8801711111111","text",
         "Happy Birthday Rakib! Hope Pathao is treating you well. 🎉","sent"),
        ("urn_nadia_002","Nadia Islam","+8801722222222","template",
         None,"delivered"),
        ("urn_mim_004","Mim Chowdhury","+8801733333333","text",
         "Happy Birthday Mim!! 🥳","replied"),
    ]
    for cid, cname, phone, mtype, text, status in demo:
        _log_message(cid, cname, phone, mtype, text,
                     "birthday_wish_v1" if mtype == "template" else None,
                     f"wamid.demo_{cid}", status, "")


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="WhatsApp Business API", page_icon="💬",
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
    .msg-row{background:var(--surface);border:1px solid var(--border);
             border-radius:8px;padding:10px 14px;margin-bottom:6px;}
    .status-pill{display:inline-flex;font-size:0.62rem;font-weight:700;
                 padding:2px 7px;border-radius:20px;text-transform:uppercase;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.6rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:#3fb950;
        border-color:#3fb950;color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_wa_tables()
    _seed_demo()

    creds  = _get_credentials()
    has_creds = bool(creds["phone_id"] and creds["token"])

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">💬</span>
      <h1>WhatsApp Business API</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    # Credentials status
    if has_creds:
        st.markdown("""
        <div style="background:#051a09;border-left:4px solid #3fb950;
                    border-radius:8px;padding:10px 16px;margin-bottom:14px;">
          <span style="color:#3fb950;font-weight:700">API Configured</span>
          <span style="font-size:0.78rem;color:#c9d1d9;margin-left:8px">
            Messages will be sent via WhatsApp Business Cloud API</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:#1a1500;border-left:4px solid #d29922;
                    border-radius:8px;padding:10px 16px;margin-bottom:14px;">
          <span style="color:#d29922;font-weight:700">Mock Mode</span>
          <span style="font-size:0.78rem;color:#c9d1d9;margin-left:8px">
            Set WHATSAPP_PHONE_ID and WHATSAPP_ACCESS_TOKEN to go live</span>
        </div>
        """, unsafe_allow_html=True)

    stats = get_delivery_stats(30)
    m1, m2, m3, m4, m5 = st.columns(5)
    for col, lbl, val, color in [
        (m1, "Total Sent",     stats["total"],                      "#e6edf3"),
        (m2, "Delivered",      f"{stats['delivery_rate']:.0%}",     "#58a6ff"),
        (m3, "Read",           f"{stats['read_rate']:.0%}",         "#3fb950"),
        (m4, "Replied",        f"{stats['reply_rate']:.0%}",        "#f78166"),
        (m5, "Failed",         stats["failed"],                     "#f85149"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Send Message</div>',
                    unsafe_allow_html=True)
        msg_type = st.selectbox("Type", ["text","template","audio"],
                                label_visibility="collapsed", key="mt")
        phone    = st.text_input("Phone (E.164)", placeholder="+8801711234567",
                                 label_visibility="collapsed", key="ph")
        cname    = st.text_input("Contact name", placeholder="Rakib Hossain",
                                 label_visibility="collapsed", key="cn")

        if msg_type == "text":
            body = st.text_area("Message", height=100,
                                label_visibility="collapsed", key="mb",
                                placeholder="Happy Birthday! ...")
            if st.button("Send via API", type="primary", use_container_width=True):
                if phone and cname and body:
                    r = send_text_message(
                        "manual_001", cname, phone, body)
                    if r["success"]:
                        mode = "Mock" if r["mock"] else "Live"
                        st.success(f"Sent ({mode}) — ID: {r['wa_message_id']}")
                    else:
                        st.error(f"Failed: {r['error']}")
                    st.rerun()

        elif msg_type == "template":
            templates = get_templates()
            tnames    = [t["name"] for t in templates]
            sel_t     = st.selectbox("Template", tnames if tnames else ["(no templates)"],
                                     label_visibility="collapsed", key="tsel")
            vars_inp  = st.text_input("Variables (comma-separated)",
                                      label_visibility="collapsed", key="tv",
                                      placeholder="Rakib, Wishing you the best!")
            if st.button("Send Template", type="primary", use_container_width=True):
                if phone and cname:
                    variables = [v.strip() for v in vars_inp.split(",") if v.strip()]
                    r = send_template_message(
                        "manual_001", cname, phone, sel_t, variables)
                    st.success(f"Sent — ID: {r['wa_message_id']}" if r["success"]
                               else f"Failed: {r['error']}")
                    st.rerun()

        else:
            audio_url = st.text_input("Audio URL", label_visibility="collapsed",
                                      key="au", placeholder="https://...")
            if st.button("Send Voice Note", type="primary", use_container_width=True):
                if phone and cname and audio_url:
                    r = send_audio_message("manual_001", cname, phone, audio_url)
                    st.success(f"Sent — ID: {r['wa_message_id']}" if r["success"]
                               else f"Failed: {r['error']}")
                    st.rerun()

        # Templates
        st.markdown('<div class="section-title">Registered Templates</div>',
                    unsafe_allow_html=True)
        for t in get_templates():
            approved_tag = (
                '<span style="color:#3fb950;font-size:0.65rem">Approved</span>'
                if t["approved"] else
                '<span style="color:#d29922;font-size:0.65rem">Pending approval</span>'
            )
            st.markdown(f"""
            <div class="msg-row">
              <div style="font-weight:700;font-size:0.84rem;display:flex;
                          align-items:center;gap:8px">
                {t['name']} {approved_tag}
              </div>
              <div style="font-size:0.72rem;color:#c9d1d9;margin-top:4px">
                {t['body_text']}
              </div>
            </div>
            """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Message Log</div>',
                    unsafe_allow_html=True)
        for msg in get_message_log(limit=15):
            sm   = STATUS_MAP.get(msg["status"], STATUS_MAP["sent"])
            ts   = (msg["sent_at"] or "")[:16].replace("T", " ")
            st.markdown(f"""
            <div class="msg-row">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <div style="font-weight:700;font-size:0.83rem">{msg['contact_name']}</div>
                <span class="status-pill"
                      style="background:{sm['color']}22;color:{sm['color']};
                             border:1px solid {sm['color']}55">
                  {sm['label']}
                </span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:2px">
                {msg['phone']} · {msg['message_type']} · {ts}
              </div>
              {f'<div style="font-size:0.75rem;color:#c9d1d9;margin-top:4px">{msg["message_text"]}</div>' if msg["message_text"] else ''}
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>WhatsApp Business API</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_wa_tables()
    _seed_demo()
    print("=== WhatsApp Business API -- self test ===\n")

    r1 = send_text_message(
        "urn_test_001","Test Contact","+8801700000000",
        "Happy Birthday! Hope you have a great day.")
    print(f"Text  : success={r1['success']} mock={r1['mock']} id={r1['wa_message_id']}")

    r2 = send_template_message(
        "urn_test_002","Test Contact 2","+8801700000001",
        "birthday_wish_v1", ["Test","Wishing you the best!"])
    print(f"Tmpl  : success={r2['success']} mock={r2['mock']} id={r2['wa_message_id']}")

    stats = get_delivery_stats(30)
    print(f"\nStats : total={stats['total']} "
          f"delivered={stats['delivery_rate']:.0%} "
          f"replied={stats['reply_rate']:.0%}")
else:
    render_dashboard()
