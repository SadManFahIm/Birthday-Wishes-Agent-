"""
FastAPI API Test Suite — Birthday Wishes Agent v10.0
=====================================================
End-to-end API tests using FastAPI TestClient + httpx.
Covers auth flow, RBAC, protected routes, rate limits,
push notifications, and error cases.

Run:
  pytest api_tests.py -v
  python api_tests.py           # fallback without pytest

Author : Fahim (SadManFahIm)
Branch : feature/api-tests (→ 10.0)
"""

import os
import json
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

# ──────────────────────────────────────────────────────────────
# Test app factory — creates a fresh FastAPI app + temp DB
# ──────────────────────────────────────────────────────────────


def _create_test_app():
    """Build a fresh FastAPI app with all routes mounted on a temp DB."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Create temp DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)

    # Patch DB_PATH in all modules BEFORE importing route registrars
    import jwt_auth
    import push_notifications
    import rate_limit_dashboard

    jwt_auth.DB_PATH = db_path
    push_notifications.DB_PATH = db_path
    rate_limit_dashboard.DB_PATH = db_path

    # Monkey-patch every public function's default db_path so route
    # handlers (which call without explicit db_path) hit the temp DB.
    # Python evaluates default args at definition time, so changing
    # the module-level DB_PATH alone doesn't affect already-defined
    # function signatures.
    import types
    for mod in [jwt_auth, push_notifications, rate_limit_dashboard]:
        for name in dir(mod):
            obj = getattr(mod, name)
            if not callable(obj) or name.startswith("_"):
                continue
            if isinstance(obj, type):
                continue
            try:
                defaults = obj.__defaults__
                if defaults:
                    new_defaults = tuple(
                        db_path if isinstance(d, Path) else d
                        for d in defaults
                    )
                    obj.__defaults__ = new_defaults
            except (AttributeError, TypeError):
                pass
            try:
                kw = obj.__kwdefaults__
                if kw:
                    for k, v in kw.items():
                        if isinstance(v, Path):
                            kw[k] = db_path
            except (AttributeError, TypeError):
                pass

    # Rebuild FastAPI deps so they pick up patched validate_access_token
    jwt_auth.get_current_user, jwt_auth.require_role, _ = (
        jwt_auth._make_fastapi_deps())

    # Init tables
    jwt_auth.init_auth_tables(db_path)
    push_notifications.init_push_tables(db_path)
    rate_limit_dashboard.init_rate_limit_tables(db_path)

    # Create app
    app = FastAPI(title="BWA Test API", version="10.0-test")

    # Mount routes
    jwt_auth.register_auth_routes(app)
    push_notifications.register_push_routes(app)
    rate_limit_dashboard.register_rate_limit_routes(app)

    # Seed admin user (needed because register route requires admin)
    jwt_auth.create_user("admin", "admin12345",
                         role="admin", db_path=db_path)
    jwt_auth.create_user("viewer1", "viewer12345",
                         role="viewer", db_path=db_path)

    client = TestClient(app)

    return client, db_path


def _login(client, username="admin", password="admin12345") -> dict:
    """Login and return the full response body."""
    resp = client.post("/api/v1/auth/login",
                       json={"username": username, "password": password})
    return resp.json()


def _auth_header(client, username="admin",
                 password="admin12345") -> dict:
    """Login and return Authorization header dict."""
    data = _login(client, username, password)
    return {"Authorization": f"Bearer {data['access_token']}"}


# ══════════════════════════════════════════════════════════════
# 1. Auth Flow
# ══════════════════════════════════════════════════════════════


class TestAuthFlow:
    """Login → access token → refresh → me → logout."""

    def setup_method(self):
        self.client, self.db = _create_test_app()

    def teardown_method(self):
        os.unlink(self.db)

    def test_login_returns_tokens(self):
        resp = self.client.post("/api/v1/auth/login",
                                json={"username": "admin",
                                      "password": "admin12345"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["role"] == "admin"

    def test_me_returns_user_info(self):
        headers = _auth_header(self.client)
        resp = self.client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"
        assert "password_hash" not in data

    def test_refresh_token_issues_new_access(self):
        login_data = _login(self.client)
        resp = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_data["refresh_token"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_logout_revokes_refresh(self):
        login_data = _login(self.client)
        # Logout
        resp = self.client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": login_data["refresh_token"]})
        assert resp.status_code == 200

        # Refresh should fail now
        resp = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_data["refresh_token"]})
        assert resp.status_code == 401

    def test_register_new_user_as_admin(self):
        headers = _auth_header(self.client)
        resp = self.client.post(
            "/api/v1/auth/register",
            json={"username": "newuser", "password": "newpass12345",
                  "role": "manager"},
            headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert data["user"]["role"] == "manager"

    def test_password_reset_flow(self):
        # Request reset
        resp = self.client.post(
            "/api/v1/auth/password-reset",
            json={"username": "viewer1"})
        assert resp.status_code == 200
        token = resp.json().get("debug_token")
        assert token is not None

        # Confirm reset
        resp = self.client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": token, "new_password": "newpassword123"})
        assert resp.status_code == 200

        # Login with new password
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "viewer1",
                  "password": "newpassword123"})
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════
# 2. RBAC
# ══════════════════════════════════════════════════════════════


class TestRBAC:
    """Admin-only routes reject viewer tokens."""

    def setup_method(self):
        self.client, self.db = _create_test_app()

    def teardown_method(self):
        os.unlink(self.db)

    def test_admin_can_list_users(self):
        headers = _auth_header(self.client, "admin", "admin12345")
        resp = self.client.get("/api/v1/auth/users", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["users"]) >= 2

    def test_viewer_cannot_list_users(self):
        headers = _auth_header(self.client, "viewer1", "viewer12345")
        resp = self.client.get("/api/v1/auth/users", headers=headers)
        assert resp.status_code == 403

    def test_viewer_cannot_register_users(self):
        headers = _auth_header(self.client, "viewer1", "viewer12345")
        resp = self.client.post(
            "/api/v1/auth/register",
            json={"username": "hacker", "password": "hack12345"},
            headers=headers)
        assert resp.status_code == 403

    def test_viewer_can_access_me(self):
        headers = _auth_header(self.client, "viewer1", "viewer12345")
        resp = self.client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "viewer"


# ══════════════════════════════════════════════════════════════
# 3. Protected Routes
# ══════════════════════════════════════════════════════════════


class TestProtectedRoutes:
    """No token / bad token / valid token behavior."""

    def setup_method(self):
        self.client, self.db = _create_test_app()

    def teardown_method(self):
        os.unlink(self.db)

    def test_no_token_returns_401(self):
        resp = self.client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        resp = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401

    def test_malformed_auth_header_returns_401(self):
        resp = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "NotBearer token"})
        assert resp.status_code == 401

    def test_valid_token_returns_200(self):
        headers = _auth_header(self.client)
        resp = self.client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════
# 4. Rate Limit Endpoints
# ══════════════════════════════════════════════════════════════


class TestRateLimitEndpoints:
    """Rate limit status and check endpoints."""

    def setup_method(self):
        self.client, self.db = _create_test_app()

    def teardown_method(self):
        os.unlink(self.db)

    def test_get_all_rate_limits(self):
        resp = self.client.get("/api/v1/rate-limits")
        assert resp.status_code == 200
        data = resp.json()
        assert "statuses" in data
        assert len(data["statuses"]) >= 10  # 10 default platforms

    def test_get_single_platform(self):
        resp = self.client.get("/api/v1/rate-limits?platform=linkedin")
        assert resp.status_code == 200
        statuses = resp.json()["statuses"]
        assert len(statuses) == 1
        assert statuses[0]["platform"] == "linkedin"

    def test_get_stats(self):
        resp = self.client.get("/api/v1/rate-limits/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_sends_today" in data
        assert "enabled" in data

    def test_check_allowed(self):
        resp = self.client.post(
            "/api/v1/rate-limits/check?platform=linkedin")
        assert resp.status_code == 200
        data = resp.json()
        assert "allowed" in data
        assert data["allowed"] is True  # fresh DB, nothing consumed

    def test_throttle_log_empty(self):
        resp = self.client.get("/api/v1/rate-limits/throttle-log")
        assert resp.status_code == 200
        assert "events" in resp.json()


# ══════════════════════════════════════════════════════════════
# 5. Push Notification Endpoints
# ══════════════════════════════════════════════════════════════


class TestPushEndpoints:
    """Device registration, push sending, stats."""

    def setup_method(self):
        self.client, self.db = _create_test_app()

    def teardown_method(self):
        os.unlink(self.db)

    def test_register_device(self):
        resp = self.client.post(
            "/api/v1/push/devices",
            json={"user_id": "u-001", "fcm_token": "tok-android-001",
                  "device_name": "Pixel", "platform": "android"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "registered"
        assert "device_id" in data

    def test_get_user_devices(self):
        # Register first
        self.client.post(
            "/api/v1/push/devices",
            json={"user_id": "u-002", "fcm_token": "tok-ios-001"})
        resp = self.client.get("/api/v1/push/devices/u-002")
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) == 1

    def test_send_push(self):
        # Register device first
        self.client.post(
            "/api/v1/push/devices",
            json={"user_id": "u-003", "fcm_token": "tok-test-003"})
        resp = self.client.post(
            "/api/v1/push/send",
            json={"user_id": "u-003", "category": "birthday_reminder",
                  "title": "Test", "body": "Test push"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 1
        assert results[0]["status"] == "sent"  # dry run

    def test_push_stats(self):
        resp = self.client.get("/api/v1/push/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_notifications" in data
        assert "devices_active" in data

    def test_push_log(self):
        resp = self.client.get("/api/v1/push/log")
        assert resp.status_code == 200
        assert "notifications" in resp.json()

    def test_mark_delivered(self):
        # Send first to create a notification
        self.client.post(
            "/api/v1/push/devices",
            json={"user_id": "u-004", "fcm_token": "tok-del-004"})
        self.client.post(
            "/api/v1/push/send",
            json={"user_id": "u-004", "body": "Delivery test"})

        # Get notification ID from log
        log_resp = self.client.get("/api/v1/push/log?user_id=u-004")
        notifications = log_resp.json()["notifications"]
        if notifications:
            nid = notifications[0]["id"]
            resp = self.client.post(f"/api/v1/push/delivered/{nid}")
            assert resp.status_code == 200
            assert resp.json()["success"] is True


# ══════════════════════════════════════════════════════════════
# 6. Error Cases
# ══════════════════════════════════════════════════════════════


class TestErrorCases:
    """Edge cases: bad input, duplicates, wrong credentials."""

    def setup_method(self):
        self.client, self.db = _create_test_app()

    def teardown_method(self):
        os.unlink(self.db)

    def test_login_wrong_password(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrongpassword"})
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]

    def test_login_nonexistent_user(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "ghost", "password": "ghost12345"})
        assert resp.status_code == 401

    def test_register_duplicate_username(self):
        headers = _auth_header(self.client)
        resp = self.client.post(
            "/api/v1/auth/register",
            json={"username": "admin", "password": "dup12345678"},
            headers=headers)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_register_short_password(self):
        headers = _auth_header(self.client)
        resp = self.client.post(
            "/api/v1/auth/register",
            json={"username": "shortpw", "password": "abc"},
            headers=headers)
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"]

    def test_invalid_json_body(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            content="this is not json",
            headers={"Content-Type": "application/json"})
        assert resp.status_code == 422  # Validation error

    def test_missing_required_fields(self):
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin"})  # missing password
        assert resp.status_code == 422

    def test_refresh_with_invalid_token(self):
        resp = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "totally-fake-token"})
        assert resp.status_code == 401

    def test_password_reset_invalid_token(self):
        resp = self.client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": "fake-reset-token",
                  "new_password": "newpass12345"})
        assert resp.status_code == 400

    def test_send_push_no_devices(self):
        resp = self.client.post(
            "/api/v1/push/send",
            json={"user_id": "nobody", "body": "Hello"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["status"] == "no_devices"


# ══════════════════════════════════════════════════════════════
# Pytest-free runner
# ══════════════════════════════════════════════════════════════


def _run_all_tests():
    """Run all test classes without pytest."""
    test_classes = [
        TestAuthFlow,
        TestRBAC,
        TestProtectedRoutes,
        TestRateLimitEndpoints,
        TestPushEndpoints,
        TestErrorCases,
    ]

    total = 0
    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("FastAPI API Test Suite — Birthday Wishes Agent v10.0")
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
        print(f"✅ ALL {total} API TESTS PASSED")
    else:
        print(f"❌ {failed}/{total} FAILED, {passed} passed")
        for cls_name, method, err in errors:
            print(f"   {cls_name}.{method}: {err}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = _run_all_tests()
    exit(0 if success else 1)
