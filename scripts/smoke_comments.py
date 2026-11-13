import json
import os
import sys

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")
os.environ.setdefault("ADMIN_PASSWORD", "test123")

from app import db
from app.comments_runner import run_comments
from app.config import ensure_dirs

ensure_dirs()
db.init_db()

target = sys.argv[1] if len(sys.argv) > 1 else "1118927064107626"
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20

job = db.create_job(target, limit, 0, kind="comments")
result = run_comments(job)
print("status:", db.get_job(job["id"])["status"])
if result:
    print("count:", result["count"])
    for comment in result["comments"][:5]:
        print("-", comment["author"], "|", comment["likes"], "likes |", comment["text"][:60].replace("\n", " "))
    print("file:", db.get_job(job["id"])["result_path"])
else:
    print("error:", db.get_job(job["id"])["error"])
