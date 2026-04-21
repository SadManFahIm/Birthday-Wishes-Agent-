"""
onboarding.py
─────────────
First-time Setup Wizard for Birthday Wishes Agent.

Run with:
    streamlit run onboarding.py

Steps:
  1. Welcome         — Introduction and overview
  2. LLM Setup       — Choose and configure AI model
  3. LinkedIn        — LinkedIn credentials
  4. Platforms       — WhatsApp, Facebook, Instagram (optional)
  5. Notifications   — Telegram and Email setup
  6. Preferences     — Schedule, dry run, cooldown settings
  7. Advanced        — Voice, A/B testing, RAG memory, etc.
  8. Done!           — Summary and launch instructions

Saves everything to .env file automatically.
"""

import os
import subprocess
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="🎂 Birthday Agent — Setup",
    page_icon="🎂",
    layout="centered",
)

ENV_FILE = Path(".env")

# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def load_env() -> dict:
    """Load existing .env values."""
    if not ENV_FILE.exists():
        return {}
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()
    return values


def save_env(values: dict):
    """Save values to .env file."""
    existing = load_env()
    existing.update({k: v for k, v in values.items() if v})
    lines = []
    for key, val in existing.items():
        lines.append(f"{key}={val}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get(key: str, default: str = "") -> str:
    return load_env().get(key, default)


def step_progress(current: int, total: int = 8):
    """Show step progress bar."""
    st.progress(current / total, text=f"Step {current} of {total}")


# ──────────────────────────────────────────────
# STYLES
# ──────────────────────────────────────────────
st.markdown("""
<style>
  .step-header {
    background: linear-gradient(135deg, #1a237e, #4CAF50);
    padding: 20px 24px; border-radius: 12px;
    margin-bottom: 20px; color: white;
  }
  .step-header h2 { margin: 0; font-size: 1.3rem; }
  .step-header p  { margin: 6px 0 0; opacity: 0.85; font-size: 0.88rem; }
  .tip-box {
    background: #1a3a2a; border-left: 4px solid #4CAF50;
    padding: 12px 16px; border-radius: 8px;
    font-size: 0.85rem; color: #ccc; margin: 12px 0;
  }
  .warning-box {
    background: #2a2a1a; border-left: 4px solid #FFC107;
    padding: 12px 16px; border-radius: 8px;
    font-size: 0.85rem; color: #ccc; margin: 12px 0;
  }
  .success-box {
    background: #1a3a2a; border: 1px solid #4CAF50;
    padding: 16px; border-radius: 12px;
    text-align: center; margin: 12px 0;
  }
  .feature-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 10px; margin: 16px 0;
  }
  .feature-item {
    background: #1E2329; border: 1px solid #2E3440;
    border-radius: 8px; padding: 10px 14px;
    font-size: 0.82rem; color: #ccc;
  }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# SESSION STATE
# ──────────────────────────────────────────────
if "step" not in st.session_state:
    st.session_state.step = 1
if "env_values" not in st.session_state:
    st.session_state.env_values = load_env()


def next_step():
    st.session_state.step += 1
    st.rerun()


def prev_step():
    st.session_state.step -= 1
    st.rerun()


def save_and_next(values: dict):
    save_env(values)
    st.session_state.env_values.update(values)
    next_step()


# ──────────────────────────────────────────────
# STEP 1 — WELCOME
# ──────────────────────────────────────────────
def step_welcome():
    st.markdown("""
    <div class="step-header">
      <h2>👋 Welcome to Birthday Wishes Agent!</h2>
      <p>Let's set up your agent in just a few minutes.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### What this agent does:")
    st.markdown("""
    <div class="feature-grid">
      <div class="feature-item">🎂 Detects birthdays on LinkedIn, WhatsApp, Facebook & Instagram</div>
      <div class="feature-item">💬 Replies to birthday wishes automatically</div>
      <div class="feature-item">🧠 Remembers contact details year over year</div>
      <div class="feature-item">🎭 Matches your reply tone to the sender</div>
      <div class="feature-item">🌍 Supports 17 languages</div>
      <div class="feature-item">📊 Weekly health & digest reports</div>
      <div class="feature-item">🎙️ Voice message replies on WhatsApp</div>
      <div class="feature-item">🤖 AI-generated personalized wishes</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="tip-box">
      💡 <strong>Tip:</strong> Start with <strong>Dry Run Mode ON</strong> —
      the agent will simulate everything without sending real messages.
      Turn it off when you're ready to go live.
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Get Started →", use_container_width=True, type="primary"):
            next_step()


# ──────────────────────────────────────────────
# STEP 2 — LLM SETUP
# ──────────────────────────────────────────────
def step_llm():
    step_progress(2)
    st.markdown("""
    <div class="step-header">
      <h2>🤖 AI Model Setup</h2>
      <p>Choose and configure the AI model that powers the agent.</p>
    </div>
    """, unsafe_allow_html=True)

    llm_choice = st.radio(
        "Which AI model do you want to use?",
        ["Google Gemini (Recommended)", "OpenAI GPT-4o"],
        index=0,
    )

    values = {}

    if llm_choice == "Google Gemini (Recommended)":
        st.markdown("""
        <div class="tip-box">
          🔑 Get your free API key at
          <strong>https://aistudio.google.com/apikey</strong>
        </div>
        """, unsafe_allow_html=True)
        api_key = st.text_input(
            "Google API Key",
            value=get("GOOGLE_API_KEY"),
            type="password",
            placeholder="AIza...",
        )
        values["GOOGLE_API_KEY"] = api_key
    else:
        st.markdown("""
        <div class="tip-box">
          🔑 Get your API key at <strong>https://platform.openai.com/api-keys</strong>
        </div>
        """, unsafe_allow_html=True)
        api_key = st.text_input(
            "OpenAI API Key",
            value=get("OPENAI_API_KEY"),
            type="password",
            placeholder="sk-...",
        )
        values["OPENAI_API_KEY"] = api_key

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step()
    with col2:
        if st.button("Next →", use_container_width=True, type="primary"):
            if not api_key:
                st.error("Please enter an API key.")
            else:
                save_and_next(values)


# ──────────────────────────────────────────────
# STEP 3 — LINKEDIN
# ──────────────────────────────────────────────
def step_linkedin():
    step_progress(3)
    st.markdown("""
    <div class="step-header">
      <h2>💼 LinkedIn Credentials</h2>
      <p>Your LinkedIn login for the agent to access your account.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="warning-box">
      ⚠️ <strong>Security Note:</strong> Your credentials are stored locally in
      <code>.env</code> and never sent anywhere except to LinkedIn directly.
      Use a strong password and enable 2FA on your account.
    </div>
    """, unsafe_allow_html=True)

    username   = st.text_input("LinkedIn Email",
                                value=get("USERNAME"),
                                placeholder="your@email.com")
    password   = st.text_input("LinkedIn Password",
                                value=get("PASSWORD"),
                                type="password",
                                placeholder="••••••••")
    github_url = st.text_input("Your GitHub URL (optional)",
                                value=get("GITHUB_URL"),
                                placeholder="https://github.com/yourusername")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step()
    with col2:
        if st.button("Next →", use_container_width=True, type="primary"):
            if not username or not password:
                st.error("LinkedIn email and password are required.")
            else:
                save_and_next({
                    "USERNAME":   username,
                    "PASSWORD":   password,
                    "GITHUB_URL": github_url,
                })


# ──────────────────────────────────────────────
# STEP 4 — PLATFORMS
# ──────────────────────────────────────────────
def step_platforms():
    step_progress(4)
    st.markdown("""
    <div class="step-header">
      <h2>🌐 Other Platforms (Optional)</h2>
      <p>Add Facebook and Instagram for multi-platform support.</p>
    </div>
    """, unsafe_allow_html=True)

    st.caption("WhatsApp uses QR code scan — no credentials needed here.")
    st.divider()

    st.subheader("📘 Facebook Messenger")
    fb_user = st.text_input("Facebook Email",
                             value=get("FB_USERNAME"),
                             placeholder="your@email.com")
    fb_pass = st.text_input("Facebook Password",
                             value=get("FB_PASSWORD"),
                             type="password",
                             placeholder="••••••••")

    st.divider()
    st.subheader("📸 Instagram")
    ig_user = st.text_input("Instagram Username",
                             value=get("IG_USERNAME"),
                             placeholder="@yourusername")
    ig_pass = st.text_input("Instagram Password",
                             value=get("IG_PASSWORD"),
                             type="password",
                             placeholder="••••••••")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step()
    with col2:
        if st.button("Next →", use_container_width=True, type="primary"):
            save_and_next({
                "FB_USERNAME": fb_user,
                "FB_PASSWORD": fb_pass,
                "IG_USERNAME": ig_user,
                "IG_PASSWORD": ig_pass,
            })


# ──────────────────────────────────────────────
# STEP 5 — NOTIFICATIONS
# ──────────────────────────────────────────────
def step_notifications():
    step_progress(5)
    st.markdown("""
    <div class="step-header">
      <h2>🔔 Notifications (Optional)</h2>
      <p>Get summaries via Telegram or Email after each run.</p>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("📨 Telegram")
    st.markdown("""
    <div class="tip-box">
      1. Open Telegram → search <strong>@BotFather</strong> → /newbot<br>
      2. Copy the token below<br>
      3. Send any message to your bot<br>
      4. Visit <code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code>
         to find your Chat ID
    </div>
    """, unsafe_allow_html=True)

    tg_token   = st.text_input("Telegram Bot Token",
                                value=get("TELEGRAM_BOT_TOKEN"),
                                placeholder="1234567890:ABC...")
    tg_chat_id = st.text_input("Telegram Chat ID",
                                value=get("TELEGRAM_CHAT_ID"),
                                placeholder="123456789")

    st.divider()
    st.subheader("📧 Email (Gmail)")
    st.markdown("""
    <div class="tip-box">
      Use a <strong>Gmail App Password</strong>, not your real password.<br>
      Gmail → Settings → Security → 2FA → App Passwords → Generate
    </div>
    """, unsafe_allow_html=True)

    email_sender   = st.text_input("Gmail Address",
                                    value=get("EMAIL_SENDER"),
                                    placeholder="your@gmail.com")
    email_password = st.text_input("App Password",
                                    value=get("EMAIL_PASSWORD"),
                                    type="password",
                                    placeholder="xxxx xxxx xxxx xxxx")
    email_receiver = st.text_input("Send Reports To",
                                    value=get("EMAIL_RECEIVER"),
                                    placeholder="receiver@email.com")
    digest_recipients = st.text_input(
        "Weekly Digest Recipients (comma-separated)",
        value=get("DIGEST_RECIPIENTS", get("EMAIL_RECEIVER")),
        placeholder="you@gmail.com, partner@gmail.com",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step()
    with col2:
        if st.button("Next →", use_container_width=True, type="primary"):
            save_and_next({
                "TELEGRAM_BOT_TOKEN":  tg_token,
                "TELEGRAM_CHAT_ID":    tg_chat_id,
                "EMAIL_SENDER":        email_sender,
                "EMAIL_PASSWORD":      email_password,
                "EMAIL_RECEIVER":      email_receiver,
                "DIGEST_RECIPIENTS":   digest_recipients,
                "REMINDER_RECIPIENTS": digest_recipients,
                "REPORT_RECIPIENTS":   digest_recipients,
            })


# ──────────────────────────────────────────────
# STEP 6 — PREFERENCES
# ──────────────────────────────────────────────
def step_preferences():
    step_progress(6)
    st.markdown("""
    <div class="step-header">
      <h2>⚙️ Preferences</h2>
      <p>Configure schedule, dry run, and cooldown settings.</p>
    </div>
    """, unsafe_allow_html=True)

    dry_run = st.toggle(
        "🧪 Start in Dry Run Mode (Recommended)",
        value=True,
        help="Simulate everything without sending real messages.",
    )
    if dry_run:
        st.success("✅ Dry Run ON — no real messages will be sent.")
    else:
        st.warning("⚡ Live Mode — real messages WILL be sent!")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        schedule_hour = st.number_input(
            "⏰ Daily Schedule Hour (24h)",
            min_value=0, max_value=23,
            value=int(get("SCHEDULE_HOUR", "9")),
        )
    with col2:
        cooldown_days = st.number_input(
            "❄️ Reply Cooldown (days)",
            min_value=1, max_value=365,
            value=int(get("COOLDOWN_DAYS", "30")),
        )

    followup_days = st.slider(
        "🔔 Follow-up Message (days after birthday)",
        min_value=1, max_value=7,
        value=int(get("FOLLOWUP_DAYS", "2")),
    )

    st.divider()
    st.subheader("🌐 Enable Platforms")
    col1, col2 = st.columns(2)
    with col1:
        enable_linkedin  = st.checkbox("💼 LinkedIn",  value=True)
        enable_whatsapp  = st.checkbox("📱 WhatsApp",  value=True)
    with col2:
        enable_facebook  = st.checkbox("📘 Facebook",  value=bool(get("FB_USERNAME")))
        enable_instagram = st.checkbox("📸 Instagram", value=bool(get("IG_USERNAME")))

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step()
    with col2:
        if st.button("Next →", use_container_width=True, type="primary"):
            save_and_next({
                "DRY_RUN":          str(dry_run).upper(),
                "SCHEDULE_HOUR":    str(schedule_hour),
                "COOLDOWN_DAYS":    str(cooldown_days),
                "FOLLOWUP_DAYS":    str(followup_days),
                "ENABLE_LINKEDIN":  str(enable_linkedin).upper(),
                "ENABLE_WHATSAPP":  str(enable_whatsapp).upper(),
                "ENABLE_FACEBOOK":  str(enable_facebook).upper(),
                "ENABLE_INSTAGRAM": str(enable_instagram).upper(),
            })


# ──────────────────────────────────────────────
# STEP 7 — ADVANCED
# ──────────────────────────────────────────────
def step_advanced():
    step_progress(7)
    st.markdown("""
    <div class="step-header">
      <h2>🔬 Advanced Features</h2>
      <p>Configure voice messages, A/B testing, and more.</p>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("🎙️ Voice Messages (WhatsApp)")
    col1, col2 = st.columns(2)
    with col1:
        voice_enabled = st.checkbox("Enable Voice Replies", value=False)
    with col2:
        voice_engine = st.selectbox(
            "Engine",
            ["gtts (Free)", "elevenlabs (Premium)"],
            index=0,
        )

    if "elevenlabs" in voice_engine:
        elevenlabs_key = st.text_input(
            "ElevenLabs API Key",
            value=get("ELEVENLABS_API_KEY"),
            type="password",
            placeholder="Get from elevenlabs.io",
        )
    else:
        elevenlabs_key = get("ELEVENLABS_API_KEY", "")

    st.divider()
    st.subheader("🧠 Memory & AI")
    col1, col2 = st.columns(2)
    with col1:
        rag_memory   = st.checkbox("RAG Memory (ChromaDB)",
                                    value=False,
                                    help="pip install chromadb required")
        ab_testing   = st.checkbox("A/B Wish Testing",      value=True)
    with col2:
        tone_match   = st.checkbox("Tone Matching",          value=True)
        multilang    = st.checkbox("Multi-language Reply",   value=True)

    st.divider()
    st.subheader("📊 Reports & Campaigns")
    col1, col2 = st.columns(2)
    with col1:
        health_report = st.checkbox("Weekly Health Report", value=True)
        email_digest  = st.checkbox("Weekly Email Digest",  value=True)
    with col2:
        dm_campaign    = st.checkbox("DM Campaign",          value=False)
        occasion_detect = st.checkbox("Occasion Detection",  value=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back", use_container_width=True):
            prev_step()
    with col2:
        if st.button("Finish Setup →", use_container_width=True, type="primary"):
            save_and_next({
                "VOICE_ENABLED":            str(voice_enabled).upper(),
                "VOICE_ENGINE":             voice_engine.split(" ")[0].lower(),
                "ELEVENLABS_API_KEY":       elevenlabs_key,
                "RAG_MEMORY_ENABLED":       str(rag_memory).upper(),
                "AB_TESTING_ENABLED":       str(ab_testing).upper(),
                "TONE_MATCHING_ENABLED":    str(tone_match).upper(),
                "MULTILANG_REPLY_ENABLED":  str(multilang).upper(),
                "HEALTH_REPORT_ENABLED":    str(health_report).upper(),
                "EMAIL_DIGEST_ENABLED":     str(email_digest).upper(),
                "DM_CAMPAIGN_ENABLED":      str(dm_campaign).upper(),
                "OCCASION_DETECTION_ENABLED": str(occasion_detect).upper(),
            })


# ──────────────────────────────────────────────
# STEP 8 — DONE!
# ──────────────────────────────────────────────
def step_done():
    step_progress(8)
    st.balloons()

    st.markdown("""
    <div class="success-box">
      <div style="font-size:2.5rem;">🎉</div>
      <h2 style="color:#4CAF50;margin:8px 0;">Setup Complete!</h2>
      <p style="color:#aaa;">Your .env file has been saved successfully.</p>
    </div>
    """, unsafe_allow_html=True)

    env  = load_env()
    cols = st.columns(2)

    checks = [
        ("LLM API Key",      bool(env.get("GOOGLE_API_KEY") or env.get("OPENAI_API_KEY"))),
        ("LinkedIn",         bool(env.get("USERNAME") and env.get("PASSWORD"))),
        ("Facebook",         bool(env.get("FB_USERNAME"))),
        ("Instagram",        bool(env.get("IG_USERNAME"))),
        ("Telegram",         bool(env.get("TELEGRAM_BOT_TOKEN"))),
        ("Email",            bool(env.get("EMAIL_SENDER"))),
        ("Voice Messages",   env.get("VOICE_ENABLED", "FALSE") == "TRUE"),
        ("RAG Memory",       env.get("RAG_MEMORY_ENABLED", "FALSE") == "TRUE"),
    ]

    with cols[0]:
        st.subheader("✅ Configuration Summary")
        for label, ok in checks:
            icon = "✅" if ok else "⬜"
            st.write(f"{icon} {label}")

    with cols[1]:
        st.subheader("🚀 How to Run")
        st.code("python agent.py", language="bash")
        st.caption("Runs the agent with the daily scheduler.")

        st.subheader("📊 Dashboards")
        st.code("""# Control dashboard
streamlit run dashboard.py

# Analytics
streamlit run analytics.py

# Contact profile cards
streamlit run profile_cards.py

# Wish preview
streamlit run wish_preview.py

# A/B testing
streamlit run ab_dashboard.py

# Real-time dashboard
uvicorn realtime_dashboard:app --port 8000

# Full web app
uvicorn webapp.main:app --port 8000""", language="bash")

    st.divider()

    dry_run_val = env.get("DRY_RUN", "TRUE")
    if dry_run_val == "TRUE":
        st.info(
            "🧪 **Dry Run Mode is ON** — the agent will simulate everything "
            "without sending real messages. Change `DRY_RUN = True` to "
            "`DRY_RUN = False` in `agent.py` when ready to go live."
        )
    else:
        st.warning(
            "⚡ **Live Mode is ON** — the agent will send real messages. "
            "Make sure everything is configured correctly!"
        )

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Edit Settings", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with col2:
        if st.button("🔁 Run Setup Again", use_container_width=True):
            st.session_state.step = 1
            st.rerun()


# ──────────────────────────────────────────────
# ROUTER
# ──────────────────────────────────────────────
step = st.session_state.step

if   step == 1: step_welcome()
elif step == 2: step_llm()
elif step == 3: step_linkedin()
elif step == 4: step_platforms()
elif step == 5: step_notifications()
elif step == 6: step_preferences()
elif step == 7: step_advanced()
elif step == 8: step_done()
else:
    st.session_state.step = 1
    st.rerun()