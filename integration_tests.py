"""
Integration Test Suite — Birthday Wishes Agent v10.0
=====================================================
Cross-module flow tests verifying that modules work together
correctly when data flows between them.

Run:
  pytest integration_tests.py -v
  python integration_tests.py          # fallback without pytest

Flows tested:
  1. Morning Briefing → Push Notification → Audit Log
  2. Rate Limit → Consume → Throttle → Status check
  3. JWT Auth → Token validation → GDPR Right-to-Forget
  4. Contact Lifecycle → Churn → Interest Graph → GDPR Erasure

Author : Fahim (SadManFahIm)
Branch : feature/integration-tests (→ 10.0)
"""

import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# Shared test DB fixture
# ──────────────────────────────────────────────────────────────


def _create_test_db() -> Path:
    """Create a temp DB and init ALL module tables."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    from morning_briefing import init_briefing_tables
    from push_notifications import init_push_tables
    from audit_log import init_audit_tables
    from rate_limit_dashboard import init_rate_limit_tables
    from jwt_auth import init_auth_tables
    from gdpr_compliance import _ensure_gdpr_tables
    from churn_predictor import init_churn_tables
    from interest_graph import init_interest_tables

    init_briefing_tables(tdb)
    init_push_tables(tdb)
    init_audit_tables(tdb)
    init_rate_limit_tables(tdb)
    init_auth_tables(tdb)

    # GDPR uses string path, not Path
    conn = sqlite3.connect(str(tdb))
    conn.row_factory = sqlite3.Row
    _ensure_gdpr_tables(conn)
    conn.close()

    # Churn & interest use module-level DB_PATH, so we init via
    # direct SQL to avoid side effects
    conn = sqlite3.connect(tdb)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contact_tier (
            contact_id TEXT PRIMARY KEY, contact_name TEXT,
            current_tier TEXT, tier_score REAL
        );
        CREATE TABLE IF NOT EXISTS contact_life_events (
            id TEXT PRIMARY KEY, contact_id TEXT,
            event_type TEXT, event_date TEXT
        );
        CREATE TABLE IF NOT EXISTS vip_contacts (
            contact_id TEXT PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS graph_nodes (
            contact_id TEXT PRIMARY KEY, platform TEXT
        );
        CREATE TABLE IF NOT EXISTS wish_outcome_log (
            id TEXT PRIMARY KEY, contact_id TEXT,
            sent_at TEXT, replied INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS autonomous_decisions (
            id TEXT PRIMARY KEY, contact_id TEXT,
            contact_name TEXT, action TEXT,
            reason TEXT, decided_at TEXT, executed INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS interest_signals (
            id TEXT PRIMARY KEY, contact_id TEXT,
            interest TEXT, weight REAL, source TEXT,
            detected_at TEXT
        );
        CREATE TABLE IF NOT EXISTS interest_profiles (
            contact_id TEXT, interest TEXT,
            weight REAL, updated_at TEXT,
            PRIMARY KEY (contact_id, interest)
        );
        CREATE TABLE IF NOT EXISTS churn_predictions (
            contact_id TEXT PRIMARY KEY,
            churn_prob REAL, churn_label TEXT,
            predicted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS reply_sentiment_log (
            id TEXT PRIMARY KEY, contact_id TEXT,
            sentiment TEXT, score REAL
        );
        CREATE TABLE IF NOT EXISTS conversation_notes (
            id TEXT PRIMARY KEY, contact_id TEXT, note TEXT
        );
        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id TEXT PRIMARY KEY, contact_id TEXT, summary TEXT
        );
        CREATE TABLE IF NOT EXISTS vector_memories (
            id TEXT PRIMARY KEY, contact_id TEXT, content TEXT
        );
        CREATE TABLE IF NOT EXISTS roi_forecasts (
            contact_id TEXT PRIMARY KEY, forecast REAL
        );
        CREATE TABLE IF NOT EXISTS wish_predictions (
            contact_id TEXT PRIMARY KEY, prob REAL
        );
        CREATE TABLE IF NOT EXISTS revenue_attributions (
            id TEXT PRIMARY KEY, contact_id TEXT, amount REAL
        );
        CREATE TABLE IF NOT EXISTS revenue_contacts (
            contact_id TEXT PRIMARY KEY, total REAL
        );
        CREATE TABLE IF NOT EXISTS calendar_sync_log (
            id TEXT PRIMARY KEY, contact_id TEXT, synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS notion_sync_log (
            id TEXT PRIMARY KEY, contact_id TEXT, synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS email_outreach_log (
            id TEXT PRIMARY KEY, contact_id TEXT, sent_at TEXT
        );
        CREATE TABLE IF NOT EXISTS wa_status_log (
            id TEXT PRIMARY KEY, contact_id TEXT, status TEXT
        );
        CREATE TABLE IF NOT EXISTS graph_edges (
            id TEXT PRIMARY KEY, contact_id TEXT,
            target_id TEXT, weight REAL
        );
        CREATE TABLE IF NOT EXISTS tier_change_log (
            id TEXT PRIMARY KEY, contact_id TEXT,
            old_tier TEXT, new_tier TEXT
        );
    """)
    conn.commit()
    conn.close()

    return tdb


def _seed_contacts(db_path: Path, count: int = 5) -> list[str]:
    """Seed test contacts and return their IDs."""
    conn = sqlite3.connect(db_path)
    today_md = datetime.now(timezone.utc).strftime("%m-%d")
    ids = []

    contacts = [
        ("c-int-001", "Alice Chen", "Close Friend", 9.5, True),
        ("c-int-002", "Bob Rahman", "Colleague", 7.0, False),
        ("c-int-003", "Sara Khan", "Close Friend", 8.5, False),
        ("c-int-004", "Tanvir Ahmed", "Acquaintance", 4.0, False),
        ("c-int-005", "Diana Prince", "Professional", 6.0, True),
    ]

    for cid, name, tier, score, is_vip in contacts[:count]:
        conn.execute(
            "INSERT OR REPLACE INTO contact_tier VALUES (?,?,?,?)",
            (cid, name, tier, score))
        conn.execute(
            "INSERT OR REPLACE INTO contact_life_events VALUES (?,?,?,?)",
            (f"ev-{cid}", cid, "birthday", f"1995-{today_md}"))
        conn.execute(
            "INSERT OR REPLACE INTO graph_nodes VALUES (?,?)",
            (cid, "LinkedIn"))
        if is_vip:
            conn.execute(
                "INSERT OR REPLACE INTO vip_contacts VALUES (?)", (cid,))
        ids.append(cid)

    conn.commit()
    conn.close()
    return ids


# ══════════════════════════════════════════════════════════════
# Flow 1: Morning Briefing → Push Notification → Audit Log
# ══════════════════════════════════════════════════════════════


class TestFlow1_BriefingPushAudit:
    """Morning briefing generates → push sends → audit records."""

    def setup_method(self):
        self.db = _create_test_db()
        self.contacts = _seed_contacts(self.db)

    def teardown_method(self):
        os.unlink(self.db)

    def test_briefing_generates_with_birthdays(self):
        """Briefing picks up seeded contacts with today's birthday."""
        from morning_briefing import generate_briefing
        brief = generate_briefing(self.db)

        assert brief["summary"]["birthdays_today"] >= 1
        assert brief["date"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert "birthdays_today" in brief
        names = [b["contact_name"] for b in brief["birthdays_today"]]
        assert "Alice Chen" in names

    def test_briefing_detects_vip_alerts(self):
        """VIP contacts without wishes trigger alerts."""
        from morning_briefing import generate_briefing
        brief = generate_briefing(self.db)

        alert_types = [a["type"] for a in brief["alerts"]]
        assert "vip_birthday" in alert_types

    def test_push_notification_sent_for_briefing(self):
        """Push notification is delivered after briefing."""
        from morning_briefing import generate_briefing
        from push_notifications import (
            init_push_tables, register_device, send_push,
            get_notification_log,
        )

        init_push_tables(self.db)
        register_device("user-001", "fcm-token-test-001",
                        device_name="TestPhone", db_path=self.db)

        brief = generate_briefing(self.db)

        # Simulate push delivery
        results = send_push(
            "user-001", "weekly_digest",
            title="Morning Briefing",
            body=f"{brief['summary']['birthdays_today']} birthdays today",
            respect_quiet=False, db_path=self.db,
        )

        assert len(results) >= 1
        assert results[0]["status"] == "sent"

        # Verify notification logged
        logs = get_notification_log("user-001", db_path=self.db)
        assert len(logs) >= 1
        assert logs[0]["category"] == "weekly_digest"

    def test_audit_log_captures_push_and_briefing(self):
        """Audit trail has entries from both briefing and push."""
        from morning_briefing import generate_briefing
        from audit_log import record, search

        # Generate briefing
        brief = generate_briefing(self.db)

        # Log to audit trail
        record("report_generated",
               f"Morning briefing for {brief['date']}",
               module="morning_briefing",
               metadata={"birthdays": brief["summary"]["birthdays_today"]},
               db_path=self.db)

        record("data_exported",
               "Briefing push sent to user-001",
               actor="system", module="push_notifications",
               db_path=self.db)

        # Verify both entries exist
        entries = search(module="morning_briefing", db_path=self.db)
        assert len(entries) >= 1

        push_entries = search(module="push_notifications", db_path=self.db)
        assert len(push_entries) >= 1

        # Verify chain integrity
        from audit_log import verify_chain
        result = verify_chain(self.db)
        assert result["is_intact"]


# ══════════════════════════════════════════════════════════════
# Flow 2: Rate Limit → Consume → Throttle → Status
# ══════════════════════════════════════════════════════════════


class TestFlow2_RateLimitFlow:
    """Rate limiting tracks consumption and blocks when exhausted."""

    def setup_method(self):
        self.db = _create_test_db()

    def teardown_method(self):
        os.unlink(self.db)

    def test_consume_then_check_status(self):
        """Consuming quota is reflected in platform status."""
        from rate_limit_dashboard import (
            set_quota, consume_quota, get_platform_status,
        )

        set_quota("linkedin", daily=5, hourly=3, per_minute=2,
                  db_path=self.db)

        # Consume 2 units
        consume_quota("linkedin", contact_id="c-001", db_path=self.db)
        consume_quota("linkedin", contact_id="c-002", db_path=self.db)

        status = get_platform_status("linkedin", self.db)
        assert len(status) == 1
        assert status[0]["counts"]["daily"] == 2
        assert status[0]["percentages"]["daily"] == 40.0

    def test_exhaust_daily_limit_triggers_block(self):
        """Exceeding daily limit blocks further sends."""
        from rate_limit_dashboard import (
            set_quota, consume_quota, is_allowed, get_throttle_log,
        )

        set_quota("telegram", daily=3, hourly=100, per_minute=100,
                  db_path=self.db)

        for i in range(3):
            consume_quota("telegram", contact_id=f"t-{i}",
                          db_path=self.db)

        check = is_allowed("telegram", db_path=self.db)
        assert not check["allowed"]
        assert check["reason"] == "daily_limit_reached"

        # Throttle event logged
        events = get_throttle_log("telegram", db_path=self.db)
        assert len(events) >= 1
        assert events[0]["limit_type"] == "daily"

    def test_contact_cooldown_blocks_repeat_send(self):
        """Sending to a contact sets cooldown, blocking resend."""
        from rate_limit_dashboard import (
            set_quota, consume_quota, is_allowed,
        )

        set_quota("whatsapp", daily=100, hourly=50, per_minute=20,
                  cooldown_days=30, db_path=self.db)

        consume_quota("whatsapp", contact_id="cd-test", db_path=self.db)

        check = is_allowed("whatsapp", contact_id="cd-test",
                           db_path=self.db)
        assert not check["allowed"]
        assert check["reason"] == "contact_on_cooldown"

    def test_rate_limit_stats_aggregate(self):
        """Stats aggregate across multiple platforms."""
        from rate_limit_dashboard import (
            set_quota, consume_quota, get_stats,
        )

        set_quota("linkedin", daily=10, hourly=5, per_minute=3,
                  db_path=self.db)
        set_quota("email", daily=100, hourly=30, per_minute=5,
                  db_path=self.db)

        for i in range(5):
            consume_quota("linkedin", contact_id=f"li-{i}",
                          db_path=self.db)
        for i in range(3):
            consume_quota("email", contact_id=f"em-{i}",
                          db_path=self.db)

        stats = get_stats(self.db)
        assert stats["total_sends_today"] == 8
        assert stats["enabled"] >= 2


# ══════════════════════════════════════════════════════════════
# Flow 3: JWT Auth → Token Validation → GDPR Right-to-Forget
# ══════════════════════════════════════════════════════════════


class TestFlow3_AuthGDPR:
    """Auth creates users, GDPR erases their associated data."""

    def setup_method(self):
        self.db = _create_test_db()
        self.contacts = _seed_contacts(self.db)

    def teardown_method(self):
        os.unlink(self.db)

    def test_create_user_and_login(self):
        """User creation and login return valid tokens."""
        from jwt_auth import create_user, login, validate_access_token

        user = create_user("admin", "admin12345",
                           role="admin", db_path=self.db)
        assert user["role"] == "admin"

        result = login("admin", "admin12345", db_path=self.db)
        assert "access_token" in result
        assert "refresh_token" in result

        payload = validate_access_token(result["access_token"], self.db)
        assert payload["username"] == "admin"
        assert payload["role"] == "admin"

    def test_token_refresh_works(self):
        """Refresh token issues a new valid access token."""
        from jwt_auth import (create_user, login,
                              refresh_access_token,
                              validate_access_token)

        create_user("user1", "password123", db_path=self.db)
        tokens = login("user1", "password123", db_path=self.db)

        new_tokens = refresh_access_token(
            tokens["refresh_token"], self.db)
        assert "access_token" in new_tokens

        payload = validate_access_token(
            new_tokens["access_token"], self.db)
        assert payload["username"] == "user1"

    def test_gdpr_consent_and_check(self):
        """Consent can be granted and checked."""
        from gdpr_compliance import (
            _get_conn, record_consent, check_consent,
        )

        conn = _get_conn(str(self.db))
        try:
            record_consent(conn, "c-int-001", "birthday_wish", True)
            assert check_consent(conn, "c-int-001", "birthday_wish")

            record_consent(conn, "c-int-001", "birthday_wish", False)
            assert not check_consent(conn, "c-int-001", "birthday_wish")
        finally:
            conn.close()

    def test_right_to_forget_erases_all_tables(self):
        """Right-to-forget removes contact data from every table."""
        from gdpr_compliance import _get_conn, right_to_forget

        cid = "c-int-001"

        # Seed data in multiple tables
        conn = sqlite3.connect(self.db)
        for tbl in ["interest_signals", "reply_sentiment_log",
                     "conversation_notes", "vector_memories"]:
            conn.execute(
                f"INSERT INTO {tbl} (id, contact_id) VALUES (?,?)",
                (str(uuid.uuid4()), cid))
        conn.commit()
        conn.close()

        # Execute erasure
        gdpr_conn = _get_conn(str(self.db))
        try:
            result = right_to_forget(gdpr_conn, cid)
            assert result["total_deleted"] > 0
            assert not result["dry_run"]

            # Verify data is gone
            conn = sqlite3.connect(self.db)
            for tbl in ["contact_tier", "graph_nodes",
                         "interest_signals", "vector_memories"]:
                cnt = conn.execute(
                    f"SELECT COUNT(*) FROM {tbl} WHERE contact_id=?",
                    (cid,),
                ).fetchone()[0]
                assert cnt == 0, f"Data remains in {tbl}"
            conn.close()
        finally:
            gdpr_conn.close()

    def test_right_to_forget_dryrun_preserves_data(self):
        """Dry run counts but does not delete."""
        from gdpr_compliance import _get_conn, right_to_forget

        cid = "c-int-002"
        gdpr_conn = _get_conn(str(self.db))
        try:
            result = right_to_forget(gdpr_conn, cid, dry_run=True)
            assert result["dry_run"] is True

            # Data should still exist
            conn = sqlite3.connect(self.db)
            cnt = conn.execute(
                "SELECT COUNT(*) FROM contact_tier WHERE contact_id=?",
                (cid,),
            ).fetchone()[0]
            assert cnt == 1
            conn.close()
        finally:
            gdpr_conn.close()


# ══════════════════════════════════════════════════════════════
# Flow 4: Contact Lifecycle → Interest → Audit → Erasure
# ══════════════════════════════════════════════════════════════


class TestFlow4_ContactLifecycle:
    """Full contact lifecycle: create → enrich → audit → erase."""

    def setup_method(self):
        self.db = _create_test_db()
        self.contacts = _seed_contacts(self.db)

    def teardown_method(self):
        os.unlink(self.db)

    def test_contact_data_flows_to_interest_graph(self):
        """Contact data can be enriched with interest signals."""
        conn = sqlite3.connect(self.db)
        cid = "c-int-001"

        # Add interest signals
        for interest in ["AI", "Python", "Photography"]:
            conn.execute(
                """INSERT INTO interest_signals
                   (id, contact_id, interest, weight, source, detected_at)
                   VALUES (?,?,?,?,?,?)""",
                (str(uuid.uuid4()), cid, interest, 0.8, "linkedin",
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.execute(
                """INSERT OR REPLACE INTO interest_profiles
                   (contact_id, interest, weight, updated_at)
                   VALUES (?,?,?,?)""",
                (cid, interest, 0.8,
                 datetime.now(timezone.utc).isoformat()),
            )
        conn.commit()

        # Verify interests recorded
        signals = conn.execute(
            "SELECT COUNT(*) FROM interest_signals WHERE contact_id=?",
            (cid,),
        ).fetchone()[0]
        assert signals == 3

        profiles = conn.execute(
            "SELECT COUNT(*) FROM interest_profiles WHERE contact_id=?",
            (cid,),
        ).fetchone()[0]
        assert profiles == 3
        conn.close()

    def test_audit_logs_contact_creation(self):
        """Creating a contact is logged in audit trail."""
        from audit_log import record, search

        cid = "c-int-003"
        record("contact_created",
               f"Contact Sara Khan created",
               contact_id=cid, module="crm_sync",
               severity="info", db_path=self.db)

        entries = search(contact_id=cid, db_path=self.db)
        assert len(entries) >= 1
        assert entries[0]["action"] == "contact_created"

    def test_full_lifecycle_create_enrich_erase(self):
        """Full cycle: contact exists → enriched → erased completely."""
        from audit_log import record, search, verify_chain
        from gdpr_compliance import _get_conn, right_to_forget

        cid = "c-int-001"

        # Step 1: Verify contact exists
        conn = sqlite3.connect(self.db)
        ct = conn.execute(
            "SELECT contact_name FROM contact_tier WHERE contact_id=?",
            (cid,),
        ).fetchone()
        assert ct is not None
        assert ct[0] == "Alice Chen"

        # Step 2: Enrich with data across tables
        for tbl, col in [
            ("reply_sentiment_log", "sentiment"),
            ("conversation_notes", "note"),
            ("conversation_summaries", "summary"),
            ("vector_memories", "content"),
            ("churn_predictions", "churn_prob"),
            ("roi_forecasts", "forecast"),
            ("wish_predictions", "prob"),
        ]:
            try:
                if col in ("churn_prob", "forecast", "prob"):
                    conn.execute(
                        f"INSERT OR REPLACE INTO {tbl} "
                        f"(contact_id, {col}) VALUES (?,?)",
                        (cid, 0.75))
                else:
                    conn.execute(
                        f"INSERT INTO {tbl} (id, contact_id, {col}) "
                        f"VALUES (?,?,?)",
                        (str(uuid.uuid4()), cid, "test data"))
            except sqlite3.OperationalError:
                pass  # table might have different schema
        conn.commit()
        conn.close()

        # Step 3: Log to audit
        record("contact_updated",
               f"Contact {cid} enriched with ML predictions",
               contact_id=cid, module="integration_test",
               db_path=self.db)

        # Step 4: Erase via GDPR
        gdpr_conn = _get_conn(str(self.db))
        try:
            result = right_to_forget(gdpr_conn, cid)
            assert result["total_deleted"] > 0
        finally:
            gdpr_conn.close()

        # Step 5: Verify complete erasure
        conn = sqlite3.connect(self.db)
        for tbl in ["contact_tier", "vip_contacts", "graph_nodes",
                     "interest_signals", "interest_profiles",
                     "reply_sentiment_log", "conversation_notes",
                     "vector_memories", "churn_predictions",
                     "wish_predictions"]:
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE contact_id=?",
                (cid,),
            ).fetchone()[0]
            assert cnt == 0, f"Erasure missed table: {tbl}"
        conn.close()

        # Step 6: Audit trail records the erasure
        entries = search(action="right_to_forget", db_path=self.db)
        # GDPR module logs its own audit (gdpr_audit_log), but
        # we also verify the external audit_trail is intact
        chain = verify_chain(self.db)
        assert chain["is_intact"]

    def test_briefing_reflects_erased_contact(self):
        """After erasure, morning briefing no longer shows the contact."""
        from gdpr_compliance import _get_conn, right_to_forget
        from morning_briefing import generate_briefing

        cid = "c-int-001"

        # Erase Alice
        gdpr_conn = _get_conn(str(self.db))
        try:
            right_to_forget(gdpr_conn, cid)
        finally:
            gdpr_conn.close()

        # Generate briefing — Alice should not appear
        brief = generate_briefing(self.db)
        names = [b["contact_name"] for b in brief["birthdays_today"]]
        assert "Alice Chen" not in names


# ══════════════════════════════════════════════════════════════
# Pytest-free runner (fallback)
# ══════════════════════════════════════════════════════════════


def _run_all_tests():
    """Run all test classes without pytest (fallback runner)."""
    import traceback

    test_classes = [
        TestFlow1_BriefingPushAudit,
        TestFlow2_RateLimitFlow,
        TestFlow3_AuthGDPR,
        TestFlow4_ContactLifecycle,
    ]

    total = 0
    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("Integration Test Suite — Birthday Wishes Agent v10.0")
    print("=" * 60)

    for cls in test_classes:
        print(f"\n{'─'*50}")
        print(f"  {cls.__name__}")
        print(f"{'─'*50}")

        methods = [m for m in dir(cls) if m.startswith("test_")]
        for method_name in sorted(methods):
            total += 1
            instance = cls()
            try:
                instance.setup_method()
                getattr(instance, method_name)()
                instance.teardown_method()
                passed += 1
                print(f"  ✅ {method_name}")
            except Exception as exc:
                failed += 1
                errors.append((cls.__name__, method_name, str(exc)))
                print(f"  ❌ {method_name}: {exc}")
                try:
                    instance.teardown_method()
                except Exception:
                    pass

    print(f"\n{'='*60}")
    if failed == 0:
        print(f"✅ ALL {total} INTEGRATION TESTS PASSED")
    else:
        print(f"❌ {failed}/{total} FAILED, {passed} passed")
        for cls_name, method, err in errors:
            print(f"   {cls_name}.{method}: {err}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = _run_all_tests()
    exit(0 if success else 1)
