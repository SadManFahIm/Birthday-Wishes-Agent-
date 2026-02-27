# LinkedIn Birthday Wishes Agent 🎂🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Version](https://img.shields.io/badge/version-2.0-green)
![LangChain](https://img.shields.io/badge/LangChain-powered-blueviolet)
![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-orange)

An intelligent browser automation agent built with Python, LangChain, and `browser_use` that automatically manages your LinkedIn birthday wishes — both sending wishes to your contacts and replying to wishes you receive.

---

## 📝 Introduction

This project demonstrates how to build production-ready browser automation agents using Python, LangChain, and the `browser_use` library.

**v2.0** is a major upgrade over the original with 13+ new features including session management, multi-language support, Telegram/Email notifications, a Streamlit dashboard, and more.

---

## ✨ Features (v2.0)

### 🤖 Core Agent

| Feature                   | Description                                                                          |
| ------------------------- | ------------------------------------------------------------------------------------ |
| **GitHub Follower Check** | Automatically visits a GitHub profile and reports the follower count                 |
| **Birthday Detection**    | Detects contacts with birthdays TODAY on LinkedIn and sends them personalized wishes |
| **Reply to Wishes**       | Scans unread messages and replies to birthday wishes sent to you                     |

### 🔐 Security & Reliability

| Feature                    | Description                                                                             |
| -------------------------- | --------------------------------------------------------------------------------------- |
| **Session Management**     | Saves browser cookies to disk — no repeated logins. Session auto-expires after 12 hours |
| **Error Handling & Retry** | Every task retries up to 3 times on failure with 5-second delay between attempts        |
| **Dry Run Mode**           | Set `DRY_RUN = True` to simulate the agent without sending any real messages            |

### 🧠 AI Upgrades

| Feature                    | Description                                                                                               |
| -------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Personalized Replies**   | Replies use the sender's actual first name (e.g. _"Thanks Rahul! Really means a lot 😊"_)                 |
| **Better Wish Detection**  | Detects direct, indirect, and creative birthday phrases beyond simple "Happy Birthday"                    |
| **Multi-Language Support** | Detects birthday wishes in Bengali, Arabic, Hindi, Spanish, French, German, Turkish, Indonesian, and more |

### ⚙️ Automation

| Feature                   | Description                                                            |
| ------------------------- | ---------------------------------------------------------------------- |
| **Scheduler**             | Runs automatically every day at a configurable time (default: 9:00 AM) |
| **Whitelist / Blacklist** | Control exactly which contacts to wish or skip                         |
| **Reply Cooldown**        | Prevents replying to the same contact more than once every 30 days     |

### 📊 Monitoring & Notifications

| Feature                   | Description                                                                           |
| ------------------------- | ------------------------------------------------------------------------------------- |
| **SQLite Logging**        | Every action is saved to `agent_history.db` for full history tracking                 |
| **Telegram Notification** | Sends a summary to your Telegram after every run                                      |
| **Email Notification**    | Sends a summary email via Gmail after every run                                       |
| **Streamlit Dashboard**   | Web UI to control the agent, toggle Dry Run, change schedule time, and view live logs |

---

## 🗂️ Project Structure

```
Birthday-Wishes-Agent/
│
├── agent.py              # Main agent logic
├── notifications.py      # Telegram & Email notification handlers
├── dashboard.py          # Streamlit web dashboard
│
├── .env                  # Your credentials (never commit this!)
├── .env.example          # Template for environment variables
├── requirements.txt      # Python dependencies
│
├── agent.log             # Live log file (auto-generated)
├── agent_history.db      # SQLite history database (auto-generated)
├── linkedin_session.json # Session timestamp (auto-generated)
└── browser_profile/      # Browser cookies/session (auto-generated)
```

---

## 🔧 Prerequisites

- Python 3.10 or higher
- pip (Python package installer)
- Google Chrome browser
- LinkedIn account
- API key for OpenAI or Google Gemini
- _(Optional)_ Telegram bot token for notifications
- _(Optional)_ Gmail app password for email notifications

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

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Email (optional - Gmail App Password)
EMAIL_SENDER=your_gmail@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECEIVER=receiver@example.com
```

### 2. Configure `agent.py` settings

At the top of `agent.py`, you can customize:

```python
# Dry Run: True = simulate only, False = send real messages
DRY_RUN = True

# Daily schedule time
SCHEDULE_HOUR   = 9   # 9 AM
SCHEDULE_MINUTE = 0

# Whitelist: only wish these contacts (leave empty for everyone)
WHITELIST = []  # e.g. ["Rahul Ahmed", "Priya Sharma"]

# Blacklist: always skip these contacts
BLACKLIST = []  # e.g. ["Spam Account"]

# Cooldown: minimum days before re-contacting the same person
COOLDOWN_DAYS = 30
```

---

## 📋 Usage

### Option 1 — Run from terminal

Uncomment the desired task in `agent.py`:

```python
async def main():
    init_db()
    try:
        # Run once immediately:
        await run_birthday_detection_task()   # Wish contacts
        # await run_linkedin_reply_task()     # Reply to wishes
        # await run_github_task()             # Check GitHub followers

        # OR run on daily schedule:
        # await run_scheduler()
    finally:
        await close_browser()
```

Then run:

```bash
python agent.py
```

### Option 2 — Streamlit Dashboard

```bash
streamlit run dashboard.py
```

Opens a web UI where you can:

- ▶️ Start / ⏹️ Stop the agent with a button
- 🧪 Toggle Dry Run mode
- ⏰ Change the daily schedule time
- 📋 View live logs from `agent.log`

---

## 🔔 Setting Up Notifications

### Telegram

1. Open Telegram → search **@BotFather** → `/newbot`
2. Copy the bot token → add to `.env` as `TELEGRAM_BOT_TOKEN`
3. Send any message to your new bot
4. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your `chat_id`
5. Add `chat_id` to `.env` as `TELEGRAM_CHAT_ID`

### Email (Gmail)

1. Enable 2-Factor Authentication on your Gmail account
2. Go to **Settings → Security → App Passwords**
3. Generate a new app password
4. Add it to `.env` as `EMAIL_PASSWORD`

---

## 🌍 Supported Languages for Wish Detection

The agent can detect birthday wishes in:

| Language   | Example Phrases                               |
| ---------- | --------------------------------------------- |
| English    | "Happy Birthday", "HBD", "Many happy returns" |
| Bengali    | "শুভ জন্মদিন", "জন্মদিনের শুভেচ্ছা"           |
| Arabic     | "عيد ميلاد سعيد", "كل عام وأنت بخير"          |
| Hindi      | "जन्मदिन मुबारक", "जन्मदिन की शुभकामनाएं"     |
| Spanish    | "Feliz cumpleaños", "Feliz cumple"            |
| French     | "Joyeux anniversaire"                         |
| German     | "Alles Gute zum Geburtstag"                   |
| Turkish    | "İyi ki doğdun"                               |
| Indonesian | "Selamat ulang tahun", "Met ultah"            |
| Emoji      | 🎂 🎉 🎈 🥳 🎁 (combined with greeting)       |

---

## 🗄️ SQLite History

All actions are saved to `agent_history.db`. You can query it:

```python
import sqlite3
conn = sqlite3.connect("agent_history.db")
rows = conn.execute("SELECT * FROM history ORDER BY created_at DESC LIMIT 20").fetchall()
for row in rows:
    print(row)
```

---

## 🔄 Changelog

### v2.0

- ✅ Session management (cookie persistence)
- ✅ Error handling & retry logic (3 attempts)
- ✅ Personalized replies with sender's name
- ✅ Birthday detection & auto-wishing
- ✅ Scheduler (daily auto-run)
- ✅ Dry Run mode
- ✅ Streamlit dashboard
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
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 👨‍💻 About the Author

This project is maintained by [Faahim Sadman](https://github.com/SadManFahIm)

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
