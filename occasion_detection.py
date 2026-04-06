"""
occasion_detection.py
─────────────────────
Occasion Detection module for Birthday Wishes Agent.

Detects life events and milestones beyond birthdays and
automatically sends congratulatory messages.

Detected Occasions:
  - Work anniversary  : "X years at Company"
  - New job           : "Excited to start at...", "I'm joining..."
  - Promotion         : "Promoted to...", "New role as..."
  - Work anniversary  : LinkedIn "X years" notifications
  - Graduation        : "Graduated from...", "Just got my degree"
  - Engagement        : "I'm engaged!", "She said yes!"
  - Marriage          : "Just got married", "Wedding day"
  - New baby          : "We're expecting", "Baby arrived"
  - Achievement       : Award, certification, milestone post

Usage:
    from occasion_detection import detect_occasion, build_occasion_task
"""

import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# OCCASION DEFINITIONS
# ──────────────────────────────────────────────
OCCASIONS = {
    "work_anniversary": {
        "signals": [
            "work anniversary", "years at", "years with", "years in",
            "celebrating my", "anniversary at", "joined X years ago",
            "X year anniversary",
        ],
        "emoji":       "🎊",
        "message_style": "Professional and warm, acknowledge their loyalty and dedication.",
    },
    "new_job": {
        "signals": [
            "excited to join", "excited to start", "i'm joining",
            "starting my new role", "new position at", "just joined",
            "thrilled to announce", "happy to share that i'll be",
            "new chapter", "new opportunity at",
        ],
        "emoji":       "🚀",
        "message_style": "Enthusiastic and encouraging, wish them success in the new role.",
    },
    "promotion": {
        "signals": [
            "promoted to", "new role as", "stepping up as",
            "i've been promoted", "excited to share my promotion",
            "new title", "taking on the role of", "officially a",
            "moving into", "level up",
        ],
        "emoji":       "⭐",
        "message_style": "Celebratory and proud, acknowledge their hard work.",
    },
    "graduation": {
        "signals": [
            "graduated", "graduation", "just got my degree",
            "completed my", "finished my", "master's degree",
            "bachelor's degree", "phd", "convocation", "commencement",
        ],
        "emoji":       "🎓",
        "message_style": "Proud and encouraging, celebrate their achievement.",
    },
    "engagement": {
        "signals": [
            "i'm engaged", "she said yes", "he said yes",
            "we're engaged", "just got engaged", "popped the question",
            "will you marry me", "engagement",
        ],
        "emoji":       "💍",
        "message_style": "Warm and joyful, wish them happiness together.",
    },
    "marriage": {
        "signals": [
            "just got married", "wedding day", "we tied the knot",
            "happily married", "my wedding", "got hitched",
            "mr and mrs", "husband and wife",
        ],
        "emoji":       "💒",
        "message_style": "Joyful and heartfelt, wish them a lifetime of happiness.",
    },
    "new_baby": {
        "signals": [
            "we're expecting", "baby on the way", "baby arrived",
            "new baby", "newborn", "it's a boy", "it's a girl",
            "welcomed our", "proud parents", "maternity", "paternity",
        ],
        "emoji":       "👶",
        "message_style": "Warm and caring, congratulate on the new addition.",
    },
    "achievement": {
        "signals": [
            "award", "certification", "certified", "won the",
            "recognized as", "honored to", "milestone",
            "achievement", "accomplished", "record", "featured in",
        ],
        "emoji":       "🏆",
        "message_style": "Impressed and congratulatory, acknowledge the specific achievement.",
    },
}


# ──────────────────────────────────────────────
# CONGRATULATION TEMPLATES
# ──────────────────────────────────────────────
CONGRATS_TEMPLATES = {
    "work_anniversary": [
        "Congratulations on your work anniversary, {name}! 🎊 "
        "{years_detail}What an incredible journey — your dedication is truly inspiring!",
        "Happy work anniversary {name}! 🎊 "
        "Your commitment and hard work over the years is something to be really proud of!",
    ],
    "new_job": [
        "Congratulations on the new role, {name}! 🚀 "
        "How exciting — wishing you all the best as you start this new chapter!",
        "How exciting {name}! 🚀 Congratulations on joining the new team — "
        "can't wait to see all the amazing things you'll accomplish there!",
    ],
    "promotion": [
        "Congratulations on your promotion, {name}! ⭐ "
        "This is so well deserved — your hard work and talent have truly paid off!",
        "Well deserved, {name}! ⭐ Congratulations on the promotion — "
        "excited to see you thrive in this new role!",
    ],
    "graduation": [
        "Congratulations on graduating, {name}! 🎓 "
        "What an incredible achievement — wishing you all the best in the next chapter!",
        "So proud of you {name}! 🎓 Congratulations on your graduation — "
        "all your hard work has paid off. The future is bright!",
    ],
    "engagement": [
        "Congratulations on your engagement, {name}! 💍 "
        "Such wonderful news — wishing you both a lifetime of love and happiness!",
        "How wonderful {name}! 💍 Congratulations on your engagement — "
        "so happy for you both!",
    ],
    "marriage": [
        "Congratulations on your wedding, {name}! 💒 "
        "Wishing you both a lifetime of love, laughter, and happiness together!",
        "How beautiful {name}! 💒 Congratulations on your special day — "
        "wishing you both all the joy in the world!",
    ],
    "new_baby": [
        "Congratulations on the new arrival, {name}! 👶 "
        "Such wonderful news — wishing your growing family all the best!",
        "How exciting {name}! 👶 Congratulations on the new baby — "
        "wishing your family lots of love and joy!",
    ],
    "achievement": [
        "Congratulations on this incredible achievement, {name}! 🏆 "
        "Your hard work and dedication are truly inspiring — well done!",
        "So impressive {name}! 🏆 Congratulations on this well-deserved recognition — "
        "you should be really proud!",
    ],
}


# ──────────────────────────────────────────────
# FAST RULE-BASED DETECTION
# ──────────────────────────────────────────────
def quick_occasion_detect(text: str) -> str | None:
    """Fast rule-based occasion detection."""
    text_lower = text.lower()
    for occasion, data in OCCASIONS.items():
        if any(signal in text_lower for signal in data["signals"]):
            logger.info("⚡ Quick occasion detection: %s", occasion)
            return occasion
    return None


# ──────────────────────────────────────────────
# LLM-BASED OCCASION DETECTION
# ──────────────────────────────────────────────
async def detect_occasion(llm, post_or_message: str) -> dict:
    """
    Detect if a LinkedIn post or message announces a life event.

    Args:
        llm              : LangChain LLM instance
        post_or_message  : The post or message text

    Returns:
        Dict with occasion, confidence, detail, should_congratulate
    """
    # Try fast detection first
    quick = quick_occasion_detect(post_or_message)
    if quick:
        return {
            "occasion":            quick,
            "confidence":          0.85,
            "detail":              "",
            "should_congratulate": True,
        }

    prompt = f"""
Analyze this LinkedIn post or message and detect if it announces a life event or milestone.

Text: "{post_or_message}"

Possible occasions:
  - work_anniversary : celebrating years at a company
  - new_job          : starting a new job or position
  - promotion        : getting promoted to a new role
  - graduation       : completing a degree or course
  - engagement       : getting engaged
  - marriage         : getting married
  - new_baby         : expecting or having a baby
  - achievement      : award, certification, or major milestone
  - none             : no special occasion detected

Return ONLY a JSON object:
{{
  "occasion": "new_job",
  "confidence": 0.95,
  "detail": "joining Google as Senior Engineer",
  "should_congratulate": true
}}

If no occasion → return {{"occasion": "none", "confidence": 1.0, "detail": "", "should_congratulate": false}}
No extra text. JSON only.
"""
    try:
        import json
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text     = response.content.strip().replace("```json", "").replace("```", "").strip()
        result   = json.loads(text)
        logger.info(
            "🎯 Occasion detected: %s (%.0f%% confidence) — %s",
            result.get("occasion"), result.get("confidence", 0) * 100,
            result.get("detail", ""),
        )
        return result
    except Exception as e:
        logger.warning("⚠️  Occasion detection failed: %s", e)
        return {"occasion": "none", "confidence": 0, "detail": "",
                "should_congratulate": False}


# ──────────────────────────────────────────────
# GET CONGRATULATION MESSAGE
# ──────────────────────────────────────────────
def get_congrats_message(
    name: str,
    occasion: str,
    detail: str = "",
    index: int = 0,
) -> str:
    """
    Get a congratulations message for a detected occasion.

    Args:
        name     : Contact's first name
        occasion : Detected occasion type
        detail   : Specific detail (e.g. "joining Google")
        index    : Which template to use (0 or 1)

    Returns:
        Formatted congratulations message.
    """
    templates = CONGRATS_TEMPLATES.get(occasion, [])
    if not templates:
        return f"Congratulations on this exciting news, {name}! 🎊 Wishing you all the best!"

    template     = templates[index % len(templates)]
    years_detail = f"({detail}) " if detail else ""
    message      = template.replace("{name}", name).replace("{years_detail}", years_detail)

    logger.info("🎊 Congrats message for %s (%s): %s", name, occasion, message[:60] + "...")
    return message


# ──────────────────────────────────────────────
# BROWSER TASK BUILDER
# ──────────────────────────────────────────────
def build_occasion_task(
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool,
) -> str:
    """
    Build a browser agent task to scan LinkedIn feed for
    life event posts and send congratulations.
    """
    dry_run_notice = """
  ⚠️  DRY RUN MODE IS ON ⚠️
  Do NOT send any messages.
  For each message you WOULD send, print:
    [DRY RUN] Would congratulate <n> for <occasion>: "<message>"
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

    occasions_list = "\n".join(
        f"  - {k.replace('_', ' ').title()} {v['emoji']}: {', '.join(v['signals'][:3])}"
        for k, v in OCCASIONS.items()
    )

    return f"""
  Open the browser.
  {login_instructions}
  {dry_run_notice}

  GOAL: Scan LinkedIn feed and notifications for life event announcements
  from your connections, then send them a congratulatory message.

  STEP 1 — Check LinkedIn notifications.
    Click the bell 🔔 icon.
    Look for notifications like:
    - "X is celebrating a work anniversary"
    - "X started a new position"
    - "Congratulate X on their promotion"

  STEP 2 — Scan LinkedIn feed (first 20 posts).
    Look for posts announcing these occasions:
{occasions_list}

  STEP 3 — For each detected occasion:
    a) Extract the person's first name.
    b) Note the specific occasion and any details
       (e.g. "joining Google as Senior Engineer").
    c) Send a warm, personalized congratulatory DM:

       work_anniversary → "Congratulations on your work anniversary [name]! 🎊
                           Your dedication is truly inspiring!"
       new_job          → "Congratulations on the new role [name]! 🚀
                           Wishing you all the best in this exciting chapter!"
       promotion        → "Congratulations on your promotion [name]! ⭐
                           So well deserved — your hard work paid off!"
       graduation       → "Congratulations on graduating [name]! 🎓
                           What an incredible achievement!"
       achievement      → "Congratulations on this amazing achievement [name]! 🏆
                           Your hard work is truly inspiring!"

    d) Also LIKE and COMMENT on their post if applicable.

  STEP 4 — Stop after 10 congratulations today.

  RULES:
    ✅ Only congratulate genuine life events
    ✅ Keep messages warm, specific, and genuine
    ❌ Do NOT congratulate the same person twice today
    ❌ Do NOT send generic copy-paste messages

  Summary at the end:
    | Name | Occasion | Message Sent |
    |------|----------|-------------|
"""


# ──────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────
async def run_occasion_detection(
    llm,
    browser,
    username: str,
    password: str,
    already_logged_in: bool,
    dry_run: bool,
) -> str:
    """
    Scan LinkedIn for life events and send congratulations.
    """
    from browser_use import Agent

    task = build_occasion_task(
        username=username,
        password=password,
        already_logged_in=already_logged_in,
        dry_run=dry_run,
    )

    logger.info("=== Occasion Detection === [DRY RUN: %s]", dry_run)
    agent  = Agent(task=task, llm=llm, browser=browser)
    result = await agent.run()
    logger.info("Occasion Detection Result: %s", result)
    return str(result)