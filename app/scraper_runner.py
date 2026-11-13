# -*- coding: utf-8 -*-
"""Runs one scrape job (blocking) and normalizes the result."""
import contextlib
import json
import math
import os
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

import fb_graphql_scraper.facebook_graphql_scraper as scraper_module
from fb_graphql_scraper.facebook_graphql_scraper import FacebookGraphqlScraper

from app import db
from app.config import CHROMEDRIVER_PATH, LOGS_DIR, RESULTS_DIR

_requests_patched = False

FACEBOOK_HOSTS = ("facebook.com", "fb.com", "fb.me", "facebook.net")
UNSUPPORTED_PATHS = {
    "groups",
    "watch",
    "reel",
    "reels",
    "video",
    "videos",
    "events",
    "marketplace",
    "gaming",
    "story.php",
    "permalink.php",
    "photo.php",
    "media",
    "login",
    "login.php",
    "home.php",
    "friends",
    "photos",
    "about",
    "help",
    "policies",
    "privacy",
    "settings",
    "notifications",
    "messages",
    "bookmarks",
    "saved",
    "memories",
    "fundraisers",
    "business",
    "donate",
    "offers",
    "jobs",
    "places",
    "hashtag",
    "search",
}


def normalize_target(raw: str) -> str:
    """Accept any facebook page/profile url, a username or a numeric id.

    Returns a username/id, or the original short url (fb.me, /share/...) that
    the worker resolves over HTTP before scraping.
    """
    value = (raw or "").strip().strip("<>").strip()
    if not value:
        raise ValueError("أرسل معرّف الصفحة أو رابطها")
    if value.startswith("@"):
        value = value[1:]

    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, flags=re.I) and re.search(
        r"(facebook\.com|fb\.me|fb\.com|facebook\.net)/", value, flags=re.I
    ):
        value = "https://" + value

    if "://" in value:
        parsed = urlparse(value)
        host = (parsed.netloc or "").lower().split(":")[0]
        path = parsed.path.strip("/")
        query = parse_qs(parsed.query)

        if host.endswith("l.facebook.com") or host.endswith("lm.facebook.com"):
            redirected = (query.get("u") or [""])[0]
            if redirected:
                return normalize_target(redirected)
            raise ValueError("رابط تحويل غير صالح")

        if not any(host == item or host.endswith("." + item) for item in FACEBOOK_HOSTS):
            raise ValueError("الرابط ليس من فيسبوك")

        if host.endswith("fb.me") or path.startswith("share/") or path.startswith("share."):
            return value

        if path.startswith("profile.php"):
            profile_id = (query.get("id") or [""])[0]
            if profile_id.isdigit():
                return profile_id
            raise ValueError("رابط profile.php بدون معرّف")

        parts = [part for part in path.split("/") if part]
        if not parts:
            raise ValueError("الرابط لا يحتوي على صفحة")

        head = parts[0].lower()
        if head in {"people", "pages"}:
            for part in reversed(parts):
                if part.isdigit():
                    return part
            trailing = re.search(r"(\d{5,})$", parts[-1])
            if trailing:
                return trailing.group(1)
            return unquote(parts[-1])

        if head in UNSUPPORTED_PATHS:
            raise ValueError("هذا النوع من الروابط غير مدعوم (مجموعة/فيديو/حدث...)")

        if parts[0].isdigit():
            return parts[0]
        return unquote(parts[0])

    cleaned = value.split("?")[0].split("#")[0].strip("/")
    if not cleaned:
        raise ValueError("معرّف الصفحة غير صالح")
    if cleaned.isdigit():
        return cleaned
    if re.fullmatch(r"[A-Za-z0-9._\-]+", cleaned):
        return cleaned
    raise ValueError("معرّف أو رابط غير صالح")


def resolve_target(raw: str, timeout: int = 25) -> str:
    """Resolve short links (fb.me, /share/...) then return the final target."""
    target = normalize_target(raw)
    for _ in range(3):
        if not target.startswith("http"):
            return target
        proxy = normalize_proxy(db.get_setting("proxy", ""))
        kwargs = {"allow_redirects": True, "timeout": timeout}
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        response = scraper_module.requests.get(target, **kwargs)
        target = normalize_target(response.url)
    return target


def normalize_proxy(raw: str) -> str:
    """Accept host:port:user:pass, host:port or a full URL."""
    value = (raw or "").strip()
    if not value:
        return ""
    if "://" in value:
        return value
    parts = value.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    return f"http://{value}"


def _patch_requests():
    """Default timeout (and optional proxy) for the plain HTTP pagination calls."""
    global _requests_patched
    if _requests_patched:
        return
    original_post = scraper_module.requests.post
    original_get = scraper_module.requests.get

    def _kwargs():
        kw = {"timeout": int(db.get_setting("request_timeout", "30"))}
        proxy = normalize_proxy(db.get_setting("proxy", ""))
        if proxy:
            kw["proxies"] = {"http": proxy, "https": proxy}
        return kw

    def post(*args, **kwargs):
        for key, value in _kwargs().items():
            kwargs.setdefault(key, value)
        return original_post(*args, **kwargs)

    def get(*args, **kwargs):
        for key, value in _kwargs().items():
            kwargs.setdefault(key, value)
        return original_get(*args, **kwargs)

    scraper_module.requests.post = post
    scraper_module.requests.get = get
    _requests_patched = True


def _sanitize(value):
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _summary(data):
    def total(key):
        return sum(int(p.get(key) or 0) for p in data)

    dates = [p.get("published_date2") for p in data if p.get("published_date2")]
    return {
        "post_count": len(data),
        "likes": total("reaction_count.count"),
        "comments": total("comment_rendering_instance.comments.total_count"),
        "shares": total("share_count.count"),
        "oldest": min(dates) if dates else None,
        "newest": max(dates) if dates else None,
    }


def _stop_after_posts(spider, posts_limit):
    original = scraper_module.compare_timestamp

    def patched(timestamp, days_limit, display_progress=True):
        if len(spider.requests_parser.collect_posts()) >= posts_limit:
            print(f"Reached posts limit ({posts_limit}).")
            return True
        return original(timestamp=timestamp, days_limit=days_limit, display_progress=display_progress)

    scraper_module.compare_timestamp = patched
    return original


def run_scrape(job):
    """job: dict from the jobs table. Returns the full result dict."""
    _patch_requests()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f"{job['id']}.log")
    result_path = os.path.join(RESULTS_DIR, f"{job['id']}.json")

    proxy = normalize_proxy(db.get_setting("proxy", ""))
    if proxy:
        os.environ["FB_PROXY"] = proxy
    else:
        os.environ.pop("FB_PROXY", None)

    db.update_job(job["id"], status="running", started_at=time.strftime("%Y-%m-%d %H:%M:%S"), log_path=log_path)

    try:
        target = resolve_target(job["target"])
    except Exception as exc:  # noqa: BLE001
        db.update_job(
            job["id"],
            status="failed",
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            error=f"رابط غير صالح: {exc}"[:500],
        )
        return None
    if target != job["target"]:
        db.update_job(job["id"], target=target)
        job = db.get_job(job["id"])

    last_error = None
    for attempt in (1, 2):
        spider = None
        try:
            with open(log_path, "a", encoding="utf-8", errors="replace") as log_file, contextlib.redirect_stdout(log_file):
                print(f"=== attempt {attempt} | target={job['target']} | posts={job['posts_limit']} | days={job['days']}")
                spider = FacebookGraphqlScraper(
                    driver_path=CHROMEDRIVER_PATH,
                    open_browser=False,
                )
                original_compare = _stop_after_posts(spider, int(job["posts_limit"]))
                try:
                    result = spider.get_user_posts(
                        fb_username_or_userid=job["target"],
                        days_limit=int(job["days"]),
                        display_progress=True,
                    )
                finally:
                    scraper_module.compare_timestamp = original_compare

            data = result.get("data", [])[: int(job["posts_limit"])]
            result["data"] = data
            result = _sanitize(result)
            with open(result_path, "w", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2, default=str)

            profile = result.get("profile") or []
            summary = _summary(data)
            db.update_job(
                job["id"],
                status="done",
                finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                result_path=result_path,
                profile_name=str(profile[0])[:200] if profile else "",
                **summary,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            with open(log_path, "a", encoding="utf-8", errors="replace") as log_file:
                log_file.write(f"\n!!! attempt {attempt} failed: {type(exc).__name__}: {exc}\n")
                if spider is not None:
                    try:
                        driver = spider.page_optional.driver
                        log_file.write(f"current_url={driver.current_url}\ntitle={driver.title}\n")
                        log_file.write("requests:\n")
                        for request in list(driver.requests)[:25]:
                            log_file.write(f"  {request.method} {request.url[:200]}\n")
                        log_file.write("page_source:\n")
                        log_file.write(driver.page_source[:3000])
                        log_file.write("\n")
                    except Exception as debug_exc:  # noqa: BLE001
                        log_file.write(f"debug dump failed: {debug_exc}\n")
            time.sleep(3)
        finally:
            if spider is not None:
                try:
                    spider.page_optional.quit_driver()
                except Exception:
                    pass

    message = f"{type(last_error).__name__}: {last_error}"[:500]
    db.update_job(job["id"], status="failed", finished_at=time.strftime("%Y-%m-%d %H:%M:%S"), error=message)
    return None
