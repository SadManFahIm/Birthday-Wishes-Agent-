# 🎂 Birthday Wishes Agent — Changelog

All notable changes to this project are documented here.
Versions follow **feature-based releases** from `v1.0` → `v8.0`.

---

## [v8.0] — Current Development Branch
> Branch: `8.0` | Status: 🟡 In Progress

### 🧠 AI & Intelligence
- **Wish Style Memory** — tracks which style (funny/formal/poetic/warm/motivational/nostalgic/short_punchy) was used per contact each year; always picks a fresh angle so wishes never feel repetitive
- **Context-Aware Opening Line** — scans contact's recent LinkedIn activity (new job, promotion, product launch, viral post) and generates a hyper-specific opening line referencing it naturally
- **Multi-Wish Variant Generator** — generates 3 distinct variants (formal / casual / funny) side-by-side with live personalization scores; pick, edit, or regenerate individually before sending
- **Smart Emoji Calibration** — learns each contact's emoji density from reply history and calibrates the wish accordingly (none / minimal / moderate / heavy / very_heavy)

### ⚙️ Automation
- **Conditional Workflow Builder** — visual IF-THEN-ELSE rule editor; create custom automation rules (e.g. "no reply in 3 days → followup → decay alert") from the dashboard without touching code
- **Batch Approve Queue** — all AI-generated wishes land in a morning review queue; bulk approve / reject / edit / send in one screen
- **Smart Send-Time Optimizer** — learns per-platform peak activity hours from reply timestamps and schedules wishes at each contact's personal active window
- **Auto-Pause on Anomaly** — monitors error patterns in real-time; auto-pauses all tasks on consecutive failures or rate-limit spikes and sends Telegram alert; requires manual resume

### 📊 Analytics & Insights
- **Weekly/Monthly Insight Report** — auto-generated summary: best platform, best wish style, score trends, fastest repliers, relationship movement, key takeaways
- **Reply Sentiment Trend** — tracks reply tone (excited → positive → neutral → cold → no_reply) per contact over time; surfaces declining relationships before they fully disengage
- **Platform ROI Comparison** — measures effort vs engagement across all 6 platforms; scores each on ROI and recommends where to double down, maintain, or reduce
- **Personalization Score Trend** — monthly/weekly chart of wish quality over time; per-contact drill-down with component breakdown; identifies weakest scoring areas

### 📋 Contact & Relationship
- **Relationship Tiering Auto-Adjust** — automatically moves contacts between Close Friend / Colleague / Acquaintance based on reply speed, depth, frequency, and sentiment — not a static manual score
- **Mutual Connection Insights** — detects shared connections, interests, alumni ties, past companies, and conversation topics; generates a natural sentence to weave into the wish
- **Life Event Timeline Merge** — unified "important dates" calendar per contact: birthday, promotion, job change, work anniversary, graduation, marriage, and more; agent queues the right action for each
- **VIP Contact Flagging** — mark contacts as Platinum / Gold / Silver VIP; enforces minimum personalization score, mandatory manual review, optional voice note and multi-platform sending

### 🏗️ Project Structure
- **Full folder restructure** — 85+ flat root files reorganized into `ai/`, `automation/`, `platforms/`, `contacts/`, `security/`, `detection/`, `notifications/`, `multi_account/`, `dashboards/`, `config/`, `tests/`
- **`config/settings.py`** — centralized settings loader using Pydantic BaseSettings
- **`PROJECT_STRUCTURE.md`** — full documented folder tree

---

## [v7.0] — Merged ✅
> Branch: `7.0` | Merged to: `main`

### 🎛️ Dashboards
- **Unified Command Center** (`command_center.py`) — single dashboard to control every platform, trigger any of 13 tasks on demand, view live agent status, and review logs & alerts; dry run toggle
- **Real-time Wish Preview** (`wish_preview.py`) — select a contact, AI-generate a wish, edit manually, and watch the personalization score update live; platform-accurate LinkedIn/WhatsApp render
- **Contact Timeline View** (`contact_timeline.py`) — full chronological interaction history per contact: wishes sent, replies, follow-ups, decay alerts, health changes; search + event-type filters

### 🧠 AI
- **Wish Personalization Scorer** (`wish_personalization_score.py`) — scores every wish 1–10 on name, job/company reference, industry, memory, unique language, length, and warmth; auto-retries if below 6

---

## [v6.0] — Merged ✅
> Branch: `6.0` | Merged to: `main`

### 🤖 AI & Model
- **AI Model Selector** — switch between OpenAI GPT-4o and Google Gemini 2.5 Pro from `.env` with no code changes; auto-fallback logic; model name logged at startup
- **A/B Testing Auto-Learning** — 5 wish styles tested, reply rates tracked with decay weighting, best style auto-selected per contact

### 🎙️ Voice
- **AI-Generated Voice Wish** — converts birthday wish text to realistic voice note using gTTS (free) or ElevenLabs (premium)

### 🌐 New Platforms
- **Twitter/X Birthday Detection** — detects birthday mentions and auto-replies
- **Slack Birthday Bot** — detects birthdays from workspace profiles; sends DM + channel announcement

### ⚙️ Automation
- **Auto Timezone Scheduler** — fully automatic: detects contact's timezone from LinkedIn location, sends at 9:00 AM their local time
- **Smart Follow-up** — if no reply in 3 days, automatically sends a warm follow-up; skips if they already replied
- **Birthday Miss Tracker** — detects which contacts had birthdays with no wish sent; queues late wishes automatically
- **Personalized Connect After Wishing** — sends a personalized LinkedIn connection request with a note referencing the wish
- **Relationship Decay Alert** — alerts when a contact has had no interaction in 30/60/90+ days; auto-sends check-in message

### 🔐 Security
- **2FA Support** — full LinkedIn 2FA: TOTP (auto-generates 6-digit code), SMS OTP, Email OTP
- **Proxy Rotation** — rotates proxies to avoid LinkedIn rate limits and IP bans
- **VPN Auto-Switch** — automatically switches VPN server when LinkedIn blocks current IP

---

## [v5.0] — Stable Tag ✅
> Branch: `5.0` | Stable release

### 🧠 AI
- **RAG-Based Memory** — ChromaDB vector store for long-term semantic relationship memory; retrieves relevant past context for each wish
- **Conversation Memory** — maintains full conversation history for context-aware replies

### 📊 Dashboards
- **Wish A/B Testing Dashboard** (`ab_dashboard.py`) — visual A/B results per style
- **Wish Preview Dashboard** — preview, edit, approve, or reject AI wishes before sending
- **Real-time Dashboard** — FastAPI + WebSocket live activity feed
- **Contact Profile Cards** — card view per contact with notes, wish history, strength score
- **Full Web App** — FastAPI + React + JWT auth + multi-user support
- **Mobile App** — Streamlit mobile-optimized version deployable to Streamlit Cloud
- **Onboarding Wizard** — step-by-step first-time setup guide

### 📋 Contact
- **Relationship Health Score** — weekly health report emailed to user
- **Weekly Email Digest** — summarizes wishes sent, upcoming birthdays, fading connections
- **Browser Extension** — LinkedIn sidebar showing contact info, notes, and wish history
- **Contact Categorizer** — auto-categorizes contacts by industry, seniority, and location
- **LinkedIn DM Campaign** — personalized icebreaker messages to new connections

---

## [v4.0] — Stable Tag ✅
> Branch: `4.0` | Stable release

### 🧠 AI & Personalization
- **Personality Profiling** — MBTI type detection from LinkedIn posts; dominant traits, tone, interests, communication style
- **Emotional Intelligence Scoring** — scores emotional tone of every wish and reply; ensures empathy before sending
- **Predictive Birthday** — predicts upcoming birthdays before they officially appear on LinkedIn
- **Wish Quality Scorer** (`wish_scorer.py`) — scores AI wishes 1–10 on grammar and tone; auto-retries below threshold
- **Sentiment Analysis** — detects if contact is sad, stressed, or lonely; adjusts reply with extra care
- **Tone Matching** — mirrors contact's communication style (formal / casual / emoji-heavy / slang)
- **Occasion Detection** — detects promotions, new jobs, graduations, engagements, marriages and sends congratulations
- **Multi-language Reply** — detects reply language and responds in the same language (17 languages supported)
- **Memory System** — remembers key details year-over-year; references them in next year's wish

### 📊 Dashboards
- **Analytics Dashboard** — charts for activity, platforms, languages, relationships, follow-ups
- **Dark/Light Mode** — theme toggle across all dashboards

### 📋 Contact
- **Contact Notes** — save personal notes per contact; injected into wish prompts automatically
- **Connection Strength Tracker** — tracks interaction history and scores connection strength over time
- **LinkedIn Post Engagement** — likes and comments on birthday contacts' latest posts
- **Birthday Reminder Email** — sends reminder email the day before a contact's birthday
- **Group Birthday Detection** — finds birthday posts in LinkedIn Groups and engages

---

## [v3.0] — Merged ✅
> Branch: merged into `main`

### 🌐 Multi-Platform Expansion
- **WhatsApp** — birthday replies with voice message support
- **Facebook Messenger** — birthday replies
- **Instagram DM** — birthday replies and birthday post detection

### ⚙️ Automation
- **AI-Generated Custom Wishes** — visits contact's profile, reads job and interests, generates a unique wish
- **Voice Messages** — generates voice message from reply text and sends on WhatsApp
- **Voice-to-Text Reply** — transcribes incoming WhatsApp voice notes and auto-replies
- **Follow-up Messages** — sends warm follow-up 2–3 days after each birthday wish
- **Auto Reply to Follow-up** — when contact replies to wish/follow-up, responds automatically
- **Birthday Calendar Export** — exports all contacts' birthdays to `.ics` for Google Calendar
- **LinkedIn DM Auto Connect** — sends personalized connection requests to 2nd-degree wishers
- **Best Time to Connect** — analyzes activity patterns to find optimal send time per contact

### 📊 Dashboards
- **Analytics Dashboard** (initial version) — basic charts for activity and platforms

---

## [v2.0] — Merged ✅
> Branch: merged into `main`

### 🔐 Reliability & Control
- **Session Management** — browser cookies saved to disk; auto-expires after 12 hours
- **Error Handling & Retry** — every task retries up to 3 times with 5-second delays
- **Dry Run Mode** — simulate the agent without sending any real messages
- **Whitelist / Blacklist** — control exactly which contacts to wish or always skip
- **Reply Cooldown** — prevents replying to the same contact within 30 days

### 📊 Monitoring
- **Streamlit Control Dashboard** — start/stop tasks, toggle dry run, view live logs
- **SQLite Logging** — every action saved to `agent_history.db`
- **Telegram Notification** — sends run summary to Telegram after each task
- **Email Notification** — sends summary email via Gmail after each task

### ⚙️ Scheduling
- **Daily Scheduler** — runs all tasks automatically at a configurable time every day

### 👥 Multi-Account Support
- **Multiple LinkedIn Accounts** — manage and rotate across multiple accounts
- **Per-Account History** — each account has independent wish history and contact memory
- **Centralized Dashboard** — single view showing activity across all accounts
- **Rate Limit Protection** — automatically rotates accounts to avoid LinkedIn rate limits

---

## [v1.0] — Initial Release ✅
> Branch: base | First working version

### 🤖 Core Features
- **GitHub Follower Check** — visits a GitHub profile and reports follower count
- **LinkedIn Birthday Detection** — finds contacts with birthdays today
- **LinkedIn Birthday Wish Reply** — scans unread messages and sends a basic reply

---

## 📊 Project Stats

| Metric | Count |
|--------|-------|
| Total versions | 8 |
| Total `.py` files | 85+ |
| Platforms supported | 6 (LinkedIn, WhatsApp, Facebook, Instagram, Twitter/X, Slack) |
| Languages supported | 17 |
| Streamlit dashboards | 12+ |
| SQLite tables | ~25 |
| CI/CD | GitHub Actions (flake8 + pytest + Docker) |

---

## 🌿 Branch History

| Branch | Status | Description |
|--------|--------|-------------|
| `main` | 🟢 Active | Latest stable — v7.0 merged |
| `8.0` | 🟡 In Progress | v8.0 features being developed |
| `7.0` | ✅ Merged | Command Center, Wish Preview, Timeline, Scorer |
| `6.0` | ✅ Merged | AI model selector, Twitter/X, Slack, Security |
| `5.0` | ✅ Stable tag | RAG memory, Web app, Browser extension |
| `4.0` | ✅ Stable tag | Personality, Emotional IQ, Tone matching |
| `feature/cloud-deployment` | ✅ Merged | AWS + GCP configs |
| `feature/docker-support` | ✅ Merged | Docker + docker-compose |
| `feature/github-actions-cicd` | ✅ Merged | CI/CD pipeline |
| `feature/multi-account-support` | ✅ Merged | Multi-account management |
| `feature/emotional-intelligence` | ✅ Merged | EQ scoring |
| `feature/personality-profiling` | ✅ Merged | MBTI detection |
| `feature/predictive-birthday` | ✅ Merged | Early birthday prediction |

---

*Maintained by [Faahim Sadman](https://github.com/SadManFahIm)*
