# -*- coding: utf-8 -*-
"""Scrape comments of one specific Facebook post."""
import contextlib
import json
import os
import re
import time
from urllib.parse import parse_qs

from app import db
from app.config import CHROMEDRIVER_PATH, LOGS_DIR, RESULTS_DIR
from app.scraper_runner import normalize_proxy

FALLBACK_PAGINATION_DOC_ID = "40427158136897660"

CLICK_COMMENTS_SCRIPT = """
const nodes = [...document.querySelectorAll('div[role="button"], span[role="button"]')];
for (const node of nodes) {
  const text = (node.innerText || '').trim().toLowerCase();
  if (/^[\\d.,\\s]+(comments?|commentaires?|تعليق|تعليقات)/.test(text)
      || text === 'comments' || text === 'تعليقات' || text === 'commentaires') {
    node.click();
    return text;
  }
}
return null;
"""

CLICK_ALL_COMMENTS_SCRIPT = """
const nodes = [...document.querySelectorAll('div[role="button"], span[role="button"]')];
for (const node of nodes) {
  const text = (node.innerText || '').trim().toLowerCase();
  if (text === 'most relevant' || text === 'الأكثر صلة' || text === 'les plus pertinents'
      || text === 'top comments' || text === 'meilleur commentaire') {
    (node.closest('[role="button"]') || node).click();
    return text;
  }
}
return null;
"""

PICK_ALL_COMMENTS_SCRIPT = """
for (const node of document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"]')) {
  const first = (node.innerText || '').split('\\n')[0].trim().toLowerCase();
  if (first === 'all comments' || first === 'كل التعليقات' || first === 'tous les commentaires') {
    node.click();
    return first;
  }
}
return null;
"""

CLICK_REPLIES_SCRIPT = """
const pattern = /^(view|عرض|afficher)\\s+(all\\s+)?\\d+\\s+(repl(y|ies)|رد|ردود|réponses?)/i;
let clicked = 0;
for (const node of document.querySelectorAll('div[role="button"], span[role="button"], a[role="link"]')) {
  const text = (node.innerText || '').trim();
  if (pattern.test(text)) {
    try { (node.closest('[role="button"]') || node).click(); clicked += 1; } catch (error) {}
  }
}
return clicked;
"""

FETCH_SCRIPT = """
const done = arguments[arguments.length - 1];
const fields = arguments[0];
const params = new URLSearchParams();
for (const key of Object.keys(fields)) params.append(key, fields[key]);
fetch('https://www.facebook.com/api/graphql/', {
  method: 'POST',
  body: params,
  headers: {'content-type': 'application/x-www-form-urlencoded'},
  credentials: 'include',
}).then(r => r.text()).then(t => done(t)).catch(e => done('ERR:' + e));
"""


def build_post_url(target):
    value = (target or "").strip().strip("<>")
    if not value:
        raise ValueError("أرسل رابط المنشور")
    if value.isdigit():
        return f"https://www.facebook.com/{value}"
    if not value.startswith("http"):
        value = "https://" + value
    return value


def _looks_like_comment(node):
    body = node.get("body")
    return (
        isinstance(body, dict)
        and isinstance(body.get("text"), str)
        and bool(body.get("text").strip())
        and ("author" in node or "created_time" in node)
        and "id" in node
    )


def _extract_comment(node):
    feedback = node.get("feedback")
    if not isinstance(feedback, dict):
        feedback = {}
    reactions = feedback.get("reaction_count")
    if not isinstance(reactions, dict):
        reactions = node.get("reaction_count")
    if not isinstance(reactions, dict):
        reactions = {}
    author = node.get("author")
    if not isinstance(author, dict):
        author = {}
    body = node.get("body")
    text = body.get("text", "") if isinstance(body, dict) else ""
    parent = node.get("parent_comment_id")
    if isinstance(parent, dict):
        parent = parent.get("id")
    elif not parent:
        comment_parent = node.get("comment_parent")
        parent = comment_parent.get("id") if isinstance(comment_parent, dict) else None

    likes = reactions.get("count")
    for container in (feedback, node):
        if likes:
            break
        reactors = container.get("reactors")
        if isinstance(reactors, dict):
            likes = reactors.get("count_reduced") or reactors.get("count")
        if not likes:
            top = container.get("top_reactions")
            if isinstance(top, dict):
                likes = sum(
                    (edge.get("reaction_count") or 0)
                    for edge in (top.get("edges") or [])
                    if isinstance(edge, dict)
                )
    try:
        likes = int(likes or 0)
    except (TypeError, ValueError):
        likes = 0

    return {
        "comment_id": str(node.get("id")),
        "author": author.get("name") or author.get("short_name") or "",
        "author_id": str(author.get("id") or ""),
        "text": text,
        "likes": likes,
        "created_time": node.get("created_time"),
        "is_reply": bool(parent) or (node.get("depth") or 0) > 0,
        "parent_comment_id": str(parent) if parent else None,
        "post_id": str(node.get("post_id") or ""),
    }


def _walk(node, found):
    if isinstance(node, dict):
        if node.get("__typename") == "Comment" or _looks_like_comment(node):
            found.append(_extract_comment(node))
        for value in node.values():
            _walk(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk(value, found)


def _decode_body(raw):
    """Meta serves GraphQL responses as zstd/gzip; JS bundles may be brotli."""
    if not raw:
        return ""
    try:
        if raw[:4] == b"\x28\xb5\x2f\xfd":
            import zstandard

            return zstandard.ZstdDecompressor().decompress(raw, max_output_size=128 * 1024 * 1024).decode("utf-8", "replace")
        if raw[:2] == b"\x1f\x8b":
            import gzip

            return gzip.decompress(raw).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        pass
    try:
        return raw.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def _add_comments(payload, known):
    found = []
    _walk(payload, found)
    for comment in found:
        key = comment["comment_id"]
        if key and comment["text"].strip() and key not in known:
            known[key] = comment


def harvest(driver, known):
    for request in list(driver.requests):
        if "/api/graphql" not in request.url or request.method != "POST":
            continue
        if request.response is None:
            continue
        text = _decode_body(request.response.body)
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            _add_comments(payload, known)
    return known


def harvest_source(source, known):
    """Facebook server-renders the first comments inside application/json blocks."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(source, "html.parser")
    for block in soup.find_all("script", {"type": "application/json"}):
        raw = block.string or block.get_text() or ""
        if '"body"' not in raw and '"Comment"' not in raw:
            continue
        try:
            payload = json.loads(raw)
        except ValueError:
            continue
        _add_comments(payload, known)
    return known


def _comments_node(payload):
    node = ((payload.get("data") or {}).get("node") or {}) if isinstance(payload, dict) else {}
    return (
        (node.get("comment_rendering_instance_for_feed_location") or {}).get("comments")
        or (node.get("comment_rendering_instance") or {}).get("comments")
        or {}
    )


def _find_comments_request(driver):
    """Return (form fields, variables, page_info, edges) of the initial comments query."""
    best = None
    for request in list(driver.requests):
        if "/api/graphql" not in request.url or request.method != "POST" or not request.body:
            continue
        text = _decode_body(request.response.body) if request.response is not None else ""
        if "comment_rendering_instance_for_feed_location" not in text:
            continue
        try:
            payload = json.loads(text.split("\n")[0])
        except ValueError:
            continue
        comments = _comments_node(payload)
        edges = comments.get("edges") or []
        if best is None or len(edges) > len(best[3]):
            form = {key: values[0] for key, values in parse_qs(request.body.decode("utf-8", "replace")).items()}
            try:
                variables = json.loads(form.get("variables") or "{}")
            except ValueError:
                variables = {}
            best = (form, variables, comments.get("page_info") or {}, edges)
    return best


def _pagination_doc_id(driver):
    pattern = re.compile(r'__d\("CommentsListComponentsPaginationQuery_facebookRelayOperation",\[\],\(function\([^)]*\)\{[a-z]\.exports="(\d+)"\}')
    for request in list(driver.requests):
        if ".js" not in request.url or request.response is None:
            continue
        text = _decode_body(request.response.body)
        match = pattern.search(text)
        if match:
            return match.group(1)
    return FALLBACK_PAGINATION_DOC_ID


def _fetch_page(driver, fields, doc_id, variables):
    body = dict(fields)
    body["doc_id"] = doc_id
    body["variables"] = json.dumps(variables)
    payload = driver.execute_async_script(FETCH_SCRIPT, body)
    if not payload or payload.startswith("ERR:"):
        return None
    try:
        return json.loads(payload.split("\n")[0])
    except ValueError:
        return None


def _open_comments(driver):
    driver.execute_script(CLICK_COMMENTS_SCRIPT)
    time.sleep(3)
    driver.execute_script(CLICK_ALL_COMMENTS_SCRIPT)
    time.sleep(1.5)
    driver.execute_script(PICK_ALL_COMMENTS_SCRIPT)
    time.sleep(2)


def run_comments(job):
    """job: dict from the jobs table with kind='comments'."""
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
    limit = max(1, int(job["posts_limit"]))
    url = build_post_url(job["target"])

    from fb_graphql_scraper.base.base_page import BasePage

    spider = None
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as log_file, contextlib.redirect_stdout(log_file):
            print(f"=== comments | url={url} | limit={limit}")
            spider = BasePage(driver_path=CHROMEDRIVER_PATH, open_browser=False)
            driver = spider.driver
            driver.get(url)
            time.sleep(6)
            try:
                from fb_graphql_scraper.pages.page_optional import PageOptional

                PageOptional(driver=driver).click_reject_login_button()
            except Exception:  # noqa: BLE001
                pass

            known = {}
            harvest_source(driver.page_source, known)
            _open_comments(driver)

            found = _find_comments_request(driver)
            if not found:
                raise RuntimeError("لم يتم العثور على طلب التعليقات (قد يكون المنشور خاصاً أو محجوباً)")

            fields, variables, page_info, edges = found
            pagination_doc_id = _pagination_doc_id(driver)
            print(f"initial edges={len(edges)} total={page_info} pagination_doc_id={pagination_doc_id}")

            for edge in edges:
                node = edge.get("node") if isinstance(edge, dict) else None
                if isinstance(node, dict):
                    _add_comments(node, known)

            cursor = page_info.get("end_cursor")
            has_next = bool(page_info.get("has_next_page"))
            rounds = 0
            while has_next and cursor and len(known) < limit and rounds < 200:
                rounds += 1
                variables_next = dict(variables)
                variables_next["commentsAfterCursor"] = cursor
                payload = _fetch_page(driver, fields, pagination_doc_id, variables_next)
                if not payload or payload.get("errors"):
                    print(f"page {rounds}: stop ({str((payload or {}).get('errors'))[:120]})")
                    break
                comments = _comments_node(payload)
                page_edges = comments.get("edges") or []
                for edge in page_edges:
                    node = edge.get("node") if isinstance(edge, dict) else None
                    if isinstance(node, dict):
                        _add_comments(node, known)
                next_info = comments.get("page_info") or {}
                cursor = next_info.get("end_cursor")
                has_next = bool(next_info.get("has_next_page"))
                print(f"page {rounds}: +{len(page_edges)} edges | total={len(known)} | next={has_next}")
                if not page_edges:
                    break
                time.sleep(0.8)

            # Replies are collapsed behind "View N replies" buttons.
            for _ in range(3):
                clicked = driver.execute_script(CLICK_REPLIES_SCRIPT)
                time.sleep(2)
                harvest(driver, known)
                harvest_source(driver.page_source, known)
                if not clicked:
                    break
            print(f"after replies: {len(known)} comments")

        comments = list(known.values())[:limit]
        for comment in comments:
            created = comment.get("created_time")
            if isinstance(created, (int, float)):
                comment["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(created))
            else:
                comment["created_at"] = None

        result = {
            "post_url": url,
            "count": len(comments),
            "comments": comments,
        }
        with open(result_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, default=str)

        db.update_job(
            job["id"],
            status="done",
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            result_path=result_path,
            post_count=len(comments),
            likes=sum(comment.get("likes") or 0 for comment in comments),
            comments=len(comments),
            shares=0,
            profile_name=url[:200],
        )
        return result
    except Exception as exc:  # noqa: BLE001
        with open(log_path, "a", encoding="utf-8", errors="replace") as log_file:
            log_file.write(f"\n!!! comments scrape failed: {type(exc).__name__}: {exc}\n")
        db.update_job(
            job["id"],
            status="failed",
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            error=f"{type(exc).__name__}: {exc}"[:500],
        )
        return None
    finally:
        if spider is not None:
            try:
                spider.quit_driver()
            except Exception:  # noqa: BLE001
                pass
