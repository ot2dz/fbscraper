import json
import os

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbai_job_test")
os.environ["ADMIN_PASSWORD"] = "test123"

from fastapi.testclient import TestClient

from app import db
from app.config import RESULTS_DIR, ensure_dirs
from app.main import app

with TestClient(app) as client:
    ensure_dirs()
    client.post("/login", data={"password": "test123"})
    job = db.create_job("https://www.facebook.com/x/posts/1", 2, 0, kind="comments")
    path = os.path.join(RESULTS_DIR, f"{job['id']}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"post_url": "https://www.facebook.com/x/posts/1", "count": 1, "comments": [{"author": "A", "text": "غالي", "likes": 2}]}, handle, ensure_ascii=False)
    analysis = {
        "summary": "ملخص تجريبي",
        "sentiment": "سلبي",
        "price_mentioned": True,
        "price_details": ["2500 دج"],
        "criticisms": ["غالي"],
        "questions": [],
        "praise": [],
        "recommendations": ["خفّض السعر"],
        "_meta": {"model": "gemini-3.8-flash", "analyzed": 1, "total": 1},
    }
    db.update_job(job["id"], status="done", result_path=path, post_count=1, likes=2, analysis=json.dumps(analysis, ensure_ascii=False))
    page = client.get(f"/jobs/{job['id']}")
    text = page.text
    print("page:", page.status_code)
    print("has analysis:", "ملخص تجريبي" in text)
    print("has raw comments table:", "صاحب التعليق" in text)
    print("has analyze button:", "حلّل الآن" in text)
