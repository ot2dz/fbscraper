import os
import sys
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbscraper_test")
os.environ["ADMIN_PASSWORD"] = "test123"

from fastapi.testclient import TestClient

from app import db
from app.main import app

with TestClient(app) as client:
    print("healthz:", client.get("/healthz").json())
    print("login page:", client.get("/login").status_code)
    print("unauth dashboard:", client.get("/", follow_redirects=False).status_code)

    bad = client.post("/login", data={"password": "nope"})
    print("bad login:", bad.status_code)
    ok = client.post("/login", data={"password": "test123"}, follow_redirects=False)
    print("login:", ok.status_code, "cookie" in ok.headers.get("set-cookie", "").lower())

    page = client.get("/")
    print("dashboard:", page.status_code, "FB Scraper Bot" in page.text)
    print("settings:", client.get("/settings").status_code)

    response = client.post("/api/scrape", data={"target": "https://www.facebook.com/100088686736411", "posts": "3", "days": "30"})
    print("scrape:", response.status_code, response.json())
    job_id = response.json()["job"]["id"]

    deadline = time.time() + 420
    job = None
    while time.time() < deadline:
        job = db.get_job(job_id)
        print("  status:", job["status"], "posts:", job["post_count"])
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(5)

    print("final:", job["status"], job["post_count"], job["likes"], job["error"])
    detail = client.get(f"/jobs/{job_id}")
    print("job page:", detail.status_code, "المنشورات" in detail.text)
    download = client.get(f"/results/{job_id}.json")
    print("result download:", download.status_code, len(download.content))
    print("jobs page:", client.get("/jobs").status_code)

    sys.exit(0 if job["status"] == "done" and job["post_count"] > 0 else 1)
