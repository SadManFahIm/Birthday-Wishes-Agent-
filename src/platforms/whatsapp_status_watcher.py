"""
WhatsApp Status Watcher -- Birthday Wishes Agent v10.0
Monitors contacts' WhatsApp statuses to detect life occasions
(birthday, promotion, wedding, new job, travel, etc.) and
triggers appropriate wishes or notes automatically.

How it works:
  1. Pull status updates via WhatsApp Business API webhook
  2. Run text + emoji pattern matching on status content
  3. Classify occasion (birthday / promotion / travel / etc.)
  4. Score urgency and enqueue a wish or alert
  5. Log all detections for audit trail

Status sources:
  - Webhook push (production): statuses arrive in real-time
  - Manual entry (dashboard): paste status text to test detection
  - Demo seeder: synthetic statuses for development

Occasion detection:
  birthday, promotion, wedding, new_job, travel,
  anniversary, graduation, baby, achievement, general

Integrates with: platforms/whatsapp_business_api.py,
                 redis_cache.py, autonomous_agent.py,
                 langgraph_workflow.py
"""

import sqlite3
import json
import re
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

DB_PATH = Path("agent_history.db")

WHATSAPP_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE = os.getenv("WHATSAPP_PHONE_ID", "")

# ── Occasion definitions ──────────────────────────────────────────────────────

OCCASIONS = {
    "birthday": {
        "label":    "Birthday",
        "icon":     "🎂",
        "color":    "#f78166",
        "priority": 10,
        "action":   "birthday_wish",
        "patterns": [
            r"\bbirthday\b", r"\bbday\b", r"\bmy birthday\b",
            r"🎂", r"🎁", r"🎉", r"🥳",
            r"\bit'?s? my (special )?day\b",
            r"\b(turning|turned) \d+\b",
            r"\banother year\b", r"\bblowing out candles\b",
        ],
    },
    "promotion": {
        "label":    "Promotion",
        "icon":     "📈",
        "color":    "#3fb950",
        "priority": 8,
        "action":   "congratulations_wish",
        "patterns": [
            r"\bpromoted\b", r"\bpromotion\b", r"\bnew role\b",
            r"\bexcited to announce\b", r"\bjoining .+ as\b",
            r"\b(senior|lead|head|director|vp|cto|ceo|coo|cmo)\b",
            r"📣", r"🚀", r"\bnext chapter\b",
            r"\bstepping into\b", r"\bstarting (my )?new (role|position|journey)\b",
        ],
    },
    "wedding": {
        "label":    "Wedding",
        "icon":     "💍",
        "color":    "#bc8cff",
        "priority": 9,
        "action":   "congratulations_wish",
        "patterns": [
            r"\bmarried\b", r"\bwedding\b", r"\bengaged\b",
            r"\bnikkah\b", r"\bwife\b", r"\bhusband\b",
            r"💍", r"👰", r"🤵", r"💒",
            r"\bsaid yes\b", r"\bknot\b",
        ],
    },
    "new_job": {
        "label":    "New Job",
        "icon":     "💼",
        "color":    "#58a6ff",
        "priority": 7,
        "action":   "congratulations_wish",
        "patterns": [
            r"\bnew job\b", r"\bstarting at\b", r"\bjoined\b",
            r"\bfirst day\b", r"\bnew company\b",
            r"\bnew opportunity\b", r"\bofficial(ly)?\b.{0,20}\bjoin\b",
            r"💼", r"\bday 1\b", r"\bonboarding\b",
        ],
    },
    "travel": {
        "label":    "Travel",
        "icon":     "✈️",
        "color":    "#d29922",
        "priority": 4,
        "action":   "travel_note",
        "patterns": [
            r"\btravel(l?ing)?\b", r"\bvacation\b", r"\bholiday\b",
            r"\bflying to\b", r"\bin [A-Z][a-z]+\b",
            r"✈️", r"🌍", r"🏖", r"🗺",
            r"\boff to\b", r"\barrived in\b", r"\bexploring\b",
        ],
    },
    "graduation": {
        "label":    "Graduation",
        "icon":     "🎓",
        "color":    "#4fc3f7",
        "priority": 8,
        "action":   "congratulations_wish",
        "patterns": [
            r"\bgraduate[ds]?\b", r"\bgraduation\b", r"\bconvocation\b",
            r"\bdegree\b", r"\balumni\b", r"🎓",
            r"\bpassed\b.{0,20}\bexam\b", r"\bCSE\b.{0,20}\bgraduate\b",
        ],
    },
    "baby": {
        "label":    "New Baby",
        "icon":     "👶",
        "color":    "#f78166",
        "priority": 9,
        "action":   "congratulations_wish",
        "patterns": [
            r"\bbaby\b", r"\bnewborn\b", r"\bmom\b.{0,10}\bnew\b",
            r"\bdad\b.{0,10}\bnew\b", r"\bparent\b",
            r"👶", r"🍼", r"\bwelcome.{0,10}world\b",
            r"\bwe have a (son|daughter|baby)\b",
        ],
    },
    "anniversary": {
        "label":    "Anniversary",
        "icon":     "💝",
        "color":    "#f85149",
        "priority": 7,
        "action":   "anniversary_wish",
        "patterns": [
            r"\banniversary\b", r"\byear(s)? together\b",
            r"\byear(s)? at\b", r"\bwork anniversary\b",
            r"💝", r"❤️", r"\bcelebrat.{0,10}year\b",
        ],
    },
    "achievement": {
        "label":    "Achievement",
        "icon":     "🏆",
        "color":    "#d29922",
        "priority": 6,
        "action":   "congratulations_wish",
        "patterns": [
            r"\bachievement\b", r"\baccomplishment\b", r"\bwon\b",
            r"\baward\b", r"\brecognition\b", r"\bhonored\b",
            r"🏆", r"🥇", r"🎖",
            r"\bpublished\b", r"\blaunched\b", r"\bshipped\b",
        ],
    },
    "general": {
        "label":    "General Update",
        "icon":     "💬",
        "color":    "#8b949e",
        "priority": 2,
        "action":   "note",
        "patterns": [],   # fallback — no patterns needed
    },
}


# ── DB setup ──────────────────────────────────────────────────────────────────

def init_watcher_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wa_status_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            phone_number    TEXT,
            status_text     TEXT NOT NULL,
            occasion        TEXT NOT NULL,
            confidence      REAL NOT NULL,
            priority        INTEGER NOT NULL,
            action_taken    TEXT,
            processed       INTEGER NOT NULL DEFAULT 0,
            detected_at     TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _safe(module: str, attr: str):
    try:
        mod = __import__(module, fromlist=[attr])
        return getattr(mod, attr, None)
    except ImportError:
        return None


# ── Occasion detector ─────────────────────────────────────────────────────────

def detect_occasion(status_text: str) -> dict:
    """
    Scan status text for occasion signals using regex + emoji patterns.

    Args:
        status_text: Raw WhatsApp status string.

    Returns:
        {
          occasion, label, icon, color, priority,
          action, confidence, matched_patterns
        }
    """
    text    = status_text.lower()
    best    = None
    best_sc = 0
    matched = []

    for occ_key, occ in OCCASIONS.items():
        if occ_key == "general":
            continue
        hits = []
        for pat in occ["patterns"]:
            if re.search(pat, text, re.IGNORECASE):
                hits.append(pat)
        if hits:
            # Score: more hits = higher confidence
            score = min(1.0, 0.4 + len(hits) * 0.2)
            if score > best_sc:
                best_sc = score
                best    = occ_key
                matched = hits

    if not best:
        return {
            "occasion":         "general",
            "label":            OCCASIONS["general"]["label"],
            "icon":             OCCASIONS["general"]["icon"],
            "color":            OCCASIONS["general"]["color"],
            "priority":         OCCASIONS["general"]["priority"],
            "action":           OCCASIONS["general"]["action"],
            "confidence":       0.1,
            "matched_patterns": [],
        }

    occ = OCCASIONS[best]
    return {
        "occasion":         best,
        "label":            occ["label"],
        "icon":             occ["icon"],
        "color":            occ["color"],
        "priority":         occ["priority"],
        "action":           occ["action"],
        "confidence":       round(best_sc, 2),
        "matched_patterns": matched[:3],
    }


# ── Status processor ──────────────────────────────────────────────────────────

def process_status(
    contact_id:   str,
    contact_name: str,
    status_text:  str,
    phone_number: str = "",
    auto_act:     bool = False,
    dry_run:      bool = True,
) -> dict:
    """
    Process one WhatsApp status update end-to-end:
      detect → log → optionally enqueue action.

    Args:
        contact_id:   Agent contact ID.
        contact_name: Full name.
        status_text:  Raw status string.
        phone_number: WhatsApp number (needed to send a reply wish).
        auto_act:     If True, automatically enqueue action for high-priority.
        dry_run:      If True, never send real messages.

    Returns:
        { occasion, confidence, action_taken, log_id, queued }
    """
    init_watcher_tables()
    detection = detect_occasion(status_text)
    occasion  = detection["occasion"]
    priority  = detection["priority"]
    action    = detection["action"]
    action_taken = ""
    queued       = False

    # Auto-act on high priority detections (birthday / wedding / graduation)
    if auto_act and priority >= 8 and not dry_run:
        enqueue_fn = _safe("redis_cache", "enqueue")
        if enqueue_fn:
            try:
                enqueue_fn("wishes", action, {
                    "contact_id":   contact_id,
                    "contact_name": contact_name,
                    "phone_number": phone_number,
                    "occasion":     occasion,
                    "status_text":  status_text[:200],
                    "trigger":      "wa_status_watcher",
                }, priority=priority)
                queued       = True
                action_taken = f"queued:{action}"
            except Exception as exc:
                action_taken = f"queue_error:{exc}"
    elif auto_act and priority >= 8 and dry_run:
        action_taken = f"DRY RUN — would queue:{action}"
        queued       = True

    # Persist
    conn   = sqlite3.connect(DB_PATH)
    cur    = conn.execute("""
        INSERT INTO wa_status_log
            (contact_id, contact_name, phone_number, status_text,
             occasion, confidence, priority, action_taken,
             processed, detected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (contact_id, contact_name, phone_number, status_text,
          occasion, detection["confidence"], priority,
          action_taken, 1 if queued else 0,
          datetime.now().isoformat()))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()

    print(f"[WAStatus] {contact_name}: {detection['icon']} {detection['label']} "
          f"({detection['confidence']:.0%}) → {action}")

    return {
        "log_id":     log_id,
        "occasion":   occasion,
        "label":      detection["label"],
        "icon":       detection["icon"],
        "confidence": detection["confidence"],
        "priority":   priority,
        "action":     action,
        "action_taken":action_taken,
        "queued":     queued,
        "matched":    detection["matched_patterns"],
    }


# ── Webhook handler ───────────────────────────────────────────────────────────

def handle_webhook_payload(payload: dict, auto_act: bool = True,
                           dry_run: bool = True) -> list[dict]:
    """
    Parse a WhatsApp Business API webhook payload and process
    any status updates found.

    Webhook structure (simplified):
        { "entry": [{ "changes": [{ "value": {
            "statuses": [{ "id": "...", "timestamp": "...",
                           "recipient_id": "...",
                           "status": "delivered" }]
        }}]}]}

    For status updates (not delivery receipts), the text comes from
    a separate 'messages' event with type='text' and source='status'.

    This handler processes the 'messages' side of status events.

    Returns:
        List of process_status results.
    """
    results = []
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value    = change.get("value", {})
                messages = value.get("messages", [])
                contacts = {c.get("wa_id"): c.get("profile",{}).get("name","Unknown")
                            for c in value.get("contacts", [])}
                for msg in messages:
                    if msg.get("type") != "text":
                        continue
                    wa_id  = msg.get("from", "")
                    text   = msg.get("text", {}).get("body", "")
                    cname  = contacts.get(wa_id, wa_id)
                    cid    = f"wa_{wa_id}"
                    if text:
                        result = process_status(
                            cid, cname, text, wa_id,
                            auto_act=auto_act, dry_run=dry_run)
                        results.append(result)
    except Exception as exc:
        results.append({"error": str(exc)})
    return results


# ── Log retrieval ─────────────────────────────────────────────────────────────

def get_status_log(
    limit:    int = 30,
    occasion: Optional[str] = None,
) -> list[dict]:
    """Return recent status detections."""
    init_watcher_tables()
    conn = _db()
    sql  = """
        SELECT contact_name, status_text, occasion, confidence,
               priority, action_taken, processed, detected_at
        FROM wa_status_log
    """
    params = []
    if occasion:
        sql   += " WHERE occasion=?"
        params.append(occasion)
    sql   += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)
    rows   = conn.execute(sql, params).fetchall()
    conn.close()
    return [{
        "contact_name": r["contact_name"],
        "status_text":  r["status_text"][:80],
        "occasion":     r["occasion"],
        "icon":         OCCASIONS.get(r["occasion"],{}).get("icon","💬"),
        "color":        OCCASIONS.get(r["occasion"],{}).get("color","#8b949e"),
        "label":        OCCASIONS.get(r["occasion"],{}).get("label","General"),
        "confidence":   r["confidence"],
        "priority":     r["priority"],
        "action_taken": r["action_taken"] or "",
        "processed":    bool(r["processed"]),
        "detected_at":  r["detected_at"],
    } for r in rows]


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_watcher_tables()
    conn  = _db()
    count = conn.execute(
        "SELECT COUNT(*) FROM wa_status_log").fetchone()[0]
    conn.close()
    if count > 0:
        return
    demo_statuses = [
        ("urn_rakib_001","Rakib Hossain","+8801711111111",
         "🎂 Turning 28 today! Feeling grateful for everyone in my life 🥳"),
        ("urn_nadia_002","Nadia Islam","+8801722222222",
         "So excited to announce I've joined bKash as Senior Product Designer! 🚀"),
        ("urn_mim_004","Mim Chowdhury","+8801733333333",
         "✈️ Off to Singapore for a data science conference! 🌍"),
        ("urn_tanvir_003","Tanvir Ahmed","+8801744444444",
         "Alhamdulillah, graduated from BUET with my CSE degree 🎓"),
        ("urn_sara_005","Sara Khan","+8801755555555",
         "Just another Thursday ☕"),
    ]
    for cid, cname, phone, text in demo_statuses:
        process_status(cid, cname, text, phone,
                       auto_act=False, dry_run=True)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="WhatsApp Status Watcher", page_icon="👁",
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
    .s-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .occ-pill{display:inline-flex;align-items:center;gap:4px;font-size:0.62rem;
              font-weight:700;padding:2px 8px;border-radius:20px;
              text-transform:uppercase;letter-spacing:0.05em;}
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
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    init_watcher_tables()
    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">👁</span>
      <h1>WhatsApp Status Watcher</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    log  = get_status_log(50)
    high = [e for e in log if e["priority"] >= 8]
    occ_counts: dict = {}
    for e in log:
        occ_counts[e["occasion"]] = occ_counts.get(e["occasion"], 0) + 1

    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Statuses Watched", len(log),    "#e6edf3"),
        (m2, "High Priority",    len(high),   "#f78166"),
        (m3, "Occasions Found",  len([e for e in log if e["occasion"]!="general"]),
         "#3fb950"),
        (m4, "Webhook Ready",
         "✓" if (WHATSAPP_TOKEN and WHATSAPP_PHONE) else "⚠ No key",
         "#3fb950" if (WHATSAPP_TOKEN and WHATSAPP_PHONE) else "#d29922"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        # Manual test
        st.markdown('<div class="section-title">Test Occasion Detector</div>',
                    unsafe_allow_html=True)
        cname_in = st.text_input("Contact name", placeholder="Rakib Hossain",
                                 label_visibility="collapsed", key="cn")
        status_in = st.text_area("Status text", height=80,
                                 label_visibility="collapsed", key="st",
                                 placeholder="🎂 Turning 28 today! Feeling grateful...")
        auto_act  = st.checkbox("Auto-enqueue action (dry run)", value=True)

        if st.button("👁 Detect Occasion", type="primary",
                     use_container_width=True):
            if status_in:
                result = process_status(
                    "manual_test", cname_in or "Test Contact",
                    status_in, auto_act=auto_act, dry_run=True)
                occ  = result["occasion"]
                meta = OCCASIONS.get(occ, OCCASIONS["general"])
                st.markdown(f"""
                <div class="s-card" style="border-color:{meta['color']}55;
                     border-left:3px solid {meta['color']}">
                  <div style="font-size:1.8rem;margin-bottom:6px">{meta['icon']}</div>
                  <div style="font-weight:700;font-size:1.1rem">
                    {meta['label']}
                  </div>
                  <div style="font-size:0.76rem;color:#8b949e;margin-top:4px">
                    Confidence: {result['confidence']:.0%} ·
                    Priority: {result['priority']}/10 ·
                    Action: {result['action']}
                  </div>
                  {f'<div style="font-size:0.7rem;color:#58a6ff;margin-top:6px">'
                   f'Matched: {", ".join(result["matched"][:3])}</div>'
                   if result["matched"] else ""}
                </div>
                """, unsafe_allow_html=True)
                st.rerun()

        # Occasion reference
        st.markdown('<div class="section-title">Detected Occasions</div>',
                    unsafe_allow_html=True)
        for occ_key, meta in OCCASIONS.items():
            if occ_key == "general":
                continue
            count = occ_counts.get(occ_key, 0)
            st.markdown(f"""
            <div style="display:flex;align-items:center;gap:10px;
                        padding:6px 0;border-bottom:1px solid #21262d">
              <div style="font-size:1.1rem">{meta['icon']}</div>
              <div style="flex:1;font-size:0.80rem">{meta['label']}</div>
              <div style="font-size:0.68rem;font-weight:700;
                          color:{meta['color']}">{count}</div>
              <div style="font-size:0.62rem;color:#8b949e">
                pri {meta['priority']}
              </div>
            </div>
            """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Recent Detections</div>',
                    unsafe_allow_html=True)
        for entry in log[:15]:
            color  = entry["color"]
            ts     = entry["detected_at"][:16].replace("T"," ")
            high_p = entry["priority"] >= 8
            st.markdown(f"""
            <div class="s-card"
                 style="{'border-left:3px solid '+color+';' if high_p else ''}">
              <div style="display:flex;align-items:center;
                          justify-content:space-between;margin-bottom:4px">
                <div style="font-weight:700;font-size:0.84rem">
                  {entry['contact_name']}
                </div>
                <span class="occ-pill"
                      style="background:{color}22;color:{color};
                             border:1px solid {color}44">
                  {entry['icon']} {entry['label']}
                </span>
              </div>
              <div style="font-size:0.70rem;color:#c9d1d9;margin-bottom:4px">
                "{entry['status_text'][:60]}{'...' if len(entry['status_text'])>60 else ''}"
              </div>
              <div style="font-size:0.65rem;color:#8b949e">
                {entry['confidence']:.0%} confidence ·
                {ts}
                {' · ✅ actioned' if entry['processed'] else ''}
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">10.0</code></span>
      <span>WhatsApp Status Watcher</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_watcher_tables()
    print("=== WhatsApp Status Watcher -- self test ===\n")

    test_statuses = [
        ("urn_rakib_001","Rakib Hossain",
         "🎂 Turning 28 today! Feeling grateful for everyone in my life 🥳"),
        ("urn_nadia_002","Nadia Islam",
         "So excited to announce I've joined bKash as Senior Product Designer! 🚀"),
        ("urn_mim_004","Mim Chowdhury",
         "✈️ Off to Singapore for a data science conference! 🌍"),
        ("urn_tanvir_003","Tanvir Ahmed",
         "Alhamdulillah, graduated from BUET with my CSE degree 🎓"),
        ("urn_imran_006","Imran Hossain",
         "Promoted to Engineering Manager at Shajgoj 📈"),
        ("urn_sara_005","Sara Khan",
         "Just another Thursday ☕"),
    ]

    results = []
    for cid, cname, text in test_statuses:
        r = process_status(cid, cname, text, dry_run=True, auto_act=False)
        results.append(r)

    print(f"\nDetection summary ({len(results)} statuses):")
    counts: dict = {}
    for r in results:
        counts[r["occasion"]] = counts.get(r["occasion"], 0) + 1
        action_note = f"→ {r['action']}" if r["occasion"] != "general" else ""
        print(f"  {r['icon']} {r['label']:<18} "
              f"{r['confidence']:.0%}  {action_note}")

    log = get_status_log(10)
    print(f"\nLog entries: {len(log)}")
else:
    render_dashboard()
