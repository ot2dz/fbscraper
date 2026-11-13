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

    clicked = driver.execute_script(
        """
        const nodes = [...document.querySelectorAll('div[role="button"], span[role="button"]')];
        for (const node of nodes) {
          const text = (node.innerText || '').trim();
          if (/^\\d+\\s+comments?$/i.test(text)) { node.click(); return text; }
        }
        return null;
        """
    )
    print("opened dialog:", clicked)
    time.sleep(3)

    filter_clicked = driver.execute_script(
        """
        const nodes = [...document.querySelectorAll('div[role="button"], span[role="button"]')];
        for (const node of nodes) {
          const text = (node.innerText || '').trim().toLowerCase();
          if (text === 'most relevant' || text === 'الأكثر صلة' || text === 'les plus pertinents') {
            node.click(); return text;
          }
        }
        return null;
        """
    )
    print("clicked filter:", filter_clicked)
    time.sleep(2)
    menu = driver.execute_script(
        """
        const out = [];
        for (const node of document.querySelectorAll('div[role="menuitem"], div[role="menuitemradio"], div[role="button"]')) {
          const text = (node.innerText || '').trim();
          if (text && text.length < 40) out.push(text);
        }
        return [...new Set(out)].slice(0, 25);
        """
    )
    print("menu:", json.dumps(menu, ensure_ascii=False))

    all_clicked = driver.execute_script(
        """
        const nodes = [...document.querySelectorAll('div[role="menuitem"], div[role="menuitemradio"], div[role="button"]')];
        for (const node of nodes) {
          const text = (node.innerText || '').trim().toLowerCase();
          if (text === 'all comments' || text === 'كل التعليقات' || text === 'tous les commentaires') {
            node.click(); return text;
          }
        }
        return null;
        """
    )
    print("clicked all comments:", all_clicked)
    time.sleep(4)
    harvest(driver, known)
    harvest_source(driver.page_source, known)
    graphql = len([r for r in driver.requests if "/api/graphql" in r.url])
    print("after filter:", len(known), "comments | graphql:", graphql)

    for index in range(5):
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
        graphql = len([r for r in driver.requests if "/api/graphql" in r.url])
        print(f"round {index + 1}: {len(known)} comments | graphql={graphql}")
finally:
    driver.quit()
