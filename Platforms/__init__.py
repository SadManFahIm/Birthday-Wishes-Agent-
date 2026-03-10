"""
platforms/
──────────
Multi-platform birthday wish detection and reply module.

Supported platforms:
  - WhatsApp Web
  - Facebook Messenger
  - Instagram DM

Each platform module exposes a single async function:
    run_<platform>_task(llm, browser, dry_run, wish_detection_rules,
                        reply_templates, filter_notice)
"""

from .whatsapp  import run_whatsapp_task
from .facebook  import run_facebook_task
from .instagram import run_instagram_task

__all__ = [
    "run_whatsapp_task",
    "run_facebook_task",
    "run_instagram_task",
]
