"""
notifications.py
────────────────
Handles Telegram and Email notifications for the Birthday Wishes Agent.

Setup:
  Telegram: Create a bot via @BotFather, get the token and your chat_id.
  Email:    Use a Gmail account with an App Password (not your real password).
            Enable 2FA on Gmail → Settings → App Passwords → Generate one.

Add to your .env file:
  TELEGRAM_BOT_TOKEN=your_bot_token
  TELEGRAM_CHAT_ID=your_chat_id
  EMAIL_SENDER=your_gmail@gmail.com
  EMAIL_PASSWORD=your_app_password
  EMAIL_RECEIVER=receiver@example.com
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from dotenv import dotenv_values

config = dotenv_values(".env")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = config.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = config.get("TELEGRAM_CHAT_ID", "")
EMAIL_SENDER       = config.get("EMAIL_SENDER", "")
EMAIL_PASSWORD     = config.get("EMAIL_PASSWORD", "")
EMAIL_RECEIVER     = config.get("EMAIL_RECEIVER", "")


# ──────────────────────────────────────────────
# TELEGRAM
# ──────────────────────────────────────────────
def send_telegram(message: str) -> bool:
    """Send a message via Telegram bot. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️  Telegram not configured. Skipping notification.")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("📨 Telegram notification sent.")
            return True
        else:
            logger.error("❌ Telegram error: %s", resp.text)
            return False
    except Exception as e:
        logger.error("❌ Telegram exception: %s", e)
        return False


# ──────────────────────────────────────────────
# EMAIL
# ──────────────────────────────────────────────
def send_email(subject: str, body: str) -> bool:
    """Send an email via Gmail SMTP. Returns True on success."""
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
        logger.warning("⚠️  Email not configured. Skipping notification.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = EMAIL_RECEIVER
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

        logger.info("📧 Email notification sent to %s.", EMAIL_RECEIVER)
        return True
    except Exception as e:
        logger.error("❌ Email exception: %s", e)
        return False


# ──────────────────────────────────────────────
# COMBINED SUMMARY NOTIFICATION
# ──────────────────────────────────────────────
def send_summary(
    task_name: str,
    wished: list[str],
    skipped: int,
    dry_run: bool,
) -> None:
    """
    Send a summary notification via both Telegram and Email.

    Args:
        task_name : e.g. "Birthday Detection" or "Reply to Wishes"
        wished    : list of contact names that were wished/replied to
        skipped   : number of threads skipped
        dry_run   : whether this was a dry run
    """
    mode_label = "🧪 DRY RUN" if dry_run else "✅ LIVE"
    count      = len(wished)
    names_str  = ", ".join(wished) if wished else "None"

    message = (
        f"🎂 *Birthday Wishes Agent — {task_name}*\n"
        f"Mode: {mode_label}\n\n"
        f"✅ Sent: {count}\n"
        f"👥 Contacts: {names_str}\n"
        f"⏭️ Skipped: {skipped}\n"
    )

    send_telegram(message)
    send_email(
        subject=f"[Birthday Agent] {task_name} Summary — {count} sent",
        body=message.replace("*", "").replace("_", ""),
    )
