import json
import os
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbreel_test")

from app.comments_runner import _decode_body, harvest, harvest_source
from fb_graphql_scraper.base.base_page import BasePage

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/watch/?v=1107691808301702")
    time.sleep(10)
    print("url:", driver.current_url)
    driver.execute_script(
        """
        for (const node of document.querySelectorAll('div[role="dialog"]')) {
          const text = (node.innerText || '').toLowerCase();
          if (text.includes('log in') || text.includes('create new account')) node.remove();
        }
        """
    )
    time.sleep(1)

    def dump(tag):
        data = driver.execute_script(
            """
            const out = [];
            for (const node of document.querySelectorAll('div[role="button"], span[role="button"], a[role="link"]')) {
              const t = (node.innerText || '').trim();
              if (t && t.length < 45) out.push(t);
            }
            return [...new Set(out)].slice(0, 40);
            """
        )
        print(tag, json.dumps(data, ensure_ascii=False))

    dump("buttons before:")
    clicked = driver.execute_script(
        """
        const out = [];
        for (const node of document.querySelectorAll('div[role="button"], span[role="button"], a[role="link"]')) {
          const t = (node.innerText || '').trim();
          if (/^(view|عرض).*(comment|تعليق)/i.test(t) || /^\\d+\\s*(comments?|تعليق)/i.test(t)
              || /^view more comments$/i.test(t) || /^عرض المزيد من التعليقات$/i.test(t)) {
            try { (node.closest('[role="button"]') || node).click(); out.push(t); } catch (error) {}
          }
        }
        return out;
        """
    )
    print("clicked:", json.dumps(clicked, ensure_ascii=False))
    time.sleep(5)
    dump("buttons after:")

    requests = [r for r in driver.requests if "/api/graphql" in r.url]
    print("graphql:", len(requests))
    for request in requests[-10:]:
        body = request.body.decode("utf-8", "replace") if request.body else ""
        text = _decode_body(request.response.body) if request.response is not None else ""
        print("doc:", body[:60].replace("\n", " "), "| len:", len(text), "| body_text:", text.count('"body":{"text"'), "| cri:", text.count("comment_rendering_instance"))

    known = {}
    harvest(driver, known)
    harvest_source(driver.page_source, known)
    print("comments:", len(known))

    # try scrolling for inline comments
    for index in range(3):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        harvest(driver, known)
        harvest_source(driver.page_source, known)
        print("scroll", index + 1, "comments:", len(known))
finally:
    driver.quit()
