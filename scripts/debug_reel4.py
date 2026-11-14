import json
import os
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbreel_test")

from app.comments_runner import _decode_body, harvest, harvest_source
from fb_graphql_scraper.base.base_page import BasePage

for url in (
    "https://www.facebook.com/watch/?v=1107691808301702",
    "https://www.facebook.com/reel/1107691808301702/?comment_id=",
):
    page = BasePage(driver_path=None, open_browser=False)
    driver = page.driver
    try:
        driver.get(url)
        time.sleep(10)
        print("====", url)
        print("final:", driver.current_url)
        print("source_len:", len(driver.page_source))
        known = {}
        harvest_source(driver.page_source, known)
        print("source comments:", len(known))

        # remove login overlay only
        driver.execute_script(
            """
            for (const node of document.querySelectorAll('div[role="dialog"]')) {
              const text = (node.innerText || '').toLowerCase();
              if (text.includes('log in') || text.includes('create new account') || text.includes('تسجيل الدخول')) node.remove();
            }
            return true;
            """
        )
        time.sleep(1)

        candidates = driver.execute_script(
            """
            const out = [];
            for (const node of document.querySelectorAll('[aria-label]')) {
              const label = node.getAttribute('aria-label') || '';
              if (/comment|تعليق/i.test(label)) out.push(label.slice(0, 50));
            }
            return [...new Set(out)].slice(0, 8);
            """
        )
        print("comment labels:", json.dumps(candidates, ensure_ascii=False))

        clicked = driver.execute_script(
            """
            for (const node of document.querySelectorAll('[aria-label]')) {
              const label = node.getAttribute('aria-label') || '';
              if (/comment|تعليق/i.test(label)) {
                node.click();
                return label;
              }
            }
            return null;
            """
        )
        print("clicked:", clicked)
        time.sleep(5)

        requests = [r for r in driver.requests if "/api/graphql" in r.url]
        interesting = 0
        for request in requests:
            text = _decode_body(request.response.body) if request.response is not None else ""
            if '"body":{"text"' in text or "comment_rendering_instance" in text:
                interesting += 1
        print("graphql:", len(requests), "with comments:", interesting)

        harvest(driver, known)
        harvest_source(driver.page_source, known)
        print("comments:", len(known))
    finally:
        driver.quit()
