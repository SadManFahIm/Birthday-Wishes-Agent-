"""
auto_connect.py
───────────────
Auto LinkedIn Connect module for Birthday Wishes Agent.

Uses birthday wishes as a natural opportunity to grow
your LinkedIn network by sending connection requests to
2nd-degree connections who wished you.

Strategy:
  1. When someone wishes you happy birthday → check if you're connected
  2. If NOT connected (2nd degree) → send a personalized connection request
  3. If already connected (1st degree) → just reply as normal
  4. Smart filtering — only connect with relevant profiles

Connection Request Templates:
  - Personalized, references the birthday wish
  - Feels natural, not spammy
  - Short and warm (LinkedIn limit: 300 characters)

Config:
  AUTO_CONNECT_ENABLED = True/False
  MAX_CONNECTS_PER_DAY = 10  (LinkedIn daily limit safety)
"""

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_FILE = Path("agent_history.db")
MAX_CONNECTS_PER_DAY = 10


# ──────────────────────────────────────────────
# CONNECTION REQUEST TEMPLATES
# ──────────────────────────────────────────────
CONNECTION_TEMPLATES = {
    "from_birthday_wish": [
        "Hi {name}! Thank you so much for the birthday wish — really made my day! "
        "Would love to connect and stay in touch 😊",

        "Hey {name}! Your birthday message was so kind, thank you! "
        "I'd love to add you to my network — looking forward to connecting!",

        "Hi {name}! Thanks for taking the time to wish me — truly appreciated! "
        "Would be great to connect properly here on LinkedIn 🙏",
    ],
    "from_birthday_wish_colleague": [
        "Hi {name}! Thank you for the birthday wishes! "
        "It's always great to connect with fellow professionals. "
        "Looking forward to staying in touch!",

        "Hey {name}! Really appreciate the birthday message. "
        "Would love to connect and explore potential collaboration. "
        "Hope to stay in touch!",
    ],
    "from_birthday_wish_mutual": [
        "Hi {name}! Thanks so much for the birthday wish — means a lot! "
        "I see we have mutual connections — would love to connect properly 😊",
    ],
}


# ──────────────────────────────────────────────
# DB HELPERS
# ──────────────────────────────────────────────
def init_connections_table():
    """Create the connections tracking table if it doesn't exist."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connection_requests (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                contact      TEXT    NOT NULL,
                profile_url  TEXT,
                message_sent TEXT,
                status       TEXT    NOT NULL DEFAULT 'sent',
                date         TEXT    NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  Connection requests table ready.")


def get_connects_today() -> int:
    """Return how many connection requests were sent today."""
    if not DB_FILE.exists():
        return 0
    today = date.today().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM connection_requests WHERE date = ?",
            (today,),
        ).fetchone()[0]
    return count


def log_connection_request(contact: str, profile_url: str, message: str):
    """Save a sent connection request to the database."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO connection_requests "
            "(contact, profile_url, message_sent, status, date, created_at) "
            "VALUES (?, ?, ?, 'sent', ?, ?)",
            (contact, profile_url, message,
             date.today().isoformat(), datetime.now().isoformat()),
        )
        conn.commit()
    logger.info("🤝 Connection request logged: %s", contact)


def already_requested(contact: str) -> bool:
    """Check if we already sent a connection request to this person."""
    if not DB_FILE.exists():
        return False
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT id FROM connection_requests WHERE contact = ?",
            (contact,),
        ).fetchone()
    return row is not None


# ──────────────────────────────────────────────
# BROWSER AGENT INSTRUCTIONS
# ──────────────────────────────────────────────
def build_auto_connect_instructions(
    connects_today: int,
    max_per_day: int = MAX_CONNECTS_PER_DAY,
) -> str:
    """
    Build instructions for the browser agent to send
    connection requests to non-connected wishers.
    """
    remaining = max_per_day - connects_today

    if remaining <= 0:
        return f"""
  AUTO-CONNECT: Daily limit reached ({max_per_day} requests sent today).
  Do NOT send any more connection requests today.
"""

    return f"""
  AUTO-CONNECT INSTRUCTIONS:
  After replying to a birthday wish, check if you are already
  connected with this person on LinkedIn.

  HOW TO CHECK:
    - If their profile shows "1st" → already connected → skip
    - If their profile shows "2nd" or "3rd" → NOT connected → send request
    - If there's a "Connect" button → NOT connected → send request
    - If there's a "Message" button only → already connected → skip

  IF NOT CONNECTED (and daily limit not reached):
    1. Click "Connect" on their profile
    2. Select "Add a note"
    3. Write a SHORT, warm connection note (max 300 characters):

       Template options (pick the most natural one):
       a) "Hi [name]! Thank you so much for the birthday wish — really made my day! Would love to connect and stay in touch 😊"
       b) "Hey [name]! Your birthday message was so kind, thank you! I'd love to add you to my network!"
       c) "Hi [name]! Thanks for the birthday wishes! Would be great to connect properly here on LinkedIn 🙏"

    4. Click Send

  DAILY LIMIT: You can send {remaining} more connection request(s) today.
  Once the limit is reached → stop sending requests for today.

  RULES:
    ❌ Do NOT connect with accounts that look like spam or bots
    ❌ Do NOT connect if the profile seems inactive (no photo, no posts)
    ✅ Only connect with real people who sent genuine birthday wishes
    ✅ Always add a personalized note — never send a blank request
"""


# ──────────────────────────────────────────────
# MAIN TASK BUILDER
# ──────────────────────────────────────────────
def build_auto_connect_task(
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool,
) -> str:
    """
    Build a browser agent task to find 2nd-degree wishers
    and send them personalized connection requests.
    """
    connects_today = get_connects_today()
    remaining      = MAX_CONNECTS_PER_DAY - connects_today

    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any connection requests.
  For each request you WOULD send, print:
    [DRY RUN] Would connect with <n>: "<message>"
  Then move on.
""" if dry_run else ""

    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {username}\n"
            f"  Password: {password}\n"
            "Handle MFA if prompted.\n"
        )
    )

    if remaining <= 0:
        return ""

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice}

  GOAL: Find people who wished you happy birthday but are NOT yet
  connected with you, and send them a warm connection request.

  STEP 1 — Go to https://www.linkedin.com/messaging/
    Look for recent birthday wish messages (from today or yesterday).

  STEP 2 — For each person who sent a birthday wish:
    a) Visit their LinkedIn profile.
    b) Check their connection degree:
       - "1st" → already connected → skip
       - "2nd" or "Connect" button → send request

    c) If NOT connected AND profile looks genuine:
       - Click "Connect"
       - Add a personalized note (max 300 characters):
         "Hi [first name]! Thank you so much for the birthday wish —
          really made my day! Would love to connect and stay in touch 😊"
       - Click Send

  STEP 3 — Stop after sending {remaining} request(s) today.

  At the end, provide a summary:
    - Connected with: (names + messages sent)
    - Skipped: (reason — already connected, spam, limit reached)
"""