# LinkedIn Birthday Wishes Agent 🎂🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Version](https://img.shields.io/badge/version-6.0-brightgreen)
![LangChain](https://img.shields.io/badge/LangChain-powered-blueviolet)
![Gemini](https://img.shields.io/badge/Gemini-2.5%20Pro-orange)
![Streamlit](https://img.shields.io/badge/Streamlit-Cloud-red)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)
![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-green)
![Platforms](https://img.shields.io/badge/platforms-6-blue)

An intelligent, production-ready AI agent pipeline that manages birthday wishes and life event congratulations across LinkedIn, WhatsApp, Facebook, Instagram, Twitter/X, and Slack — with memory, sentiment awareness, tone matching, multi-language support, voice messages, personality profiling, emotional intelligence, predictive birthdays, multi-account support, Docker, CI/CD, cloud deployment, proxy rotation, VPN auto-switch, and 2FA support.

---

## 📝 Introduction

This project demonstrates how to build a sophisticated, multi-feature AI agent using Python, LangChain, and browser automation. What started as a simple LinkedIn reply bot has grown into a comprehensive relationship management system across six social platforms — now with enterprise-grade security, fully automatic timezone scheduling, and AI-powered auto-learning.

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

| Feature | Description |
| ------- | ----------- |
| **GitHub Follower Check** | Visits a GitHub profile and reports the follower count |
| **LinkedIn Birthday Detection** | Finds contacts with birthdays today and sends personalized wishes |
| **LinkedIn Reply to Wishes** | Scans unread messages and replies to birthday wishes |
| **Multi-Platform Support** | Extends all features to WhatsApp, Facebook Messenger, Instagram DM, Twitter/X, and Slack |

### 🔐 Security & Reliability

| Feature | Description |
| ------- | ----------- |
| **Session Management** | Browser cookies saved to disk — no repeated logins. Auto-expires after 12 hours |
| **Error Handling & Retry** | Every task retries up to 3 times with a 5-second delay between attempts |
| **Dry Run Mode** | Simulate the agent without sending any real messages |
| **Whitelist / Blacklist** | Control exactly which contacts to wish or always skip |
| **Reply Cooldown** | Prevents replying to the same contact within 30 days |
| **2FA Support** 🆕 | Full LinkedIn 2FA support — TOTP (auto-generates code), SMS OTP, Email OTP |
| **Proxy Rotation** 🆕 | Rotates proxies to avoid LinkedIn rate limits and IP bans |
| **VPN Auto-Switch** 🆕 | Automatically switches VPN server when LinkedIn blocks current IP |

### 🤖 AI Model Selector 🆕

| Feature | Description |
| ------- | ----------- |
| **GPT-4o / Gemini 2.5 Pro Switch** | Switch between OpenAI GPT-4o and Google Gemini 2.5 Pro from `.env` — no code change needed |
| **Fallback Logic** | Auto-falls back to Gemini if unknown model set. Clear error if API key missing |
| **Startup Log** | Model name logged at startup for transparency |

### 🧠 AI & Personalization

| Feature | Description |
| ------- | ----------- |
| **AI-Generated Custom Wishes** | Visits the contact's profile, reads their job and interests, generates a completely unique wish |
| **Contact Relationship Score** | Classifies each contact as Close Friend, Colleague, or Acquaintance and adjusts wish style |
| **Memory System** | Remembers key details from last year — references them in this year's wish |
| **Sentiment Analysis** | Detects if someone is sad, stressed, or lonely and replies with extra care |
| **Tone Matching** | Mirrors the contact's communication style — formal, casual, emoji-heavy, slang |
| **Multi-language Reply** | Detects the language of the wish and replies in the same language (17 languages) |
| **Wish Quality Scorer** | Scores every AI-generated wish 1–10 and auto-retries if below threshold |
| **Occasion Detection** | Detects promotions, new jobs, graduations, engagements, marriages and congratulates |
| **Personality Profiling** | Analyzes LinkedIn posts to detect MBTI type, dominant traits, tone, interests, communication style |
| **Emotional Intelligence** | Scores the emotional tone of every wish and reply — ensures empathy and warmth before sending |
| **Predictive Birthday** | Predicts upcoming birthdays before they officially appear on LinkedIn |
| **RAG-Based Memory** | ChromaDB vector store for long-term, semantic relationship memory |
| **Conversation Memory** | Maintains full conversation history for context-aware replies |

### 🎙️ Voice Messages

| Feature | Description |
| ------- | ----------- |
| **Voice Message Reply** | Generates a voice message from the reply text and sends it on WhatsApp |
| **AI-Generated Voice Wish** 🆕 | Converts birthday wish text to a realistic voice note (gTTS or ElevenLabs) |
| **gTTS Engine** | Free Google Text-to-Speech, no API key required |
| **ElevenLabs Engine** | Premium realistic voice generation |
| **Voice-to-Text Reply** | Transcribes incoming WhatsApp voice notes and auto-replies |
| **Auto Language Detection** | Selects the correct TTS language automatically |

### ⚙️ Smart Automation

| Feature | Description |
| ------- | ----------- |
| **Daily Scheduler** | Runs all tasks automatically at a configurable time every day |
| **Auto Timezone Scheduler** 🆕 | Fully automatic — detects contact's timezone from LinkedIn location and sends at 9:00 AM their local time |
| **Smart Follow-up Timing** 🆕 | If no reply in 3 days, automatically sends a warm follow-up. Skips if they replied |
| **Follow-up Messages** | Sends a warm follow-up message 2-3 days after each birthday wish |
| **Auto Reply to Follow-up** | When someone replies to a wish or follow-up, responds automatically |
| **Birthday Calendar Export** | Exports all contacts' birthdays to a `.ics` file for Google Calendar |
| **Birthday Reminder Email** | Sends a reminder email the day before a contact's birthday |
| **Birthday Miss Tracker** 🆕 | Detects which contacts had birthdays but received no wish — sends late wishes automatically |
| **LinkedIn Post Engagement** | Likes and comments on birthday contacts' latest LinkedIn posts |
| **Group Birthday Detection** | Finds birthday posts in LinkedIn Groups and engages with them |
| **Auto LinkedIn Connect** | Sends personalized connection requests to 2nd-degree wishers |
| **Personalized Connect After Wishing** 🆕 | After wishing a contact, sends a personalized connection request with a note referencing the wish |
| **Wish A/B Testing (Auto-Learning)** 🆕 | Tests 5 wish styles, tracks reply rates with decay weighting, auto-selects best style |
| **Best Time to Connect** | Analyzes activity patterns to find the optimal send time per contact |
| **Contact Categorizer** | Auto-categorizes contacts by industry, seniority, and location |
| **LinkedIn DM Campaign** | Sends personalized icebreaker messages to new connections |

### 🌐 Multi-Platform

| Platform | Features |
| -------- | -------- |
| **LinkedIn** | Birthday detection, wishing, replying, post engagement, connection requests |
| **WhatsApp** | Birthday replies, voice messages, voice-to-text |
| **Facebook** | Birthday replies |
| **Instagram** | Birthday replies, birthday post detection |
| **Twitter/X** 🆕 | Birthday mention detection, auto-reply to birthday tweets |
| **Slack** 🆕 | Birthday detection from workspace profiles, DM + channel announcements |

### 📋 Contact Management

| Feature | Description |
| ------- | ----------- |
| **Contact Notes** | Save personal notes per contact — injected into wish prompts automatically |
| **Memory System** | Year-over-year memory of job, company, life events, and interests |
| **Connection Strength Tracker** | Tracks interaction history and scores connection strength over time |
| **Relationship Health Score** | Weekly relationship health report sent to your email |
| **Relationship Decay Alert** 🆕 | Alerts when a contact hasn't been interacted with in 30/60/90+ days. Auto sends check-in |

### 👥 Multi-Account Support

| Feature | Description |
| ------- | ----------- |
| **Multiple LinkedIn Accounts** | Manage and rotate across multiple LinkedIn accounts |
| **Per-Account History** | Each account has independent wish history and contact memory |
| **Centralized Dashboard** | Single dashboard showing activity across all accounts |
| **Rate Limit Protection** | Automatically rotates accounts to avoid LinkedIn rate limits |

### 📊 Monitoring & Notifications

| Feature | Description |
| ------- | ----------- |
| **SQLite Logging** | Every action saved to `agent_history.db` |
| **Telegram Notification** | Sends a run summary to Telegram after each task |
| **Email Notification** | Sends a summary email via Gmail after each task |
| **Weekly Email Digest** | Summarizes wishes sent, upcoming birthdays, and fading connections |
| **Streamlit Control Dashboard** | Start/stop tasks, toggle Dry Run, view live logs |
| **Analytics Dashboard** | Charts for activity, platforms, languages, relationships, follow-ups |
| **Real-time Dashboard** | Live updates via FastAPI + WebSocket |
| **Contact Profile Cards** | Card view for every contact — notes, wish history, strength score |
| **Wish Preview Dashboard** | Preview, edit, approve, or reject wishes before sending |
| **Full Web App** | FastAPI + React + JWT auth + multi-user support |
| **Browser Extension** | LinkedIn sidebar showing contact info, notes, and wish history |
| **Mobile App** | Mobile-optimized Streamlit app deployable to Streamlit Cloud |
| **Onboarding Wizard** | Step-by-step first-time setup guide |
| **Dark / Light Mode** | Theme toggle available across all dashboards |

---

## 🗂️ Project Structure

```
Birthday-Wishes-Agent/
│
├── agent.py                     # Main agent — all tasks, toggles, scheduler
│
├── ── AI & Personalization ──
├── wish_scorer.py               # Wish quality scorer (1-10) with auto-retry
├── sentiment.py                 # Sentiment analysis (happy/sad/stressed/lonely)
├── tone_matching.py             # Communication tone detection and mirroring
├── multilang_reply.py           # Multi-language reply (17 languages)
├── occasion_detection.py        # Life event detection and congratulations
├── memory.py                    # Year-over-year contact memory system
├── personality_profiling.py     # MBTI personality detection from LinkedIn posts
├── emotional_intelligence.py    # Emotional intelligence scoring
├── predictive_birthday.py       # Predict upcoming birthdays early
├── rag_memory.py                # ChromaDB vector store for long-term memory
│
├── ── Contact Management ──
├── contact_notes.py             # Personal notes per contact
├── connection_tracker.py        # Connection strength tracker
├── contact_categorizer.py       # Auto-categorize by industry, seniority
├── ab_testing.py                # Wish A/B testing with auto-learning (5 styles)
├── decay_alert.py               # Relationship decay alert + auto check-in 🆕
│
├── ── Automation ──
├── auto_reply_followup.py       # Auto reply to follow-up responses
├── auto_connect.py              # Auto LinkedIn connect for 2nd-degree wishers
├── personalized_connect.py      # Connection request with note after wishing 🆕
├── smart_followup.py            # Smart follow-up if no reply in 3 days 🆕
├── auto_timezone_scheduler.py   # Fully automatic timezone-aware scheduling 🆕
├── birthday_miss_tracker.py     # Detect and send missed birthday wishes 🆕
├── post_engagement.py           # LinkedIn post like and comment
├── group_birthday.py            # LinkedIn Group birthday detection
├── birthday_reminder.py         # Birthday reminder email (day before)
├── best_time_connect.py         # Activity pattern analyzer
├── dm_campaign.py               # LinkedIn DM campaign for new connections
├── voice.py                     # Voice message + AI-generated voice wish 🆕
├── voice_to_text.py             # Transcribe WhatsApp voice notes
│
├── ── Platforms ──
├── platforms/
│   ├── linkedin.py              # LinkedIn with AI wishes + relationship scoring
│   ├── whatsapp.py              # WhatsApp Web with voice message support
│   ├── facebook.py              # Facebook Messenger
│   └── instagram.py            # Instagram DM
├── twitter_birthday.py          # Twitter/X birthday mention detection 🆕
├── slack_birthday_bot.py        # Slack workspace birthday bot 🆕
│
├── ── Security ──
├── two_factor_auth.py           # 2FA support — TOTP, SMS, Email 🆕
├── proxy_rotation.py            # Proxy rotation to avoid rate limits 🆕
├── vpn_switch.py                # VPN auto-switch when IP blocked 🆕
│
├── ── Notifications ──
├── notifications.py             # Telegram & Email notifications
├── email_digest.py              # Weekly email digest
├── relationship_health.py       # Relationship health score report
│
├── ── Multi-Account ──
├── multi_account.py             # Manage and rotate LinkedIn accounts
│
├── ── Dashboards ──
├── dashboard.py                 # Streamlit control dashboard
├── analytics.py                 # Analytics dashboard with charts
├── profile_cards.py             # Contact profile cards
├── wish_preview.py              # Wish preview — approve/edit/reject
├── mobile_app.py                # Mobile app for Streamlit Cloud
├── realtime_dashboard.py        # FastAPI + WebSocket live dashboard
├── ab_dashboard.py              # A/B testing dashboard
├── webapp/                      # FastAPI + React web app
├── extension/                   # LinkedIn sidebar browser extension
├── onboarding.py                # First-time setup wizard
├── theme_toggle.py              # Dark/Light mode helper
│
├── ── DevOps ──
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/ci-cd.yml  # GitHub Actions pipeline
├── deploy/aws/                  # AWS deployment configs
├── deploy/gcp/                  # GCP deployment configs
│
├── .env                         # Your credentials (never commit!)
├── .env.example                 # Credentials template
├── requirements.txt
│
├── agent.log                    # Live log (auto-generated)
├── agent_history.db             # SQLite database (auto-generated)
├── birthdays.ics                # Exported calendar (auto-generated)
├── audio_messages/              # Voice files (auto-generated)
├── proxies.txt                  # Proxy list (optional)
└── browser_profile/             # Browser cookies (auto-generated)
```

---

## 🌿 Branch Guide

| Branch | Status | What was added |
| ------ | ------ | -------------- |
| `main` | 🟢 Active (v6.0) | All features merged |
| `6.0` | ✅ Merged | AI model selector, A/B auto-learning, voice wish, decay alert, miss tracker, Twitter/X, Slack, auto timezone, smart follow-up, personalized connect, 2FA, proxy rotation, VPN auto-switch |
| `5.0` | ✅ Stable tag | Relationship health score, RAG memory, A/B testing, web app, browser extension |
| `4.0` | ✅ Stable tag | Reminder emails, tone matching, wish quality scorer, dark mode |
| `feature/cloud-deployment` | ✅ Merged | AWS + GCP cloud deployment |
| `feature/docker-support` | ✅ Merged | Docker + docker-compose one-command setup |
| `feature/emotional-intelligence` | ✅ Merged | Emotional intelligence scoring |
| `feature/github-actions-cicd` | ✅ Merged | GitHub Actions CI/CD pipeline |
| `feature/multi-account-support` | ✅ Merged | Multiple LinkedIn account management |
| `feature/personality-profiling` | ✅ Merged | MBTI detection from LinkedIn posts |
| `feature/predictive-birthday` | ✅ Merged | Predict birthdays before they appear |

---

## 🔧 Prerequisites

- Python 3.10 or higher
- Google Chrome browser
- LinkedIn account
- API key for OpenAI or Google Gemini
- _(Optional)_ Facebook, Instagram, Twitter/X, Slack accounts
- _(Optional)_ Telegram bot token
- _(Optional)_ Gmail App Password
- _(Optional)_ ElevenLabs API key for premium voice
- _(Optional)_ Docker (for containerized setup)
- _(Optional)_ AWS or GCP account (for cloud deployment)
- _(Optional)_ NordVPN / ExpressVPN / OpenVPN (for VPN auto-switch)

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

```bash
docker-compose up --build   # Build and run
docker-compose up -d        # Run in background
docker-compose logs -f      # View live logs
docker-compose down         # Stop
```

---

## ☁️ Cloud Deployment

### AWS
```bash
# See deploy/aws/ for full configuration
```

### GCP
```bash
# See deploy/gcp/ for full configuration
```

---

## ⚙️ Configuration

### 1. Set up your `.env` file

```bash
cp .env.example .env
```

```env
# ── AI Model Selector 🆕 ──────────────────────
AI_MODEL=gemini            # gemini / gpt-4o
GOOGLE_API_KEY=
OPENAI_API_KEY=

# ── LinkedIn ──────────────────────────────────
USERNAME=your_linkedin_email
PASSWORD=your_linkedin_password
GITHUB_URL=https://github.com/yourusername

# ── LinkedIn 2FA 🆕 ───────────────────────────
LINKEDIN_2FA_ENABLED=false
LINKEDIN_2FA_METHOD=totp   # totp / sms / email
LINKEDIN_TOTP_SECRET=      # Base32 secret from authenticator app
LINKEDIN_OTP_WAIT=30

# ── Multi-Account ─────────────────────────────
LINKEDIN_ACCOUNTS=account1@email.com,account2@email.com
LINKEDIN_PASSWORDS=password1,password2

# ── Proxy Rotation 🆕 ─────────────────────────
PROXY_ENABLED=false
PROXY_LIST=http://user:pass@ip1:port,http://user:pass@ip2:port
PROXY_ROTATION=round_robin  # round_robin / random / fastest

# ── VPN Auto-Switch 🆕 ────────────────────────
VPN_ENABLED=false
VPN_CLIENT=nordvpn          # nordvpn / expressvpn / openvpn / custom
VPN_SERVERS=us1,uk1,de1
VPN_ROTATION=round_robin

# ── Twitter/X 🆕 ──────────────────────────────
TWITTER_BEARER_TOKEN=
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=

# ── Slack 🆕 ──────────────────────────────────
SLACK_BOT_TOKEN=xoxb-...
SLACK_BIRTHDAY_CHANNEL=#birthdays

# ── Facebook (optional) ───────────────────────
FB_USERNAME=
FB_PASSWORD=

# ── Instagram (optional) ──────────────────────
IG_USERNAME=
IG_PASSWORD=

# ── Telegram (optional) ───────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ── Email / Gmail ─────────────────────────────
EMAIL_SENDER=your_gmail@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=receiver@example.com
REMINDER_RECIPIENTS=you@gmail.com

# ── Voice ─────────────────────────────────────
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
TRANSCRIPTION_ENGINE=whisper

# ── Feature Flags ─────────────────────────────
CONNECTION_TRACKER_ENABLED=true
```

### 2. Key `agent.py` settings

```python
DRY_RUN = True

# Platform toggles
ENABLE_LINKEDIN  = True
ENABLE_WHATSAPP  = True
ENABLE_FACEBOOK  = True
ENABLE_INSTAGRAM = True

# AI features
PERSONALITY_PROFILING_ENABLED  = True
EMOTIONAL_INTELLIGENCE_ENABLED = True
PREDICTIVE_BIRTHDAY_ENABLED    = True
RAG_MEMORY_ENABLED             = True
AB_TESTING_ENABLED             = True

# Automation
AUTO_CONNECT_ENABLED           = True
POST_ENGAGEMENT_ENABLED        = True
GROUP_BIRTHDAY_ENABLED         = True
BIRTHDAY_REMINDER_ENABLED      = True
AUTO_REPLY_FOLLOWUP_ENABLED    = True
CONNECTION_TRACKER_ENABLED     = True
DM_CAMPAIGN_ENABLED            = True
MULTI_ACCOUNT_ENABLED          = True

# Scheduling
SCHEDULE_HOUR   = 9
SCHEDULE_MINUTE = 0
COOLDOWN_DAYS   = 30
FOLLOWUP_DAYS   = 3
```

---

## 📋 Usage

### Option 1 — Run a task immediately

```bash
python agent.py
```

Uncomment desired task in `agent.py`:

```python
await run_birthday_detection_task()
# await run_ai_custom_wish_task()
# await run_linkedin_reply_task()
# await run_whatsapp_reply_task()
# await run_twitter_birthday_task()     # 🆕
# await run_slack_birthday_task()       # 🆕
# await run_smart_followup_task()       # 🆕
# await run_decay_alert_task()          # 🆕
# await run_miss_tracker_task()         # 🆕
# await run_auto_timezone_task()        # 🆕
# await run_personalized_connect_task() # 🆕
```

### Option 2 — Daily Scheduler

```python
await run_scheduler()
```

### Option 3 — Streamlit Dashboards

```bash
streamlit run dashboard.py
streamlit run analytics.py
streamlit run ab_dashboard.py
streamlit run mobile_app.py
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

## 🔐 2FA Setup (LinkedIn)

### TOTP (Recommended — fully automatic)

1. Go to LinkedIn **Settings → Sign in & Security → Two-step verification**
2. Choose **Authenticator App**
3. Add to `.env`:
```env
LINKEDIN_2FA_ENABLED=true
LINKEDIN_2FA_METHOD=totp
LINKEDIN_TOTP_SECRET=YOUR_BASE32_SECRET
```

The agent will auto-generate the 6-digit code every 30 seconds.

### SMS / Email OTP
```env
LINKEDIN_2FA_ENABLED=true
LINKEDIN_2FA_METHOD=sms   # or email
LINKEDIN_OTP_WAIT=30
```

---

## 🛡️ Proxy & VPN Setup

### Proxy Rotation
```env
PROXY_ENABLED=true
PROXY_LIST=http://user:pass@ip1:port,http://user:pass@ip2:port
PROXY_ROTATION=round_robin
```

### VPN Auto-Switch (NordVPN example)
```env
VPN_ENABLED=true
VPN_CLIENT=nordvpn
VPN_SERVERS=us1,uk2,de3
VPN_ROTATION=round_robin
```

---

## 👥 Multi-Account Support

- Configure multiple LinkedIn accounts in `.env` via `LINKEDIN_ACCOUNTS`
- Agent automatically rotates across accounts to avoid rate limiting
- Each account maintains independent wish history and contact memory

---

## ⚙️ CI/CD Pipeline

- Triggers on every push to `main` and all PRs
- Linting + unit tests
- Docker build verification
- Deploy step disabled until Docker Hub secrets configured

---

## 🌍 Supported Languages

| Language | Detection | Reply |
| -------- | --------- | ----- |
| 🇬🇧 English | ✅ | ✅ |
| 🇧🇩 Bengali | ✅ | ✅ |
| 🇸🇦 Arabic | ✅ | ✅ |
| 🇮🇳 Hindi | ✅ | ✅ |
| 🇵🇰 Urdu | ✅ | ✅ |
| 🇪🇸 Spanish | ✅ | ✅ |
| 🇫🇷 French | ✅ | ✅ |
| 🇩🇪 German | ✅ | ✅ |
| 🇹🇷 Turkish | ✅ | ✅ |
| 🇮🇩 Indonesian | ✅ | ✅ |
| 🇲🇾 Malay | ✅ | ✅ |
| 🇨🇳 Chinese | ✅ | ✅ |
| 🇯🇵 Japanese | ✅ | ✅ |
| 🇰🇷 Korean | ✅ | ✅ |
| 🇧🇷 Portuguese | ✅ | ✅ |
| 🇮🇹 Italian | ✅ | ✅ |
| 🇷🇺 Russian | ✅ | ✅ |

---

## 💝 Relationship Scoring

| Score | Type | Wish Style |
| ----- | ---- | ---------- |
| 60-100 | 🟢 Close Friend | Casual, warm, funny |
| 30-59 | 🔵 Colleague | Professional but friendly |
| 0-29 | ⚪ Acquaintance | Polite and brief |

---

## 🎭 Tone Matching

| Their Tone | Reply Style |
| ---------- | ----------- |
| Formal | Full sentences, no emoji, professional |
| Semi-formal | Friendly, 1 emoji max |
| Casual | Relaxed, contractions, 2 emoji |
| Very Casual | Slang ok, short, fun |
| Emoji-heavy | Match their emoji count |

---

## 🔄 Changelog

### v6.0 (current)

**🤖 AI & Intelligence**
- ✅ **AI Model Selector** — switch between GPT-4o and Gemini 2.5 Pro from `.env`
- ✅ **A/B Testing Auto-Learning** — 5 wish styles, decay weighting, auto-selects best

**🎙️ Voice**
- ✅ **AI-Generated Voice Wish** — text to realistic voice note (gTTS + ElevenLabs)

**🌐 New Platforms**
- ✅ **Twitter/X Birthday Detection** — detects birthday mentions, auto-replies
- ✅ **Slack Birthday Bot** — DM + channel birthday announcements

**⚙️ Automation**
- ✅ **Auto Timezone Scheduler** — fully automatic, detects timezone from LinkedIn location
- ✅ **Smart Follow-up** — auto follow-up if no reply in 3 days
- ✅ **Birthday Miss Tracker** — detects missed birthdays, sends late wishes
- ✅ **Personalized Connect After Wishing** — connection request with note after wishing
- ✅ **Relationship Decay Alert** — alerts when contacts are fading (30/60/90+ days)

**🔐 Security**
- ✅ **2FA Support** — TOTP (auto-generates), SMS OTP, Email OTP
- ✅ **Proxy Rotation** — rotates proxies to avoid rate limits
- ✅ **VPN Auto-Switch** — switches VPN when IP is blocked

### v5.0

- ✅ Relationship Health Score, RAG Memory (ChromaDB), Wish A/B Testing
- ✅ Voice-to-Text Reply, Real-time Dashboard, Full Web App
- ✅ Browser Extension, Weekly Email Digest, Onboarding Wizard
- ✅ Conversation Memory, Contact Categorizer, LinkedIn DM Campaign

### v4.0

- ✅ Personality Profiling (MBTI), Sentiment Analysis, Memory System
- ✅ LinkedIn Post Engagement, Birthday Reminder Email, Contact Notes
- ✅ Wish Quality Scorer, Group Birthday Detection, Connection Strength Tracker
- ✅ Tone Matching, Occasion Detection, Multi-language Reply (17 languages)
- ✅ Dark/Light Mode, Wish Preview Dashboard, Contact Profile Cards

### v3.0

- ✅ Multi-platform (WhatsApp, Facebook, Instagram)
- ✅ AI-generated custom wishes, Voice messages, Follow-up messages
- ✅ Birthday calendar export, Smart timezone timing, Analytics dashboard

### v2.0

- ✅ Session management, Error handling & retry, Daily scheduler
- ✅ Dry Run mode, Streamlit dashboard, Telegram & Email notifications
- ✅ SQLite logging, Whitelist / Blacklist, Reply cooldown

### v1.0

- ✅ GitHub follower check, LinkedIn birthday wish reply (basic)

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
