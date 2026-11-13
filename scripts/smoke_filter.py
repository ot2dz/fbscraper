import json
import os

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbscraper_filter_test")
os.environ["ADMIN_PASSWORD"] = "test123"

from fastapi.testclient import TestClient

from app import db
from app.config import RESULTS_DIR, ensure_dirs
from app.main import app


def make_post(post_id, comments, likes, shares, text, day):
    return {
        "post_id": post_id,
        "post_url": f"https://www.facebook.com/{post_id}",
        "username_or_userid": "1",
        "owing_profile": {"name": "test"},
        "published_date": f"2026-11-{day} 10:00:00",
        "published_date2": f"2026-11-{day}",
        "time": 1000 + day,
        "reaction_count.count": likes,
        "comment_rendering_instance.comments.total_count": comments,
        "share_count.count": shares,
        "sub_reactions": {},
        "context": text,
        "video_view_count": None,
    }


with TestClient(app) as client:
    ensure_dirs()
    client.post("/login", data={"password": "test123"})
    job = db.create_job("100088686736411", 4, 30)
    path = os.path.join(RESULTS_DIR, f"{job['id']}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "data": [
                    make_post("1", 5, 100, 1, "منشور عادي", 10),
                    make_post("2", 153, 1877, 9, "أعلى تعليقات", 12),
                    make_post("3", 0, 300, 2, "بدون تعليقات", 11),
                    make_post("4", 24, 50, 0, None, 13),
                ]
            },
            handle,
            ensure_ascii=False,
        )
    db.update_job(job["id"], status="done", result_path=path, post_count=4)

    page = client.get(f"/jobs/{job['id']}")
    print("default page:", page.status_code, "ترتيب وفلترة" in page.text)
    order_default = page.text.find("أعلى تعليقات") < page.text.find("منشور عادي") < page.text.find("بدون تعليقات")
    print("default sorted by comments:", order_default)

    page = client.get(f"/jobs/{job['id']}?sort=likes&order=desc")
    print("likes desc:", page.text.find("أعلى تعليقات") < page.text.find("بدون تعليقات"))

    page = client.get(f"/jobs/{job['id']}?sort=comments&min_comments=50")
    print("min_comments filter:", "أعلى تعليقات" in page.text, "منشور عادي" not in page.text)

    page = client.get(f"/jobs/{job['id']}?q=عادي")
    print("text search:", "منشور عادي" in page.text, "بدون تعليقات" not in page.text)

    page = client.get(f"/jobs/{job['id']}?sort=date&order=asc")
    print("date asc:", page.text.find("منشور عادي") < page.text.find("بدون تعليقات") < page.text.find("أعلى تعليقات"))
