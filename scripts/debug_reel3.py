import json
import os
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbreel_test")

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from app.comments_runner import _decode_body, harvest, harvest_source
from fb_graphql_scraper.base.base_page import BasePage

REMOVE_DIALOGS = """
for (const node of document.querySelectorAll('div[role="dialog"]')) {
  node.remove();
}
return true;
"""

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/reel/1107691808301702")
    time.sleep(10)
    body = driver.find_element(By.TAG_NAME, "body")
    body.send_keys(Keys.ESCAPE)
    time.sleep(1)
    driver.execute_script(REMOVE_DIALOGS)
    time.sleep(1)

    elements = driver.find_elements(By.CSS_SELECTOR, '[aria-label*="omment"], [aria-label*="تعليق"]')
    print("comment elements:", len(elements))
    for element in elements[:3]:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.4)
            driver.execute_script("arguments[0].click();", element)
            print("clicked:", element.get_attribute("aria-label"))
            time.sleep(5)
        except Exception as exc:  # noqa: BLE001
            print("click err:", str(exc)[:120])

    driver.execute_script(REMOVE_DIALOGS)
    print("dialogs after:", driver.execute_script("return document.querySelectorAll('div[role=\"dialog\"]').length;"))
    print("buttons:", driver.execute_script(
        """
        const out = [];
        for (const node of document.querySelectorAll('div[role="button"], span[role="button"]')) {
          const t = (node.innerText || '').trim();
          if (t && t.length < 40) out.push(t);
        }
        return [...new Set(out)].slice(0, 30);
        """
    ))

    requests = [r for r in driver.requests if "/api/graphql" in r.url]
    print("graphql:", len(requests))
    for request in requests[-8:]:
        body_text = request.body.decode("utf-8", "replace") if request.body else ""
        text = _decode_body(request.response.body) if request.response is not None else ""
        print("doc:", body_text[:70].replace("\n", " "), "| len:", len(text), "| body:", text.count('"body":{"text"'), "| cri:", text.count("comment_rendering_instance"))

    known = {}
    harvest(driver, known)
    harvest_source(driver.page_source, known)
    print("comments:", len(known))
finally:
    driver.quit()
