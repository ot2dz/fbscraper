import json
import os
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from fb_graphql_scraper.base.base_page import BasePage

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/1118927064107626")
    time.sleep(8)
    info = driver.execute_script(
        """
        const labels = [];
        for (const node of document.querySelectorAll('[aria-label]')) {
          const label = node.getAttribute('aria-label');
          if (label && label.length < 40) labels.push(label);
        }
        const dialog = document.querySelector('div[role="dialog"]');
        return {
          labels: [...new Set(labels)].slice(0, 50),
          dialog: dialog ? dialog.innerText.slice(0, 300) : null,
          html: dialog ? dialog.innerHTML.slice(0, 600) : null,
        };
        """
    )
    print("labels:", json.dumps(info["labels"], ensure_ascii=False))
    print("dialog text:", info["dialog"])
    print("dialog html:", (info["html"] or "")[:600])
finally:
    driver.quit()
