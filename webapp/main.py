"""
webapp/main.py
──────────────
Full Web App Backend for Birthday Wishes Agent.

FastAPI backend with:
  - JWT authentication (login system)
  - Multi-user support
  - REST API for all agent features
  - WebSocket for real-time updates
  - SQLite user management

Run with:
    uvicorn webapp.main:app --reload --port 8000

Default admin credentials:
    Username: admin
    Password: admin123
    (Change in .env: ADMIN_USERNAME, ADMIN_PASSWORD)
"""

import asyncio
import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values
from fastapi import (Depends, FastAPI, HTTPException,
                     WebSocket, WebSocketDisconnect, status)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from jose import JWTError, jwt
    from passlib.context import CryptContext
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

logger  = logging.getLogger(__name__)
_env    = dotenv_values(".env")
DB_FILE = Path("agent_history.db")
LOG_FILE = Path("agent.log")

SECRET_KEY      = _env.get("SECRET_KEY", "birthday-agent-secret-key-change-in-production")
ALGORITHM       = "HS256"
TOKEN_EXPIRE    = 60 * 24  # 24 hours
ADMIN_USERNAME  = _env.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD  = _env.get("ADMIN_PASSWORD", "admin123")


# ──────────────────────────────────────────────
# APP SETUP
# ──────────────────────────────────────────────
app = FastAPI(
    title="Birthday Wishes Agent",
    description="Full web app for managing LinkedIn birthday wishes",
    version="5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (React frontend)
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────
if JWT_AVAILABLE:
    pwd_context    = CryptContext(schemes=["bcrypt"], deprecated="auto")
    oauth2_scheme  = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    def create_token(data: dict) -> str:
        payload = data.copy()
        payload["exp"] = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE)
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    def decode_token(token: str) -> dict:
        try:
            return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            return {}
else:
    def hash_password(p): return p
    def verify_password(p, h): return p == h
    def create_token(d): return json.dumps(d)
    def decode_token(t):
        try: return json.loads(t)
        except: return {}


# ──────────────────────────────────────────────
# USER DB
# ──────────────────────────────────────────────
USER_DB = Path("users.db")

def init_user_db():
    with sqlite3.connect(USER_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT    NOT NULL UNIQUE,
                password   TEXT    NOT NULL,
                role       TEXT    NOT NULL DEFAULT 'user',
                created_at TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id    INTEGER NOT NULL,
                key        TEXT    NOT NULL,
                value      TEXT,
                PRIMARY KEY (user_id, key)
            )
        """)
        # Create default admin
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (username, password, role, created_at) "
                "VALUES (?, ?, 'admin', ?)",
                (ADMIN_USERNAME, hash_password(ADMIN_PASSWORD),
                 datetime.now().isoformat()),
            )
        conn.commit()
    logger.info("🗄️  User database ready.")

init_user_db()


def get_user(username: str) -> dict | None:
    with sqlite3.connect(USER_DB) as conn:
        row = conn.execute(
            "SELECT id, username, password, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    return {"id": row[0], "username": row[1],
            "password": row[2], "role": row[3]}


def get_all_users() -> list[dict]:
    with sqlite3.connect(USER_DB) as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY id"
        ).fetchall()
    return [{"id": r[0], "username": r[1], "role": r[2], "created_at": r[3]}
            for r in rows]


async def get_current_user(token: str = Depends(
    OAuth2PasswordBearer(tokenUrl="/api/auth/login") if JWT_AVAILABLE
    else lambda: "admin"
)):
    payload = decode_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ──────────────────────────────────────────────
# PYDANTIC MODELS
# ──────────────────────────────────────────────
class UserCreate(BaseModel):
    username: str
    password: str
    role: Optional[str] = "user"

class SettingUpdate(BaseModel):
    key: str
    value: str

class TaskRequest(BaseModel):
    task: str
    dry_run: Optional[bool] = True


# ──────────────────────────────────────────────
# DB HELPERS
# ──────────────────────────────────────────────
def get_stats() -> dict:
    if not DB_FILE.exists():
        return {"wishes": 0, "replies": 0, "followups": 0, "contacts": 0}
    try:
        conn = sqlite3.connect(DB_FILE)
        wishes   = conn.execute(
            "SELECT COUNT(*) FROM history WHERE task LIKE '%Birthday%' AND dry_run=0"
        ).fetchone()[0]
        replies  = conn.execute(
            "SELECT COUNT(*) FROM history WHERE task LIKE '%Reply%' AND dry_run=0"
        ).fetchone()[0]
        contacts = conn.execute(
            "SELECT COUNT(DISTINCT contact) FROM history WHERE dry_run=0"
        ).fetchone()[0]
        try:
            followups = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE followup_sent=1"
            ).fetchone()[0]
        except Exception:
            followups = 0
        conn.close()
        return {"wishes": wishes, "replies": replies,
                "followups": followups, "contacts": contacts}
    except Exception:
        return {"wishes": 0, "replies": 0, "followups": 0, "contacts": 0}


def get_recent_activity(limit: int = 20) -> list:
    if not DB_FILE.exists():
        return []
    try:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(
            "SELECT date, task, contact, message, dry_run "
            "FROM history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [{"date": r[0], "task": r[1], "contact": r[2],
                 "message": r[3], "dry_run": bool(r[4])} for r in rows]
    except Exception:
        return []


def read_log_tail(lines: int = 100) -> list[str]:
    if not LOG_FILE.exists():
        return []
    try:
        return LOG_FILE.read_text(encoding="utf-8").splitlines()[-lines:]
    except Exception:
        return []


# ──────────────────────────────────────────────
# WEBSOCKET MANAGER
# ──────────────────────────────────────────────
class WSManager:
    def __init__(self):
        self.connections: dict[str, WebSocket] = {}  # user → ws

    async def connect(self, ws: WebSocket, username: str):
        await ws.accept()
        self.connections[username] = ws

    def disconnect(self, username: str):
        self.connections.pop(username, None)

    async def broadcast(self, message: dict):
        dead = []
        for username, ws in self.connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(username)
        for u in dead:
            self.connections.pop(u, None)

    async def send_to(self, username: str, message: dict):
        ws = self.connections.get(username)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.connections.pop(username, None)

ws_manager = WSManager()


# ──────────────────────────────────────────────
# LOG WATCHER
# ──────────────────────────────────────────────
async def watch_log():
    last_size = 0
    while True:
        try:
            if LOG_FILE.exists():
                size = LOG_FILE.stat().st_size
                if size > last_size:
                    with open(LOG_FILE, "r", encoding="utf-8") as f:
                        f.seek(last_size)
                        new_lines = f.read()
                    last_size = size
                    for line in new_lines.splitlines():
                        if line.strip():
                            await ws_manager.broadcast({
                                "type":      "log",
                                "message":   line,
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                            })
        except Exception:
            pass
        await asyncio.sleep(0.5)


@app.on_event("startup")
async def startup():
    asyncio.create_task(watch_log())


# ──────────────────────────────────────────────
# AUTH ROUTES
# ──────────────────────────────────────────────
@app.post("/api/auth/login")
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = get_user(form.username)
    if not user or not verify_password(form.password, user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_token({"sub": user["username"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer",
            "role": user["role"], "username": user["username"]}


@app.get("/api/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"username": user["username"], "role": user["role"]}


# ──────────────────────────────────────────────
# USER MANAGEMENT ROUTES (admin only)
# ──────────────────────────────────────────────
@app.get("/api/users")
async def list_users(admin: dict = Depends(require_admin)):
    return get_all_users()


@app.post("/api/users")
async def create_user(
    body: UserCreate,
    admin: dict = Depends(require_admin),
):
    try:
        with sqlite3.connect(USER_DB) as conn:
            conn.execute(
                "INSERT INTO users (username, password, role, created_at) "
                "VALUES (?, ?, ?, ?)",
                (body.username, hash_password(body.password),
                 body.role, datetime.now().isoformat()),
            )
            conn.commit()
        return {"status": "created", "username": body.username}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")


@app.delete("/api/users/{username}")
async def delete_user(
    username: str,
    admin: dict = Depends(require_admin),
):
    if username == ADMIN_USERNAME:
        raise HTTPException(status_code=400, detail="Cannot delete admin")
    with sqlite3.connect(USER_DB) as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
    return {"status": "deleted"}


# ──────────────────────────────────────────────
# DASHBOARD DATA ROUTES
# ──────────────────────────────────────────────
@app.get("/api/stats")
async def api_stats(user: dict = Depends(get_current_user)):
    return get_stats()


@app.get("/api/activity")
async def api_activity(
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    return get_recent_activity(limit)


@app.get("/api/logs")
async def api_logs(
    lines: int = 100,
    user: dict = Depends(get_current_user),
):
    return {"logs": read_log_tail(lines)}


# ──────────────────────────────────────────────
# SETTINGS ROUTES
# ──────────────────────────────────────────────
@app.get("/api/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    with sqlite3.connect(USER_DB) as conn:
        rows = conn.execute(
            "SELECT key, value FROM user_settings WHERE user_id = ?",
            (user["id"],),
        ).fetchall()
    return {r[0]: r[1] for r in rows}


@app.post("/api/settings")
async def update_setting(
    body: SettingUpdate,
    user: dict = Depends(get_current_user),
):
    with sqlite3.connect(USER_DB) as conn:
        conn.execute(
            "INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user["id"], body.key, body.value),
        )
        conn.commit()
    return {"status": "saved"}


# ──────────────────────────────────────────────
# WEBSOCKET
# ──────────────────────────────────────────────
@app.websocket("/ws/{token}")
async def websocket_endpoint(ws: WebSocket, token: str):
    payload  = decode_token(token)
    username = payload.get("sub", "anonymous")

    await ws_manager.connect(ws, username)
    try:
        await ws.send_json({
            "type":     "init",
            "stats":    get_stats(),
            "activity": get_recent_activity(),
            "logs":     read_log_tail(30),
            "user":     username,
        })
        while True:
            data = await ws.receive_text()
            msg  = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif msg.get("type") == "get_stats":
                await ws.send_json({"type": "stats_update",
                                    "stats": get_stats()})
            elif msg.get("type") == "get_activity":
                await ws.send_json({"type": "activity_update",
                                    "activity": get_recent_activity()})
    except WebSocketDisconnect:
        ws_manager.disconnect(username)


# ──────────────────────────────────────────────
# FRONTEND ROUTE
# ──────────────────────────────────────────────
@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_frontend(full_path: str):
    index = frontend_dir / "index.html"
    if index.exists():
        return HTMLResponse(content=index.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Frontend not found. Place index.html in webapp/frontend/</h1>")