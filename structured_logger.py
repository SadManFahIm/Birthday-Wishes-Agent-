"""
Structured Logger — Birthday Wishes Agent v10.0
=================================================
JSON-structured logging with correlation IDs, per-module level
control, file rotation, and a performance decorator.

Usage:
  from structured_logger import get_logger, log_duration, set_correlation_id
  logger = get_logger("my_module")
  logger.info("Something happened", extra={"contact_id": "c-001"})

  @log_duration
  def slow_function(): ...

  with correlation_context("briefing-abc123"):
      logger.info("All logs in this block share the correlation ID")

Environment:
  BWA_LOG_LEVEL=INFO               # global default
  BWA_LOG_LEVEL_AUDIT=DEBUG        # per-module override
  BWA_LOG_LEVEL_PUSH=WARNING
  BWA_LOG_FORMAT=json              # json (prod) or text (dev)
  BWA_LOG_FILE=agent.log           # file path (empty = no file)
  BWA_LOG_MAX_BYTES=10485760       # 10 MB
  BWA_LOG_BACKUP_COUNT=5

Author : Fahim (SadManFahIm)
Branch : feature/structured-logging (→ 10.0)
"""

import json
import logging
import logging.handlers
import os
import sys
import time
import uuid
import functools
import threading
import contextvars
from datetime import datetime, timezone
from typing import Optional

# ──────────────────────────────────────────────────────────────
# Correlation ID — thread-safe + asyncio-safe via contextvars
# ──────────────────────────────────────────────────────────────

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="")


def set_correlation_id(cid: str = "") -> str:
    """Set correlation ID for the current context. Auto-generates if empty."""
    if not cid:
        cid = uuid.uuid4().hex[:12]
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str:
    """Get current correlation ID."""
    return _correlation_id.get()


class correlation_context:
    """Context manager that sets a correlation ID for a block."""

    def __init__(self, cid: str = ""):
        self.cid = cid
        self.token = None

    def __enter__(self):
        if not self.cid:
            self.cid = uuid.uuid4().hex[:12]
        self.token = _correlation_id.set(self.cid)
        return self.cid

    def __exit__(self, *args):
        if self.token is not None:
            _correlation_id.reset(self.token)


# ──────────────────────────────────────────────────────────────
# JSON formatter
# ──────────────────────────────────────────────────────────────


class JSONFormatter(logging.Formatter):
    """Formats every log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
            "correlation_id": _correlation_id.get(),
        }

        # Merge extra fields
        for key in ("contact_id", "action", "duration_ms",
                    "entity_id", "platform", "user_id",
                    "error", "count", "file", "func"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        # Catch-all for any extra dict passed
        if hasattr(record, "data") and record.data:
            entry["data"] = record.data

        # Exception info
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        # Source location for DEBUG/ERROR
        if record.levelno >= logging.ERROR or record.levelno <= logging.DEBUG:
            entry["func"] = record.funcName
            entry["file"] = f"{record.filename}:{record.lineno}"

        return json.dumps(entry, default=str, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────
# Human-readable formatter (dev mode)
# ──────────────────────────────────────────────────────────────


class DevFormatter(logging.Formatter):
    """Color-coded, human-readable formatter for development."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[41m",  # red bg
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET
        cid = _correlation_id.get()
        cid_str = f" [{cid}]" if cid else ""
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

        msg = record.getMessage()

        # Append extra fields if present
        extras = []
        for key in ("contact_id", "action", "duration_ms",
                    "platform", "count"):
            val = getattr(record, key, None)
            if val is not None:
                extras.append(f"{key}={val}")
        extra_str = f" ({', '.join(extras)})" if extras else ""

        return (f"{ts} {color}{record.levelname:<8}{reset} "
                f"{record.name}{cid_str} {msg}{extra_str}")


# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

_LOG_FORMAT = os.getenv("BWA_LOG_FORMAT", "text").lower()
_LOG_LEVEL = os.getenv("BWA_LOG_LEVEL", "INFO").upper()
_LOG_FILE = os.getenv("BWA_LOG_FILE", "agent.log")
_LOG_MAX_BYTES = int(os.getenv("BWA_LOG_MAX_BYTES", "10485760"))
_LOG_BACKUP_COUNT = int(os.getenv("BWA_LOG_BACKUP_COUNT", "5"))

_configured_loggers: set[str] = set()
_setup_lock = threading.Lock()
_root_configured = False


def _get_module_level(module_name: str) -> int:
    """Resolve log level for a module. Checks BWA_LOG_LEVEL_<MODULE> first."""
    suffix = module_name.upper().replace(".", "_").replace("-", "_")
    env_key = f"BWA_LOG_LEVEL_{suffix}"
    module_level = os.getenv(env_key, "").upper()
    if module_level and hasattr(logging, module_level):
        return getattr(logging, module_level)
    return getattr(logging, _LOG_LEVEL, logging.INFO)


def _setup_root():
    """Configure the root logger once (handlers, formatters)."""
    global _root_configured
    if _root_configured:
        return
    with _setup_lock:
        if _root_configured:
            return

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)  # handlers filter by their own level

        # Remove default handlers
        root.handlers.clear()

        # Console handler
        console = logging.StreamHandler(sys.stderr)
        if _LOG_FORMAT == "json":
            console.setFormatter(JSONFormatter())
        else:
            console.setFormatter(DevFormatter())
        console.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
        root.addHandler(console)

        # File handler (rotating)
        if _LOG_FILE:
            try:
                file_handler = logging.handlers.RotatingFileHandler(
                    _LOG_FILE,
                    maxBytes=_LOG_MAX_BYTES,
                    backupCount=_LOG_BACKUP_COUNT,
                    encoding="utf-8",
                )
                # File always gets JSON for machine parsing
                file_handler.setFormatter(JSONFormatter())
                file_handler.setLevel(logging.DEBUG)
                root.addHandler(file_handler)
            except (OSError, PermissionError):
                pass  # Can't write log file, continue with console only

        _root_configured = True


# ──────────────────────────────────────────────────────────────
# Public API: get_logger()
# ──────────────────────────────────────────────────────────────


def get_logger(module_name: str) -> logging.Logger:
    """
    Factory function for module loggers.
    Drop-in replacement for logging.getLogger(__name__).

    Usage:
      from structured_logger import get_logger
      logger = get_logger(__name__)
    """
    _setup_root()

    logger = logging.getLogger(module_name)

    if module_name not in _configured_loggers:
        logger.setLevel(_get_module_level(module_name))
        _configured_loggers.add(module_name)

    return logger


# ──────────────────────────────────────────────────────────────
# Performance decorator: @log_duration
# ──────────────────────────────────────────────────────────────


def log_duration(func=None, *, logger_name: str = "",
                 level: int = logging.INFO):
    """
    Decorator that logs function execution time.

    Usage:
      @log_duration
      def my_function(): ...

      @log_duration(level=logging.DEBUG)
      def detailed_function(): ...
    """
    def decorator(fn):
        _logger = get_logger(logger_name or fn.__module__)

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                _logger.log(
                    level,
                    "%s completed in %.1fms",
                    fn.__name__, elapsed,
                    extra={"duration_ms": round(elapsed, 1),
                           "func": fn.__name__})
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                _logger.error(
                    "%s failed after %.1fms: %s",
                    fn.__name__, elapsed, exc,
                    extra={"duration_ms": round(elapsed, 1),
                           "func": fn.__name__,
                           "error": str(exc)})
                raise

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                _logger.log(
                    level,
                    "%s completed in %.1fms",
                    fn.__name__, elapsed,
                    extra={"duration_ms": round(elapsed, 1),
                           "func": fn.__name__})
                return result
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                _logger.error(
                    "%s failed after %.1fms: %s",
                    fn.__name__, elapsed, exc,
                    extra={"duration_ms": round(elapsed, 1),
                           "func": fn.__name__,
                           "error": str(exc)})
                raise

        import asyncio
        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    if func is not None:
        return decorator(func)
    return decorator


# ──────────────────────────────────────────────────────────────
# Audit bridge — log CRITICAL to audit_trail table
# ──────────────────────────────────────────────────────────────


class AuditBridgeHandler(logging.Handler):
    """Writes CRITICAL log events to the audit_trail table."""

    def __init__(self, db_path: str = "agent_history.db"):
        super().__init__(level=logging.CRITICAL)
        self.db_path = db_path

    def emit(self, record: logging.LogRecord):
        try:
            from audit_log import record as audit_record
            from pathlib import Path
            audit_record(
                "system_alert",
                record.getMessage()[:200],
                actor="logger",
                module=record.name,
                severity="critical",
                details=json.dumps({
                    "level": record.levelname,
                    "correlation_id": _correlation_id.get(),
                    "file": f"{record.filename}:{record.lineno}",
                }, default=str),
                db_path=Path(self.db_path),
            )
        except Exception:
            pass  # Never let audit logging break the app


def enable_audit_bridge(db_path: str = "agent_history.db"):
    """Add audit bridge handler to root logger."""
    root = logging.getLogger()
    handler = AuditBridgeHandler(db_path)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """Logging configuration dashboard."""
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Structured Logger", page_icon="📝",
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
    .log-line{font-family:'JetBrains Mono',monospace;font-size:0.72rem;
              padding:4px 8px;margin:2px 0;border-radius:4px;
              background:#0d1117;border:1px solid var(--border);}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">📝</span>
      <h1>Structured Logger</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    # KPIs
    st.markdown('<div class="section-title">Configuration</div>',
                unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    for col, val, lbl in [
        (k1, _LOG_FORMAT.upper(), "Format"),
        (k2, _LOG_LEVEL, "Level"),
        (k3, _LOG_FILE or "(none)", "Log File"),
        (k4, len(_configured_loggers), "Active Loggers"),
    ]:
        col.markdown(
            f'<div class="mini"><div class="mini-val">{val}</div>'
            f'<div class="mini-lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

    tabs = st.tabs(["📋 Config", "🔍 Live Test", "📄 Log File"])

    # Config tab
    with tabs[0]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        st.markdown("**Environment Variables**")
        env_vars = {
            "BWA_LOG_FORMAT": _LOG_FORMAT,
            "BWA_LOG_LEVEL": _LOG_LEVEL,
            "BWA_LOG_FILE": _LOG_FILE,
            "BWA_LOG_MAX_BYTES": str(_LOG_MAX_BYTES),
            "BWA_LOG_BACKUP_COUNT": str(_LOG_BACKUP_COUNT),
        }
        for k, v in env_vars.items():
            st.markdown(f'`{k}` = `{v}`')

        st.markdown("**Per-Module Overrides**")
        st.markdown("Set `BWA_LOG_LEVEL_<MODULE>=DEBUG` to override "
                     "per module.")
        if _configured_loggers:
            for name in sorted(_configured_loggers):
                lvl = logging.getLevelName(
                    logging.getLogger(name).getEffectiveLevel())
                st.markdown(f'  `{name}` → `{lvl}`')
        st.markdown('</div>', unsafe_allow_html=True)

    # Live test tab
    with tabs[1]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        test_module = st.text_input("Module name", "test_module",
                                    key="tm")
        test_msg = st.text_input("Message", "Hello from dashboard",
                                 key="tmsg")
        test_level = st.selectbox("Level",
                                  ["DEBUG", "INFO", "WARNING", "ERROR"],
                                  index=1, key="tlvl")
        if st.button("📤 Emit Log", key="btn_emit"):
            test_logger = get_logger(test_module)
            with correlation_context() as cid:
                test_logger.log(
                    getattr(logging, test_level),
                    test_msg,
                    extra={"contact_id": "dashboard-test"})
                st.success(f"Emitted {test_level} with correlation_id={cid}")
        st.markdown('</div>', unsafe_allow_html=True)

    # Log file tab
    with tabs[2]:
        if _LOG_FILE and os.path.exists(_LOG_FILE):
            st.markdown('<div class="section-title">Recent Entries</div>',
                        unsafe_allow_html=True)
            try:
                with open(_LOG_FILE, "r") as f:
                    lines = f.readlines()
                for line in lines[-20:]:
                    st.markdown(
                        f'<div class="log-line">{line.strip()}</div>',
                        unsafe_allow_html=True)
            except Exception as exc:
                st.error(f"Error reading log: {exc}")
        else:
            st.info(f"Log file not found: {_LOG_FILE}")

    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/structured-logging</code> · Structured Logger v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test."""
    import io

    print("=" * 60)
    print("Structured Logger — Self-Test")
    print("=" * 60)

    # Reset state for clean test
    global _root_configured
    _root_configured = False
    _configured_loggers.clear()
    logging.getLogger().handlers.clear()

    # 1. get_logger
    print("\n[1/8] get_logger ...")
    logger = get_logger("test_module")
    assert logger.name == "test_module"
    assert "test_module" in _configured_loggers
    print("      ✅ Logger created: test_module")

    # 2. Correlation ID
    print("[2/8] Correlation ID ...")
    cid = set_correlation_id("test-abc-123")
    assert get_correlation_id() == "test-abc-123"
    with correlation_context("ctx-xyz-789") as inner_cid:
        assert inner_cid == "ctx-xyz-789"
        assert get_correlation_id() == "ctx-xyz-789"
    # Context manager resets
    assert get_correlation_id() == "test-abc-123"
    set_correlation_id("")  # reset
    print("      ✅ set/get/context_manager all work")

    # 3. JSON formatter output
    print("[3/8] JSON formatter ...")
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="json_test", level=logging.INFO,
        pathname="test.py", lineno=42,
        msg="Test message", args=(), exc_info=None)
    record.contact_id = "c-001"
    set_correlation_id("json-cid")
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["module"] == "json_test"
    assert parsed["message"] == "Test message"
    assert parsed["correlation_id"] == "json-cid"
    assert parsed["contact_id"] == "c-001"
    set_correlation_id("")
    print(f"      ✅ Valid JSON with all fields")

    # 4. Dev formatter output
    print("[4/8] Dev formatter ...")
    dev_formatter = DevFormatter()
    output = dev_formatter.format(record)
    assert "INFO" in output
    assert "json_test" in output
    assert "Test message" in output
    print(f"      ✅ Human-readable format OK")

    # 5. Per-module log level
    print("[5/8] Per-module level ...")
    os.environ["BWA_LOG_LEVEL_SPECIAL_MODULE"] = "DEBUG"
    level = _get_module_level("special_module")
    assert level == logging.DEBUG
    del os.environ["BWA_LOG_LEVEL_SPECIAL_MODULE"]
    level = _get_module_level("normal_module")
    assert level == getattr(logging, _LOG_LEVEL)
    print("      ✅ Module-specific level resolution OK")

    # 6. @log_duration (sync)
    print("[6/8] @log_duration (sync) ...")

    @log_duration
    def _test_slow():
        time.sleep(0.01)
        return "done"

    result = _test_slow()
    assert result == "done"
    print("      ✅ Sync function timed + returned correctly")

    # 7. @log_duration (async)
    print("[7/8] @log_duration (async) ...")
    import asyncio

    @log_duration
    async def _test_async_slow():
        await asyncio.sleep(0.01)
        return "async_done"

    result = asyncio.run(_test_async_slow())
    assert result == "async_done"
    print("      ✅ Async function timed + returned correctly")

    # 8. @log_duration (error)
    print("[8/8] @log_duration (error handling) ...")

    @log_duration
    def _test_fail():
        raise ValueError("Intentional test error")

    try:
        _test_fail()
        assert False, "Should have raised"
    except ValueError:
        pass
    print("      ✅ Error logged, exception re-raised")

    print("\n" + "=" * 60)
    print("✅ ALL STRUCTURED LOGGER SELF-TESTS PASSED")
    print("=" * 60)


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Structured Logger -- self test ===\n")
    _self_test()
else:
    render_dashboard()
