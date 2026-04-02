"""
auto_reply_followup.py
──────────────────────
Auto Reply to Follow-up module for Birthday Wishes Agent.

When someone replies to a birthday wish or follow-up message,
this module detects the reply and responds with a natural,
AI-generated message to keep the conversation going.

How it works:
  1. Scans LinkedIn/WhatsApp/Instagram/Facebook for replies
     to messages the agent previously sent
  2. Detects if the reply needs a response
  3. Generates a contextual, natural reply using the LLM
  4. Sends the reply

Reply Types:
  - Thank you reply     : "Thanks for wishing me too!"
  - Question reply      : Someone asks "How are you?"
  - Update reply        : "I just got promoted!" → congratulate
  - Emotional reply     : Sad/stressed → caring response
  - Short reply         : "Thanks!" → brief warm acknowledgement

Config in agent.py:
  AUTO_REPLY_FOLLOWUP_ENABLED = True
  MAX_AUTO_REPLIES_PER_DAY    = 20
"""

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_auto_reply_table():
    """Create auto reply tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact       TEXT    NOT NULL,
                platform      TEXT    NOT NULL,
                original_msg  TEXT,
                their_reply   TEXT,
                our_reply     TEXT,
                date          TEXT    NOT NULL,
                dry_run       INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  Auto reply table ready.")


def log_auto_reply(
    contact: str,
    platform: str,
    their_reply: str,
    our_reply: str,
    original_msg: str = "",
    dry_run: bool = True,
):
    """Log an auto reply to the database."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO auto_replies "
            "(contact, platform, original_msg, their_reply, our_reply, date, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (contact, platform, original_msg, their_reply, our_reply,
             date.today().isoformat(), int(dry_run), datetime.now().isoformat()),
        )
        conn.commit()
    logger.info("💬 Auto reply logged: [%s] %s", platform, contact)


def get_auto_replies_today() -> int:
    """Return how many auto replies were sent today."""
    if not DB_FILE.exists():
        return 0
    today = date.today().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM auto_replies WHERE date = ? AND dry_run = 0",
            (today,),
        ).fetchone()[0]
    return count


def already_replied(contact: str, their_reply: str) -> bool:
    """Check if we already replied to this exact message."""
    if not DB_FILE.exists():
        return False
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT id FROM auto_replies "
            "WHERE LOWER(contact) = LOWER(?) AND their_reply = ? AND dry_run = 0",
            (contact, their_reply[:200]),
        ).fetchone()
    return row is not None


# ──────────────────────────────────────────────
# REPLY GENERATOR
# ──────────────────────────────────────────────
async def generate_followup_reply(
    llm,
    contact: str,
    their_reply: str,
    original_message: str = "",
    relationship: str = "acquaintance",
) -> str:
    """
    Generate a natural reply to someone's response.

    Args:
        llm              : LangChain LLM instance
        contact          : Contact's first name
        their_reply      : What they said in response
        original_message : What we sent them originally
        relationship     : "close_friend", "colleague", "acquaintance"

    Returns:
        Generated reply string.
    """
    from langchain_core.messages import HumanMessage

    prompt = f"""
You are replying to a message on LinkedIn on behalf of the user.

Context:
  Contact name : {contact}
  Relationship : {relationship}
  We sent      : "{original_message or 'a birthday wish or follow-up message'}"
  They replied : "{their_reply}"

Write a SHORT, natural reply (1-2 sentences max) that:
  ✅ Feels warm and genuine
  ✅ Matches the relationship tone:
     - close_friend  → casual and friendly
     - colleague     → professional but warm
     - acquaintance  → polite and brief
  ✅ Responds naturally to what they said:
     - If they said "thanks" → acknowledge briefly
     - If they asked a question → answer it naturally
     - If they shared good news → congratulate them
     - If they seem sad/stressed → be extra caring
     - If it's just a short reply → keep your reply equally short
  ❌ Do NOT be overly formal or robotic
  ❌ Do NOT be longer than 2 sentences
  ❌ Do NOT start with "I" — vary the opening

Reply with ONLY the message text. No quotes, no explanation.
"""
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        reply = response.content.strip().strip('"').strip("'")
        logger.info("💬 Auto reply generated for %s: %s", contact, reply[:60] + "...")
        return reply
    except Exception as e:
        logger.error("❌ Auto reply generation failed: %s", e)
        return f"That means a lot, {contact}! 😊 Hope you're having a great day!"


# ──────────────────────────────────────────────
# BROWSER TASK BUILDER
# ──────────────────────────────────────────────
def build_auto_reply_task(
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool,
    max_replies: int = 20,
    platforms: list[str] = None,
) -> str:
    """
    Build a browser agent task to find and reply to
    responses to our birthday wishes and follow-ups.
    """
    replies_today = get_auto_replies_today()
    remaining     = max_replies - replies_today

    if remaining <= 0:
        logger.info("📊 Daily auto reply limit reached (%d).", max_replies)
        return ""

    if platforms is None:
        platforms = ["linkedin"]

    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any replies.
  For each reply you WOULD send, print:
    [DRY RUN] Would reply to <n>: "<message>"
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

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice}

  GOAL: Find replies to birthday wishes and follow-up messages
  that we sent previously, and respond to them naturally.

  STEP 1 — Go to LinkedIn Messaging.
    Visit https://www.linkedin.com/messaging/
    Look for conversations where:
    a) WE sent the last message (birthday wish or follow-up)
    b) THEY replied AFTER our message
    c) We have NOT yet replied to their reply

  STEP 2 — For each unresponded reply (up to {remaining}):

    a) Read their reply carefully.
    b) Check the context — what did we originally send them?
    c) Assess the tone of their reply:
       - Simple thank you → brief warm acknowledgement
       - Question ("How are you?") → answer naturally
       - Good news (promotion, new job) → congratulate warmly
       - Sad/stressed tone → be extra caring and supportive
       - Short reply ("Thanks!") → equally short response

    d) Write a SHORT, natural reply (1-2 sentences):
       - Match their energy and tone
       - Keep it conversational
       - Do NOT start every reply the same way

    e) Send the reply (or log if DRY RUN).

  STEP 3 — Stop after {remaining} replies.

  RULES:
    ✅ Only reply to messages that were replies to OUR messages
    ✅ Keep replies short and natural
    ❌ Do NOT reply to cold messages or spam
    ❌ Do NOT reply if we already responded in this thread today
    ❌ Do NOT send more than {remaining} replies today

  At the end, provide a summary:
    - Replied to: (names + their message + our reply)
    - Skipped: (count + reason)
"""


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_auto_reply_followup(
    llm,
    browser,
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool,
    max_replies: int = 20,
) -> str:
    """
    Scan for replies to our messages and respond automatically.

    Returns:
        Agent result string.
    """
    from browser_use import Agent

    task = build_auto_reply_task(
        username=username,
        password=password,
        already_logged_in=already_logged_in,
        dry_run=dry_run,
        max_replies=max_replies,
    )

    if not task:
        logger.info("📭 No auto replies to send.")
        return "No auto replies performed."

    logger.info(
        "=== Auto Reply to Follow-up === [DRY RUN: %s]", dry_run
    )

    agent  = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("Auto Reply Result: %s", result)
    return str(result)