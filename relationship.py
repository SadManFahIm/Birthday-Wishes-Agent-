"""
relationship.py
───────────────
Contact Relationship Score module.

Determines the relationship type between you and a LinkedIn contact
based on interaction signals, then selects the appropriate wish style.

Relationship Types:
  - close_friend   : High interaction, long connection, many mutual connections
  - colleague      : Work-related connection, same industry/company
  - acquaintance   : Low interaction, few mutuals, recent connection

Wish Styles:
  - close_friend   : Casual, warm, funny, personal
  - colleague      : Professional but friendly, mentions work
  - acquaintance   : Polite, brief, warm
"""

import logging

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# RELATIONSHIP SCORE CALCULATOR
# ──────────────────────────────────────────────
def calculate_relationship_score(profile_info: dict) -> dict:
    """
    Calculate a relationship score based on profile signals.

    Args:
        profile_info: Dict with keys:
            - mutual_connections (int)
            - connection_duration_years (float) — how long connected
            - same_company (bool)
            - same_industry (bool)
            - interaction_count (int) — likes, comments, messages
            - is_followed_back (bool)

    Returns:
        Dict with:
            - score (int 0-100)
            - relationship_type ("close_friend" | "colleague" | "acquaintance")
            - signals (list of reasons)
    """
    score = 0
    signals = []

    mutual = profile_info.get("mutual_connections", 0)
    duration = profile_info.get("connection_duration_years", 0)
    same_company = profile_info.get("same_company", False)
    same_industry = profile_info.get("same_industry", False)
    interactions = profile_info.get("interaction_count", 0)
    followed_back = profile_info.get("is_followed_back", False)

    # Mutual connections scoring
    if mutual >= 50:
        score += 30
        signals.append(f"Many mutual connections ({mutual})")
    elif mutual >= 20:
        score += 20
        signals.append(f"Good mutual connections ({mutual})")
    elif mutual >= 5:
        score += 10
        signals.append(f"Some mutual connections ({mutual})")

    # Connection duration scoring
    if duration >= 3:
        score += 25
        signals.append(f"Long-term connection ({duration:.1f} years)")
    elif duration >= 1:
        score += 15
        signals.append(f"Connected for {duration:.1f} years")
    else:
        score += 5
        signals.append("Recent connection")

    # Interaction scoring
    if interactions >= 20:
        score += 25
        signals.append(f"High interaction ({interactions} times)")
    elif interactions >= 5:
        score += 15
        signals.append(f"Some interaction ({interactions} times)")
    elif interactions >= 1:
        score += 5
        signals.append("Minimal interaction")

    # Same company/industry
    if same_company:
        score += 15
        signals.append("Works at same company")
    elif same_industry:
        score += 10
        signals.append("Same industry")

    # Followed back
    if followed_back:
        score += 5
        signals.append("Follows you back")

    # Determine relationship type
    if score >= 60:
        relationship_type = "close_friend"
    elif score >= 30:
        relationship_type = "colleague"
    else:
        relationship_type = "acquaintance"

    logger.info(
        "📊 Relationship score for contact: %d/100 → %s",
        score, relationship_type
    )

    return {
        "score": score,
        "relationship_type": relationship_type,
        "signals": signals,
    }


# ──────────────────────────────────────────────
# WISH STYLE TEMPLATES BY RELATIONSHIP
# ──────────────────────────────────────────────
WISH_STYLES = {
    "close_friend": {
        "description": "Casual, warm, funny, and personal",
        "templates": [
            "Happy Birthday {name}! 🎉 Another year of being awesome — hope today is as incredible as you are! Let's celebrate soon!",
            "Hey {name}, Happy Birthday! 🥳 You officially have permission to eat all the cake today. Hope it's an amazing one!",
            "Happy Birthday {name}! 🎂 Can't believe another year has flown by. Wishing you nothing but the best — you deserve it all!",
            "Birthday time for {name}! 🎈 Hope your day is as fun and fantastic as you always make everything around you. Cheers! 🥂",
            "Happy Birthday {name}! 🎁 Here's to another year of you being absolutely brilliant. So lucky to know you!",
        ],
        "tone": "casual, warm, funny",
    },
    "colleague": {
        "description": "Professional but friendly, mentions work context",
        "templates": [
            "Happy Birthday {name}! 🎂 Wishing you a wonderful day and a year filled with great achievements both personally and professionally!",
            "Happy Birthday {name}! 💼 It's been a pleasure working alongside such a talented professional. Hope your special day is fantastic!",
            "Wishing you a very Happy Birthday {name}! 🌟 May this year bring you exciting new opportunities and continued success in everything you do!",
            "Happy Birthday {name}! 🎉 Your dedication and hard work are truly inspiring. Hope you take today to relax and celebrate yourself!",
            "Many happy returns {name}! 🎈 Wishing you a day as great as the work you do. Hope the year ahead brings you joy and success!",
        ],
        "tone": "professional, friendly",
    },
    "acquaintance": {
        "description": "Polite, brief, and warm",
        "templates": [
            "Happy Birthday {name}! 🎂 Wishing you a wonderful day and a fantastic year ahead!",
            "Wishing you a very Happy Birthday {name}! 🎉 Hope your day is filled with joy and happiness!",
            "Happy Birthday {name}! 🌟 Hope you have a great celebration and an amazing year ahead!",
            "Many happy returns of the day {name}! 🎈 Wishing you all the best on your special day!",
            "Happy Birthday {name}! 🥳 Hope today brings you lots of smiles and wonderful memories!",
        ],
        "tone": "polite, brief, warm",
    },
}


# ──────────────────────────────────────────────
# GET WISH BY RELATIONSHIP
# ──────────────────────────────────────────────
def get_wish_by_relationship(
    name: str,
    relationship_type: str,
    index: int = 0,
) -> str:
    """
    Get a birthday wish based on relationship type.

    Args:
        name              : Contact's first name
        relationship_type : "close_friend", "colleague", or "acquaintance"
        index             : Which template to use (0-4), use randomly

    Returns:
        Formatted wish string with name filled in.
    """
    style = WISH_STYLES.get(relationship_type, WISH_STYLES["acquaintance"])
    templates = style["templates"]
    template = templates[index % len(templates)]
    wish = template.replace("{name}", name)
    logger.info(
        "💝 Wish selected for %s (%s): %s",
        name, relationship_type, wish[:50] + "..."
    )
    return wish


# ──────────────────────────────────────────────
# RELATIONSHIP DETECTION TASK (for browser agent)
# ──────────────────────────────────────────────
def build_relationship_detection_instructions() -> str:
    """
    Returns instructions for the browser agent to detect
    relationship signals from a LinkedIn profile.
    """
    return """
  RELATIONSHIP DETECTION:
  Before sending a birthday wish, assess the relationship by checking:

  1. MUTUAL CONNECTIONS
     - Look for "X mutual connections" on their profile
     - 50+  → likely close_friend
     - 20+  → likely colleague
     - <5   → likely acquaintance

  2. CONNECTION DURATION
     - Check when you connected (shown on profile or "Connected X years ago")
     - 3+ years → closer relationship
     - < 1 year → recent/acquaintance

  3. SAME COMPANY / INDUSTRY
     - If their current company matches yours → colleague
     - If same industry → likely colleague

  4. INTERACTION HISTORY
     - Check if they've liked/commented on your posts recently
     - Check if you've messaged before

  Based on these signals, classify as ONE of:
    - "close_friend"  (score 60+)
    - "colleague"     (score 30-59)
    - "acquaintance"  (score 0-29)

  Then use the appropriate wish style:

  close_friend  → Casual, fun, warm: "Hey {name}! 🥳 Hope today is as awesome as you are!"
  colleague     → Professional but friendly: "Happy Birthday {name}! 💼 Wishing you continued success!"
  acquaintance  → Polite and brief: "Happy Birthday {name}! 🎂 Hope you have a wonderful day!"
"""