"""
Email Outreach -- Birthday Wishes Agent v10.0
Sends professional branded birthday emails via Gmail API or SMTP.
Includes HTML-rendered templates with dynamic personalization.

Auth options:
  gmail_api  -- OAuth2 via Gmail API (recommended, no app password needed)
  smtp       -- SMTP with Gmail app password (simpler setup)

Templates:
  warm       -- casual, friendly tone with emoji accents
  formal     -- professional, clean corporate style
  minimal    -- short and sweet, mobile-optimized
  festive    -- colorful, celebration-themed with confetti

Requires (choose one):
  pip install google-api-python-client google-auth-oauthlib  (Gmail API)
  — or —
  No extra install needed for SMTP (uses built-in smtplib)

Integrates with: ai/self_improving_agent.py,
                 contacts/vip_contact_flagging.py,
                 autonomous_agent.py, langgraph_workflow.py
"""

import os
import json
import sqlite3
import smtplib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path("agent_history.db")

EMAIL_SENDER   = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
GMAIL_TOKEN    = Path("gmail_token.json")
GMAIL_CREDS    = Path("gmail_credentials.json")
SCOPES         = ["https://www.googleapis.com/auth/gmail.send"]

TEMPLATES = {
    "warm": {
        "label":   "Warm & Friendly",
        "subject": "Happy Birthday {first}! 🎂",
        "preview": "Casual, emoji-accented",
    },
    "formal": {
        "label":   "Professional",
        "subject": "Birthday Greetings — {first}",
        "preview": "Clean corporate style",
    },
    "minimal": {
        "label":   "Minimal",
        "subject": "HBD {first}!",
        "preview": "Short, mobile-friendly",
    },
    "festive": {
        "label":   "Festive",
        "subject": "🎉 It's Your Day, {first}! 🎉",
        "preview": "Colorful celebration",
    },
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_email_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_outreach_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            recipient_email TEXT NOT NULL,
            subject         TEXT NOT NULL,
            template        TEXT NOT NULL,
            method          TEXT NOT NULL,
            sent            INTEGER NOT NULL DEFAULT 0,
            error_msg       TEXT,
            sent_at         TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── HTML templates ────────────────────────────────────────────────────────────

def _render_html(
    contact_name: str,
    wish_text:    str,
    template:     str = "warm",
    sender_name:  str = "Birthday Wishes Agent",
) -> str:
    """Render a branded HTML email body."""
    first = contact_name.split()[0]
    year  = datetime.now().year

    COLORS = {
        "warm":    {"bg": "#fff8f0", "accent": "#f78166", "text": "#333"},
        "formal":  {"bg": "#f8f9fa", "accent": "#2c3e50", "text": "#333"},
        "minimal": {"bg": "#ffffff", "accent": "#333333", "text": "#555"},
        "festive": {"bg": "#1a0a2e", "accent": "#f78166", "text": "#e6edf3"},
    }
    c = COLORS.get(template, COLORS["warm"])

    confetti = ""
    if template == "festive":
        confetti = """
        <div style="text-align:center;font-size:2rem;margin-bottom:10px">
            🎂 🎉 🎊 🥳 🎈
        </div>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:{c['bg']};font-family:Arial,Helvetica,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;padding:20px">
<tr><td>

  <!-- Header -->
  <div style="background:{c['accent']};color:#fff;padding:24px 30px;
              border-radius:12px 12px 0 0;text-align:center">
    {confetti}
    <h1 style="margin:0;font-size:24px;font-weight:700">
      Happy Birthday, {first}!
    </h1>
  </div>

  <!-- Body -->
  <div style="background:#fff;padding:30px;border-left:1px solid #eee;
              border-right:1px solid #eee">
    <p style="color:{c['text']};font-size:16px;line-height:1.7;margin:0 0 20px">
      {wish_text}
    </p>
    <p style="color:{c['text']};font-size:15px;line-height:1.6;margin:0">
      Warm regards,<br>
      <strong>{sender_name}</strong>
    </p>
  </div>

  <!-- Footer -->
  <div style="background:#f1f1f1;padding:16px 30px;border-radius:0 0 12px 12px;
              text-align:center;font-size:11px;color:#999">
    Sent with care by Birthday Wishes Agent v10.0 · {year}
  </div>

</td></tr>
</table>
</body>
</html>"""


# ── Gmail API sender ──────────────────────────────────────────────────────────

def _send_via_gmail_api(
    to_email:  str,
    subject:   str,
    html_body: str,
) -> dict:
    """Send email via Gmail API (OAuth2)."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        return {"success": False, "error": "google-api-python-client not installed"}

    if not GMAIL_TOKEN.exists():
        return {"success": False,
                "error": "Gmail token not found. Run: python email_outreach.py auth"}

    try:
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            GMAIL_TOKEN.write_text(creds.to_json())

        service = build("gmail", "v1", credentials=creds)
        msg     = MIMEMultipart("alternative")
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        raw     = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result  = service.users().messages().send(
            userId="me", body={"raw": raw}).execute()

        return {"success": True, "message_id": result.get("id", ""),
                "method": "gmail_api"}
    except Exception as exc:
        return {"success": False, "error": str(exc), "method": "gmail_api"}


def run_gmail_auth() -> bool:
    """Run interactive OAuth2 flow for Gmail API."""
    if not GMAIL_CREDS.exists():
        print(f"[Email] {GMAIL_CREDS} not found.")
        print("  Download OAuth client credentials from Google Cloud Console")
        print("  (APIs & Services > Credentials > OAuth client ID > Desktop app)")
        print(f"  Save as {GMAIL_CREDS}")
        return False
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow  = InstalledAppFlow.from_client_secrets_file(str(GMAIL_CREDS), SCOPES)
        creds = flow.run_local_server(port=0)
        GMAIL_TOKEN.write_text(creds.to_json())
        print(f"[Email] Auth complete. Token saved to {GMAIL_TOKEN}")
        return True
    except Exception as exc:
        print(f"[Email] OAuth flow failed: {exc}")
        return False


# ── SMTP sender ───────────────────────────────────────────────────────────────

def _send_via_smtp(
    to_email:  str,
    subject:   str,
    html_body: str,
) -> dict:
    """Send email via Gmail SMTP with app password."""
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        return {"success": False,
                "error": "EMAIL_SENDER and EMAIL_PASSWORD not set in .env"}
    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)

        return {"success": True, "method": "smtp"}
    except Exception as exc:
        return {"success": False, "error": str(exc), "method": "smtp"}


# ── Main send function ────────────────────────────────────────────────────────

def send_birthday_email(
    contact_id:      str,
    contact_name:    str,
    recipient_email: str,
    wish_text:       str,
    template:        str = "warm",
    sender_name:     str = "Birthday Wishes Agent",
    method:          str = "auto",
    dry_run:         bool = True,
) -> dict:
    """
    Send a branded birthday email.

    Args:
        contact_id:      Unique contact identifier.
        contact_name:    Full name.
        recipient_email: Email address to send to.
        wish_text:       Personalized wish message.
        template:        warm / formal / minimal / festive.
        sender_name:     Name shown in the email signature.
        method:          auto / gmail_api / smtp.
        dry_run:         If True, render but don't actually send.

    Returns:
        { success, method, message_id, subject, template, dry_run, error }
    """
    init_email_tables()
    first    = contact_name.split()[0]
    tmpl     = TEMPLATES.get(template, TEMPLATES["warm"])
    subject  = tmpl["subject"].format(first=first)
    html     = _render_html(contact_name, wish_text, template, sender_name)

    if dry_run:
        result = {"success": True, "method": "dry_run", "message_id": None,
                  "subject": subject, "template": template,
                  "dry_run": True, "error": ""}
        _log_email(contact_id, contact_name, recipient_email,
                   subject, template, "dry_run", True, "")
        print(f"[Email] DRY RUN → {contact_name} <{recipient_email}> "
              f"[{template}]")
        return result

    # Auto-select method
    if method == "auto":
        method = "gmail_api" if GMAIL_TOKEN.exists() else "smtp"

    if method == "gmail_api":
        result = _send_via_gmail_api(recipient_email, subject, html)
    else:
        result = _send_via_smtp(recipient_email, subject, html)

    result["subject"]  = subject
    result["template"] = template
    result["dry_run"]  = False

    _log_email(contact_id, contact_name, recipient_email,
               subject, template, result.get("method","unknown"),
               result.get("success",False), result.get("error",""))

    status = "✅" if result.get("success") else "❌"
    print(f"[Email] {status} {contact_name} <{recipient_email}> "
          f"[{template}] via {result.get('method')}")

    return result


def _log_email(contact_id, contact_name, email, subject,
               template, method, sent, error):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO email_outreach_log
            (contact_id, contact_name, recipient_email, subject,
             template, method, sent, error_msg, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, email, subject,
          template, method, 1 if sent else 0, error,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ── Batch send ────────────────────────────────────────────────────────────────

def send_batch(
    contacts:  list[dict],
    template:  str = "warm",
    dry_run:   bool = True,
    verbose:   bool = True,
) -> dict:
    """
    Send birthday emails to a list of contacts.

    Each contact dict needs: contact_id, contact_name, email, wish_text.

    Returns:
        { total, sent, failed, dry_run }
    """
    if verbose:
        print(f"[Email] Sending {len(contacts)} emails "
              f"({'DRY RUN' if dry_run else 'LIVE'})\n")

    sent = failed = 0
    for c in contacts:
        result = send_birthday_email(
            c["contact_id"], c["contact_name"],
            c["email"], c["wish_text"],
            template=template, dry_run=dry_run)
        if result.get("success"):
            sent += 1
        else:
            failed += 1

    if verbose:
        print(f"\n[Email] Done: {sent} sent, {failed} failed")

    return {"total": len(contacts), "sent": sent,
            "failed": failed, "dry_run": dry_run}


def preview_template(
    contact_name: str = "Rakib Hossain",
    wish_text:    str = "Wishing you an incredible year ahead!",
    template:     str = "warm",
) -> str:
    """Return rendered HTML for preview (no sending)."""
    return _render_html(contact_name, wish_text, template)


def get_email_log(limit: int = 20) -> list[dict]:
    """Return recent email send history."""
    init_email_tables()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT contact_name, recipient_email, subject, template,
               method, sent, error_msg, sent_at
        FROM email_outreach_log ORDER BY sent_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_email_status() -> dict:
    """Return email configuration status."""
    init_email_tables()
    has_gmail_api = GMAIL_TOKEN.exists()
    has_smtp      = bool(EMAIL_SENDER and EMAIL_PASSWORD)
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute(
        "SELECT COUNT(*) FROM email_outreach_log WHERE sent=1").fetchone()[0]
    conn.close()
    return {
        "gmail_api_ready": has_gmail_api,
        "smtp_ready":      has_smtp,
        "method":          "gmail_api" if has_gmail_api else
                           "smtp" if has_smtp else "none",
        "total_sent":      total,
    }


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Email Outreach", page_icon="📧",
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
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.3rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    .log-row{background:var(--surface);border:1px solid var(--border);
             border-radius:8px;padding:10px 14px;margin-bottom:6px;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);
        border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_email_tables()
    status = get_email_status()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📧</span>
      <h1>Email Outreach</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Gmail API", "✓ Ready" if status["gmail_api_ready"] else "✗",
         "#3fb950" if status["gmail_api_ready"] else "#f85149"),
        (m2, "SMTP",      "✓ Ready" if status["smtp_ready"] else "✗",
         "#3fb950" if status["smtp_ready"] else "#d29922"),
        (m3, "Method",    status["method"], "#58a6ff"),
        (m4, "Emails Sent", status["total_sent"], "#f78166"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" '
                        f'style="color:{color};font-size:0.95rem">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.2, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Send Email</div>',
                    unsafe_allow_html=True)
        cname   = st.text_input("Contact name", placeholder="Rakib Hossain",
                                label_visibility="collapsed", key="cn")
        cemail  = st.text_input("Email", placeholder="rakib@example.com",
                                label_visibility="collapsed", key="ce")
        cwish   = st.text_area("Wish text", height=80,
                               label_visibility="collapsed", key="cw",
                               placeholder="Happy Birthday! Wishing you...")
        tmpl    = st.selectbox("Template",
                               list(TEMPLATES.keys()),
                               format_func=lambda x: f"{TEMPLATES[x]['label']} — {TEMPLATES[x]['preview']}",
                               label_visibility="collapsed", key="tmpl")
        dry_run = st.checkbox("Dry Run", value=True, key="dr")

        if st.button("📧 Send Email", type="primary", use_container_width=True):
            if cname and cemail and cwish:
                result = send_birthday_email(
                    "manual_001", cname, cemail, cwish,
                    template=tmpl, dry_run=dry_run)
                if result["success"]:
                    st.success(f"{'DRY RUN — ' if dry_run else ''}Email sent!")
                else:
                    st.error(f"Failed: {result.get('error','')}")
                st.rerun()

        # Template preview
        st.markdown('<div class="section-title">Template Preview</div>',
                    unsafe_allow_html=True)
        preview_name = cname or "Rakib Hossain"
        preview_wish = cwish or "Wishing you an incredible year ahead!"
        html_preview = preview_template(preview_name, preview_wish, tmpl)
        st.components.v1.html(html_preview, height=320, scrolling=True)

    with right:
        st.markdown('<div class="section-title">Send Log</div>',
                    unsafe_allow_html=True)
        log = get_email_log(15)
        if not log:
            st.caption("No emails sent yet.")
        for entry in log:
            ok    = bool(entry["sent"])
            color = "#3fb950" if ok else "#f85149"
            ts    = entry["sent_at"][:16].replace("T", " ")
            st.markdown(f"""
            <div class="log-row">
              <div style="display:flex;justify-content:space-between">
                <span style="font-weight:700;font-size:0.82rem">
                  {entry['contact_name']}
                </span>
                <span style="color:{color};font-size:0.7rem;font-weight:700">
                  {'✅' if ok else '❌'} {entry['method']}
                </span>
              </div>
              <div style="font-size:0.68rem;color:#8b949e;margin-top:3px">
                {entry['recipient_email']} · {entry['template']} · {ts}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>Email Outreach</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"

    if cmd == "auth":
        run_gmail_auth()

    elif cmd == "test":
        init_email_tables()
        print("=== Email Outreach -- self test ===\n")
        status = get_email_status()
        print(f"Gmail API : {'Ready' if status['gmail_api_ready'] else 'Not configured'}")
        print(f"SMTP      : {'Ready' if status['smtp_ready'] else 'Not configured'}")
        print(f"Method    : {status['method']}")

        print("\nSending test emails (dry run):\n")
        contacts = [
            {"contact_id":"urn_rakib_001","contact_name":"Rakib Hossain",
             "email":"rakib@example.com",
             "wish_text":"Happy Birthday Rakib! Hope this year brings everything you've been working toward!"},
            {"contact_id":"urn_nadia_002","contact_name":"Nadia Islam",
             "email":"nadia@example.com",
             "wish_text":"Happy Birthday Nadia! Your design work continues to inspire everyone around you."},
        ]
        result = send_batch(contacts, template="warm", dry_run=True)
        print(f"\nResult: {result}")

        print("\nTemplate previews generated:")
        for t in TEMPLATES:
            html = preview_template("Test User", "Have an amazing day!", t)
            print(f"  {t:<10} → {len(html)} chars HTML")

    elif cmd == "send":
        if len(sys.argv) < 4:
            print("Usage: python email_outreach.py send <name> <email> [template]")
        else:
            name  = sys.argv[2]
            email = sys.argv[3]
            tmpl  = sys.argv[4] if len(sys.argv) > 4 else "warm"
            live  = "--live" in sys.argv
            send_birthday_email(
                "cli_001", name, email,
                f"Happy Birthday {name.split()[0]}! Wishing you an amazing year ahead!",
                template=tmpl, dry_run=not live)
else:
    render_dashboard()
