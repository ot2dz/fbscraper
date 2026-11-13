import json
import os
import time
from urllib.parse import parse_qs

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from fb_graphql_scraper.base.base_page import BasePage

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/1118927064107626")
    time.sleep(8)
    driver.execute_script(
        """
        const nodes = [...document.querySelectorAll('div[role="button"], span[role="button"]')];
        for (const node of nodes) {
          if (/^\\d+\\s+comments?$/i.test((node.innerText || '').trim())) { node.click(); return; }
        }
        """
    )
    time.sleep(3)
    driver.execute_script(
        """
        const nodes = [...document.querySelectorAll('div[role="button"], span[role="button"]')];
        for (const node of nodes) {
          if ((node.innerText || '').trim().toLowerCase() === 'most relevant') {
            (node.closest('[role="button"]') || node).click(); return;
          }
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
    requests = [r for r in driver.requests if "/api/graphql" in r.url]
    print("graphql requests:", len(requests))
    for request in requests[-3:]:
        body = request.body.decode("utf-8", "replace") if request.body else ""
        parsed = parse_qs(body)
        print("doc_id:", (parsed.get("doc_id") or [""])[0])
        print("variables:", (parsed.get("variables") or [""])[0][:300])
        response = request.response
        text = ""
        if response is not None:
            try:
                from app.comments_runner import _decode_body

                text = _decode_body(response.body)
            except Exception as exc:  # noqa: BLE001
                print("decode error:", exc)
        print("response len:", len(text), "| body count:", text.count('"body"'), "| comment:", text.count("comment"), "| page_info:", text.count("page_info"))
        print("head:", text[:300].replace("\n", " "))
finally:
    driver.quit()
