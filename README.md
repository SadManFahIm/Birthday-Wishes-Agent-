# LinkedIn Birthday Wishes Agent 🎂🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Version](https://img.shields.io/badge/version-6.0--dev-brightgreen)
![LangChain](https://img.shields.io/badge/LangChain-powered-blueviolet)
![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-orange)

<!-- cspell:ignore Streamlit -->

![Streamlit](https://img.shields.io/badge/Streamlit-Cloud-red)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-green)
![Platforms](https://img.shields.io/badge/platforms-4-blue)

An intelligent, production-ready AI agent pipeline that manages birthday wishes and life event congratulations across LinkedIn, WhatsApp, Facebook, and Instagram — with memory, sentiment awareness, tone matching, multi-language support, voice messages, personality profiling, emotional intelligence, predictive birthdays, multi-account support, Docker, CI/CD, and cloud deployment.

---

## 📝 Introduction

This project demonstrates how to build a sophisticated, multi-feature AI agent using Python, LangChain, and browser automation. What started as a simple LinkedIn reply bot has grown into a comprehensive relationship management system across four social platforms — now with cloud-ready deployment, multi-account management, and AI-powered personality intelligence.

---

## 📌 Table of Contents

- [Features](#-features)
- [Project Structure](#️-project-structure)
- [Branch Guide](#-branch-guide)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Docker Setup](#-docker-setup)
- [Cloud Deployment](#️-cloud-deployment)
- [Configuration](#️-configuration)
- [Usage](#-usage)
- [Deploy to Streamlit Cloud](#-deploy-to-streamlit-cloud)
- [Notification Setup](#-notification-setup)
- [Multi-Account Support](#-multi-account-support)
- [Supported Languages](#-supported-languages)
- [Relationship Scoring](#-relationship-scoring)
- [Tone Matching](#-tone-matching)
- [Changelog](#-changelog)
- [Contributing](#-contributing)

---

## ✨ Features

### 🤖 Core Agent

| Feature                         | Description                                                            |
| ------------------------------- | ---------------------------------------------------------------------- |
| **GitHub Follower Check**       | Visits a GitHub profile and reports the follower count                 |
| **LinkedIn Birthday Detection** | Finds contacts with birthdays today and sends personalized wishes      |
| **LinkedIn Reply to Wishes**    | Scans unread messages and replies to birthday wishes                   |
| **Multi-Platform Support**      | Extends all features to WhatsApp, Facebook Messenger, and Instagram DM |

### 🔐 Security & Reliability

| Feature                    | Description                                                                     |
| -------------------------- | ------------------------------------------------------------------------------- |
| **Session Management**     | Browser cookies saved to disk — no repeated logins. Auto-expires after 12 hours |
| **Error Handling & Retry** | Every task retries up to 3 times with a 5-second delay between attempts         |
| **Dry Run Mode**           | Simulate the agent without sending any real messages                            |
| **Whitelist / Blacklist**  | Control exactly which contacts to wish or always skip                           |
| **Reply Cooldown**         | Prevents replying to the same contact within 30 days                            |

### 🧠 AI & Personalization

| Feature                        | Description                                                                                                                                               |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **AI-Generated Custom Wishes** | Visits the contact's profile, reads their job and interests, generates a completely unique wish                                                           |
| **Contact Relationship Score** | Classifies each contact as Close Friend, Colleague, or Acquaintance and adjusts wish style                                                                |
| **Memory System**              | Remembers key details from last year — references them in this year's wish                                                                                |
| **Sentiment Analysis**         | Detects if someone is sad, stressed, or lonely and replies with extra care                                                                                |
| **Tone Matching**              | Mirrors the contact's communication style — formal, casual, emoji-heavy, slang                                                                            |
| **Multi-language Reply**       | Detects the language of the wish and replies in the same language (17 languages)                                                                          |
| **Wish Quality Scorer**        | Scores every AI-generated wish 1–10 and auto-retries if below threshold                                                                                   |
| **Occasion Detection**         | Detects promotions, new jobs, graduations, engagements, marriages and congratulates                                                                       |
| **Personality Profiling** 🆕   | Analyzes LinkedIn posts to detect MBTI type, dominant traits, tone, interests, communication style — generates personality-aware wishes, cached in SQLite |
| **Emotional Intelligence** 🆕  | Scores the emotional tone of every wish and reply — ensures empathy and warmth before sending                                                             |
| **Predictive Birthday** 🆕     | Predicts upcoming birthdays before they officially appear on LinkedIn                                                                                     |
| **RAG-Based Memory** 🆕        | ChromaDB vector store for long-term, semantic relationship memory                                                                                         |
| **Conversation Memory** 🆕     | Maintains full conversation history for context-aware replies                                                                                             |

### 🎙️ Voice Messages

| Feature                     | Description                                                            |
| --------------------------- | ---------------------------------------------------------------------- |
| **Voice Message Reply**     | Generates a voice message from the reply text and sends it on WhatsApp |
| **gTTS Engine**             | Free Google Text-to-Speech, no API key required                        |
| **ElevenLabs Engine**       | Premium realistic voice generation                                     |
| **Voice-to-Text Reply** 🆕  | Transcribes incoming WhatsApp voice notes and auto-replies             |
| **Auto Language Detection** | Selects the correct TTS language automatically                         |

### ⚙️ Smart Automation

| Feature                      | Description                                                                 |
| ---------------------------- | --------------------------------------------------------------------------- |
| **Daily Scheduler**          | Runs all tasks automatically at a configurable time every day               |
| **Smart Timing**             | Detects the contact's timezone and sends wishes at 9:00 AM their local time |
| **Follow-up Messages**       | Sends a warm follow-up message 2–3 days after each birthday wish            |
| **Auto Reply to Follow-up**  | When someone replies to a wish or follow-up, responds automatically         |
| **Birthday Calendar Export** | Exports all contacts' birthdays to a `.ics` file for Google Calendar        |
| **Birthday Reminder Email**  | Sends a reminder email the day before a contact's birthday                  |
| **LinkedIn Post Engagement** | Likes and comments on birthday contacts' latest LinkedIn posts              |
| **Group Birthday Detection** | Finds birthday posts in LinkedIn Groups and engages with them               |
| **Auto LinkedIn Connect**    | Sends personalized connection requests to 2nd-degree wishers                |
| **Wish A/B Testing** 🆕      | Tracks which wish style gets more replies — learns over time                |
| **Best Time to Connect** 🆕  | Analyzes activity patterns to find the optimal send time per contact        |
| **Contact Categorizer** 🆕   | Auto-categorizes contacts by industry, seniority, and location              |
| **LinkedIn DM Campaign** 🆕  | Sends personalized icebreaker messages to new connections                   |

### 📋 Contact Management

| Feature                          | Description                                                                |
| -------------------------------- | -------------------------------------------------------------------------- |
| **Contact Notes**                | Save personal notes per contact — injected into wish prompts automatically |
| **Memory System**                | Year-over-year memory of job, company, life events, and interests          |
| **Connection Strength Tracker**  | Tracks interaction history and scores connection strength over time        |
| **Relationship Health Score** 🆕 | Weekly relationship health report sent to your email                       |

### 👥 Multi-Account Support 🆕

| Feature                        | Description                                                  |
| ------------------------------ | ------------------------------------------------------------ |
| **Multiple LinkedIn Accounts** | Manage and rotate across multiple LinkedIn accounts          |
| **Per-Account History**        | Each account has independent wish history and contact memory |
| **Centralized Dashboard**      | Single dashboard showing activity across all accounts        |
| **Rate Limit Protection**      | Automatically rotates accounts to avoid LinkedIn rate limits |

### 📊 Monitoring & Notifications

| Feature                         | Description                                                          |
| ------------------------------- | -------------------------------------------------------------------- |
| **SQLite Logging**              | Every action saved to `agent_history.db`                             |
| **Telegram Notification**       | Sends a run summary to Telegram after each task                      |
| **Email Notification**          | Sends a summary email via Gmail after each task                      |
| **Weekly Email Digest** 🆕      | Summarizes wishes sent, upcoming birthdays, and fading connections   |
| **Streamlit Control Dashboard** | Start/stop tasks, toggle Dry Run, view live logs                     |
| **Analytics Dashboard**         | Charts for activity, platforms, languages, relationships, follow-ups |
| **Real-time Dashboard** 🆕      | Live updates via FastAPI + WebSocket                                 |
| **Contact Profile Cards**       | Card view for every contact — notes, wish history, strength score    |
| **Wish Preview Dashboard**      | Preview, edit, approve, or reject wishes before sending              |
| **Full Web App** 🆕             | FastAPI + React + JWT auth + multi-user support                      |
| **Browser Extension** 🆕        | LinkedIn sidebar showing contact info, notes, and wish history       |
| **Mobile App**                  | Mobile-optimized Streamlit app deployable to Streamlit Cloud         |
| **Onboarding Wizard** 🆕        | Step-by-step first-time setup guide                                  |
| **Dark / Light Mode**           | Theme toggle available across all dashboards                         |

---

## 🗂️ Project Structure

```
Birthday-Wishes-Agent/
│
├── agent.py                   # Main agent — all tasks, toggles, scheduler
│
├── ── AI & Personalization ──
├── wish_generator.py          # AI-generated custom wish generator
├── wish_scorer.py             # Wish quality scorer (1-10) with auto-retry
├── sentiment.py               # Sentiment analysis (happy/sad/stressed/lonely)
├── tone_matching.py           # Communication tone detection and mirroring
├── multilang_reply.py         # Multi-language reply (17 languages)
├── occasion_detection.py      # Life event detection and congratulations
├── relationship.py            # Contact relationship scoring
├── memory.py                  # Year-over-year contact memory system
├── personality_profiling.py   # MBTI personality detection from LinkedIn posts 🆕
├── emotional_intelligence.py  # Emotional intelligence scoring 🆕
├── predictive_birthday.py     # Predict upcoming birthdays early 🆕
├── rag_memory.py              # ChromaDB vector store for long-term memory 🆕
├── conversation_memory.py     # Context-aware full conversation history 🆕
│
├── ── Contact Management ──
├── contact_notes.py           # Personal notes per contact
├── connection_tracker.py      # Connection strength tracker
├── contact_categorizer.py     # Auto-categorize by industry, seniority 🆕
├── ab_testing.py              # Wish A/B testing tracker 🆕
│
├── ── Automation ──
├── followup.py                # Follow-up message scheduler
├── auto_reply_followup.py     # Auto reply to follow-up responses
├── auto_connect.py            # Auto LinkedIn connect for 2nd-degree wishers
├── post_engagement.py         # LinkedIn post like and comment
├── group_birthday.py          # LinkedIn Group birthday detection
├── birthday_reminder.py       # Birthday reminder email (day before)
├── calendar_export.py         # Birthday calendar export (.ics)
├── smart_timing.py            # Timezone-aware optimal send time
├── best_time.py               # Activity pattern analyzer 🆕
├── dm_campaign.py             # LinkedIn DM campaign for new connections 🆕
├── voice.py                   # Voice message (gTTS + ElevenLabs)
├── voice_to_text.py           # Transcribe WhatsApp voice notes 🆕
│
├── ── Notifications ──
├── notifications.py           # Telegram & Email notifications
├── weekly_digest.py           # Weekly email digest 🆕
├── health_score.py            # Relationship health score report 🆕
│
├── ── Multi-Account ── 🆕
├── account_manager.py         # Manage and rotate LinkedIn accounts
│
├── ── Platforms ──
├── platforms/
│   ├── __init__.py
│   ├── linkedin.py            # LinkedIn with AI wishes + relationship scoring
│   ├── whatsapp.py            # WhatsApp Web with voice message support
│   ├── facebook.py            # Facebook Messenger
│   └── instagram.py          # Instagram DM
│
├── ── Dashboards ──
├── dashboard.py               # Streamlit control dashboard
├── analytics.py               # Analytics dashboard with charts
├── profile_cards.py           # Contact profile cards
├── wish_preview.py            # Wish preview — approve/edit/reject
├── mobile_app.py              # Mobile app for Streamlit Cloud
├── realtime_dashboard.py      # FastAPI + WebSocket live dashboard 🆕
├── web_app/                   # FastAPI + React web app 🆕
│   ├── main.py
│   ├── auth.py
│   └── frontend/
├── browser_extension/         # LinkedIn sidebar extension 🆕
├── onboarding.py              # First-time setup wizard 🆕
├── theme_toggle.py            # Dark/Light mode helper
│
├── ── DevOps ── 🆕
├── Dockerfile
├── docker-compose.yml
├── .github/
│   └── workflows/
│       └── ci-cd.yml          # GitHub Actions pipeline
├── deployment/
│   ├── aws/                   # AWS deployment configs
│   └── gcp/                   # GCP deployment configs
│
├── .streamlit/
│   ├── config.toml            # Streamlit theme config
│   └── secrets.toml.example  # Secrets template for Streamlit Cloud
│
├── .env                       # Your credentials (never commit!)
├── .env.example               # Credentials template
├── .gitignore
├── requirements.txt
│
├── agent.log                  # Live log (auto-generated)
├── agent_history.db           # SQLite database (auto-generated)
├── birthdays.ics              # Exported calendar (auto-generated)
├── audio_messages/            # Voice files (auto-generated)
├── linkedin_session.json      # Session timestamp (auto-generated)
└── browser_profile/           # Browser cookies (auto-generated)
```

---

## 🌿 Branch Guide

| Branch                             | Status               | What was added                                                                 |
| ---------------------------------- | -------------------- | ------------------------------------------------------------------------------ |
| `main`                             | 🟢 Active (v6.0-dev) | All features merged — latest development                                       |
| `5.0`                              | ✅ Stable tag        | Relationship health score, RAG memory, A/B testing, web app, browser extension |
| `4.0`                              | ✅ Stable tag        | Reminder emails, tone matching, wish quality scorer, dark mode                 |
| `feature/cloud-deployment`         | ✅ Merged            | AWS + GCP cloud deployment                                                     |
| `feature/docker-support`           | ✅ Merged            | Docker + docker-compose one-command setup                                      |
| `feature/emotional-intelligence`   | ✅ Merged            | Emotional intelligence scoring                                                 |
| `feature/github-actions-cicd`      | ✅ Merged            | GitHub Actions CI/CD pipeline                                                  |
| `feature/multi-account-support`    | ✅ Merged            | Multiple LinkedIn account management                                           |
| `feature/multi-account-support-v2` | ✅ Merged            | Improved multi-account with rotation                                           |
| `feature/personality-profiling`    | ✅ Merged            | MBTI detection from LinkedIn posts                                             |
| `feature/predictive-birthday`      | ✅ Merged            | Predict birthdays before they appear                                           |

---

## 🔧 Prerequisites

- Python 3.10 or higher
- Google Chrome browser
- LinkedIn account
- API key for OpenAI or Google Gemini
- _(Optional)_ Facebook and Instagram accounts
- _(Optional)_ Telegram bot token
- _(Optional)_ Gmail App Password
- _(Optional)_ ElevenLabs API key for premium voice
- _(Optional)_ Docker (for containerized setup)
- _(Optional)_ AWS or GCP account (for cloud deployment)

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/SadManFahIm/Birthday-Wishes-Agent-.git
cd Birthday-Wishes-Agent-
```

### 2. Create a virtual environment

**Windows:**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS/Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## 🐳 Docker Setup

One-command setup — no manual environment configuration needed:

```bash
# Build and run
docker-compose up --build

# Run in background
docker-compose up -d

# View live logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## ☁️ Cloud Deployment

### AWS

```bash
# See deployment/aws/ for full configuration
# Supports EC2 and Lambda deployment
```

### GCP

```bash
# See deployment/gcp/ for full configuration
# Supports Cloud Run deployment
```

---

## ⚙️ Configuration

### 1. Set up your `.env` file

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# LLM (choose one)
OPENAI_API_KEY=
GOOGLE_API_KEY=

# LinkedIn
USERNAME=your_linkedin_email
PASSWORD=your_linkedin_password
GITHUB_URL=https://github.com/yourusername

# Multi-Account Support 🆕
LINKEDIN_ACCOUNTS=account1@email.com,account2@email.com
LINKEDIN_PASSWORDS=password1,password2

# Facebook (optional)
FB_USERNAME=your_facebook_email
FB_PASSWORD=your_facebook_password

# Instagram (optional)
IG_USERNAME=your_instagram_username
IG_PASSWORD=your_instagram_password

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Email (optional - Gmail App Password)
EMAIL_SENDER=your_gmail@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=receiver@example.com

# Birthday Reminder Recipients
REMINDER_RECIPIENTS=you@gmail.com

# Voice (optional - ElevenLabs)
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Voice-to-Text 🆕
TRANSCRIPTION_ENGINE=whisper

# Feature Flags 🆕
CONNECTION_TRACKER_ENABLED=true
```

### 2. Key `agent.py` settings

```python
DRY_RUN = True                  # Simulate — no real messages sent

# Platform toggles
ENABLE_LINKEDIN  = True
ENABLE_WHATSAPP  = True
ENABLE_FACEBOOK  = True
ENABLE_INSTAGRAM = True

# Voice
VOICE_ENABLED = True
VOICE_ENGINE  = "gtts"          # "gtts" or "elevenlabs"

# AI features
SENTIMENT_ANALYSIS_ENABLED     = True
MEMORY_ENABLED                 = True
WISH_SCORER_ENABLED            = True
SCORE_THRESHOLD                = 7
TONE_MATCHING_ENABLED          = True
MULTILANG_REPLY_ENABLED        = True
OCCASION_DETECTION_ENABLED     = True
PERSONALITY_PROFILING_ENABLED  = True   # 🆕
EMOTIONAL_INTELLIGENCE_ENABLED = True   # 🆕
PREDICTIVE_BIRTHDAY_ENABLED    = True   # 🆕
RAG_MEMORY_ENABLED             = True   # 🆕
AB_TESTING_ENABLED             = True   # 🆕

# Automation
AUTO_CONNECT_ENABLED           = True
POST_ENGAGEMENT_ENABLED        = True
GROUP_BIRTHDAY_ENABLED         = True
BIRTHDAY_REMINDER_ENABLED      = True
AUTO_REPLY_FOLLOWUP_ENABLED    = True
WISH_PREVIEW_ENABLED           = False  # True = manual approval required
CONNECTION_TRACKER_ENABLED     = True   # 🆕
DM_CAMPAIGN_ENABLED            = True   # 🆕

# Multi-Account 🆕
MULTI_ACCOUNT_ENABLED          = True

# Scheduling
SCHEDULE_HOUR   = 9
SCHEDULE_MINUTE = 0
COOLDOWN_DAYS   = 30
FOLLOWUP_DAYS   = 2
```

---

## 📋 Usage

### Option 1 — Run a task immediately

Uncomment the desired task in `agent.py`:

```python
async def main():
    init_db()
    init_followup_table()
    init_connections_table()
    init_memory_table()
    init_engagement_table()
    init_reminder_table()
    init_notes_table()
    init_group_birthday_table()
    init_tracker_table()
    init_auto_reply_table()
    try:
        await run_birthday_detection_task()
        # await run_ai_custom_wish_task()
        # await run_memory_wish_task()
        # await run_sentiment_reply_task()
        # await run_linkedin_reply_task()
        # await run_whatsapp_reply_task()
        # await run_facebook_reply_task()
        # await run_instagram_reply_task()
        # await run_followup_task()
        # await run_auto_reply_task()
        # await run_post_engagement_task()
        # await run_group_birthday_task()
        # await run_occasion_detection_task()
        # await run_birthday_reminder_task()
        # await run_calendar_export()
        # await run_predictive_birthday_task()     # 🆕
        # await run_personality_profiling_task()   # 🆕
        # await run_dm_campaign_task()             # 🆕
        # await run_weekly_digest_task()           # 🆕
        # await run_health_score_task()            # 🆕
    finally:
        await close_browser()
```

```bash
python agent.py
```

### Option 2 — Daily Scheduler

```python
await run_scheduler()
```

### Option 3 — Streamlit Dashboards

```bash
streamlit run dashboard.py         # Control dashboard
streamlit run analytics.py         # Analytics & charts
streamlit run profile_cards.py     # Contact profile cards
streamlit run wish_preview.py      # Wish preview & approval
streamlit run mobile_app.py        # Mobile app
```

### Option 4 — Docker

```bash
docker-compose up --build
```

---

## 📱 Deploy to Streamlit Cloud

1. Push the repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set **Main file**: `mobile_app.py`
5. Go to **App Settings → Secrets** and paste your `.env` values
6. Click **Deploy**

---

## 🔔 Notification Setup

### Telegram

1. Search **@BotFather** on Telegram → `/newbot`
2. Copy the token → add as `TELEGRAM_BOT_TOKEN`
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to get your `chat_id`

### Email (Gmail)

1. Enable 2FA on Gmail
2. **Settings → Security → App Passwords → Generate**
3. Add the password as `EMAIL_PASSWORD`

---

## 👥 Multi-Account Support

Added in `feature/multi-account-support` + `feature/multi-account-support-v2`:

- Configure multiple LinkedIn accounts in `.env` via `LINKEDIN_ACCOUNTS`
- Agent automatically rotates across accounts to avoid rate limiting
- Each account maintains independent wish history and contact memory
- Centralized dashboard shows combined activity across all accounts

---

## ⚙️ CI/CD Pipeline

GitHub Actions workflow (added in `feature/github-actions-cicd`):

- ✅ Triggers on every push to `main` and all PRs
- ✅ Linting + unit tests
- ✅ Docker build verification
- ✅ Auto-deploy to cloud on merge to `main`

See `.github/workflows/ci-cd.yml` for the full pipeline configuration.

---

## 📅 Birthday Calendar Export

```python
await run_calendar_export()
```

Generates `birthdays.ics`. To import into Google Calendar:

1. Go to [calendar.google.com](https://calendar.google.com)
2. **Settings → Import & Export → Import**
3. Upload `birthdays.ics`

All events repeat **yearly** with a **1-day reminder**.

---

## 🌍 Supported Languages

| Language      | Detection | Reply |
| ------------- | --------- | ----- |
| 🇬🇧 English    | ✅        | ✅    |
| 🇧🇩 Bengali    | ✅        | ✅    |
| 🇸🇦 Arabic     | ✅        | ✅    |
| 🇮🇳 Hindi      | ✅        | ✅    |
| 🇵🇰 Urdu       | ✅        | ✅    |
| 🇪🇸 Spanish    | ✅        | ✅    |
| 🇫🇷 French     | ✅        | ✅    |
| 🇩🇪 German     | ✅        | ✅    |
| 🇹🇷 Turkish    | ✅        | ✅    |
| 🇮🇩 Indonesian | ✅        | ✅    |
| 🇲🇾 Malay      | ✅        | ✅    |
| 🇨🇳 Chinese    | ✅        | ✅    |
| 🇯🇵 Japanese   | ✅        | ✅    |
| 🇰🇷 Korean     | ✅        | ✅    |
| 🇧🇷 Portuguese | ✅        | ✅    |
| 🇮🇹 Italian    | ✅        | ✅    |
| 🇷🇺 Russian    | ✅        | ✅    |

---

## 💝 Relationship Scoring

| Score  | Type            | Wish Style                |
| ------ | --------------- | ------------------------- |
| 60–100 | 🟢 Close Friend | Casual, warm, funny       |
| 30–59  | 🔵 Colleague    | Professional but friendly |
| 0–29   | ⚪ Acquaintance | Polite and brief          |

---

## 🎭 Tone Matching

| Their Tone  | Reply Style                            |
| ----------- | -------------------------------------- |
| Formal      | Full sentences, no emoji, professional |
| Semi-formal | Friendly, 1 emoji max                  |
| Casual      | Relaxed, contractions, 2 emoji         |
| Very Casual | Slang ok, short, fun                   |
| Emoji-heavy | Match their emoji count                |

---

## 🔄 Changelog

### v6.0-dev (main — current)

- ✅ **Cloud Deployment** — AWS + GCP support (`feature/cloud-deployment`)
- ✅ **Multi-Account LinkedIn v2** — improved rotation and per-account memory (`feature/multi-account-support-v2`)
- ✅ **GitHub Actions CI/CD** — lint, test, Docker build, auto-deploy (`feature/github-actions-cicd`)
- ✅ **Docker Support** — one-command `docker-compose up` setup (`feature/docker-support`)
- ✅ **Emotional Intelligence Scoring** — checks empathy and warmth before sending (`feature/emotional-intelligence`)
- ✅ **Predictive Birthday** — detects upcoming birthdays before LinkedIn shows them (`feature/predictive-birthday`)
- 🐛 Fix: syntax error in predictive birthday task call
- 🐛 Fix: missing `TRANSCRIPTION_ENGINE` and `CONNECTION_TRACKER_ENABLED` config vars
- 🐛 Fix: undefined exception variable `e` in `_run_sub_agent`
- 🐛 Fix: f-string syntax error in `build_report_email`

### v5.0

- ✅ **Relationship Health Score** — weekly report with email digest
- ✅ **Best Time to Connect** — activity pattern analysis for optimal send time
- ✅ **LinkedIn DM Campaign** — personalized icebreaker messages for new connections
- ✅ **Contact Categorizer** — auto-categorize by industry, seniority, location
- ✅ **Wish A/B Testing** — tracks which wish style gets more replies
- ✅ **RAG-Based Memory** — ChromaDB vector store for semantic long-term memory
- ✅ **Voice-to-Text Reply** — transcribes WhatsApp voice notes and auto-replies
- ✅ **Real-time Dashboard** — FastAPI + WebSocket live updates
- ✅ **Full Web App** — FastAPI + React + JWT auth + multi-user support
- ✅ **Browser Extension** — LinkedIn sidebar with contact info, notes, wish history
- ✅ **Weekly Email Digest** — wishes sent, upcoming birthdays, fading connections
- ✅ **Onboarding Wizard** — step-by-step first-time setup
- ✅ **Conversation Memory** — context-aware replies with full history

### v4.0

- ✅ Sentiment Analysis (sad/stressed/lonely → extra caring replies)
- ✅ Auto LinkedIn Connect (connection requests to 2nd-degree wishers)
- ✅ Memory System (year-over-year contact memory)
- ✅ LinkedIn Post Engagement (like + comment on birthday posts)
- ✅ Birthday Reminder Email (day-before reminder)
- ✅ Contact Notes (personal notes per contact)
- ✅ Wish Quality Scorer (auto-retry if score < 7/10)
- ✅ Group Birthday Detection (LinkedIn Groups)
- ✅ Connection Strength Tracker
- ✅ Auto Reply to Follow-up
- ✅ Contact Profile Cards dashboard
- ✅ Wish Preview dashboard (approve/edit/reject)
- ✅ Dark / Light mode toggle
- ✅ Tone Matching (mirrors contact's communication style)
- ✅ Occasion Detection (promotion, new job, graduation, etc.)
- ✅ Multi-language Reply (17 languages)
- ✅ **Personality Profiling** — MBTI detection from LinkedIn posts, personality-aware wishes, SQLite caching

### v3.0

- ✅ Multi-platform support (WhatsApp, Facebook, Instagram)
- ✅ AI-generated custom wishes (profile-aware)
- ✅ Contact relationship scoring
- ✅ Voice message reply (gTTS + ElevenLabs)
- ✅ Follow-up messages (2–3 days after wish)
- ✅ Birthday calendar export (.ics)
- ✅ Smart timezone timing
- ✅ Analytics dashboard
- ✅ Mobile app (Streamlit Cloud)

### v2.0

- ✅ Session management
- ✅ Error handling & retry logic
- ✅ Personalized replies with sender's name
- ✅ Birthday detection & auto-wishing
- ✅ Daily scheduler
- ✅ Dry Run mode
- ✅ Streamlit control dashboard
- ✅ Better wish detection
- ✅ Multi-language detection (9 languages)
- ✅ Telegram & Email notifications
- ✅ SQLite logging
- ✅ Whitelist / Blacklist
- ✅ Reply cooldown

### v1.0

- ✅ GitHub follower check
- ✅ LinkedIn birthday wish reply (basic)

---

## 👥 Contributing

1. Fork the repository
2. Create your branch: `git checkout -b feat/amazing-feature`
3. Commit: `git commit -m 'feat: add amazing feature'`
4. Push: `git push origin feat/amazing-feature`
5. Open a Pull Request

---

## 👨‍💻 Author

Maintained by [Faahim Sadman](https://github.com/SadManFahIm)

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
