"""
sentiment.py
────────────
Sentiment Analysis module for Birthday Wishes Agent.

Analyzes the tone of incoming birthday wishes to detect
if the sender seems sad, stressed, overwhelmed, or going
through a difficult time — and adjusts the reply accordingly.

Sentiment Types:
  - happy      : Normal, cheerful message → standard reply
  - neutral    : Polite but flat message → warm reply
  - sad        : Hints of sadness or difficulty → extra caring reply
  - stressed   : Mentions work pressure, exhaustion → supportive reply
  - lonely     : Sounds isolated or disconnected → extra warm reply

Usage:
    from sentiment import analyze_sentiment, get_sentiment_reply

    result = await analyze_sentiment(llm, "Thanks... it's been a rough year honestly")
    # result = {"sentiment": "sad", "confidence": 0.9, "signals": ["rough year"]}

    reply = get_sentiment_reply("Rahul", result["sentiment"])
"""

import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# REPLY TEMPLATES BY SENTIMENT
# ──────────────────────────────────────────────
SENTIMENT_REPLIES = {
    "happy": [
        "Thanks so much, {name}! Really means a lot 😊",
        "Appreciate it, {name}! Thank you for the lovely wishes 🎉",
        "Aww, thanks {name}! Hope you're having a great day too! 😄",
    ],
    "neutral": [
        "Thank you so much, {name}! Your wishes truly made my day brighter 😊",
        "That's so kind of you, {name}! Really appreciate you thinking of me 🙏",
        "Thanks {name}! Means a lot to hear from you on my special day 🎂",
    ],
    "sad": [
        "Thank you so much, {name} 🙏 Your message truly touched my heart. "
        "I hope things get easier for you soon — you deserve all the good things in life 💛",
        "That means the world to me, {name}. Thank you 💙 "
        "I hope whatever you're going through right now passes quickly. "
        "Sending you lots of warmth and positive energy 🌟",
        "Thank you, {name} 🤗 Your kindness means so much. "
        "I'm here if you ever need someone to talk to — take care of yourself 💛",
    ],
    "stressed": [
        "Thank you so much, {name}! 😊 I really appreciate you taking the time "
        "to wish me even when things seem busy. Please don't forget to take "
        "care of yourself too — you've got this! 💪",
        "Thanks {name}! 🙏 It means a lot. I know life can get overwhelming "
        "sometimes — I hope you get a moment to breathe and recharge soon 🌿",
        "That's so thoughtful of you, {name}! Thank you 😊 "
        "Wishing you a calmer, lighter week ahead — you deserve a break! ☀️",
    ],
    "lonely": [
        "Thank you so much, {name} 💛 Your message genuinely made me smile. "
        "I hope we get to catch up soon — would love to hear how you're doing!",
        "That really means a lot, {name} 🤗 Thank you for thinking of me. "
        "Let's not let too much time pass — would be great to reconnect soon!",
        "Thanks {name}! 😊 Your wish warmed my heart. "
        "I hope you're surrounded by good people and good energy. "
        "Let's catch up sometime soon! 🌟",
    ],
}

# Signals that indicate each sentiment
SENTIMENT_SIGNALS = {
    "sad": [
        "rough year", "hard year", "difficult year", "tough year",
        "not doing great", "not been easy", "going through a lot",
        "rough time", "hard time", "struggling", "things are hard",
        "been tough", "miss you", "feeling down", "sad", "depressed",
        "lost", "grieving", "heartbroken", "alone",
    ],
    "stressed": [
        "so busy", "really busy", "crazy busy", "overwhelmed",
        "exhausted", "burnt out", "stressed", "no time",
        "deadline", "workload", "pressure", "drowning in work",
        "barely surviving", "running on empty", "need a break",
        "haven't slept", "non-stop",
    ],
    "lonely": [
        "no one around", "all alone", "by myself", "lonely",
        "isolated", "miss everyone", "far from home", "no family",
        "no friends", "nobody", "just me",
    ],
}


# ──────────────────────────────────────────────
# RULE-BASED FAST DETECTION
# ──────────────────────────────────────────────
def quick_sentiment_check(message: str) -> str | None:
    """
    Fast rule-based sentiment check before calling the LLM.
    Returns sentiment string if confident, None if uncertain.
    """
    msg_lower = message.lower()
    for sentiment, signals in SENTIMENT_SIGNALS.items():
        if any(signal in msg_lower for signal in signals):
            logger.info("⚡ Quick sentiment match: %s", sentiment)
            return sentiment
    return None


# ──────────────────────────────────────────────
# LLM-BASED SENTIMENT ANALYSIS
# ──────────────────────────────────────────────
async def analyze_sentiment(llm, message: str) -> dict:
    """
    Analyze the sentiment of an incoming birthday wish message.

    Args:
        llm     : LangChain LLM instance
        message : The incoming message text

    Returns:
        Dict with:
            - sentiment   : "happy" | "neutral" | "sad" | "stressed" | "lonely"
            - confidence  : float 0.0 to 1.0
            - signals     : list of detected signal phrases
            - reasoning   : short explanation
    """
    # Try fast check first
    quick = quick_sentiment_check(message)
    if quick:
        return {
            "sentiment":  quick,
            "confidence": 0.85,
            "signals":    [],
            "reasoning":  f"Rule-based detection: {quick}",
        }

    # Fall back to LLM
    prompt = f"""
Analyze the emotional tone of this birthday wish message.

Message: "{message}"

Classify the sender's emotional state as ONE of:
  - happy    : Cheerful, enthusiastic, genuinely joyful
  - neutral  : Polite but flat, no strong emotion
  - sad      : Hints of sadness, difficulty, hardship, or loss
  - stressed : Mentions busyness, exhaustion, pressure, or overwhelm
  - lonely   : Sounds isolated, disconnected, or missing people

Return ONLY a JSON object like this:
{{
  "sentiment": "happy",
  "confidence": 0.9,
  "signals": ["phrase that indicated this"],
  "reasoning": "one sentence explanation"
}}

No extra text. JSON only.
"""
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        import json
        text = response.content.strip()
        # Strip markdown code fences if present
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        logger.info(
            "🎭 Sentiment detected: %s (%.0f%% confidence) — %s",
            result.get("sentiment"), result.get("confidence", 0) * 100,
            result.get("reasoning", ""),
        )
        return result
    except Exception as e:
        logger.warning("⚠️  Sentiment analysis failed: %s. Defaulting to neutral.", e)
        return {
            "sentiment":  "neutral",
            "confidence": 0.5,
            "signals":    [],
            "reasoning":  "Fallback due to error",
        }


# ──────────────────────────────────────────────
# GET SENTIMENT-AWARE REPLY
# ──────────────────────────────────────────────
def get_sentiment_reply(name: str, sentiment: str, index: int = 0) -> str:
    """
    Get a reply message tailored to the detected sentiment.

    Args:
        name      : Sender's first name
        sentiment : Detected sentiment string
        index     : Which template to use (0-2)

    Returns:
        Formatted reply string.
    """
    templates = SENTIMENT_REPLIES.get(sentiment, SENTIMENT_REPLIES["neutral"])
    template  = templates[index % len(templates)]
    reply     = template.replace("{name}", name)
    logger.info(
        "💬 Sentiment reply selected for %s (%s): %s",
        name, sentiment, reply[:60] + "...",
    )
    return reply


# ──────────────────────────────────────────────
# SENTIMENT INSTRUCTIONS FOR BROWSER AGENT
# ──────────────────────────────────────────────
def build_sentiment_instructions() -> str:
    """
    Returns instructions for the browser agent to detect
    sentiment and reply with the appropriate tone.
    """
    return """
  SENTIMENT ANALYSIS INSTRUCTIONS:
  Before composing a reply, carefully read the birthday wish message
  and assess the sender's emotional state.

  STEP 1 — Detect sentiment:
    😊 happy    : Cheerful, enthusiastic — "Happy birthday!! Hope you have an amazing day!!! 🎉"
    😐 neutral  : Polite but flat — "Happy birthday." or "HBD"
    😢 sad      : Hints of difficulty — "Happy birthday... it's been a rough year for me"
    😓 stressed : Mentions busyness — "HBD! Sorry for the late wish, been crazy busy"
    😔 lonely   : Sounds isolated — "Happy birthday, I miss everyone so much"

  STEP 2 — Choose reply tone:
    happy    → Standard warm reply
    neutral  → Slightly warmer, more personal
    sad      → Extra caring, empathetic, offer support
    stressed → Supportive, acknowledge their busyness, encourage rest
    lonely   → Extra warm, suggest catching up, make them feel valued

  STEP 3 — Important rules:
    ❌ Never directly say "I can see you're sad" or call out their emotion
    ✅ Subtly inject warmth and care into the reply
    ✅ Keep it natural — it should feel like a genuine human response
    ✅ For sad/lonely/stressed → add one sentence of emotional support
"""