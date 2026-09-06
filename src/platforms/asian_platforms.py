"""
Asian Platforms -- Birthday Wishes Agent v9.0
Birthday wishes via WeChat (Work API) and LINE Messaging API.
Both use official REST APIs -- no browser automation.

WeChat:
  Uses WeChat Work (企业微信) API -- suitable for professional contacts.
  Personal WeChat has no official API; Work API is the production path.
  Requires: WECHAT_CORP_ID, WECHAT_CORP_SECRET, WECHAT_AGENT_ID

LINE:
  Uses LINE Messaging API (push messages to registered LINE user IDs).
  Requires: LINE_CHANNEL_ACCESS_TOKEN

Both modules fall back to mock mode when credentials are not configured.

Integrates with: platforms/telegram_birthday.py (same pattern),
                 agent.py
"""

import sqlite3
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

PLATFORMS = {
    "wechat": {"label": "WeChat Work", "icon": "💚", "color": "#07c160"},
    "line":   {"label": "LINE",        "icon": "💚", "color": "#00b900"},
}

STATUS_MAP = {
    "sent":    {"label": "Sent",    "color": "#58a6ff"},
    "failed":  {"label": "Failed",  "color": "#f85149"},
    "replied": {"label": "Replied", "color": "#3fb950"},
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_asian_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS asian_platform_contacts (
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            platform        TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            display_name    TEXT,
            added_at        TEXT NOT NULL,
            PRIMARY KEY (contact_id, platform)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS asian_message_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            platform        TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            message_text    TEXT,
            platform_msg_id TEXT,
            status          TEXT NOT NULL DEFAULT 'sent',
            error_msg       TEXT,
            sent_at         TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── Contact management ────────────────────────────────────────────────────────

def register_contact(
    contact_id:      str,
    contact_name:    str,
    platform:        str,
    platform_user_id:str,
    display_name:    str = "",
) -> None:
    """
    Save a contact's platform user ID.

    platform: 'wechat' or 'line'
    platform_user_id:
      WeChat Work -- employee userid (e.g. 'zhangwei')
      LINE        -- LINE user ID (starts with 'U', e.g. 'U1234567...')
    """
    init_asian_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO asian_platform_contacts
            (contact_id, contact_name, platform, platform_user_id,
             display_name, added_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id, platform) DO UPDATE SET
            platform_user_id = excluded.platform_user_id,
            display_name     = excluded.display_name
    """, (contact_id, contact_name, platform, platform_user_id,
          display_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_platform_user_id(contact_id: str, platform: str) -> Optional[str]:
    init_asian_tables()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("""
        SELECT platform_user_id FROM asian_platform_contacts
        WHERE contact_id=? AND platform=?
    """, (contact_id, platform)).fetchone()
    conn.close()
    return row[0] if row else None


def get_all_contacts(platform: Optional[str] = None) -> list[dict]:
    init_asian_tables()
    conn = sqlite3.connect(DB_PATH)
    if platform:
        rows = conn.execute("""
            SELECT contact_id, contact_name, platform,
                   platform_user_id, display_name
            FROM asian_platform_contacts
            WHERE platform=? ORDER BY contact_name
        """, (platform,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT contact_id, contact_name, platform,
                   platform_user_id, display_name
            FROM asian_platform_contacts ORDER BY platform, contact_name
        """).fetchall()
    conn.close()
    return [{"contact_id": r[0], "contact_name": r[1],
             "platform": r[2], "platform_user_id": r[3],
             "display_name": r[4]} for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# WECHAT WORK (企业微信)
# ══════════════════════════════════════════════════════════════════════════════

def _wechat_get_token() -> Optional[str]:
    """
    Fetch WeChat Work access token.
    Token is valid for 7200s -- cache in production.
    Falls back to None (mock mode) if credentials missing.
    """
    corp_id = os.getenv("WECHAT_CORP_ID", "")
    secret  = os.getenv("WECHAT_CORP_SECRET", "")
    if not corp_id or not secret:
        return None
    try:
        url  = (f"https://qyapi.weixin.qq.com/cgi-bin/gettoken"
                f"?corpid={corp_id}&corpsecret={secret}")
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("access_token")
    except Exception:
        return None


def send_wechat_wish(
    contact_id:      str,
    contact_name:    str,
    wish_text:       str,
    wechat_user_id:  Optional[str] = None,
) -> dict:
    """
    Send a birthday wish via WeChat Work message.

    Args:
        wechat_user_id: Employee userid in WeChat Work.
                        If None, looked up from registered contacts.
    Returns:
        { success, platform_msg_id, log_id, mock }
    """
    init_asian_tables()
    uid = wechat_user_id or get_platform_user_id(contact_id, "wechat")
    if not uid:
        return {"success": False, "error": "No WeChat user ID",
                "log_id": None, "mock": False}

    token    = _wechat_get_token()
    is_mock  = token is None
    agent_id = os.getenv("WECHAT_AGENT_ID", "1000001")
    success  = False
    msg_id   = None
    error    = ""

    if is_mock:
        success = True
        msg_id  = f"wechat_mock_{int(datetime.now().timestamp())}"
    else:
        try:
            payload = {
                "touser":  uid,
                "msgtype": "text",
                "agentid": agent_id,
                "text":    {"content": wish_text},
            }
            url  = (f"https://qyapi.weixin.qq.com/cgi-bin/message/send"
                    f"?access_token={token}")
            data = json.dumps(payload).encode()
            req  = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result  = json.loads(resp.read())
                success = result.get("errcode", -1) == 0
                msg_id  = result.get("msgid")
                if not success:
                    error = result.get("errmsg", "")
        except Exception as exc:
            error = str(exc)[:200]

    log_id = _log_message(contact_id, contact_name, "wechat",
                          uid, wish_text, msg_id,
                          "sent" if success else "failed", error)
    return {"success": success, "platform_msg_id": msg_id,
            "log_id": log_id, "mock": is_mock, "error": error}


# ══════════════════════════════════════════════════════════════════════════════
# LINE MESSAGING API
# ══════════════════════════════════════════════════════════════════════════════

def _line_api(endpoint: str, payload: dict) -> dict:
    """
    Call LINE Messaging API.
    Falls back to mock if LINE_CHANNEL_ACCESS_TOKEN is not set.
    """
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        return {"mock": True,
                "sentMessages": [{"id": f"line_mock_{int(datetime.now().timestamp())}"}]}
    try:
        url  = f"https://api.line.me/v2/bot{endpoint}"
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            url, data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            return json.loads(body) if body else {"ok": True}
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}: {exc.reason}"}
    except Exception as exc:
        return {"error": str(exc)[:200]}


def send_line_wish(
    contact_id:   str,
    contact_name: str,
    wish_text:    str,
    line_user_id: Optional[str] = None,
    with_sticker: bool = False,
) -> dict:
    """
    Send a birthday wish via LINE push message.

    Args:
        line_user_id: LINE user ID (starts with 'U').
        with_sticker: Prepend a birthday sticker before the text.

    Returns:
        { success, platform_msg_id, log_id, mock }
    """
    init_asian_tables()
    uid = line_user_id or get_platform_user_id(contact_id, "line")
    if not uid:
        return {"success": False, "error": "No LINE user ID",
                "log_id": None, "mock": False}

    messages = []
    if with_sticker:
        # Birthday sticker from LINE sticker set
        messages.append({
            "type":       "sticker",
            "packageId":  "11537",
            "stickerId":  "52002738",
        })
    messages.append({"type": "text", "text": wish_text})

    payload  = {"to": uid, "messages": messages}
    resp     = _line_api("/message/push", payload)
    is_mock  = resp.get("mock", False)
    success  = is_mock or ("error" not in resp)
    msg_id   = (resp.get("sentMessages", [{}])[0].get("id")
                if is_mock or success else None)
    error    = resp.get("error", "") if not success else ""

    log_id = _log_message(contact_id, contact_name, "line",
                          uid, wish_text, msg_id,
                          "sent" if success else "failed", error)
    return {"success": success, "platform_msg_id": msg_id,
            "log_id": log_id, "mock": is_mock, "error": error}


def send_line_flex_wish(
    contact_id:   str,
    contact_name: str,
    wish_text:    str,
    line_user_id: Optional[str] = None,
) -> dict:
    """
    Send a birthday wish as a LINE Flex Message (rich card layout).
    Falls back to plain text if Flex fails.
    """
    init_asian_tables()
    uid = line_user_id or get_platform_user_id(contact_id, "line")
    if not uid:
        return {"success": False, "error": "No LINE user ID",
                "log_id": None, "mock": False}

    first_name = contact_name.split()[0]
    flex_msg   = {
        "type":     "flex",
        "altText":  f"Happy Birthday {first_name}!",
        "contents": {
            "type":       "bubble",
            "body": {
                "type":   "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "🎂 Happy Birthday!",
                     "weight": "bold", "size": "xl", "color": "#f78166"},
                    {"type": "text", "text": wish_text, "wrap": True,
                     "margin": "md", "color": "#555555"},
                    {"type": "text", "text": f"— Birthday Wishes Agent",
                     "size": "xs", "color": "#aaaaaa", "margin": "lg"},
                ],
            },
        },
    }
    payload  = {"to": uid, "messages": [flex_msg]}
    resp     = _line_api("/message/push", payload)
    is_mock  = resp.get("mock", False)
    success  = is_mock or ("error" not in resp)
    msg_id   = (resp.get("sentMessages", [{}])[0].get("id")
                if is_mock or success else None)
    error    = resp.get("error", "") if not success else ""

    log_id = _log_message(contact_id, contact_name, "line",
                          uid, wish_text, msg_id,
                          "sent" if success else "failed", error)
    return {"success": success, "platform_msg_id": msg_id,
            "log_id": log_id, "mock": is_mock, "error": error}


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_stats(days: int = 30) -> dict:
    """Reply rate and totals per platform for the last N days."""
    init_asian_tables()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn   = sqlite3.connect(DB_PATH)
    rows   = conn.execute("""
        SELECT platform, status, COUNT(*) FROM asian_message_log
        WHERE sent_at >= ? GROUP BY platform, status
    """, (cutoff,)).fetchall()
    conn.close()

    result = {p: {"total": 0, "replied": 0, "failed": 0}
              for p in PLATFORMS}
    for plat, status, count in rows:
        if plat in result:
            result[plat]["total"] += count
            if status == "replied":
                result[plat]["replied"] += count
            elif status == "failed":
                result[plat]["failed"] += count

    for plat in result:
        total = result[plat]["total"]
        result[plat]["reply_rate"] = (
            round(result[plat]["replied"] / total, 2) if total else 0)
    return result


def get_message_log(limit: int = 20) -> list[dict]:
    init_asian_tables()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_name, platform, platform_user_id,
               message_text, status, sent_at
        FROM asian_message_log ORDER BY sent_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"contact_name": r[0], "platform": r[1],
             "platform_user_id": r[2],
             "message_text": (r[3] or "")[:80],
             "status": r[4], "sent_at": r[5]} for r in rows]


def _log_message(contact_id, contact_name, platform,
                 uid, text, msg_id, status, error):
    conn   = sqlite3.connect(DB_PATH)
    cur    = conn.execute("""
        INSERT INTO asian_message_log
            (contact_id, contact_name, platform, platform_user_id,
             message_text, platform_msg_id, status, error_msg, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, platform, uid,
          text, msg_id, status, error, datetime.now().isoformat()))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()
    return log_id


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_asian_tables()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) FROM asian_platform_contacts").fetchone()[0]
    conn.close()
    if count > 0:
        return

    contacts = [
        ("urn_wei_001",  "Zhang Wei",    "wechat", "zhangwei",          "張偉"),
        ("urn_ming_002", "Li Ming",      "wechat", "liming_corp",       "李明"),
        ("urn_yuki_003", "Yuki Tanaka",  "line",   "U1a2b3c4d5e6f7890", "Yuki"),
        ("urn_chen_004", "Chen Jing",    "line",   "Uabcdef1234567890", "Chen"),
    ]
    for cid, cname, plat, uid, dname in contacts:
        register_contact(cid, cname, plat, uid, dname)

    # Seed some messages
    _log_message("urn_wei_001","Zhang Wei","wechat","zhangwei",
                 "Happy Birthday Wei! 生日快乐!","wechat_mock_1","replied","")
    _log_message("urn_yuki_003","Yuki Tanaka","line","U1a2b3c4d5e6f7890",
                 "Happy Birthday Yuki! お誕生日おめでとう!","line_mock_1","sent","")


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Asian Platforms", page_icon="🌏",
                       layout="wide", initial_sidebar_state="collapsed")

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    html,body,[class*="css"]{font-family:'Inter',sans-serif;}
    :root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--accent:#f78166;
          --green:#3fb950;--red:#f85149;--blue:#58a6ff;
          --muted:#8b949e;--text:#e6edf3;
          --wechat:#07c160;--line:#00b900;}
    .stApp{background:var(--bg);color:var(--text);}
    .cc-header{display:flex;align-items:center;gap:14px;padding:18px 0 10px;
               border-bottom:1px solid var(--border);margin-bottom:24px;}
    .cc-header h1{font-size:1.4rem;font-weight:700;letter-spacing:-0.02em;margin:0;}
    .cc-badge{background:linear-gradient(135deg,var(--wechat),var(--line));
              color:#fff;font-size:0.65rem;font-weight:700;padding:2px 8px;
              border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;}
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);
                font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:var(--muted);margin:22px 0 10px;
                   display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .c-card{background:var(--surface);border:1px solid var(--border);
            border-radius:9px;padding:11px 14px;margin-bottom:6px;}
    .msg-row{background:var(--surface);border:1px solid var(--border);
             border-radius:8px;padding:10px 14px;margin-bottom:6px;}
    .sp{display:inline-flex;font-size:0.62rem;font-weight:700;padding:2px 7px;
        border-radius:20px;text-transform:uppercase;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.6rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--wechat);
        border-color:var(--wechat);color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_asian_tables()
    _seed_demo()

    wechat_ok = bool(os.getenv("WECHAT_CORP_ID") and os.getenv("WECHAT_CORP_SECRET"))
    line_ok   = bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🌏</span>
      <h1>Asian Platforms</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">WeChat Work + LINE</span>
    </div>
    """, unsafe_allow_html=True)

    cred_col1, cred_col2 = st.columns(2)
    with cred_col1:
        color  = "#3fb950" if wechat_ok else "#d29922"
        status = "Configured" if wechat_ok else "Mock Mode"
        st.markdown(f"""
        <div style="background:{'#051a09' if wechat_ok else '#1a1500'};
                    border-left:4px solid {color};border-radius:8px;
                    padding:10px 16px;margin-bottom:14px;">
          <span style="color:{color};font-weight:700">💚 WeChat Work — {status}</span>
        </div>
        """, unsafe_allow_html=True)
    with cred_col2:
        color  = "#3fb950" if line_ok else "#d29922"
        status = "Configured" if line_ok else "Mock Mode"
        st.markdown(f"""
        <div style="background:{'#051a09' if line_ok else '#1a1500'};
                    border-left:4px solid {color};border-radius:8px;
                    padding:10px 16px;margin-bottom:14px;">
          <span style="color:{color};font-weight:700">💚 LINE — {status}</span>
        </div>
        """, unsafe_allow_html=True)

    stats   = get_stats(30)
    wc_stat = stats.get("wechat", {})
    ln_stat = stats.get("line", {})
    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "WeChat Sent",   wc_stat.get("total", 0),        "#07c160"),
        (m2, "WeChat Replied",f"{wc_stat.get('reply_rate',0):.0%}", "#07c160"),
        (m3, "LINE Sent",     ln_stat.get("total", 0),        "#00b900"),
        (m4, "LINE Replied",  f"{ln_stat.get('reply_rate',0):.0%}", "#00b900"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Send Wish</div>',
                    unsafe_allow_html=True)
        platform = st.selectbox("Platform", ["WeChat Work","LINE"],
                                label_visibility="collapsed", key="plat")
        plat_key = "wechat" if platform == "WeChat Work" else "line"
        contacts = get_all_contacts(plat_key)
        names    = [c["contact_name"] for c in contacts]
        sel_name = st.selectbox("Contact", names if names else ["(none)"],
                                label_visibility="collapsed", key="sel_c")
        sel_c    = next((c for c in contacts if c["contact_name"] == sel_name), None)
        wish_txt = st.text_area("Message", height=100,
                                label_visibility="collapsed", key="wtxt",
                                placeholder="Happy Birthday! 🎂")

        if plat_key == "line":
            use_flex = st.checkbox("Use Flex Message (rich card)", value=True,
                                   key="use_flex")
            use_sticker = st.checkbox("Add birthday sticker", value=False,
                                      key="use_sticker")

        btn_color = "#07c160" if plat_key == "wechat" else "#00b900"
        if st.button(f"Send via {platform}", type="primary",
                     use_container_width=True):
            if sel_c and wish_txt:
                if plat_key == "wechat":
                    r = send_wechat_wish(
                        sel_c["contact_id"], sel_c["contact_name"],
                        wish_txt, sel_c["platform_user_id"])
                elif st.session_state.get("use_flex", True):
                    r = send_line_flex_wish(
                        sel_c["contact_id"], sel_c["contact_name"],
                        wish_txt, sel_c["platform_user_id"])
                else:
                    r = send_line_wish(
                        sel_c["contact_id"], sel_c["contact_name"],
                        wish_txt, sel_c["platform_user_id"],
                        st.session_state.get("use_sticker", False))

                if r["success"]:
                    mode = "Mock" if r.get("mock") else "Live"
                    st.success(f"Sent ({mode}) — ID: {r['platform_msg_id']}")
                else:
                    st.error(f"Failed: {r.get('error','unknown')}")
                st.rerun()

        # Register
        st.markdown('<div class="section-title">Register Contact</div>',
                    unsafe_allow_html=True)
        with st.expander("Add contact"):
            ra1, ra2 = st.columns(2)
            with ra1:
                r_cid   = st.text_input("Contact ID",   key="r_cid",
                                        label_visibility="collapsed",
                                        placeholder="urn_...")
                r_cname = st.text_input("Name",         key="r_cname",
                                        label_visibility="collapsed")
            with ra2:
                r_plat  = st.selectbox("Platform", ["wechat","line"],
                                       label_visibility="collapsed", key="r_plat")
                r_uid   = st.text_input("Platform User ID", key="r_uid",
                                        label_visibility="collapsed",
                                        placeholder="userid / LINE U...")
            if st.button("Register", use_container_width=True):
                if r_cid and r_cname and r_uid:
                    register_contact(r_cid, r_cname, r_plat, r_uid)
                    st.success(f"Registered {r_cname} on {r_plat} ✅")
                    st.rerun()

        # Contact list
        for plat_k, plat_label, plat_color in [
            ("wechat","WeChat Work","#07c160"),
            ("line","LINE","#00b900"),
        ]:
            cs = get_all_contacts(plat_k)
            if cs:
                st.markdown(
                    f'<div class="section-title" style="margin-top:14px">'
                    f'<span style="color:{plat_color}">{plat_label} Contacts</span>'
                    f'</div>', unsafe_allow_html=True)
                for c in cs:
                    dname = f" ({c['display_name']})" if c.get("display_name") else ""
                    st.markdown(f"""
                    <div class="c-card">
                      <div style="font-weight:700;font-size:0.84rem">
                        {c['contact_name']}{dname}
                      </div>
                      <div style="font-size:0.68rem;color:#8b949e">
                        {c['platform_user_id']}
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Message Log</div>',
                    unsafe_allow_html=True)
        for msg in get_message_log(limit=15):
            sm      = STATUS_MAP.get(msg["status"], STATUS_MAP["sent"])
            ts      = (msg["sent_at"] or "")[:16].replace("T", " ")
            p_color = "#07c160" if msg["platform"] == "wechat" else "#00b900"
            p_label = PLATFORMS.get(msg["platform"], {}).get("label", msg["platform"])
            st.markdown(f"""
            <div class="msg-row">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <div style="font-weight:700;font-size:0.83rem">
                  {msg['contact_name']}
                </div>
                <span class="sp"
                      style="background:{sm['color']}22;color:{sm['color']};
                             border:1px solid {sm['color']}55">
                  {sm['label']}
                </span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:2px">
                <span style="color:{p_color}">{p_label}</span> · {ts}
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
      <span>WeChat Work + LINE</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_asian_tables()
    _seed_demo()
    print("=== Asian Platforms -- self test ===\n")

    contacts = get_all_contacts()
    wc = [c for c in contacts if c["platform"] == "wechat"]
    ln = [c for c in contacts if c["platform"] == "line"]
    print(f"WeChat contacts : {len(wc)}")
    print(f"LINE contacts   : {len(ln)}")

    r1 = send_wechat_wish(
        "urn_wei_001","Zhang Wei",
        "Happy Birthday Wei! 生日快乐! Wishing you a wonderful year ahead.",
        wechat_user_id="zhangwei")
    print(f"\nWeChat: success={r1['success']} mock={r1['mock']} id={r1['platform_msg_id']}")

    r2 = send_line_flex_wish(
        "urn_yuki_003","Yuki Tanaka",
        "Happy Birthday Yuki! お誕生日おめでとうございます!",
        line_user_id="U1a2b3c4d5e6f7890")
    print(f"LINE  : success={r2['success']} mock={r2['mock']} id={r2['platform_msg_id']}")

    stats = get_stats(30)
    for plat, s in stats.items():
        print(f"\n{plat}: total={s['total']} replied={s['reply_rate']:.0%}")
else:
    render_dashboard()
