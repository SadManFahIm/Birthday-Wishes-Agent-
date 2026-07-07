"""
VIP Contact Flagging — Birthday Wishes Agent v8.0
Mark contacts as VIP so they always receive highest-effort wishes,
mandatory manual review before sending, and premium features like
voice notes and multi-platform wishes.

VIP levels:
  platinum  → CEO / very close friend — manual review + voice note + multi-platform
  gold      → Senior contact / close colleague — manual review + premium wish
  silver    → Important contact — manual review only

Integrates with: contacts/relationship_tiering.py,
                 dashboards/batch_approve_queue.py, agent.py
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH = Path("agent_history.db")

VIP_LEVELS = {
    "platinum": {
        "label": "Platinum", "icon": "💎", "color": "#4fc3f7",
        "min_score":         10,
        "manual_review":     True,
        "voice_note":        True,
        "multi_platform":    True,
        "wish_style":        "poetic",
    },
    "gold": {
        "label": "Gold",     "icon": "🥇", "color": "#d29922",
        "min_score":         9,
        "manual_review":     True,
        "voice_note":        False,
        "multi_platform":    False,
        "wish_style":        "warm",
    },
    "silver": {
        "label": "Silver",   "icon": "🥈", "color": "#8b949e",
        "min_score":         8,
        "manual_review":     True,
        "voice_note":        False,
        "multi_platform":    False,
        "wish_style":        "formal",
    },
}

# ── DB setup ──────────────────────────────────────────────────────────────────

def init_vip_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vip_contacts (
            contact_id      TEXT PRIMARY KEY,
            contact_name    TEXT NOT NULL,
            vip_level       TEXT NOT NULL DEFAULT 'gold',
            reason          TEXT,
            added_at        TEXT NOT NULL,
            added_by        TEXT NOT NULL DEFAULT 'manual',
            active          INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vip_wish_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id      TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            vip_level       TEXT NOT NULL,
            wish_text       TEXT,
            review_status   TEXT NOT NULL DEFAULT 'pending',
            reviewed_by     TEXT,
            reviewed_at     TEXT,
            sent_at         TEXT,
            logged_at       TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── VIP management ────────────────────────────────────────────────────────────

def flag_vip(
    contact_id:   str,
    contact_name: str,
    vip_level:    str = "gold",
    reason:       str = "",
    added_by:     str = "manual",
):
    """
    Mark a contact as VIP.

    Args:
        contact_id:   Unique contact identifier.
        contact_name: Human-readable name.
        vip_level:    platinum / gold / silver
        reason:       Why this contact is VIP.
        added_by:     Who flagged them (manual / auto / agent).
    """
    init_vip_table()
    if vip_level not in VIP_LEVELS:
        vip_level = "gold"
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO vip_contacts
            (contact_id, contact_name, vip_level, reason, added_at, added_by)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(contact_id) DO UPDATE SET
            vip_level  = excluded.vip_level,
            reason     = excluded.reason,
            added_at   = excluded.added_at,
            added_by   = excluded.added_by,
            active     = 1
    """, (contact_id, contact_name, vip_level, reason,
          datetime.now().isoformat(), added_by))
    conn.commit()
    conn.close()


def unflag_vip(contact_id: str):
    """Remove VIP status from a contact."""
    init_vip_table()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE vip_contacts SET active=0 WHERE contact_id=?",
                 (contact_id,))
    conn.commit()
    conn.close()


def is_vip(contact_id: str) -> bool:
    """Quick check — call before generating a wish."""
    init_vip_table()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute(
        "SELECT active FROM vip_contacts WHERE contact_id=?", (contact_id,)
    ).fetchone()
    conn.close()
    return bool(row and row[0])


def get_vip_profile(contact_id: str) -> Optional[dict]:
    """Return full VIP profile for a contact, or None if not VIP."""
    init_vip_table()
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("""
        SELECT contact_id, contact_name, vip_level, reason, added_at, added_by, active
        FROM vip_contacts WHERE contact_id=? AND active=1
    """, (contact_id,)).fetchone()
    conn.close()
    if not row:
        return None
    level = row[2]
    meta  = VIP_LEVELS.get(level, VIP_LEVELS["gold"])
    return {
        "contact_id":   row[0], "contact_name":  row[1],
        "vip_level":    level,  "reason":         row[3],
        "added_at":     row[4], "added_by":        row[5],
        "active":       bool(row[6]),
        "icon":         meta["icon"],   "color":          meta["color"],
        "label":        meta["label"],  "manual_review":  meta["manual_review"],
        "voice_note":   meta["voice_note"],
        "multi_platform":meta["multi_platform"],
        "min_score":    meta["min_score"],
        "wish_style":   meta["wish_style"],
    }


def get_all_vip_contacts() -> list[dict]:
    """Return all active VIP contacts sorted by level."""
    init_vip_table()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT contact_id, contact_name, vip_level, reason, added_at, added_by
        FROM vip_contacts WHERE active=1
        ORDER BY CASE vip_level
            WHEN 'platinum' THEN 1
            WHEN 'gold'     THEN 2
            WHEN 'silver'   THEN 3
        END
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        meta = VIP_LEVELS.get(r[2], VIP_LEVELS["gold"])
        result.append({
            "contact_id": r[0], "contact_name": r[1], "vip_level": r[2],
            "reason": r[3] or "", "added_at": r[4], "added_by": r[5],
            "icon": meta["icon"], "color": meta["color"], "label": meta["label"],
            "manual_review": meta["manual_review"],
            "voice_note": meta["voice_note"],
            "min_score": meta["min_score"],
        })
    return result


# ── Wish review queue ─────────────────────────────────────────────────────────

def queue_vip_wish(
    contact_id:   str,
    contact_name: str,
    vip_level:    str,
    wish_text:    str,
) -> int:
    """
    Queue a generated wish for mandatory manual review before sending.
    Returns the log row ID.
    """
    init_vip_table()
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute("""
        INSERT INTO vip_wish_log
            (contact_id, contact_name, vip_level, wish_text, review_status, logged_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (contact_id, contact_name, vip_level, wish_text, datetime.now().isoformat()))
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def approve_vip_wish(log_id: int, reviewed_by: str = "user") -> bool:
    """Approve a queued VIP wish for sending."""
    init_vip_table()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE vip_wish_log SET
            review_status = 'approved',
            reviewed_by   = ?,
            reviewed_at   = ?
        WHERE id = ?
    """, (reviewed_by, datetime.now().isoformat(), log_id))
    conn.commit()
    conn.close()
    return True


def reject_vip_wish(log_id: int, reviewed_by: str = "user") -> bool:
    """Reject a queued VIP wish — agent will regenerate."""
    init_vip_table()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE vip_wish_log SET
            review_status = 'rejected',
            reviewed_by   = ?,
            reviewed_at   = ?
        WHERE id = ?
    """, (reviewed_by, datetime.now().isoformat(), log_id))
    conn.commit()
    conn.close()
    return True


def get_pending_vip_reviews() -> list[dict]:
    """Return all VIP wishes awaiting manual review."""
    init_vip_table()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, contact_id, contact_name, vip_level, wish_text, logged_at
        FROM vip_wish_log WHERE review_status='pending'
        ORDER BY logged_at ASC
    """).fetchall()
    conn.close()
    return [{
        "id": r[0], "contact_id": r[1], "contact_name": r[2],
        "vip_level": r[3], "wish_text": r[4], "logged_at": r[5],
        "icon":  VIP_LEVELS.get(r[3], {}).get("icon",  "🥇"),
        "color": VIP_LEVELS.get(r[3], {}).get("color", "#d29922"),
    } for r in rows]


# ── Agent integration helper ──────────────────────────────────────────────────

def get_vip_wish_config(contact_id: str) -> dict:
    """
    Main entry point for agent.py. Returns wish config for a VIP contact.

    Returns:
        {
          is_vip, vip_level, min_score, wish_style,
          manual_review, voice_note, multi_platform,
          prompt_instruction
        }
    """
    profile = get_vip_profile(contact_id)
    if not profile:
        return {"is_vip": False}

    level = profile["vip_level"]
    meta  = VIP_LEVELS[level]

    prompt = (
        f"This is a VIP contact ({meta['label']} level). "
        f"Generate the highest-quality wish possible. "
        f"Minimum personalization score: {meta['min_score']}/10. "
        f"Preferred style: {meta['wish_style']}. "
        f"Be thoughtful, specific, and warm — this wish will be manually reviewed before sending."
    )

    return {
        "is_vip":          True,
        "vip_level":       level,
        "vip_label":       meta["label"],
        "vip_icon":        meta["icon"],
        "min_score":       meta["min_score"],
        "wish_style":      meta["wish_style"],
        "manual_review":   meta["manual_review"],
        "voice_note":      meta["voice_note"],
        "multi_platform":  meta["multi_platform"],
        "prompt_instruction": prompt,
    }


# ── Demo seeder ───────────────────────────────────────────────────────────────

def _seed_demo():
    init_vip_table()
    conn  = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM vip_contacts").fetchone()[0]
    conn.close()
    if count > 0:
        return
    demo = [
        ("urn_rakib_001", "Rakib Hossain", "gold",     "Close friend + key collaborator"),
        ("urn_mim_004",   "Mim Chowdhury", "platinum", "University best friend"),
        ("urn_nadia_002", "Nadia Islam",   "silver",   "Senior colleague at bKash"),
    ]
    for cid, cname, level, reason in demo:
        flag_vip(cid, cname, level, reason)
    queue_vip_wish("urn_mim_004", "Mim Chowdhury", "platinum",
                   "From IUT to where you are now — what a run, Mim! "
                   "Happy Birthday to someone who makes every room better. "
                   "Hope today is as brilliant as you are. 🎉")
    queue_vip_wish("urn_rakib_001", "Rakib Hossain", "gold",
                   "Happy Birthday Rakib! Your work at Pathao speaks for itself — "
                   "but it's the person behind the code that makes it count. "
                   "Have an amazing one! 🎂")


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="VIP Contacts", page_icon="💎",
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
    .vip-card{background:var(--surface);border-radius:12px;padding:16px 18px;
              margin-bottom:10px;}
    .vip-pill{display:inline-flex;align-items:center;gap:4px;font-size:0.68rem;
              font-weight:700;padding:3px 10px;border-radius:20px;
              text-transform:uppercase;letter-spacing:0.06em;}
    .review-card{background:var(--surface);border-radius:10px;padding:14px 16px;
                 margin-bottom:10px;}
    .wish-box{background:#010409;border:1px solid var(--border);border-radius:8px;
              padding:12px 14px;font-size:0.82rem;color:#c9d1d9;
              line-height:1.6;margin:8px 0;}
    .feature-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:6px;}
    .f-chip{font-size:0.62rem;font-weight:700;padding:2px 7px;border-radius:12px;
            background:#21262d;color:var(--muted);border:1px solid var(--border);}
    .f-chip.on{background:#051a09;color:var(--green);border-color:var(--green);}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:var(--blue);background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:var(--accent);
        border-color:var(--accent);color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    _seed_demo()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">💎</span>
      <h1>VIP Contact Flagging</h1>
      <span class="cc-badge">v8.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    left, right = st.columns([1.2, 1], gap="large")

    with left:
        # ── VIP list ──────────────────────────────────────────────────────────
        vip_contacts = get_all_vip_contacts()
        st.markdown(f'<div class="section-title">VIP Contacts ({len(vip_contacts)})</div>',
                    unsafe_allow_html=True)

        for c in vip_contacts:
            meta = VIP_LEVELS[c["vip_level"]]
            st.markdown(f"""
            <div class="vip-card" style="border:1px solid {c['color']}44;
                 border-left:4px solid {c['color']}">
              <div style="display:flex;align-items:center;justify-content:space-between;
                          margin-bottom:8px">
                <div style="font-weight:700;font-size:0.92rem">{c['contact_name']}</div>
                <span class="vip-pill"
                      style="background:{c['color']}22;color:{c['color']};
                             border:1px solid {c['color']}55">
                  {c['icon']} {c['label']}
                </span>
              </div>
              <div style="font-size:0.7rem;color:#8b949e;margin-bottom:8px">
                {c['reason'] or 'No reason given'} · Added {c['added_at'][:10]}
              </div>
              <div class="feature-row">
                <span class="f-chip on">Min score {c['min_score']}/10</span>
                <span class="f-chip {'on' if meta['manual_review'] else ''}">
                  Manual review {'✓' if meta['manual_review'] else '✗'}
                </span>
                <span class="f-chip {'on' if meta['voice_note'] else ''}">
                  Voice note {'✓' if meta['voice_note'] else '✗'}
                </span>
                <span class="f-chip {'on' if meta['multi_platform'] else ''}">
                  Multi-platform {'✓' if meta['multi_platform'] else '✗'}
                </span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            rc1, rc2 = st.columns(2)
            with rc1:
                levels = list(VIP_LEVELS.keys())
                new_level = st.selectbox("Level", levels,
                                         index=levels.index(c["vip_level"]),
                                         key=f"lvl_{c['contact_id']}",
                                         label_visibility="collapsed")
                if new_level != c["vip_level"]:
                    flag_vip(c["contact_id"], c["contact_name"], new_level, c["reason"])
                    st.rerun()
            with rc2:
                if st.button("🗑 Remove VIP", key=f"rm_{c['contact_id']}",
                             use_container_width=True):
                    unflag_vip(c["contact_id"])
                    st.rerun()

        # ── Add VIP ───────────────────────────────────────────────────────────
        st.markdown('<div class="section-title">Flag New VIP</div>', unsafe_allow_html=True)
        new_id   = st.text_input("Contact ID",   placeholder="urn_...", key="new_id",
                                 label_visibility="collapsed")
        new_name = st.text_input("Contact name", placeholder="Full name", key="new_name",
                                 label_visibility="collapsed")
        new_lvl  = st.selectbox("VIP level", list(VIP_LEVELS.keys()),
                                label_visibility="collapsed", key="new_lvl")
        new_reason = st.text_input("Reason (optional)", key="new_reason",
                                   label_visibility="collapsed")
        if st.button("💎 Flag as VIP", type="primary", use_container_width=True):
            if new_id.strip() and new_name.strip():
                flag_vip(new_id.strip(), new_name.strip(), new_lvl, new_reason)
                st.success(f"{new_name} flagged as {new_lvl.title()} VIP ✅")
                st.rerun()

    with right:
        # ── Manual review queue ───────────────────────────────────────────────
        pending = get_pending_vip_reviews()
        st.markdown(f'<div class="section-title">Review Queue ({len(pending)} pending)</div>',
                    unsafe_allow_html=True)

        if not pending:
            st.info("No wishes pending review.")

        for p in pending:
            st.markdown(f"""
            <div class="review-card" style="border:1px solid {p['color']}44;
                 border-left:3px solid {p['color']}">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                <span style="font-size:1.1rem">{p['icon']}</span>
                <div>
                  <div style="font-weight:700;font-size:0.86rem">{p['contact_name']}</div>
                  <div style="font-size:0.66rem;color:#8b949e">
                    {VIP_LEVELS[p['vip_level']]['label']} · {p['logged_at'][:16].replace('T',' ')}
                  </div>
                </div>
              </div>
              <div class="wish-box">{p['wish_text']}</div>
            </div>
            """, unsafe_allow_html=True)

            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("✅ Approve", key=f"ap_{p['id']}", type="primary",
                             use_container_width=True):
                    approve_vip_wish(p["id"])
                    st.success("Approved — wish will be sent ✅")
                    st.rerun()
            with a2:
                if st.button("✕ Reject", key=f"rj_{p['id']}", use_container_width=True):
                    reject_vip_wish(p["id"])
                    st.warning("Rejected — agent will regenerate")
                    st.rerun()
            with a3:
                if st.button("✏️ Edit", key=f"ed_{p['id']}", use_container_width=True):
                    st.session_state[f"edit_{p['id']}"] = True
                    st.rerun()

            if st.session_state.get(f"edit_{p['id']}"):
                edited = st.text_area("Edit wish", value=p["wish_text"],
                                      key=f"ea_{p['id']}", height=120,
                                      label_visibility="collapsed")
                if st.button("Save & Approve", key=f"sa_{p['id']}",
                             use_container_width=True):
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("UPDATE vip_wish_log SET wish_text=? WHERE id=?",
                                 (edited, p["id"]))
                    conn.commit()
                    conn.close()
                    approve_vip_wish(p["id"])
                    st.rerun()

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">8.0</code></span>
      <span>VIP Contact Flagging</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    init_vip_table()
    _seed_demo()
    print("=== VIP Contact Flagging — self test ===\n")
    vips = get_all_vip_contacts()
    print(f"{len(vips)} VIP contacts:")
    for v in vips:
        print(f"  {v['icon']} {v['contact_name']:<22} {v['label']:<10} "
              f"min_score={v['min_score']} review={'✓' if v['manual_review'] else '✗'}")
    pending = get_pending_vip_reviews()
    print(f"\nPending reviews: {len(pending)}")
    for p in pending:
        print(f"  {p['icon']} {p['contact_name']} — {p['wish_text'][:50]}...")
    config = get_vip_wish_config("urn_mim_004")
    print(f"\nWish config for Mim: level={config['vip_level']} "
          f"voice={config['voice_note']} review={config['manual_review']}")
else:
    render_dashboard()
