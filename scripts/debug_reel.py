import json
import os
import sys
import time
from urllib.parse import parse_qs

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbreel_test")

from app.comments_runner import _decode_body, harvest, harvest_source
from fb_graphql_scraper.base.base_page import BasePage

url = sys.argv[1] if len(sys.argv) > 1 else "https://www.facebook.com/reel/1107691808301702"
if not url.startswith("http"):
    url = "https://www.facebook.com/" + url

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get(url)
    time.sleep(10)
    print("final:", driver.current_url)
    print("title:", driver.title[:80])
    print("source_len:", len(driver.page_source))

    known = {}
    harvest_source(driver.page_source, known)
    print("source comments:", len(known))

    # try clicking comment controls
    clicked = driver.execute_script(
        """
        const out = [];
        for (const node of document.querySelectorAll('div[role="button"], span[role="button"], div[aria-label], span[aria-label]')) {
          const label = (node.getAttribute('aria-label') || '').toLowerCase();
          const text = (node.innerText || '').trim().toLowerCase();
          if (label.includes('comment') || text === 'comment' || text.includes('comments')
              || label.includes('تعليق') || text === 'تعليق') {
            try { (node.closest('[role="button"]') || node).click(); out.push(label || text); } catch (error) {}
            if (out.length >= 3) break;
          }
        }
        return out;
        """
    )
    print("clicked:", json.dumps(clicked, ensure_ascii=False))
    time.sleep(4)

    requests = [r for r in driver.requests if "/api/graphql" in r.url]
    print("graphql requests:", len(requests))
    for request in requests[-8:]:
        body = request.body.decode("utf-8", "replace") if request.body else ""
        parsed = parse_qs(body)
        doc_id = (parsed.get("doc_id") or [""])[0]
        variables = (parsed.get("variables") or [""])[0]
        text = _decode_body(request.response.body) if request.response is not None else ""
        print("----")
        print("doc_id:", doc_id)
        print("vars:", variables[:200])
        print("len:", len(text), "| body_text:", text.count('"body":{"text"'), "| cri:", text.count("comment_rendering_instance"), "| comments:", text.count('"comments"'))
        if text:
            print("head:", text[:200].replace("\n", " "))

    harvest(driver, known)
    print("after harvest:", len(known))
finally:
    driver.quit()
