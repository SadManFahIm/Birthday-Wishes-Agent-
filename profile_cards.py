"""
profile_cards.py
────────────────
Contact Profile Cards dashboard for Birthday Wishes Agent.

Run with:
    streamlit run profile_cards.py

Shows a card for each contact with:
  - Name and connection strength level
  - Job title and company
  - Wish history (how many times wished, last wish date)
  - Personal notes
  - Interaction trend (growing/stable/fading)
  - Quick action buttons (Add Note, View History)
"""

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import streamlit as st

DB_FILE = Path("agent_history.db")

# ──────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Contact Profile Cards",
    page_icon="👥",
    layout="wide",
)

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def get_db():
    if not DB_FILE.exists():
        return None
    return sqlite3.connect(DB_FILE)


def get_all_contacts() -> list[str]:
    conn = get_db()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT DISTINCT contact FROM history ORDER BY contact"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def get_contact_history(contact: str) -> list[dict]:
    conn = get_db()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT date, task, message, dry_run FROM history "
            "WHERE LOWER(contact) = LOWER(?) ORDER BY date DESC",
            (contact,),
        ).fetchall()
        conn.close()
        return [{"date": r[0], "task": r[1], "message": r[2], "dry_run": bool(r[3])}
                for r in rows]
    except Exception:
        return []


def get_contact_memory(contact: str) -> dict:
    conn = get_db()
    if not conn:
        return {}
    try:
        row = conn.execute(
            "SELECT job_title, company, life_event, interests, last_wish "
            "FROM contact_memory WHERE LOWER(contact) = LOWER(?) "
            "ORDER BY year DESC LIMIT 1",
            (contact,),
        ).fetchone()
        conn.close()
        if not row:
            return {}
        return {
            "job_title":  row[0] or "",
            "company":    row[1] or "",
            "life_event": row[2] or "",
            "interests":  json.loads(row[3]) if row[3] else [],
            "last_wish":  row[4] or "",
        }
    except Exception:
        return {}


def get_contact_notes(contact: str) -> list[dict]:
    conn = get_db()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT id, note, tags, created_at FROM contact_notes "
            "WHERE LOWER(contact) = LOWER(?) ORDER BY created_at DESC",
            (contact,),
        ).fetchall()
        conn.close()
        return [{"id": r[0], "note": r[1],
                 "tags": r[2].split(",") if r[2] else [],
                 "created_at": r[3]}
                for r in rows]
    except Exception:
        return []


def get_strength(contact: str) -> dict:
    conn = get_db()
    if not conn:
        return {"score": 0, "level": "Fading", "emoji": "🔴"}
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM connection_interactions "
            "WHERE LOWER(contact) = LOWER(?)",
            (contact,),
        ).fetchone()[0]
        conn.close()
        score = min(100, count * 8)
        if score >= 81:
            return {"score": score, "level": "Very Strong", "emoji": "⭐"}
        elif score >= 61:
            return {"score": score, "level": "Strong",      "emoji": "💙"}
        elif score >= 41:
            return {"score": score, "level": "Moderate",    "emoji": "🟢"}
        elif score >= 21:
            return {"score": score, "level": "Weak",        "emoji": "🟡"}
        else:
            return {"score": score, "level": "Fading",      "emoji": "🔴"}
    except Exception:
        return {"score": 0, "level": "Fading", "emoji": "🔴"}


def save_note(contact: str, note: str, tags: str):
    conn = get_db()
    if not conn:
        return
    try:
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO contact_notes (contact, note, tags, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (contact, note, tags, now, now),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Could not save note: {e}")


def delete_note(note_id: int):
    conn = get_db()
    if not conn:
        return
    try:
        conn.execute("DELETE FROM contact_notes WHERE id = ?", (note_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
  .profile-card {
    background: #1E2329;
    border: 1px solid #2E3440;
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
    transition: box-shadow 0.2s;
  }
  .profile-card:hover {
    box-shadow: 0 4px 20px rgba(76,175,80,0.15);
    border-color: #4CAF50;
  }
  .contact-name {
    font-size: 1.2rem;
    font-weight: 700;
    color: #FAFAFA;
    margin: 0;
  }
  .contact-job {
    font-size: 0.9rem;
    color: #888;
    margin: 4px 0 0;
  }
  .strength-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 600;
    background: #2E3440;
    color: #FAFAFA;
  }
  .note-chip {
    display: inline-block;
    background: #2E3440;
    border-radius: 8px;
    padding: 4px 10px;
    margin: 3px;
    font-size: 0.8rem;
    color: #aaa;
  }
  .tag-chip {
    display: inline-block;
    background: #1a3a2a;
    border-radius: 8px;
    padding: 2px 8px;
    margin: 2px;
    font-size: 0.75rem;
    color: #4CAF50;
  }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────
st.title("👥 Contact Profile Cards")
st.caption("All contacts with their wish history, notes, and connection strength.")
st.divider()

# ──────────────────────────────────────────────
# SIDEBAR FILTERS
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Search & Filter")
    search = st.text_input("Search contacts", placeholder="Type a name...")
    strength_filter = st.selectbox(
        "Filter by strength",
        ["All", "⭐ Very Strong", "💙 Strong", "🟢 Moderate", "🟡 Weak", "🔴 Fading"],
    )
    sort_by = st.selectbox("Sort by", ["Name A-Z", "Most Interactions", "Recently Active"])
    st.divider()
    st.caption(f"🗄️ Database: {DB_FILE.name}")

# ──────────────────────────────────────────────
# LOAD CONTACTS
# ──────────────────────────────────────────────
all_contacts = get_all_contacts()

if not all_contacts:
    st.info("📭 No contacts found. Run the agent first to populate data.")
    st.stop()

# Apply search filter
if search:
    all_contacts = [c for c in all_contacts if search.lower() in c.lower()]

# Apply strength filter
if strength_filter != "All":
    emoji = strength_filter.split()[0]
    filtered = []
    for c in all_contacts:
        s = get_strength(c)
        if s["emoji"] == emoji:
            filtered.append(c)
    all_contacts = filtered

# ──────────────────────────────────────────────
# STATS BAR
# ──────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("👥 Total Contacts", len(all_contacts))
col2.metric("📝 With Notes",
            sum(1 for c in all_contacts if get_contact_notes(c)))
col3.metric("🧠 With Memory",
            sum(1 for c in all_contacts if get_contact_memory(c)))
col4.metric("⭐ Strong+",
            sum(1 for c in all_contacts if get_strength(c)["score"] >= 61))

st.divider()

# ──────────────────────────────────────────────
# PROFILE CARDS GRID
# ──────────────────────────────────────────────
if not all_contacts:
    st.warning("No contacts match your filters.")
    st.stop()

# 2 columns grid
cols = st.columns(2)

for idx, contact in enumerate(all_contacts):
    col = cols[idx % 2]

    with col:
        history  = get_contact_history(contact)
        memory   = get_contact_memory(contact)
        notes    = get_contact_notes(contact)
        strength = get_strength(contact)

        live_history = [h for h in history if not h["dry_run"]]
        last_date    = live_history[0]["date"] if live_history else "Never"
        wish_count   = len(live_history)

        job_title = memory.get("job_title", "")
        company   = memory.get("company", "")
        job_line  = f"{job_title} @ {company}" if job_title and company \
                    else job_title or company or "No profile data"

        with st.container():
            # Card header
            h_col1, h_col2 = st.columns([3, 1])
            with h_col1:
                st.markdown(f"### 👤 {contact}")
                st.caption(f"💼 {job_line}")
            with h_col2:
                st.markdown(
                    f'<span class="strength-badge">'
                    f'{strength["emoji"]} {strength["level"]}'
                    f'</span>',
                    unsafe_allow_html=True,
                )

            # Stats row
            s1, s2, s3 = st.columns(3)
            s1.metric("🎂 Wishes", wish_count)
            s2.metric("📅 Last Wish", last_date)
            s3.metric("💪 Score", f"{strength['score']}/100")

            # Memory life event
            if memory.get("life_event"):
                st.info(f"💡 {memory['life_event']}")

            # Interests
            if memory.get("interests"):
                interests_str = " • ".join(memory["interests"][:4])
                st.caption(f"🎯 Interests: {interests_str}")

            # Notes section
            with st.expander(f"📝 Notes ({len(notes)})"):
                if notes:
                    for n in notes:
                        n_col1, n_col2 = st.columns([5, 1])
                        with n_col1:
                            tag_html = "".join(
                                f'<span class="tag-chip">#{t.strip()}</span>'
                                for t in n["tags"] if t.strip()
                            )
                            st.markdown(
                                f'<div class="note-chip">{n["note"]}</div>'
                                f'{tag_html}',
                                unsafe_allow_html=True,
                            )
                            st.caption(f"Added: {n['created_at'][:10]}")
                        with n_col2:
                            if st.button("🗑️", key=f"del_{n['id']}"):
                                delete_note(n["id"])
                                st.rerun()
                else:
                    st.caption("No notes yet.")

                # Add new note
                new_note = st.text_area(
                    "Add a note", key=f"note_{contact}",
                    placeholder="e.g. Met at Google I/O, loves cricket...",
                    height=80,
                )
                new_tags = st.text_input(
                    "Tags (comma-separated)", key=f"tags_{contact}",
                    placeholder="personal, work, sensitive",
                )
                if st.button("💾 Save Note", key=f"save_{contact}"):
                    if new_note.strip():
                        save_note(contact, new_note.strip(), new_tags.strip())
                        st.success("Note saved!")
                        st.rerun()
                    else:
                        st.warning("Note cannot be empty.")

            # Wish history
            with st.expander(f"🕐 Wish History ({wish_count})"):
                if live_history:
                    for h in live_history[:5]:
                        st.markdown(f"**{h['date']}** — {h['task']}")
                        st.caption(f"💬 {h['message'][:100]}...")
                        st.divider()
                else:
                    st.caption("No live wishes sent yet.")

            st.divider()

# ──────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────
st.caption("🎂 Birthday Wishes Agent v4.0 — Contact Profile Cards")