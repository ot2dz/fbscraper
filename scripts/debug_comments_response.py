import json
import os
import time
from urllib.parse import parse_qs

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
        if '"body"' in text and "comment_rendering_instance" in text:
            best = (request, text)
    if not best:
        print("no comments response found")
    else:
        request, text = best
        body = request.body.decode("utf-8", "replace")
        parsed = parse_qs(body)
        print("doc_id:", (parsed.get("doc_id") or [""])[0])
        print("variables:", (parsed.get("variables") or [""])[0])
        data = json.loads(text)
        out_path = os.path.join(os.environ["TEMP"], "fb_comments_response.json")
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        print("saved:", out_path, "len:", len(text))

        def show(node, depth=0, path="data"):
            if depth > 5:
                return
            if isinstance(node, dict):
                keys = list(node.keys())
                print("  " * depth + path + " keys: " + ", ".join(keys[:14]))
                for key in ("page_info", "comments", "edges"):
                    if key in node:
                        show(node[key], depth + 1, key)
            elif isinstance(node, list):
                print("  " * depth + path + f" list[{len(node)}]")
                if node:
                    show(node[0], depth + 1, path + "[0]")

        show(data)
finally:
    driver.quit()
