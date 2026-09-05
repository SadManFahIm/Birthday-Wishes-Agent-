"""
FastAPI Backend -- Birthday Wishes Agent v9.0
Proper REST API replacing Streamlit as the primary interface.
All agent features exposed as versioned JSON endpoints.

Structure:
  GET  /api/v1/health          -- agent + network health
  GET  /api/v1/contacts        -- contact list with tiers
  GET  /api/v1/queue           -- pending wish queue
  POST /api/v1/queue/{id}/approve
  POST /api/v1/queue/{id}/reject
  GET  /api/v1/analytics       -- platform ROI, sentiment, score trend
  POST /api/v1/wish/generate   -- generate wish for a contact
  POST /api/v1/wish/send       -- send generated wish
  GET  /api/v1/vip             -- VIP contacts
  POST /api/v1/vip/{id}        -- flag contact as VIP
  GET  /api/v1/revenue         -- revenue attribution summary
  POST /api/v1/revenue         -- log new deal
  WS   /ws/live                -- real-time agent log stream

Run:
  pip install fastapi uvicorn
  uvicorn fastapi_backend:app --reload --port 8000

Integrates with: all v8.0/v9.0 modules, agent.py
"""

import sqlite3
import json
import asyncio
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from contextlib import asynccontextmanager

# FastAPI imports -- guarded so module can be syntax-checked without install
try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    class BaseModel:           # type: ignore
        pass
    class WebSocket:           # type: ignore
        pass
    class WebSocketDisconnect(Exception):  # type: ignore
        pass
    def Field(*a, **k):        # type: ignore
        return None
    def HTTPException(*a, **k):  # type: ignore
        return Exception()
    status = type("status", (), {})()

DB_PATH = Path("agent_history.db")

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class WishGenerateRequest(BaseModel):
    contact_id:   str
    contact_name: str
    platform:     str = "LinkedIn"
    style:        str = "warm"
    use_consensus:bool = False


class WishSendRequest(BaseModel):
    contact_id:   str
    contact_name: str
    platform:     str
    wish_text:    str
    phone_number: Optional[str] = None
    telegram_id:  Optional[str] = None


class QueueActionRequest(BaseModel):
    reviewed_by: str = "api_user"
    edited_text: Optional[str] = None


class VIPFlagRequest(BaseModel):
    contact_name: str
    vip_level:    str = Field(default="gold", pattern="^(platinum|gold|silver)$")
    reason:       str = ""


class RevenueLogRequest(BaseModel):
    contact_id:       str
    contact_name:     str
    deal_name:        str
    deal_value:       float
    attribution_type: str = "direct"
    currency:         str = "BDT"
    notes:            str = ""


class ContactUpsertRequest(BaseModel):
    contact_id:   str
    contact_name: str
    platform:     str = "LinkedIn"
    tier:         str = "Acquaintance"
    strength:     float = 5.0


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(table: str) -> bool:
    conn = _db()
    row  = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone()
    conn.close()
    return bool(row)


def _safe_import(module: str, attr: str):
    """Import agent module function; return None stub if unavailable."""
    try:
        mod = __import__(module, fromlist=[attr])
        return getattr(mod, attr, None)
    except ImportError:
        return None


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: str):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> "FastAPI":
    if not HAS_FASTAPI:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        print("[FastAPI] Birthday Wishes Agent API starting...")
        yield
        print("[FastAPI] Shutting down.")

    application = FastAPI(
        title="Birthday Wishes Agent API",
        description="REST API for Birthday Wishes Agent v9.0",
        version="9.0.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health ────────────────────────────────────────────────────────────────

    @application.get("/api/v1/health", tags=["System"])
    def get_health():
        """Agent status + network health score."""
        compute = _safe_import("dashboards.network_health_score",
                               "compute_health_score")
        is_paused_fn = _safe_import("automation.auto_pause_on_anomaly", "is_paused")

        health_data = {"score": None, "grade": "N/A", "grade_label": "No data"}
        if compute:
            try:
                h = compute(save_snapshot=False, verbose=False)
                health_data = {
                    "score":       h["score"],
                    "grade":       h["grade"],
                    "grade_label": h["grade_label"],
                    "color":       h["color"],
                }
            except Exception:
                pass

        paused = False
        if is_paused_fn:
            try:
                paused = is_paused_fn()
            except Exception:
                pass

        return {
            "status":         "paused" if paused else "running",
            "paused":         paused,
            "network_health": health_data,
            "timestamp":      datetime.now().isoformat(),
            "version":        "9.0.0",
        }

    # ── Contacts ──────────────────────────────────────────────────────────────

    @application.get("/api/v1/contacts", tags=["Contacts"])
    def list_contacts(tier: Optional[str] = None, limit: int = 50):
        """List contacts with tier, sentiment, and strength data."""
        if not _table_exists("contact_tier"):
            return {"contacts": [], "total": 0}
        conn  = _db()
        query = "SELECT contact_id, contact_name, current_tier, tier_score, last_adjusted FROM contact_tier"
        params: list = []
        if tier:
            query  += " WHERE current_tier=?"
            params.append(tier)
        query += f" ORDER BY tier_score DESC LIMIT {limit}"
        rows  = conn.execute(query, params).fetchall()
        conn.close()
        return {
            "contacts": [dict(r) for r in rows],
            "total":    len(rows),
        }

    @application.post("/api/v1/contacts", tags=["Contacts"], status_code=201)
    def upsert_contact(req: ContactUpsertRequest):
        """Add or update a contact node."""
        upsert = _safe_import("dashboards.relationship_graph", "upsert_node")
        add_edge_fn = _safe_import("dashboards.relationship_graph", "add_edge")
        if upsert:
            upsert(req.contact_id, req.contact_name, req.platform,
                   req.tier, req.strength)
        if add_edge_fn:
            add_edge_fn("ME", req.contact_id, "direct", req.strength)
        return {"success": True, "contact_id": req.contact_id}

    # ── Wish queue ────────────────────────────────────────────────────────────

    @application.get("/api/v1/queue", tags=["Queue"])
    def get_queue(status: str = "pending"):
        """Return wish queue items by status."""
        if not _table_exists("wish_queue"):
            return {"items": [], "total": 0}
        conn = _db()
        rows = conn.execute("""
            SELECT id, contact_name, platform, wish_text,
                   personalization_score, status, created_at
            FROM wish_queue WHERE status=?
            ORDER BY created_at ASC
        """, (status,)).fetchall()
        conn.close()
        return {"items": [dict(r) for r in rows], "total": len(rows)}

    @application.post("/api/v1/queue/{item_id}/approve", tags=["Queue"])
    def approve_queue_item(item_id: int, req: QueueActionRequest):
        """Approve a queued wish for sending."""
        if not _table_exists("wish_queue"):
            raise HTTPException(status_code=404, detail="Queue table not found")
        conn = _db()
        row  = conn.execute(
            "SELECT id FROM wish_queue WHERE id=?", (item_id,)
        ).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Item not found")
        if req.edited_text:
            conn.execute("UPDATE wish_queue SET wish_text=? WHERE id=?",
                         (req.edited_text, item_id))
        conn.execute("""
            UPDATE wish_queue SET status='approved', approved_by=?,
            approved_at=? WHERE id=?
        """, (req.reviewed_by, datetime.now().isoformat(), item_id))
        conn.commit()
        conn.close()
        return {"success": True, "item_id": item_id, "status": "approved"}

    @application.post("/api/v1/queue/{item_id}/reject", tags=["Queue"])
    def reject_queue_item(item_id: int, req: QueueActionRequest):
        """Reject a queued wish."""
        if not _table_exists("wish_queue"):
            raise HTTPException(status_code=404, detail="Queue table not found")
        conn = _db()
        conn.execute("""
            UPDATE wish_queue SET status='rejected', approved_by=?,
            approved_at=? WHERE id=?
        """, (req.reviewed_by, datetime.now().isoformat(), item_id))
        conn.commit()
        conn.close()
        return {"success": True, "item_id": item_id, "status": "rejected"}

    # ── Wish generation & sending ─────────────────────────────────────────────

    @application.post("/api/v1/wish/generate", tags=["Wishes"])
    def generate_wish(req: WishGenerateRequest):
        """Generate a birthday wish using active prompt (or consensus)."""
        if req.use_consensus:
            gen_fn = _safe_import("ai.multi_model_consensus", "generate_consensus_wish")
            if gen_fn:
                try:
                    contact = {
                        "name": req.contact_name,
                        "job": "", "company": "", "memory": "",
                    }
                    result = gen_fn(req.contact_id, contact,
                                    req.platform, req.style, verbose=False)
                    return {
                        "wish_text":    result["winner_wish"],
                        "score":        result["winner_score"],
                        "model":        result["winner_model"],
                        "method":       "consensus",
                    }
                except Exception as exc:
                    raise HTTPException(status_code=500, detail=str(exc))

        # Default: use active prompt template
        get_prompt = _safe_import("ai.self_improving_agent", "get_active_prompt")
        prompt_ver = "v1.0"
        if get_prompt:
            try:
                p = get_prompt()
                prompt_ver = p.get("version_tag", "v1.0")
            except Exception:
                pass

        wish_text = (
            f"Happy Birthday {req.contact_name.split()[0]}! "
            f"Wishing you a wonderful {datetime.now().year}. "
            f"Hope this year brings everything you've been working toward!"
        )
        return {
            "wish_text":    wish_text,
            "score":        None,
            "prompt_version":prompt_ver,
            "method":       "template",
        }

    @application.post("/api/v1/wish/send", tags=["Wishes"])
    def send_wish(req: WishSendRequest):
        """Send a wish via the appropriate platform."""
        results: dict[str, Any] = {}

        if req.platform in ("WhatsApp", "whatsapp") and req.phone_number:
            send_fn = _safe_import("platforms.whatsapp_business_api", "send_text_message")
            if send_fn:
                r = send_fn(req.contact_id, req.contact_name,
                            req.phone_number, req.wish_text)
                results["whatsapp"] = r

        elif req.platform in ("Telegram", "telegram") and req.telegram_id:
            send_fn = _safe_import("platforms.telegram_birthday", "send_birthday_wish")
            if send_fn:
                r = send_fn(req.contact_id, req.contact_name,
                            req.wish_text, req.telegram_id)
                results["telegram"] = r

        else:
            results["note"] = (f"Platform '{req.platform}' send handled by "
                               "agent.py browser automation")

        return {"success": True, "platform": req.platform, "results": results}

    # ── Analytics ─────────────────────────────────────────────────────────────

    @application.get("/api/v1/analytics/platform-roi", tags=["Analytics"])
    def get_platform_roi(period_days: int = 30):
        """Platform ROI comparison."""
        compute = _safe_import("dashboards.platform_roi_comparison",
                               "compute_platform_roi")
        if not compute:
            raise HTTPException(status_code=503, detail="Module unavailable")
        try:
            return compute(period_days)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @application.get("/api/v1/analytics/sentiment", tags=["Analytics"])
    def get_sentiment_trend():
        """Aggregate sentiment distribution."""
        get_agg = _safe_import("contacts.reply_sentiment_trend", "get_aggregate_trend")
        if not get_agg:
            return {"distribution": {}, "weekly_avg": []}
        try:
            return get_agg(30)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @application.get("/api/v1/analytics/score-trend", tags=["Analytics"])
    def get_score_trend(period_days: int = 90, bucket: str = "month"):
        """Personalization score trend."""
        get_trend = _safe_import("dashboards.personalization_score_trend",
                                 "get_aggregate_trend")
        if not get_trend:
            return {"trend": []}
        try:
            return {"trend": get_trend(period_days, bucket)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── VIP ───────────────────────────────────────────────────────────────────

    @application.get("/api/v1/vip", tags=["VIP"])
    def list_vip():
        """List all active VIP contacts."""
        get_fn = _safe_import("contacts.vip_contact_flagging", "get_all_vip_contacts")
        if not get_fn:
            return {"vip_contacts": []}
        return {"vip_contacts": get_fn()}

    @application.post("/api/v1/vip/{contact_id}", tags=["VIP"], status_code=201)
    def flag_vip(contact_id: str, req: VIPFlagRequest):
        """Flag a contact as VIP."""
        flag_fn = _safe_import("contacts.vip_contact_flagging", "flag_vip")
        if not flag_fn:
            raise HTTPException(status_code=503, detail="VIP module unavailable")
        flag_fn(contact_id, req.contact_name, req.vip_level, req.reason)
        return {"success": True, "contact_id": contact_id,
                "vip_level": req.vip_level}

    @application.delete("/api/v1/vip/{contact_id}", tags=["VIP"])
    def unflag_vip_contact(contact_id: str):
        """Remove VIP status from a contact."""
        unflag = _safe_import("contacts.vip_contact_flagging", "unflag_vip")
        if unflag:
            unflag(contact_id)
        return {"success": True, "contact_id": contact_id}

    # ── Revenue ───────────────────────────────────────────────────────────────

    @application.get("/api/v1/revenue", tags=["Revenue"])
    def get_revenue(days: int = 365):
        """Revenue attribution summary."""
        get_stats = _safe_import("dashboards.revenue_attribution", "get_summary_stats")
        get_top   = _safe_import("dashboards.revenue_attribution", "get_top_contacts")
        result: dict = {}
        if get_stats:
            result["summary"] = get_stats(days)
        if get_top:
            result["top_contacts"] = get_top(10)
        return result

    @application.post("/api/v1/revenue", tags=["Revenue"], status_code=201)
    def log_revenue(req: RevenueLogRequest):
        """Log a new revenue attribution."""
        log_fn = _safe_import("dashboards.revenue_attribution", "log_attribution")
        if not log_fn:
            raise HTTPException(status_code=503, detail="Revenue module unavailable")
        row_id = log_fn(
            req.contact_id, req.contact_name, req.deal_name,
            req.deal_value, req.attribution_type, req.currency,
            notes=req.notes)
        return {"success": True, "log_id": row_id}

    # ── Agent control ─────────────────────────────────────────────────────────

    @application.post("/api/v1/agent/pause", tags=["Agent"])
    def pause_agent():
        """Manually pause the agent."""
        from automation.auto_pause_on_anomaly import _set_paused
        _set_paused("manual", "Paused via API", "low", 0)
        return {"success": True, "status": "paused"}

    @application.post("/api/v1/agent/resume", tags=["Agent"])
    def resume_agent_endpoint():
        """Force-resume the agent."""
        resume = _safe_import("automation.auto_pause_on_anomaly", "force_resume")
        if resume:
            resume("api_user")
        return {"success": True, "status": "running"}

    @application.post("/api/v1/agent/tune", tags=["Agent"])
    def run_tune_cycle():
        """Trigger self-improvement tune cycle."""
        tune = _safe_import("ai.self_improving_agent", "run_auto_tune_cycle")
        if not tune:
            raise HTTPException(status_code=503, detail="Self-improve module unavailable")
        result = tune(verbose=False)
        return result

    # ── WebSocket live log ────────────────────────────────────────────────────

    @application.websocket("/ws/live")
    async def websocket_live(websocket: WebSocket):
        """
        Real-time agent log stream.
        Connect with: ws://localhost:8000/ws/live
        Broadcasts JSON events as the agent runs.
        """
        await manager.connect(websocket)
        try:
            await websocket.send_json({
                "type":      "connected",
                "message":   "Connected to Birthday Wishes Agent live log",
                "timestamp": datetime.now().isoformat(),
            })
            while True:
                # Keep alive — real events are pushed via manager.broadcast()
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping",
                                           "timestamp": datetime.now().isoformat()})
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return application


# ── Module-level app instance ─────────────────────────────────────────────────
if HAS_FASTAPI:
    app = create_app()
else:
    app = None  # type: ignore


# ── CLI runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== FastAPI Backend -- self test ===\n")
    print("Checking dependencies:")
    print(f"  FastAPI  : {'installed' if HAS_FASTAPI else 'NOT installed -- pip install fastapi uvicorn'}")

    import importlib
    for mod in ["ai.self_improving_agent", "ai.multi_model_consensus",
                "contacts.vip_contact_flagging", "dashboards.revenue_attribution",
                "dashboards.network_health_score",
                "automation.auto_pause_on_anomaly"]:
        try:
            importlib.import_module(mod)
            print(f"  {mod:<40} OK")
        except ImportError:
            print(f"  {mod:<40} not found (will use stub)")

    if HAS_FASTAPI:
        print("\nAvailable endpoints:")
        for route in app.routes:
            if hasattr(route, "methods"):
                methods = ",".join(sorted(route.methods - {"HEAD","OPTIONS"}))
                print(f"  [{methods:<6}] {route.path}")
        print("\nStart server:")
        print("  uvicorn fastapi_backend:app --reload --port 8000")
        print("  Docs: http://localhost:8000/docs")
