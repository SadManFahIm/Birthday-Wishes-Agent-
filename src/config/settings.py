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
