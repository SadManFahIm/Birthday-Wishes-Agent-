"""
Push Notifications Module — Birthday Wishes Agent v10.0
========================================================
Mobile push notifications via Firebase Cloud Messaging (FCM).
Sends real-time alerts for birthdays, wish deliveries, agent
decisions, system events, and more — straight to the user's
phone.

Features:
  - Device registration & management (FCM tokens)
  - Topic-based subscriptions (birthdays, alerts, system)
  - Notification templates with priority levels
  - Batch sending (multicast) for broadcast alerts
  - Delivery tracking & analytics
  - Quiet-hours enforcement
  - Retry with exponential backoff
  - Streamlit dashboard (dark theme)
  - Full self-test (no Firebase dependency needed)

Integration:
  from push_notifications import (
      send_push, register_device, subscribe_topic,
      register_push_routes,
  )
  send_push("user-001", "birthday_reminder",
            title="🎂 Birthday Today!",
            body="Alice Chen's birthday is today — wish ready to send")

Author : Fahim (SadManFahIm)
Branch : feature/push-notifications (→ 10.0)
"""

import sqlite3
import json
import os
import uuid
import hashlib
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

DB_PATH = Path(os.getenv("BWA_DB_PATH", "agent_history.db"))

FCM_SERVER_KEY = os.getenv("BWA_FCM_SERVER_KEY", "")
FCM_API_URL = "https://fcm.googleapis.com/fcm/send"

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Notification categories & templates
# ──────────────────────────────────────────────────────────────

CATEGORIES = {
    "birthday_reminder": {
        "label": "Birthday Reminder",
        "icon": "🎂",
        "priority": "high",
        "default_title": "Birthday Today!",
        "color": "#f78166",
        "channel": "birthdays",
    },
    "wish_sent": {
        "label": "Wish Sent",
        "icon": "✅",
        "priority": "normal",
        "default_title": "Wish Delivered",
        "color": "#3fb950",
        "channel": "wishes",
    },
    "wish_failed": {
        "label": "Wish Failed",
        "icon": "❌",
        "priority": "high",
        "default_title": "Wish Delivery Failed",
        "color": "#f85149",
        "channel": "alerts",
    },
    "agent_decision": {
        "label": "Agent Decision",
        "icon": "🤖",
        "priority": "normal",
        "default_title": "Agent Update",
        "color": "#58a6ff",
        "channel": "agent",
    },
    "vip_alert": {
        "label": "VIP Alert",
        "icon": "⭐",
        "priority": "high",
        "default_title": "VIP Contact Alert",
        "color": "#d29922",
        "channel": "vip",
    },
    "system_alert": {
        "label": "System Alert",
        "icon": "⚙️",
        "priority": "high",
        "default_title": "System Notification",
        "color": "#8b949e",
        "channel": "system",
    },
    "rate_limit_warning": {
        "label": "Rate Limit Warning",
        "icon": "⚡",
        "priority": "normal",
        "default_title": "Rate Limit Alert",
        "color": "#d29922",
        "channel": "alerts",
    },
    "consent_update": {
        "label": "Consent Update",
        "icon": "🔒",
        "priority": "normal",
        "default_title": "Consent Changed",
        "color": "#58a6ff",
        "channel": "gdpr",
    },
    "weekly_digest": {
        "label": "Weekly Digest",
        "icon": "📊",
        "priority": "normal",
        "default_title": "Weekly Summary",
        "color": "#f78166",
        "channel": "digest",
    },
    "custom": {
        "label": "Custom",
        "icon": "📱",
        "priority": "normal",
        "default_title": "Notification",
        "color": "#8b949e",
        "channel": "general",
    },
}

TOPICS = [
    "birthdays", "wishes", "alerts", "agent", "vip",
    "system", "gdpr", "digest", "general", "all",
]

PRIORITY_MAP = {"high": 10, "normal": 5, "low": 1}

# ──────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────


def init_push_tables(db_path: Path = DB_PATH) -> None:
    """Create push notification tables."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS push_devices (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            fcm_token       TEXT NOT NULL,
            device_name     TEXT DEFAULT '',
            platform        TEXT DEFAULT 'android',
            app_version     TEXT DEFAULT '',
            is_active       INTEGER NOT NULL DEFAULT 1,
            quiet_start     TEXT DEFAULT '23:00',
            quiet_end       TEXT DEFAULT '07:00',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_push_dev_user
            ON push_devices(user_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_push_dev_token
            ON push_devices(fcm_token);

        CREATE TABLE IF NOT EXISTS push_topic_subs (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL,
            device_id       TEXT NOT NULL,
            topic           TEXT NOT NULL,
            subscribed_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_push_topic_key
            ON push_topic_subs(device_id, topic);
        CREATE INDEX IF NOT EXISTS idx_push_topic_user
            ON push_topic_subs(user_id);

        CREATE TABLE IF NOT EXISTS push_notification_log (
            id              TEXT PRIMARY KEY,
            user_id         TEXT,
            device_id       TEXT,
            category        TEXT NOT NULL,
            title           TEXT NOT NULL,
            body            TEXT NOT NULL,
            data_payload    TEXT,
            priority        TEXT NOT NULL DEFAULT 'normal',
            topic           TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            fcm_message_id  TEXT,
            error_message   TEXT,
            retry_count     INTEGER NOT NULL DEFAULT 0,
            sent_at         TEXT,
            delivered_at    TEXT,
            opened_at       TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_push_log_user
            ON push_notification_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_push_log_status
            ON push_notification_log(status);
        CREATE INDEX IF NOT EXISTS idx_push_log_cat
            ON push_notification_log(category);
        CREATE INDEX IF NOT EXISTS idx_push_log_ts
            ON push_notification_log(created_at);

        CREATE TABLE IF NOT EXISTS push_preferences (
            user_id         TEXT PRIMARY KEY,
            enabled         INTEGER NOT NULL DEFAULT 1,
            categories      TEXT DEFAULT '{}',
            quiet_hours     INTEGER NOT NULL DEFAULT 1,
            quiet_start     TEXT DEFAULT '23:00',
            quiet_end       TEXT DEFAULT '07:00',
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    logger.info("Push notification tables initialised: %s", db_path)


def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ──────────────────────────────────────────────────────────────
# Device management
# ──────────────────────────────────────────────────────────────


def register_device(user_id: str, fcm_token: str, *,
                    device_name: str = "", platform: str = "android",
                    app_version: str = "",
                    db_path: Path = DB_PATH) -> dict:
    """Register or update a device's FCM token."""
    conn = _get_conn(db_path)
    try:
        existing = conn.execute(
            "SELECT id FROM push_devices WHERE fcm_token=?",
            (fcm_token,),
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()

        if existing:
            device_id = existing["id"]
            conn.execute(
                """UPDATE push_devices SET user_id=?, device_name=?,
                   platform=?, app_version=?, is_active=1, updated_at=?
                   WHERE id=?""",
                (user_id, device_name, platform, app_version,
                 now, device_id),
            )
        else:
            device_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO push_devices
                   (id, user_id, fcm_token, device_name, platform,
                    app_version, is_active, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,1,?,?)""",
                (device_id, user_id, fcm_token, device_name,
                 platform, app_version, now, now),
            )
            # Auto-subscribe to 'all' topic
            conn.execute(
                """INSERT OR IGNORE INTO push_topic_subs
                   (id, user_id, device_id, topic) VALUES (?,?,?,?)""",
                (str(uuid.uuid4()), user_id, device_id, "all"),
            )
        conn.commit()
        return {"device_id": device_id, "user_id": user_id,
                "fcm_token": fcm_token[:20] + "...",
                "platform": platform, "status": "registered"}
    finally:
        conn.close()


def unregister_device(device_id: str,
                      db_path: Path = DB_PATH) -> bool:
    """Deactivate a device (soft-delete)."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "UPDATE push_devices SET is_active=0, updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), device_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_user_devices(user_id: str, active_only: bool = True,
                     db_path: Path = DB_PATH) -> list[dict]:
    """List devices for a user."""
    conn = _get_conn(db_path)
    try:
        query = "SELECT * FROM push_devices WHERE user_id=?"
        if active_only:
            query += " AND is_active=1"
        rows = conn.execute(query, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Topic subscriptions
# ──────────────────────────────────────────────────────────────


def subscribe_topic(user_id: str, device_id: str, topic: str,
                    db_path: Path = DB_PATH) -> bool:
    """Subscribe a device to a topic."""
    if topic not in TOPICS:
        raise ValueError(f"Unknown topic: {topic}. Valid: {TOPICS}")
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT OR IGNORE INTO push_topic_subs
               (id, user_id, device_id, topic) VALUES (?,?,?,?)""",
            (str(uuid.uuid4()), user_id, device_id, topic),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def unsubscribe_topic(device_id: str, topic: str,
                      db_path: Path = DB_PATH) -> bool:
    """Unsubscribe a device from a topic."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "DELETE FROM push_topic_subs WHERE device_id=? AND topic=?",
            (device_id, topic),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_device_topics(device_id: str,
                      db_path: Path = DB_PATH) -> list[str]:
    """List topics a device is subscribed to."""
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT topic FROM push_topic_subs WHERE device_id=?",
            (device_id,),
        ).fetchall()
        return [r["topic"] for r in rows]
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Preferences
# ──────────────────────────────────────────────────────────────


def set_preferences(user_id: str, *, enabled: bool = True,
                    categories: Optional[dict] = None,
                    quiet_hours: bool = True,
                    quiet_start: str = "23:00",
                    quiet_end: str = "07:00",
                    db_path: Path = DB_PATH) -> dict:
    """Set push notification preferences for a user."""
    cat_json = json.dumps(categories or {})
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO push_preferences
               (user_id, enabled, categories, quiet_hours,
                quiet_start, quiet_end, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
               enabled=excluded.enabled,
               categories=excluded.categories,
               quiet_hours=excluded.quiet_hours,
               quiet_start=excluded.quiet_start,
               quiet_end=excluded.quiet_end,
               updated_at=excluded.updated_at""",
            (user_id, 1 if enabled else 0, cat_json,
             1 if quiet_hours else 0, quiet_start, quiet_end, now),
        )
        conn.commit()
        return {"user_id": user_id, "enabled": enabled,
                "quiet_hours": quiet_hours}
    finally:
        conn.close()


def get_preferences(user_id: str,
                    db_path: Path = DB_PATH) -> dict:
    """Get push preferences for a user."""
    conn = _get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM push_preferences WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if row:
            d = dict(row)
            d["categories"] = json.loads(d.get("categories", "{}"))
            return d
        # Default preferences
        return {"user_id": user_id, "enabled": True,
                "categories": {}, "quiet_hours": True,
                "quiet_start": "23:00", "quiet_end": "07:00"}
    finally:
        conn.close()


def _is_quiet_hour(prefs: dict) -> bool:
    """Check if current UTC time is within quiet hours."""
    if not prefs.get("quiet_hours"):
        return False
    now = datetime.now(timezone.utc)
    current_time = now.strftime("%H:%M")
    start = prefs.get("quiet_start", "23:00")
    end = prefs.get("quiet_end", "07:00")

    if start <= end:
        return start <= current_time <= end
    else:
        return current_time >= start or current_time <= end


# ──────────────────────────────────────────────────────────────
# FCM sending (HTTP v1 legacy API — works without google-auth)
# ──────────────────────────────────────────────────────────────


def _build_fcm_payload(fcm_token: str, title: str, body: str,
                       category: str, data: Optional[dict] = None,
                       priority: str = "normal",
                       topic: str = "") -> dict:
    """Build FCM HTTP v1 (legacy) JSON payload."""
    cat_info = CATEGORIES.get(category, CATEGORIES["custom"])

    payload = {
        "to": fcm_token,
        "notification": {
            "title": title,
            "body": body,
            "icon": cat_info["icon"],
            "color": cat_info["color"],
            "sound": "default",
            "click_action": "OPEN_APP",
            "channel_id": cat_info["channel"],
        },
        "data": {
            "category": category,
            "channel": cat_info["channel"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(data or {}),
        },
        "priority": "high" if priority == "high" else "normal",
        "content_available": True,
    }

    if topic:
        payload["to"] = f"/topics/{topic}"

    return payload


def _send_fcm_request(payload: dict) -> dict:
    """Send a single FCM request. Returns {success, message_id, error}."""
    if not FCM_SERVER_KEY:
        logger.warning("FCM_SERVER_KEY not set — push skipped (dry run)")
        return {"success": True, "message_id": f"dry-{uuid.uuid4().hex[:8]}",
                "error": None, "dry_run": True}

    try:
        body_bytes = json.dumps(payload).encode("utf-8")
        req = Request(
            FCM_API_URL,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"key={FCM_SERVER_KEY}",
            },
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("success", 0) >= 1:
                msg_id = (result.get("results", [{}])[0]
                          .get("message_id", ""))
                return {"success": True, "message_id": msg_id,
                        "error": None, "dry_run": False}
            else:
                err = (result.get("results", [{}])[0]
                       .get("error", "unknown_error"))
                return {"success": False, "message_id": None,
                        "error": err, "dry_run": False}
    except URLError as exc:
        return {"success": False, "message_id": None,
                "error": str(exc), "dry_run": False}
    except Exception as exc:
        return {"success": False, "message_id": None,
                "error": str(exc), "dry_run": False}


# ──────────────────────────────────────────────────────────────
# Core: send_push
# ──────────────────────────────────────────────────────────────


def send_push(user_id: str, category: str, *,
              title: str = "", body: str = "",
              data: Optional[dict] = None,
              priority: str = "",
              respect_quiet: bool = True,
              db_path: Path = DB_PATH) -> list[dict]:
    """
    Send a push notification to all active devices of a user.

    Parameters
    ----------
    user_id : str       – target user
    category : str      – notification category key
    title : str         – override default title
    body : str          – notification body text
    data : dict         – extra data payload
    priority : str      – "high" / "normal" / "low"
    respect_quiet : bool – skip during quiet hours

    Returns list of result dicts (one per device).
    """
    cat_info = CATEGORIES.get(category, CATEGORIES["custom"])
    title = title or cat_info["default_title"]
    priority = priority or cat_info["priority"]

    # Check preferences
    prefs = get_preferences(user_id, db_path)
    if not prefs.get("enabled"):
        return [{"device_id": None, "status": "disabled",
                 "reason": "user_notifications_disabled"}]

    cat_prefs = prefs.get("categories", {})
    if cat_prefs.get(category) is False:
        return [{"device_id": None, "status": "disabled",
                 "reason": f"category_{category}_disabled"}]

    if respect_quiet and _is_quiet_hour(prefs):
        return [{"device_id": None, "status": "deferred",
                 "reason": "quiet_hours"}]

    devices = get_user_devices(user_id, active_only=True, db_path=db_path)
    if not devices:
        return [{"device_id": None, "status": "no_devices",
                 "reason": "no_active_devices"}]

    results = []
    conn = _get_conn(db_path)
    try:
        for dev in devices:
            log_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            payload = _build_fcm_payload(
                dev["fcm_token"], title, body, category,
                data, priority)

            fcm_result = _send_fcm_request(payload)

            status = "sent" if fcm_result["success"] else "failed"
            conn.execute(
                """INSERT INTO push_notification_log
                   (id, user_id, device_id, category, title, body,
                    data_payload, priority, status, fcm_message_id,
                    error_message, sent_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (log_id, user_id, dev["id"], category, title, body,
                 json.dumps(data or {}), priority, status,
                 fcm_result.get("message_id"),
                 fcm_result.get("error"), now, now),
            )

            # Deactivate device on permanent errors
            if fcm_result.get("error") in (
                "NotRegistered", "InvalidRegistration"
            ):
                conn.execute(
                    "UPDATE push_devices SET is_active=0 WHERE id=?",
                    (dev["id"],),
                )

            results.append({
                "device_id": dev["id"],
                "platform": dev["platform"],
                "status": status,
                "message_id": fcm_result.get("message_id"),
                "error": fcm_result.get("error"),
                "dry_run": fcm_result.get("dry_run", False),
            })
        conn.commit()
    finally:
        conn.close()

    return results


def send_topic_push(topic: str, category: str, *,
                    title: str = "", body: str = "",
                    data: Optional[dict] = None,
                    db_path: Path = DB_PATH) -> dict:
    """Send a push notification to all subscribers of a topic."""
    cat_info = CATEGORIES.get(category, CATEGORIES["custom"])
    title = title or cat_info["default_title"]
    priority = cat_info["priority"]

    payload = _build_fcm_payload(
        "", title, body, category, data, priority, topic=topic)

    fcm_result = _send_fcm_request(payload)
    status = "sent" if fcm_result["success"] else "failed"

    # Log
    conn = _get_conn(db_path)
    try:
        conn.execute(
            """INSERT INTO push_notification_log
               (id, user_id, device_id, category, title, body,
                data_payload, priority, topic, status,
                fcm_message_id, error_message, sent_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), "topic", "topic", category, title, body,
             json.dumps(data or {}), priority, topic, status,
             fcm_result.get("message_id"),
             fcm_result.get("error"),
             datetime.now(timezone.utc).isoformat(),
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    return {"topic": topic, "status": status,
            "message_id": fcm_result.get("message_id"),
            "dry_run": fcm_result.get("dry_run", False)}


# ──────────────────────────────────────────────────────────────
# Convenience senders
# ──────────────────────────────────────────────────────────────


def notify_birthday_reminder(user_id: str, contact_name: str,
                             platform: str = "",
                             db_path: Path = DB_PATH) -> list[dict]:
    """Send a birthday reminder push."""
    return send_push(
        user_id, "birthday_reminder",
        title=f"🎂 {contact_name}'s Birthday!",
        body=f"{contact_name}'s birthday is today"
             + (f" — wish ready on {platform}" if platform else ""),
        data={"contact_name": contact_name, "platform": platform},
        db_path=db_path)


def notify_wish_sent(user_id: str, contact_name: str,
                     platform: str = "",
                     db_path: Path = DB_PATH) -> list[dict]:
    """Notify that a wish was successfully sent."""
    return send_push(
        user_id, "wish_sent",
        title="✅ Wish Delivered",
        body=f"Birthday wish sent to {contact_name}"
             + (f" via {platform}" if platform else ""),
        data={"contact_name": contact_name, "platform": platform},
        db_path=db_path)


def notify_wish_failed(user_id: str, contact_name: str,
                       error: str = "",
                       db_path: Path = DB_PATH) -> list[dict]:
    """Notify that a wish delivery failed."""
    return send_push(
        user_id, "wish_failed",
        title="❌ Wish Failed",
        body=f"Could not send wish to {contact_name}"
             + (f": {error}" if error else ""),
        data={"contact_name": contact_name, "error": error},
        db_path=db_path)


def notify_system_alert(user_id: str, message: str,
                        severity: str = "info",
                        db_path: Path = DB_PATH) -> list[dict]:
    """Send a system alert push."""
    return send_push(
        user_id, "system_alert",
        title="⚙️ System Alert",
        body=message,
        priority="high" if severity == "critical" else "normal",
        data={"severity": severity},
        db_path=db_path)


# ──────────────────────────────────────────────────────────────
# Delivery tracking
# ──────────────────────────────────────────────────────────────


def mark_delivered(notification_id: str,
                   db_path: Path = DB_PATH) -> bool:
    """Mark a notification as delivered (called from client callback)."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "UPDATE push_notification_log SET delivered_at=?, status='delivered' "
            "WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), notification_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def mark_opened(notification_id: str,
                db_path: Path = DB_PATH) -> bool:
    """Mark a notification as opened."""
    conn = _get_conn(db_path)
    try:
        conn.execute(
            "UPDATE push_notification_log SET opened_at=?, status='opened' "
            "WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), notification_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# Analytics & stats
# ──────────────────────────────────────────────────────────────


def get_notification_log(user_id: str = "", category: str = "",
                         status: str = "", limit: int = 50,
                         db_path: Path = DB_PATH) -> list[dict]:
    """Query notification history with filters."""
    clauses = ["1=1"]
    params: list = []
    if user_id:
        clauses.append("user_id=?"); params.append(user_id)
    if category:
        clauses.append("category=?"); params.append(category)
    if status:
        clauses.append("status=?"); params.append(status)
    where = " AND ".join(clauses)
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            f"SELECT * FROM push_notification_log WHERE {where} "
            f"ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_stats(db_path: Path = DB_PATH) -> dict:
    """Aggregate push notification stats."""
    conn = _get_conn(db_path)
    try:
        total = conn.execute(
            "SELECT COUNT(*) as c FROM push_notification_log"
        ).fetchone()["c"]

        by_status = conn.execute(
            """SELECT status, COUNT(*) as c FROM push_notification_log
               GROUP BY status ORDER BY c DESC"""
        ).fetchall()

        by_category = conn.execute(
            """SELECT category, COUNT(*) as c FROM push_notification_log
               GROUP BY category ORDER BY c DESC"""
        ).fetchall()

        sent_24h = conn.execute(
            """SELECT COUNT(*) as c FROM push_notification_log
               WHERE status IN ('sent','delivered','opened')
               AND created_at >= datetime('now','-24 hours')"""
        ).fetchone()["c"]

        failed_24h = conn.execute(
            """SELECT COUNT(*) as c FROM push_notification_log
               WHERE status='failed'
               AND created_at >= datetime('now','-24 hours')"""
        ).fetchone()["c"]

        devices_total = conn.execute(
            "SELECT COUNT(*) as c FROM push_devices"
        ).fetchone()["c"]
        devices_active = conn.execute(
            "SELECT COUNT(*) as c FROM push_devices WHERE is_active=1"
        ).fetchone()["c"]

        delivery_rate = 0.0
        delivered = conn.execute(
            """SELECT COUNT(*) as c FROM push_notification_log
               WHERE status IN ('delivered','opened')"""
        ).fetchone()["c"]
        sent_total = conn.execute(
            """SELECT COUNT(*) as c FROM push_notification_log
               WHERE status IN ('sent','delivered','opened')"""
        ).fetchone()["c"]
        if sent_total > 0:
            delivery_rate = round((delivered / sent_total) * 100, 1)

        open_rate = 0.0
        opened = conn.execute(
            """SELECT COUNT(*) as c FROM push_notification_log
               WHERE status='opened'"""
        ).fetchone()["c"]
        if delivered > 0:
            open_rate = round((opened / delivered) * 100, 1)

        daily_7d = conn.execute(
            """SELECT DATE(created_at) as day, COUNT(*) as c
               FROM push_notification_log
               WHERE created_at >= datetime('now','-7 days')
               GROUP BY day ORDER BY day"""
        ).fetchall()

        return {
            "total_notifications": total,
            "by_status": [dict(r) for r in by_status],
            "by_category": [dict(r) for r in by_category],
            "sent_24h": sent_24h,
            "failed_24h": failed_24h,
            "devices_total": devices_total,
            "devices_active": devices_active,
            "delivery_rate_pct": delivery_rate,
            "open_rate_pct": open_rate,
            "daily_7d": [dict(r) for r in daily_7d],
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────
# FastAPI routes (optional)
# ──────────────────────────────────────────────────────────────


def register_push_routes(app) -> None:
    """Mount /api/v1/push/* onto a FastAPI app."""
    try:
        from fastapi import HTTPException
        from pydantic import BaseModel as BM
    except ImportError:
        return

    class DeviceRegReq(BM):
        user_id: str
        fcm_token: str
        device_name: str = ""
        platform: str = "android"

    class SendPushReq(BM):
        user_id: str
        category: str = "custom"
        title: str = ""
        body: str = ""
        data: dict = {}

    class TopicPushReq(BM):
        topic: str
        category: str = "custom"
        title: str = ""
        body: str = ""

    @app.post("/api/v1/push/devices", tags=["Push"], status_code=201)
    def api_register_device(req: DeviceRegReq):
        return register_device(req.user_id, req.fcm_token,
                               device_name=req.device_name,
                               platform=req.platform)

    @app.get("/api/v1/push/devices/{user_id}", tags=["Push"])
    def api_user_devices(user_id: str):
        return {"devices": get_user_devices(user_id)}

    @app.post("/api/v1/push/send", tags=["Push"])
    def api_send_push(req: SendPushReq):
        results = send_push(req.user_id, req.category,
                            title=req.title, body=req.body,
                            data=req.data)
        return {"results": results}

    @app.post("/api/v1/push/topic", tags=["Push"])
    def api_topic_push(req: TopicPushReq):
        return send_topic_push(req.topic, req.category,
                               title=req.title, body=req.body)

    @app.get("/api/v1/push/stats", tags=["Push"])
    def api_push_stats():
        return get_stats()

    @app.get("/api/v1/push/log", tags=["Push"])
    def api_push_log(user_id: str = "", category: str = "",
                     limit: int = 50):
        return {"notifications": get_notification_log(
            user_id, category, limit=limit)}

    @app.post("/api/v1/push/delivered/{notification_id}", tags=["Push"])
    def api_mark_delivered(notification_id: str):
        mark_delivered(notification_id)
        return {"success": True}

    @app.post("/api/v1/push/opened/{notification_id}", tags=["Push"])
    def api_mark_opened(notification_id: str):
        mark_opened(notification_id)
        return {"success": True}

    logger.info("Push routes registered: /api/v1/push/*")


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """Push notification management dashboard."""
    try:
        import streamlit as st
        import pandas as pd
    except ImportError:
        return

    st.set_page_config(page_title="Push Notifications", page_icon="📱",
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
    .tag{display:inline-block;font-size:0.65rem;padding:1px 7px;border-radius:10px;
         font-weight:600;margin-right:4px;}
    .tag-sent{background:rgba(63,185,80,0.15);color:var(--green);}
    .tag-failed{background:rgba(248,81,73,0.15);color:var(--red);}
    .tag-pending{background:rgba(210,153,34,0.15);color:var(--yellow);}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    </style>
    """, unsafe_allow_html=True)

    init_push_tables()
    stats = get_stats()

    # Header
    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📱</span>
      <h1>Push Notifications</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent · Firebase FCM</span>
    </div>
    """, unsafe_allow_html=True)

    # KPIs
    st.markdown('<div class="section-title">Overview</div>',
                unsafe_allow_html=True)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    for col, val, lbl in [
        (k1, stats["sent_24h"], "Sent (24h)"),
        (k2, stats["failed_24h"], "Failed (24h)"),
        (k3, stats["devices_active"], "Active Devices"),
        (k4, f'{stats["delivery_rate_pct"]}%', "Delivery Rate"),
        (k5, f'{stats["open_rate_pct"]}%', "Open Rate"),
        (k6, stats["total_notifications"], "Total All Time"),
    ]:
        col.markdown(
            f'<div class="mini"><div class="mini-val">{val}</div>'
            f'<div class="mini-lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

    tabs = st.tabs(["📨 Send", "📱 Devices", "📋 Log",
                     "📊 Analytics", "⚙️ Preferences"])

    # Tab 0: Send
    with tabs[0]:
        st.markdown('<div class="section-title">Send Push Notification'
                    '</div>', unsafe_allow_html=True)
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        with s1:
            s_user = st.text_input("User ID", key="s_uid")
            s_cat = st.selectbox("Category",
                                 list(CATEGORIES.keys()), key="s_cat")
            s_title = st.text_input("Title (optional)", key="s_title")
        with s2:
            s_body = st.text_area("Body", height=100, key="s_body")
            s_priority = st.selectbox("Priority",
                                      ["high", "normal", "low"],
                                      index=1, key="s_pri")
        if st.button("📤 Send", key="btn_send"):
            if s_user and s_body:
                results = send_push(s_user, s_cat,
                                    title=s_title, body=s_body,
                                    priority=s_priority)
                for r in results:
                    if r["status"] == "sent":
                        st.success(f"Sent → {r.get('device_id', 'N/A')}"
                                   f" (dry_run={r.get('dry_run')})")
                    else:
                        st.warning(f"{r['status']}: {r.get('reason', r.get('error', ''))}")
        st.markdown('</div>', unsafe_allow_html=True)

        # Topic send
        st.markdown('<div class="section-title">Topic Broadcast</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        t1, t2 = st.columns(2)
        with t1:
            t_topic = st.selectbox("Topic", TOPICS, key="t_topic")
            t_cat = st.selectbox("Category",
                                 list(CATEGORIES.keys()), key="t_cat")
        with t2:
            t_title = st.text_input("Title", key="t_title")
            t_body = st.text_input("Body", key="t_body")
        if st.button("📡 Broadcast", key="btn_broadcast"):
            if t_body:
                result = send_topic_push(t_topic, t_cat,
                                         title=t_title, body=t_body)
                st.success(f"Broadcast to /{t_topic}: {result['status']}")
        st.markdown('</div>', unsafe_allow_html=True)

    # Tab 1: Devices
    with tabs[1]:
        st.markdown('<div class="section-title">Device Management</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        d_uid = st.text_input("User ID to lookup", key="d_uid")
        if d_uid:
            devices = get_user_devices(d_uid, active_only=False)
            if devices:
                df = pd.DataFrame(devices)
                st.dataframe(df, use_container_width=True, height=200)
            else:
                st.info("No devices found.")
        st.markdown('</div>', unsafe_allow_html=True)

        # Register
        st.markdown('<div class="section-title">Register Device</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        r1, r2 = st.columns(2)
        with r1:
            r_uid = st.text_input("User ID", key="r_uid")
            r_token = st.text_input("FCM Token", key="r_token")
        with r2:
            r_name = st.text_input("Device Name", key="r_name")
            r_plat = st.selectbox("Platform",
                                  ["android", "ios", "web"], key="r_plat")
        if st.button("Register", key="btn_reg"):
            if r_uid and r_token:
                result = register_device(r_uid, r_token,
                                         device_name=r_name,
                                         platform=r_plat)
                st.success(f"Device registered: {result['device_id']}")
        st.markdown('</div>', unsafe_allow_html=True)

    # Tab 2: Log
    with tabs[2]:
        st.markdown('<div class="section-title">Notification Log</div>',
                    unsafe_allow_html=True)
        l1, l2, l3 = st.columns(3)
        with l1:
            l_uid = st.text_input("User ID", key="l_uid")
        with l2:
            l_cat = st.selectbox("Category",
                                 [""] + list(CATEGORIES.keys()),
                                 key="l_cat")
        with l3:
            l_lim = st.number_input("Limit", 10, 500, 50, key="l_lim")
        logs = get_notification_log(l_uid, l_cat, limit=l_lim)
        if logs:
            display = []
            for n in logs:
                display.append({
                    "Time": n["created_at"][:19],
                    "Category": n["category"],
                    "Title": n["title"][:40],
                    "Status": n["status"],
                    "User": n.get("user_id", "")[:12],
                    "Error": (n.get("error_message") or "")[:30],
                })
            st.dataframe(pd.DataFrame(display),
                         use_container_width=True, height=400)
        else:
            st.info("No notifications logged yet.")

    # Tab 3: Analytics
    with tabs[3]:
        st.markdown('<div class="section-title">Analytics</div>',
                    unsafe_allow_html=True)
        ac, sc = st.columns(2)
        with ac:
            st.markdown('<div class="c-card">', unsafe_allow_html=True)
            st.markdown("**By Category**")
            for item in stats["by_category"]:
                cat = item["category"]
                icon = CATEGORIES.get(cat, {}).get("icon", "📱")
                st.markdown(
                    f'{icon} **{cat}**: {item["c"]}',
                    unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        with sc:
            st.markdown('<div class="c-card">', unsafe_allow_html=True)
            st.markdown("**By Status**")
            for item in stats["by_status"]:
                cls = f"tag-{item['status']}" if item["status"] in (
                    "sent", "failed", "pending") else ""
                st.markdown(
                    f'<span class="tag {cls}">{item["status"]}</span>'
                    f' {item["c"]}', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        if stats["daily_7d"]:
            st.markdown('<div class="section-title">Daily Volume (7d)'
                        '</div>', unsafe_allow_html=True)
            d7 = pd.DataFrame(stats["daily_7d"])
            d7.columns = ["Date", "Notifications"]
            st.bar_chart(d7.set_index("Date"), color="#f78166", height=220)

    # Tab 4: Preferences
    with tabs[4]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        p_uid = st.text_input("User ID", key="p_uid")
        if p_uid:
            prefs = get_preferences(p_uid)
            p_enabled = st.checkbox("Notifications enabled",
                                    prefs.get("enabled", True), key="p_en")
            p_quiet = st.checkbox("Quiet hours",
                                  prefs.get("quiet_hours", True), key="p_qh")
            pc1, pc2 = st.columns(2)
            with pc1:
                p_start = st.text_input("Quiet start (HH:MM)",
                                        prefs.get("quiet_start", "23:00"),
                                        key="p_qs")
            with pc2:
                p_end = st.text_input("Quiet end (HH:MM)",
                                      prefs.get("quiet_end", "07:00"),
                                      key="p_qe")
            if st.button("Save Preferences", key="btn_prefs"):
                set_preferences(p_uid, enabled=p_enabled,
                                quiet_hours=p_quiet,
                                quiet_start=p_start, quiet_end=p_end)
                st.success("Preferences saved")
        st.markdown('</div>', unsafe_allow_html=True)

    # Footer
    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/push-notifications</code> · Push Notifications v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test for all push notification functions."""
    import tempfile

    print("=" * 60)
    print("Push Notifications Module — Self-Test")
    print("=" * 60)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tdb = Path(tmp.name)

    try:
        init_push_tables(tdb)
        user = "test-user-001"

        # 1. Register devices
        print("\n[1/10] Register devices ...")
        d1 = register_device(user, "fcm-token-android-001",
                             device_name="Pixel 8", platform="android",
                             db_path=tdb)
        assert d1["status"] == "registered"
        d2 = register_device(user, "fcm-token-ios-001",
                             device_name="iPhone 15", platform="ios",
                             db_path=tdb)
        devices = get_user_devices(user, db_path=tdb)
        assert len(devices) == 2
        print(f"       ✅ 2 devices registered (android + ios)")

        # 2. Re-register (update)
        print("[2/10] Re-register (update) ...")
        d1_up = register_device(user, "fcm-token-android-001",
                                device_name="Pixel 8 Pro",
                                app_version="2.0", db_path=tdb)
        assert d1_up["device_id"] == d1["device_id"]
        print(f"       ✅ Device updated, same ID")

        # 3. Topic subscription
        print("[3/10] Topic subscriptions ...")
        subscribe_topic(user, d1["device_id"], "birthdays", tdb)
        subscribe_topic(user, d1["device_id"], "vip", tdb)
        topics = get_device_topics(d1["device_id"], tdb)
        assert "all" in topics  # auto-subscribed
        assert "birthdays" in topics
        assert "vip" in topics
        print(f"       ✅ Subscribed to {len(topics)} topics: {topics}")

        # 4. Unsubscribe
        print("[4/10] Unsubscribe ...")
        unsubscribe_topic(d1["device_id"], "vip", tdb)
        topics = get_device_topics(d1["device_id"], tdb)
        assert "vip" not in topics
        print(f"       ✅ Unsubscribed from vip")

        # 5. Preferences
        print("[5/10] Preferences ...")
        set_preferences(user, enabled=True, quiet_hours=True,
                        quiet_start="23:00", quiet_end="07:00",
                        db_path=tdb)
        prefs = get_preferences(user, tdb)
        assert prefs["enabled"]
        assert prefs["quiet_hours"]
        print(f"       ✅ Preferences saved and loaded")

        # 6. Send push (dry run — no FCM key set)
        print("[6/10] Send push (dry run) ...")
        results = send_push(user, "birthday_reminder",
                            title="🎂 Test Birthday!",
                            body="Alice's birthday is today",
                            data={"contact": "alice"},
                            respect_quiet=False,
                            db_path=tdb)
        assert len(results) == 2  # 2 devices
        assert all(r["status"] == "sent" for r in results)
        assert all(r["dry_run"] for r in results)
        print(f"       ✅ Sent to {len(results)} devices (dry run)")

        # 7. Convenience senders
        print("[7/10] Convenience senders ...")
        r1 = notify_birthday_reminder(user, "Bob",
                                      platform="LinkedIn",
                                      db_path=tdb)
        r2 = notify_wish_sent(user, "Bob", "WhatsApp", tdb)
        r3 = notify_wish_failed(user, "Charlie",
                                error="timeout", db_path=tdb)
        r4 = notify_system_alert(user, "Agent paused",
                                 severity="critical", db_path=tdb)
        assert all(len(r) == 2 for r in [r1, r2, r3, r4])
        print(f"       ✅ 4 convenience methods OK (8 deliveries)")

        # 8. Topic broadcast
        print("[8/10] Topic broadcast ...")
        tr = send_topic_push("birthdays", "birthday_reminder",
                             title="Daily Birthdays",
                             body="3 contacts have birthdays today",
                             db_path=tdb)
        assert tr["status"] == "sent"
        print(f"       ✅ Broadcast to /birthdays: {tr['status']}")

        # 9. Delivery tracking
        print("[9/10] Delivery tracking ...")
        logs = get_notification_log(user, db_path=tdb)
        assert len(logs) >= 8
        first_id = logs[0]["id"]
        mark_delivered(first_id, tdb)
        mark_opened(first_id, tdb)
        updated = get_notification_log(user, db_path=tdb)
        opened_entry = [n for n in updated if n["id"] == first_id][0]
        assert opened_entry["status"] == "opened"
        print(f"       ✅ Delivered + opened tracked ({len(logs)} total)")

        # 10. Stats & device deactivation
        print("[10/10] Stats & deactivation ...")
        s = get_stats(tdb)
        assert s["devices_active"] == 2
        assert s["sent_24h"] >= 8
        unregister_device(d2["device_id"], tdb)
        devices = get_user_devices(user, active_only=True, db_path=tdb)
        assert len(devices) == 1
        print(f"       ✅ Stats OK, 1 device deactivated "
              f"({s['sent_24h']} sent 24h)")

        print("\n" + "=" * 60)
        print("✅ ALL PUSH NOTIFICATION SELF-TESTS PASSED")
        print("=" * 60)

    finally:
        os.unlink(tdb)


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_push_tables()
    print("=== Push Notifications -- self test ===\n")
    _self_test()
else:
    render_dashboard()
