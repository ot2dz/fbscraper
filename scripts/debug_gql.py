import json
import os
import time
from urllib.parse import parse_qs

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from fb_graphql_scraper.base.base_page import BasePage

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/1118927064107626")
    time.sleep(8)
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
    driver.execute_script(
        """
        const nodes = [...document.querySelectorAll('div[role="button"], span[role="button"]')];
        for (const node of nodes) {
          const text = (node.innerText || '').trim().toLowerCase();
          if (text === 'most relevant') { node.click(); return; }
        }
        """
    )
    time.sleep(2)
    driver.execute_script(
        """
        const nodes = [...document.querySelectorAll('div[role="menuitem"], div[role="menuitemradio"], div[role="button"]')];
        for (const node of nodes) {
          const text = (node.innerText || '').trim().toLowerCase();
          if (text === 'all comments') { node.click(); return; }
        }
        """
    )
    time.sleep(4)
    for index, request in enumerate([r for r in driver.requests if "/api/graphql" in r.url][-8:]):
        body = ""
        try:
            body = request.body.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        parsed = parse_qs(body)
        doc_id = (parsed.get("doc_id") or [""])[0]
        variables = (parsed.get("variables") or [""])[0]
        response_text = ""
        if request.response is not None:
            try:
                response_text = request.response.body.decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                pass
        print(f"[{index}] doc_id={doc_id} vars={variables[:160]}")
        print(f"    resp_len={len(response_text)} body_text={response_text.count(chr(34) + 'body' + chr(34) + ':{' + chr(34) + 'text')} comments={response_text.count('comment_list')}")
        print(f"    head={response_text[:150].replace(chr(10), ' ')}")
finally:
    driver.quit()
