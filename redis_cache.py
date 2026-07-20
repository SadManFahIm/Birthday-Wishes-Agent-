"""
Redis Cache & Task Queue -- Birthday Wishes Agent v9.0
Provides caching and background task queuing via Redis.
Falls back to in-memory dict when Redis is not configured.

Features:
  Cache:
    - get / set / delete with TTL
    - Cache decorators for expensive functions
    - Namespaced keys (agent:contacts:, agent:wish:, etc.)

  Task Queue:
    - enqueue(task_name, payload) -- add task to queue
    - dequeue() -- pop next task (for worker)
    - get_queue_length() -- monitor backlog
    - Task result storage with TTL

Requires (optional):
  pip install redis

Integrates with: fastapi_backend.py, ai/self_improving_agent.py,
                 automation/smart_send_time_optimizer.py, agent.py
"""

import json
import os
import time
import hashlib
import functools
from datetime import datetime
from typing import Any, Optional, Callable

REDIS_URL    = os.getenv("REDIS_URL", "")
HAS_REDIS    = False
_redis_client = None

# Cache TTLs (seconds)
TTL = {
    "health":       30,
    "contacts":     120,
    "queue":        10,
    "analytics":    300,
    "vip":          60,
    "revenue":      300,
    "wish_prompt":  3600,
    "platform_roi": 600,
    "score_trend":  600,
    "default":      60,
}

# Queue names
QUEUES = {
    "wishes":     "agent:queue:wishes",
    "followups":  "agent:queue:followups",
    "analytics":  "agent:queue:analytics",
    "alerts":     "agent:queue:alerts",
}

# Key namespaces
NS = {
    "cache":   "agent:cache:",
    "task":    "agent:task:",
    "result":  "agent:result:",
    "session": "agent:session:",
    "rate":    "agent:rate:",
}


# ── Redis client setup ────────────────────────────────────────────────────────

def _get_client():
    global _redis_client, HAS_REDIS
    if _redis_client is not None:
        return _redis_client
    if not REDIS_URL:
        return None
    try:
        import redis
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        HAS_REDIS = True
        print(f"[Redis] Connected to {REDIS_URL}")
        return _redis_client
    except Exception as exc:
        print(f"[Redis] Connection failed ({exc}) — using in-memory fallback")
        return None


# ── In-memory fallback ────────────────────────────────────────────────────────

_mem_store: dict[str, tuple[Any, float]] = {}   # key → (value, expires_at)
_mem_queues: dict[str, list] = {q: [] for q in QUEUES.values()}


def _mem_get(key: str) -> Optional[str]:
    if key not in _mem_store:
        return None
    val, exp = _mem_store[key]
    if exp and time.time() > exp:
        del _mem_store[key]
        return None
    return val


def _mem_set(key: str, val: str, ttl: int = 0):
    exp = time.time() + ttl if ttl else 0
    _mem_store[key] = (val, exp)


def _mem_delete(key: str):
    _mem_store.pop(key, None)


def _mem_enqueue(queue: str, payload: str):
    _mem_queues.setdefault(queue, []).append(payload)


def _mem_dequeue(queue: str) -> Optional[str]:
    q = _mem_queues.get(queue, [])
    return q.pop(0) if q else None


def _mem_qlen(queue: str) -> int:
    return len(_mem_queues.get(queue, []))


# ── Public cache API ──────────────────────────────────────────────────────────

def cache_get(key: str) -> Optional[Any]:
    """
    Get a cached value. Returns deserialized Python object or None.
    key: use namespaced key like 'contacts:list' (NS prefix auto-added)
    """
    full_key = NS["cache"] + key
    r = _get_client()
    raw = r.get(full_key) if r else _mem_get(full_key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw


def cache_set(key: str, value: Any, ttl: int = TTL["default"]) -> bool:
    """
    Store a value in cache with TTL (seconds).
    Value is JSON-serialized automatically.
    """
    full_key = NS["cache"] + key
    try:
        serialized = json.dumps(value, default=str)
    except Exception:
        return False
    r = _get_client()
    if r:
        r.setex(full_key, ttl, serialized)
    else:
        _mem_set(full_key, serialized, ttl)
    return True


def cache_delete(key: str) -> None:
    """Invalidate a cached key."""
    full_key = NS["cache"] + key
    r = _get_client()
    if r:
        r.delete(full_key)
    else:
        _mem_delete(full_key)


def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern (e.g. 'contacts:*')."""
    full_pattern = NS["cache"] + pattern
    r = _get_client()
    if r:
        keys = r.keys(full_pattern)
        if keys:
            return r.delete(*keys)
        return 0
    # In-memory: filter
    to_del = [k for k in _mem_store if k.startswith(NS["cache"] + pattern.rstrip("*"))]
    for k in to_del:
        _mem_delete(k)
    return len(to_del)


def cached(key_template: str, ttl: int = TTL["default"]):
    """
    Decorator that caches function return value.

    Usage:
        @cached("contacts:list:{tier}", ttl=TTL["contacts"])
        def get_contacts(tier: str = "all"):
            ...

    The key_template can reference function arg names with {}.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Build cache key from template + args
            sig  = fn.__code__.co_varnames[:fn.__code__.co_argcount]
            bound = dict(zip(sig, args))
            bound.update(kwargs)
            try:
                key = key_template.format(**bound)
            except KeyError:
                key = key_template + ":" + hashlib.md5(
                    str(args).encode() + str(kwargs).encode()
                ).hexdigest()[:8]

            hit = cache_get(key)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            cache_set(key, result, ttl)
            return result
        return wrapper
    return decorator


# ── Task queue API ────────────────────────────────────────────────────────────

def enqueue(
    queue_name: str,
    task_type:  str,
    payload:    dict,
    priority:   int = 5,
) -> str:
    """
    Add a task to the queue.

    Args:
        queue_name: Key from QUEUES dict (wishes, followups, analytics, alerts)
        task_type:  Human-readable task identifier
        payload:    Task data dict
        priority:   1 (highest) to 10 (lowest) -- stored for worker awareness

    Returns:
        task_id (UUID-like string)
    """
    task_id  = hashlib.md5(
        f"{task_type}{json.dumps(payload, sort_keys=True)}{time.time()}".encode()
    ).hexdigest()[:12]

    task = {
        "task_id":   task_id,
        "task_type": task_type,
        "payload":   payload,
        "priority":  priority,
        "enqueued_at": datetime.now().isoformat(),
        "status":    "queued",
    }
    serialized = json.dumps(task)
    queue_key  = QUEUES.get(queue_name, f"agent:queue:{queue_name}")

    r = _get_client()
    if r:
        r.rpush(queue_key, serialized)
    else:
        _mem_enqueue(queue_key, serialized)

    # Store task record for status lookup
    result_key = NS["result"] + task_id
    r2 = _get_client()
    if r2:
        r2.setex(result_key, 3600, serialized)
    else:
        _mem_set(result_key, serialized, 3600)

    return task_id


def dequeue(queue_name: str, block: bool = False) -> Optional[dict]:
    """
    Pop the next task from a queue.

    Args:
        queue_name: Key from QUEUES dict
        block:      If True, block up to 5s waiting for a task (Redis only)

    Returns:
        Task dict or None if queue is empty
    """
    queue_key = QUEUES.get(queue_name, f"agent:queue:{queue_name}")
    r = _get_client()

    if r:
        if block:
            result = r.blpop(queue_key, timeout=5)
            raw = result[1] if result else None
        else:
            raw = r.lpop(queue_key)
    else:
        raw = _mem_dequeue(queue_key)

    if not raw:
        return None
    try:
        task = json.loads(raw)
        task["status"] = "processing"
        return task
    except Exception:
        return None


def complete_task(task_id: str, result: Any = None, error: str = "") -> None:
    """Mark a task as completed or failed."""
    result_key = NS["result"] + task_id
    r = _get_client()
    raw = r.get(result_key) if r else _mem_get(result_key)
    if not raw:
        return
    try:
        task = json.loads(raw)
    except Exception:
        return
    task["status"]       = "failed" if error else "completed"
    task["completed_at"] = datetime.now().isoformat()
    task["result"]       = result
    task["error"]        = error
    serialized = json.dumps(task, default=str)
    if r:
        r.setex(result_key, 3600, serialized)
    else:
        _mem_set(result_key, serialized, 3600)


def get_task_status(task_id: str) -> Optional[dict]:
    """Look up status of a previously enqueued task."""
    result_key = NS["result"] + task_id
    r  = _get_client()
    raw = r.get(result_key) if r else _mem_get(result_key)
    return json.loads(raw) if raw else None


def get_queue_lengths() -> dict:
    """Return item count for all queues."""
    lengths = {}
    r = _get_client()
    for name, key in QUEUES.items():
        if r:
            lengths[name] = r.llen(key)
        else:
            lengths[name] = _mem_qlen(key)
    return lengths


# ── Rate limiting ─────────────────────────────────────────────────────────────

def check_rate_limit(
    identifier: str,
    limit:      int,
    window_sec: int,
) -> dict:
    """
    Token-bucket rate limiter.

    Args:
        identifier: e.g. "linkedin:send:contact_123"
        limit:      Max calls in window
        window_sec: Window size in seconds

    Returns:
        { allowed: bool, remaining: int, reset_at: str }
    """
    key = NS["rate"] + identifier
    r   = _get_client()
    now = int(time.time())

    if r:
        pipe  = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_sec)
        count, _ = pipe.execute()
    else:
        raw   = _mem_get(key)
        count = (int(raw) + 1) if raw else 1
        _mem_set(key, str(count), window_sec)

    allowed   = count <= limit
    remaining = max(0, limit - count)
    reset_at  = datetime.fromtimestamp(now + window_sec).isoformat()

    return {"allowed": allowed, "remaining": remaining,
            "reset_at": reset_at, "count": count}


# ── Session storage ───────────────────────────────────────────────────────────

def session_set(session_id: str, data: dict, ttl: int = 3600) -> None:
    """Store agent session data (replaces in-memory session dict)."""
    key = NS["session"] + session_id
    r   = _get_client()
    serialized = json.dumps(data, default=str)
    if r:
        r.setex(key, ttl, serialized)
    else:
        _mem_set(key, serialized, ttl)


def session_get(session_id: str) -> Optional[dict]:
    """Retrieve agent session data."""
    key = NS["session"] + session_id
    r   = _get_client()
    raw = r.get(key) if r else _mem_get(key)
    return json.loads(raw) if raw else None


# ── Health check ──────────────────────────────────────────────────────────────

def get_redis_info() -> dict:
    """Return Redis connection info and queue snapshot."""
    r       = _get_client()
    is_live = r is not None
    info: dict = {
        "connected":   is_live,
        "mode":        "redis" if is_live else "in-memory",
        "url":         REDIS_URL or "(not set)",
        "queues":      get_queue_lengths(),
        "cache_keys":  0,
    }
    if r:
        try:
            server = r.info("server")
            info["redis_version"] = server.get("redis_version", "?")
            info["uptime_days"]   = server.get("uptime_in_days", 0)
            info["cache_keys"]    = len(r.keys(NS["cache"] + "*"))
        except Exception:
            pass
    else:
        info["cache_keys"] = sum(
            1 for k in _mem_store if k.startswith(NS["cache"]))
    return info


# ── Demo seeder & self-test ───────────────────────────────────────────────────

def _seed_demo_tasks():
    """Enqueue a few demo tasks for the dashboard."""
    lengths = get_queue_lengths()
    if any(v > 0 for v in lengths.values()):
        return
    enqueue("wishes", "birthday_wish",
            {"contact_id": "urn_rakib_001", "platform": "LinkedIn"}, priority=3)
    enqueue("wishes", "birthday_wish",
            {"contact_id": "urn_mim_004",   "platform": "WhatsApp"}, priority=2)
    enqueue("followups", "smart_followup",
            {"contact_id": "urn_nadia_002", "days_since": 3}, priority=5)
    enqueue("analytics", "compute_roi",
            {"period_days": 30}, priority=8)


# ── Streamlit dashboard ───────────────────────────────────────────────────────

def render_dashboard():
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Redis Cache", page_icon="⚡",
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
    .cc-badge{background:#dc382d;color:#fff;font-size:0.65rem;font-weight:700;
              padding:2px 8px;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;}
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);
                font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:var(--muted);margin:22px 0 10px;
                   display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    .q-row{background:var(--surface);border:1px solid var(--border);
           border-radius:8px;padding:10px 14px;margin-bottom:6px;
           display:flex;align-items:center;justify-content:space-between;}
    .code-box{background:#010409;border:1px solid var(--border);border-radius:8px;
              padding:12px 14px;font-family:'JetBrains Mono',monospace;
              font-size:0.76rem;color:#7ee787;white-space:pre;}
    div[data-testid="stButton"]>button{background:var(--surface);
        border:1px solid var(--border);color:var(--text);border-radius:8px;
        font-size:0.79rem;font-weight:500;}
    div[data-testid="stButton"]>button:hover{border-color:#58a6ff;background:#1c2128;}
    div[data-testid="stButton"]>button[kind="primary"]{background:#dc382d;
        border-color:#dc382d;color:#fff;}
    ::-webkit-scrollbar{width:5px;}::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
    </style>
    """, unsafe_allow_html=True)

    _seed_demo_tasks()

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">⚡</span>
      <h1>Redis Cache & Task Queue</h1>
      <span class="cc-badge">v9.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    info = get_redis_info()

    if info["connected"]:
        st.markdown("""
        <div style="background:#051a09;border-left:4px solid #3fb950;
                    border-radius:8px;padding:10px 16px;margin-bottom:14px;">
          <span style="color:#3fb950;font-weight:700">Redis Connected</span>
          <span style="font-size:0.78rem;color:#c9d1d9;margin-left:8px">
            All caching and queuing live</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:#1a1500;border-left:4px solid #d29922;
                    border-radius:8px;padding:10px 16px;margin-bottom:14px;">
          <span style="color:#d29922;font-weight:700">In-Memory Mode</span>
          <span style="font-size:0.78rem;color:#c9d1d9;margin-left:8px">
            Set REDIS_URL to enable Redis</span>
        </div>
        """, unsafe_allow_html=True)

    queues = info["queues"]
    total_q = sum(queues.values())
    m1, m2, m3, m4 = st.columns(4)
    for col, lbl, val, color in [
        (m1, "Mode",        info["mode"].title(), "#3fb950" if info["connected"] else "#d29922"),
        (m2, "Cache Keys",  info["cache_keys"],   "#58a6ff"),
        (m3, "Queue Total", total_q,              "#f78166"),
        (m4, "Version",     info.get("redis_version","–"), "#8b949e"),
    ]:
        with col:
            st.markdown(f'<div class="mini"><div class="mini-val" style="color:{color}">'
                        f'{val}</div><div class="mini-lbl">{lbl}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown('<div class="section-title">Task Queues</div>',
                    unsafe_allow_html=True)
        Q_COLORS = {"wishes":"#f78166","followups":"#58a6ff",
                    "analytics":"#d29922","alerts":"#f85149"}
        for qname, count in queues.items():
            color = Q_COLORS.get(qname, "#8b949e")
            st.markdown(f"""
            <div class="q-row">
              <div>
                <div style="font-weight:700;font-size:0.84rem">{qname}</div>
                <div style="font-size:0.68rem;color:#8b949e;margin-top:2px;
                            font-family:'JetBrains Mono',monospace">
                  {QUEUES[qname]}
                </div>
              </div>
              <div style="font-size:1.2rem;font-weight:700;font-family:'JetBrains Mono',monospace;
                          color:{color}">{count}</div>
            </div>
            """, unsafe_allow_html=True)

        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("+ Enqueue Test Task", type="primary",
                         use_container_width=True):
                tid = enqueue("wishes","test_wish",
                              {"contact": "test","platform":"LinkedIn"})
                st.success(f"Task {tid} queued")
                st.rerun()
        with bc2:
            if st.button("Pop & Process", use_container_width=True):
                task = dequeue("wishes")
                if task:
                    complete_task(task["task_id"], result="processed")
                    st.success(f"Processed: {task['task_type']}")
                else:
                    st.info("Queue empty")
                st.rerun()

        st.markdown('<div class="section-title">Rate Limit Test</div>',
                    unsafe_allow_html=True)
        rl = check_rate_limit("test:linkedin:send", limit=5, window_sec=60)
        color = "#3fb950" if rl["allowed"] else "#f85149"
        st.markdown(f"""
        <div class="q-row">
          <div style="font-size:0.82rem">linkedin:send (5/min)</div>
          <div>
            <span style="color:{color};font-weight:700">
              {'✅ Allowed' if rl['allowed'] else '🚫 Blocked'}
            </span>
            <span style="font-size:0.68rem;color:#8b949e;margin-left:8px">
              {rl['remaining']} left
            </span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with right:
        st.markdown('<div class="section-title">Setup</div>',
                    unsafe_allow_html=True)
        st.markdown("""
<div class="code-box">pip install redis

# .env
REDIS_URL=redis://localhost:6379/0

# Docker (quick start)
docker run -d -p 6379:6379 redis:alpine

# agent.py integration
from redis_cache import cache_get, cache_set, enqueue, cached

# Cache contacts for 2 minutes
@cached("contacts:list", ttl=120)
def get_contacts(): ...

# Queue a birthday wish
task_id = enqueue("wishes", "birthday_wish", {
    "contact_id": "urn_rakib_001",
    "platform":   "LinkedIn",
})</div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">TTL Reference</div>',
                    unsafe_allow_html=True)
        for key, seconds in TTL.items():
            mins = seconds // 60
            label = f"{mins}m" if mins >= 1 else f"{seconds}s"
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;
                        padding:5px 0;border-bottom:1px solid #21262d;
                        font-size:0.76rem;">
              <span style="font-family:'JetBrains Mono',monospace">{key}</span>
              <span style="color:#8b949e">{label}</span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;font-size:0.7rem;
                color:#8b949e;padding:4px 0 10px;">
      <span>Birthday Wishes Agent · branch <code style="background:#161b22;
            padding:1px 5px;border-radius:4px">9.0</code></span>
      <span>Redis Cache & Task Queue</span>
      <span>Built by <strong style="color:#e6edf3">SadManFahIm</strong></span>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    print("=== Redis Cache & Task Queue -- self test ===\n")
    info = get_redis_info()
    print(f"Mode       : {info['mode']}")
    print(f"Connected  : {info['connected']}")

    # Cache test
    cache_set("test:key", {"hello": "world"}, ttl=10)
    val = cache_get("test:key")
    print(f"\nCache set/get : {'✅' if val == {'hello':'world'} else '❌'} {val}")

    cache_delete("test:key")
    print(f"Cache delete  : {'✅' if cache_get('test:key') is None else '❌'}")

    # Queue test
    _seed_demo_tasks()
    lengths = get_queue_lengths()
    print(f"\nQueue lengths : {lengths}")
    task = dequeue("wishes")
    if task:
        complete_task(task["task_id"], result="ok")
        status = get_task_status(task["task_id"])
        print(f"Dequeue+complete: ✅ status={status['status'] if status else 'N/A'}")

    # Rate limit test
    rl = check_rate_limit("test:api", limit=3, window_sec=60)
    print(f"\nRate limit (3/min): allowed={rl['allowed']} remaining={rl['remaining']}")
else:
    render_dashboard()
