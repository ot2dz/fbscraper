# -*- coding: utf-8 -*-
"""Minimal Telegram bot (long polling) for the scraper."""
import asyncio
import html
import json
import os

import httpx

from app import db
from app.config import ensure_dirs
from app.scraper_runner import normalize_target

API = "https://api.telegram.org/bot{token}/{method}"

HELP = (
    "بوت سحب منشورات فيسبوك\n\n"
    "/scrape <معرّف أو رابط الصفحة> [عدد المنشورات] [عدد الأيام]\n"
    "مثال: /scrape 100088686736411 30 30\n\n"
    "/status حالة الطابور\n"
    "/last آخر 5 عمليات\n"
    "/result <job_id> إعادة إرسال الملف\n"
    "/id معرّف المحادثة\n\n"
    "يمكنك أيضاً إرسال رابط الصفحة مباشرة."
)


def _allowed(chat_id):
    if db.get_setting("telegram_allow_all", "1") == "1":
        return True
    allowed = db.get_setting("telegram_allowed_ids", "")
    ids = {item.strip() for item in allowed.replace(";", ",").split(",") if item.strip()}
    return str(chat_id) in ids


def _limits():
    max_posts = int(db.get_setting("max_posts", "200") or 200)
    default_posts = min(int(db.get_setting("default_posts", "30") or 30), max_posts)
    default_days = int(db.get_setting("default_days", "30") or 30)
    return max_posts, default_posts, default_days


def _parse_scrape_args(parts):
    if not parts:
        raise ValueError("أرسل معرّف الصفحة أو رابطها")
    target = normalize_target(parts[0])
    max_posts, default_posts, default_days = _limits()
    posts = default_posts
    days = default_days
    if len(parts) > 1 and parts[1].isdigit():
        posts = max(1, min(int(parts[1]), max_posts))
    if len(parts) > 2 and parts[2].isdigit():
        days = max(1, int(parts[2]))
    return target, posts, days


def send_message(chat_id, text):
    token = db.get_setting("telegram_token", "")
    if not token or not chat_id:
        print(f"telegram sendMessage skipped (token={bool(token)} chat={chat_id})")
        return
    try:
        response = httpx.post(
            API.format(token=token, method="sendMessage"),
            json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
            timeout=30,
        )
        payload = response.json()
        if not payload.get("ok"):
            print(f"telegram sendMessage failed: {payload.get('error_code')} {payload.get('description')}")
        else:
            print(f"telegram sendMessage ok -> chat={chat_id}")
    except Exception as exc:  # noqa: BLE001
        print(f"telegram sendMessage failed: {exc}")


def send_document(chat_id, path, caption=""):
    token = db.get_setting("telegram_token", "")
    if not token or not chat_id or not path or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as handle:
            httpx.post(
                API.format(token=token, method="sendDocument"),
                data={"chat_id": chat_id, "caption": caption[:1000]},
                files={"document": (os.path.basename(path), handle, "application/json")},
                timeout=120,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"telegram sendDocument failed: {exc}")


def _top_posts_by_comments(path, limit=3):
    try:
        with open(path, encoding="utf-8") as handle:
            posts = json.load(handle).get("data", [])
    except Exception:  # noqa: BLE001
        return []
    posts.sort(
        key=lambda post: post.get("comment_rendering_instance.comments.total_count") or 0,
        reverse=True,
    )
    return posts[:limit]


def job_summary_text(job):
    if job["status"] == "done":
        lines = [
            f"تم سحب {job['post_count']} منشوراً ✅",
            f"الصفحة: {job['target']}",
            f"الفترة: {job['oldest'] or '-'} → {job['newest'] or '-'}",
            f"الإعجابات: {job['likes']}",
            f"التعليقات: {job['comments']}",
            f"المشاركات: {job['shares']}",
            f"job_id: {job['id']}",
        ]
        top = _top_posts_by_comments(job.get("result_path") or "")
        if top:
            lines.append("")
            lines.append("أعلى المنشورات بالتعليقات:")
            for index, post in enumerate(top, start=1):
                text = " ".join(str(post.get("context") or "").split())[:70]
                lines.append(
                    f"{index}. {post.get('comment_rendering_instance.comments.total_count') or 0} تعليق / "
                    f"{post.get('reaction_count.count') or 0} إعجاب — {text}"
                )
        return "\n".join(lines)
    return f"فشل السحب ❌\njob_id: {job['id']}\n{job['error'] or ''}"[:1500]


class TelegramBot:
    def __init__(self):
        self._task = None
        self._offset = 0
        self._username = None
        self._last_error = None
        self._webhook_url = None

    @property
    def running(self):
        return self._task is not None and not self._task.done()

    def status(self):
        return {
            "running": self.running,
            "username": self._username,
            "token_set": bool(db.get_setting("telegram_token", "")),
            "enabled": db.get_setting("telegram_enabled", "1") == "1",
            "last_error": self._last_error,
            "webhook_url": self._webhook_url,
        }

    async def start(self):
        await self.stop()
        token = db.get_setting("telegram_token", "")
        if db.get_setting("telegram_enabled", "1") != "1" or not token:
            return
        self._task = asyncio.create_task(self._poll_loop(token))

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _poll_loop(self, token):
        await self._refresh_identity(token)
        while True:
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.get(
                        API.format(token=token, method="getUpdates"),
                        params={"offset": self._offset, "timeout": 30, "allowed_updates": '["message"]'},
                    )
                    payload = response.json()
                if not payload.get("ok"):
                    description = payload.get("description", "telegram error")
                    self._last_error = description
                    if "webhook" in description.lower() or "409" in str(payload.get("error_code")):
                        await self._delete_webhook(token)
                    await asyncio.sleep(10)
                    continue
                self._last_error = None
                for update in payload.get("result", []):
                    self._offset = update["update_id"] + 1
                    message = update.get("message") or {}
                    if message:
                        await self._handle(token, message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(10)

    async def _delete_webhook(self, token):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                payload = (await client.post(
                    API.format(token=token, method="deleteWebhook"),
                    json={"drop_pending_updates": False},
                )).json()
            if payload.get("ok"):
                self._webhook_url = ""
                print("Telegram webhook removed, long polling can receive updates.")
            else:
                self._last_error = payload.get("description")
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)

    async def diagnostics(self):
        """Live Telegram API state (used by the settings page)."""
        token = db.get_setting("telegram_token", "")
        result = {
            "token_set": bool(token),
            "running": self.running,
            "username": self._username,
            "last_error": self._last_error,
        }
        if not token:
            return result
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                me = (await client.post(API.format(token=token, method="getMe"))).json()
                webhook = (await client.post(API.format(token=token, method="getWebhookInfo"))).json()
                updates = (await client.post(
                    API.format(token=token, method="getUpdates"),
                    json={"offset": -1, "limit": 1, "timeout": 0},
                )).json()
            result["get_me"] = me.get("result") if me.get("ok") else me.get("description")
            info = webhook.get("result") or {}
            result["webhook"] = {
                "url": info.get("url") or "",
                "pending_updates": info.get("pending_update_count"),
                "last_error": info.get("last_error_message"),
            }
            result["pending_updates"] = len(updates.get("result") or []) if updates.get("ok") else updates.get("description")
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    async def _refresh_identity(self, token):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(API.format(token=token, method="getMe"))
                payload = response.json()
                if payload.get("ok"):
                    self._username = payload["result"].get("username")
                else:
                    self._last_error = payload.get("description")
                webhook = (await client.post(API.format(token=token, method="getWebhookInfo"))).json()
            info = webhook.get("result") or {}
            self._webhook_url = info.get("url") or ""
            if self._webhook_url:
                # Long polling and a webhook cannot work together.
                await self._delete_webhook(token)
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)

    async def _handle(self, token, message):
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = (message.get("text") or "").strip()
        print(f"[telegram] chat={chat_id} text={text[:60]!r}")
        if not text:
            return
        if not _allowed(chat_id):
            send_message(chat_id, f"غير مصرح لك. معرّف المحادثة: {chat_id}")
            return

        command, _, rest = text.partition(" ")
        command = command.split("@")[0].lower()

        if command in {"/start", "/help"}:
            send_message(chat_id, HELP)
            return
        if command == "/id":
            send_message(chat_id, f"chat_id: {chat_id}")
            return
        if command == "/status":
            from app.jobs import queue_status

            send_message(chat_id, queue_status())
            return
        if command == "/last":
            rows = db.list_jobs(limit=5)
            if not rows:
                send_message(chat_id, "لا توجد عمليات بعد.")
                return
            lines = [
                f"{row['id']} | {row['status']} | {row['target']} | {row['post_count']} منشور"
                for row in rows
            ]
            send_message(chat_id, "\n".join(lines))
            return
        if command == "/result":
            job_id = rest.strip()
            job = db.get_job(job_id)
            if not job or not job.get("result_path"):
                send_message(chat_id, "لم أجد نتيجة لهذا المعرّف.")
                return
            send_document(chat_id, job["result_path"], caption=job_summary_text(job))
            return

        from app.jobs import enqueue

        if command == "/scrape":
            args = rest.split()
        else:
            args = text.split()

        try:
            target, posts, days = _parse_scrape_args(args)
        except ValueError as exc:
            send_message(chat_id, f"خطأ: {exc}\n\n{HELP}")
            return

        job = enqueue(target, posts, days, source="telegram", chat_id=chat_id)
        send_message(
            chat_id,
            f"تم استلام الطلب ✅\njob_id: {job['id']}\nالصفحة: {target}\nالمنشورات: {posts}\nالأيام: {days}\n"
            "سأرسل النتيجة عند الانتهاء.",
        )


bot = TelegramBot()
