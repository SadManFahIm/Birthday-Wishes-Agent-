"""
contact_notes.py
────────────────
Contact Notes module for Birthday Wishes Agent.

Allows saving personal notes for each LinkedIn contact.
Notes are stored in SQLite and can be retrieved before
wishing or replying to make interactions more personal.

Examples:
  - "Met at Google I/O 2024"
  - "Loves cricket, supports CSK"
  - "Mentioned he's moving to Canada next year"
  - "Prefers formal communication"
  - "Don't mention work — going through a tough time"

Features:
  - Add, update, delete, and view notes per contact
  - Notes are injected into wish/reply prompts automatically
  - Tag-based organization (e.g. #personal, #work, #sensitive)
  - Timestamp tracking for each note

Usage:
    from contact_notes import (add_note, get_notes,
                                build_notes_context)
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_notes_table():
    """Create the contact notes table if it doesn't exist."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contact_notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                contact    TEXT    NOT NULL,
                note       TEXT    NOT NULL,
                tags       TEXT,
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  Contact notes table ready.")


# ──────────────────────────────────────────────
# ADD / UPDATE NOTE
# ──────────────────────────────────────────────
def add_note(contact: str, note: str, tags: list[str] = None) -> int:
    """
    Add a new note for a contact.

    Args:
        contact : Contact's name
        note    : The note text
        tags    : Optional list of tags e.g. ["personal", "sensitive"]

    Returns:
        ID of the new note.
    """
    tags_str = ", ".join(tags) if tags else ""
    now      = datetime.now().isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute(
            "INSERT INTO contact_notes (contact, note, tags, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (contact, note, tags_str, now, now),
        )
        note_id = cursor.lastrowid
        conn.commit()

    logger.info("📝 Note added for %s (ID: %d)", contact, note_id)
    return note_id


def update_note(note_id: int, note: str, tags: list[str] = None):
    """Update an existing note by ID."""
    tags_str = ", ".join(tags) if tags else ""
    now      = datetime.now().isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "UPDATE contact_notes SET note = ?, tags = ?, updated_at = ? WHERE id = ?",
            (note, tags_str, now, note_id),
        )
        conn.commit()
    logger.info("✏️  Note #%d updated.", note_id)


def delete_note(note_id: int):
    """Delete a note by ID."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM contact_notes WHERE id = ?", (note_id,))
        conn.commit()
    logger.info("🗑️  Note #%d deleted.", note_id)


# ──────────────────────────────────────────────
# GET NOTES
# ──────────────────────────────────────────────
def get_notes(contact: str) -> list[dict]:
    """
    Get all notes for a contact.

    Args:
        contact : Contact's name (case-insensitive)

    Returns:
        List of note dicts with id, note, tags, created_at, updated_at
    """
    if not DB_FILE.exists():
        return []

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT id, note, tags, created_at, updated_at "
            "FROM contact_notes "
            "WHERE LOWER(contact) = LOWER(?) "
            "ORDER BY created_at DESC",
            (contact,),
        ).fetchall()

    notes = [
        {
            "id":         row[0],
            "note":       row[1],
            "tags":       [t.strip() for t in row[2].split(",")] if row[2] else [],
            "created_at": row[3],
            "updated_at": row[4],
        }
        for row in rows
    ]

    logger.info("📋 Found %d note(s) for %s", len(notes), contact)
    return notes


def get_all_contacts_with_notes() -> list[str]:
    """Return a list of all contacts that have notes."""
    if not DB_FILE.exists():
        return []
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT DISTINCT contact FROM contact_notes ORDER BY contact"
        ).fetchall()
    return [row[0] for row in rows]


def search_notes(query: str) -> list[dict]:
    """
    Search notes by keyword across all contacts.

    Args:
        query : Search keyword

    Returns:
        List of matching note dicts with contact name included.
    """
    if not DB_FILE.exists():
        return []

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            "SELECT id, contact, note, tags, created_at "
            "FROM contact_notes "
            "WHERE LOWER(note) LIKE LOWER(?) OR LOWER(tags) LIKE LOWER(?)"
            "ORDER BY created_at DESC",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()

    return [
        {
            "id":         row[0],
            "contact":    row[1],
            "note":       row[2],
            "tags":       [t.strip() for t in row[3].split(",")] if row[3] else [],
            "created_at": row[4],
        }
        for row in rows
    ]


# ──────────────────────────────────────────────
# BUILD NOTES CONTEXT (for agent prompts)
# ──────────────────────────────────────────────
def build_notes_context(contact: str) -> str:
    """
    Build a natural language notes context string for a contact.
    This is injected into wish/reply prompts.

    Returns:
        A formatted string of notes, or empty string if none.
    """
    notes = get_notes(contact)
    if not notes:
        return ""

    lines = []
    for n in notes:
        tag_str = f" [{', '.join(n['tags'])}]" if n["tags"] else ""
        lines.append(f"  • {n['note']}{tag_str}")

    context = "\n".join(lines)
    logger.info("📋 Notes context built for %s (%d notes)", contact, len(notes))
    return context


# ──────────────────────────────────────────────
# NOTES INSTRUCTIONS (for browser agent)
# ──────────────────────────────────────────────
def build_notes_instructions(contact: str) -> str:
    """
    Build notes-aware instructions for the browser agent.
    Injects personal notes into the wish/reply prompt.
    """
    notes_context = build_notes_context(contact)

    if not notes_context:
        return ""

    return f"""
  PERSONAL NOTES FOR {contact.upper()}:
  The following notes have been saved about this contact.
  Use them to make your message more personal and thoughtful.
  Be subtle — do not directly quote the notes.

{notes_context}

  Examples of how to use notes naturally:
  - Note: "Loves cricket" → mention "Hope you caught the match!" if relevant
  - Note: "Moving to Canada" → "Hope the move is going smoothly!"
  - Note: "Sensitive about work" → avoid mentioning work at all
  - Note: "Prefers formal tone" → use formal language in reply
"""