# -*- coding: utf-8 -*-
"""Application configuration (env + SQLite-backed runtime settings)."""
import os
import secrets

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
DB_PATH = os.path.join(DATA_DIR, "app.db")
RESULTS_DIR = os.path.join(DATA_DIR, "results")
LOGS_DIR = os.path.join(DATA_DIR, "logs")

PORT = int(os.environ.get("PORT", "8000"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
CHROME_BIN = os.environ.get("CHROME_BIN", "")
CHROMEDRIVER_PATH = os.environ.get("CHROMEDRIVER_PATH", "") or None
SCRAPE_TIME_LIMIT = int(os.environ.get("SCRAPE_TIME_LIMIT", "1800"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")

DEFAULTS = {
    "telegram_token": "",
    "telegram_enabled": "1",
    "telegram_allow_all": "1",
    "telegram_allowed_ids": "",
    "default_posts": "30",
    "max_posts": "200",
    "default_days": "30",
    "proxy": "",
    "request_timeout": "30",
    "ai_enabled": "0",
    "ai_base_url": "https://opencode.ai/inference/openai/v1",
    "ai_api_key": "",
    "ai_model": "gemini-3.8-flash",
    "ai_max_comments": "150",
    "ai_prompt_extra": "",
    "welcome_message": "أرسل /scrape <page_id أو رابط الصفحة> [عدد المنشورات] [عدد الأيام]",
}


def ensure_dirs():
    for path in (DATA_DIR, RESULTS_DIR, LOGS_DIR):
        os.makedirs(path, exist_ok=True)


def secret_key() -> str:
    """Stable signing key: env first, otherwise generated once and persisted."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    ensure_dirs()
    from app.db import get_setting, set_setting

    key = get_setting("_secret_key")
    if not key:
        key = secrets.token_urlsafe(48)
        set_setting("_secret_key", key)
    return key
