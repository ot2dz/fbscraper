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
    time.sleep(4)
    driver.execute_script(
        """
        const pattern = /^(view|عرض)\\s+(all\\s+)?\\d+\\s+(repl(y|ies)|رد|ردود)/i;
        for (const node of document.querySelectorAll('div[role="button"], span[role="button"]')) {
          const text = (node.innerText || '').trim();
          if (pattern.test(text)) { try { (node.closest('[role="button"]') || node).click(); } catch (error) {} }
        }
        """
    )
    time.sleep(4)
    for request in [r for r in driver.requests if "/api/graphql" in r.url][-6:]:
        body = request.body.decode("utf-8", "replace") if request.body else ""
        parsed = parse_qs(body)
        doc_id = (parsed.get("doc_id") or [""])[0]
        variables = (parsed.get("variables") or [""])[0]
        text = _decode_body(request.response.body) if request.response is not None else ""
        edges = text.count('"cursor"')
        print("doc_id:", doc_id, "| vars:", variables[:220])
        print("   response len:", len(text), "| cursors:", edges, "| has page_info:", "page_info" in text)
finally:
    driver.quit()
