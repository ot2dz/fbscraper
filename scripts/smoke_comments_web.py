import json
import os
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_web_test")
os.environ["ADMIN_PASSWORD"] = "test123"

from fastapi.testclient import TestClient

from app import db
from app.main import app

with TestClient(app) as client:
    client.post("/login", data={"password": "test123"})
    response = client.post(
        "/api/scrape_comments",
        data={"target": "https://www.facebook.com/1118927064107626", "limit": "20"},
    )
    print("scrape_comments:", response.status_code, response.json().get("job", {}).get("kind"))
    job_id = response.json()["job"]["id"]

    deadline = time.time() + 600
    job = None
    while time.time() < deadline:
        job = db.get_job(job_id)
        print("  status:", job["status"], "count:", job["post_count"])
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(5)

    print("final:", job["status"], job["post_count"], job["likes"], job["error"])
    page = client.get(f"/jobs/{job_id}")
    print("job page:", page.status_code, "التعليقات" in page.text, "صاحب التعليق" in page.text)
    result = client.get(f"/results/{job_id}.json")
    print("json:", result.status_code)
    if result.status_code == 200:
        payload = json.loads(result.content)
        print("comments in json:", payload["count"], "| first:", payload["comments"][0]["author"])
