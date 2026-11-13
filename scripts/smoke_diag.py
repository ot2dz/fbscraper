import os

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbdiag")
os.environ["ADMIN_PASSWORD"] = "test123"

from fastapi.testclient import TestClient

from app.main import app

with TestClient(app) as client:
    client.post("/login", data={"password": "test123"})
    print("diagnostics:", client.get("/api/bot/diagnostics").json())
    page = client.get("/settings")
    print("settings page:", page.status_code, "فحص اتصال البوت" in page.text, "diagBtn" in page.text)
    print("dashboard:", client.get("/").status_code)
