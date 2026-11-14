import json
import os
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbreel_test")

from selenium.webdriver.common.by import By

from app.comments_runner import _decode_body, harvest, harvest_source
from fb_graphql_scraper.base.base_page import BasePage

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/reel/1107691808301702")
    time.sleep(10)

    candidates = driver.execute_script(
        """
        const out = [];
        for (const node of document.querySelectorAll('[aria-label]')) {
          const label = node.getAttribute('aria-label') || '';
          if (/comment|تعليق/i.test(label)) {
            const rect = node.getBoundingClientRect();
            out.push({label: label.slice(0, 60), tag: node.tagName, role: node.getAttribute('role'),
                      x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)});
          }
        }
        return out.slice(0, 10);
        """
    )
    print("candidates:", json.dumps(candidates, ensure_ascii=False))

    elements = driver.find_elements(By.CSS_SELECTOR, '[aria-label*="omment"], [aria-label*="تعليق"]')
    print("selenium elements:", len(elements))
    for index, element in enumerate(elements[:4]):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)
            element.click()
            print("clicked", index, element.get_attribute("aria-label"))
            time.sleep(4)
        except Exception as exc:  # noqa: BLE001
            print("click failed", index, str(exc)[:100])

    print("dialogs:", driver.execute_script("return document.querySelectorAll('div[role=\"dialog\"]').length;"))
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
    for request in requests[-6:]:
        body = request.body.decode("utf-8", "replace") if request.body else ""
        text = _decode_body(request.response.body) if request.response is not None else ""
        print("doc:", body[:60].replace("\n", " "), "| len:", len(text), "| body_text:", text.count('"body":{"text"'), "| cri:", text.count("comment_rendering_instance"))

    known = {}
    harvest(driver, known)
    harvest_source(driver.page_source, known)
    print("comments:", len(known))
finally:
    driver.quit()
