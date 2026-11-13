# -*- coding: utf-8 -*-
"""Telegram bot (long polling) with inline buttons."""
import asyncio
import json
import os

import httpx

from app import db
from app.config import PUBLIC_URL
from app.scraper_runner import normalize_target

API = "https://api.telegram.org/bot{token}/{method}"

HELP = (
    "بوت سحب منشورات فيسبوك\n\n"
    "استخدم الأزرار:\n"
    "🚀 سحب جديد — أرسل معرّف الصفحة أو رابطها ثم اختر العدد والأيام\n"
    "📋 آخر العمليات — عرض النتائج السابقة وإعادة إرسال الملف\n"
    "⏳ حالة الطابور — ما يعمل الآن وما ينتظر\n\n"
    "يمكنك أيضاً إرسال رابط الصفحة مباشرة في أي وقت."
)

_sessions = {}


def _keyboard(rows):
    return {"inline_keyboard": rows}


def _main_keyboard():
    rows = [
        [
            {"text": "🚀 سحب جديد", "callback_data": "m:new"},
            {"text": "📋 آخر العمليات", "callback_data": "m:jobs"},
        ],
        [
            {"text": "⏳ حالة الطابور", "callback_data": "m:status"},
            {"text": "❓ مساعدة", "callback_data": "m:help"},
        ],
    ]
    if PUBLIC_URL:
        rows.append([{"text": "🌐 لوحة التحكم", "url": PUBLIC_URL}])
    return _keyboard(rows)


def _back_keyboard():
    return _keyboard([[{"text": "⬅️ القائمة", "callback_data": "m:menu"}]])


def _options_keyboard(session):
    posts = session.get("posts")
    days = session.get("days")

    def mark(value, current):
        return f"{'✅ ' if value == current else ''}{value}"

    return _keyboard(
        [
            [
                {"text": f"{mark(10, posts)} منشور", "callback_data": "p:10"},
                {"text": f"{mark(20, posts)}", "callback_data": "p:20"},
                {"text": f"{mark(30, posts)}", "callback_data": "p:30"},
            ],
            [
                {"text": f"{mark(50, posts)}", "callback_data": "p:50"},
                {"text": f"{mark(100, posts)}", "callback_data": "p:100"},
                {"text": "✏️ مخصص", "callback_data": "p:c"},
            ],
            [
                {"text": f"{mark(7, days)} يوم", "callback_data": "d:7"},
                {"text": f"{mark(30, days)} يوم", "callback_data": "d:30"},
                {"text": f"{mark(90, days)} يوم", "callback_data": "d:90"},
            ],
            [
                {"text": "✏️ أيام مخصصة", "callback_data": "d:c"},
            ],
            [
                {"text": "✅ ابدأ السحب", "callback_data": "g"},
                {"text": "✖️ إلغاء", "callback_data": "c"},
            ],
        ]
    )


def _options_text(session):
    return (
        "اختر إعدادات السحب:\n\n"
        f"الصفحة: {session.get('target')}\n"
        f"عدد المنشورات: {session.get('posts')}\n"
        f"عدد الأيام: {session.get('days')}\n\n"
        "اضغط ✅ ابدأ السحب عند الجاهزية."
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


def _session(chat_id):
    if chat_id not in _sessions:
        _, default_posts, default_days = _limits()
        _sessions[chat_id] = {
            "state": "idle",
            "target": None,
            "posts": default_posts,
            "days": default_days,
        }
    return _sessions[chat_id]


def _api(method, token):
    return API.format(token=token, method=method)


def send_message(chat_id, text, keyboard=None):
    token = db.get_setting("telegram_token", "")
    if not token or not chat_id:
        return None
    try:
        payload = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
        if keyboard:
            payload["reply_markup"] = keyboard
        response = httpx.post(_api("sendMessage", token), json=payload, timeout=30).json()
        if not response.get("ok"):
            print(f"telegram sendMessage failed: {response.get('error_code')} {response.get('description')}")
            return None
        return response.get("result")
    except Exception as exc:  # noqa: BLE001
        print(f"telegram sendMessage failed: {exc}")
        return None


def edit_message(chat_id, message_id, text, keyboard=None):
    token = db.get_setting("telegram_token", "")
    if not token:
        return
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:4000], "disable_web_page_preview": True}
    if keyboard:
        payload["reply_markup"] = keyboard
    try:
        response = httpx.post(_api("editMessageText", token), json=payload, timeout=30).json()
        if not response.get("ok") and "not modified" not in str(response.get("description", "")):
            print(f"telegram editMessageText failed: {response.get('description')}")
    except Exception as exc:  # noqa: BLE001
        print(f"telegram editMessageText failed: {exc}")


def answer_callback(callback_id, text=""):
    token = db.get_setting("telegram_token", "")
    if not token:
        return
    try:
        httpx.post(_api("answerCallbackQuery", token), json={"callback_query_id": callback_id, "text": text[:200]}, timeout=20)
    except Exception as exc:  # noqa: BLE001
        print(f"telegram answerCallbackQuery failed: {exc}")


def send_document(chat_id, path, caption=""):
    token = db.get_setting("telegram_token", "")
    if not token or not chat_id or not path or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as handle:
            httpx.post(
                _api("sendDocument", token),
                data={"chat_id": chat_id, "caption": caption[:1000]},
                files={"document": (os.path.basename(path), handle, "application/json")},
                timeout=120,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"telegram sendDocument failed: {exc}")


def _top_posts_by_comments(path, limit=5):
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


def top_posts_keyboard(job, limit=5):
    """Inline buttons linking to the best posts by comment count."""
    rows = []
    for index, post in enumerate(_top_posts_by_comments(job.get("result_path") or "", limit), start=1):
        url = post.get("post_url")
        if not url:
            continue
        comments = post.get("comment_rendering_instance.comments.total_count") or 0
        likes = post.get("reaction_count.count") or 0
        rows.append(
            [{"text": f"{index}. {comments} تعليق / {likes} إعجاب", "url": url}]
        )
    return _keyboard(rows) if rows else None


def send_top_posts(chat_id, job, limit=5):
    posts = _top_posts_by_comments(job.get("result_path") or "", limit)
    if not posts:
        return
    lines = [f"أفضل {len(posts)} منشورات حسب التعليقات:"]
    for index, post in enumerate(posts, start=1):
        comments = post.get("comment_rendering_instance.comments.total_count") or 0
        likes = post.get("reaction_count.count") or 0
        text = " ".join(str(post.get("context") or "").split())[:45]
        lines.append(f"{index}. {comments} تعليق / {likes} إعجاب — {text}")
        if post.get("post_url"):
            lines.append(f"   {post['post_url']}")
    send_message(chat_id, "\n".join(lines), top_posts_keyboard(job, limit))


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
                        _api("getUpdates", token),
                        params={
                            "offset": self._offset,
                            "timeout": 30,
                            "allowed_updates": '["message","callback_query"]',
                        },
                    )
                    payload = response.json()
                if not payload.get("ok"):
                    description = payload.get("description", "telegram error")
                    self._last_error = description
                    if "webhook" in description.lower():
                        await self._delete_webhook(token)
                    await asyncio.sleep(10)
                    continue
                self._last_error = None
                for update in payload.get("result", []):
                    self._offset = update["update_id"] + 1
                    if update.get("message"):
                        await self._handle_message(token, update["message"])
                    elif update.get("callback_query"):
                        await self._handle_callback(token, update["callback_query"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(10)

    async def _delete_webhook(self, token):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                payload = (await client.post(
                    _api("deleteWebhook", token),
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
                me = (await client.post(_api("getMe", token))).json()
                webhook = (await client.post(_api("getWebhookInfo", token))).json()
            result["get_me"] = me.get("result") if me.get("ok") else me.get("description")
            info = webhook.get("result") or {}
            result["webhook"] = {
                "url": info.get("url") or "",
                "pending_updates": info.get("pending_update_count"),
                "last_error": info.get("last_error_message"),
            }
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    async def _refresh_identity(self, token):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(_api("getMe", token))
                payload = response.json()
                if payload.get("ok"):
                    self._username = payload["result"].get("username")
                else:
                    self._last_error = payload.get("description")
                webhook = (await client.post(_api("getWebhookInfo", token))).json()
            info = webhook.get("result") or {}
            self._webhook_url = info.get("url") or ""
            if self._webhook_url:
                await self._delete_webhook(token)
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)

    async def _handle_message(self, token, message):
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = (message.get("text") or "").strip()
        print(f"[telegram] chat={chat_id} text={text[:60]!r}")
        if not text:
            return
        if not _allowed(chat_id):
            send_message(chat_id, f"غير مصرح لك. معرّف المحادثة: {chat_id}")
            return

        session = _session(chat_id)
        command = text.split("@")[0].lower()

        if command in {"/start", "/menu"}:
            session["state"] = "idle"
            send_message(chat_id, "القائمة الرئيسية:", _main_keyboard())
            return
        if command == "/help":
            send_message(chat_id, HELP, _back_keyboard())
            return
        if command == "/id":
            send_message(chat_id, f"chat_id: {chat_id}")
            return
        if command == "/status":
            send_message(chat_id, _queue_status_text(), _back_keyboard())
            return

        if session["state"] == "await_posts":
            if not text.isdigit():
                send_message(chat_id, "أرسل رقماً صحيحاً لعدد المنشورات.", _back_keyboard())
                return
            max_posts, _, _ = _limits()
            session["posts"] = max(1, min(int(text), max_posts))
            session["state"] = "idle"
            send_message(chat_id, _options_text(session), _options_keyboard(session))
            return

        if session["state"] == "await_days":
            if not text.isdigit():
                send_message(chat_id, "أرسل رقماً صحيحاً لعدد الأيام.", _back_keyboard())
                return
            session["days"] = max(1, int(text))
            session["state"] = "idle"
            send_message(chat_id, _options_text(session), _options_keyboard(session))
            return

        if command == "/scrape":
            parts = text.split()[1:]
            if not parts:
                session["state"] = "await_target"
                send_message(chat_id, "أرسل معرّف الصفحة أو رابطها:", _back_keyboard())
                return
            try:
                session["target"] = normalize_target(parts[0])
            except ValueError as exc:
                send_message(chat_id, f"خطأ: {exc}", _back_keyboard())
                return
            if len(parts) > 1 and parts[1].isdigit():
                session["posts"] = int(parts[1])
            if len(parts) > 2 and parts[2].isdigit():
                session["days"] = int(parts[2])
            send_message(chat_id, _options_text(session), _options_keyboard(session))
            return

        try:
            session["target"] = normalize_target(text)
        except ValueError:
            send_message(chat_id, "أرسل /start لعرض القائمة أو رابط صفحة فيسبوك.", _main_keyboard())
            return
        session["state"] = "idle"
        send_message(chat_id, _options_text(session), _options_keyboard(session))

    async def _handle_callback(self, token, callback):
        chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
        message_id = callback.get("message", {}).get("message_id")
        data = callback.get("data", "")
        answer_callback(callback.get("id"), "")
        if not _allowed(chat_id):
            return

        session = _session(chat_id)

        if data == "m:menu":
            session["state"] = "idle"
            edit_message(chat_id, message_id, "القائمة الرئيسية:", _main_keyboard())
            return
        if data == "m:new":
            session["state"] = "await_target"
            edit_message(
                chat_id,
                message_id,
                "أرسل معرّف الصفحة أو رابطها (مثال: 100088686736411).",
                _back_keyboard(),
            )
            return
        if data == "m:help":
            edit_message(chat_id, message_id, HELP, _back_keyboard())
            return
        if data == "m:status":
            edit_message(chat_id, message_id, _queue_status_text(), _back_keyboard())
            return
        if data == "m:jobs":
            edit_message(chat_id, message_id, _jobs_text(), _jobs_keyboard())
            return
        if data == "c":
            session["state"] = "idle"
            edit_message(chat_id, message_id, "تم الإلغاء.", _main_keyboard())
            return
        if data.startswith("p:"):
            value = data.split(":", 1)[1]
            if value == "c":
                session["state"] = "await_posts"
                edit_message(chat_id, message_id, "أرسل عدد المنشورات المطلوب (رقم).", _back_keyboard())
                return
            session["posts"] = int(value)
            edit_message(chat_id, message_id, _options_text(session), _options_keyboard(session))
            return
        if data.startswith("d:"):
            value = data.split(":", 1)[1]
            if value == "c":
                session["state"] = "await_days"
                edit_message(chat_id, message_id, "أرسل عدد الأيام المطلوب (رقم).", _back_keyboard())
                return
            session["days"] = int(value)
            edit_message(chat_id, message_id, _options_text(session), _options_keyboard(session))
            return
        if data == "g":
            if not session.get("target"):
                edit_message(chat_id, message_id, "أرسل معرّف الصفحة أولاً.", _main_keyboard())
                return
            from app.jobs import enqueue

            max_posts, _, _ = _limits()
            job = enqueue(
                session["target"],
                max(1, min(int(session.get("posts") or 30), max_posts)),
                max(1, int(session.get("days") or 30)),
                source="telegram",
                chat_id=chat_id,
            )
            edit_message(
                chat_id,
                message_id,
                f"تم استلام الطلب ✅\njob_id: {job['id']}\n"
                f"الصفحة: {job['target']}\nالمنشورات: {job['posts_limit']}\nالأيام: {job['days']}\n"
                "سأرسل النتيجة عند الانتهاء.",
                _back_keyboard(),
            )
            return
        if data.startswith("j:"):
            job = db.get_job(data.split(":", 1)[1])
            if not job:
                edit_message(chat_id, message_id, "لم أجد هذه العملية.", _back_keyboard())
                return
            if job["status"] == "done":
                send_message(chat_id, job_summary_text(job))
                send_top_posts(chat_id, job)
                send_document(chat_id, job.get("result_path"), caption="النتيجة الكاملة (JSON)")
            else:
                send_message(chat_id, f"الحالة: {job['status']}\nالمنشورات: {job['post_count']}")
            return


def _queue_status_text():
    from app.jobs import queue_status

    return "حالة الطابور:\n" + queue_status()


def _jobs_text():
    rows = db.list_jobs(limit=5)
    if not rows:
        return "لا توجد عمليات بعد."
    return "آخر العمليات (اضغط للتفاصيل):"


def _jobs_keyboard():
    rows = db.list_jobs(limit=5)
    buttons = [
        [
            {
                "text": f"{row['id']} | {row['status']} | {row['post_count']} منشور",
                "callback_data": f"j:{row['id']}",
            }
        ]
        for row in rows
    ]
    buttons.append([{"text": "⬅️ القائمة", "callback_data": "m:menu"}])
    return _keyboard(buttons)


bot = TelegramBot()
