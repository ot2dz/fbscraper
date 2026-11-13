import json
import os
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from app.comments_runner import harvest, harvest_source
from fb_graphql_scraper.base.base_page import BasePage

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
        const nodes = [...document.querySelectorAll('div[role="button"], span[role="button"]')];
        for (const node of nodes) {
          const text = (node.innerText || '').trim();
          if (/^\\d+\\s+comments?$/i.test(text)) { node.click(); return; }
        }
        """
    )
    time.sleep(3)
    clicked = driver.execute_script(
        """
        const nodes = [...document.querySelectorAll('div[role="button"], span[role="button"]')];
        for (const node of nodes) {
          const text = (node.innerText || '').trim().toLowerCase();
          if (text === 'most relevant') {
            const target = node.closest('[role="button"]') || node;
            target.click();
            return text;
          }
        }
        return null;
        """
    )
    print("filter clicked:", clicked)
    time.sleep(2)
    items = driver.execute_script(
        """
        const out = [];
        for (const node of document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"]')) {
          const text = (node.innerText || '').trim();
          if (text) out.push(text);
        }
        return [...new Set(out)];
        """
    )
    print("menu items:", json.dumps(items, ensure_ascii=False))

    for label in ("All comments", "كل التعليقات", "Tous les commentaires"):
        if label.lower() in [item.split("\n")[0].strip().lower() for item in items]:
            clicked_label = driver.execute_script(
                """
                const label = arguments[0].toLowerCase();
                for (const node of document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"]')) {
                  const first = (node.innerText || '').split('\\n')[0].trim().toLowerCase();
                  if (first === label) { node.click(); return first; }
                }
                return null;
                """,
                label,
            )
            print("clicked:", clicked_label)
            break
    time.sleep(5)
    harvest(driver, known)
    harvest_source(driver.page_source, known)
    print("after switch:", len(known), "graphql:", len([r for r in driver.requests if "/api/graphql" in r.url]))

    for index in range(6):
        driver.execute_script(
            """
            const dialog = document.querySelector('div[role="dialog"]');
            const root = dialog || document.body;
            for (const el of root.querySelectorAll('*')) {
              if (el.scrollHeight > el.clientHeight + 40 && el.clientHeight > 80) el.scrollTop = el.scrollHeight;
            }
            """
        )
        time.sleep(2)
        harvest(driver, known)
        harvest_source(driver.page_source, known)
        print(f"round {index + 1}: {len(known)} comments")
finally:
    driver.quit()
