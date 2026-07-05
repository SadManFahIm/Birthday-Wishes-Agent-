BirthdayAgent/
│
├── agent.py                          # ← main entry point, এখানেই থাকবে
├── requirements.txt
├── pyproject.toml                    # (নতুন — setup.cfg replace করে)
├── .env
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── dockerignore
├── LICENSE
├── README.md
│
├── 📁 .github/
│   └── workflows/
│       └── ci-cd.yml
│
├── 📁 .streamlit/
├── 📁 .vscode/
├── 📁 deploy/
│   ├── aws/
│   └── gcp/
├── 📁 webapp/                        # FastAPI + React (unchanged)
├── 📁 extension/                     # Browser extension (unchanged)
│
# ════════════════════════════════════════════
# 📁 ai/          ← AI & Personalization
# ════════════════════════════════════════════
├── 📁 ai/
│   ├── __init__.py
│   │
│   ├── # ── Core wish generation ──
│   ├── wish_scorer.py                # from root
│   ├── wish_personalization_score.py # from root
│   ├── wish_style_memory.py          # from root
│   ├── wish_variant_generator.py     # from root
│   │
│   ├── # ── Memory & context ──
│   ├── memory.py                     # from root
│   ├── rag_memory.py                 # from root
│   ├── context_aware_opener.py       # from root
│   │
│   ├── # ── Analysis ──
│   ├── sentiment.py                  # from root
│   ├── tone_matching.py              # from root
│   ├── emotional_intelligence.py     # from root
│   ├── personality_profiling.py      # from root
│   ├── multilang_reply.py            # from root
│   ├── occasion_detection.py         # from root
│   ├── predictive_birthday.py        # from root
│   │
│   ├── # ── Optimization ──
│   ├── ab_testing.py                 # from root
│   ├── model_ensemble.py             # from root
│   └── smart_emoji_calibration.py    # from root
│
# ════════════════════════════════════════════
# 📁 automation/  ← Scheduling & workflows
# ════════════════════════════════════════════
├── 📁 automation/
│   ├── __init__.py
│   │
│   ├── # ── Follow-up & replies ──
│   ├── auto_reply_followup.py        # from root
│   ├── auto_learning_reply.py        # from root
│   ├── smart_followup.py             # from root
│   │
│   ├── # ── Scheduling ──
│   ├── auto_timezone_scheduler.py    # from root
│   ├── smart_send_time_optimizer.py  # from root
│   ├── birthday_reminder.py          # from root
│   ├── birthday_eve_reminder.py      # from root
│   ├── birthday_miss_tracker.py      # from root
│   │
│   ├── # ── Connections & engagement ──
│   ├── auto_connect.py               # from root
│   ├── personalized_connect.py       # from root
│   ├── post_engagement.py            # from root
│   ├── group_birthday.py             # from root
│   ├── dm_campaign.py                # from root
│   │
│   ├── # ── Workflow engine ──
│   ├── workflow_builder.py           # from root
│   └── auto_pause_on_anomaly.py      # from root
│
# ════════════════════════════════════════════
# 📁 platforms/   ← Per-platform logic
# ════════════════════════════════════════════
├── 📁 platforms/
│   ├── __init__.py
│   ├── linkedin.py                   # already here
│   ├── whatsapp.py                   # already here
│   ├── facebook.py                   # already here
│   ├── instagram.py                  # already here
│   ├── twitter_birthday.py           # from root
│   ├── slack_birthday_bot.py         # from root
│   ├── instagram_birthday_detector.py# from root
│   └── instagram_birthdays.py        # from root
│
# ════════════════════════════════════════════
# 📁 contacts/    ← Contact & relationship
# ════════════════════════════════════════════
├── 📁 contacts/
│   ├── __init__.py
│   ├── contact_notes.py              # from root
│   ├── contact_categorizer.py        # from root
│   ├── contact_importance_scorer.py  # from root
│   ├── contact_timeline.py           # from root
│   ├── connection_tracker.py         # from root
│   ├── relationship_health.py        # from root
│   ├── decay_alert.py                # from root
│   ├── network_growth_tracker.py     # from root
│   ├── smart_reengagement.py         # from root
│   └── reply_sentiment_trend.py      # from root
│
# ════════════════════════════════════════════
# 📁 security/    ← Auth, proxy, session
# ════════════════════════════════════════════
├── 📁 security/
│   ├── __init__.py
│   ├── two_factor_auth.py            # from root
│   ├── proxy_rotation.py             # from root
│   ├── vpn_switch.py                 # from root
│   ├── browser_fingerprint.py        # from root
│   └── session_health_monitor.py     # from root
│
# ════════════════════════════════════════════
# 📁 detection/   ← Event & activity detect
# ════════════════════════════════════════════
├── 📁 detection/
│   ├── __init__.py
│   ├── job_change_detector.py        # from root
│   ├── work_anniversary_detector.py  # from root
│   ├── linkedin_post_commenter.py    # from root
│   └── human_delay.py               # from root
│
# ════════════════════════════════════════════
# 📁 notifications/  ← Alerts & messages
# ════════════════════════════════════════════
├── 📁 notifications/
│   ├── __init__.py
│   ├── notifications.py              # from root
│   ├── email_digest.py               # from root
│   └── voice.py                      # from root
│       voice_to_text.py              # from root
│
# ════════════════════════════════════════════
# 📁 multi_account/  ← Multi-account mgmt
# ════════════════════════════════════════════
├── 📁 multi_account/
│   ├── __init__.py
│   ├── multi_account.py              # from root
│   ├── multi_agent_orchestrator.py   # from root
│   └── multi_agent_runner.py         # from root
│
# ════════════════════════════════════════════
# 📁 dashboards/  ← All Streamlit pages
# ════════════════════════════════════════════
├── 📁 dashboards/
│   ├── __init__.py
│   │
│   ├── # ── v7.0 dashboards ──
│   ├── command_center.py             # from root
│   ├── wish_preview.py               # from root
│   ├── wish_roi_report.py            # from root
│   │
│   ├── # ── v8.0 dashboards ──
│   ├── batch_approve_queue.py        # from root
│   ├── workflow_builder_ui.py        # from root
│   ├── insight_report.py             # from root
│   ├── platform_roi_comparison.py    # from root
│   ├── personalization_score_trend.py# from root
│   │
│   ├── # ── Analytics ──
│   ├── analytics.py                  # from root
│   ├── ab_dashboard.py               # from root
│   ├── engagement_heatmap.py         # from root
│   ├── monthly_report.py             # from root
│   │
│   ├── # ── Other UI ──
│   ├── profile_cards.py              # from root
│   ├── realtime_dashboard.py         # from root
│   ├── onboarding.py                 # from root
│   ├── mobile_app.py                 # from root
│   ├── theme_toggle.py               # from root
│   └── dashboard.py                  # from root (legacy)
│
# ════════════════════════════════════════════
# 📁 config/      ← Settings & constants
# ════════════════════════════════════════════
├── 📁 config/
│   ├── __init__.py
│   └── settings.py                   # (নতুন — .env load করবে)
│
# ════════════════════════════════════════════
# 📁 tests/
# ════════════════════════════════════════════
└── 📁 tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_wish_scorer.py
    │   ├── test_sentiment.py
    │   └── test_emoji_calibration.py
    └── integration/
        ├── test_agent.py
        └── test_api.py
