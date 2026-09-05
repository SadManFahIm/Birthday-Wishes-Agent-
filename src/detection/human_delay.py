"""
human_delay.py
--------------
Human-like Delay Engine for Birthday Wishes Agent.

Adds realistic random delays and typing speed variations
to avoid LinkedIn bot detection.

What it does:
  - Random delays between actions (not fixed intervals)
  - Typing speed variation (fast typist vs slow typist)
  - Natural pauses before clicking, scrolling, sending
  - Session-level behavior profiling (consistent per session)
  - Peak/off-peak timing awareness

Usage:
    from human_delay import (
        delay,
        typing_delay,
        before_click,
        before_send,
        before_scroll,
        before_search,
        HumanSession,
    )

    await delay("short")
    await before_click()
    await before_send()
"""

import asyncio
import logging
import random
import time
from enum import Enum

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# DELAY PROFILES
# ------------------------------------------------------------

class DelayProfile(Enum):
    FAST    = "fast"     # Power user
    NORMAL  = "normal"   # Average user
    SLOW    = "slow"     # Careful/slow user


# Delay ranges in seconds per profile (min, max)
DELAY_RANGES = {
    "short": {
        DelayProfile.FAST:   (0.3, 0.8),
        DelayProfile.NORMAL: (0.5, 1.5),
        DelayProfile.SLOW:   (1.0, 2.5),
    },
    "medium": {
        DelayProfile.FAST:   (1.0, 2.0),
        DelayProfile.NORMAL: (1.5, 3.5),
        DelayProfile.SLOW:   (2.5, 5.0),
    },
    "long": {
        DelayProfile.FAST:   (2.0, 4.0),
        DelayProfile.NORMAL: (3.0, 6.0),
        DelayProfile.SLOW:   (5.0, 10.0),
    },
    "think": {
        DelayProfile.FAST:   (1.5, 3.0),
        DelayProfile.NORMAL: (2.0, 5.0),
        DelayProfile.SLOW:   (4.0, 8.0),
    },
    "read": {
        DelayProfile.FAST:   (3.0, 6.0),
        DelayProfile.NORMAL: (5.0, 10.0),
        DelayProfile.SLOW:   (8.0, 15.0),
    },
}

# Typing speed in chars per second (min, max)
TYPING_SPEEDS = {
    DelayProfile.FAST:   (8, 15),   # 8-15 chars/sec (fast typist)
    DelayProfile.NORMAL: (4, 8),    # 4-8 chars/sec (average)
    DelayProfile.SLOW:   (2, 5),    # 2-5 chars/sec (slow)
}

# Probability of taking a "micro break" during typing (0-1)
MICRO_BREAK_CHANCE = 0.15

# Probability of making a "mistake pause" (backspace simulation)
MISTAKE_CHANCE = 0.05


# ------------------------------------------------------------
# HUMAN SESSION
# ------------------------------------------------------------

class HumanSession:
    """
    Maintains consistent human-like behavior for a session.
    One instance per browser session — profile stays consistent.
    """

    def __init__(self, profile: DelayProfile | None = None):
        # Randomly assign a profile if not given
        self.profile = profile or random.choices(
            [DelayProfile.FAST, DelayProfile.NORMAL, DelayProfile.SLOW],
            weights=[20, 60, 20],
        )[0]

        # Session start time
        self.start_time = time.time()

        # Action count (humans slow down after many actions)
        self.action_count = 0

        # Fatigue factor (increases over time)
        self.fatigue = 1.0

        logger.info("HumanSession created: profile=%s", self.profile.value)

    def update_fatigue(self):
        """Increase delay slightly after many actions (fatigue)."""
        self.action_count += 1
        if self.action_count > 20:
            self.fatigue = min(1.5, 1.0 + (self.action_count - 20) * 0.02)

    def get_delay(self, delay_type: str) -> float:
        """Get a random delay for the given type."""
        ranges  = DELAY_RANGES.get(delay_type, DELAY_RANGES["short"])
        lo, hi  = ranges.get(self.profile, (0.5, 1.5))
        base    = random.uniform(lo, hi)
        return base * self.fatigue

    def get_typing_delay(self, char_count: int) -> float:
        """Get realistic typing duration for a given text length."""
        lo, hi    = TYPING_SPEEDS[self.profile]
        speed     = random.uniform(lo, hi)
        base_time = char_count / speed

        # Add micro-breaks
        micro_breaks = sum(
            random.uniform(0.3, 1.2)
            for _ in range(char_count)
            if random.random() < MICRO_BREAK_CHANCE / char_count
        )

        # Add mistake pauses
        mistakes = sum(
            random.uniform(0.5, 1.5)
            for _ in range(char_count)
            if random.random() < MISTAKE_CHANCE / char_count
        )

        return (base_time + micro_breaks + mistakes) * self.fatigue


# Global session (reset each agent run)
_current_session: HumanSession | None = None


def get_session() -> HumanSession:
    """Get or create the current human session."""
    global _current_session
    if _current_session is None:
        _current_session = HumanSession()
    return _current_session


def reset_session(profile: DelayProfile | None = None):
    """Start a new human session (call at the beginning of each agent run)."""
    global _current_session
    _current_session = HumanSession(profile)
    logger.info("Human session reset: %s", _current_session.profile.value)


# ------------------------------------------------------------
# DELAY FUNCTIONS
# ------------------------------------------------------------

async def delay(delay_type: str = "short", log: bool = False):
    """
    Wait for a human-like random delay.

    Args:
        delay_type: short / medium / long / think / read
        log       : Whether to log the delay
    """
    session    = get_session()
    wait_time  = session.get_delay(delay_type)
    session.update_fatigue()

    if log:
        logger.debug("Human delay [%s]: %.2fs", delay_type, wait_time)

    await asyncio.sleep(wait_time)


async def typing_delay(text: str, log: bool = False):
    """
    Wait realistically for typing a given text.

    Args:
        text: The text being typed
        log : Whether to log the delay
    """
    if not text:
        return

    session   = get_session()
    wait_time = session.get_typing_delay(len(text))

    if log:
        logger.debug("Typing delay [%d chars]: %.2fs", len(text), wait_time)

    await asyncio.sleep(wait_time)


# ------------------------------------------------------------
# ACTION-SPECIFIC DELAYS
# ------------------------------------------------------------

async def before_click():
    """Natural pause before clicking a button or link."""
    session   = get_session()
    wait_time = session.get_delay("short")
    await asyncio.sleep(wait_time)


async def before_send():
    """
    Pause before sending a message — simulates reviewing the text.
    Slightly longer than a regular click.
    """
    session   = get_session()
    wait_time = session.get_delay("think")
    await asyncio.sleep(wait_time)


async def before_scroll():
    """Brief pause before scrolling."""
    wait_time = random.uniform(0.3, 0.9)
    await asyncio.sleep(wait_time)


async def before_search():
    """Pause before typing a search query."""
    session   = get_session()
    wait_time = session.get_delay("short")
    await asyncio.sleep(wait_time)


async def after_page_load():
    """
    Wait after a page loads — simulates reading/scanning the page.
    """
    session   = get_session()
    wait_time = session.get_delay("read")
    await asyncio.sleep(wait_time)


async def between_messages():
    """
    Wait between sending multiple messages.
    Longer delay to seem natural.
    """
    session   = get_session()
    wait_time = session.get_delay("long")
    await asyncio.sleep(wait_time)


async def between_profiles():
    """
    Wait between visiting different LinkedIn profiles.
    Medium delay to avoid detection.
    """
    session   = get_session()
    wait_time = session.get_delay("medium")
    await asyncio.sleep(wait_time)


async def occasional_long_pause():
    """
    Occasionally take a longer break — like checking phone or thinking.
    Call randomly during long sessions.
    """
    if random.random() < 0.1:  # 10% chance
        wait_time = random.uniform(8.0, 20.0)
        logger.debug("Taking occasional long pause: %.1fs", wait_time)
        await asyncio.sleep(wait_time)


# ------------------------------------------------------------
# BATCH DELAY HELPERS
# ------------------------------------------------------------

async def delay_between_contacts(contact_count: int):
    """
    Delay between processing multiple contacts.
    Increases with count to simulate natural slowdown.
    """
    session   = get_session()
    base      = session.get_delay("medium")
    extra     = min(contact_count * 0.2, 3.0)
    wait_time = base + extra
    await asyncio.sleep(wait_time)
    await occasional_long_pause()


async def delay_after_send(sent_count: int):
    """
    Delay after sending a message.
    Gets longer after many sends (like taking a break).
    """
    session = get_session()

    if sent_count > 0 and sent_count % 5 == 0:
        # Take a longer break every 5 sends
        wait_time = random.uniform(15.0, 45.0)
        logger.info("Taking break after %d sends: %.1fs", sent_count, wait_time)
    else:
        wait_time = session.get_delay("long")

    await asyncio.sleep(wait_time)


# ------------------------------------------------------------
# INSTRUCTIONS FOR AGENT
# ------------------------------------------------------------

def build_delay_instructions() -> str:
    """
    Build delay instructions to inject into agent task prompt.
    Tells the browser agent to behave more humanly.
    """
    session = get_session()
    profile = session.profile.value

    if profile == "fast":
        style = "You are an efficient professional quickly managing LinkedIn."
        speed = "Move quickly but naturally between actions."
    elif profile == "slow":
        style = "You are a careful user who reads things thoroughly."
        speed = "Take your time between each action. Read before clicking."
    else:
        style = "You are a regular LinkedIn user going through your messages."
        speed = "Move at a natural pace. Pause briefly between actions."

    return f"""
  HUMAN BEHAVIOR INSTRUCTIONS:
  {style}
  {speed}

  - Pause 1-3 seconds before clicking buttons
  - Pause 2-5 seconds before sending messages (like reviewing them)
  - Scroll naturally — not instantly to the bottom
  - Wait for pages to fully load before taking action
  - Do not rush through contacts — take natural breaks
  - If you have sent more than 5 messages, pause for 15-30 seconds
"""


# ------------------------------------------------------------
# STATUS
# ------------------------------------------------------------

def get_delay_status() -> dict:
    """Get current session delay status."""
    session = get_session()
    elapsed = time.time() - session.start_time

    return {
        "profile":      session.profile.value,
        "action_count": session.action_count,
        "fatigue":      round(session.fatigue, 2),
        "elapsed_mins": round(elapsed / 60, 1),
    }
