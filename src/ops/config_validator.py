"""
Configuration Validator — Birthday Wishes Agent v10.0
======================================================
Structured registry of every environment variable, with startup
validation, CLI status table, .env.example generator, and a
Streamlit health dashboard.

Usage:
  python config_validator.py                 # self-test
  python config_validator.py status          # print config table
  python config_validator.py validate        # validate + report errors
  python config_validator.py generate-env    # write .env.example

Integration:
  from config_validator import validate_config, get_config
  errors = validate_config()       # call on startup
  cfg = get_config()               # returns clean dict

Author : Fahim (SadManFahIm)
Branch : feature/config-validation (→ 10.0)
"""

import os
import re
import logging
import sys
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Config entry definition
# ──────────────────────────────────────────────────────────────


@dataclass
class ConfigEntry:
    """One environment variable definition."""
    name: str
    category: str
    var_type: str = "str"           # str, int, bool, url, email, path
    required: bool = False
    secret: bool = False
    default: str = ""
    description: str = ""
    module: str = ""
    validator: Optional[str] = None  # regex pattern or special rule name
    example: str = ""


# ──────────────────────────────────────────────────────────────
# Registry — every env var the project uses
# ──────────────────────────────────────────────────────────────

REGISTRY: list[ConfigEntry] = [
    # ── AI Models ──────────────────────────────────────────────
    ConfigEntry("AI_MODEL", "AI Models", default="gemini",
                description="AI model to use: gemini / gpt-4o",
                module="contact_loader / model_config",
                validator="^(gemini|gpt-4o|claude)$",
                example="gemini"),
    ConfigEntry("GOOGLE_API_KEY", "AI Models", secret=True,
                description="Google Gemini API key",
                module="contact_loader / model_config",
                example="AIza...your_key"),
    ConfigEntry("OPENAI_API_KEY", "AI Models", secret=True,
                description="OpenAI GPT-4o API key",
                module="contact_loader / model_config",
                example="sk-...your_key"),
    ConfigEntry("ANTHROPIC_API_KEY", "AI Models", secret=True,
                description="Anthropic Claude API key",
                module="model_config",
                example="sk-ant-...your_key"),
    ConfigEntry("MODEL_MODE", "AI Models", default="default",
                description="Model selection mode: default/fast/cheap/premium",
                module="model_config",
                validator="^(default|fast|cheap|premium)$",
                example="default"),

    # ── LinkedIn ───────────────────────────────────────────────
    ConfigEntry("USERNAME", "LinkedIn", required=True,
                description="LinkedIn email/username",
                module="agent / contact_loader",
                example="your_email@gmail.com"),
    ConfigEntry("PASSWORD", "LinkedIn", required=True, secret=True,
                description="LinkedIn password",
                module="agent / contact_loader",
                example="your_password"),
    ConfigEntry("GITHUB_URL", "LinkedIn",
                default="https://github.com/SadManFahIm",
                description="GitHub profile URL for follower check",
                module="agent", var_type="url",
                example="https://github.com/yourusername"),

    # ── Auth (v10.0) ──────────────────────────────────────────
    ConfigEntry("BWA_JWT_SECRET", "Auth", secret=True,
                default="bwa-dev-secret-change-in-prod",
                description="JWT signing secret (MUST change in production)",
                module="jwt_auth",
                example="your-random-secret-key-here"),
    ConfigEntry("BWA_ACCESS_TOKEN_MINUTES", "Auth", var_type="int",
                default="30",
                description="Access token lifetime in minutes",
                module="jwt_auth",
                validator="^[1-9][0-9]*$",
                example="30"),
    ConfigEntry("BWA_REFRESH_TOKEN_DAYS", "Auth", var_type="int",
                default="7",
                description="Refresh token lifetime in days",
                module="jwt_auth",
                validator="^[1-9][0-9]*$",
                example="7"),

    # ── Push Notifications (v10.0) ────────────────────────────
    ConfigEntry("BWA_FCM_SERVER_KEY", "Push", secret=True,
                description="Firebase Cloud Messaging server key "
                            "(dry-run if not set)",
                module="push_notifications",
                example="AAAA...your_fcm_key"),

    # ── Morning Briefing (v10.0) ──────────────────────────────
    ConfigEntry("BWA_BRIEFING_HOUR", "Briefing", var_type="int",
                default="7",
                description="UTC hour for daily morning briefing (0-23)",
                module="morning_briefing",
                validator="^([0-9]|1[0-9]|2[0-3])$",
                example="7"),

    # ── Database ──────────────────────────────────────────────
    ConfigEntry("BWA_DB_PATH", "Database", var_type="path",
                default="agent_history.db",
                description="SQLite database file path",
                module="all modules",
                example="agent_history.db"),
    ConfigEntry("DATABASE_URL", "Database", var_type="url",
                description="PostgreSQL URL (leave empty for SQLite dev mode)",
                module="postgres_migration",
                example="postgresql://user:pass@localhost:5432/birthday_agent"),
    ConfigEntry("REDIS_URL", "Database", var_type="url",
                description="Redis URL (falls back to in-memory without config)",
                module="redis_cache",
                example="redis://localhost:6379/0"),

    # ── Platforms ─────────────────────────────────────────────
    ConfigEntry("FB_USERNAME", "Platforms",
                description="Facebook email", module="platforms",
                example="your_fb_email"),
    ConfigEntry("FB_PASSWORD", "Platforms", secret=True,
                description="Facebook password", module="platforms",
                example="your_fb_password"),
    ConfigEntry("IG_USERNAME", "Platforms",
                description="Instagram username", module="platforms",
                example="your_ig_username"),
    ConfigEntry("IG_PASSWORD", "Platforms", secret=True,
                description="Instagram password", module="platforms",
                example="your_ig_password"),
    ConfigEntry("TELEGRAM_BOT_TOKEN", "Platforms", secret=True,
                description="Telegram bot token", module="telegram",
                example="123456:ABC-DEF..."),
    ConfigEntry("TELEGRAM_CHAT_ID", "Platforms",
                description="Telegram chat ID for notifications",
                module="telegram", example="123456789"),
    ConfigEntry("WHATSAPP_PHONE_ID", "Platforms",
                description="WhatsApp Business phone number ID",
                module="whatsapp", example="your_phone_number_id"),
    ConfigEntry("WHATSAPP_ACCESS_TOKEN", "Platforms", secret=True,
                description="WhatsApp Business permanent access token",
                module="whatsapp",
                example="your_permanent_token"),
    ConfigEntry("WHATSAPP_BUSINESS_ID", "Platforms",
                description="WhatsApp Business account ID",
                module="whatsapp", example="your_waba_id"),

    # ── Email ─────────────────────────────────────────────────
    ConfigEntry("EMAIL_SENDER", "Email", var_type="email",
                description="Gmail sender address",
                module="email_outreach / notifications",
                example="your_gmail@gmail.com"),
    ConfigEntry("EMAIL_PASSWORD", "Email", secret=True,
                description="Gmail app password",
                module="email_outreach / notifications",
                example="your_app_password"),
    ConfigEntry("EMAIL_RECEIVER", "Email", var_type="email",
                description="Default email recipient",
                module="notifications", example="receiver@example.com"),
    ConfigEntry("REMINDER_RECIPIENTS", "Email",
                description="Comma-separated reminder recipients",
                module="birthday_reminder",
                example="you@gmail.com,team@company.com"),
    ConfigEntry("DIGEST_RECIPIENTS", "Email",
                description="Weekly digest recipients",
                module="email_digest",
                example="you@gmail.com"),
    ConfigEntry("REPORT_RECIPIENTS", "Email",
                description="Health report recipients",
                module="relationship_health",
                example="you@gmail.com"),

    # ── Integrations ──────────────────────────────────────────
    ConfigEntry("CRM_PROVIDER", "Integrations",
                description="CRM provider: hubspot / salesforce (empty = mock)",
                module="crm_sync",
                validator="^(hubspot|salesforce|)$",
                example="hubspot"),
    ConfigEntry("HUBSPOT_ACCESS_TOKEN", "Integrations", secret=True,
                description="HubSpot private app access token",
                module="crm_sync", example="pat-..."),
    ConfigEntry("SALESFORCE_CLIENT_ID", "Integrations",
                description="Salesforce OAuth client ID",
                module="crm_sync", example="your_client_id"),
    ConfigEntry("SALESFORCE_CLIENT_SECRET", "Integrations", secret=True,
                description="Salesforce OAuth client secret",
                module="crm_sync", example="your_client_secret"),
    ConfigEntry("SALESFORCE_USERNAME", "Integrations",
                description="Salesforce username",
                module="crm_sync", example="user@company.com"),
    ConfigEntry("SALESFORCE_PASSWORD", "Integrations", secret=True,
                description="Salesforce password + security token",
                module="crm_sync", example="password+token"),
    ConfigEntry("SALESFORCE_LOGIN_URL", "Integrations", var_type="url",
                default="https://login.salesforce.com",
                description="Salesforce login endpoint",
                module="crm_sync",
                example="https://login.salesforce.com"),
    ConfigEntry("NOTION_API_KEY", "Integrations", secret=True,
                description="Notion integration token",
                module="notion_sync", example="secret_..."),
    ConfigEntry("NOTION_CONTACTS_DB_ID", "Integrations",
                description="Notion contacts database ID",
                module="notion_sync", example="abc123..."),
    ConfigEntry("NOTION_LOG_DB_ID", "Integrations",
                description="Notion wish log database ID",
                module="notion_sync", example="def456..."),
    ConfigEntry("GOOGLE_SERVICE_ACCOUNT_JSON", "Integrations",
                var_type="path",
                description="Google service account JSON path",
                module="google_calendar_sync",
                example="service-account.json"),
    ConfigEntry("GOOGLE_CALENDAR_ID", "Integrations",
                description="Google Calendar ID",
                module="google_calendar_sync",
                example="primary"),

    # ── Security ──────────────────────────────────────────────
    ConfigEntry("SECRET_KEY", "Security", secret=True,
                default="change-this-to-a-random-secret-key",
                description="Web app session secret key",
                module="web_app", example="random-secret-key"),
    ConfigEntry("ADMIN_USERNAME", "Security", default="admin",
                description="Web app admin username",
                module="web_app", example="admin"),
    ConfigEntry("ADMIN_PASSWORD", "Security", secret=True,
                default="admin123",
                description="Web app admin password",
                module="web_app", example="secure-password"),

    # ── Voice ─────────────────────────────────────────────────
    ConfigEntry("ELEVENLABS_API_KEY", "Voice", secret=True,
                description="ElevenLabs API key for voice cloning",
                module="voice_cloning", example="your_key"),
    ConfigEntry("ELEVENLABS_VOICE_ID", "Voice",
                default="21m00Tcm4TlvDq8ikWAM",
                description="ElevenLabs voice ID",
                module="voice_cloning", example="21m00Tcm..."),
    ConfigEntry("TRANSCRIPTION_ENGINE", "Voice",
                default="whisper",
                description="Voice-to-text engine: whisper / google",
                module="voice_to_text",
                validator="^(whisper|google)$",
                example="whisper"),
    ConfigEntry("GOOGLE_SPEECH_API_KEY", "Voice", secret=True,
                description="Google Speech API key (optional, Whisper is free)",
                module="voice_to_text", example="AIza..."),

    # ── Feature Flags ─────────────────────────────────────────
    ConfigEntry("CONNECTION_TRACKER_ENABLED", "Feature Flags",
                var_type="bool", default="true",
                description="Enable connection strength tracking",
                module="scheduler", example="true"),
]

CATEGORIES = sorted(set(e.category for e in REGISTRY))

# ──────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────

EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
URL_PATTERN = re.compile(
    r"^https?://[^\s]+$")


def _validate_entry(entry: ConfigEntry, value: str) -> Optional[str]:
    """Validate a single entry. Returns error message or None."""
    if entry.required and not value:
        return f"Required variable not set"

    if not value:
        return None  # Optional and empty = OK

    # Type checks
    if entry.var_type == "int":
        try:
            int(value)
        except ValueError:
            return f"Expected integer, got '{value}'"

    elif entry.var_type == "bool":
        if value.lower() not in ("true", "false", "1", "0", "yes", "no"):
            return f"Expected bool (true/false), got '{value}'"

    elif entry.var_type == "email":
        if not EMAIL_PATTERN.match(value):
            return f"Invalid email format: '{value}'"

    elif entry.var_type == "url":
        if not URL_PATTERN.match(value):
            return f"Invalid URL format: '{value}'"

    # Regex validator
    if entry.validator and value:
        if not re.match(entry.validator, value):
            return (f"Value '{value}' does not match "
                    f"pattern {entry.validator}")

    return None


def _get_value(name: str) -> str:
    """Get env var value, checking os.environ and .env file."""
    val = os.environ.get(name, "")
    if val:
        return val

    # Also check dotenv if available
    try:
        from dotenv import dotenv_values
        env = dotenv_values(".env")
        return env.get(name, "")
    except ImportError:
        return ""


def validate_config() -> dict:
    """
    Validate all registered env vars.
    Returns {valid, errors, warnings, config}.
    """
    errors = []
    warnings = []
    config = {}

    for entry in REGISTRY:
        value = _get_value(entry.name)

        if not value and entry.default:
            value = entry.default

        error = _validate_entry(entry, value)
        if error:
            if entry.required:
                errors.append({
                    "var": entry.name,
                    "category": entry.category,
                    "error": error,
                    "module": entry.module,
                })
            else:
                warnings.append({
                    "var": entry.name,
                    "category": entry.category,
                    "warning": error,
                })

        config[entry.name] = value or entry.default

    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "total_vars": len(REGISTRY),
        "total_set": sum(1 for e in REGISTRY if _get_value(e.name)),
        "total_required": sum(1 for e in REGISTRY if e.required),
        "total_secrets": sum(1 for e in REGISTRY if e.secret),
        "config": config,
    }

    if errors:
        for err in errors:
            logger.error("CONFIG ERROR: %s — %s (%s)",
                         err["var"], err["error"], err["module"])
    if warnings:
        for w in warnings:
            logger.warning("CONFIG WARNING: %s — %s",
                           w["var"], w["warning"])

    return result


def get_config() -> dict:
    """Get validated config dict (values resolved with defaults)."""
    result = validate_config()
    return result["config"]


# ──────────────────────────────────────────────────────────────
# CLI status table
# ──────────────────────────────────────────────────────────────


def _redact(value: str, is_secret: bool) -> str:
    """Redact secret values for display."""
    if not value:
        return ""
    if not is_secret:
        return value[:40] + ("..." if len(value) > 40 else "")
    if len(value) <= 8:
        return "****"
    return value[:3] + "****" + value[-3:]


def print_config_status():
    """Print a CLI-friendly config status table."""
    print()
    print("=" * 78)
    print("  Birthday Wishes Agent — Configuration Status")
    print("=" * 78)

    current_cat = ""
    set_count = 0
    total = len(REGISTRY)

    for entry in REGISTRY:
        if entry.category != current_cat:
            current_cat = entry.category
            print(f"\n  ── {current_cat} {'─' * (60 - len(current_cat))}")

        value = _get_value(entry.name)
        if not value:
            value = entry.default

        if value:
            if entry.secret:
                icon = "🔒"
                display = _redact(value, True)
            else:
                icon = "✅"
                display = _redact(value, False)
            set_count += 1
        elif entry.required:
            icon = "❌"
            display = "NOT SET (required!)"
        else:
            icon = "⚠️ "
            display = "(not set)"

        req_marker = "*" if entry.required else " "
        print(f"  {icon} {req_marker}{entry.name:<35} {display}")

    print(f"\n{'─' * 78}")
    print(f"  {set_count}/{total} configured  |  "
          f"* = required  |  🔒 = secret (redacted)")
    print("=" * 78)
    print()


# ──────────────────────────────────────────────────────────────
# .env.example generator
# ──────────────────────────────────────────────────────────────


def generate_env_example(output_path: str = ".env.example") -> str:
    """Auto-generate .env.example from the registry."""
    lines = [
        "# ═══════════════════════════════════════════════════",
        "# Birthday Wishes Agent — Environment Variables",
        "# Generated by config_validator.py",
        "# ═══════════════════════════════════════════════════",
        "",
    ]

    current_cat = ""
    for entry in REGISTRY:
        if entry.category != current_cat:
            current_cat = entry.category
            lines.append("")
            lines.append(
                f"# ── {current_cat} "
                f"{'─' * (50 - len(current_cat))}")

        # Description comment
        req = " (REQUIRED)" if entry.required else ""
        secret_note = " [SECRET]" if entry.secret else ""
        lines.append(f"# {entry.description}{req}{secret_note}")
        if entry.module:
            lines.append(f"# Used by: {entry.module}")

        # Value line
        example_val = entry.example or entry.default or ""
        lines.append(f"{entry.name}={example_val}")
        lines.append("")

    content = "\n".join(lines)

    with open(output_path, "w") as f:
        f.write(content)

    logger.info("Generated %s (%d vars)", output_path, len(REGISTRY))
    return content


# ──────────────────────────────────────────────────────────────
# Health summary
# ──────────────────────────────────────────────────────────────


def get_health_summary() -> dict:
    """Get a health summary grouped by category."""
    categories = {}
    for entry in REGISTRY:
        cat = entry.category
        if cat not in categories:
            categories[cat] = {"total": 0, "set": 0, "required": 0,
                               "required_missing": 0, "secrets": 0}
        categories[cat]["total"] += 1
        value = _get_value(entry.name) or entry.default
        if value:
            categories[cat]["set"] += 1
        if entry.required:
            categories[cat]["required"] += 1
            if not value:
                categories[cat]["required_missing"] += 1
        if entry.secret:
            categories[cat]["secrets"] += 1

    overall = "healthy"
    for cat, info in categories.items():
        if info["required_missing"] > 0:
            overall = "critical"
            break
        if info["set"] < info["total"] * 0.5:
            overall = "warning"

    return {"categories": categories, "overall": overall,
            "total_vars": len(REGISTRY)}


# ──────────────────────────────────────────────────────────────
# Streamlit dashboard
# ──────────────────────────────────────────────────────────────


def render_dashboard():
    """Config health dashboard."""
    try:
        import streamlit as st
    except ImportError:
        return

    st.set_page_config(page_title="Config Validator", page_icon="⚙️",
                       layout="wide", initial_sidebar_state="collapsed")

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    html,body,[class*="css"]{font-family:'Inter',sans-serif;}
    :root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--accent:#f78166;
          --green:#3fb950;--yellow:#d29922;--red:#f85149;--blue:#58a6ff;
          --muted:#8b949e;--text:#e6edf3;}
    .stApp{background:var(--bg);color:var(--text);}
    .cc-header{display:flex;align-items:center;gap:14px;padding:18px 0 10px;
               border-bottom:1px solid var(--border);margin-bottom:24px;}
    .cc-header h1{font-size:1.4rem;font-weight:700;letter-spacing:-0.02em;margin:0;}
    .cc-badge{background:var(--accent);color:#fff;font-size:0.65rem;font-weight:700;
              padding:2px 8px;border-radius:20px;letter-spacing:0.08em;text-transform:uppercase;}
    .cc-version{margin-left:auto;font-size:0.75rem;color:var(--muted);
                font-family:'JetBrains Mono',monospace;}
    .section-title{font-size:0.7rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:var(--muted);margin:22px 0 10px;
                   display:flex;align-items:center;gap:8px;}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border);}
    .c-card{background:var(--surface);border:1px solid var(--border);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
    .mini{background:#0d1117;border:1px solid #30363d;border-radius:8px;
          padding:10px;text-align:center;}
    .mini-val{font-size:1.4rem;font-weight:700;line-height:1;}
    .mini-lbl{font-size:0.58rem;color:#8b949e;text-transform:uppercase;
              letter-spacing:0.07em;margin-top:3px;}
    .var-set{border-left:3px solid var(--green);padding-left:12px;margin:4px 0;
             font-size:0.85rem;}
    .var-secret{border-left:3px solid var(--blue);padding-left:12px;margin:4px 0;
                font-size:0.85rem;}
    .var-missing{border-left:3px solid var(--yellow);padding-left:12px;margin:4px 0;
                 font-size:0.85rem;}
    .var-error{border-left:3px solid var(--red);padding-left:12px;margin:4px 0;
               font-size:0.85rem;}
    .footer{text-align:center;padding:24px 0 12px;font-size:0.7rem;color:var(--muted);}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="cc-header">
      <span style="font-size:1.6rem">⚙️</span>
      <h1>Configuration Validator</h1>
      <span class="cc-badge">v10.0</span>
      <span class="cc-version">Birthday Wishes Agent</span>
    </div>
    """, unsafe_allow_html=True)

    result = validate_config()
    health = get_health_summary()

    # KPIs
    st.markdown('<div class="section-title">Overview</div>',
                unsafe_allow_html=True)
    k1, k2, k3, k4, k5 = st.columns(5)
    for col, val, lbl in [
        (k1, result["total_vars"], "Total Vars"),
        (k2, result["total_set"], "Configured"),
        (k3, result["total_required"], "Required"),
        (k4, len(result["errors"]), "Errors"),
        (k5, len(result["warnings"]), "Warnings"),
    ]:
        col.markdown(
            f'<div class="mini"><div class="mini-val">{val}</div>'
            f'<div class="mini-lbl">{lbl}</div></div>',
            unsafe_allow_html=True)

    tabs = st.tabs(["📋 Status", "🔍 By Category",
                     "📄 Generate .env"])

    # Status tab
    with tabs[0]:
        if result["errors"]:
            st.markdown('<div class="section-title">Errors</div>',
                        unsafe_allow_html=True)
            for err in result["errors"]:
                st.markdown(
                    f'<div class="var-error">❌ <strong>{err["var"]}'
                    f'</strong> — {err["error"]} '
                    f'<span style="color:var(--muted)">'
                    f'({err["module"]})</span></div>',
                    unsafe_allow_html=True)

        if result["warnings"]:
            st.markdown('<div class="section-title">Warnings</div>',
                        unsafe_allow_html=True)
            for w in result["warnings"]:
                st.markdown(
                    f'<div class="var-missing">⚠️ <strong>{w["var"]}'
                    f'</strong> — {w["warning"]}</div>',
                    unsafe_allow_html=True)

        if result["valid"]:
            st.success("All required variables are configured.")

    # By category tab
    with tabs[1]:
        for cat in CATEGORIES:
            entries = [e for e in REGISTRY if e.category == cat]
            st.markdown(
                f'<div class="section-title">{cat}</div>',
                unsafe_allow_html=True)
            for entry in entries:
                value = _get_value(entry.name) or entry.default
                if value and entry.secret:
                    cls = "var-secret"
                    icon = "🔒"
                    display = _redact(value, True)
                elif value:
                    cls = "var-set"
                    icon = "✅"
                    display = _redact(value, False)
                elif entry.required:
                    cls = "var-error"
                    icon = "❌"
                    display = "NOT SET"
                else:
                    cls = "var-missing"
                    icon = "⚠️"
                    display = "(not set)"
                req = " *" if entry.required else ""
                st.markdown(
                    f'<div class="{cls}">{icon} '
                    f'<strong>{entry.name}{req}</strong> '
                    f'<span style="color:var(--muted);font-size:0.75rem">'
                    f'{display}</span> '
                    f'<br><span style="color:var(--muted);font-size:0.7rem">'
                    f'{entry.description}</span></div>',
                    unsafe_allow_html=True)

    # Generate .env tab
    with tabs[2]:
        st.markdown('<div class="c-card">', unsafe_allow_html=True)
        if st.button("📄 Generate .env.example", key="btn_gen"):
            content = generate_env_example()
            st.success("Generated .env.example")
            st.code(content[:2000], language="bash")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="footer">'
        'Birthday Wishes Agent · branch <code style="background:#161b22;'
        'padding:2px 6px;border-radius:4px;font-size:0.68rem">'
        'feature/config-validation</code> · Config Validator v10.0'
        '</div>', unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────


def _self_test():
    """Comprehensive self-test."""
    import tempfile

    print("=" * 60)
    print("Configuration Validator — Self-Test")
    print("=" * 60)

    # 1. Registry
    print(f"\n[1/8] Registry ...")
    assert len(REGISTRY) >= 45
    assert len(CATEGORIES) >= 9
    cats = [e.category for e in REGISTRY]
    assert "AI Models" in cats
    assert "Auth" in cats
    assert "Push" in cats
    print(f"      ✅ {len(REGISTRY)} vars in {len(CATEGORIES)} categories")

    # 2. Required vars
    print("[2/8] Required vars ...")
    required = [e for e in REGISTRY if e.required]
    assert len(required) >= 2  # USERNAME, PASSWORD
    req_names = [e.name for e in required]
    assert "USERNAME" in req_names
    assert "PASSWORD" in req_names
    print(f"      ✅ {len(required)} required vars identified")

    # 3. Secret vars
    print("[3/8] Secret vars ...")
    secrets = [e for e in REGISTRY if e.secret]
    assert len(secrets) >= 10
    sec_names = [e.name for e in secrets]
    assert "BWA_JWT_SECRET" in sec_names
    assert "GOOGLE_API_KEY" in sec_names
    print(f"      ✅ {len(secrets)} secret vars identified")

    # 4. Type validation
    print("[4/8] Type validation ...")
    int_entry = ConfigEntry("TEST_INT", "Test", var_type="int")
    assert _validate_entry(int_entry, "42") is None
    assert _validate_entry(int_entry, "abc") is not None

    email_entry = ConfigEntry("TEST_EMAIL", "Test", var_type="email")
    assert _validate_entry(email_entry, "user@example.com") is None
    assert _validate_entry(email_entry, "not-an-email") is not None

    url_entry = ConfigEntry("TEST_URL", "Test", var_type="url")
    assert _validate_entry(url_entry, "https://example.com") is None
    assert _validate_entry(url_entry, "not-a-url") is not None

    bool_entry = ConfigEntry("TEST_BOOL", "Test", var_type="bool")
    assert _validate_entry(bool_entry, "true") is None
    assert _validate_entry(bool_entry, "maybe") is not None
    print("      ✅ int, email, url, bool validation OK")

    # 5. Pattern validation
    print("[5/8] Pattern validation ...")
    ai_entry = next(e for e in REGISTRY if e.name == "AI_MODEL")
    assert _validate_entry(ai_entry, "gemini") is None
    assert _validate_entry(ai_entry, "invalid_model") is not None

    hour_entry = next(e for e in REGISTRY if e.name == "BWA_BRIEFING_HOUR")
    assert _validate_entry(hour_entry, "7") is None
    assert _validate_entry(hour_entry, "25") is not None
    assert _validate_entry(hour_entry, "0") is None
    assert _validate_entry(hour_entry, "23") is None
    print("      ✅ Regex pattern validation OK")

    # 6. Redaction
    print("[6/8] Secret redaction ...")
    assert _redact("my-secret-key-12345", True) == "my-****345"
    assert _redact("short", True) == "****"
    assert _redact("normal-value", False) == "normal-value"
    assert _redact("", True) == ""
    print("      ✅ Redaction OK (secrets hidden, values shown)")

    # 7. .env.example generation
    print("[7/8] .env.example generation ...")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env",
                                     delete=False) as f:
        tmp_path = f.name
    content = generate_env_example(tmp_path)
    assert "USERNAME" in content
    assert "BWA_JWT_SECRET" in content
    assert "REQUIRED" in content
    assert "[SECRET]" in content
    assert len(content.splitlines()) > 100
    os.unlink(tmp_path)
    print(f"      ✅ Generated {len(content.splitlines())} lines")

    # 8. Health summary
    print("[8/8] Health summary ...")
    health = get_health_summary()
    assert len(health["categories"]) >= 9
    assert health["total_vars"] == len(REGISTRY)
    assert health["overall"] in ("healthy", "warning", "critical")
    print(f"      ✅ Overall: {health['overall']}, "
          f"{len(health['categories'])} categories")

    # Print status table
    print_config_status()

    print("=" * 60)
    print("✅ ALL CONFIG VALIDATOR SELF-TESTS PASSED")
    print("=" * 60)


# ──────────────────────────────────────────────────────────────
# CLI + entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            print_config_status()
        elif cmd == "validate":
            result = validate_config()
            if result["valid"]:
                print("✅ Configuration valid")
            else:
                print(f"❌ {len(result['errors'])} error(s):")
                for err in result["errors"]:
                    print(f"   {err['var']}: {err['error']}")
            if result["warnings"]:
                print(f"⚠️  {len(result['warnings'])} warning(s):")
                for w in result["warnings"]:
                    print(f"   {w['var']}: {w['warning']}")
        elif cmd == "generate-env":
            path = sys.argv[2] if len(sys.argv) > 2 else ".env.example"
            generate_env_example(path)
            print(f"Generated {path}")
        else:
            print(f"Unknown: {cmd}")
            print("Usage: python config_validator.py "
                  "[status|validate|generate-env [path]]")
    else:
        print("=== Config Validator -- self test ===\n")
        _self_test()
else:
    render_dashboard()
