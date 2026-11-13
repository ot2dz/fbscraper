import json
import os
import time
from urllib.parse import parse_qs

import requests

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from app.comments_runner import _decode_body
from fb_graphql_scraper.base.base_page import BasePage

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/1118927064107626")
    time.sleep(8)
    driver.execute_script(
        """
        for (const node of document.querySelectorAll('div[role="button"], span[role="button"]')) {
          if (/^\\d+\\s+comments?$/i.test((node.innerText || '').trim())) { node.click(); return; }
        }
        """
    )
    time.sleep(3)
    driver.execute_script(
        """
        for (const node of document.querySelectorAll('div[role="button"], span[role="button"]')) {
          if ((node.innerText || '').trim().toLowerCase() === 'most relevant') { (node.closest('[role="button"]') || node).click(); return; }
        }
        """
    )
    time.sleep(2)
    driver.execute_script(
        """
        for (const node of document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"]')) {
          if ((node.innerText || '').split('\\n')[0].trim().toLowerCase() === 'all comments') { node.click(); return; }
        }
        """
    )
    time.sleep(5)

    best = None
    for request in [r for r in driver.requests if "/api/graphql" in r.url]:
        if request.response is None:
            continue
        text = _decode_body(request.response.body)
        if "comment_rendering_instance_for_feed_location" not in text:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        node = ((data.get("data") or {}).get("node") or {})
        comments = ((node.get("comment_rendering_instance_for_feed_location") or {}).get("comments") or {})
        edges = comments.get("edges") or []
        if best is None or len(edges) > len(best[2]):
            best = (request, text, edges, comments.get("page_info") or {})

    if not best:
        print("no comments response")
        raise SystemExit

    request, text, edges, page_info = best
    body = request.body.decode("utf-8", "replace")
    parsed = parse_qs(body)
    doc_id = (parsed.get("doc_id") or [""])[0]
    variables = json.loads((parsed.get("variables") or ["{}"])[0])
    print("doc_id:", doc_id, "edges:", len(edges), "page_info:", page_info)
    print("variables keys:", list(variables.keys()))

    cookies = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}
    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Content-Type": "application/x-www-form-urlencoded",
    }

    base_fields = {key: values[0] for key, values in parsed.items()}
    cursor = page_info.get("end_cursor")
    PAGINATION_DOC_ID = "40427158136897660"
    attempts = {
        "pag+after": {**variables, "commentsAfterCursor": cursor},
        "pag+after+count": {**variables, "commentsAfterCursor": cursor, "commentsAfterCount": 10},
        "minimal": {
            "commentsAfterCursor": cursor,
            "commentsAfterCount": 10,
            "commentsBeforeCursor": None,
            "commentsBeforeCount": None,
            "commentsIntentToken": variables.get("commentsIntentToken"),
            "feedLocation": variables.get("feedLocation"),
            "feedbackSource": 2,
            "focusCommentID": None,
            "scale": 1,
            "useDefaultActor": False,
            "id": variables.get("id"),
        },
    }

    fetch_script = """
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

    for name, vars_out in attempts.items():
        fields = dict(base_fields)
        fields["doc_id"] = PAGINATION_DOC_ID
        fields["variables"] = json.dumps(vars_out)
        payload = driver.execute_async_script(fetch_script, fields)
        if payload.startswith("ERR:"):
            print(name, "-> fetch error", payload[:100])
            continue
        try:
            data = json.loads(payload.split("\n")[0])
        except ValueError:
            print(name, "-> invalid json", payload[:120])
            continue
        if data.get("errors"):
            print(name, "-> errors:", str(data["errors"])[:160])
            continue
        node = ((data.get("data") or {}).get("node") or {})
        comments = ((node.get("comment_rendering_instance_for_feed_location") or {}).get("comments") or {})
        new_edges = comments.get("edges") or []
        print(name, "-> edges:", len(new_edges), "next:", (comments.get("page_info") or {}).get("has_next_page"))
        if new_edges:
            print("   first:", (new_edges[0].get("node") or {}).get("body", {}).get("text", "")[:60])
finally:
    driver.quit()
