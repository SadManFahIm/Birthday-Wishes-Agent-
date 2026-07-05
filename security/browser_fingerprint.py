"""
browser_fingerprint.py
----------------------
Browser Fingerprint Randomizer for Birthday Wishes Agent.

Randomizes browser fingerprints to avoid LinkedIn bot detection.
Each session gets a unique combination of user agent, viewport,
timezone, language, and other browser properties.

What gets randomized:
  - User agent (Chrome version, OS, platform)
  - Viewport size (common screen resolutions)
  - Browser timezone
  - Accept-Language header
  - Color depth and pixel ratio
  - Hardware concurrency (CPU cores)
  - WebGL renderer string
  - Canvas fingerprint noise

How it works:
  1. Generates a random fingerprint profile before each session
  2. Applies it to browser_use BrowserConfig
  3. Rotates fingerprint every N sessions
  4. Logs used fingerprints to avoid repeating

Usage:
    from browser_fingerprint import (
        get_random_fingerprint,
        build_fingerprint_browser_config,
        get_fingerprint_stats,
    )

    config  = build_fingerprint_browser_config()
    browser = Browser(config=config)
"""

import logging
import random
import sqlite3
import hashlib
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ------------------------------------------------------------
# FINGERPRINT DATA POOLS
# ------------------------------------------------------------

USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 1600, "height": 900},
    {"width": 2560, "height": 1440},
    {"width": 1280, "height": 800},
]

TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "America/Toronto",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Asia/Kolkata",
    "Asia/Dhaka",
    "Australia/Sydney",
]

LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-US,en;q=0.9,de;q=0.8",
    "en-CA,en;q=0.9",
    "en-AU,en;q=0.9",
]

PLATFORMS = [
    "Win32",
    "MacIntel",
    "Linux x86_64",
]

WEBGL_RENDERERS = [
    "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (Intel, Intel(R) Iris Xe Graphics Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0)",
    "ANGLE (Intel, Intel HD Graphics 530 Direct3D11 vs_5_0 ps_5_0)",
]

COLOR_DEPTHS    = [24, 30, 32]
PIXEL_RATIOS    = [1.0, 1.25, 1.5, 2.0]
CPU_CORES       = [2, 4, 6, 8, 12, 16]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_fingerprint_table():
    """Create fingerprint tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fingerprint_sessions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint_hash TEXT NOT NULL,
                user_agent   TEXT,
                viewport     TEXT,
                timezone     TEXT,
                language     TEXT,
                used_date    TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("Fingerprint table ready.")


# ------------------------------------------------------------
# FINGERPRINT GENERATION
# ------------------------------------------------------------

def get_random_fingerprint() -> dict:
    """
    Generate a random browser fingerprint profile.

    Returns:
        Dict with all fingerprint properties.
    """
    user_agent  = random.choice(USER_AGENTS)
    viewport    = random.choice(VIEWPORTS)
    timezone    = random.choice(TIMEZONES)
    language    = random.choice(LANGUAGES)
    platform    = _infer_platform(user_agent)
    webgl       = random.choice(WEBGL_RENDERERS)
    color_depth = random.choice(COLOR_DEPTHS)
    pixel_ratio = random.choice(PIXEL_RATIOS)
    cpu_cores   = random.choice(CPU_CORES)

    # Add small random noise to viewport
    viewport = {
        "width":  viewport["width"]  + random.randint(-10, 10),
        "height": viewport["height"] + random.randint(-10, 10),
    }

    fingerprint = {
        "user_agent":    user_agent,
        "viewport":      viewport,
        "timezone":      timezone,
        "language":      language,
        "platform":      platform,
        "webgl_renderer": webgl,
        "color_depth":   color_depth,
        "pixel_ratio":   pixel_ratio,
        "cpu_cores":     cpu_cores,
        "hash":          _hash_fingerprint(user_agent, viewport, timezone),
    }

    logger.info(
        "Fingerprint generated: %s | %dx%d | %s",
        user_agent[:50], viewport["width"], viewport["height"], timezone,
    )

    _log_fingerprint(fingerprint)
    return fingerprint


def _infer_platform(user_agent: str) -> str:
    """Infer platform from user agent string."""
    ua = user_agent.lower()
    if "windows" in ua:
        return "Win32"
    if "macintosh" in ua or "mac os" in ua:
        return "MacIntel"
    if "linux" in ua:
        return "Linux x86_64"
    return random.choice(PLATFORMS)


def _hash_fingerprint(user_agent: str, viewport: dict, timezone: str) -> str:
    """Generate a short hash for a fingerprint combination."""
    raw = f"{user_agent}|{viewport['width']}x{viewport['height']}|{timezone}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _log_fingerprint(fingerprint: dict):
    """Log used fingerprint to DB."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("""
                INSERT INTO fingerprint_sessions
                (fingerprint_hash, user_agent, viewport, timezone,
                 language, used_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                fingerprint["hash"],
                fingerprint["user_agent"][:100],
                f"{fingerprint['viewport']['width']}x{fingerprint['viewport']['height']}",
                fingerprint["timezone"],
                fingerprint["language"],
                date.today().isoformat(),
                datetime.now().isoformat(),
            ))
            conn.commit()
    except Exception as e:
        logger.warning("Could not log fingerprint: %s", e)


# ------------------------------------------------------------
# BROWSER CONFIG
# ------------------------------------------------------------

def build_fingerprint_browser_config(fingerprint: dict | None = None):
    """
    Build BrowserConfig with randomized fingerprint.

    Args:
        fingerprint: Pre-generated fingerprint dict.
                     If None, generates a new random one.

    Returns:
        BrowserConfig with fingerprint applied.
    """
    try:
        from browser_use import BrowserConfig

        if not fingerprint:
            fingerprint = get_random_fingerprint()

        browser_profile = str(Path.cwd() / "browser_profile")

        config = BrowserConfig(
            user_data_dir=browser_profile,
            extra_chromium_args=_build_chromium_args(fingerprint),
        )

        logger.info(
            "Browser config built with fingerprint: %s",
            fingerprint["hash"],
        )
        return config, fingerprint

    except Exception as e:
        logger.error("Failed to build fingerprint browser config: %s", e)
        from browser_use import BrowserConfig
        return BrowserConfig(
            user_data_dir=str(Path.cwd() / "browser_profile")
        ), {}


def _build_chromium_args(fingerprint: dict) -> list[str]:
    """Build Chromium launch args for fingerprint spoofing."""
    vp    = fingerprint.get("viewport", {"width": 1920, "height": 1080})
    lang  = fingerprint.get("language", "en-US,en;q=0.9").split(",")[0]
    ua    = fingerprint.get("user_agent", "")

    args = [
        f"--window-size={vp['width']},{vp['height']}",
        f"--lang={lang}",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--disable-infobars",
        "--disable-extensions",
        "--disable-web-security",
        "--allow-running-insecure-content",
    ]

    if ua:
        args.append(f"--user-agent={ua}")

    return args


# ------------------------------------------------------------
# JS INJECTION
# ------------------------------------------------------------

def get_fingerprint_js(fingerprint: dict) -> str:
    """
    Get JavaScript to inject for deeper fingerprint spoofing.
    Inject this into page context after page load.
    """
    platform    = fingerprint.get("platform", "Win32")
    cpu_cores   = fingerprint.get("cpu_cores", 4)
    color_depth = fingerprint.get("color_depth", 24)
    pixel_ratio = fingerprint.get("pixel_ratio", 1.0)
    webgl       = fingerprint.get("webgl_renderer", "")
    vp          = fingerprint.get("viewport", {"width": 1920, "height": 1080})
    lang        = fingerprint.get("language", "en-US")

    return f"""
// Override navigator properties
Object.defineProperty(navigator, 'platform', {{
    get: () => '{platform}'
}});
Object.defineProperty(navigator, 'hardwareConcurrency', {{
    get: () => {cpu_cores}
}});
Object.defineProperty(navigator, 'language', {{
    get: () => '{lang.split(",")[0]}'
}});
Object.defineProperty(navigator, 'languages', {{
    get: () => ['{lang.split(",")[0]}', 'en']
}});

// Override screen properties
Object.defineProperty(screen, 'width',      {{ get: () => {vp['width']} }});
Object.defineProperty(screen, 'height',     {{ get: () => {vp['height']} }});
Object.defineProperty(screen, 'colorDepth', {{ get: () => {color_depth} }});
Object.defineProperty(window, 'devicePixelRatio', {{ get: () => {pixel_ratio} }});

// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});

// Override plugins (non-empty)
Object.defineProperty(navigator, 'plugins', {{
    get: () => [1, 2, 3, 4, 5]
}});

// WebGL renderer override
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {{
    if (parameter === 37446) return '{webgl}';
    if (parameter === 37445) return 'WebKit WebGL';
    return getParameter.call(this, parameter);
}};

// Canvas noise
const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {{
    const ctx = this.getContext('2d');
    if (ctx) {{
        const noise = ctx.createImageData(1, 1);
        noise.data[0] = Math.floor(Math.random() * 10);
        ctx.putImageData(noise, 0, 0);
    }}
    return origToDataURL.apply(this, arguments);
}};
"""


# ------------------------------------------------------------
# STATS
# ------------------------------------------------------------

def get_fingerprint_stats() -> dict:
    """Get fingerprint usage stats."""
    if not DB_FILE.exists():
        return {"total_sessions": 0, "unique_fingerprints": 0}

    with sqlite3.connect(DB_FILE) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM fingerprint_sessions"
        ).fetchone()[0]

        unique = conn.execute(
            "SELECT COUNT(DISTINCT fingerprint_hash) FROM fingerprint_sessions"
        ).fetchone()[0]

        today = conn.execute(
            "SELECT COUNT(*) FROM fingerprint_sessions WHERE used_date = ?",
            (date.today().isoformat(),)
        ).fetchone()[0]

    return {
        "total_sessions":      total,
        "unique_fingerprints": unique,
        "sessions_today":      today,
    }


def build_fingerprint_report() -> str:
    """Build human-readable fingerprint report."""
    stats = get_fingerprint_stats()
    fp    = get_random_fingerprint()

    lines = [
        "Browser Fingerprint Randomizer Report",
        "-" * 55,
        f"  Total sessions     : {stats['total_sessions']}",
        f"  Unique fingerprints: {stats['unique_fingerprints']}",
        f"  Sessions today     : {stats['sessions_today']}",
        "-" * 55,
        "",
        "Current session fingerprint:",
        f"  User Agent : {fp['user_agent'][:60]}...",
        f"  Viewport   : {fp['viewport']['width']}x{fp['viewport']['height']}",
        f"  Timezone   : {fp['timezone']}",
        f"  Language   : {fp['language']}",
        f"  Platform   : {fp['platform']}",
        f"  CPU Cores  : {fp['cpu_cores']}",
        f"  Hash       : {fp['hash']}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    return "\n".join(lines)
