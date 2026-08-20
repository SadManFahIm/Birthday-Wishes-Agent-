<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/version-10.0-f78166" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/LangGraph-workflow-blueviolet" />
  <img src="https://img.shields.io/badge/Claude-Sonnet-orange" />
  <img src="https://img.shields.io/badge/Gemini-2.5%20Flash-blue" />
  <img src="https://img.shields.io/badge/Streamlit-dashboards-FF4B4B?logo=streamlit&logoColor=white" />
  <img src="https://img.shields.io/badge/Firebase-FCM-FFCA28?logo=firebase&logoColor=black" />
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/Kubernetes-ready-326CE5?logo=kubernetes&logoColor=white" />
  <img src="https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white" />
  <img src="https://img.shields.io/badge/platforms-10-blue" />
  <img src="https://img.shields.io/badge/flake8-passing-brightgreen" />
</p>

<h1 align="center">🎂 Birthday Wishes Agent</h1>

<p align="center">
  <strong>An AI-powered relationship management agent that automates personalized birthday wishes across 10+ platforms — with memory, sentiment awareness, autonomous decision-making, GDPR compliance, and a full analytics suite.</strong>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-features">Features</a> •
  <a href="#%EF%B8%8F-project-structure">Structure</a> •
  <a href="#-branch-guide">Branches</a> •
  <a href="#-configuration">Config</a> •
  <a href="#-changelog">Changelog</a>
</p>

---

## 📝 Introduction

What started as a simple LinkedIn birthday reply bot has evolved into a **production-grade AI agent system** spanning 10+ social platforms. The agent detects birthdays, generates hyper-personalized wishes using multi-model AI (Claude Sonnet, Gemini 2.5 Flash, GPT-4o), tracks relationships over time, autonomously decides the best outreach strategy, and provides a comprehensive analytics dashboard — all while staying GDPR-compliant and tamper-evident.

**v10.0** introduces a LangGraph-powered workflow engine, MCP server integration (14 tools for Claude Desktop), ML-based churn prediction, ROI forecasting, GDPR compliance, JWT authentication, Firebase push notifications, per-platform rate limiting, and a daily morning briefing system.

---

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/SadManFahIm/Birthday-Wishes-Agent-.git
cd Birthday-Wishes-Agent-

# Virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env            # Edit with your API keys

# Run
python agent.py                 # Main agent
streamlit run churn_predictor.py  # Any dashboard module
```

**Docker:**
```bash
docker-compose up --build -d
```

---

## ✨ Features

### 🧬 v10.0 — Intelligence, Privacy & Operations

| Module | Description |
|--------|-------------|
| **LangGraph Workflow Engine** | State-machine orchestration with conditional routing, parallel execution, and checkpoint persistence |
| **MCP Server** | 14-tool server for Claude Desktop — query contacts, trigger wishes, check stats, all from chat |
| **Multi-Model Config** | Unified interface across Claude Sonnet 4.6, Gemini 2.5 Flash, GPT-4o with automatic fallback |
| **Autonomous Agent** | Self-governing decision engine — scores contacts, picks actions (wish/follow-up/check-in/skip), daily cap enforcement |
| **Churn Predictor** | ML-based churn scoring with decay curves, risk factors, and automated alerts |
| **ROI Forecasting** | Revenue attribution and pipeline forecasting per contact and platform |
| **Wish Performance Predictor** | Predicts reply probability, optimal send time, and best wish style per contact |
| **Interest Graph** | Maps contact interests and relationship clusters as a weighted graph |
| **Vector Memory** | Semantic search across all past interactions using embedded vectors |
| **Conversation Summary** | Auto-summarizes conversation threads for quick context |
| **GDPR Compliance** | Consent tracking, right-to-forget (22 tables), data retention policies, data export (Article 20) |
| **Audit Trail** | Tamper-evident SHA-256 hash-chain logging of every data operation across all modules |
| **JWT Auth** | Zero-dependency JWT authentication — PBKDF2 passwords, RBAC (admin/manager/viewer), token refresh, account lockout |
| **Push Notifications** | Firebase FCM mobile push — 10 categories, topic subscriptions, quiet hours, delivery tracking |
| **Rate Limit Dashboard** | Per-platform quota tracking (daily/hourly/per-minute) across 10 platforms with cooldown enforcement |
| **Morning Briefing** | Daily digest — today's birthdays, pending tasks, agent status, rate limits, alerts — delivered via push |
| **Engagement Calendar** | Visual calendar of all outreach activity and upcoming birthdays |
| **Email Outreach** | Templated email campaigns with tracking |
| **Google Calendar Sync** | Two-way sync of birthdays and reminders |
| **Notion Sync** | Pushes contact data and wish history to Notion databases |
| **CRM Sync** | Bidirectional sync with HubSpot and Salesforce |

### 🤖 v9.0 — Autonomy, Rich Media & Scale

| Feature | Description |
|---------|-------------|
| **Self-Improving Agent** | Reviews outcomes and auto-tunes prompts and style choices over time |
| **Multi-Model Consensus** | Runs wishes through multiple LLMs, reconciles into a single high-confidence result |
| **Voice Cloning** | Clones user's voice (with consent) for personalized voice notes |
| **AI Video Message** | Generates personalized video birthday messages per contact |
| **Gift Suggestion Engine** | AI-powered gift recommendations based on profile, interests, and history |
| **WhatsApp Business API** | Official API integration — replaces browser automation |
| **Telegram Bot** | Dedicated birthday bot with detection, wishing, and replies |
| **Discord Bot** | Server and DM birthday announcements |
| **Asian Platforms** | WeChat, LINE, KakaoTalk support |
| **FastAPI Backend** | REST API decoupled from dashboards |
| **PostgreSQL Migration** | Production-scale storage replacing SQLite |
| **Redis Cache** | Caching layer for contacts, scores, and sessions |
| **Kubernetes Support** | Full-stack K8s manifests |

### 🚀 v8.0 — Intelligence & Automation

| Feature | Description |
|---------|-------------|
| **Wish Style Memory** | Tracks past styles per contact, always picks a fresh angle |
| **Context-Aware Opener** | Reads recent LinkedIn activity for hyper-specific opening lines |
| **Multi-Wish Variants** | Formal/casual/funny side-by-side with live personalization scores |
| **Smart Emoji Calibration** | Learns emoji density from reply history |
| **Conditional Workflow Builder** | Visual IF-THEN-ELSE rule editor, no code needed |
| **Batch Approve Queue** | Morning review — bulk approve/reject/edit/send |
| **Send-Time Optimizer** | Per-platform activity learning, peak-hour scheduling |
| **Auto-Pause on Anomaly** | Self-pausing on failure spikes with Telegram alert |
| **Reply Sentiment Trend** | Tracks tone changes per contact over time |
| **Platform ROI Comparison** | Effort vs. engagement matrix with focus recommendations |
| **VIP Contact Flagging** | Platinum/Gold/Silver with mandatory review and multi-platform sending |

### 🔐 Security & Reliability

| Feature | Description |
|---------|-------------|
| **JWT Authentication** | Role-based access control (admin/manager/viewer) with token refresh and blocklist |
| **GDPR Compliance** | Full Article 17 (right to forget) and Article 20 (data portability) support |
| **Tamper-Evident Audit** | SHA-256 hash-chain on every data operation |
| **Session Management** | Browser cookies with 12-hour auto-expiry |
| **Error Handling & Retry** | 3 retries with exponential backoff |
| **2FA Support** | TOTP, SMS OTP, Email OTP for LinkedIn |
| **Proxy Rotation** | Round-robin/random/fastest proxy selection |
| **VPN Auto-Switch** | Automatic VPN server rotation on IP blocks |

### 🌐 Multi-Platform

| Platform | Capabilities |
|----------|-------------|
| **LinkedIn** | Birthday detection, AI wishing, replying, post engagement, connection requests |
| **WhatsApp** | Birthday replies, voice messages, voice-to-text, Business API |
| **Facebook** | Birthday detection and replies |
| **Instagram** | Birthday replies, post detection |
| **Twitter/X** | Birthday mention detection, auto-reply |
| **Slack** | Workspace birthday detection, DM + channel announcements |
| **Telegram** | Dedicated birthday bot |
| **Discord** | Server/DM birthday announcements |
| **WeChat** | Birthday detection and wishing |
| **LINE** | Birthday detection and wishing |

### 📊 Dashboards

Every v10.0 module ships with a Streamlit dashboard using a consistent dark theme (`#0d1117` / `#161b22` / `#f78166`). Run any module with `streamlit run <module>.py`:

| Dashboard | Tabs |
|-----------|------|
| Churn Predictor | Predictions, Risk Factors, Alerts |
| ROI Forecasting | Forecasts, Pipeline, Contacts |
| GDPR Compliance | Consent, Erasure, Export, Retention, Audit, Integrity |
| Audit Trail | Browse, Analytics, Chain Verify, Export, Archive |
| JWT Auth | Users, Create User, Login Log, Test Login |
| Push Notifications | Send, Devices, Log, Analytics, Preferences |
| Rate Limit Dashboard | Live Status, Quotas, Throttle Log, History, Maintenance |
| Morning Briefing | Today's Brief, History, Settings |
| Interest Graph | Graph View, Clusters, Signals |
| Engagement Calendar | Calendar, Upcoming, History |
| Wish Performance | Predictions, Accuracy, Factors |

---

## 🗂️ Project Structure

```
Birthday-Wishes-Agent/
│
├── ── Core Agent ──────────────────────────────────────────────
├── agent.py                          # Main agent — tasks, toggles, scheduler (2.4k lines)
├── autonomous_agent.py               # Self-governing decision engine with safety rails
├── langgraph_workflow.py             # LangGraph state-machine workflow orchestration
├── mcp_server.py                     # MCP server — 14 tools for Claude Desktop
├── model_config.py                   # Multi-model config (Claude / Gemini / GPT-4o)
│
├── ── ML & Intelligence ───────────────────────────────────────
├── churn_predictor.py                # ML-based churn scoring with decay curves
├── roi_forecasting.py                # Revenue attribution and pipeline forecasting
├── wish_performance_predictor.py     # Reply probability and optimal send-time prediction
├── interest_graph.py                 # Contact interest mapping as weighted graph
├── vector_memory.py                  # Semantic vector search across interactions
├── conversation_summary.py           # Auto-summarization of conversation threads
│
├── ── Privacy & Security ──────────────────────────────────────
├── gdpr_compliance.py                # GDPR — consent, erasure (22 tables), retention, export
├── audit_log.py                      # Tamper-evident SHA-256 hash-chain audit trail
├── jwt_auth.py                       # JWT auth — PBKDF2, RBAC, token refresh, lockout
│
├── ── Operations ──────────────────────────────────────────────
├── push_notifications.py             # Firebase FCM push — 10 categories, topics, quiet hours
├── rate_limit_dashboard.py           # Per-platform quotas (daily/hourly/min) for 10 platforms
├── morning_briefing.py               # Daily digest — birthdays, tasks, alerts, agent status
├── engagement_calendar.py            # Visual outreach calendar
├── email_outreach.py                 # Templated email campaigns with tracking
│
├── ── Integrations ────────────────────────────────────────────
├── crm_sync.py                       # HubSpot + Salesforce bidirectional sync
├── google_calendar_sync.py           # Google Calendar two-way sync
├── notion_sync.py                    # Notion database sync
│
├── ── Backend & Data ──────────────────────────────────────────
├── fastapi_backend.py                # FastAPI REST API service
├── postgres_migration.py             # SQLite → PostgreSQL migration
├── redis_cache.py                    # Redis caching layer
│
├── ── Config & Data ───────────────────────────────────────────
├── .env.example                      # Environment variable template
├── requirements.txt                  # Python dependencies
├── agent_history.db                  # SQLite database (auto-created)
│
├── ── DevOps ──────────────────────────────────────────────────
├── Dockerfile
├── docker-compose.yml
├── k8s/                              # Kubernetes manifests
├── .github/workflows/ci-cd.yml      # GitHub Actions (flake8 gate)
├── deploy/aws/                       # AWS deployment configs
└── deploy/gcp/                       # GCP deployment configs
```

**Module pattern (v10.0):** Every module follows the same structure:
- `init_*_tables()` — auto-bootstrap SQLite schema
- Core business logic functions
- `render_dashboard()` — Streamlit dashboard with dark theme
- `_self_test()` — comprehensive self-test with temp DB
- `if __name__ == "__main__": _self_test()` / `else: render_dashboard()`
- flake8 clean (`--select=E9,F63,F7,F82`)

---

## 🌿 Branch Guide

| Branch | Status | What was added |
|--------|--------|----------------|
| `main` | 🟢 Active (v9.0) | All merged features through v9.0 |
| `10.0` | 🔵 Development | LangGraph workflow, MCP server (14 tools), multi-model config, autonomous agent, churn predictor, ROI forecasting, wish performance predictor, interest graph, vector memory, conversation summary, engagement calendar, email outreach, Google Calendar sync, Notion sync, CRM sync |
| `feature/gdpr-compliance` | 🟡 PR → main | GDPR — consent tracking, right-to-forget (22 tables), data retention, data export, audit log |
| `feature/audit-log` | 🟡 PR → main | Tamper-evident SHA-256 hash-chain audit trail with search, export, analytics dashboard |
| `feature/jwt-auth` | 🟡 PR → main | JWT auth — PBKDF2 passwords, RBAC (admin/manager/viewer), token refresh, lockout, FastAPI routes |
| `feature/push-notifications` | 🟡 PR → main | Firebase FCM push — 10 categories, topic subscriptions, quiet hours, delivery tracking |
| `feature/rate-limit-dashboard` | 🟡 PR → main | Per-platform quota tracking (daily/hourly/min) across 10 platforms with cooldown enforcement |
| `feature/morning-briefing` | 🟡 PR → main | Daily morning digest — birthdays, tasks, agent status, rate limits, alerts via push |
| `9.0` | ✅ Merged | Self-improving agent, multi-model consensus, voice cloning, AI video, gift suggestions, WhatsApp Business API, Telegram, Discord, Asian platforms, FastAPI, PostgreSQL, Redis, Kubernetes |
| `8.0` | ✅ Merged | Wish style memory, context opener, variant generator, emoji calibration, workflow builder, batch queue, send-time optimizer, auto-pause, sentiment trend, platform ROI, VIP flagging |
| `7.0` | ✅ Merged | Wish personalization scorer, Command Center, Real-time Wish Preview, Contact Timeline View |
| `6.0` | ✅ Merged | AI model selector, A/B auto-learning, voice wish, decay alert, Twitter/X, Slack, 2FA, proxy rotation, VPN |
| `5.0` | ✅ Stable | Relationship health, RAG memory, A/B testing, web app, browser extension |
| `4.0` | ✅ Stable | Reminder emails, tone matching, wish quality scorer, dark mode |
| `feature/cloud-deployment` | ✅ Merged | AWS + GCP cloud deployment |
| `feature/docker-support` | ✅ Merged | Docker + docker-compose |
| `feature/emotional-intelligence` | ✅ Merged | Emotional intelligence scoring |
| `feature/github-actions-cicd` | ✅ Merged | GitHub Actions CI/CD pipeline |
| `feature/multi-account-support` | ✅ Merged | Multiple LinkedIn account management |
| `feature/personality-profiling` | ✅ Merged | MBTI detection from LinkedIn posts |
| `feature/predictive-birthday` | ✅ Merged | Predict birthdays before they appear |

---

## ⚙️ Configuration

### Environment Variables

```bash
cp .env.example .env
```

```env
# ── AI Models ─────────────────────────────────
AI_MODEL=gemini                    # gemini / claude / gpt-4o
GOOGLE_API_KEY=                    # Gemini 2.5 Flash
ANTHROPIC_API_KEY=                 # Claude Sonnet
OPENAI_API_KEY=                    # GPT-4o

# ── LinkedIn ──────────────────────────────────
USERNAME=your_linkedin_email
PASSWORD=your_linkedin_password

# ── Auth (v10.0) ──────────────────────────────
BWA_JWT_SECRET=your-secret-key     # Required in production
BWA_ACCESS_TOKEN_MINUTES=30
BWA_REFRESH_TOKEN_DAYS=7

# ── Push Notifications (v10.0) ────────────────
BWA_FCM_SERVER_KEY=                # Firebase Cloud Messaging

# ── Morning Briefing (v10.0) ──────────────────
BWA_BRIEFING_HOUR=7                # UTC hour for daily digest

# ── Database ──────────────────────────────────
BWA_DB_PATH=agent_history.db       # Override SQLite path

# ── Platforms (optional) ──────────────────────
TWITTER_BEARER_TOKEN=
SLACK_BOT_TOKEN=
TELEGRAM_BOT_TOKEN=
DISCORD_BOT_TOKEN=
WHATSAPP_BUSINESS_API_TOKEN=

# ── Integrations (optional) ───────────────────
HUBSPOT_API_KEY=
SALESFORCE_CLIENT_ID=
NOTION_API_KEY=
GOOGLE_CALENDAR_CREDENTIALS=

# ── Security (optional) ──────────────────────
LINKEDIN_2FA_ENABLED=false
LINKEDIN_2FA_METHOD=totp
PROXY_ENABLED=false
VPN_ENABLED=false
```

---

## 📖 Usage

### Running Modules

```bash
# Main agent
python agent.py

# Autonomous agent
python autonomous_agent.py run             # dry run
python autonomous_agent.py run --live      # live sends
python autonomous_agent.py status          # show status

# Morning briefing
python morning_briefing.py run             # print today's briefing
python morning_briefing.py run --push default  # + push notification

# Any self-test
python churn_predictor.py
python gdpr_compliance.py
python audit_log.py
python jwt_auth.py
python push_notifications.py
python rate_limit_dashboard.py
```

### Running Dashboards

```bash
streamlit run churn_predictor.py
streamlit run roi_forecasting.py
streamlit run gdpr_compliance.py
streamlit run audit_log.py
streamlit run jwt_auth.py
streamlit run push_notifications.py
streamlit run rate_limit_dashboard.py
streamlit run morning_briefing.py
streamlit run interest_graph.py
streamlit run engagement_calendar.py
```

### Docker

```bash
docker-compose up --build -d    # Build and run in background
docker-compose logs -f          # View live logs
docker-compose down             # Stop
```

---

## 🧪 Testing

Every v10.0 module includes a comprehensive self-test suite that runs against a temporary database:

```bash
# Run all module self-tests
python churn_predictor.py       # ML scoring tests
python gdpr_compliance.py       # Consent, erasure, retention, export
python audit_log.py             # Hash-chain integrity
python jwt_auth.py              # Auth flow, lockout, password reset
python push_notifications.py    # Device management, delivery tracking
python rate_limit_dashboard.py  # Quota enforcement, cooldowns
python morning_briefing.py      # Briefing generation, formatting

# CI gate (runs on every PR)
flake8 --select=E9,F63,F7,F82 *.py
```

---

## 📋 Changelog

### v10.0 🆕

**🧠 AI & Workflow**
- ✅ **LangGraph Workflow Engine** — state-machine orchestration with conditional routing
- ✅ **MCP Server** — 14 tools for Claude Desktop integration
- ✅ **Multi-Model Config** — Claude Sonnet, Gemini 2.5 Flash, GPT-4o with fallback
- ✅ **Autonomous Agent** — self-governing decisions with safety rails (error rate pause, daily cap)
- ✅ **Churn Predictor** — ML-based scoring with decay curves and automated alerts
- ✅ **ROI Forecasting** — revenue attribution and pipeline forecasting
- ✅ **Wish Performance Predictor** — reply probability and optimal timing
- ✅ **Interest Graph** — weighted relationship and interest mapping
- ✅ **Vector Memory** — semantic search across all past interactions
- ✅ **Conversation Summary** — auto-summarization of threads

**🔒 Privacy & Security**
- ✅ **GDPR Compliance** — consent, right-to-forget (22 tables), retention, data export
- ✅ **Audit Trail** — tamper-evident SHA-256 hash-chain across all modules
- ✅ **JWT Auth** — PBKDF2 passwords, RBAC, token refresh/revocation, account lockout

**📱 Operations**
- ✅ **Push Notifications** — Firebase FCM, 10 categories, topic subscriptions, quiet hours
- ✅ **Rate Limit Dashboard** — per-platform quotas for 10 platforms, throttle logging
- ✅ **Morning Briefing** — daily digest with push delivery

**🔗 Integrations**
- ✅ **CRM Sync** — HubSpot + Salesforce bidirectional
- ✅ **Google Calendar Sync** — two-way birthday sync
- ✅ **Notion Sync** — database sync for contacts and wishes
- ✅ **Email Outreach** — templated campaigns
- ✅ **Engagement Calendar** — visual outreach calendar

### v9.0

**🤖 Autonomy & Media**
- ✅ Self-improving agent, multi-model consensus, agent session memory
- ✅ Voice cloning, AI video message, gift suggestion engine
- ✅ WhatsApp Business API, Telegram bot, Discord bot, Asian platforms

**🏗️ Infrastructure**
- ✅ FastAPI backend, Next.js web app, PostgreSQL migration, Redis cache, Kubernetes

### v8.0

**🚀 Intelligence**
- ✅ Wish style memory, context-aware opener, variant generator, emoji calibration

**⚙️ Automation**
- ✅ Workflow builder, batch queue, send-time optimizer, auto-pause on anomaly

**📊 Analytics**
- ✅ Insight reports, sentiment trend, platform ROI, personalization score trend

**📋 Contacts**
- ✅ Tier auto-adjust, mutual connection insights, life event timeline, VIP flagging

### v7.0
- ✅ Wish personalization scorer, Command Center, Real-time Wish Preview, Contact Timeline

### v6.0
- ✅ AI model selector, A/B auto-learning, voice wish, Twitter/X, Slack, 2FA, proxy, VPN

### v5.0
- ✅ Relationship health, RAG memory, A/B testing, web app, browser extension

### v4.0
- ✅ Personality profiling, sentiment analysis, tone matching, multi-language (17 langs)

### v3.0
- ✅ Multi-platform (WhatsApp, Facebook, Instagram), voice messages, calendar export

### v2.0
- ✅ Session management, error handling, scheduler, Streamlit dashboard, notifications

### v1.0
- ✅ GitHub follower check, LinkedIn birthday wish reply

---

## 👥 Contributing

1. Fork the repository
2. Create your branch: `git checkout -b feat/amazing-feature`
3. Commit: `git commit -m 'feat: add amazing feature'`
4. Push: `git push origin feat/amazing-feature`
5. Open a Pull Request

All PRs must pass: `flake8 --select=E9,F63,F7,F82 *.py`

---

## 👨‍💻 Author

Maintained by **[Sadman Chowdhury Fahim](https://github.com/SadManFahIm)**

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
