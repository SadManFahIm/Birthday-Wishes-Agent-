"""
realtime_dashboard.py
─────────────────────
Real-time Dashboard for Birthday Wishes Agent.

Built with FastAPI + WebSocket — shows live agent activity
as it happens, without page refresh.

Features:
  - Live log streaming via WebSocket
  - Real-time stats (wishes, replies, follow-ups)
  - Start/Stop agent tasks from the browser
  - Live activity feed with timestamps
  - Connection status indicator

Run with:
    uvicorn realtime_dashboard:app --reload --port 8000

Then open: http://localhost:8000
"""

import asyncio
import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

DB_FILE  = Path("agent_history.db")
LOG_FILE = Path("agent.log")

# ──────────────────────────────────────────────
# FASTAPI APP
# ──────────────────────────────────────────────
app = FastAPI(title="Birthday Wishes Agent — Real-time Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

# Store active WebSocket connections
active_connections: Set[WebSocket] = set()


# ──────────────────────────────────────────────
# WEBSOCKET MANAGER
# ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.add(ws)
        logger.info("🔌 WebSocket connected. Total: %d", len(self.connections))

    def disconnect(self, ws: WebSocket):
        self.connections.discard(ws)
        logger.info("🔌 WebSocket disconnected. Total: %d", len(self.connections))

    async def broadcast(self, message: dict):
        """Send a message to all connected clients."""
        dead = set()
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.connections.discard(ws)


manager = ConnectionManager()


# ──────────────────────────────────────────────
# DB HELPERS
# ──────────────────────────────────────────────
def get_stats() -> dict:
    if not DB_FILE.exists():
        return {"wishes": 0, "replies": 0, "followups": 0, "contacts": 0}
    try:
        conn = sqlite3.connect(DB_FILE)
        wishes = conn.execute(
            "SELECT COUNT(*) FROM history WHERE task LIKE '%Birthday%' AND dry_run=0"
        ).fetchone()[0]
        replies = conn.execute(
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


def get_recent_activity(limit: int = 10) -> list:
    if not DB_FILE.exists():
        return []
    try:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(
            "SELECT date, task, contact, message, dry_run "
            "FROM history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [
            {"date": r[0], "task": r[1], "contact": r[2],
             "message": r[3][:80], "dry_run": bool(r[4])}
            for r in rows
        ]
    except Exception:
        return []


def read_log_tail(lines: int = 50) -> list[str]:
    if not LOG_FILE.exists():
        return []
    try:
        all_lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        return all_lines[-lines:]
    except Exception:
        return []


# ──────────────────────────────────────────────
# LOG WATCHER (streams new log lines via WS)
# ──────────────────────────────────────────────
async def watch_log_file():
    """
    Background task that watches agent.log for new lines
    and broadcasts them to all connected WebSocket clients.
    """
    last_size = 0
    while True:
        try:
            if LOG_FILE.exists():
                current_size = LOG_FILE.stat().st_size
                if current_size > last_size:
                    with open(LOG_FILE, "r", encoding="utf-8") as f:
                        f.seek(last_size)
                        new_lines = f.read()
                    last_size = current_size
                    for line in new_lines.splitlines():
                        if line.strip():
                            await manager.broadcast({
                                "type":      "log",
                                "message":   line,
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                            })
        except Exception:
            pass
        await asyncio.sleep(0.5)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(watch_log_file())
    logger.info("🚀 Real-time dashboard started.")


# ──────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ──────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Send initial data on connect
        await ws.send_json({
            "type":     "init",
            "stats":    get_stats(),
            "activity": get_recent_activity(),
            "logs":     read_log_tail(30),
        })

        # Keep connection alive + handle incoming messages
        while True:
            data = await ws.receive_text()
            msg  = json.loads(data)

            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})

            elif msg.get("type") == "get_stats":
                await ws.send_json({
                    "type":  "stats_update",
                    "stats": get_stats(),
                })

            elif msg.get("type") == "get_activity":
                await ws.send_json({
                    "type":     "activity_update",
                    "activity": get_recent_activity(),
                })

    except WebSocketDisconnect:
        manager.disconnect(ws)


# ──────────────────────────────────────────────
# REST ENDPOINTS
# ──────────────────────────────────────────────
@app.get("/api/stats")
async def api_stats():
    return get_stats()


@app.get("/api/activity")
async def api_activity():
    return get_recent_activity(20)


@app.get("/api/logs")
async def api_logs(lines: int = 50):
    return {"logs": read_log_tail(lines)}


@app.post("/api/broadcast")
async def api_broadcast(message: dict):
    """Broadcast a custom message to all dashboard clients."""
    await manager.broadcast(message)
    return {"status": "sent", "clients": len(manager.connections)}


# ──────────────────────────────────────────────
# HTML DASHBOARD
# ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🎂 Birthday Agent — Live Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'Segoe UI', sans-serif;
      background: #0E1117;
      color: #FAFAFA;
      min-height: 100vh;
    }

    /* ── HEADER ── */
    .header {
      background: linear-gradient(135deg, #1a237e, #4CAF50);
      padding: 20px 30px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .header h1 { font-size: 1.4rem; }
    .status-dot {
      width: 12px; height: 12px;
      border-radius: 50%;
      background: #F44336;
      display: inline-block;
      margin-right: 8px;
      transition: background 0.3s;
    }
    .status-dot.connected { background: #4CAF50; animation: pulse 2s infinite; }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.4; }
    }

    /* ── LAYOUT ── */
    .container { padding: 20px; max-width: 1400px; margin: auto; }

    /* ── KPI CARDS ── */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .kpi-card {
      background: #1E2329;
      border: 1px solid #2E3440;
      border-radius: 12px;
      padding: 20px;
      text-align: center;
      transition: border-color 0.3s;
    }
    .kpi-card:hover { border-color: #4CAF50; }
    .kpi-value {
      font-size: 2.2rem;
      font-weight: 700;
      color: #4CAF50;
    }
    .kpi-label { color: #888; font-size: 0.85rem; margin-top: 4px; }

    /* ── TWO COLUMN ── */
    .two-col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 24px;
    }
    @media (max-width: 768px) { .two-col { grid-template-columns: 1fr; } }

    /* ── PANELS ── */
    .panel {
      background: #1E2329;
      border: 1px solid #2E3440;
      border-radius: 12px;
      padding: 20px;
      height: 380px;
      display: flex;
      flex-direction: column;
    }
    .panel h3 {
      font-size: 1rem;
      margin-bottom: 12px;
      color: #4CAF50;
      border-bottom: 1px solid #2E3440;
      padding-bottom: 8px;
    }
    .panel-body { flex: 1; overflow-y: auto; }
    .panel-body::-webkit-scrollbar { width: 4px; }
    .panel-body::-webkit-scrollbar-thumb {
      background: #2E3440; border-radius: 4px;
    }

    /* ── LOG LINES ── */
    .log-line {
      font-family: 'Courier New', monospace;
      font-size: 0.78rem;
      padding: 3px 0;
      border-bottom: 1px solid #1a1a2a;
      color: #ccc;
      word-break: break-all;
    }
    .log-line.new {
      animation: highlight 1.5s ease-out;
    }
    @keyframes highlight {
      0%   { background: #1a3a2a; }
      100% { background: transparent; }
    }
    .log-line .ts { color: #555; margin-right: 8px; }
    .log-line.info    { color: #82b1ff; }
    .log-line.error   { color: #ff5252; }
    .log-line.warning { color: #ffab40; }
    .log-line.success { color: #69f0ae; }

    /* ── ACTIVITY ITEMS ── */
    .activity-item {
      padding: 10px 0;
      border-bottom: 1px solid #2E3440;
      display: flex;
      align-items: flex-start;
      gap: 12px;
    }
    .activity-icon {
      font-size: 1.2rem;
      min-width: 24px;
    }
    .activity-text .contact {
      font-weight: 600;
      color: #FAFAFA;
    }
    .activity-text .task {
      font-size: 0.8rem;
      color: #4CAF50;
    }
    .activity-text .message {
      font-size: 0.78rem;
      color: #888;
      margin-top: 2px;
    }
    .activity-text .date {
      font-size: 0.75rem;
      color: #555;
    }
    .mode-badge {
      font-size: 0.7rem;
      padding: 2px 8px;
      border-radius: 10px;
      background: #1a3a2a;
      color: #4CAF50;
      margin-left: 8px;
    }
    .mode-badge.dryrun {
      background: #2a2a1a;
      color: #FFC107;
    }

    /* ── FULL-WIDTH LOG ── */
    .full-panel {
      background: #1E2329;
      border: 1px solid #2E3440;
      border-radius: 12px;
      padding: 20px;
      height: 300px;
      display: flex;
      flex-direction: column;
    }
    .full-panel h3 {
      font-size: 1rem;
      margin-bottom: 12px;
      color: #4CAF50;
      border-bottom: 1px solid #2E3440;
      padding-bottom: 8px;
      display: flex;
      justify-content: space-between;
    }
    .clear-btn {
      font-size: 0.75rem;
      background: #2E3440;
      color: #aaa;
      border: none;
      border-radius: 6px;
      padding: 3px 10px;
      cursor: pointer;
    }
    .clear-btn:hover { background: #3E4450; }

    /* ── FOOTER ── */
    .footer {
      text-align: center;
      color: #444;
      font-size: 0.8rem;
      padding: 20px;
    }
  </style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <h1>🎂 Birthday Wishes Agent — Live Dashboard</h1>
  <div>
    <span class="status-dot" id="statusDot"></span>
    <span id="statusText" style="font-size:0.9rem;color:#aaa;">Connecting...</span>
  </div>
</div>

<div class="container">

  <!-- KPI CARDS -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-value" id="kpiWishes">—</div>
      <div class="kpi-label">🎂 Wishes Sent</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value" id="kpiReplies">—</div>
      <div class="kpi-label">💬 Replies Sent</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value" id="kpiFollowups">—</div>
      <div class="kpi-label">🔔 Follow-ups</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value" id="kpiContacts">—</div>
      <div class="kpi-label">👥 Contacts</div>
    </div>
  </div>

  <!-- TWO COLUMNS -->
  <div class="two-col">

    <!-- LIVE LOG -->
    <div class="panel">
      <h3>📋 Live Agent Log</h3>
      <div class="panel-body" id="liveLog"></div>
    </div>

    <!-- RECENT ACTIVITY -->
    <div class="panel">
      <h3>🕐 Recent Activity</h3>
      <div class="panel-body" id="activityFeed"></div>
    </div>

  </div>

  <!-- FULL WIDTH LOG -->
  <div class="full-panel">
    <h3>
      🖥️ Full Log Stream
      <button class="clear-btn" onclick="clearLog()">Clear</button>
    </h3>
    <div class="panel-body" id="fullLog" style="font-family:monospace;font-size:0.75rem;"></div>
  </div>

</div>

<div class="footer">
  🎂 Birthday Wishes Agent v5.0 — Real-time Dashboard |
  Built with FastAPI + WebSocket
</div>

<!-- WEBSOCKET SCRIPT -->
<script>
  let ws;
  let logCount = 0;
  const MAX_LOGS = 200;

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
      document.getElementById('statusDot').classList.add('connected');
      document.getElementById('statusText').textContent = 'Connected';
      document.getElementById('statusText').style.color = '#4CAF50';
    };

    ws.onclose = () => {
      document.getElementById('statusDot').classList.remove('connected');
      document.getElementById('statusText').textContent = 'Disconnected — Reconnecting...';
      document.getElementById('statusText').style.color = '#F44336';
      setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      document.getElementById('statusText').textContent = 'Connection Error';
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    };
  }

  function handleMessage(msg) {
    if (msg.type === 'init') {
      updateStats(msg.stats);
      renderActivity(msg.activity);
      if (msg.logs) {
        msg.logs.forEach(line => appendLog(line, false));
      }
    }
    else if (msg.type === 'stats_update') {
      updateStats(msg.stats);
    }
    else if (msg.type === 'activity_update') {
      renderActivity(msg.activity);
    }
    else if (msg.type === 'log') {
      appendLog(msg.message, true);
      appendFullLog(msg.message, msg.timestamp);
      // Refresh stats on each log
      ws.send(JSON.stringify({ type: 'get_stats' }));
    }
    else if (msg.type === 'pong') {
      // heartbeat ok
    }
  }

  function updateStats(stats) {
    document.getElementById('kpiWishes').textContent    = stats.wishes    ?? '—';
    document.getElementById('kpiReplies').textContent   = stats.replies   ?? '—';
    document.getElementById('kpiFollowups').textContent = stats.followups ?? '—';
    document.getElementById('kpiContacts').textContent  = stats.contacts  ?? '—';
  }

  function appendLog(line, isNew) {
    const container = document.getElementById('liveLog');
    const div = document.createElement('div');
    div.className = 'log-line' + (isNew ? ' new' : '');

    // Color code by log level
    if (line.includes('[ERROR]') || line.includes('❌'))
      div.classList.add('error');
    else if (line.includes('[WARNING]') || line.includes('⚠️'))
      div.classList.add('warning');
    else if (line.includes('✅') || line.includes('🎂') || line.includes('💬'))
      div.classList.add('success');
    else
      div.classList.add('info');

    div.textContent = line;
    container.appendChild(div);

    // Limit log lines
    logCount++;
    if (logCount > MAX_LOGS) {
      container.removeChild(container.firstChild);
    }

    // Auto-scroll to bottom
    container.scrollTop = container.scrollHeight;
  }

  function appendFullLog(line, timestamp) {
    const container = document.getElementById('fullLog');
    const div = document.createElement('div');
    div.innerHTML = `<span style="color:#555;">[${timestamp}]</span> ${escapeHtml(line)}`;
    container.appendChild(div);
    if (container.children.length > 500)
      container.removeChild(container.firstChild);
    container.scrollTop = container.scrollHeight;
  }

  function renderActivity(activity) {
    const container = document.getElementById('activityFeed');
    container.innerHTML = '';
    if (!activity || activity.length === 0) {
      container.innerHTML = '<p style="color:#555;padding:12px;">No activity yet.</p>';
      return;
    }
    activity.forEach(item => {
      const icon = item.task.includes('Birthday') ? '🎂'
                 : item.task.includes('Reply')    ? '💬'
                 : item.task.includes('Follow')   ? '🔔'
                 : '📋';
      const modeLabel = item.dry_run
        ? '<span class="mode-badge dryrun">🧪 Dry Run</span>'
        : '<span class="mode-badge">🟢 Live</span>';
      const div = document.createElement('div');
      div.className = 'activity-item';
      div.innerHTML = `
        <div class="activity-icon">${icon}</div>
        <div class="activity-text">
          <div class="contact">${escapeHtml(item.contact)} ${modeLabel}</div>
          <div class="task">${escapeHtml(item.task)}</div>
          <div class="message">${escapeHtml(item.message || '')}</div>
          <div class="date">${item.date}</div>
        </div>
      `;
      container.appendChild(div);
    });
  }

  function clearLog() {
    document.getElementById('liveLog').innerHTML = '';
    document.getElementById('fullLog').innerHTML = '';
    logCount = 0;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // Heartbeat every 30s
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }));
      ws.send(JSON.stringify({ type: 'get_activity' }));
    }
  }, 30000);

  // Start connection
  connect();
</script>
</body>
</html>
""")