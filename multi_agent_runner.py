"""
multi_agent_runner.py
---------------------
Multi-Agent Architecture for Birthday Wishes Agent.

Runs separate AI agents per platform in parallel:
  - LinkedIn Agent   : birthday detection, wishing, replying
  - WhatsApp Agent   : birthday replies, voice messages
  - Facebook Agent   : birthday replies
  - Instagram Agent  : birthday replies
  - Slack Agent      : workspace birthday bot
  - Twitter Agent    : birthday mention detection

All agents run concurrently using asyncio.gather().
Each agent has its own browser context and task queue.
Results are collected and merged into a unified report.

vs multi_agent_orchestrator.py:
  - This file focuses on PLATFORM parallelism
  - Each platform gets its own dedicated agent instance
  - Agents are isolated — one crash doesn't stop others
  - Configurable: enable/disable per platform

Usage:
    from multi_agent_runner import (
        MultiAgentRunner,
        run_all_platforms_parallel,
    )

    results = await run_all_platforms_parallel(
        llm=llm,
        browser=browser,
        dry_run=True,
    )
"""

import asyncio
import logging
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# AGENT RESULT
# ------------------------------------------------------------

@dataclass
class AgentResult:
    """Result from a single platform agent."""
    platform:    str
    success:     bool
    wished:      int = 0
    replied:     int = 0
    errors:      int = 0
    skipped:     int = 0
    duration_s:  float = 0.0
    notes:       str = ""
    error_msg:   str = ""


# ------------------------------------------------------------
# PLATFORM AGENTS
# ------------------------------------------------------------

async def run_linkedin_agent(
    llm,
    browser,
    username: str,
    password: str,
    dry_run: bool = True,
    already_logged_in: bool = False,
) -> AgentResult:
    """LinkedIn platform agent — birthday detection + wishing + replying."""
    start = datetime.now()
    logger.info("[LinkedIn Agent] Starting...")

    try:
        from platforms import run_linkedin_birthday_with_custom_wish

        result = await run_linkedin_birthday_with_custom_wish(
            llm=llm,
            browser=browser,
            dry_run=dry_run,
            username=username,
            password=password,
            already_logged_in=already_logged_in,
            filter_notice="",
            wish_detection_rules="",
        )

        duration = (datetime.now() - start).total_seconds()
        logger.info("[LinkedIn Agent] Done in %.1fs", duration)

        return AgentResult(
            platform="LinkedIn",
            success=True,
            wished=1,
            duration_s=duration,
        )

    except Exception as e:
        logger.error("[LinkedIn Agent] Failed: %s", e)
        return AgentResult(
            platform="LinkedIn",
            success=False,
            error_msg=str(e),
            duration_s=(datetime.now() - start).total_seconds(),
        )


async def run_whatsapp_agent(
    llm,
    browser,
    dry_run: bool = True,
) -> AgentResult:
    """WhatsApp platform agent — birthday replies + voice messages."""
    start = datetime.now()
    logger.info("[WhatsApp Agent] Starting...")

    try:
        from platforms import run_whatsapp_task

        await run_whatsapp_task(
            llm=llm,
            browser=browser,
            dry_run=dry_run,
            wish_detection_rules="",
            reply_templates=[
                "Thanks so much, {name}! Really means a lot!",
            ],
            filter_notice="",
            voice_enabled=False,
            voice_engine="gtts",
        )

        duration = (datetime.now() - start).total_seconds()
        logger.info("[WhatsApp Agent] Done in %.1fs", duration)
        return AgentResult(platform="WhatsApp", success=True, duration_s=duration)

    except Exception as e:
        logger.error("[WhatsApp Agent] Failed: %s", e)
        return AgentResult(
            platform="WhatsApp",
            success=False,
            error_msg=str(e),
            duration_s=(datetime.now() - start).total_seconds(),
        )


async def run_facebook_agent(
    llm,
    browser,
    dry_run: bool = True,
) -> AgentResult:
    """Facebook platform agent — birthday replies."""
    start = datetime.now()
    logger.info("[Facebook Agent] Starting...")

    try:
        from platforms import run_facebook_task

        await run_facebook_task(
            llm=llm,
            browser=browser,
            dry_run=dry_run,
            wish_detection_rules="",
            reply_templates=[
                "Thanks so much, {name}! Really means a lot!",
            ],
            filter_notice="",
        )

        duration = (datetime.now() - start).total_seconds()
        logger.info("[Facebook Agent] Done in %.1fs", duration)
        return AgentResult(platform="Facebook", success=True, duration_s=duration)

    except Exception as e:
        logger.error("[Facebook Agent] Failed: %s", e)
        return AgentResult(
            platform="Facebook",
            success=False,
            error_msg=str(e),
            duration_s=(datetime.now() - start).total_seconds(),
        )


async def run_instagram_agent(
    llm,
    browser,
    dry_run: bool = True,
) -> AgentResult:
    """Instagram platform agent — birthday replies."""
    start = datetime.now()
    logger.info("[Instagram Agent] Starting...")

    try:
        from platforms import run_instagram_task

        await run_instagram_task(
            llm=llm,
            browser=browser,
            dry_run=dry_run,
            wish_detection_rules="",
            reply_templates=[
                "Thanks so much, {name}! Really means a lot!",
            ],
            filter_notice="",
        )

        duration = (datetime.now() - start).total_seconds()
        logger.info("[Instagram Agent] Done in %.1fs", duration)
        return AgentResult(platform="Instagram", success=True, duration_s=duration)

    except Exception as e:
        logger.error("[Instagram Agent] Failed: %s", e)
        return AgentResult(
            platform="Instagram",
            success=False,
            error_msg=str(e),
            duration_s=(datetime.now() - start).total_seconds(),
        )


async def run_slack_agent(dry_run: bool = True) -> AgentResult:
    """Slack platform agent — workspace birthday bot."""
    start = datetime.now()
    logger.info("[Slack Agent] Starting...")

    try:
        from slack_birthday_bot import run_slack_birthday_bot

        result = await run_slack_birthday_bot(
            dry_run=dry_run,
            send_dm=True,
            send_channel=True,
        )

        duration = (datetime.now() - start).total_seconds()
        wished   = result.get("total_wished", 0)
        logger.info("[Slack Agent] Done in %.1fs | wished=%d", duration, wished)
        return AgentResult(
            platform="Slack",
            success=True,
            wished=wished,
            duration_s=duration,
        )

    except Exception as e:
        logger.error("[Slack Agent] Failed: %s", e)
        return AgentResult(
            platform="Slack",
            success=False,
            error_msg=str(e),
            duration_s=(datetime.now() - start).total_seconds(),
        )


async def run_twitter_agent(dry_run: bool = True) -> AgentResult:
    """Twitter/X agent — birthday mention detection."""
    start = datetime.now()
    logger.info("[Twitter Agent] Starting...")

    try:
        from twitter_birthday import run_twitter_birthday_detection

        result = await run_twitter_birthday_detection(dry_run=dry_run)

        duration = (datetime.now() - start).total_seconds()
        found    = result.get("total_found", 0)
        logger.info("[Twitter Agent] Done in %.1fs | found=%d", duration, found)
        return AgentResult(
            platform="Twitter",
            success=True,
            wished=found,
            duration_s=duration,
        )

    except Exception as e:
        logger.error("[Twitter Agent] Failed: %s", e)
        return AgentResult(
            platform="Twitter",
            success=False,
            error_msg=str(e),
            duration_s=(datetime.now() - start).total_seconds(),
        )


# ------------------------------------------------------------
# MULTI-AGENT RUNNER
# ------------------------------------------------------------

class MultiAgentRunner:
    """
    Runs platform agents in parallel.
    Each platform is isolated — one failure doesn't stop others.
    """

    def __init__(
        self,
        llm,
        browser,
        username: str = "",
        password: str = "",
        dry_run: bool = True,
        enable_linkedin:  bool = True,
        enable_whatsapp:  bool = True,
        enable_facebook:  bool = True,
        enable_instagram: bool = True,
        enable_slack:     bool = False,
        enable_twitter:   bool = False,
        already_logged_in: bool = False,
    ):
        self.llm              = llm
        self.browser          = browser
        self.username         = username
        self.password         = password
        self.dry_run          = dry_run
        self.already_logged_in = already_logged_in

        self.enabled = {
            "LinkedIn":  enable_linkedin,
            "WhatsApp":  enable_whatsapp,
            "Facebook":  enable_facebook,
            "Instagram": enable_instagram,
            "Slack":     enable_slack,
            "Twitter":   enable_twitter,
        }

    def _build_tasks(self) -> list:
        """Build list of coroutines for enabled platforms."""
        tasks = []

        if self.enabled["LinkedIn"]:
            tasks.append(run_linkedin_agent(
                self.llm, self.browser,
                self.username, self.password,
                self.dry_run, self.already_logged_in,
            ))

        if self.enabled["WhatsApp"]:
            tasks.append(run_whatsapp_agent(
                self.llm, self.browser, self.dry_run
            ))

        if self.enabled["Facebook"]:
            tasks.append(run_facebook_agent(
                self.llm, self.browser, self.dry_run
            ))

        if self.enabled["Instagram"]:
            tasks.append(run_instagram_agent(
                self.llm, self.browser, self.dry_run
            ))

        if self.enabled["Slack"]:
            tasks.append(run_slack_agent(self.dry_run))

        if self.enabled["Twitter"]:
            tasks.append(run_twitter_agent(self.dry_run))

        return tasks

    async def run_parallel(self) -> list[AgentResult]:
        """
        Run all enabled platform agents in parallel.
        Returns list of AgentResult — one per platform.
        """
        tasks = self._build_tasks()

        if not tasks:
            logger.warning("No platforms enabled.")
            return []

        enabled_names = [p for p, e in self.enabled.items() if e]
        logger.info(
            "Starting %d platform agents in parallel: %s",
            len(tasks), ", ".join(enabled_names),
        )

        start   = datetime.now()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total   = (datetime.now() - start).total_seconds()

        agent_results = []
        for r in results:
            if isinstance(r, Exception):
                agent_results.append(AgentResult(
                    platform="Unknown",
                    success=False,
                    error_msg=str(r),
                ))
            else:
                agent_results.append(r)

        logger.info(
            "All agents done in %.1fs | success=%d/%d",
            total,
            sum(1 for r in agent_results if r.success),
            len(agent_results),
        )

        return agent_results

    async def run_sequential(self) -> list[AgentResult]:
        """
        Run platform agents one by one (fallback if parallel causes issues).
        """
        tasks   = self._build_tasks()
        results = []

        for task in tasks:
            try:
                result = await task
                results.append(result)
            except Exception as e:
                results.append(AgentResult(
                    platform="Unknown",
                    success=False,
                    error_msg=str(e),
                ))

        return results


# ------------------------------------------------------------
# REPORT
# ------------------------------------------------------------

def build_multi_agent_report(results: list[AgentResult]) -> str:
    """Build human-readable multi-agent run report."""
    if not results:
        return "No agent results."

    total_wished  = sum(r.wished for r in results)
    total_replied = sum(r.replied for r in results)
    total_errors  = sum(r.errors for r in results)
    success_count = sum(1 for r in results if r.success)

    lines = [
        "Multi-Agent Run Report",
        "-" * 55,
        f"  Platforms run  : {len(results)}",
        f"  Successful     : {success_count}/{len(results)}",
        f"  Total wished   : {total_wished}",
        f"  Total replied  : {total_replied}",
        f"  Total errors   : {total_errors}",
        "-" * 55,
        "",
        f"  {'Platform':<12} {'Status':<8} {'Wished':>6} {'Time':>8}",
        "  " + "-" * 40,
    ]

    for r in results:
        status = "OK" if r.success else "FAIL"
        lines.append(
            f"  {r.platform:<12} {status:<8} {r.wished:>6} "
            f"{r.duration_s:>6.1f}s"
        )
        if not r.success and r.error_msg:
            lines.append(f"    Error: {r.error_msg[:50]}")

    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ------------------------------------------------------------
# CONVENIENCE FUNCTION
# ------------------------------------------------------------

async def run_all_platforms_parallel(
    llm,
    browser,
    username: str = "",
    password: str = "",
    dry_run: bool = True,
    already_logged_in: bool = False,
    enable_slack: bool = False,
    enable_twitter: bool = False,
) -> dict:
    """
    Convenience function to run all platforms in parallel.
    Call this from agent.py instead of running platforms one by one.

    Returns:
        Dict with results and report.
    """
    runner = MultiAgentRunner(
        llm=llm,
        browser=browser,
        username=username,
        password=password,
        dry_run=dry_run,
        already_logged_in=already_logged_in,
        enable_slack=enable_slack,
        enable_twitter=enable_twitter,
    )

    results = await runner.run_parallel()
    report  = build_multi_agent_report(results)

    logger.info("\n%s", report)

    return {
        "results": [r.__dict__ for r in results],
        "report":  report,
        "success": all(r.success for r in results),
    }
