"""
multi_agent_orchestrator.py
============================
Feature 4: Multi-Agent Architecture
-------------------------------------
Orchestrator agent টা parallel এ multiple sub-agents চালায়।
প্রতিটা sub-agent একটা নির্দিষ্ট কাজের জন্য responsible।
asyncio.gather() দিয়ে সব একসাথে run হয় → overall speed অনেক বাড়ে।

Usage:
    from multi_agent_orchestrator import OrchestratorAgent
    orchestrator = OrchestratorAgent(llm, browser, config)
    await orchestrator.run_all_parallel()
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 1. SUB-AGENT STATUS
# ──────────────────────────────────────────────

class AgentStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCESS   = "success"
    FAILED    = "failed"
    SKIPPED   = "skipped"


# ──────────────────────────────────────────────
# 2. SUB-AGENT RESULT
# ──────────────────────────────────────────────

@dataclass
class SubAgentResult:
    name:       str
    status:     AgentStatus
    result:     Any  = None
    error:      str  = ""
    duration_s: float = 0.0

    def __str__(self):
        icon = {
            AgentStatus.SUCCESS: "✅",
            AgentStatus.FAILED:  "❌",
            AgentStatus.SKIPPED: "⏭️",
            AgentStatus.RUNNING: "⏳",
            AgentStatus.PENDING: "🕐",
        }[self.status]
        return (
            f"{icon} [{self.name}] {self.status.value.upper()} "
            f"({self.duration_s:.1f}s)"
            + (f" — {self.error}" if self.error else "")
        )


# ──────────────────────────────────────────────
# 3. ORCHESTRATOR CONFIG
# ──────────────────────────────────────────────

@dataclass
class OrchestratorConfig:
    """কোন sub-agents চালাবে তা এখানে toggle করো।"""

    # ── Platform toggles ─────────────────────
    enable_linkedin:        bool = True
    enable_whatsapp:        bool = True
    enable_facebook:        bool = True
    enable_instagram:       bool = True

    # ── Feature toggles ──────────────────────
    enable_birthday_detect: bool = True
    enable_linkedin_reply:  bool = True
    enable_followup:        bool = True
    enable_sentiment_reply: bool = True
    enable_post_engagement: bool = True
    enable_occasion_detect: bool = True
    enable_group_birthday:  bool = True
    enable_auto_reply:      bool = True
    enable_memory_wish:     bool = True
    enable_rag_wish:        bool = False   # heavy; off by default

    # ── Concurrency control ───────────────────
    # Browser-based tasks একসাথে একটা browser share করে।
    # Browser-independent tasks (notifications, DB) বেশি parallel চলতে পারে।
    max_browser_concurrency: int = 3   # একসাথে সর্বোচ্চ browser tasks
    max_light_concurrency:   int = 10  # non-browser tasks এর limit

    # ── Retry ─────────────────────────────────
    retries: int = 2
    retry_delay_s: int = 5

    # ── Dry run forwarded from agent.py ───────
    dry_run: bool = True


# ──────────────────────────────────────────────
# 4. ORCHESTRATOR AGENT
# ──────────────────────────────────────────────

class OrchestratorAgent:
    """
    Orchestrator যে সব sub-agents কে manage করে।

    Architecture:
    ┌─────────────────────────────────────────────┐
    │            OrchestratorAgent                │
    │  ┌──────────────────────────────────────┐   │
    │  │         Task Queue / Plan            │   │
    │  └──────────────────────────────────────┘   │
    │       │              │             │         │
    │  ┌────▼────┐   ┌─────▼────┐  ┌────▼────┐   │
    │  │ Sub-    │   │  Sub-    │  │  Sub-   │   │
    │  │ Agent 1 │   │  Agent 2 │  │  Agent 3│   │
    │  │LinkedIn │   │WhatsApp  │  │Facebook │   │
    │  │Birthday │   │Reply     │  │Reply    │   │
    │  └─────────┘   └──────────┘  └─────────┘   │
    │       │              │             │         │
    │  ┌────▼──────────────▼─────────────▼────┐   │
    │  │         Result Aggregator            │   │
    │  └──────────────────────────────────────┘   │
    └─────────────────────────────────────────────┘
    """

    def __init__(self, llm, browser, config: OrchestratorConfig, agent_module):
        """
        Parameters
        ----------
        llm          : LangChain LLM instance (agent.py থেকে pass করো)
        browser      : browser_use Browser instance
        config       : OrchestratorConfig
        agent_module : agent.py module (এর functions call করব)
        """
        self.llm    = llm
        self.browser = browser
        self.cfg    = config
        self.mod    = agent_module  # agent.py এর functions

        # Semaphores for concurrency limiting
        self._browser_sem = asyncio.Semaphore(config.max_browser_concurrency)
        self._light_sem   = asyncio.Semaphore(config.max_light_concurrency)

        self.results: list[SubAgentResult] = []

    # ── Internal runner ───────────────────────

    async def _run_sub_agent(
        self,
        name: str,
        coro_factory,
        use_browser: bool = True,
    ) -> SubAgentResult:
        """
        একটা sub-agent run করে।
        Semaphore দিয়ে concurrency limit enforce করে।
        Retry logic built-in।
        """
        sem = self._browser_sem if use_browser else self._light_sem
        start = time.monotonic()

        async with sem:
            logger.info("🤖 [Orchestrator] Starting sub-agent: %s", name)
            for attempt in range(1, self.cfg.retries + 1):
                try:
                    result = await coro_factory()
                    duration = time.monotonic() - start
                    r = SubAgentResult(
                        name=name,
                        status=AgentStatus.SUCCESS,
                        result=result,
                        duration_s=duration,
                    )
                    logger.info("✅ [%s] Done in %.1fs", name, duration)
                    return r
                except Exception as e:
                    logger.warning(
                        "⚠️ [%s] Attempt %d/%d failed: %s",
                        name, attempt, self.cfg.retries, e,
                    )
                    if attempt < self.cfg.retries:
                        await asyncio.sleep(self.cfg.retry_delay_s)

            duration = time.monotonic() - start
            return SubAgentResult(
                name=name,
                status=AgentStatus.FAILED,
                error=str(e),
                duration_s=duration,
            )

    def _skip(self, name: str) -> SubAgentResult:
        return SubAgentResult(name=name, status=AgentStatus.SKIPPED)

    # ── Sub-agent definitions ─────────────────

    def _make_sub_agents(self) -> list[tuple[str, Any, bool]]:
        """
        Returns list of (name, coro_factory, use_browser) tuples.
        config এর toggles দেখে কোনগুলো run হবে বা skip হবে।
        """
        m   = self.mod   # agent.py module
        cfg = self.cfg

        tasks = []

        # ── LinkedIn Birthday Detection ──
        if cfg.enable_linkedin and cfg.enable_birthday_detect:
            tasks.append((
                "LinkedIn-BirthdayDetection",
                lambda: m.run_birthday_detection_task(),
                True,
            ))

        # ── LinkedIn Reply to Wishes ──
        if cfg.enable_linkedin and cfg.enable_linkedin_reply:
            tasks.append((
                "LinkedIn-ReplyToWishes",
                lambda: m.run_linkedin_reply_task(),
                True,
            ))

        # ── WhatsApp Reply ──
        if cfg.enable_whatsapp:
            tasks.append((
                "WhatsApp-Reply",
                lambda: m.run_whatsapp_reply_task(),
                True,
            ))

        # ── Facebook Reply ──
        if cfg.enable_facebook:
            tasks.append((
                "Facebook-Reply",
                lambda: m.run_facebook_reply_task(),
                True,
            ))

        # ── Instagram Reply ──
        if cfg.enable_instagram:
            tasks.append((
                "Instagram-Reply",
                lambda: m.run_instagram_reply_task(),
                True,
            ))

        # ── Follow-up Messages ──
        if cfg.enable_followup:
            tasks.append((
                "FollowUp-Messages",
                lambda: m.run_followup_task(),
                True,
            ))

        # ── Sentiment Reply + Auto Connect ──
        if cfg.enable_sentiment_reply:
            tasks.append((
                "Sentiment-AutoConnect",
                lambda: m.run_sentiment_reply_task(),
                True,
            ))

        # ── Post Engagement ──
        if cfg.enable_post_engagement:
            tasks.append((
                "Post-Engagement",
                lambda: m.run_post_engagement_task(),
                True,
            ))

        # ── Occasion Detection ──
        if cfg.enable_occasion_detect:
            tasks.append((
                "Occasion-Detection",
                lambda: m.run_occasion_detection_task(),
                True,
            ))

        # ── Group Birthday ──
        if cfg.enable_group_birthday:
            tasks.append((
                "Group-Birthday",
                lambda: m.run_group_birthday_task(),
                True,
            ))

        # ── Auto Reply Follow-up ──
        if cfg.enable_auto_reply:
            tasks.append((
                "Auto-Reply-FollowUp",
                lambda: m.run_auto_reply_task(),
                True,
            ))

        # ── Memory-Aware Wishes (browser, but lighter) ──
        if cfg.enable_memory_wish:
            tasks.append((
                "Memory-Aware-Wishes",
                lambda: m.run_memory_wish_task(),
                True,
            ))

        # ── RAG Wishes ──
        if cfg.enable_rag_wish:
            tasks.append((
                "RAG-Wishes",
                lambda: m.run_rag_wish_task(),
                True,
            ))

        return tasks

    # ── Main orchestration entry point ────────

    async def run_all_parallel(self) -> list[SubAgentResult]:
        """
        সব sub-agents কে parallel এ run করে।
        asyncio.gather() ব্যবহার করে — সব coroutine একসাথে শুরু হয়।
        Semaphore দিয়ে browser concurrency নিয়ন্ত্রণ করা হয়।
        """
        wall_start = time.monotonic()
        logger.info("=" * 60)
        logger.info("🎯 [Orchestrator] Starting parallel multi-agent run")
        logger.info("   DRY_RUN      : %s", self.cfg.dry_run)
        logger.info("   Browser limit: %d concurrent tasks",
                    self.cfg.max_browser_concurrency)
        logger.info("=" * 60)

        sub_agents = self._make_sub_agents()

        if not sub_agents:
            logger.warning("⚠️ [Orchestrator] No sub-agents enabled. Check config.")
            return []

        logger.info("📋 [Orchestrator] %d sub-agents queued:", len(sub_agents))
        for name, _, _ in sub_agents:
            logger.info("   • %s", name)

        # Launch all sub-agent coroutines at once
        coros = [
            self._run_sub_agent(name, factory, use_browser)
            for name, factory, use_browser in sub_agents
        ]

        self.results = await asyncio.gather(*coros, return_exceptions=False)

        wall_total = time.monotonic() - wall_start
        self._print_summary(wall_total)
        return self.results

    # ── Selective parallel run ────────────────

    async def run_selected_parallel(
        self, agent_names: list[str]
    ) -> list[SubAgentResult]:
        """
        Specific sub-agents গুলো parallel এ run করো।
        যেমন: await orchestrator.run_selected_parallel(
                   ["LinkedIn-BirthdayDetection", "WhatsApp-Reply"])
        """
        all_agents = {name: (factory, use_browser)
                      for name, factory, use_browser in self._make_sub_agents()}

        chosen = []
        for name in agent_names:
            if name in all_agents:
                factory, use_browser = all_agents[name]
                chosen.append(self._run_sub_agent(name, factory, use_browser))
            else:
                logger.warning("⚠️ Unknown sub-agent: %s — skipping", name)

        if not chosen:
            return []

        self.results = await asyncio.gather(*chosen, return_exceptions=False)
        self._print_summary(0)
        return self.results

    # ── Sequential fallback ───────────────────

    async def run_all_sequential(self) -> list[SubAgentResult]:
        """
        Sequential fallback — debugging বা rate limit issue হলে এটা ব্যবহার করো।
        আগের daily_job() এর মতোই কাজ করে।
        """
        logger.info("🔄 [Orchestrator] Running in SEQUENTIAL mode (fallback)")
        results = []
        for name, factory, use_browser in self._make_sub_agents():
            r = await self._run_sub_agent(name, factory, use_browser)
            results.append(r)
        self.results = results
        self._print_summary(0)
        return results

    # ── Summary printer ───────────────────────

    def _print_summary(self, wall_time: float):
        success = [r for r in self.results if r.status == AgentStatus.SUCCESS]
        failed  = [r for r in self.results if r.status == AgentStatus.FAILED]
        skipped = [r for r in self.results if r.status == AgentStatus.SKIPPED]

        logger.info("=" * 60)
        logger.info("📊 [Orchestrator] Run Complete")
        if wall_time > 0:
            logger.info("   Total wall time : %.1f seconds", wall_time)
            total_agent_time = sum(r.duration_s for r in self.results)
            if wall_time > 0:
                speedup = total_agent_time / wall_time
                logger.info("   Agent work time : %.1f seconds", total_agent_time)
                logger.info("   Speedup factor  : %.1fx (vs sequential)", speedup)
        logger.info("   ✅ Success : %d", len(success))
        logger.info("   ❌ Failed  : %d", len(failed))
        logger.info("   ⏭️ Skipped : %d", len(skipped))
        logger.info("-" * 60)
        for r in self.results:
            logger.info("   %s", r)
        logger.info("=" * 60)

        if failed:
            logger.error(
                "⚠️ Failed sub-agents: %s",
                ", ".join(r.name for r in failed),
            )

    # ── Result helpers ────────────────────────

    def get_result(self, name: str) -> SubAgentResult | None:
        return next((r for r in self.results if r.name == name), None)

    def all_succeeded(self) -> bool:
        return all(r.status == AgentStatus.SUCCESS for r in self.results
                   if r.status != AgentStatus.SKIPPED)


# ──────────────────────────────────────────────
# 5. DAILY JOB REPLACEMENT
# ──────────────────────────────────────────────

async def parallel_daily_job(llm, browser, dry_run: bool = True):
    """
    agent.py এর daily_job() কে replace করে।
    এটাকে scheduler এ plug করো।

    agent.py তে এভাবে ব্যবহার করো:
    ─────────────────────────────────────
    from multi_agent_orchestrator import parallel_daily_job

    async def run_scheduler():
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            lambda: parallel_daily_job(llm, browser, DRY_RUN),
            trigger="cron",
            hour=SCHEDULE_HOUR,
            minute=SCHEDULE_MINUTE,
        )
        scheduler.start()
        ...
    ─────────────────────────────────────
    """
    import agent as agent_module  # agent.py কে module হিসেবে import

    cfg = OrchestratorConfig(dry_run=dry_run)
    orchestrator = OrchestratorAgent(
        llm=llm,
        browser=browser,
        config=cfg,
        agent_module=agent_module,
    )

    return await orchestrator.run_all_parallel()