"""
vpn_switch.py
-------------
VPN Auto-Switch for Birthday Wishes Agent.

Automatically switches VPN server when LinkedIn blocks or
rate-limits the current IP address.

Supported VPN clients:
  - OpenVPN  (cross-platform, config file based)
  - NordVPN  (CLI based)
  - ExpressVPN (CLI based)
  - Custom   (any CLI command)

How it works:
  1. Monitors LinkedIn responses for block/rate-limit signals
  2. When blocked -> disconnects current VPN
  3. Connects to next VPN server from the list
  4. Verifies new IP is different and not blocked
  5. Retries the failed task

.env setup:
  VPN_ENABLED=true
  VPN_CLIENT=nordvpn          # nordvpn / expressvpn / openvpn / custom
  VPN_SERVERS=us1,uk1,de1     # server list (NordVPN/ExpressVPN server names)
  VPN_OPENVPN_CONFIG_DIR=./vpn_configs   # for OpenVPN
  VPN_CUSTOM_CONNECT=my_vpn connect {server}   # for custom client
  VPN_CUSTOM_DISCONNECT=my_vpn disconnect
  VPN_ROTATION=round_robin    # round_robin / random

Usage:
    from vpn_switch import (
        init_vpn_table,
        auto_switch_vpn,
        connect_vpn,
        disconnect_vpn,
        get_current_ip,
        is_vpn_connected,
        build_vpn_report,
    )

    await auto_switch_vpn()
"""

import logging
import random
import sqlite3
import subprocess
import time
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")

# Supported VPN clients
SUPPORTED_CLIENTS = ["nordvpn", "expressvpn", "openvpn", "custom"]

# IP check URLs
IP_CHECK_URLS = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
]

# Signals that indicate a block or rate limit
BLOCK_SIGNALS = [
    "429",
    "too many requests",
    "rate limit",
    "blocked",
    "captcha",
    "security check",
    "unusual activity",
    "access denied",
    "403",
]


# ------------------------------------------------------------
# DB SETUP
# ------------------------------------------------------------

def init_vpn_table():
    """Create VPN switch tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vpn_switches (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                server       TEXT    NOT NULL,
                old_ip       TEXT,
                new_ip       TEXT,
                reason       TEXT,
                success      INTEGER DEFAULT 0,
                switch_date  TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("VPN switch table ready.")


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

def load_vpn_config() -> dict:
    """Load VPN config from .env."""
    from dotenv import dotenv_values
    config = dotenv_values(".env")

    servers_str = config.get("VPN_SERVERS", "")
    servers = [s.strip() for s in servers_str.split(",") if s.strip()]

    return {
        "enabled":          config.get("VPN_ENABLED", "false").lower() == "true",
        "client":           config.get("VPN_CLIENT", "nordvpn").lower(),
        "servers":          servers,
        "openvpn_dir":      config.get("VPN_OPENVPN_CONFIG_DIR", "./vpn_configs"),
        "custom_connect":   config.get("VPN_CUSTOM_CONNECT", ""),
        "custom_disconnect":config.get("VPN_CUSTOM_DISCONNECT", ""),
        "rotation":         config.get("VPN_ROTATION", "round_robin").lower(),
    }


def is_vpn_feature_enabled() -> bool:
    """Check if VPN auto-switch is enabled."""
    return load_vpn_config()["enabled"]


# ------------------------------------------------------------
# IP CHECK
# ------------------------------------------------------------

def get_current_ip() -> str | None:
    """Get current public IP address."""
    import requests

    for url in IP_CHECK_URLS:
        try:
            response = requests.get(url, timeout=5)
            ip = response.text.strip()
            logger.info("Current IP: %s", ip)
            return ip
        except Exception:
            continue

    logger.warning("Could not determine current IP.")
    return None


def is_ip_blocked(ip: str) -> bool:
    """
    Check if current IP is blocked by LinkedIn.
    Makes a test request and checks for block signals.
    """
    import requests

    try:
        response = requests.get(
            "https://www.linkedin.com",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        content = response.text.lower()

        for signal in BLOCK_SIGNALS:
            if signal in content or str(response.status_code) in signal:
                logger.warning("Block signal detected: '%s' for IP %s", signal, ip)
                return True

        return False

    except Exception as e:
        logger.warning("IP block check failed: %s", e)
        return False


def is_blocked_response(response_text: str) -> bool:
    """Check if a response text indicates a LinkedIn block."""
    text_lower = response_text.lower()
    return any(signal in text_lower for signal in BLOCK_SIGNALS)


# ------------------------------------------------------------
# VPN CONNECT / DISCONNECT
# ------------------------------------------------------------

def connect_vpn(server: str = "") -> bool:
    """
    Connect to a VPN server.

    Args:
        server: Server name or location. If empty, picks next server.

    Returns:
        True if connected successfully.
    """
    config = load_vpn_config()

    if not config["enabled"]:
        logger.info("VPN disabled in .env")
        return False

    if not server:
        server = get_next_server()

    if not server:
        logger.error("No VPN servers configured in .env VPN_SERVERS")
        return False

    client = config["client"]
    logger.info("Connecting to VPN: %s via %s", server, client)

    if client == "nordvpn":
        return _nordvpn_connect(server)
    elif client == "expressvpn":
        return _expressvpn_connect(server)
    elif client == "openvpn":
        return _openvpn_connect(server, config["openvpn_dir"])
    elif client == "custom":
        return _custom_connect(server, config["custom_connect"])

    logger.error("Unknown VPN client: %s", client)
    return False


def disconnect_vpn() -> bool:
    """Disconnect from current VPN."""
    config = load_vpn_config()
    client = config["client"]

    logger.info("Disconnecting VPN (%s)...", client)

    if client == "nordvpn":
        return _run_command(["nordvpn", "disconnect"])
    elif client == "expressvpn":
        return _run_command(["expressvpn", "disconnect"])
    elif client == "openvpn":
        return _run_command(["sudo", "pkill", "openvpn"])
    elif client == "custom":
        cmd = config["custom_disconnect"]
        if cmd:
            return _run_command(cmd.split())

    return False


def is_vpn_connected() -> bool:
    """Check if VPN is currently connected."""
    config = load_vpn_config()
    client = config["client"]

    try:
        if client == "nordvpn":
            result = subprocess.run(
                ["nordvpn", "status"],
                capture_output=True, text=True, timeout=10,
            )
            return "connected" in result.stdout.lower()

        elif client == "expressvpn":
            result = subprocess.run(
                ["expressvpn", "status"],
                capture_output=True, text=True, timeout=10,
            )
            return "connected" in result.stdout.lower()

        elif client == "openvpn":
            result = subprocess.run(
                ["pgrep", "openvpn"],
                capture_output=True, text=True, timeout=5,
            )
            return bool(result.stdout.strip())

    except Exception as e:
        logger.warning("Could not check VPN status: %s", e)

    return False


# ------------------------------------------------------------
# VPN CLIENT IMPLEMENTATIONS
# ------------------------------------------------------------

def _nordvpn_connect(server: str) -> bool:
    """Connect using NordVPN CLI."""
    return _run_command(["nordvpn", "connect", server])


def _expressvpn_connect(server: str) -> bool:
    """Connect using ExpressVPN CLI."""
    return _run_command(["expressvpn", "connect", server])


def _openvpn_connect(server: str, config_dir: str) -> bool:
    """Connect using OpenVPN config file."""
    config_path = Path(config_dir) / f"{server}.ovpn"

    if not config_path.exists():
        logger.error("OpenVPN config not found: %s", config_path)
        return False

    return _run_command(
        ["sudo", "openvpn", "--config", str(config_path), "--daemon"]
    )


def _custom_connect(server: str, command_template: str) -> bool:
    """Connect using custom command."""
    if not command_template:
        logger.error("VPN_CUSTOM_CONNECT not set in .env")
        return False

    cmd = command_template.format(server=server)
    return _run_command(cmd.split())


def _run_command(cmd: list[str], timeout: int = 30) -> bool:
    """Run a system command and return success status."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            logger.info("Command success: %s", " ".join(cmd))
            return True
        else:
            logger.error("Command failed: %s | Error: %s",
                         " ".join(cmd), result.stderr[:100])
            return False
    except subprocess.TimeoutExpired:
        logger.error("Command timed out: %s", " ".join(cmd))
        return False
    except FileNotFoundError:
        logger.error("Command not found: %s", cmd[0])
        return False
    except Exception as e:
        logger.error("Command error: %s | %s", " ".join(cmd), e)
        return False


# ------------------------------------------------------------
# SERVER SELECTION
# ------------------------------------------------------------

_server_index = 0


def get_next_server() -> str | None:
    """Get the next VPN server based on rotation strategy."""
    global _server_index

    config  = load_vpn_config()
    servers = config["servers"]

    if not servers:
        logger.error("No VPN servers in .env VPN_SERVERS")
        return None

    if config["rotation"] == "random":
        server = random.choice(servers)
    else:
        # Round robin
        server = servers[_server_index % len(servers)]
        _server_index += 1

    logger.info("Next VPN server: %s", server)
    return server


# ------------------------------------------------------------
# AUTO SWITCH
# ------------------------------------------------------------

async def auto_switch_vpn(
    reason: str = "manual",
    max_retries: int = 3,
) -> bool:
    """
    Auto-switch to a new VPN server.

    Args:
        reason    : Why switching (block/rate_limit/manual)
        max_retries: Max switch attempts before giving up

    Returns:
        True if successfully switched to a working server.
    """
    if not is_vpn_feature_enabled():
        logger.info("VPN auto-switch disabled.")
        return False

    config  = load_vpn_config()
    servers = config["servers"]

    if not servers:
        logger.error("No VPN servers configured.")
        return False

    old_ip = get_current_ip()
    logger.info("Auto-switching VPN | Reason: %s | Current IP: %s", reason, old_ip)

    # Disconnect current VPN
    disconnect_vpn()
    time.sleep(2)

    for attempt in range(max_retries):
        server = get_next_server()
        if not server:
            break

        logger.info("VPN switch attempt %d/%d -> %s",
                    attempt + 1, max_retries, server)

        success = connect_vpn(server)

        if success:
            time.sleep(3)  # Wait for connection to stabilize
            new_ip = get_current_ip()

            if new_ip and new_ip != old_ip:
                _log_vpn_switch(
                    server=server,
                    old_ip=old_ip or "",
                    new_ip=new_ip,
                    reason=reason,
                    success=True,
                )
                logger.info("VPN switched: %s -> %s (server: %s)",
                            old_ip, new_ip, server)
                return True
            else:
                logger.warning("IP did not change after switch. Retrying...")
                disconnect_vpn()
                time.sleep(2)
        else:
            logger.warning("Failed to connect to %s. Trying next...", server)

    logger.error("VPN auto-switch failed after %d attempts.", max_retries)
    _log_vpn_switch(
        server="none",
        old_ip=old_ip or "",
        new_ip="",
        reason=reason,
        success=False,
    )
    return False


def _log_vpn_switch(
    server: str,
    old_ip: str,
    new_ip: str,
    reason: str,
    success: bool,
):
    """Log a VPN switch to SQLite."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO vpn_switches
            (server, old_ip, new_ip, reason, success, switch_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (server, old_ip, new_ip, reason,
              int(success), date.today().isoformat(),
              datetime.now().isoformat()))
        conn.commit()


# ------------------------------------------------------------
# MONITOR & DETECT BLOCKS
# ------------------------------------------------------------

def check_and_switch_if_blocked() -> bool:
    """
    Check if current IP is blocked and switch VPN if needed.
    Call this before starting browser tasks.

    Returns:
        True if IP is fine or successfully switched.
        False if blocked and switch failed.
    """
    if not is_vpn_feature_enabled():
        return True

    import asyncio

    current_ip = get_current_ip()
    if not current_ip:
        return True

    if is_ip_blocked(current_ip):
        logger.warning("Current IP %s is blocked. Auto-switching VPN...", current_ip)
        return asyncio.run(auto_switch_vpn(reason="ip_blocked"))

    logger.info("IP %s is clean. No VPN switch needed.", current_ip)
    return True


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def get_vpn_status() -> dict:
    """Get current VPN status."""
    config     = load_vpn_config()
    connected  = is_vpn_connected()
    current_ip = get_current_ip()

    return {
        "enabled":   config["enabled"],
        "client":    config["client"],
        "connected": connected,
        "current_ip": current_ip,
        "servers":   config["servers"],
        "rotation":  config["rotation"],
    }


def build_vpn_report() -> str:
    """Build human-readable VPN report."""
    status = get_vpn_status()

    if not DB_FILE.exists():
        switches = []
    else:
        with sqlite3.connect(DB_FILE) as conn:
            rows = conn.execute("""
                SELECT server, old_ip, new_ip, reason, success, switch_date
                FROM   vpn_switches
                ORDER  BY id DESC LIMIT 10
            """).fetchall()
        switches = rows

    lines = [
        "VPN Auto-Switch Report",
        "-" * 50,
        f"  Enabled   : {status['enabled']}",
        f"  Client    : {status['client']}",
        f"  Connected : {status['connected']}",
        f"  Current IP: {status['current_ip'] or 'unknown'}",
        f"  Servers   : {len(status['servers'])} configured",
        "-" * 50,
    ]

    if switches:
        lines.append("\nRecent VPN Switches:")
        for row in switches:
            result = "OK" if row[4] else "FAIL"
            lines.append(
                f"  [{result}] {row[5]} | {row[3]} | "
                f"{row[1]} -> {row[2]} (server: {row[0]})"
            )

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)
