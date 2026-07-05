# restructure.ps1
# BirthdayAgent project restructure script
# Run from: C:\Users\Hp\Desktop\Others\ETC\P\BirthdayAgent
# Command:  .\restructure.ps1

$root = Get-Location

# ── Create all folders ────────────────────────────────────────────────────────
$folders = @(
    "ai", "automation", "platforms", "contacts",
    "security", "detection", "notifications",
    "multi_account", "dashboards", "config",
    "tests\unit", "tests\integration"
)
foreach ($f in $folders) {
    New-Item -ItemType Directory -Force -Path "$root\$f" | Out-Null
}
Write-Host "Folders created." -ForegroundColor Green

# ── Create __init__.py in each package folder ─────────────────────────────────
$packages = @(
    "ai", "automation", "platforms", "contacts",
    "security", "detection", "notifications",
    "multi_account", "dashboards", "config", "tests"
)
foreach ($p in $packages) {
    $init = "$root\$p\__init__.py"
    if (-not (Test-Path $init)) { New-Item -ItemType File -Path $init | Out-Null }
}
Write-Host "__init__.py files created." -ForegroundColor Green

# ── Helper: move file if it exists ───────────────────────────────────────────
function Move-If-Exists($file, $dest) {
    $src = "$root\$file"
    if (Test-Path $src) {
        Move-Item -Path $src -Destination "$root\$dest\$file" -Force
        Write-Host "  Moved $file -> $dest/" -ForegroundColor Cyan
    } else {
        Write-Host "  Skipped (not found): $file" -ForegroundColor DarkGray
    }
}

# ════════════════════════════════════════════
# ai/
# ════════════════════════════════════════════
Write-Host "`nMoving ai/ files..." -ForegroundColor Yellow
$aiFiles = @(
    "wish_scorer.py",
    "wish_personalization_score.py",
    "wish_style_memory.py",
    "wish_variant_generator.py",
    "memory.py",
    "rag_memory.py",
    "context_aware_opener.py",
    "sentiment.py",
    "tone_matching.py",
    "emotional_intelligence.py",
    "personality_profiling.py",
    "multilang_reply.py",
    "occasion_detection.py",
    "predictive_birthday.py",
    "ab_testing.py",
    "model_ensemble.py",
    "smart_emoji_calibration.py"
)
foreach ($f in $aiFiles) { Move-If-Exists $f "ai" }

# ════════════════════════════════════════════
# automation/
# ════════════════════════════════════════════
Write-Host "`nMoving automation/ files..." -ForegroundColor Yellow
$automationFiles = @(
    "auto_reply_followup.py",
    "auto_learning_reply.py",
    "smart_followup.py",
    "auto_timezone_scheduler.py",
    "smart_send_time_optimizer.py",
    "birthday_reminder.py",
    "birthday_eve_reminder.py",
    "birthday_miss_tracker.py",
    "auto_connect.py",
    "personalized_connect.py",
    "post_engagement.py",
    "group_birthday.py",
    "dm_campaign.py",
    "workflow_builder.py",
    "auto_pause_on_anomaly.py"
)
foreach ($f in $automationFiles) { Move-If-Exists $f "automation" }

# ════════════════════════════════════════════
# platforms/
# ════════════════════════════════════════════
Write-Host "`nMoving platforms/ files..." -ForegroundColor Yellow
$platformFiles = @(
    "twitter_birthday.py",
    "slack_birthday_bot.py",
    "instagram_birthday_detector.py",
    "instagram_birthdays.py"
)
foreach ($f in $platformFiles) { Move-If-Exists $f "platforms" }
# Note: linkedin.py, whatsapp.py, facebook.py, instagram.py already in platforms/

# ════════════════════════════════════════════
# contacts/
# ════════════════════════════════════════════
Write-Host "`nMoving contacts/ files..." -ForegroundColor Yellow
$contactFiles = @(
    "contact_notes.py",
    "contact_categorizer.py",
    "contact_importance_scorer.py",
    "contact_timeline.py",
    "connection_tracker.py",
    "relationship_health.py",
    "decay_alert.py",
    "network_growth_tracker.py",
    "smart_reengagement.py",
    "reply_sentiment_trend.py"
)
foreach ($f in $contactFiles) { Move-If-Exists $f "contacts" }

# ════════════════════════════════════════════
# security/
# ════════════════════════════════════════════
Write-Host "`nMoving security/ files..." -ForegroundColor Yellow
$securityFiles = @(
    "two_factor_auth.py",
    "proxy_rotation.py",
    "vpn_switch.py",
    "browser_fingerprint.py",
    "session_health_monitor.py"
)
foreach ($f in $securityFiles) { Move-If-Exists $f "security" }

# ════════════════════════════════════════════
# detection/
# ════════════════════════════════════════════
Write-Host "`nMoving detection/ files..." -ForegroundColor Yellow
$detectionFiles = @(
    "job_change_detector.py",
    "work_anniversary_detector.py",
    "linkedin_post_commenter.py",
    "human_delay.py"
)
foreach ($f in $detectionFiles) { Move-If-Exists $f "detection" }

# ════════════════════════════════════════════
# notifications/
# ════════════════════════════════════════════
Write-Host "`nMoving notifications/ files..." -ForegroundColor Yellow
$notifFiles = @(
    "notifications.py",
    "email_digest.py",
    "voice.py",
    "voice_to_text.py"
)
foreach ($f in $notifFiles) { Move-If-Exists $f "notifications" }

# ════════════════════════════════════════════
# multi_account/
# ════════════════════════════════════════════
Write-Host "`nMoving multi_account/ files..." -ForegroundColor Yellow
$multiFiles = @(
    "multi_account.py",
    "multi_agent_orchestrator.py",
    "multi_agent_runner.py"
)
foreach ($f in $multiFiles) { Move-If-Exists $f "multi_account" }

# ════════════════════════════════════════════
# dashboards/
# ════════════════════════════════════════════
Write-Host "`nMoving dashboards/ files..." -ForegroundColor Yellow
$dashFiles = @(
    "command_center.py",
    "wish_preview.py",
    "wish_roi_report.py",
    "batch_approve_queue.py",
    "workflow_builder_ui.py",
    "insight_report.py",
    "platform_roi_comparison.py",
    "personalization_score_trend.py",
    "analytics.py",
    "ab_dashboard.py",
    "engagement_heatmap.py",
    "monthly_report.py",
    "profile_cards.py",
    "realtime_dashboard.py",
    "onboarding.py",
    "mobile_app.py",
    "theme_toggle.py",
    "dashboard.py",
    "best_time_connect.py"
)
foreach ($f in $dashFiles) { Move-If-Exists $f "dashboards" }

# ════════════════════════════════════════════
# config/settings.py (create if missing)
# ════════════════════════════════════════════
$settingsPath = "$root\config\settings.py"
if (-not (Test-Path $settingsPath)) {
    @'
"""
config/settings.py
Central settings loader — reads from .env
"""
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # AI model
    AI_MODEL: str = "gemini"
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # LinkedIn
    USERNAME: str = ""
    PASSWORD: str = ""
    GITHUB_URL: str = ""

    # Platforms
    SLACK_BOT_TOKEN: str = ""
    SLACK_BIRTHDAY_CHANNEL: str = "#birthdays"
    TWITTER_BEARER_TOKEN: str = ""

    # Notifications
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    EMAIL_SENDER: str = ""
    EMAIL_PASSWORD: str = ""

    # Agent
    DRY_RUN: bool = True
    COOLDOWN_DAYS: int = 30
    FOLLOWUP_DAYS: int = 3
    SCHEDULE_HOUR: int = 9
    SCHEDULE_MINUTE: int = 0

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
'@ | Set-Content $settingsPath
    Write-Host "  Created config/settings.py" -ForegroundColor Cyan
}

Write-Host "`nDone! Project restructured." -ForegroundColor Green
Write-Host "
NEXT STEPS:
  1. Update imports in agent.py:
       from ai.wish_scorer import ...
       from automation.smart_followup import ...
       from contacts.contact_timeline import ...

  2. Run: pip install pydantic-settings

  3. Test: python agent.py
" -ForegroundColor White
