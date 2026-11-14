# -*- coding: utf-8 -*-
"""AI analysis of scraped comments (OpenAI-compatible endpoint)."""
import json
import re

import httpx

from app import db

SYSTEM_PROMPT = (
    "أنت محلل تعليقات تسويقية لمنشورات فيسبوك. "
    "حلّل التعليقات وأعد JSON فقط (بدون أي نص خارج JSON) بالعربية المختصرة. "
    "المفاتيح المطلوبة:\n"
    '{"summary":"شرح مختصر 2-4 أسطر","sentiment":"إيجابي|سلبي|مختلط",'
    '"price_mentioned":true,"price_details":["السعر أو العملة إن ذكر"],'
    '"criticisms":["الانتقادات"],"questions":["الأسئلة أو الطلبات"],'
    '"praise":["الإشادة"],"recommendations":["اقتراحات للبائع"],'
    '"top_comments":[{"text":"...","likes":0}]}'
)

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_BASE_URL = "https://opencode.ai/inference/openai/v1"


def _settings():
    return {
        "enabled": db.get_setting("ai_enabled", "0") == "1",
        "base_url": (db.get_setting("ai_base_url", "") or DEFAULT_BASE_URL).rstrip("/"),
        "api_key": db.get_setting("ai_api_key", "") or "",
        "model": db.get_setting("ai_model", "") or DEFAULT_MODEL,
        "max_comments": int(db.get_setting("ai_max_comments", "150") or 150),
        "extra": db.get_setting("ai_prompt_extra", "") or "",
    }


def _chat(base_url, api_key, model, messages, max_tokens=2600):
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        },
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return content or ""


def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"لم يرجع النموذج JSON صالحاً (بداية الرد: {text[:120]!r})")
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except ValueError:
        # last resort: remove trailing commas and retry
        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
        return json.loads(cleaned)


def analyze_comments(comments, post_url="", force=False):
    settings = _settings()
    if not settings["enabled"] and not force:
        return {"skipped": "تحليل AI غير مفعّل في الإعدادات"}
    if not settings["api_key"]:
        return {"skipped": "لم يتم إضافة مفتاح API للتحليل"}

    selected = comments[: settings["max_comments"]]
    lines = []
    for index, comment in enumerate(selected, start=1):
        text = " ".join(str(comment.get("text") or "").split())[:400]
        lines.append(
            f"{index}. {comment.get('author') or '?'} ({(comment.get('likes') or 0)} إعجاب"
            f"{'، رد' if comment.get('is_reply') else ''}): {text}"
        )

    user_prompt = (
        f"رابط المنشور: {post_url}\n"
        f"عدد التعليقات المحللة: {len(selected)} من {len(comments)}\n\n"
        "التعليقات:\n" + "\n".join(lines)
    )
    if settings["extra"]:
        user_prompt += f"\n\nتعليمات إضافية: {settings['extra']}"

    try:
        content = _chat(
            settings["base_url"],
            settings["api_key"],
            settings["model"],
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        analysis = _extract_json(content)
    except Exception as exc:  # noqa: BLE001
        try:
            content = _chat(
                settings["base_url"],
                settings["api_key"],
                settings["model"],
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                    {"role": "user", "content": "أعد الآن JSON صحيحاً فقط بدون أي نص أو شرح أو علامات ```"},
                ],
            )
            analysis = _extract_json(content)
        except Exception as retry_exc:  # noqa: BLE001
            print(f"AI analysis failed: {type(retry_exc).__name__}: {retry_exc}")
            return {"error": f"{type(retry_exc).__name__}: {retry_exc}"[:500]}

    analysis["_meta"] = {
        "model": settings["model"],
        "analyzed": len(selected),
        "total": len(comments),
    }
    return analysis


def analyze_job(job_id):
    job = db.get_job(job_id)
    if not job or not job.get("result_path"):
        return {"error": "لا توجد نتيجة محفوظة لهذه العملية"}
    import os

    if not os.path.exists(job["result_path"]):
        return {"error": "ملف النتيجة غير موجود"}
    with open(job["result_path"], encoding="utf-8") as handle:
        payload = json.load(handle)
    comments = payload.get("comments", [])
    analysis = analyze_comments(comments, payload.get("post_url", job.get("target") or ""))
    db.update_job(job_id, analysis=json.dumps(analysis, ensure_ascii=False))
    return analysis


def analysis_text(analysis, max_items=5):
    """Human readable Arabic summary for Telegram / UI."""
    if not analysis:
        return ""
    if analysis.get("skipped"):
        return f"ℹ️ {analysis['skipped']}"
    if analysis.get("error"):
        return f"⚠️ تعذر التحليل: {analysis['error']}"

    lines = [f"🧠 التحليل: {analysis.get('summary', '').strip()}"]
    if analysis.get("sentiment"):
        lines.append(f"• الانطباع العام: {analysis['sentiment']}")

    if analysis.get("price_mentioned"):
        details = analysis.get("price_details") or []
        text = "، ".join(str(item) for item in details[:3]) if details else "نعم"
        lines.append(f"• السعر: مذكور ({text})")
    else:
        lines.append("• السعر: غير مذكور")

    for label, key in (
        ("الانتقادات", "criticisms"),
        ("الأسئلة/الطلبات", "questions"),
        ("الإشادة", "praise"),
        ("اقتراحات", "recommendations"),
    ):
        items = [str(item).strip() for item in (analysis.get(key) or []) if str(item).strip()]
        if items:
            lines.append(f"• {label}: " + " | ".join(items[:max_items]))

    meta = analysis.get("_meta") or {}
    if meta.get("analyzed"):
        lines.append(f"(حُللت {meta['analyzed']} من {meta.get('total')} تعليقاً)")
    return "\n".join(lines)
