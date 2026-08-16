"""
JWT Auth Module — Birthday Wishes Agent v10.0
===============================================
Proper authentication & authorisation for the FastAPI backend.

Features:
  - User registration with bcrypt password hashing
  - JWT access + refresh token pair (HS256)
  - Role-based access control (admin / manager / viewer)
  - Token refresh & revocation (blocklist)
  - Rate-limited login attempts per user
  - Password reset token flow
  - Streamlit user-management dashboard (dark theme)
  - Full self-test suite

Integration:
  from jwt_auth import require_role, get_current_user
  @app.get("/api/v1/protected")
  def protected(user = Depends(get_current_user)):
      ...
  @app.post("/api/v1/admin-only")
  def admin_only(user = Depends(require_role("admin"))):
      ...

Author : Fahim (SadManFahIm)
Branch : feature/jwt-auth (→ 10.0)
"""

import sqlite3
import json
import os
import uuid
import hmac
import hashlib
import base64
import struct
import time
import logging
import secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional
from functools import wraps

# ──────────────────────────────────────────────────────────────
# Constants & config
# ──────────────────────────────────────────────────────────────

DB_PATH = Path(os.getenv("BWA_DB_PATH", "agent_history.db"))

JWT_SECRET = os.getenv("BWA_JWT_SECRET", "bwa-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("BWA_ACCESS_TOKEN_MINUTES", "30"))
REFRESH_TOKEN_DAYS = int(os.getenv("BWA_REFRESH_TOKEN_DAYS", "7"))

ROLES = ("admin", "manager", "viewer")
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Pure-Python bcrypt-style password hashing (PBKDF2-SHA256)
# No external dependency needed — stdlib only.
# ──────────────────────────────────────────────────────────────


def _hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256, 260 000 iterations, 32-byte salt."""
    salt = os.urandom(32)
    iterations = 260_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    payload = (base64.b64encode(salt).decode() + "$"
               + str(iterations) + "$"
               + base64.b64encode(dk).decode())
    return payload


def _verify_password(password: str, stored: str) -> bool:
    """Verify password against PBKDF2 hash."""
    try:
        parts = stored.split("$")
        salt = base64.b64decode(parts[0])
        iterations = int(parts[1])
        expected_dk = base64.b64decode(parts[2])
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt,
                                 iterations)
        return hmac.compare_digest(dk, expected_dk)
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────
# Pure-Python JWT (HS256) — no PyJWT dependency
# ──────────────────────────────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _jwt_encode(payload: dict, secret: str = JWT_SECRET) -> str:
    """Create a signed JWT (HS256)."""
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":"),
                                  default=str).encode())
    sig_input = f"{h}.{p}".encode()
    sig = hmac.new(secret.encode(), sig_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def _jwt_decode(token: str, secret: str = JWT_SECRET) -> Optional[dict]:
    """Decode and verify a JWT. Returns None on failure."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        sig_input = f"{parts[0]}.{parts[1]}".encode()
        expected_sig = hmac.new(secret.encode(), sig_input,
                                hashlib.sha256).digest()
        actual_sig = _b64url_decode(parts[2])
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(parts[1]))
        # Check expiry
        if "exp" in payload:
            exp_ts = payload["exp"]
            if time.time() > exp_ts:
                return None
        return payload
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────


def init_auth_tables(db_path: Path = DB_PATH) -> None:
    """Create auth tables if not present."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auth_users (
            id              TEXT PRIMARY KEY,
            username        TEXT NOT NULL UNIQUE,
            email           TEXT UNIQUE,
            password_hash   TEXT NOT NULL,
            display_name    TEXT NOT NULL DEFAULT '',
            role            TEXT NOT NULL DEFAULT 'viewer',
            is_active       INTEGER NOT NULL DEFAULT 1,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until    TEXT,
            last_login_at   TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_auth_username
            ON auth_users(username);

        CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            token_hash      TEXT NOT NULL,
            expires_at      TEXT NOT NULL,
            revoked         INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES auth_users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_refresh_user
            ON auth_refresh_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_refresh_hash
            ON auth_refresh_tokens(token_hash);

        CREATE TABLE IF NOT EXISTS auth_token_blocklist (
            jti             TEXT PRIMARY KEY,
            blocked_at      TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at      TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_blocklist_exp
            ON auth_token_blocklist(expires_at);

        CREATE TABLE IF NOT EXISTS auth_password_resets (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            token_hash      TEXT NOT NULL,
            expires_at      TEXT NOT NULL,
            used            INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES auth_users(id)
        );

        CREATE TABLE IF NOT EXISTS auth_login_log (
            id              TEXT PRIMARY KEY,
            user_id         TEXT,
            username        TEXT NOT NULL,
            success         INTEGER NOT NULL,
            ip_hash         TEXT,
            user_agent      TEXT,
            timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_login_log_user
            ON auth_login_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_login_log_ts
            ON auth_login_log(timestamp);
    """)
    conn.commit()
    conn.close()
    logger.info("Auth tables initialised: %s", db_path)


def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ──────────────────────────────────────────────────────────────
# User management
# ──────────────────────────────────────────────────────────────


def create_user(username: str, password: str, *,
                email: str = "", display_name: str = "",
                role: str = "viewer",
                db_path: Path = DB_PATH) -> dict:
    """Register a new user. Returns user dict (no password hash)."""
    if role not in ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {ROLES}")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    user_id = str(uuid.uuid4())
    pw_hash = _hash_password(password)
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_conn(db_path)
    try:
        # Check duplicate
        existing = conn.execute(
            "SELECT id FROM auth_users WHERE username=?", (username,)
        ).fetchone()
        if existing:
            raise ValueError(f"Username '{username}' already exists")

        # Store empty email as NULL to avoid UNIQUE constraint clash
        email_val = email if email else None

        conn.execute(
            """INSERT INTO auth_users
               (id, username, email, password_hash, display_name,
                role, is_active, created_at, updated_at)
               VALUES (?,?,?,?,?,?,1,?,?)""",
            (user_id, username, email_val, pw_hash,
             display_name or username, role, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    return {"id": user_id, "username": username, "email": email,
            "display_name": display_name or username, "role": role,
            "is_active": True}


def get_user(user_id: str, db_path: Path = DB_PATH) -> Optional[dict]:
    """Fetch user by ID (no password hash)."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM auth_users WHERE id=?", (user_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d.pop("password_hash", None)
        return d
    finally:
        conn.close()


def get_user_by_username(username: str,
                         db_path: Path = DB_PATH) -> Optional[dict]:
    """Fetch user by username (includes password_hash for internal use)."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM auth_users WHERE username=?", (username,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users(db_path: Path = DB_PATH) -> list[dict]:
    """List all users (no password hashes)."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, username, email, display_name, role, is_active, "
            "last_login_at, created_at FROM auth_users ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_user_role(user_id: str, new_role: str,
                     db_path: Path = DB_PATH) -> bool:
    """Change a user's role."""
    if new_role not in ROLES:
        raise ValueError(f"Invalid role: {new_role}")
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "UPDATE auth_users SET role=?, updated_at=? WHERE id=?",
            (new_role, datetime.now(timezone.utc).isoformat(), user_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def deactivate_user(user_id: str, db_path: Path = DB_PATH) -> bool:
    """Soft-delete: deactivate a user account."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "UPDATE auth_users SET is_active=0, updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), user_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def activate_user(user_id: str, db_path: Path = DB_PATH) -> bool:
    """Re-activate a deactivated user."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "UPDATE auth_users SET is_active=1, updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), user_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Authentication (login / token issue)
# ──────────────────────────────────────────────────────────────


def _is_locked(user: dict) -> bool:
    """Check if user is locked out from too many failed attempts."""
    if not user.get("locked_until"):
        return False
    locked = datetime.fromisoformat(user["locked_until"])
    return datetime.now(timezone.utc) < locked.replace(tzinfo=timezone.utc)


def _record_login(conn: sqlite3.Connection, user_id: Optional[str],
                  username: str, success: bool,
                  ip_hash: str = "") -> None:
    """Log a login attempt."""
    conn.execute(
        """INSERT INTO auth_login_log
           (id, user_id, username, success, ip_hash, timestamp)
           VALUES (?,?,?,?,?,?)""",
        (str(uuid.uuid4()), user_id, username, 1 if success else 0,
         ip_hash, datetime.now(timezone.utc).isoformat()),
    )


def _create_access_token(user_id: str, username: str,
                         role: str) -> tuple[str, str]:
    """Create an access token. Returns (token, jti)."""
    jti = str(uuid.uuid4())
    now = time.time()
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "type": "access",
        "jti": jti,
        "iat": int(now),
        "exp": int(now + ACCESS_TOKEN_MINUTES * 60),
    }
    return _jwt_encode(payload), jti


def _create_refresh_token(user_id: str,
                          db_path: Path = DB_PATH) -> str:
    """Create and store a refresh token."""
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc)
               + timedelta(days=REFRESH_TOKEN_DAYS)).isoformat()

    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO auth_refresh_tokens
               (id, user_id, token_hash, expires_at)
               VALUES (?,?,?,?)""",
            (str(uuid.uuid4()), user_id, token_hash, expires),
        )
        conn.commit()
    finally:
        conn.close()

    return raw_token


def login(username: str, password: str, *,
          ip_hash: str = "",
          db_path: Path = DB_PATH) -> dict:
    """
    Authenticate user. Returns token pair on success.
    Raises ValueError on failure.
    """
    conn = _get_conn(db_path)
    try:
        user = conn.execute(
            "SELECT * FROM auth_users WHERE username=?", (username,)
        ).fetchone()

        if not user:
            _record_login(conn, None, username, False, ip_hash)
            conn.commit()
            raise ValueError("Invalid username or password")

        user = dict(user)

        if not user["is_active"]:
            _record_login(conn, user["id"], username, False, ip_hash)
            conn.commit()
            raise ValueError("Account is deactivated")

        if _is_locked(user):
            _record_login(conn, user["id"], username, False, ip_hash)
            conn.commit()
            raise ValueError(
                f"Account locked due to {MAX_LOGIN_ATTEMPTS} failed attempts. "
                f"Try again after {LOCKOUT_MINUTES} minutes.")

        if not _verify_password(password, user["password_hash"]):
            attempts = user["failed_attempts"] + 1
            updates = {"failed_attempts": attempts}
            if attempts >= MAX_LOGIN_ATTEMPTS:
                lock_until = (datetime.now(timezone.utc)
                              + timedelta(minutes=LOCKOUT_MINUTES))
                updates["locked_until"] = lock_until.isoformat()
            conn.execute(
                "UPDATE auth_users SET failed_attempts=?, locked_until=?, "
                "updated_at=? WHERE id=?",
                (updates["failed_attempts"],
                 updates.get("locked_until"),
                 datetime.now(timezone.utc).isoformat(),
                 user["id"]),
            )
            _record_login(conn, user["id"], username, False, ip_hash)
            conn.commit()
            raise ValueError("Invalid username or password")

        # Success — reset counters
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE auth_users SET failed_attempts=0, locked_until=NULL, "
            "last_login_at=?, updated_at=? WHERE id=?",
            (now, now, user["id"]),
        )
        _record_login(conn, user["id"], username, True, ip_hash)
        conn.commit()
    finally:
        conn.close()

    access_token, jti = _create_access_token(
        user["id"], user["username"], user["role"])
    refresh_token = _create_refresh_token(user["id"], db_path)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"],
        },
    }


def refresh_access_token(refresh_token: str,
                         db_path: Path = DB_PATH) -> dict:
    """Issue a new access token using a valid refresh token."""
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            """SELECT rt.*, u.username, u.role, u.is_active
               FROM auth_refresh_tokens rt
               JOIN auth_users u ON u.id = rt.user_id
               WHERE rt.token_hash=? AND rt.revoked=0""",
            (token_hash,),
        ).fetchone()

        if not row:
            raise ValueError("Invalid or revoked refresh token")

        row = dict(row)

        expires = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires.replace(tzinfo=timezone.utc):
            raise ValueError("Refresh token expired")

        if not row["is_active"]:
            raise ValueError("User account is deactivated")

        access_token, jti = _create_access_token(
            row["user_id"], row["username"], row["role"])

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_MINUTES * 60,
        }
    finally:
        conn.close()


def revoke_refresh_token(refresh_token: str,
                         db_path: Path = DB_PATH) -> bool:
    """Revoke a refresh token (logout)."""
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "UPDATE auth_refresh_tokens SET revoked=1 WHERE token_hash=?",
            (token_hash,),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def revoke_all_user_tokens(user_id: str,
                           db_path: Path = DB_PATH) -> int:
    """Revoke all refresh tokens for a user (force logout everywhere)."""
    conn = _get_conn(db_path)
    try:
        cursor = conn.execute(
            "UPDATE auth_refresh_tokens SET revoked=1 "
            "WHERE user_id=? AND revoked=0",
            (user_id,),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def blocklist_access_token(jti: str, exp_timestamp: int,
                           db_path: Path = DB_PATH) -> None:
    """Add an access token's JTI to the blocklist (early revocation)."""
    expires = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO auth_token_blocklist (jti, expires_at) "
            "VALUES (?,?)",
            (jti, expires.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def is_token_blocklisted(jti: str,
                         db_path: Path = DB_PATH) -> bool:
    """Check if an access token JTI is blocklisted."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT jti FROM auth_token_blocklist WHERE jti=?", (jti,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def cleanup_expired_blocklist(db_path: Path = DB_PATH) -> int:
    """Remove expired entries from blocklist."""
    conn = _get_conn(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM auth_token_blocklist WHERE expires_at < ?",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Password reset
# ──────────────────────────────────────────────────────────────


def create_password_reset_token(username: str,
                                db_path: Path = DB_PATH) -> Optional[str]:
    """Generate a password reset token. Returns token or None."""
    user = get_user_by_username(username, db_path)
    if not user:
        return None

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO auth_password_resets
               (id, user_id, token_hash, expires_at)
               VALUES (?,?,?,?)""",
            (str(uuid.uuid4()), user["id"], token_hash, expires),
        )
        conn.commit()
    finally:
        conn.close()

    return raw_token


def reset_password(token: str, new_password: str,
                   db_path: Path = DB_PATH) -> bool:
    """Reset password using a valid reset token."""
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters")

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            """SELECT * FROM auth_password_resets
               WHERE token_hash=? AND used=0""",
            (token_hash,),
        ).fetchone()

        if not row:
            return False

        row = dict(row)
        expires = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires.replace(tzinfo=timezone.utc):
            return False

        pw_hash = _hash_password(new_password)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE auth_users SET password_hash=?, updated_at=? WHERE id=?",
            (pw_hash, now, row["user_id"]),
        )
        conn.execute(
            "UPDATE auth_password_resets SET used=1 WHERE id=?",
            (row["id"],),
        )
        # Revoke all refresh tokens on password change
        conn.execute(
            "UPDATE auth_refresh_tokens SET revoked=1 WHERE user_id=?",
            (row["user_id"],),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# FastAPI dependencies (for route protection)
# ──────────────────────────────────────────────────────────────


def validate_access_token(token: str,
                          db_path: Path = DB_PATH) -> dict:
    """
    Decode + validate an access token.
    Returns the payload dict or raises ValueError.
    """
    payload = _jwt_decode(token)
    if not payload:
        raise ValueError("Invalid or expired token")
    if payload.get("type") != "access":
        raise ValueError("Not an access token")
    if is_token_blocklisted(payload.get("jti", ""), db_path):
        raise ValueError("Token has been revoked")
    return payload


def _extract_bearer_token(authorization: str) -> str:
    """Extract token from 'Bearer <token>' header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise ValueError("Missing or invalid Authorization header")
    return authorization[7:]


# FastAPI dependency factories — only usable when FastAPI is installed
def _make_fastapi_deps():
    """Create FastAPI Depends-compatible callables."""
    try:
        from fastapi import Depends, HTTPException, status
        from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

        bearer_scheme = HTTPBearer(auto_error=True)

        async def get_current_user(
            credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        ) -> dict:
            """FastAPI dependency: extract and validate JWT from header."""
            try:
                payload = validate_access_token(credentials.credentials)
                return payload
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(exc),
                    headers={"WWW-Authenticate": "Bearer"},
                )

        def require_role(*allowed_roles: str):
            """FastAPI dependency factory: require specific role(s)."""
            async def role_checker(
                user: dict = Depends(get_current_user),
            ) -> dict:
                if user.get("role") not in allowed_roles:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(f"Role '{user.get('role')}' not permitted. "
                                f"Required: {', '.join(allowed_roles)}"),
                    )
                return user
            return role_checker

        return get_current_user, require_role, bearer_scheme
    except ImportError:
        return None, None, None


get_current_user, require_role, bearer_scheme = _make_fastapi_deps()


# ──────────────────────────────────────────────────────────────
# FastAPI auth routes factory
# ──────────────────────────────────────────────────────────────


def register_auth_routes(app) -> None:
    """Mount /api/v1/auth/* endpoints onto a FastAPI app."""
    try:
        from fastapi import HTTPException, status, Depends
        from pydantic import BaseModel as BM, Field as F
    except ImportError:
        logger.warning("FastAPI not installed — skipping auth route mount")
        return

    class RegisterRequest(BM):
        username: str
        password: str
        email: str = ""
        display_name: str = ""
        role: str = F(default="viewer", pattern="^(admin|manager|viewer)$")

    class LoginRequest(BM):
        username: str
        password: str

    class RefreshRequest(BM):
        refresh_token: str

    class PasswordResetRequest(BM):
        username: str

    class PasswordResetConfirm(BM):
        token: str
        new_password: str

    @app.post("/api/v1/auth/register", tags=["Auth"], status_code=201)
    def auth_register(req: RegisterRequest,
                      user=Depends(require_role("admin"))):
        """Register a new user (admin only)."""
        try:
            u = create_user(req.username, req.password,
                            email=req.email,
                            display_name=req.display_name,
                            role=req.role)
            return {"success": True, "user": u}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/v1/auth/login", tags=["Auth"])
    def auth_login(req: LoginRequest):
        """Login and receive access + refresh tokens."""
        try:
            result = login(req.username, req.password)
            return result
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc))

    @app.post("/api/v1/auth/refresh", tags=["Auth"])
    def auth_refresh(req: RefreshRequest):
        """Refresh an access token."""
        try:
            return refresh_access_token(req.refresh_token)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc))

    @app.post("/api/v1/auth/logout", tags=["Auth"])
    def auth_logout(req: RefreshRequest):
        """Revoke refresh token (logout)."""
        revoke_refresh_token(req.refresh_token)
        return {"success": True, "message": "Logged out"}

    @app.get("/api/v1/auth/me", tags=["Auth"])
    def auth_me(user=Depends(get_current_user)):
        """Return the currently authenticated user's info."""
        u = get_user(user["sub"])
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        return u

    @app.get("/api/v1/auth/users", tags=["Auth"])
    def auth_list_users(user=Depends(require_role("admin"))):
        """List all users (admin only)."""
        return {"users": list_users()}

    @app.post("/api/v1/auth/password-reset", tags=["Auth"])
    def auth_request_reset(req: PasswordResetRequest):
        """Request a password reset token."""
        token = create_password_reset_token(req.username)
        # In production, email this token — here we return it for testing
        return {"success": True,
                "message": "If the account exists a reset link was sent",
                "debug_token": token}

    @app.post("/api/v1/auth/password-reset/confirm", tags=["Auth"])
    def auth_confirm_reset(req: PasswordResetConfirm):
        """Reset password with token."""
        try:
            ok = reset_password(req.token, req.new_password)
            if not ok:
                raise HTTPException(status_code=400,
                                    detail="Invalid or expired reset token")
            return {"success": True, "message": "Password updated"}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    logger.info("Auth routes registered: /api/v1/auth/*")


# ──────────────────────────────────────────────────────────────
# Stats
# ──────────────────────────────────────────────────────────────


def get_auth_stats(db_path: Path = DB_PATH) -> dict:
    """Dashboard stats."""
    conn = _get_conn(db_path)
    try:
        users_total = conn.execute(
            "SELECT COUNT(*) as c FROM auth_users"
        ).fetchone()["c"]
        users_active = conn.execute(
            "SELECT COUNT(*) as c FROM auth_users WHERE is_active=1"
        ).fetchone()["c"]
        by_role = conn.execute(
            "SELECT role, COUNT(*) as c FROM auth_users GROUP BY role"
        ).fetchall()
        logins_24h = conn.execute(
            """SELECT COUNT(*) as c FROM auth_login_log
               WHERE success=1 AND timestamp >= datetime('now','-24 hours')"""
        ).fetchone()["c"]
        failed_24h = conn.execute(
            """SELECT COUNT(*) as c FROM auth_login_log
               WHERE success=0 AND timestamp >= datetime('now','-24 hours')"""
        ).fetchone()["c"]
        active_refresh = conn.execute(
            """SELECT COUNT(*) as c FROM auth_refresh_tokens
               WHERE revoked=0 AND expires_at > datetime('now')"""
        ).fetchone()["c"]
        blocked_tokens = conn.execute(
            "SELECT COUNT(*) as c FROM auth_token_blocklist"
        ).fetchone()["c"]
        recent_logins = conn.execute(
            """SELECT username, success, timestamp
               FROM auth_login_log ORDER BY timestamp DESC LIMIT 15"""
        ).fetchall()

        return {
            "users_total": users_total,
            "users_active": users_active,
            "by_role": [dict(r) for r in by_role],
            "logins_24h": logins_24h,
            "failed_24h": failed_24h,
            "active_refresh_tokens": active_refresh,
            "blocked_access_tokens": blocked_tokens,
            "recent_logins": [dict(r) for r in recent_logins],
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """User management & auth monitoring dashboard."""
    try:
        import streamlit as st
        import pandas as pd
    except ImportError:
        return

    st.set_page_config(page_title="JWT Auth", page_icon="🔐",
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
    .c-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
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
    div.stTabs [data-baseweb="tab-list"]{gap:0;border-bottom:1px solid var(--border);}
    div.stTabs [data-baseweb="tab"]{color:var(--muted)!important;background:transparent!important;
        border-bottom:2px solid transparent;padding:0.5rem 1rem;}
    div.stTabs [aria-selected="true"]{color:var(--accent)!important;
        border-bottom:2px solid var(--accent)!important;}
    .role-admin{color:var(--red);font-weight:600;}
    .role-manager{color:var(--yellow);font-weight:600;}
    .role-viewer{color:var(--blue);}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    </style>
    """, unsafe_allow_html=True)

    init_auth_tables()
    stats = get_auth_stats()

    # Header
    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">🔐</span>
      <h1>JWT Auth Manager</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    # KPIs
    st.markdown('<div class="section-title">Overview</div>',
                unsafe_allow_html=True)
    k1, k2, k3, k4, k5 = st.columns(5)
    for col, val, lbl in [
        (k1, stats["users_total"], "Total Users"),
        (k2, stats["users_active"], "Active"),
        (k3, stats["logins_24h"], "Logins (24h)"),
        (k4, stats["failed_24h"], "Failed (24h)"),
        (k5, stats["active_refresh_tokens"], "Active Sessions"),
    ]:
        col.markdown(
            f'<div class="mini"><div class="mini-val">{val}</div>'
            f'<div class="mini-lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

    tabs = st.tabs(["👥 Users", "➕ Create User", "📊 Login Log",
                     "🔑 Test Login"])

    # Tab 0: Users
    with tabs[0]:
        users = list_users()
        if users:
            df = pd.DataFrame(users)
            st.dataframe(df, use_container_width=True, height=300)

            st.markdown('<div class="section-title">User Actions</div>',
                        unsafe_allow_html=True)
            sel_user = st.selectbox(
                "Select user",
                [u["username"] for u in users], key="sel_user")
            sel = next(u for u in users if u["username"] == sel_user)

            ac1, ac2, ac3 = st.columns(3)
            with ac1:
                new_role = st.selectbox("Change role", ROLES, key="nr")
                if st.button("Update Role", key="btn_role"):
                    update_user_role(sel["id"], new_role)
                    st.success(f"Role → {new_role}")
                    st.rerun()
            with ac2:
                if sel.get("is_active"):
                    if st.button("Deactivate", key="btn_deact"):
                        deactivate_user(sel["id"])
                        st.warning("User deactivated")
                        st.rerun()
                else:
                    if st.button("Activate", key="btn_act"):
                        activate_user(sel["id"])
                        st.success("User activated")
                        st.rerun()
            with ac3:
                if st.button("Revoke All Sessions", key="btn_revall"):
                    n = revoke_all_user_tokens(sel["id"])
                    st.info(f"Revoked {n} refresh token(s)")
        else:
            st.info("No users registered yet. Use the Create User tab.")

    # Tab 1: Create User
    with tabs[1]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        cu_name = st.text_input("Username", key="cu_name")
        cu_pass = st.text_input("Password", type="password", key="cu_pass")
        cu_email = st.text_input("Email (optional)", key="cu_email")
        cu_display = st.text_input("Display Name", key="cu_disp")
        cu_role = st.selectbox("Role", ROLES, key="cu_role")
        if st.button("Create User", key="btn_create"):
            if cu_name and cu_pass:
                try:
                    u = create_user(cu_name, cu_pass,
                                    email=cu_email,
                                    display_name=cu_display,
                                    role=cu_role)
                    st.success(f"User '{u['username']}' created ({u['role']})")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        st.markdown('</div>', unsafe_allow_html=True)

    # Tab 2: Login log
    with tabs[2]:
        if stats["recent_logins"]:
            df = pd.DataFrame(stats["recent_logins"])
            df["success"] = df["success"].map({1: "✅", 0: "❌"})
            st.dataframe(df, use_container_width=True, height=380)
        else:
            st.info("No login attempts recorded yet.")

    # Tab 3: Test Login
    with tabs[3]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        tl_user = st.text_input("Username", key="tl_user")
        tl_pass = st.text_input("Password", type="password", key="tl_pass")
        if st.button("Login", key="btn_tl"):
            if tl_user and tl_pass:
                try:
                    result = login(tl_user, tl_pass)
                    st.success(f"Logged in as {result['user']['username']} "
                               f"({result['user']['role']})")
                    st.json({
                        "access_token": result["access_token"][:40] + "...",
                        "refresh_token": result["refresh_token"][:20] + "...",
                        "expires_in": result["expires_in"],
                    })
                except ValueError as exc:
                    st.error(str(exc))
        st.markdown('</div>', unsafe_allow_html=True)

    # Footer
    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/jwt-auth</code> · JWT Auth v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test for all auth functions."""
    import tempfile

    print("=" * 60)
    print("JWT Auth Module — Self-Test")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    try:
        init_auth_tables(tdb)

        # 1. Create users
        print("\n[1/10] Create users ...")
        admin = create_user("admin", "admin12345", role="admin", db_path=tdb)
        assert admin["role"] == "admin"
        mgr = create_user("manager1", "manager123",
                          role="manager", display_name="Mgr One", db_path=tdb)
        viewer = create_user("viewer1", "viewer123",
                             email="v@test.com", db_path=tdb)
        print(f"       ✅ Created 3 users (admin, manager, viewer)")

        # 2. Duplicate check
        print("[2/10] Duplicate username ...")
        try:
            create_user("admin", "other12345", db_path=tdb)
            assert False, "Should have raised"
        except ValueError:
            pass
        print("       ✅ Duplicate correctly rejected")

        # 3. Password validation
        print("[3/10] Short password ...")
        try:
            create_user("shortpw", "abc", db_path=tdb)
            assert False
        except ValueError:
            pass
        print("       ✅ Short password rejected")

        # 4. Login success
        print("[4/10] Login ...")
        result = login("admin", "admin12345", db_path=tdb)
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["user"]["role"] == "admin"
        print(f"       ✅ Login OK, got tokens")

        # 5. Token validation
        print("[5/10] Token validation ...")
        payload = validate_access_token(result["access_token"], tdb)
        assert payload["username"] == "admin"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"
        print(f"       ✅ Token valid: sub={payload['sub'][:8]}...")

        # 6. Token refresh
        print("[6/10] Refresh token ...")
        new_tokens = refresh_access_token(result["refresh_token"], tdb)
        assert "access_token" in new_tokens
        new_payload = validate_access_token(new_tokens["access_token"], tdb)
        assert new_payload["username"] == "admin"
        print(f"       ✅ Refreshed, new token valid")

        # 7. Wrong password + lockout
        print("[7/10] Failed login + lockout ...")
        for i in range(MAX_LOGIN_ATTEMPTS):
            try:
                login("viewer1", "wrongpassword", db_path=tdb)
            except ValueError:
                pass
        try:
            login("viewer1", "viewer123", db_path=tdb)
            assert False, "Should be locked"
        except ValueError as e:
            assert "locked" in str(e).lower()
        print(f"       ✅ Locked after {MAX_LOGIN_ATTEMPTS} failed attempts")

        # 8. Password reset
        print("[8/10] Password reset ...")
        reset_tok = create_password_reset_token("manager1", db_path=tdb)
        assert reset_tok is not None
        ok = reset_password(reset_tok, "newpass12345", tdb)
        assert ok
        result2 = login("manager1", "newpass12345", db_path=tdb)
        assert result2["user"]["username"] == "manager1"
        print(f"       ✅ Password reset + login with new password")

        # 9. Token revocation
        print("[9/10] Token revocation ...")
        revoke_refresh_token(result2["refresh_token"], tdb)
        try:
            refresh_access_token(result2["refresh_token"], tdb)
            assert False
        except ValueError:
            pass
        blocklist_access_token(payload["jti"], payload["exp"], tdb)
        assert is_token_blocklisted(payload["jti"], tdb)
        print(f"       ✅ Refresh revoked, access blocklisted")

        # 10. User management
        print("[10/10] User management ...")
        users = list_users(tdb)
        assert len(users) == 3
        deactivate_user(admin["id"], tdb)
        try:
            login("admin", "admin12345", db_path=tdb)
            assert False
        except ValueError as e:
            assert "deactivated" in str(e).lower()
        activate_user(admin["id"], tdb)
        login("admin", "admin12345", db_path=tdb)
        update_user_role(viewer["id"], "manager", tdb)
        u = get_user(viewer["id"], tdb)
        assert u["role"] == "manager"
        print(f"       ✅ Deactivate/activate/role-change all OK")

        # Stats
        st = get_auth_stats(tdb)
        print(f"\n📊 Stats: {st['users_total']} users, "
              f"{st['logins_24h']} logins(24h), "
              f"{st['failed_24h']} failed(24h)")

        print("\n" + "=" * 60)
        print("✅ ALL JWT AUTH SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(tdb)


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_auth_tables()
    print("=== JWT Auth -- self test ===\n")
    _self_test()
else:
    render_dashboard()
