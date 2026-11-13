import os

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbscraper_settings_test")
os.environ["ADMIN_PASSWORD"] = "test123"

from fastapi.testclient import TestClient

from app import db
from app.main import app

with TestClient(app) as client:
    client.post("/login", data={"password": "test123"})
    response = client.post(
        "/settings",
        data={
            "telegram_token": "123456:FAKE-TOKEN",
            "telegram_enabled": "0",
            "telegram_allow_all": "0",
            "telegram_allowed_ids": "111,222",
            "default_posts": "12",
            "max_posts": "50",
            "default_days": "9",
            "proxy": "",
            "request_timeout": "25",
        },
        follow_redirects=False,
    )
    print("save settings:", response.status_code, response.headers.get("location"))
    page = client.get("/settings?saved=1")
    print("settings page:", page.status_code, "تم حفظ الإعدادات" in page.text)
    print("stored:", {k: db.get_setting(k) for k in ("telegram_enabled", "telegram_allowed_ids", "default_posts", "max_posts")})
    print("bot status:", client.get("/healthz").json())
    print("dashboard:", client.get("/").status_code)
