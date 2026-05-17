"""
multilang_reply.py
------------------
Multi-language Reply module for Birthday Wishes Agent.

Detects the language of an incoming birthday wish and
replies in the SAME language automatically.

Supported Languages:
  - English, Bengali, Arabic, Hindi, Spanish, French,
    German, Turkish, Indonesian, Malay, Urdu, Chinese,
    Japanese, Korean, Portuguese, Italian, Russian

How it works:
  1. Detects language of incoming wish
  2. Generates a reply in that exact language
  3. Falls back to English if language unsupported

Usage:
    from multilang_reply import detect_language, get_multilang_reply
"""

import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


# ----------------------------------------------
# LANGUAGE DEFINITIONS
# ----------------------------------------------
SUPPORTED_LANGUAGES = {
    "english":    {"code": "en", "name": "English",    "flag": ""},
    "bengali":    {"code": "bn", "name": "Bengali",    "flag": ""},
    "arabic":     {"code": "ar", "name": "Arabic",     "flag": ""},
    "hindi":      {"code": "hi", "name": "Hindi",      "flag": ""},
    "spanish":    {"code": "es", "name": "Spanish",    "flag": ""},
    "french":     {"code": "fr", "name": "French",     "flag": ""},
    "german":     {"code": "de", "name": "German",     "flag": ""},
    "turkish":    {"code": "tr", "name": "Turkish",    "flag": ""},
    "indonesian": {"code": "id", "name": "Indonesian", "flag": ""},
    "malay":      {"code": "ms", "name": "Malay",      "flag": ""},
    "urdu":       {"code": "ur", "name": "Urdu",       "flag": ""},
    "chinese":    {"code": "zh", "name": "Chinese",    "flag": ""},
    "japanese":   {"code": "ja", "name": "Japanese",   "flag": ""},
    "korean":     {"code": "ko", "name": "Korean",     "flag": ""},
    "portuguese": {"code": "pt", "name": "Portuguese", "flag": ""},
    "italian":    {"code": "it", "name": "Italian",    "flag": ""},
    "russian":    {"code": "ru", "name": "Russian",    "flag": ""},
}

# Fast rule-based detection signals
LANGUAGE_SIGNALS = {
    "bengali":    ["", "", "", "", ""],
    "arabic":     ["", "", "", "", " "],
    "hindi":      ["", "", "", "", ""],
    "urdu":       ["", "", "", " "],
    "spanish":    ["feliz", "cumpleaos", "cumple", "felicidades"],
    "french":     ["joyeux", "anniversaire", "bon anniversaire", "flicitations"],
    "german":     ["geburtstag", "alles gute", "herzlichen glckwunsch"],
    "turkish":    ["doum gnn", "iyi ki dodun", "mutlu yllar"],
    "indonesian": ["selamat ulang tahun", "met ultah", "hbd ya"],
    "malay":      ["selamat hari jadi", "ucapan tahniah"],
    "chinese":    ["", "", ""],
    "japanese":   ["", "", ""],
    "korean":     ["", "", ""],
    "portuguese": ["feliz aniversrio", "parabns", "muitos anos"],
    "italian":    ["buon compleanno", "tanti auguri", "felice"],
    "russian":    ["  ", "", ""],
}

# Pre-built reply templates in each language
REPLY_TEMPLATES = {
    "english":    [
        "Thank you so much, {name}! Really means a lot ",
        "Appreciate it, {name}! Thank you for the lovely wishes ",
    ],
    "bengali":    [
        " , {name}!     ",
        "    , {name}! ",
    ],
    "arabic":     [
        "   {name}!   ",
        "     {name}!     ",
    ],
    "hindi":      [
        "  , {name}!     ",
        "      , {name}! ",
    ],
    "spanish":    [
        "Muchas gracias, {name}! De verdad significa mucho ",
        "Gracias por tus buenos deseos, {name}! Me alegra mucho ",
    ],
    "french":     [
        "Merci beaucoup, {name}! a me touche vraiment ",
        "Merci infiniment pour tes vux, {name}! ",
    ],
    "german":     [
        "Vielen herzlichen Dank, {name}! Das bedeutet mir wirklich viel ",
        "Danke schn fr deine Wnsche, {name}! ",
    ],
    "turkish":    [
        "ok teekkr ederim, {name}! Gerekten ok anlaml ",
        "Gzel dileklerin iin teekkrler, {name}! ",
    ],
    "indonesian": [
        "Terima kasih banyak, {name}! Benar-benar berarti ",
        "Makasih buat ucapannya ya {name}! ",
    ],
    "malay":      [
        "Terima kasih banyak-banyak, {name}! Sungguh bermakna ",
        "Terima kasih atas ucapan {name}! ",
    ],
    "urdu":       [
        "   {name}!     ",
        "      {name}! ",
    ],
    "chinese":    [
        "{name} ",
        "{name} ",
    ],
    "japanese":   [
        "{name} ",
        "{name}",
    ],
    "korean":     [
        " , {name}!   ",
        "{name},   ! ",
    ],
    "portuguese": [
        "Muito obrigado(a), {name}! Significa muito para mim ",
        "Obrigado pelos votos, {name}! Fico muito feliz ",
    ],
    "italian":    [
        "Grazie mille, {name}! Significa davvero tanto ",
        "Grazie per i tuoi auguri, {name}! Mi fa molto piacere ",
    ],
    "russian":    [
        " , {name}!       ",
        "  , {name}!   ",
    ],
}


# ----------------------------------------------
# FAST RULE-BASED LANGUAGE DETECTION
# ----------------------------------------------
def quick_language_detect(message: str) -> str | None:
    """Fast rule-based language detection."""
    msg_lower = message.lower()
    for lang, signals in LANGUAGE_SIGNALS.items():
        if any(signal in msg_lower for signal in signals):
            logger.info(" Quick language detection: %s", lang)
            return lang
    return None


# ----------------------------------------------
# LLM-BASED LANGUAGE DETECTION
# ----------------------------------------------
async def detect_language(llm, message: str) -> dict:
    """
    Detect the language of an incoming message.

    Args:
        llm     : LangChain LLM instance
        message : The incoming message text

    Returns:
        Dict with language, code, confidence, flag
    """
    # Try fast detection first
    quick = quick_language_detect(message)
    if quick:
        lang_info = SUPPORTED_LANGUAGES.get(quick, SUPPORTED_LANGUAGES["english"])
        return {
            "language":   quick,
            "code":       lang_info["code"],
            "confidence": 0.9,
            "flag":       lang_info["flag"],
        }

    # Fall back to LLM
    supported = ", ".join(SUPPORTED_LANGUAGES.keys())
    prompt = f"""
Detect the language of this message:

"{message}"

Supported languages: {supported}

Return ONLY a JSON object:
{{
  "language": "english",
  "confidence": 0.98
}}

If unsure or mixed -> return "english".
No extra text. JSON only.
"""
    try:
        import json
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text     = response.content.strip().replace("```json", "").replace("```", "").strip()
        result   = json.loads(text)
        lang     = result.get("language", "english").lower()
        lang_info = SUPPORTED_LANGUAGES.get(lang, SUPPORTED_LANGUAGES["english"])

        result["code"] = lang_info["code"]
        result["flag"] = lang_info["flag"]
        result["language"] = lang

        logger.info(
            " Language detected: %s %s (%.0f%% confidence)",
            lang_info["flag"], lang, result.get("confidence", 0) * 100,
        )
        return result

    except Exception as e:
        logger.warning("  Language detection failed: %s. Defaulting to English.", e)
        return {
            "language":   "english",
            "code":       "en",
            "confidence": 0.5,
            "flag":       "",
        }


# ----------------------------------------------
# GET MULTI-LANGUAGE REPLY
# ----------------------------------------------
async def get_multilang_reply(
    llm,
    name: str,
    their_message: str,
    lang_result: dict = None,
    index: int = 0,
) -> str:
    """
    Generate a reply in the same language as the incoming message.

    Args:
        llm           : LangChain LLM instance
        name          : Contact's first name
        their_message : Their birthday wish
        lang_result   : Pre-detected language dict (optional)
        index         : Which template to use

    Returns:
        Reply string in the detected language.
    """
    if not lang_result:
        lang_result = await detect_language(llm, their_message)

    language = lang_result.get("language", "english")
    flag     = lang_result.get("flag", "")

    # Try pre-built template first
    templates = REPLY_TEMPLATES.get(language, REPLY_TEMPLATES["english"])
    if templates:
        reply = templates[index % len(templates)].replace("{name}", name)
        logger.info(
            " Template reply in %s %s for %s",
            flag, language, name,
        )
        return reply

    # Fall back to LLM generation in target language
    lang_name = SUPPORTED_LANGUAGES.get(language, {}).get("name", "English")
    prompt = f"""
Write a short birthday thank-you reply in {lang_name}.

The person's name is: {name}
They wished you: "{their_message}"

Write a warm, genuine reply (1-2 sentences) in {lang_name}.
Include 1-2 emoji.
Reply with ONLY the message text.
"""
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        reply    = response.content.strip().strip('"').strip("'")
        logger.info(" LLM reply in %s for %s: %s", language, name, reply[:60])
        return reply
    except Exception as e:
        logger.error(" Multilang reply failed: %s", e)
        return f"Thank you so much, {name}! Really means a lot "


# ----------------------------------------------
# AGENT INSTRUCTIONS
# ----------------------------------------------
def build_multilang_instructions() -> str:
    """
    Returns instructions for the browser agent to detect
    language and reply in the same language.
    """
    lang_examples = "\n".join(
        f"  {info['flag']} {info['name']:12} -> reply in {info['name']}"
        for info in list(SUPPORTED_LANGUAGES.values())[:10]
    )

    return f"""
  MULTI-LANGUAGE REPLY INSTRUCTIONS:
  Always reply in the SAME language the person used to wish you.

  Language detection examples:
{lang_examples}
  ... and more

  Reply examples by language:
   Bengali  : "  [name]!     "
   Arabic   : "   [name]!   "
   Hindi    : "   [name]!     "
   Spanish  : "Muchas gracias [name]! De verdad significa mucho "
   French   : "Merci beaucoup [name]! a me touche vraiment "
   German   : "Vielen Dank [name]! Das bedeutet mir wirklich viel "
   English  : "Thanks so much [name]! Really means a lot "

  RULES:
   Detect the language from the wish message
   Reply in that exact language
   Keep the reply warm and genuine
   Include 1-2 emoji
   Never reply in English if they wrote in another language
   Never mix languages in one reply
"""