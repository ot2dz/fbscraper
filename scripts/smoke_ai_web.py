import os

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbai_web_test")
os.environ["ADMIN_PASSWORD"] = "test123"

from fastapi.testclient import TestClient

from app import db
from app.main import app

with TestClient(app) as client:
    client.post("/login", data={"password": "test123"})
    response = client.post(
        "/settings",
        data={
            "telegram_token": "",
            "telegram_enabled": "0",
            "telegram_allow_all": "1",
            "telegram_allowed_ids": "",
            "default_posts": "30",
            "max_posts": "200",
            "default_days": "30",
            "proxy": "",
            "request_timeout": "30",
            "ai_enabled": "1",
            "ai_base_url": "https://opencode.ai/inference/openai/v1",
            "ai_api_key": "sk-fake",
            "ai_model": "gemini-3.8-flash",
            "ai_max_comments": "120",
            "ai_prompt_extra": "ركّز على السعر",
        },
        follow_redirects=False,
    )
    print("save:", response.status_code)
    print("stored:", {k: db.get_setting(k) for k in ("ai_enabled", "ai_model", "ai_max_comments", "ai_prompt_extra")})
    print("settings page:", client.get("/settings").status_code, "تحليل الذكاء" in client.get("/settings").text)
    test = client.post("/api/ai/test")
    print("ai test:", test.status_code, str(test.json().get("text"))[:120])
