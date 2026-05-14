"""
dm_campaign.py
──────────────
LinkedIn DM Campaign module for Birthday Wishes Agent.

Runs automated, personalized icebreaker campaigns for new
LinkedIn connections — beyond just birthday wishes.

Campaign Types:
  - welcome      : Welcome message to new connections
  - icebreaker   : Start a conversation based on shared interests
  - reconnect    : Re-engage with fading connections
  - value_share  : Share a useful resource or insight
  - coffee_chat  : Suggest a virtual coffee chat

Features:
  - Fully personalized messages based on profile
  - Daily send limit to avoid spam flags
  - Cooldown period between messages to same person
  - Campaign tracking in SQLite
  - A/B testing support (two message variants)

Config in agent.py:
  DM_CAMPAIGN_ENABLED    = True
  CAMPAIGN_TYPE          = "welcome"
  MAX_DM_PER_DAY         = 10
  DM_COOLDOWN_DAYS       = 60
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

logger  = logging.getLogger(__name__)
DB_FILE = Path("agent_history.db")


# ──────────────────────────────────────────────
# DB SETUP
# ──────────────────────────────────────────────
def init_campaign_table():
    """Create the DM campaign tracking table."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_campaigns (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                contact       TEXT    NOT NULL,
                campaign_type TEXT    NOT NULL,
                message_sent  TEXT,
                variant       TEXT    DEFAULT 'A',
                replied       INTEGER DEFAULT 0,
                date          TEXT    NOT NULL,
                dry_run       INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.info("🗄️  DM campaign table ready.")


def log_campaign_dm(
    contact: str,
    campaign_type: str,
    message_sent: str,
    variant: str = "A",
    dry_run: bool = True,
):
    """Log a sent campaign DM."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO dm_campaigns "
            "(contact, campaign_type, message_sent, variant, date, dry_run, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (contact, campaign_type, message_sent, variant,
             date.today().isoformat(), int(dry_run),
             datetime.now().isoformat()),
        )
        conn.commit()
    logger.info("📨 Campaign DM logged: [%s] → %s", campaign_type, contact)


def get_campaign_dms_today() -> int:
    """Return how many campaign DMs were sent today."""
    if not DB_FILE.exists():
        return 0
    today = date.today().isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM dm_campaigns WHERE date = ? AND dry_run = 0",
            (today,),
        ).fetchone()[0]
    return count


def already_in_campaign(contact: str, cooldown_days: int = 60) -> bool:
    """Check if contact was already messaged within cooldown period."""
    if not DB_FILE.exists():
        return False
    cutoff = (date.today() - timedelta(days=cooldown_days)).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT id FROM dm_campaigns "
            "WHERE LOWER(contact) = LOWER(?) AND date >= ? AND dry_run = 0",
            (contact, cutoff),
        ).fetchone()
    return row is not None


def get_campaign_stats() -> dict:
    """Get overall campaign statistics."""
    if not DB_FILE.exists():
        return {}
    with sqlite3.connect(DB_FILE) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM dm_campaigns WHERE dry_run = 0"
        ).fetchone()[0]
        replied = conn.execute(
            "SELECT COUNT(*) FROM dm_campaigns WHERE replied = 1 AND dry_run = 0"
        ).fetchone()[0]
        by_type = conn.execute(
            "SELECT campaign_type, COUNT(*) FROM dm_campaigns "
            "WHERE dry_run = 0 GROUP BY campaign_type"
        ).fetchall()
    reply_rate = round((replied / total * 100), 1) if total > 0 else 0
    return {
        "total_sent":  total,
        "total_replied": replied,
        "reply_rate":  reply_rate,
        "by_type":     {r[0]: r[1] for r in by_type},
    }


# ──────────────────────────────────────────────
# MESSAGE TEMPLATES
# ──────────────────────────────────────────────
CAMPAIGN_TEMPLATES = {
    "welcome": {
        "description": "Welcome new connections warmly",
        "variants": {
            "A": (
                "Hi {name}! 👋 Thanks for connecting — really glad to have you in my network! "
                "I noticed you work in {industry} — would love to stay in touch and "
                "see what you're working on. Feel free to reach out anytime! 😊"
            ),
            "B": (
                "Hey {name}! Great to connect with you 🙌 "
                "I see you're at {company} — fascinating work! "
                "Looking forward to learning from each other. "
                "Don't hesitate to drop a message anytime!"
            ),
        },
    },
    "icebreaker": {
        "description": "Start a conversation based on shared interests",
        "variants": {
            "A": (
                "Hi {name}! I came across your profile and noticed we both have an interest "
                "in {interest} 🎯 I've been exploring this space a lot lately — "
                "would love to hear your perspective on it sometime!"
            ),
            "B": (
                "Hey {name}! Your recent post about {topic} really resonated with me 💡 "
                "I've been thinking about the same thing from a different angle. "
                "Would be great to exchange thoughts — what do you think?"
            ),
        },
    },
    "reconnect": {
        "description": "Re-engage with fading connections",
        "variants": {
            "A": (
                "Hi {name}! It's been a while since we connected — hope you're doing well! 😊 "
                "I saw your recent update about {recent_activity} and it caught my attention. "
                "Would love to catch up sometime!"
            ),
            "B": (
                "Hey {name}! Just thinking about some of the great people in my network "
                "and wanted to reach out 👋 Hope things are going well on your end! "
                "What have you been up to lately?"
            ),
        },
    },
    "value_share": {
        "description": "Share a useful insight or resource",
        "variants": {
            "A": (
                "Hi {name}! I came across something I thought might be relevant to your work "
                "in {industry} 💡 {resource_or_insight} — thought you might find it valuable! "
                "Would love to hear your thoughts if you get a chance to check it out."
            ),
            "B": (
                "Hey {name}! Given your background in {field}, I think you'd find this "
                "interesting: {insight} 🎯 "
                "Always good to connect with thoughtful people in this space!"
            ),
        },
    },
    "coffee_chat": {
        "description": "Suggest a virtual coffee chat",
        "variants": {
            "A": (
                "Hi {name}! I've been really impressed by your work in {field} and would love "
                "to learn more about your experience ☕ "
                "Would you be open to a quick 15-min virtual coffee chat sometime? "
                "No agenda — just a friendly conversation!"
            ),
            "B": (
                "Hey {name}! Your journey from {background} to {current_role} is really inspiring 🌟 "
                "I'd love to hear more about it over a quick virtual coffee if you're open to it? "
                "Happy to work around your schedule!"
            ),
        },
    },
}


# ──────────────────────────────────────────────
# BROWSER TASK BUILDER
# ──────────────────────────────────────────────
def build_campaign_task(
    campaign_type: str,
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool,
    max_dms: int = 10,
    cooldown_days: int = 60,
    variant: str = "A",
) -> str:
    """
    Build a browser agent task to run a DM campaign
    on LinkedIn for new or existing connections.
    """
    dms_today = get_campaign_dms_today()
    remaining = max_dms - dms_today

    if remaining <= 0:
        logger.info("📊 Daily DM limit reached (%d).", max_dms)
        return ""

    campaign = CAMPAIGN_TEMPLATES.get(
        campaign_type, CAMPAIGN_TEMPLATES["welcome"]
    )
    description   = campaign["description"]
    template_a    = campaign["variants"]["A"]
    template_b    = campaign["variants"]["B"]
    chosen_template = campaign["variants"].get(variant, template_a)

    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT actually send any messages.
  For each DM you WOULD send, print:
    [DRY RUN] Would send to <n>: "<message>"
  Then move on.
""" if dry_run else ""

    login_instructions = (
        "You are already logged into LinkedIn. Skip the login step."
        if already_logged_in
        else (
            f"Go to https://linkedin.com and log in with:\n"
            f"  Email:    {username}\n"
            f"  Password: {password}\n"
        )
    )

    source_instructions = {
        "welcome": """
    Go to https://www.linkedin.com/mynetwork/
    Click "Connections" → sort by "Recently Added"
    Target the most recent connections (added in last 7 days)
    who you have NOT yet messaged.
""",
        "icebreaker": """
    Go to your LinkedIn feed or search for people in your network.
    Look for connections who have recently posted about topics
    relevant to your industry or interests.
    Target people you haven't connected with deeply yet.
""",
        "reconnect": """
    Go to https://www.linkedin.com/mynetwork/
    Look for connections you haven't interacted with in 6+ months.
    Focus on people who were once active but seem to have gone quiet.
""",
        "value_share": """
    Go to https://www.linkedin.com/mynetwork/
    Find connections who work in industries where your insight would be valuable.
    Target people in relevant fields who you want to start a conversation with.
""",
        "coffee_chat": """
    Go to https://www.linkedin.com/mynetwork/
    Find connections whose career journey or expertise you genuinely admire.
    Target people whose work you've been following and want to learn from.
""",
    }

    source = source_instructions.get(campaign_type, source_instructions["welcome"])

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice}

  CAMPAIGN TYPE: {campaign_type.upper()} — {description}

  GOAL: Send personalized, genuine DMs to LinkedIn connections
  as part of a {campaign_type} campaign.

  STEP 1 — Find target contacts:
{source}

  STEP 2 — For each target contact (up to {remaining}):

    a) Check: have they been messaged in the last {cooldown_days} days?
       If yes → skip.

    b) Visit their profile and note:
       - First name
       - Current job title and company
       - Industry
       - Recent post topic (if any)
       - Shared interests or skills

    c) Personalize this message template by filling in the details:
       "{chosen_template}"

       Replace placeholders naturally:
       {{name}}             → their first name
       {{company}}          → their current company
       {{industry}}         → their industry
       {{interest}}         → a shared interest
       {{topic}}            → topic of their recent post
       {{recent_activity}}  → something recent on their profile
       {{field}}            → their professional field
       {{background}}       → their background
       {{current_role}}     → their current role
       {{resource_or_insight}} → a relevant insight (make it up naturally)

    d) Send the personalized DM (or log if DRY RUN).

  STEP 3 — Stop after {remaining} DMs today.

  RULES:
    ✅ Every message must feel personal and genuine
    ✅ Reference something specific from their profile
    ❌ Never send copy-paste messages without personalization
    ❌ Never pitch products or services
    ❌ Never message the same person twice within {cooldown_days} days
    ❌ Stop after {remaining} messages today

  Summary at the end:
    - Sent to: (names + personalized messages)
    - Skipped: (count + reason)
    - Total today: X/{max_dms}
"""


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_dm_campaign(
    llm,
    browser,
    campaign_type: str,
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool,
    max_dms: int = 10,
    cooldown_days: int = 60,
    variant: str = "A",
) -> str:
    """
    Run a LinkedIn DM campaign.

    Args:
        llm               : LangChain LLM instance
        browser           : browser_use Browser instance
        campaign_type     : "welcome", "icebreaker", "reconnect",
                            "value_share", or "coffee_chat"
        username          : LinkedIn email
        password          : LinkedIn password
        already_logged_in : Whether session is valid
        dry_run           : Simulate or actually send
        max_dms           : Daily send limit
        cooldown_days     : Days before re-messaging same person
        variant           : "A" or "B" for A/B testing

    Returns:
        Agent result string.
    """
    from browser_use import Agent

    task = build_campaign_task(
        campaign_type=campaign_type,
        username=username,
        password=password,
        already_logged_in=already_logged_in,
        dry_run=dry_run,
        max_dms=max_dms,
        cooldown_days=cooldown_days,
        variant=variant,
    )

    if not task:
        logger.info("📭 No DMs to send — limit reached or no targets.")
        return "No DMs sent."

    logger.info(
        "=== LinkedIn DM Campaign: %s === [DRY RUN: %s | Variant: %s]",
        campaign_type.upper(), dry_run, variant,
    )

    agent  = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("DM Campaign Result: %s", result)
    return str(result)