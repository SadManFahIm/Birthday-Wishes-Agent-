"""
tone_matching.py
────────────────
Tone Matching module for Birthday Wishes Agent.

Analyzes how a contact communicates (formal/informal/casual/emoji-heavy)
and adjusts the reply style to match their tone exactly.

How it works:
  1. Reads the contact's message
  2. Detects their communication style
  3. Generates a reply that mirrors their tone

Tone Types:
  - formal      : Professional, full sentences, no emoji
  - semi_formal : Friendly but professional, minimal emoji
  - casual      : Relaxed, contractions, some emoji
  - very_casual : Slang, abbreviations, lots of emoji
  - emoji_heavy : Mostly emoji, very short text

Usage:
    from tone_matching import detect_tone, get_tone_matched_reply
"""

import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# TONE DEFINITIONS
# ──────────────────────────────────────────────
TONE_PROFILES = {
    "formal": {
        "description": "Professional and formal",
        "signals":     ["Dear", "Sincerely", "I hope this message finds you",
                        "Best regards", "Warm regards", "Please accept"],
        "reply_style": "Use full sentences, professional language, no contractions, no emoji.",
        "example":     "Thank you sincerely for your kind birthday wishes. "
                       "I truly appreciate your thoughtfulness.",
    },
    "semi_formal": {
        "description": "Friendly but professional",
        "signals":     ["Hi", "Hello", "Thanks", "Hope you have",
                        "Wishing you", "Best wishes"],
        "reply_style": "Warm and friendly tone, occasional emoji (1 max), "
                       "short sentences, natural language.",
        "example":     "Thanks so much for the lovely wishes! Really made my day 😊",
    },
    "casual": {
        "description": "Relaxed and friendly",
        "signals":     ["Hey", "Heyy", "yo", "omg", "lol", "haha",
                        "btw", "gonna", "wanna", "u ", "ur "],
        "reply_style": "Casual and relaxed, contractions, 1-2 emoji, "
                       "conversational tone.",
        "example":     "Aww thanks so much!! Really means a lot 🎉😊",
    },
    "very_casual": {
        "description": "Very casual with slang",
        "signals":     ["HBD", "hbd", "bro", "dude", "man ", "sis ",
                        "fr fr", "ngl", "lowkey", "bestie", "girlie"],
        "reply_style": "Match their energy — very casual, abbreviations ok, "
                       "2-3 emoji, keep it short and fun.",
        "example":     "Aww thank u sm bro!! means a lot fr 🙏🎂🥳",
    },
    "emoji_heavy": {
        "description": "Emoji-heavy communication",
        "signals":     [],  # Detected by emoji count
        "reply_style": "Use plenty of emoji (3-5), short text, match their "
                       "enthusiastic energy.",
        "example":     "Thank you!! 🎂🎉🥳 So sweet of you!! 💛✨",
    },
}


# ──────────────────────────────────────────────
# EMOJI COUNTER
# ──────────────────────────────────────────────
def count_emojis(text: str) -> int:
    """Count the number of emoji in a text string."""
    count = 0
    for char in text:
        if ord(char) > 127000:  # Most emoji are in this range
            count += 1
        elif char in "🎂🎉🎈🥳🎁🙏😊😄💛💙❤️🌟⭐🔥✨🎊🎀":
            count += 1
    return count


# ──────────────────────────────────────────────
# FAST RULE-BASED TONE DETECTION
# ──────────────────────────────────────────────
def quick_tone_detect(message: str) -> str | None:
    """
    Fast rule-based tone detection before calling LLM.
    Returns tone string if confident, None if uncertain.
    """
    msg_lower = message.lower()
    emoji_count = count_emojis(message)

    # Emoji-heavy detection
    if emoji_count >= 4:
        return "emoji_heavy"

    # Check signals for each tone
    for tone, profile in TONE_PROFILES.items():
        if tone == "emoji_heavy":
            continue
        if any(signal.lower() in msg_lower for signal in profile["signals"]):
            return tone

    return None


# ──────────────────────────────────────────────
# LLM-BASED TONE DETECTION
# ──────────────────────────────────────────────
async def detect_tone(llm, message: str) -> dict:
    """
    Detect the communication tone of a message.

    Args:
        llm     : LangChain LLM instance
        message : The incoming message text

    Returns:
        Dict with tone, confidence, signals, reply_style
    """
    # Try fast detection first
    quick = quick_tone_detect(message)
    if quick:
        profile = TONE_PROFILES[quick]
        logger.info("⚡ Quick tone detection: %s", quick)
        return {
            "tone":        quick,
            "confidence":  0.85,
            "signals":     [],
            "reply_style": profile["reply_style"],
            "example":     profile["example"],
        }

    # Fall back to LLM
    prompt = f"""
Analyze the communication tone of this message:

Message: "{message}"

Classify the tone as ONE of:
  - formal      : Professional, "Dear...", full sentences, no emoji
  - semi_formal : Friendly but professional, "Hi/Hello", minimal emoji
  - casual      : Relaxed, "Hey", contractions, some emoji
  - very_casual : Slang, "bro/dude/HBD", abbreviations, emoji
  - emoji_heavy : Mostly emoji, very short text, enthusiastic

Return ONLY a JSON object:
{{
  "tone": "casual",
  "confidence": 0.9,
  "signals": ["Hey", "lol", "emoji used"],
  "reasoning": "one sentence"
}}

No extra text. JSON only.
"""
    try:
        import json
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text     = response.content.strip().replace("```json", "").replace("```", "").strip()
        result   = json.loads(text)
        tone     = result.get("tone", "semi_formal")
        profile  = TONE_PROFILES.get(tone, TONE_PROFILES["semi_formal"])

        result["reply_style"] = profile["reply_style"]
        result["example"]     = profile["example"]

        logger.info("🎭 Tone detected: %s (%.0f%% confidence)",
                    tone, result.get("confidence", 0) * 100)
        return result

    except Exception as e:
        logger.warning("⚠️  Tone detection failed: %s. Defaulting to semi_formal.", e)
        profile = TONE_PROFILES["semi_formal"]
        return {
            "tone":        "semi_formal",
            "confidence":  0.5,
            "signals":     [],
            "reply_style": profile["reply_style"],
            "example":     profile["example"],
        }


# ──────────────────────────────────────────────
# TONE-MATCHED REPLY GENERATOR
# ──────────────────────────────────────────────
async def get_tone_matched_reply(
    llm,
    name: str,
    their_message: str,
    tone_result: dict = None,
) -> str:
    """
    Generate a reply that matches the contact's communication tone.

    Args:
        llm           : LangChain LLM instance
        name          : Contact's first name
        their_message : Their birthday wish message
        tone_result   : Pre-detected tone dict (optional)

    Returns:
        Tone-matched reply string.
    """
    if not tone_result:
        tone_result = await detect_tone(llm, their_message)

    tone        = tone_result.get("tone", "semi_formal")
    reply_style = tone_result.get("reply_style", "")
    example     = tone_result.get("example", "")

    prompt = f"""
You are replying to a birthday wish on LinkedIn.

Contact name  : {name}
Their message : "{their_message}"
Their tone    : {tone}

Reply style to match: {reply_style}

Example of this tone: "{example}"

Write a SHORT reply (1-2 sentences) that:
  ✅ Exactly matches their communication tone
  ✅ Feels like a natural human response
  ✅ Acknowledges their birthday wish warmly
  ✅ If they used emoji → use similar emoji
  ✅ If they were formal → stay formal
  ✅ If they used slang → it's ok to mirror it slightly
  ❌ Do NOT be longer than 2 sentences
  ❌ Do NOT start with "I"

Reply with ONLY the message. No quotes, no explanation.
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        reply    = response.content.strip().strip('"').strip("'")
        logger.info("🎨 Tone-matched reply for %s (%s): %s",
                    name, tone, reply[:60] + "...")
        return reply
    except Exception as e:
        logger.error("❌ Tone-matched reply failed: %s", e)
        return f"Thanks so much, {name}! Really appreciate it 😊"


# ──────────────────────────────────────────────
# AGENT INSTRUCTIONS
# ──────────────────────────────────────────────
def build_tone_matching_instructions() -> str:
    """
    Returns instructions for the browser agent to detect
    tone and match it in replies.
    """
    return """
  TONE MATCHING INSTRUCTIONS:
  Before replying to any birthday wish, analyze HOW the person wrote
  their message and mirror their communication style.

  DETECT TONE:
    📋 formal      → "Dear...", full sentences, no emoji, professional
    😊 semi_formal → "Hi/Hello", friendly, 1 emoji max
    😄 casual      → "Hey", contractions, some emoji, relaxed
    🤙 very_casual → "bro/HBD/omg", slang, abbreviations, emoji
    🎉 emoji_heavy → lots of emoji, short text, enthusiastic

  MATCH THE TONE IN YOUR REPLY:

    If FORMAL:
      → "Thank you sincerely for your kind wishes. I truly appreciate it."
      → No emoji. Full sentences. Professional.

    If SEMI_FORMAL:
      → "Thanks so much for the lovely wishes! Really made my day 😊"
      → 1 emoji max. Natural language.

    If CASUAL:
      → "Aww thanks!! Means a lot to me 🎉😊"
      → A couple emoji. Relaxed tone.

    If VERY_CASUAL:
      → "Thank u sm bro!! fr means a lot 🙏🎂"
      → Mirror their energy. Short. Fun.

    If EMOJI_HEAVY:
      → "Thank you!! 🎂🎉🥳 So sweet of you!! 💛✨"
      → Match the emoji count. Enthusiastic.

  RULE: Never reply formally to a casual message, and never reply
  casually to a formal message. Always mirror the sender's energy.
"""