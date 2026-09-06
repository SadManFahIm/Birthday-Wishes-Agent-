"""
Wish Templates — Birthday Wishes Agent v10.0
==============================================
All message templates, wish detection rules, prompt builders,
and dry-run notice logic.

Extracted from agent.py god file.

Author : Fahim (SadManFahIm)
Branch : feature/agent-decompose (→ 10.0)
"""

import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Reply & Wish Templates
# ──────────────────────────────────────────────────────────────

PERSONALIZED_REPLY_TEMPLATES = [
    "Thanks so much, {name}! Really means a lot ",
    "Appreciate it, {name}! Thank you for thinking of me ",
    "Thank you, {name}! Hope you're having a great day too ",
    "That's so kind of you, {name}! Thanks a lot ",
    "Aww, thanks {name}! Really appreciate the birthday wishes ",
]

BIRTHDAY_WISH_TEMPLATES = [
    "Happy Birthday, {name}!  Hope your day is as amazing as you are!",
    "Wishing you a fantastic birthday, {name}!  Hope it's full of joy!",
    "Happy Birthday {name}!  Wishing you all the best on your special day!",
    "Many happy returns of the day, {name}!  Hope this year brings great success!",
    "Happy Birthday {name}!  May your day be filled with happiness and laughter!",
]

# ──────────────────────────────────────────────────────────────
# Wish Detection Rules
# ──────────────────────────────────────────────────────────────

WISH_DETECTION_RULES = """
  A message IS a birthday wish if it contains ANY of the following -

   Direct English: "Happy birthday", "HBD", "Happy bday", "Many happy returns",
     "Wishing you a wonderful birthday", "Congrats on your special day",
     "Hope you have a great day", "Birthday greetings"

   Indirect English: "Another year older", "Another trip around the sun",
     "Hope your day is as special as you are", "Celebrate you today",
     "May this year bring you", "Here's to another year"

   Bengali:    " ", " ", " "
   Arabic:     "  ", "   "
   Hindi:      " ", "  "
   Spanish:    "Feliz cumpleaos", "Feliz cumple"
   French:     "Joyeux anniversaire"
   German:     "Alles Gute zum Geburtstag"
   Turkish:    "yi ki dodun"
   Indonesian: "Selamat ulang tahun", "Met ultah"
   Emoji:           (combined with name or greeting)

   NOT a birthday wish: job offers, "Hi/Hello", business messages,
     group announcements, replies to your own message.

  When in doubt -> SKIP.
"""


# ──────────────────────────────────────────────────────────────
# Dry Run Notice
# ──────────────────────────────────────────────────────────────


def dry_run_notice(dry_run: bool = True) -> str:
    """Generate a dry-run instruction block for agent prompts."""
    if dry_run:
        return """
    DRY RUN MODE IS ON 
  Do NOT send any messages.
  For each message you WOULD send, print:
    [DRY RUN] Would send to <n>: "<message>"
  Then move on without clicking Send.
"""
    return ""


# ──────────────────────────────────────────────────────────────
# LinkedIn Task Builders
# ──────────────────────────────────────────────────────────────


def build_linkedin_reply_task(already_logged_in: bool,
                              dry_run: bool = True,
                              filter_notice_str: str = "",
                              login_instructions: str = "") -> str:
    """Build the LinkedIn reply task prompt."""
    templates_str = "\n".join(
        f'  {i+1}. "{t}"'
        for i, t in enumerate(PERSONALIZED_REPLY_TEMPLATES)
    )
    return f"""
  Open the browser. {login_instructions}
  {dry_run_notice(dry_run)}
  {filter_notice_str}

  Go to https://www.linkedin.com/messaging/
  Check up to 15 UNREAD threads.

  For each thread:
    STEP 1 - Get sender's FIRST NAME.
    STEP 2 - Apply filters (blacklist, whitelist, cooldown).
    STEP 3 - Detect birthday wish: {WISH_DETECTION_RULES}
    STEP 4 - If yes -> choose ONE template randomly, fill {{name}}, send:
{templates_str}
    If no -> skip.

  Summary at the end: replied to (names), skipped (count+reason).
"""


def build_birthday_detection_task(already_logged_in: bool,
                                  dry_run: bool = True,
                                  filter_notice_str: str = "",
                                  login_instructions: str = "") -> str:
    """Build the LinkedIn birthday detection task prompt."""
    templates_str = "\n".join(
        f'  {i+1}. "{t}"'
        for i, t in enumerate(BIRTHDAY_WISH_TEMPLATES)
    )
    return f"""
  Open the browser. {login_instructions}
  {dry_run_notice(dry_run)}
  {filter_notice_str}

  Go to https://www.linkedin.com/mynetwork/
  Find contacts with birthdays TODAY (check Birthdays section + ).

  For each birthday contact:
    a) Get FIRST NAME only.
    b) Apply filters.
    c) Choose ONE wish randomly, fill {{name}}, send (or log if DRY RUN):
{templates_str}

  Stop after 20 contacts. TODAY only. No duplicates.
  Summary: wished (names), skipped (count+reason).
"""


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Wish Templates — Self-Test")
    print("=" * 50)

    # 1. Templates exist
    print("\n[1/4] Templates ...")
    assert len(PERSONALIZED_REPLY_TEMPLATES) == 5
    assert len(BIRTHDAY_WISH_TEMPLATES) == 5
    assert "{name}" in PERSONALIZED_REPLY_TEMPLATES[0]
    print("      ✅ 5 reply + 5 wish templates")

    # 2. Detection rules
    print("[2/4] Detection rules ...")
    assert "Happy birthday" in WISH_DETECTION_RULES
    assert "Bengali" in WISH_DETECTION_RULES
    print("      ✅ Multi-language detection rules present")

    # 3. Dry run notice
    print("[3/4] Dry run notice ...")
    assert "DRY RUN" in dry_run_notice(True)
    assert dry_run_notice(False) == ""
    print("      ✅ Dry run notice OK")

    # 4. Task builders
    print("[4/4] Task builders ...")
    reply_task = build_linkedin_reply_task(True, True, "test-filter")
    assert "linkedin.com/messaging" in reply_task
    assert "test-filter" in reply_task
    detect_task = build_birthday_detection_task(False, False)
    assert "linkedin.com/mynetwork" in detect_task
    assert "DRY RUN MODE IS ON" not in detect_task
    print("      ✅ LinkedIn reply + detection task builders OK")

    print("\n" + "=" * 50)
    print("✅ ALL WISH TEMPLATES TESTS PASSED")
    print("=" * 50)
