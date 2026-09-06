"""
two_factor_auth.py
------------------
2FA Support for LinkedIn Login - Birthday Wishes Agent.

Handles LinkedIn two-factor authentication automatically.

Supported 2FA methods:
  1. TOTP (Authenticator App) - Google Authenticator, Authy
  2. SMS OTP                  - Code sent to phone
  3. Email OTP                - Code sent to email

How it works:
  1. Agent detects LinkedIn 2FA challenge during login
  2. Calls the appropriate handler based on 2FA type
  3. For TOTP -> generates code from secret key automatically
  4. For SMS/Email OTP -> waits for user input or reads from .env
  5. Submits the code to complete login

.env setup:
  LINKEDIN_2FA_ENABLED=true
  LINKEDIN_2FA_METHOD=totp          # totp / sms / email
  LINKEDIN_TOTP_SECRET=BASE32SECRET # for TOTP (from authenticator app)
  LINKEDIN_OTP_WAIT=30              # seconds to wait for SMS/email OTP

Usage:
    from two_factor_auth import (
        is_2fa_enabled,
        get_totp_code,
        build_2fa_login_task,
        get_2fa_instructions,
    )

    task = build_2fa_login_task(username, password)
"""

import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

def load_2fa_config() -> dict:
    """Load 2FA config from .env."""
    from dotenv import dotenv_values
    config = dotenv_values(".env")

    return {
        "enabled":     config.get("LINKEDIN_2FA_ENABLED", "false").lower() == "true",
        "method":      config.get("LINKEDIN_2FA_METHOD", "totp").lower(),
        "totp_secret": config.get("LINKEDIN_TOTP_SECRET", ""),
        "otp_wait":    int(config.get("LINKEDIN_OTP_WAIT", "30")),
    }


def is_2fa_enabled() -> bool:
    """Check if 2FA is enabled in .env."""
    return load_2fa_config()["enabled"]


# ------------------------------------------------------------
# TOTP (Authenticator App)
# ------------------------------------------------------------

def get_totp_code(secret: str = "") -> str | None:
    """
    Generate current TOTP code from secret key.

    Args:
        secret: Base32 TOTP secret from authenticator app setup.
                If empty, reads from .env LINKEDIN_TOTP_SECRET.

    Returns:
        6-digit TOTP code string, or None on failure.
    """
    if not secret:
        secret = load_2fa_config().get("totp_secret", "")

    if not secret:
        logger.error("LINKEDIN_TOTP_SECRET missing in .env")
        return None

    try:
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        logger.info("TOTP code generated: %s (valid for %ds)",
                    code, 30 - int(time.time()) % 30)
        return code

    except ImportError:
        logger.error("pyotp not installed. Run: pip install pyotp")
        return None
    except Exception as e:
        logger.error("TOTP generation failed: %s", e)
        return None


def get_totp_time_remaining() -> int:
    """Get seconds remaining before current TOTP code expires."""
    return 30 - int(time.time()) % 30


# ------------------------------------------------------------
# LOGIN TASK BUILDERS
# ------------------------------------------------------------

def build_2fa_login_task(
    username: str,
    password: str,
    method: str = "",
) -> str:
    """
    Build a LinkedIn login task string with 2FA handling.

    Args:
        username : LinkedIn email
        password : LinkedIn password
        method   : 2FA method override (totp/sms/email)
                   If empty, reads from .env

    Returns:
        Task string for the browser agent.
    """
    config = load_2fa_config()

    if not method:
        method = config["method"]

    if method == "totp":
        return _build_totp_task(username, password, config)
    elif method == "sms":
        return _build_sms_task(username, password, config)
    elif method == "email":
        return _build_email_task(username, password, config)
    else:
        return _build_generic_2fa_task(username, password)


def _build_totp_task(username: str, password: str, config: dict) -> str:
    """Build login task with automatic TOTP code injection."""
    totp_code = get_totp_code(config.get("totp_secret", ""))

    if totp_code:
        code_instruction = f"""
  If LinkedIn asks for a verification code (2FA):
    - Enter this TOTP code: {totp_code}
    - This code expires in {get_totp_time_remaining()} seconds
    - If it expires, generate a new one (codes refresh every 30s)
    - Click "Verify" or "Submit"
"""
    else:
        code_instruction = """
  If LinkedIn asks for a verification code (2FA):
    - Check your authenticator app for the current code
    - Enter the 6-digit code shown
    - Click "Verify" or "Submit"
"""

    return f"""
Go to https://www.linkedin.com and log in:
  Email    : {username}
  Password : {password}

After entering credentials:
{code_instruction}

  If login succeeds -> continue with the main task.
  If login fails    -> report: LOGIN FAILED: <reason>
"""


def _build_sms_task(username: str, password: str, config: dict) -> str:
    """Build login task with SMS OTP handling."""
    wait_seconds = config.get("otp_wait", 30)

    return f"""
Go to https://www.linkedin.com and log in:
  Email    : {username}
  Password : {password}

If LinkedIn sends an SMS verification code:
  1. Wait up to {wait_seconds} seconds for the SMS
  2. LinkedIn may show an input field for the code
  3. Check the phone number registered with LinkedIn
  4. Enter the 6-digit code received via SMS
  5. Click "Verify" or "Submit"
  6. If code not received -> click "Resend code"

  If login succeeds -> continue with the main task.
  If login fails    -> report: LOGIN FAILED: <reason>
"""


def _build_email_task(username: str, password: str, config: dict) -> str:
    """Build login task with email OTP handling."""
    wait_seconds = config.get("otp_wait", 30)

    return f"""
Go to https://www.linkedin.com and log in:
  Email    : {username}
  Password : {password}

If LinkedIn sends a verification code to your email:
  1. LinkedIn will show a screen asking for the code
  2. Open your email inbox at {username}
  3. Find the LinkedIn verification email (subject: "Your LinkedIn verification code")
  4. Copy the 6-digit code
  5. Enter it in the LinkedIn verification field
  6. Click "Verify" or "Submit"
  7. Wait up to {wait_seconds} seconds for the email to arrive

  If login succeeds -> continue with the main task.
  If login fails    -> report: LOGIN FAILED: <reason>
"""


def _build_generic_2fa_task(username: str, password: str) -> str:
    """Build login task with generic 2FA handling."""
    return f"""
Go to https://www.linkedin.com and log in:
  Email    : {username}
  Password : {password}

If LinkedIn shows a verification/2FA screen:
  1. Check the verification method shown (SMS, email, or authenticator app)
  2. Get the verification code from the appropriate source
  3. Enter the code in the field provided
  4. Click "Verify" or "Submit"
  5. Handle any additional security challenges if shown

  If login succeeds -> continue with the main task.
  If login fails    -> report: LOGIN FAILED: <reason>
"""


# ------------------------------------------------------------
# INSTRUCTIONS HELPER
# ------------------------------------------------------------

def get_2fa_instructions(already_logged_in: bool = False) -> str:
    """
    Get 2FA-aware login instructions for agent tasks.
    Drop-in replacement for the plain login string in agent.py.

    Args:
        already_logged_in: If True, returns skip-login string.

    Returns:
        Login instruction string with 2FA handling.
    """
    if already_logged_in:
        return "You are already logged into LinkedIn. Skip login."

    from dotenv import dotenv_values
    config_raw = dotenv_values(".env")

    username = config_raw.get("USERNAME", "")
    password = config_raw.get("PASSWORD", "")
    config   = load_2fa_config()

    if not config["enabled"]:
        # Standard login without 2FA
        return (
            f"Go to https://linkedin.com and log in:\n"
            f"  Email: {username}\n  Password: {password}\n"
            f"Handle MFA if prompted.\n"
        )

    # 2FA enabled - use full task
    return build_2fa_login_task(username, password, config["method"])


# ------------------------------------------------------------
# TOTP SETUP HELPER
# ------------------------------------------------------------

def generate_totp_setup_instructions() -> str:
    """
    Print instructions for setting up TOTP with LinkedIn.
    Run this once to get your TOTP secret.
    """
    try:
        import pyotp
        secret = pyotp.random_base32()
        totp   = pyotp.TOTP(secret)
        uri    = totp.provisioning_uri(
            name="LinkedIn",
            issuer_name="Birthday-Wishes-Agent",
        )

        return f"""
TOTP Setup Instructions for LinkedIn 2FA
-----------------------------------------

1. Go to LinkedIn Settings -> Sign in & Security -> Two-step verification
2. Choose "Authenticator App"
3. LinkedIn will show a QR code

4. Add this secret to your .env file:
   LINKEDIN_TOTP_SECRET={secret}

5. To scan via QR code, use this URI in any QR generator:
   {uri}

6. Scan the QR code with Google Authenticator or Authy
7. Verify by entering the current code: {totp.now()}

8. Set in .env:
   LINKEDIN_2FA_ENABLED=true
   LINKEDIN_2FA_METHOD=totp
   LINKEDIN_TOTP_SECRET={secret}
"""
    except ImportError:
        return (
            "pyotp not installed. Run: pip install pyotp\n"
            "Then run this function again."
        )


def verify_totp_secret(secret: str) -> bool:
    """Verify a TOTP secret by generating and checking a code."""
    try:
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        valid = totp.verify(code)
        logger.info("TOTP secret valid: %s | Current code: %s", valid, code)
        return valid
    except Exception as e:
        logger.error("TOTP verification failed: %s", e)
        return False


# ------------------------------------------------------------
# STATUS
# ------------------------------------------------------------

def get_2fa_status() -> dict:
    """Get current 2FA configuration status."""
    config = load_2fa_config()

    status = {
        "enabled":       config["enabled"],
        "method":        config["method"],
        "totp_secret":   "SET" if config["totp_secret"] else "NOT SET",
        "otp_wait":      config["otp_wait"],
    }

    if config["method"] == "totp" and config["totp_secret"]:
        code = get_totp_code(config["totp_secret"])
        status["current_totp_code"]    = code or "FAILED"
        status["totp_expires_in_secs"] = get_totp_time_remaining()

    return status
