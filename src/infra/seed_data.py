"""
Seed Data — Birthday Wishes Agent v10.0
=========================================
Realistic test/demo data for all modules. Extracted from
autonomous_agent.py's inline _demo_contacts() and expanded
to seed every table with coherent, interconnected data.

Usage:
  python seed_data.py                # seed the DB
  python seed_data.py --reset        # clear + re-seed
  python seed_data.py --status       # show current row counts
  python seed_data.py --self-test    # run self-test on temp DB

NEVER auto-runs in production — only when explicitly called.

Integration:
  from seed_data import demo_contacts, seed_all_tables
  contacts = demo_contacts()        # returns the 6 original contacts
  seed_all_tables(db_path)           # fills everything

Author : Fahim (SadManFahIm)
Branch : feature/clean-demo-data (→ 10.0)
"""

import sqlite3
import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("BWA_DB_PATH", "agent_history.db"))

# ──────────────────────────────────────────────────────────────
# Original demo contacts (backward-compatible IDs/names)
# ──────────────────────────────────────────────────────────────


def demo_contacts() -> list[dict]:
    """
    The original 6 demo contacts from autonomous_agent.py.
    IDs and names preserved for backward compatibility.
    """
    today = datetime.now().strftime("%m-%d")
    return [
        {"contact_id": "urn_rakib_001", "contact_name": "Rakib Hossain",
         "tier": "Close Friend", "tier_score": 9.0,
         "platform": "LinkedIn", "birthday": today},
        {"contact_id": "urn_nadia_002", "contact_name": "Nadia Islam",
         "tier": "Colleague", "tier_score": 7.0,
         "platform": "WhatsApp"},
        {"contact_id": "urn_tanvir_003", "contact_name": "Tanvir Ahmed",
         "tier": "Colleague", "tier_score": 5.0,
         "platform": "LinkedIn"},
        {"contact_id": "urn_mim_004", "contact_name": "Mim Chowdhury",
         "tier": "Close Friend", "tier_score": 9.5,
         "platform": "WhatsApp", "birthday": today},
        {"contact_id": "urn_sara_005", "contact_name": "Sara Khan",
         "tier": "Acquaintance", "tier_score": 3.0,
         "platform": "LinkedIn"},
        {"contact_id": "urn_farah_007", "contact_name": "Farah Akter",
         "tier": "Acquaintance", "tier_score": 2.0,
         "platform": "LinkedIn"},
    ]


# ──────────────────────────────────────────────────────────────
# Extended contacts (20 total across 5 tiers)
# ──────────────────────────────────────────────────────────────

_EXTENDED_CONTACTS = [
    # Original 6 (keep same IDs)
    ("urn_rakib_001", "Rakib Hossain", "Close Friend", 9.0, "LinkedIn", True, 0),
    ("urn_nadia_002", "Nadia Islam", "Colleague", 7.0, "WhatsApp", False, 1),
    ("urn_tanvir_003", "Tanvir Ahmed", "Colleague", 5.0, "LinkedIn", False, 2),
    ("urn_mim_004", "Mim Chowdhury", "Close Friend", 9.5, "WhatsApp", True, 0),
    ("urn_sara_005", "Sara Khan", "Acquaintance", 3.0, "LinkedIn", False, 3),
    ("urn_farah_007", "Farah Akter", "Acquaintance", 2.0, "LinkedIn", False, 4),
    # 14 new contacts
    ("urn_arif_008", "Arif Rahman", "Close Friend", 9.2, "WhatsApp", True, 5),
    ("urn_priya_009", "Priya Das", "Professional", 6.5, "LinkedIn", False, 1),
    ("urn_kamal_010", "Kamal Uddin", "Colleague", 7.5, "Telegram", False, 2),
    ("urn_rima_011", "Rima Sultana", "Close Friend", 8.8, "WhatsApp", True, 0),
    ("urn_fahim_012", "Sadia Fahim", "Professional", 6.0, "Email", False, 3),
    ("urn_imran_013", "Imran Hossain", "Acquaintance", 4.0, "LinkedIn", False, 6),
    ("urn_tania_014", "Tania Akhter", "Colleague", 5.5, "Slack", False, 4),
    ("urn_rifat_015", "Rifat Islam", "Professional", 6.8, "LinkedIn", False, 5),
    ("urn_joya_016", "Joya Rahman", "Close Friend", 8.5, "Instagram", False, 1),
    ("urn_abir_017", "Abir Hasan", "Colleague", 7.2, "WhatsApp", False, 2),
    ("urn_lamia_018", "Lamia Khatun", "Acquaintance", 3.5, "Facebook", False, 3),
    ("urn_rohan_019", "Rohan Mia", "Professional", 5.8, "Twitter", False, 6),
    ("urn_nusrat_020", "Nusrat Jahan", "Close Friend", 9.0, "WhatsApp", True, 0),
    ("urn_sabbir_021", "Sabbir Ahmed", "Acquaintance", 2.5, "LinkedIn", False, 5),
]

_INTERESTS = [
    "AI", "Python", "Photography", "Cricket", "Cooking",
    "Travel", "Music", "Startups", "Design", "Reading",
    "Fitness", "Gaming", "Gardening", "Movies", "Teaching",
]


# ──────────────────────────────────────────────────────────────
# Table creation helper
# ──────────────────────────────────────────────────────────────


def _ensure_tables(conn: sqlite3.Connection) -> None:
    """Create all tables that seed_data populates."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contact_tier (
            contact_id TEXT PRIMARY KEY, contact_name TEXT,
            current_tier TEXT, tier_score REAL);
        CREATE TABLE IF NOT EXISTS contact_life_events (
            id TEXT PRIMARY KEY, contact_id TEXT,
            event_type TEXT, event_date TEXT);
        CREATE TABLE IF NOT EXISTS vip_contacts (
            contact_id TEXT PRIMARY KEY, reason TEXT,
            added_at TEXT);
        CREATE TABLE IF NOT EXISTS graph_nodes (
            contact_id TEXT PRIMARY KEY, platform TEXT);
        CREATE TABLE IF NOT EXISTS wish_outcome_log (
            id TEXT PRIMARY KEY, contact_id TEXT,
            sent_at TEXT, replied INTEGER DEFAULT 0,
            platform TEXT, wish_text TEXT);
        CREATE TABLE IF NOT EXISTS interest_signals (
            id TEXT PRIMARY KEY, contact_id TEXT,
            interest TEXT, weight REAL, source TEXT,
            detected_at TEXT);
        CREATE TABLE IF NOT EXISTS interest_profiles (
            contact_id TEXT, interest TEXT,
            weight REAL, updated_at TEXT,
            PRIMARY KEY (contact_id, interest));
        CREATE TABLE IF NOT EXISTS gdpr_consent (
            id TEXT PRIMARY KEY, contact_id TEXT,
            consent_type TEXT, granted INTEGER,
            granted_at TEXT, source TEXT,
            created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS rl_platform_quotas (
            platform TEXT PRIMARY KEY, daily_limit INTEGER,
            hourly_limit INTEGER, per_minute_limit INTEGER,
            cooldown_days INTEGER, is_enabled INTEGER DEFAULT 1,
            auto_pause INTEGER DEFAULT 1,
            updated_at TEXT);
        CREATE TABLE IF NOT EXISTS autonomous_decisions (
            id TEXT PRIMARY KEY, contact_id TEXT,
            contact_name TEXT, action TEXT,
            reason TEXT, decided_at TEXT,
            executed INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS reply_sentiment_log (
            id TEXT PRIMARY KEY, contact_id TEXT,
            sentiment TEXT, score REAL, analyzed_at TEXT);
        CREATE TABLE IF NOT EXISTS churn_predictions (
            contact_id TEXT PRIMARY KEY,
            churn_prob REAL, churn_label TEXT,
            predicted_at TEXT);
    """)
    conn.commit()


# ──────────────────────────────────────────────────────────────
# Seed functions
# ──────────────────────────────────────────────────────────────


def _uid() -> str:
    return str(uuid.uuid4())


def _ts(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc)
            - timedelta(days=days_ago)).isoformat()


def seed_contacts(conn: sqlite3.Connection) -> int:
    """Seed 20 contacts across 5 tiers."""
    now = datetime.now(timezone.utc)
    count = 0
    for cid, name, tier, score, platform, is_vip, bday_offset in _EXTENDED_CONTACTS:
        conn.execute(
            "INSERT OR REPLACE INTO contact_tier VALUES (?,?,?,?)",
            (cid, name, tier, score))
        conn.execute(
            "INSERT OR REPLACE INTO graph_nodes VALUES (?,?)",
            (cid, platform))

        # Birthday spread across the week
        bday = now + timedelta(days=bday_offset)
        conn.execute(
            "INSERT OR REPLACE INTO contact_life_events VALUES (?,?,?,?)",
            (_uid(), cid, "birthday",
             f"1995-{bday.strftime('%m-%d')}"))

        if is_vip:
            conn.execute(
                "INSERT OR REPLACE INTO vip_contacts VALUES (?,?,?)",
                (cid, f"Top {tier}", _ts()))
        count += 1
    conn.commit()
    return count


def seed_wish_history(conn: sqlite3.Connection) -> int:
    """Seed sample wish history for half the contacts."""
    count = 0
    sentiments = ["positive", "neutral", "grateful", "warm"]
    for i, (cid, name, _, _, platform, _, _) in enumerate(_EXTENDED_CONTACTS[:10]):
        days_ago = 30 + i * 15  # staggered history
        conn.execute(
            "INSERT OR REPLACE INTO wish_outcome_log VALUES (?,?,?,?,?,?)",
            (_uid(), cid, _ts(days_ago), 1 if i % 3 == 0 else 0,
             platform, f"Happy Birthday {name}! Hope you have a great day!"))

        # Sentiment for those who replied
        if i % 3 == 0:
            conn.execute(
                "INSERT OR REPLACE INTO reply_sentiment_log VALUES (?,?,?,?,?)",
                (_uid(), cid, sentiments[i % len(sentiments)],
                 0.7 + (i % 4) * 0.08, _ts(days_ago - 1)))
        count += 1
    conn.commit()
    return count


def seed_interests(conn: sqlite3.Connection) -> int:
    """Seed 2-4 interests per contact."""
    count = 0
    for i, (cid, *_) in enumerate(_EXTENDED_CONTACTS):
        n_interests = 2 + (i % 3)  # 2, 3, or 4
        for j in range(n_interests):
            interest = _INTERESTS[(i + j) % len(_INTERESTS)]
            weight = 0.5 + (j * 0.15)
            conn.execute(
                "INSERT OR REPLACE INTO interest_signals VALUES (?,?,?,?,?,?)",
                (_uid(), cid, interest, weight, "linkedin", _ts(i)))
            conn.execute(
                "INSERT OR REPLACE INTO interest_profiles VALUES (?,?,?,?)",
                (cid, interest, weight, _ts(i)))
            count += 1
    conn.commit()
    return count


def seed_consent(conn: sqlite3.Connection) -> int:
    """Seed consent records — most granted, a few revoked."""
    count = 0
    for i, (cid, *_) in enumerate(_EXTENDED_CONTACTS):
        granted = 0 if i in (12, 17) else 1  # 2 revoked
        conn.execute(
            "INSERT OR REPLACE INTO gdpr_consent VALUES (?,?,?,?,?,?,?,?)",
            (_uid(), cid, "birthday_wish", granted,
             _ts(60) if granted else None,
             "import", _ts(90), _ts(60)))
        count += 1
    conn.commit()
    return count


def seed_rate_limits(conn: sqlite3.Connection) -> int:
    """Seed rate limit quotas for all platforms."""
    quotas = [
        ("linkedin", 25, 10, 3, 30),
        ("whatsapp", 50, 20, 5, 7),
        ("telegram", 100, 40, 10, 7),
        ("email", 200, 50, 10, 30),
        ("twitter", 30, 10, 2, 30),
        ("instagram", 20, 8, 2, 30),
        ("slack", 100, 30, 5, 1),
        ("facebook", 30, 10, 3, 30),
        ("wechat", 40, 15, 3, 14),
        ("line", 50, 20, 5, 14),
    ]
    for plat, daily, hourly, per_min, cooldown in quotas:
        conn.execute(
            "INSERT OR REPLACE INTO rl_platform_quotas VALUES (?,?,?,?,?,1,1,?)",
            (plat, daily, hourly, per_min, cooldown, _ts()))
    conn.commit()
    return len(quotas)


def seed_churn_predictions(conn: sqlite3.Connection) -> int:
    """Seed churn predictions based on tier scores."""
    count = 0
    for cid, _, tier, score, *_ in _EXTENDED_CONTACTS:
        # Low tier = higher churn probability
        prob = max(0.05, min(0.95, 1.0 - (score / 10.0)))
        label = ("high" if prob > 0.6 else
                 "medium" if prob > 0.3 else "low")
        conn.execute(
            "INSERT OR REPLACE INTO churn_predictions VALUES (?,?,?,?)",
            (cid, round(prob, 3), label, _ts()))
        count += 1
    conn.commit()
    return count


def seed_autonomous_decisions(conn: sqlite3.Connection) -> int:
    """Seed a few sample agent decisions for today."""
    actions = [
        ("urn_rakib_001", "Rakib Hossain", "birthday_wish",
         "Birthday today, Close Friend tier"),
        ("urn_mim_004", "Mim Chowdhury", "birthday_wish",
         "Birthday today, VIP contact"),
        ("urn_nadia_002", "Nadia Islam", "checkin",
         "No contact in 45 days, decay risk"),
        ("urn_sara_005", "Sara Khan", "skip",
         "Low tier, no birthday, recent contact"),
    ]
    for cid, name, action, reason in actions:
        conn.execute(
            "INSERT OR REPLACE INTO autonomous_decisions VALUES (?,?,?,?,?,?,0)",
            (_uid(), cid, name, action, reason, _ts()))
    conn.commit()
    return len(actions)


# ──────────────────────────────────────────────────────────────
# Main seed orchestrator
# ──────────────────────────────────────────────────────────────


def seed_all_tables(db_path: Path = DB_PATH) -> dict:
    """
    Populate ALL tables with realistic, interconnected test data.
    Returns counts per section.
    """
    conn = sqlite3.connect(db_path)
    _ensure_tables(conn)

    results = {
        "contacts": seed_contacts(conn),
        "wish_history": seed_wish_history(conn),
        "interests": seed_interests(conn),
        "consent": seed_consent(conn),
        "rate_limits": seed_rate_limits(conn),
        "churn_predictions": seed_churn_predictions(conn),
        "autonomous_decisions": seed_autonomous_decisions(conn),
    }

    conn.close()
    total = sum(results.values())
    results["total_rows"] = total
    return results


def reset_and_seed(db_path: Path = DB_PATH) -> dict:
    """Clear all seeded tables and re-seed from scratch."""
    conn = sqlite3.connect(db_path)
    _ensure_tables(conn)

    tables_to_clear = [
        "contact_tier", "contact_life_events", "vip_contacts",
        "graph_nodes", "wish_outcome_log", "interest_signals",
        "interest_profiles", "gdpr_consent", "rl_platform_quotas",
        "autonomous_decisions", "reply_sentiment_log",
        "churn_predictions",
    ]
    for tbl in tables_to_clear:
        try:
            conn.execute(f"DELETE FROM {tbl}")
        except Exception:
            pass
    conn.commit()
    conn.close()

    return seed_all_tables(db_path)


def get_status(db_path: Path = DB_PATH) -> dict:
    """Show current row counts for all seeded tables."""
    conn = sqlite3.connect(db_path)
    _ensure_tables(conn)

    tables = [
        "contact_tier", "contact_life_events", "vip_contacts",
        "graph_nodes", "wish_outcome_log", "interest_signals",
        "interest_profiles", "gdpr_consent", "rl_platform_quotas",
        "autonomous_decisions", "reply_sentiment_log",
        "churn_predictions",
    ]
    counts = {}
    for tbl in tables:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
            counts[tbl] = row[0]
        except Exception:
            counts[tbl] = -1
    conn.close()

    counts["total"] = sum(v for v in counts.values() if v > 0)
    return counts


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test on temp DB."""
    import tempfile

    print("=" * 60)
    print("Seed Data — Self-Test")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    try:
        # 1. demo_contacts backward compat
        print("\n[1/7] demo_contacts() ...")
        dc = demo_contacts()
        assert len(dc) == 6
        assert dc[0]["contact_id"] == "urn_rakib_001"
        assert dc[0]["contact_name"] == "Rakib Hossain"
        assert dc[3]["contact_id"] == "urn_mim_004"
        print("      ✅ 6 contacts, IDs match original")

        # 2. seed_all_tables
        print("[2/7] seed_all_tables ...")
        result = seed_all_tables(tdb)
        assert result["contacts"] == 20
        assert result["rate_limits"] == 10
        assert result["consent"] == 20
        assert result["total_rows"] > 100
        print(f"      ✅ {result['total_rows']} total rows seeded")

        # 3. Verify contacts
        print("[3/7] Verify contacts ...")
        conn = sqlite3.connect(tdb)
        ct = conn.execute("SELECT COUNT(*) FROM contact_tier").fetchone()[0]
        assert ct == 20
        vip = conn.execute("SELECT COUNT(*) FROM vip_contacts").fetchone()[0]
        assert vip == 5
        tiers = conn.execute(
            "SELECT current_tier, COUNT(*) FROM contact_tier GROUP BY current_tier"
        ).fetchall()
        tier_names = {r[0] for r in tiers}
        assert "Close Friend" in tier_names
        assert "Colleague" in tier_names
        assert "Professional" in tier_names
        assert "Acquaintance" in tier_names
        conn.close()
        print(f"      ✅ 20 contacts, 5 VIPs, {len(tier_names)} tiers")

        # 4. Verify interests spread
        print("[4/7] Verify interests ...")
        conn = sqlite3.connect(tdb)
        signals = conn.execute(
            "SELECT COUNT(*) FROM interest_signals").fetchone()[0]
        assert signals >= 40
        distinct = conn.execute(
            "SELECT COUNT(DISTINCT interest) FROM interest_signals"
        ).fetchone()[0]
        assert distinct >= 10
        conn.close()
        print(f"      ✅ {signals} signals, {distinct} distinct interests")

        # 5. Verify consent
        print("[5/7] Verify consent ...")
        conn = sqlite3.connect(tdb)
        granted = conn.execute(
            "SELECT COUNT(*) FROM gdpr_consent WHERE granted=1"
        ).fetchone()[0]
        revoked = conn.execute(
            "SELECT COUNT(*) FROM gdpr_consent WHERE granted=0"
        ).fetchone()[0]
        assert granted == 18
        assert revoked == 2
        conn.close()
        print(f"      ✅ {granted} granted, {revoked} revoked")

        # 6. Reset and re-seed
        print("[6/7] Reset + re-seed ...")
        result2 = reset_and_seed(tdb)
        assert result2["contacts"] == 20
        status = get_status(tdb)
        assert status["contact_tier"] == 20
        print(f"      ✅ Reset clean, re-seeded {result2['total_rows']} rows")

        # 7. Status
        print("[7/7] Status check ...")
        s = get_status(tdb)
        assert s["total"] > 100
        assert s["rl_platform_quotas"] == 10
        print(f"      ✅ Total: {s['total']} rows across "
              f"{sum(1 for v in s.values() if isinstance(v, int) and v > 0)} tables")

        print("\n" + "=" * 60)
        print("✅ ALL SEED DATA SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(tdb)


# ──────────────────────────────────────────────────────────────
# CLI entry point — NEVER auto-runs
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        _self_test()
    elif "--reset" in sys.argv:
        print("Resetting and re-seeding...")
        result = reset_and_seed()
        print(f"Done! Seeded {result['total_rows']} rows:")
        for k, v in result.items():
            if k != "total_rows":
                print(f"  {k}: {v}")
    elif "--status" in sys.argv:
        import json
        print(json.dumps(get_status(), indent=2))
    else:
        print("Seeding database...")
        result = seed_all_tables()
        print(f"Done! Seeded {result['total_rows']} rows:")
        for k, v in result.items():
            if k != "total_rows":
                print(f"  {k}: {v}")
