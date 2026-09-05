# 🎂 Birthday Wishes Agent — Project Tree
# Version + Category Combined Structure

BirthdayAgent/
│
├── 📁 .github/
│   └── workflows/
│       └── ci-cd.yml
│
├── 📁 .streamlit/
├── 📁 .vscode/
├── 📁 __pycache__/
├── 📁 deploy/
│   ├── aws/
│   └── gcp/
├── 📁 extension/          # LinkedIn sidebar browser extension
├── 📁 Platforms/          # Per-platform browser automation
│   ├── linkedin.py
│   ├── whatsapp.py
│   ├── facebook.py
│   └── instagram.py
├── 📁 tests/
├── 📁 webapp/             # FastAPI + React full web app
│
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── dockerignore
├── env.example
├── LICENSE
├── README.md
├── requirements.txt
│
# ═══════════════════════════════════════════════════
# BRANCH: main (v8.0) — ALL MERGED
# ═══════════════════════════════════════════════════
│
# ───────────────────────────────────────────────────
# CATEGORY: 🤖 CORE AGENT
# ───────────────────────────────────────────────────
├── agent.py                        # ← Main entry point (all tasks, scheduler, toggles)
│
# ───────────────────────────────────────────────────
# CATEGORY: 🧠 AI & PERSONALIZATION  [v4.0 → v8.0]
# ───────────────────────────────────────────────────
│
│  ── v4.0 ──────────────────────────────────────────
├── sentiment.py                    # Sentiment analysis (happy/sad/stressed/lonely)
├── tone_matching.py                # Communication tone detection & mirroring
├── multilang_reply.py              # Multi-language reply (17 languages)
├── occasion_detection.py           # Life event detection (promotions, marriages)
├── memory.py                       # Year-over-year contact memory
├── personality_profiling.py        # MBTI detection from LinkedIn posts
├── emotional_intelligence.py       # Emotional intelligence scoring
├── predictive_birthday.py          # Predict upcoming birthdays early
│
│  ── v5.0 ──────────────────────────────────────────
├── rag_memory.py                   # ChromaDB vector store — long-term memory
│
│  ── v6.0 ──────────────────────────────────────────
├── wish_scorer.py                  # Wish quality scorer (1-10), auto-retry
├── ab_testing.py                   # A/B testing — 5 styles, auto-learning
├── model_ensemble.py               # GPT-4o / Gemini 2.5 Pro model selector
│
│  ── v7.0 ──────────────────────────────────────────
├── wish_personalization_score.py   # Personalization scorer (name/job/memory/tone)
│
│  ── v8.0 ──────────────────────────────────────────
├── wish_style_memory.py            # Tracks past styles, always picks fresh angle
├── context_aware_opener.py         # LinkedIn activity → hyper-specific opening line
├── wish_variant_generator.py       # 3 variants (formal/casual/funny) side-by-side
├── smart_emoji_calibration.py      # Learns emoji density from reply history
│
# ───────────────────────────────────────────────────
# CATEGORY: ⚙️ AUTOMATION  [v3.0 → v8.0]
# ───────────────────────────────────────────────────
│
│  ── v3.0 ──────────────────────────────────────────
├── auto_reply_followup.py          # Auto-reply to follow-up responses
├── auto_connect.py                 # Auto LinkedIn connect for 2nd-degree wishers
├── post_engagement.py              # LinkedIn post like & comment
├── group_birthday.py               # LinkedIn Group birthday detection
├── birthday_reminder.py            # Birthday reminder email (day before)
├── birthday_eve_reminder.py        # Eve-of-birthday reminder
├── best_time_connect.py            # Activity pattern analyzer
├── dm_campaign.py                  # LinkedIn DM campaign for new connections
├── voice.py                        # Voice message + AI-generated voice wish
├── voice_to_text.py                # Transcribe WhatsApp voice notes
│
│  ── v6.0 ──────────────────────────────────────────
├── auto_timezone_scheduler.py      # Auto timezone detection → 9 AM local send
├── smart_followup.py               # Smart follow-up if no reply in 3 days
├── birthday_miss_tracker.py        # Detect missed birthdays → late wishes
├── personalized_connect.py         # Connection request with note after wishing
├── decay_alert.py                  # Relationship decay alert + auto check-in
│
│  ── v8.0 ──────────────────────────────────────────
├── batch_approve_queue.py          # Morning wish review — bulk approve/reject/send
├── smart_send_time_optimizer.py    # Per-platform activity learning → peak-hour send
├── workflow_builder.py             # IF-THEN-ELSE rule engine (SQLite-backed)
├── auto_pause_on_anomaly.py        # Self-pausing agent on failure spikes
│
# ───────────────────────────────────────────────────
# CATEGORY: 🌐 PLATFORMS  [v3.0 → v6.0]
# ───────────────────────────────────────────────────
│
│  ── v3.0 ──────────────────────────────────────────
├── instagram_birthday_detector.py  # Instagram DM birthday detection
├── instagram_birthdays.py          # Instagram birthday scraper
│
│  ── v6.0 ──────────────────────────────────────────
├── twitter_birthday.py             # Twitter/X birthday mention detection
├── slack_birthday_bot.py           # Slack workspace birthday bot
│
# ───────────────────────────────────────────────────
# CATEGORY: 🔐 SECURITY  [v6.0]
# ───────────────────────────────────────────────────
│
├── two_factor_auth.py              # 2FA — TOTP / SMS / Email OTP
├── proxy_rotation.py               # Proxy rotation → avoid rate limits
├── vpn_switch.py                   # VPN auto-switch when IP blocked
├── browser_fingerprint.py          # Browser fingerprint randomization
├── session_health_monitor.py       # Session health check & auto-renewal
│
# ───────────────────────────────────────────────────
# CATEGORY: 📋 CONTACT MANAGEMENT  [v4.0 → v8.0]
# ───────────────────────────────────────────────────
│
│  ── v4.0 ──────────────────────────────────────────
├── contact_notes.py                # Personal notes per contact
├── connection_tracker.py           # Connection strength tracker
├── contact_categorizer.py          # Auto-categorize by industry/seniority
│
│  ── v5.0 ──────────────────────────────────────────
├── relationship_health.py          # Relationship health score + weekly report
│
│  ── v6.0 ──────────────────────────────────────────
├── contact_importance_scorer.py    # VIP/priority contact scoring
├── network_growth_tracker.py       # Network growth over time
├── smart_reengagement.py           # Re-engagement for cold contacts
│
│  ── v7.0 ──────────────────────────────────────────
├── contact_timeline.py             # Full interaction history per contact
│
│  ── v8.0 ──────────────────────────────────────────
├── reply_sentiment_trend.py        # Reply tone trend (excited→cold) over time
│
# ───────────────────────────────────────────────────
# CATEGORY: 👥 MULTI-ACCOUNT  [v5.0]
# ───────────────────────────────────────────────────
│
├── multi_account.py                # Manage & rotate LinkedIn accounts
├── multi_agent_orchestrator.py     # Multi-agent task orchestration
├── multi_agent_runner.py           # Multi-agent parallel runner
│
# ───────────────────────────────────────────────────
# CATEGORY: 📊 DASHBOARDS & ANALYTICS  [v4.0 → v8.0]
# ───────────────────────────────────────────────────
│
│  ── v4.0 ──────────────────────────────────────────
├── ab_dashboard.py                 # A/B testing dashboard
├── profile_cards.py                # Contact profile cards
├── theme_toggle.py                 # Dark/Light mode helper
│
│  ── v5.0 ──────────────────────────────────────────
├── realtime_dashboard.py           # FastAPI + WebSocket live dashboard
├── onboarding.py                   # First-time setup wizard
│
│  ── v6.0 ──────────────────────────────────────────
├── monthly_report.py               # Monthly activity report
├── engagement_heatmap.py           # Engagement heatmap by hour/day
│
│  ── v7.0 ──────────────────────────────────────────
├── command_center.py               # Unified Command Center (control everything)
├── wish_preview.py                 # Real-time wish preview + live score
├── wish_roi_report.py              # Wish ROI reporting
│
│  ── v8.0 ──────────────────────────────────────────
├── workflow_builder_ui.py          # Visual IF-THEN-ELSE workflow builder
├── insight_report.py               # Weekly/Monthly auto-generated summary
├── platform_roi_comparison.py      # Platform effort vs engagement ROI
├── personalization_score_trend.py  # Wish quality trend over months
│
# ───────────────────────────────────────────────────
# CATEGORY: 🔔 NOTIFICATIONS  [v2.0 → v6.0]
# ───────────────────────────────────────────────────
│
├── notifications.py                # Telegram & Email notifications
├── email_digest.py                 # Weekly email digest
│
# ───────────────────────────────────────────────────
# CATEGORY: 🧬 ADVANCED DETECTION  [v6.0 → v7.0]
# ───────────────────────────────────────────────────
│
├── job_change_detector.py          # Detect job changes from LinkedIn
├── work_anniversary_detector.py    # Work anniversary detection
├── linkedin_post_commenter.py      # Smart LinkedIn post commenter
├── human_delay.py                  # Human-like delay simulation
│
# ───────────────────────────────────────────────────
# CATEGORY: 🔧 UTILITIES
# ───────────────────────────────────────────────────
│
└── auto_learning_reply.py          # Auto-learning reply optimizer


# ═══════════════════════════════════════════════════
# BRANCH HISTORY
# ═══════════════════════════════════════════════════

main          ← 🟢 Active (v8.0) — all features merged
  │
  ├── 8.0    ← ✅ Current dev branch
  │     └── wish_style_memory, context_aware_opener,
  │         wish_variant_generator, smart_emoji_calibration,
  │         workflow_builder (+ui), batch_approve_queue,
  │         smart_send_time_optimizer, auto_pause_on_anomaly,
  │         insight_report, reply_sentiment_trend,
  │         platform_roi_comparison, personalization_score_trend
  │
  ├── 7.0    ← ✅ Merged
  │     └── wish_personalization_score, command_center,
  │         wish_preview, contact_timeline
  │
  ├── 6.0    ← ✅ Merged
  │     └── AI model selector, A/B auto-learning, voice wish,
  │         decay alert, miss tracker, Twitter/X, Slack,
  │         auto timezone, smart follow-up, personalized connect,
  │         2FA, proxy rotation, VPN auto-switch
  │
  ├── 5.0    ← ✅ Stable tag
  │     └── RAG memory, relationship health, A/B testing,
  │         web app, browser extension, weekly digest
  │
  ├── 4.0    ← ✅ Stable tag
  │     └── Personality profiling, sentiment, memory,
  │         wish quality scorer, tone matching, dark mode
  │
  ├── 3.0    ← ✅ Merged
  │     └── WhatsApp, Facebook, Instagram, voice messages,
  │         follow-ups, birthday calendar export
  │
  ├── 2.0    ← ✅ Merged
  │     └── Session management, scheduler, dry run,
  │         Streamlit dashboard, Telegram/Email, SQLite
  │
  └── 1.0    ← ✅ Base
        └── GitHub follower check, LinkedIn birthday reply


# ═══════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════
# Total .py files  : ~85
# Total branches   : 8 (main + 7 version branches)
# Dashboards       : 12 Streamlit pages
# Platforms        : 6 (LinkedIn, WhatsApp, Facebook,
#                      Instagram, Twitter/X, Slack)
# Languages        : 17
# DB tables        : ~20 SQLite tables in agent_history.db
