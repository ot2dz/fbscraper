import json
import os
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from app.comments_runner import harvest, harvest_source
from fb_graphql_scraper.base.base_page import BasePage

SCROLL_ALL = """
const dialog = document.querySelector('div[role="dialog"]');
const root = dialog || document.body;
let scrolled = 0;
for (const el of root.querySelectorAll('*')) {
  if (el.scrollHeight > el.clientHeight + 40 && el.clientHeight > 80) {
    el.scrollTop = el.scrollHeight;
    scrolled += 1;
  }
}
window.scrollTo(0, document.body.scrollHeight);
return scrolled;
"""

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/1118927064107626")
    time.sleep(8)
    known = {}
    harvest_source(driver.page_source, known)
    print("initial:", len(known))
    driver.execute_script(
        """
        for (const node of document.querySelectorAll('div[role="button"], span[role="button"]')) {
          const text = (node.innerText || '').trim();
          if (/^\\d+\\s+comments?$/i.test(text)) { node.click(); break; }
        }
        """
    )
    time.sleep(4)
    for index in range(6):
        scrolled = driver.execute_script(SCROLL_ALL)
        time.sleep(2)
        buttons = driver.execute_script(
            """
            const out = [];
            for (const node of document.querySelectorAll('div[role="button"], span[role="button"]')) {
              const text = (node.innerText || '').trim();
              if (text && text.length < 40 && /comment|reply|تعليق|رد/i.test(text)) out.push(text);
            }
            return [...new Set(out)].slice(0, 12);
            """
        )
        harvest(driver, known)
        harvest_source(driver.page_source, known)
        graphql = len([r for r in driver.requests if "/api/graphql" in r.url])
        print(f"round {index + 1}: {len(known)} comments | scrolled={scrolled} | graphql={graphql} | {json.dumps(buttons, ensure_ascii=False)}")
finally:
    driver.quit()
