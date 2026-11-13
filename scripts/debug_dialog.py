import json
import os
import sys
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from app.comments_runner import CLICK_COMMENTS_SCRIPT, harvest, harvest_source
from fb_graphql_scraper.base.base_page import BasePage

url = sys.argv[1] if len(sys.argv) > 1 else "1118927064107626"
if not url.startswith("http"):
    url = "https://www.facebook.com/" + url

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get(url)
    time.sleep(8)
    known = {}
    harvest_source(driver.page_source, known)
    print("initial source comments:", len(known))
    clicked = driver.execute_script(CLICK_COMMENTS_SCRIPT)
    print("clicked comments button:", clicked)
    time.sleep(4)
    print("dialog:", driver.execute_script("return !!document.querySelector('div[role=\"dialog\"]');"))
    buttons = driver.execute_script(
        """
        const out = [];
        for (const node of document.querySelectorAll('div[role="button"], span[role="button"]')) {
          const text = (node.innerText || '').trim();
          if (text && text.length < 60) out.push(text);
        }
        return [...new Set(out)].slice(0, 60);
        """
    )
    print("buttons:", json.dumps(buttons, ensure_ascii=False))
    for index in range(4):
        clicked = driver.execute_script(CLICK_COMMENTS_SCRIPT)
        driver.execute_script(
            "const d=document.querySelector('div[role=\"dialog\"]'); if(d){d.scrollTop=d.scrollHeight;} else {window.scrollTo(0,document.body.scrollHeight);}"
        )
        time.sleep(2)
        harvest(driver, known)
        harvest_source(driver.page_source, known)
        print(f"round {index + 1}: {len(known)} comments, clicked={clicked}, graphql={len([r for r in driver.requests if '/api/graphql' in r.url])}")
finally:
    driver.quit()
