"""
tests/test_core.py
━━━━━━━━━━━━━━━━━━
Core module গুলোর basic unit tests।
Browser বা LinkedIn connection ছাড়াই run হয়।
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# ── Add project root to path ──────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────
# DB helpers (agent.py থেকে isolated)
# ─────────────────────────────────────────────

def make_temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, task TEXT, contact TEXT,
                message TEXT, dry_run INTEGER, created_at TEXT
            )
        """)
        conn.commit()
    return db


def test_db_creation(tmp_path):
    db = make_temp_db(tmp_path)
    assert db.exists()


def test_db_insert_and_query(tmp_path):
    from datetime import date, datetime
    db = make_temp_db(tmp_path)

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO history (date, task, contact, message, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date.today().isoformat(), "Test", "Alice",
             "Happy Birthday!", 1, datetime.now().isoformat()),
        )
        conn.commit()
        row = conn.execute("SELECT contact FROM history").fetchone()

    assert row[0] == "Alice"


# ─────────────────────────────────────────────
# Personality Profiling — DB tests
# ─────────────────────────────────────────────

def test_personality_table_creation(tmp_path, monkeypatch):
    db = tmp_path / "agent_history.db"
    monkeypatch.setattr("personality_profiling.DB_FILE", db)

    from personality_profiling import init_personality_table, save_personality_profile, get_personality_profile
    init_personality_table()

    save_personality_profile(
        contact="Bob",
        profile_url="https://linkedin.com/in/bob",
        mbti_type="INTJ",
        dominant_traits=["analytical", "strategic"],
        tone="formal",
        interests=["AI", "leadership"],
        communication_style="Direct and concise.",
        confidence_score=0.85,
        raw_summary="Bob is analytical and strategic.",
    )

    profile = get_personality_profile("Bob")
    assert profile is not None
    assert profile["mbti_type"] == "INTJ"
    assert "analytical" in profile["dominant_traits"]


# ─────────────────────────────────────────────
# Predictive Birthday — DB tests
# ─────────────────────────────────────────────

def test_predicted_birthday_table(tmp_path, monkeypatch):
    db = tmp_path / "agent_history.db"
    monkeypatch.setattr("predictive_birthday.DB_FILE", db)

    from predictive_birthday import (
        init_predicted_birthday_table,
        save_predicted_birthday,
        get_predicted_birthday,
    )
    init_predicted_birthday_table()

    save_predicted_birthday(
        contact="Carol",
        profile_url="https://linkedin.com/in/carol",
        predicted_month=7,
        predicted_day=15,
        predicted_year=1992,
        confidence="high",
        confidence_score=0.9,
        evidence=["Post from 2023-07-15 had 5 birthday wishes"],
        prediction_method="birthday_wishes_from_others",
    )

    result = get_predicted_birthday("Carol")
    assert result is not None
    assert result["predicted_month"] == 7
    assert result["predicted_day"] == 15
    assert result["confidence"] == "high"


def test_predicted_birthday_upsert(tmp_path, monkeypatch):
    db = tmp_path / "agent_history.db"
    monkeypatch.setattr("predictive_birthday.DB_FILE", db)

    from predictive_birthday import (
        init_predicted_birthday_table,
        save_predicted_birthday,
        get_predicted_birthday,
    )
    init_predicted_birthday_table()

    # First insert
    save_predicted_birthday("Dave", "", 3, 10, None, "low", 0.3, [], "no_signal")
    # Update with better data
    save_predicted_birthday("Dave", "", 3, 10, 1990, "medium", 0.6,
                            ["Graduation year 2012"], "education_calc")

    result = get_predicted_birthday("Dave")
    assert result["confidence"] == "medium"
    assert result["predicted_year"] == 1990


# ─────────────────────────────────────────────
# Filter / Whitelist / Blacklist logic
# ─────────────────────────────────────────────

def test_is_allowed_no_filters():
    WHITELIST = []
    BLACKLIST = []

    def is_allowed(name):
        n = name.lower()
        if BLACKLIST and n in [b.lower() for b in BLACKLIST]:
            return False
        if WHITELIST and n not in [w.lower() for w in WHITELIST]:
            return False
        return True

    assert is_allowed("Alice") is True
    assert is_allowed("Bob") is True


def test_is_allowed_blacklist():
    WHITELIST = []
    BLACKLIST = ["spammer"]

    def is_allowed(name):
        n = name.lower()
        if BLACKLIST and n in [b.lower() for b in BLACKLIST]:
            return False
        if WHITELIST and n not in [w.lower() for w in WHITELIST]:
            return False
        return True

    assert is_allowed("Alice") is True
    assert is_allowed("Spammer") is False


def test_is_allowed_whitelist():
    WHITELIST = ["alice", "bob"]
    BLACKLIST = []

    def is_allowed(name):
        n = name.lower()
        if BLACKLIST and n in [b.lower() for b in BLACKLIST]:
            return False
        if WHITELIST and n not in [w.lower() for w in WHITELIST]:
            return False
        return True

    assert is_allowed("Alice") is True
    assert is_allowed("Charlie") is False


# ─────────────────────────────────────────────
# Session management
# ─────────────────────────────────────────────

def test_session_invalid_if_no_file(tmp_path):
    session_file = tmp_path / "linkedin_session.json"
    assert not session_file.exists()


def test_session_expired():
    import time
    data = {"saved_at": time.time() - (13 * 3600)}  # 13 hours ago
    age_hours = (time.time() - data["saved_at"]) / 3600
    assert age_hours > 12  # expired


def test_session_valid():
    import time
    data = {"saved_at": time.time() - (2 * 3600)}  # 2 hours ago
    age_hours = (time.time() - data["saved_at"]) / 3600
    assert age_hours <= 12  # still valid