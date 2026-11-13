# -*- coding: utf-8 -*-
"""Single-thread job queue: one browser at a time."""
import queue
import threading

from app import db
from app.scraper_runner import run_scrape
from app.telegram_bot import job_summary_text, send_document, send_message, send_top_comments, send_top_posts

_queue = queue.Queue()
_started = False
_current_job = None
_lock = threading.Lock()


def enqueue(target, posts, days, source="web", chat_id=None, kind="posts"):
    job = db.create_job(target, posts, days, source=source, chat_id=chat_id, kind=kind)
    _queue.put(job["id"])
    return job


def _loop():
    global _current_job
    while True:
        job_id = _queue.get()
        job = db.get_job(job_id)
        with _lock:
            _current_job = job_id
        try:
            if job.get("kind") == "comments":
                from app.comments_runner import run_comments

                result = run_comments(job)
            else:
                result = run_scrape(job)
        except Exception as exc:  # noqa: BLE001
            db.update_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}"[:500])
            result = None
        finally:
            with _lock:
                _current_job = None
        finished = db.get_job(job_id)
        if finished and finished.get("source") == "telegram" and finished.get("chat_id"):
            if finished["status"] == "done":
                send_message(finished["chat_id"], job_summary_text(finished))
                if finished.get("kind") == "comments":
                    send_top_comments(finished["chat_id"], finished)
                else:
                    send_top_posts(finished["chat_id"], finished)
                send_document(finished["chat_id"], finished.get("result_path"), caption="النتيجة الكاملة (JSON)")
            else:
                send_message(finished["chat_id"], job_summary_text(finished))
        _queue.task_done()


def start_worker():
    global _started
    if _started:
        return
    thread = threading.Thread(target=_loop, name="scrape-worker", daemon=True)
    thread.start()
    _started = True


def queue_status():
    with _lock:
        current = _current_job
    pending = _queue.qsize()
    lines = [f"قيد التنفيذ: {current or 'لا شيء'}", f"في الانتظار: {pending}"]
    return "\n".join(lines)


def current_job():
    with _lock:
        return _current_job
