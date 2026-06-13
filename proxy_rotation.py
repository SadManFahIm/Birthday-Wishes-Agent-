"""
proxy_rotation.py
-----------------
Proxy Rotation for Birthday Wishes Agent.

Automatically rotates proxies to avoid LinkedIn rate limits
and IP bans during automated browsing.

How it works:
  1. Loads proxy list from .env or proxy file
  2. Assigns a proxy to each browser session
  3. Rotates to next proxy if current one is blocked or slow
  4. Marks failed proxies and skips them automatically
  5. Supports HTTP, HTTPS, and SOCKS5 proxies

.env setup:
  PROXY_ENABLED=true
  PROXY_LIST=http://user:pass@ip1:port,http://user:pass@ip2:port
  PROXY_FILE=proxies.txt        (optional, one proxy per line)
  PROXY_ROTATION=round_robin    (round_robin / random / fastest)
  PROXY_TEST_URL=https://www.linkedin.com

proxies.txt format (one per line):
  http://user:pass@ip:port
  socks5://ip:port
  https://ip:port

Usage:
    from proxy_rotation import (
        init_proxy_table,
        get_next_proxy,
        mark_proxy_failed,
        mark_proxy_success,
        build_proxy_browser_config,
        get_proxy_stats,
    )

    config = build_proxy_browser_config()
    browser = Browser(config=config)
"""

import logging
import random
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE    = Path("agent_history.db")
PROXY_FILE = Path("proxies.txt")

# Proxy rotation strategies
STRATEGIES = ["round_robin", "random", "fastest"]

# Max failures before a proxy is blacklisted
MAX_FAILURES = 3

# Cooldown before retrying a failed proxy (minutes)
FAILURE_COOLDOWN_MINUTES = 30


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_proxy_table():
    """Create proxy tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proxy_stats (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                proxy_url     TEXT    NOT NULL UNIQUE,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                last_used     TEXT,
                last_failure  TEXT,
                avg_speed_ms  REAL    DEFAULT 0,
                blacklisted   INTEGER DEFAULT 0,
                created_at    TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("Proxy stats table ready.")


# ------------------------------------------------------------
# LOAD PROXIES
# ------------------------------------------------------------

def load_proxies() -> list[str]:
    """
    Load proxy list from .env and/or proxy file.

    Returns:
        List of proxy URLs.
    """
    from dotenv import dotenv_values
    config = dotenv_values(".env")

    proxies = []

    # From .env PROXY_LIST
    proxy_list_str = config.get("PROXY_LIST", "")
    if proxy_list_str:
        for p in proxy_list_str.split(","):
            p = p.strip()
            if p:
                proxies.append(p)

    # From proxies.txt file
    if PROXY_FILE.exists():
        for line in PROXY_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                proxies.append(line)

    # Deduplicate
    proxies = list(dict.fromkeys(proxies))
    logger.info("Loaded %d proxies.", len(proxies))

    # Register new proxies in DB
    _register_proxies(proxies)

    return proxies


def _register_proxies(proxies: list[str]):
    """Register proxies in DB if not already there."""
    with sqlite3.connect(DB_FILE) as conn:
        for proxy in proxies:
            conn.execute("""
                INSERT OR IGNORE INTO proxy_stats
                (proxy_url, created_at)
                VALUES (?, ?)
            """, (proxy, datetime.now().isoformat()))
        conn.commit()


# ------------------------------------------------------------
# PROXY SELECTION
# ------------------------------------------------------------

def get_available_proxies() -> list[dict]:
    """Get proxies that are not blacklisted and not in cooldown."""
    if not DB_FILE.exists():
        return []

    cooldown_cutoff = (
        datetime.now() - timedelta(minutes=FAILURE_COOLDOWN_MINUTES)
    ).isoformat()

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT proxy_url, success_count, failure_count,
                   last_used, avg_speed_ms
            FROM   proxy_stats
            WHERE  blacklisted = 0
              AND  (last_failure IS NULL OR last_failure < ?)
            ORDER  BY failure_count ASC, avg_speed_ms ASC
        """, (cooldown_cutoff,)).fetchall()

    return [
        {
            "url":           row[0],
            "success_count": row[1],
            "failure_count": row[2],
            "last_used":     row[3],
            "avg_speed_ms":  row[4],
        }
        for row in rows
    ]


def get_next_proxy(strategy: str = "") -> str | None:
    """
    Get the next proxy to use based on strategy.

    Args:
        strategy: rotation strategy (round_robin/random/fastest)
                  If empty, reads from .env PROXY_ROTATION

    Returns:
        Proxy URL string or None if no proxies available.
    """
    from dotenv import dotenv_values
    config = dotenv_values(".env")

    if not config.get("PROXY_ENABLED", "false").lower() == "true":
        logger.info("Proxy rotation disabled.")
        return None

    if not strategy:
        strategy = config.get("PROXY_ROTATION", "round_robin").lower()

    proxies = get_available_proxies()

    if not proxies:
        # Try loading from config again
        load_proxies()
        proxies = get_available_proxies()

    if not proxies:
        logger.warning("No available proxies. Running without proxy.")
        return None

    if strategy == "random":
        chosen = random.choice(proxies)

    elif strategy == "fastest":
        # Sort by avg speed (lowest = fastest)
        sorted_proxies = sorted(
            proxies,
            key=lambda p: p["avg_speed_ms"] if p["avg_speed_ms"] > 0 else 9999,
        )
        chosen = sorted_proxies[0]

    else:
        # round_robin: pick least recently used
        sorted_proxies = sorted(
            proxies,
            key=lambda p: p["last_used"] or "0000",
        )
        chosen = sorted_proxies[0]

    proxy_url = chosen["url"]
    logger.info("Using proxy: %s (strategy: %s)", _mask_proxy(proxy_url), strategy)

    # Update last_used
    _update_last_used(proxy_url)
    return proxy_url


def _mask_proxy(proxy_url: str) -> str:
    """Mask credentials in proxy URL for safe logging."""
    try:
        if "@" in proxy_url:
            scheme_creds, host = proxy_url.rsplit("@", 1)
            scheme = scheme_creds.split("://")[0]
            return f"{scheme}://***:***@{host}"
        return proxy_url
    except Exception:
        return "***"


def _update_last_used(proxy_url: str):
    """Update last_used timestamp for a proxy."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE proxy_stats SET last_used = ? WHERE proxy_url = ?
        """, (datetime.now().isoformat(), proxy_url))
        conn.commit()


# ------------------------------------------------------------
# MARK SUCCESS / FAILURE
# ------------------------------------------------------------

def mark_proxy_success(proxy_url: str, speed_ms: float = 0):
    """Mark a proxy as successful and update speed."""
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT success_count, avg_speed_ms FROM proxy_stats WHERE proxy_url = ?",
            (proxy_url,)
        ).fetchone()

        if row:
            count     = (row[0] or 0) + 1
            old_speed = row[1] or 0
            # Rolling average speed
            new_speed = ((old_speed * (count - 1)) + speed_ms) / count if speed_ms else old_speed

            conn.execute("""
                UPDATE proxy_stats
                SET success_count = ?, avg_speed_ms = ?
                WHERE proxy_url = ?
            """, (count, new_speed, proxy_url))
            conn.commit()

    logger.info("Proxy success: %s (speed: %.0fms)", _mask_proxy(proxy_url), speed_ms)


def mark_proxy_failed(proxy_url: str, reason: str = ""):
    """
    Mark a proxy as failed.
    Blacklists proxy after MAX_FAILURES failures.
    """
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT failure_count FROM proxy_stats WHERE proxy_url = ?",
            (proxy_url,)
        ).fetchone()

        failure_count = (row[0] if row else 0) + 1
        blacklisted   = 1 if failure_count >= MAX_FAILURES else 0

        conn.execute("""
            UPDATE proxy_stats
            SET failure_count = ?,
                last_failure  = ?,
                blacklisted   = ?
            WHERE proxy_url = ?
        """, (failure_count, datetime.now().isoformat(), blacklisted, proxy_url))
        conn.commit()

    if blacklisted:
        logger.warning("Proxy BLACKLISTED after %d failures: %s",
                       MAX_FAILURES, _mask_proxy(proxy_url))
    else:
        logger.warning("Proxy failure %d/%d: %s | Reason: %s",
                       failure_count, MAX_FAILURES, _mask_proxy(proxy_url), reason)


def reset_proxy(proxy_url: str):
    """Reset a proxy's failure count and remove from blacklist."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            UPDATE proxy_stats
            SET failure_count = 0,
                blacklisted   = 0,
                last_failure  = NULL
            WHERE proxy_url = ?
        """, (proxy_url,))
        conn.commit()
    logger.info("Proxy reset: %s", _mask_proxy(proxy_url))


# ------------------------------------------------------------
# BROWSER CONFIG
# ------------------------------------------------------------

def build_proxy_browser_config(proxy_url: str = ""):
    """
    Build BrowserConfig with proxy settings.

    Args:
        proxy_url: Proxy URL. If empty, gets next proxy automatically.

    Returns:
        BrowserConfig object with proxy set, or default config.
    """
    try:
        from browser_use import BrowserConfig
        from pathlib import Path

        browser_profile = str(Path.cwd() / "browser_profile")

        if not proxy_url:
            proxy_url = get_next_proxy()

        if not proxy_url:
            return BrowserConfig(user_data_dir=browser_profile)

        # Parse proxy
        proxy_settings = _parse_proxy(proxy_url)

        config = BrowserConfig(
            user_data_dir=browser_profile,
            proxy=proxy_settings,
        )

        logger.info("Browser configured with proxy: %s", _mask_proxy(proxy_url))
        return config

    except Exception as e:
        logger.error("Failed to build proxy browser config: %s", e)
        from browser_use import BrowserConfig
        return BrowserConfig(user_data_dir=str(Path.cwd() / "browser_profile"))


def _parse_proxy(proxy_url: str) -> dict:
    """Parse proxy URL into browser_use proxy dict format."""
    proxy = {"server": proxy_url}

    # Extract credentials if present
    if "@" in proxy_url:
        try:
            scheme_creds, host = proxy_url.rsplit("@", 1)
            creds = scheme_creds.split("://")[-1]
            if ":" in creds:
                username, password = creds.split(":", 1)
                scheme = proxy_url.split("://")[0]
                proxy["server"]   = f"{scheme}://{host}"
                proxy["username"] = username
                proxy["password"] = password
        except Exception as e:
            logger.warning("Could not parse proxy credentials: %s", e)

    return proxy


# ------------------------------------------------------------
# TEST PROXY
# ------------------------------------------------------------

def test_proxy(proxy_url: str, test_url: str = "https://www.linkedin.com") -> dict:
    """
    Test if a proxy is working.

    Returns:
        Dict with working (bool), speed_ms (float), error (str).
    """
    import requests

    proxies = {
        "http":  proxy_url,
        "https": proxy_url,
    }

    start = time.time()
    try:
        response = requests.get(
            test_url,
            proxies=proxies,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        speed_ms = (time.time() - start) * 1000

        if response.status_code < 500:
            mark_proxy_success(proxy_url, speed_ms)
            logger.info("Proxy OK: %s (%.0fms)", _mask_proxy(proxy_url), speed_ms)
            return {"working": True, "speed_ms": speed_ms, "error": ""}
        else:
            mark_proxy_failed(proxy_url, f"HTTP {response.status_code}")
            return {"working": False, "speed_ms": 0,
                    "error": f"HTTP {response.status_code}"}

    except Exception as e:
        mark_proxy_failed(proxy_url, str(e))
        return {"working": False, "speed_ms": 0, "error": str(e)}


def test_all_proxies() -> list[dict]:
    """Test all loaded proxies and return results."""
    proxies = load_proxies()
    results = []

    for proxy in proxies:
        result = test_proxy(proxy)
        result["proxy"] = _mask_proxy(proxy)
        results.append(result)

    working = sum(1 for r in results if r["working"])
    logger.info("Proxy test: %d/%d working.", working, len(results))
    return results


# ------------------------------------------------------------
# STATS & REPORT
# ------------------------------------------------------------

def get_proxy_stats() -> list[dict]:
    """Get stats for all proxies."""
    if not DB_FILE.exists():
        return []

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("""
            SELECT proxy_url, success_count, failure_count,
                   last_used, avg_speed_ms, blacklisted
            FROM   proxy_stats
            ORDER  BY blacklisted ASC, failure_count ASC
        """).fetchall()

    return [
        {
            "proxy":         _mask_proxy(row[0]),
            "success_count": row[1],
            "failure_count": row[2],
            "last_used":     row[3],
            "avg_speed_ms":  round(row[4] or 0, 1),
            "blacklisted":   bool(row[5]),
        }
        for row in rows
    ]


def build_proxy_report() -> str:
    """Build human-readable proxy stats report."""
    stats = get_proxy_stats()

    if not stats:
        return "No proxies configured. Add proxies to .env or proxies.txt"

    active      = [s for s in stats if not s["blacklisted"]]
    blacklisted = [s for s in stats if s["blacklisted"]]

    lines = [
        "Proxy Rotation Report",
        "-" * 60,
        f"  Total     : {len(stats)}",
        f"  Active    : {len(active)}",
        f"  Blacklisted: {len(blacklisted)}",
        "-" * 60,
        f"  {'Proxy':<30} {'OK':>5} {'Fail':>5} {'Speed':>8}",
        "  " + "-" * 52,
    ]

    for s in stats:
        status = "[X]" if s["blacklisted"] else "[OK]"
        lines.append(
            f"  {status} {s['proxy']:<28} {s['success_count']:>5} "
            f"{s['failure_count']:>5} {s['avg_speed_ms']:>7.0f}ms"
        )

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)
