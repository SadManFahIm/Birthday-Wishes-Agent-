# LinkedIn Birthday Wishes Agent 🎂🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Version](https://img.shields.io/badge/version-3.0-brightgreen)
![LangChain](https://img.shields.io/badge/LangChain-powered-blueviolet)
![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-orange)
![Streamlit](https://img.shields.io/badge/Streamlit-Cloud-red)

An intelligent, multi-platform browser automation agent built with Python, LangChain, and `browser_use` that automatically manages birthday wishes across LinkedIn, WhatsApp, Facebook, and Instagram — with AI-generated personalized messages, voice replies, smart timezone scheduling, and a mobile-accessible dashboard.

---

## 📝 Introduction

This project demonstrates how to build a production-ready AI agent pipeline using Python, LangChain, and browser automation.

**v3.0** is a complete overhaul — adding multi-platform support, AI-generated custom wishes, voice messages, contact relationship scoring, follow-up automation, birthday calendar export, smart timezone timing, an analytics dashboard, and a mobile app deployable to Streamlit Cloud.

---

## ✨ Features

### 🤖 Core Agent

| Feature                         | Description                                                                              |
| ------------------------------- | ---------------------------------------------------------------------------------------- |
| **GitHub Follower Check**       | Visits a GitHub profile and reports the follower count                                   |
| **LinkedIn Birthday Detection** | Finds contacts with birthdays today and sends personalized wishes                        |
| **LinkedIn Reply to Wishes**    | Scans unread messages and replies to birthday wishes                                     |
| **Multi-Platform Support**      | Extends birthday detection and replies to WhatsApp, Facebook Messenger, and Instagram DM |

### 🔐 Security & Reliability

| Feature                    | Description                                                                        |
| -------------------------- | ---------------------------------------------------------------------------------- |
| **Session Management**     | Browser cookies saved to disk — no repeated logins. Auto-expires after 12 hours    |
| **Error Handling & Retry** | Every task retries up to 3 times with a 5-second delay between attempts            |
| **Dry Run Mode**           | Set `DRY_RUN = True` to fully simulate the agent without sending any real messages |
| **Whitelist / Blacklist**  | Control exactly which contacts to wish or always skip                              |
| **Reply Cooldown**         | Prevents replying to the same contact more than once within 30 days                |

### 🧠 AI & Personalization

| Feature                        | Description                                                                                                                                                                             |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Personalized Replies**       | Replies use the sender's actual first name from each message thread                                                                                                                     |
| **AI-Generated Custom Wishes** | Visits the contact's LinkedIn profile, reads their job title, company, and interests, then generates a completely unique wish using the LLM — no templates                              |
| **Contact Relationship Score** | Classifies each contact as Close Friend, Colleague, or Acquaintance based on mutual connections, connection duration, and interaction history — then selects the appropriate wish style |
| **Better Wish Detection**      | Detects direct, indirect, and creative birthday phrases across 9+ languages                                                                                                             |
| **Multi-Language Support**     | Detects birthday wishes in Bengali, Arabic, Hindi, Spanish, French, German, Turkish, Indonesian, and more                                                                               |
| **Sentiment Awareness**        | Relationship-aware tone — casual for friends, professional for colleagues, polite for acquaintances                                                                                     |

### 🎙️ Voice Messages

| Feature                     | Description                                                                                  |
| --------------------------- | -------------------------------------------------------------------------------------------- |
| **Voice Message Reply**     | Generates a voice message from the reply text and sends it on WhatsApp instead of plain text |
| **gTTS Engine**             | Free Google Text-to-Speech, no API key required                                              |
| **ElevenLabs Engine**       | Premium realistic voice generation via ElevenLabs API                                        |
| **Auto Language Detection** | Detects Bengali, Arabic, Hindi, and English to select the correct TTS language               |
| **Auto Cleanup**            | Generated audio files are deleted after being sent                                           |

### ⚙️ Smart Automation

| Feature                      | Description                                                                                                                |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **Daily Scheduler**          | Runs all tasks automatically every day at a configurable time                                                              |
| **Smart Timing**             | Detects the contact's timezone from their LinkedIn location and sends wishes at 9:00 AM their local time — not midnight    |
| **Follow-up Messages**       | Automatically sends a warm follow-up message 2–3 days after a birthday wish is sent                                        |
| **Birthday Calendar Export** | Scrapes LinkedIn contacts' birthdays and exports a `.ics` file importable into Google Calendar, Apple Calendar, or Outlook |
| **Platform Toggles**         | Enable or disable LinkedIn, WhatsApp, Facebook, and Instagram independently                                                |

### 📊 Monitoring & Notifications

| Feature                   | Description                                                                                                                               |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **SQLite Logging**        | Every action is saved to `agent_history.db` with full history tracking                                                                    |
| **Telegram Notification** | Sends a run summary to Telegram after each task completes                                                                                 |
| **Email Notification**    | Sends a summary email via Gmail after each task completes                                                                                 |
| **Streamlit Dashboard**   | Desktop web UI to control the agent, toggle Dry Run, set schedule time, and view live logs                                                |
| **Analytics Dashboard**   | Charts for daily activity, platform breakdown, relationship breakdown, language breakdown, monthly summary, and follow-up completion rate |
| **Mobile App**            | Mobile-optimized Streamlit app deployable to Streamlit Cloud — control the agent from any phone or browser                                |

---

## 🗂️ Project Structure

```
Birthday-Wishes-Agent/
│
├── agent.py                  # Main agent — all tasks and scheduler
├── notifications.py          # Telegram & Email notification handlers
├── voice.py                  # Voice message generation (gTTS + ElevenLabs)
├── wish_generator.py         # AI-powered custom wish generator
├── relationship.py           # Contact relationship scoring
├── followup.py               # Follow-up message scheduler and sender
├── calendar_export.py        # Birthday calendar export to .ics
├── smart_timing.py           # Timezone-aware optimal send time
│
├── platforms/
│   ├── __init__.py           # Platform module entry point
│   ├── linkedin.py           # LinkedIn with AI wishes + relationship scoring
│   ├── whatsapp.py           # WhatsApp Web with voice message support
│   ├── facebook.py           # Facebook Messenger
│   └── instagram.py          # Instagram DM
│
├── dashboard.py              # Streamlit control dashboard (desktop)
├── analytics.py              # Streamlit analytics dashboard
├── mobile_app.py             # Mobile-optimized Streamlit app (Streamlit Cloud)
│
├── .streamlit/
│   ├── config.toml           # Streamlit theme and server config
│   └── secrets.toml.example  # Secrets template for Streamlit Cloud
│
├── .env                      # Your credentials (never commit this!)
├── .env.example              # Credentials template
├── .gitignore                # Protects .env and secrets.toml
├── requirements.txt          # Python dependencies
│
├── agent.log                 # Live log file (auto-generated)
├── agent_history.db          # SQLite history database (auto-generated)
├── birthdays.ics             # Exported calendar file (auto-generated)
├── audio_messages/           # Temporary voice files (auto-generated)
├── linkedin_session.json     # Session timestamp (auto-generated)
└── browser_profile/          # Browser cookies (auto-generated)
```

---

## 🔧 Prerequisites

- Python 3.10 or higher
- pip (Python package installer)
- Google Chrome browser
- LinkedIn account
- API key for OpenAI or Google Gemini
- _(Optional)_ Facebook and Instagram accounts for multi-platform support
- _(Optional)_ Telegram bot token for notifications
- _(Optional)_ Gmail App Password for email notifications
- _(Optional)_ ElevenLabs API key for premium voice messages

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

## ⚙️ Configuration

### 1. Set up your `.env` file

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# LLM API Key (choose one)
OPENAI_API_KEY=your_openai_api_key
GOOGLE_API_KEY=your_google_api_key

# LinkedIn credentials
USERNAME=your_linkedin_email
PASSWORD=your_linkedin_password

# GitHub URL
GITHUB_URL=https://github.com/yourusername

# Facebook Messenger (optional)
FB_USERNAME=your_facebook_email
FB_PASSWORD=your_facebook_password

# Instagram (optional)
IG_USERNAME=your_instagram_username
IG_PASSWORD=your_instagram_password

# Telegram Notification (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Email Notification (optional - Gmail App Password)
EMAIL_SENDER=your_gmail@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=receiver@example.com

# Voice Messages (optional - ElevenLabs premium)
ELEVENLABS_API_KEY=your_api_key
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
```

### 2. Configure `agent.py` settings

```python
# Dry Run: True = simulate only, False = send real messages
DRY_RUN = True

# Daily schedule time (24h)
SCHEDULE_HOUR   = 9
SCHEDULE_MINUTE = 0

# Platform toggles
ENABLE_LINKEDIN  = True
ENABLE_WHATSAPP  = True
ENABLE_FACEBOOK  = True
ENABLE_INSTAGRAM = True

# Voice messages
VOICE_ENABLED = True
VOICE_ENGINE  = "gtts"     # "gtts" (free) or "elevenlabs" (premium)

# Contact filters
WHITELIST     = []          # Only wish these contacts (empty = everyone)
BLACKLIST     = []          # Always skip these contacts
COOLDOWN_DAYS = 30          # Days before re-contacting the same person

# Follow-up timing
FOLLOWUP_DAYS = 2           # Days after birthday to send follow-up
```

---

## 📋 Usage

### Option 1 — Run a task immediately

Uncomment the desired task in `agent.py`:

```python
async def main():
    init_db()
    init_followup_table()
    try:
        await run_birthday_detection_task()    # Standard birthday wishes
        # await run_ai_custom_wish_task()      # AI-generated unique wishes
        # await run_linkedin_reply_task()      # Reply to incoming wishes
        # await run_whatsapp_reply_task()      # WhatsApp reply (with voice)
        # await run_facebook_reply_task()      # Facebook Messenger reply
        # await run_instagram_reply_task()     # Instagram DM reply
        # await run_followup_task()            # Send follow-up messages
        # await run_calendar_export()          # Export .ics calendar file
    finally:
        await close_browser()
```

Then run:

```bash
python agent.py
```

### Option 2 — Daily Scheduler (runs all platforms automatically)

In `agent.py`, use:

```python
await run_scheduler()
```

### Option 3 — Streamlit Dashboards

```bash
# Control dashboard (start/stop tasks, toggle dry run, view logs)
streamlit run dashboard.py

# Analytics dashboard (charts, stats, activity table)
streamlit run analytics.py

# Mobile-optimized app (also deployable to Streamlit Cloud)
streamlit run mobile_app.py
```

---

## 📱 Mobile App (Streamlit Cloud)

Deploy the mobile app so you can control the agent from your phone:

1. Push the repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub account and select this repo
4. Set **Main file path** to `mobile_app.py`
5. Go to **App Settings → Secrets** and paste the contents of `.streamlit/secrets.toml.example` with your real credentials
6. Click **Deploy**

You will receive a public URL that works from any phone or browser.

---

## 🔔 Setting Up Notifications

### Telegram

1. Open Telegram → search **@BotFather** → `/newbot`
2. Copy the bot token → add to `.env` as `TELEGRAM_BOT_TOKEN`
3. Send any message to your new bot
4. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `chat_id`
5. Add it to `.env` as `TELEGRAM_CHAT_ID`

### Email (Gmail)

1. Enable 2-Factor Authentication on your Gmail account
2. Go to **Settings → Security → App Passwords**
3. Generate a new App Password
4. Add it to `.env` as `EMAIL_PASSWORD`

---

## 📅 Birthday Calendar Export

Export all LinkedIn contacts' birthdays to a `.ics` file:

```python
await run_calendar_export()
```

This generates `birthdays.ics` in the project folder. To import into Google Calendar:

1. Go to [calendar.google.com](https://calendar.google.com)
2. **Settings → Import & Export → Import**
3. Upload `birthdays.ics`

All events are set to **repeat yearly** with a **1-day reminder**.

---

## 🌍 Supported Languages for Wish Detection

| Language   | Example Phrases                                                              |
| ---------- | ---------------------------------------------------------------------------- |
| English    | "Happy Birthday", "HBD", "Many happy returns", "Another trip around the sun" |
| Bengali    | "শুভ জন্মদিন", "জন্মদিনের শুভেচ্ছা"                                          |
| Arabic     | "عيد ميلاد سعيد", "كل عام وأنت بخير"                                         |
| Hindi      | "जन्मदिन मुबारक", "जन्मदिन की शुभकामनाएं"                                    |
| Spanish    | "Feliz cumpleaños", "Feliz cumple"                                           |
| French     | "Joyeux anniversaire"                                                        |
| German     | "Alles Gute zum Geburtstag"                                                  |
| Turkish    | "İyi ki doğdun"                                                              |
| Indonesian | "Selamat ulang tahun", "Met ultah"                                           |
| Emoji      | 🎂 🎉 🎈 🥳 🎁 combined with a name or greeting                              |

---

## 💝 Relationship Scoring

The agent classifies each contact and adjusts the wish style accordingly:

| Score  | Type            | Wish Style                                                                              |
| ------ | --------------- | --------------------------------------------------------------------------------------- |
| 60–100 | 🟢 Close Friend | Casual, warm, funny — _"Hey Rahul! 🥳 Hope today is as epic as you are!"_               |
| 30–59  | 🔵 Colleague    | Professional but friendly — _"Happy Birthday Priya! 💼 Wishing you continued success!"_ |
| 0–29   | ⚪ Acquaintance | Polite and brief — _"Happy Birthday Ahmed! 🎂 Hope you have a wonderful day!"_          |

Signals used: mutual connections, connection duration, same company/industry, interaction history.

---

## 🗄️ SQLite History

All actions are saved to `agent_history.db`:

```python
import sqlite3
conn = sqlite3.connect("agent_history.db")
rows = conn.execute(
    "SELECT * FROM history ORDER BY created_at DESC LIMIT 20"
).fetchall()
for row in rows:
    print(row)
```

---

## 🔄 Changelog

### v3.0

- ✅ Multi-platform support (WhatsApp, Facebook Messenger, Instagram DM)
- ✅ AI-generated custom wishes (profile-aware, no templates)
- ✅ Contact relationship scoring (Close Friend / Colleague / Acquaintance)
- ✅ Voice message reply via gTTS (free) and ElevenLabs (premium)
- ✅ Follow-up messages (auto-sent 2–3 days after birthday wish)
- ✅ Birthday calendar export (.ics — Google Calendar compatible)
- ✅ Smart timezone timing (9:00 AM in contact's local timezone)
- ✅ Analytics dashboard (charts for activity, platforms, languages, relationships)
- ✅ Mobile app for Streamlit Cloud deployment

### v2.0

- ✅ Session management (cookie persistence)
- ✅ Error handling & retry logic (3 attempts)
- ✅ Personalized replies with sender's first name
- ✅ Birthday detection & auto-wishing
- ✅ Daily scheduler
- ✅ Dry Run mode
- ✅ Streamlit control dashboard
- ✅ Better wish detection (indirect phrases)
- ✅ Multi-language support (9 languages)
- ✅ Telegram & Email notifications
- ✅ SQLite action logging
- ✅ Whitelist / Blacklist
- ✅ Reply cooldown (30 days)

### v1.0

- ✅ GitHub follower check
- ✅ LinkedIn birthday wish reply (basic)

---

## 👥 Contributing

Contributions are welcome!

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'feat: add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 👨‍💻 About the Author

This project is maintained by [Faahim Sadman](https://github.com/SadManFahIm)

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
