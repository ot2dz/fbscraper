import json
import os
import sys
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from fb_graphql_scraper.base.base_page import BasePage

url = sys.argv[1] if len(sys.argv) > 1 else "1118927064107626"
if not url.startswith("http"):
    url = "https://www.facebook.com/" + url
page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get(url)
    time.sleep(10)
    print("final_url:", driver.current_url)
    print("title:", driver.title)
    print("source_len:", len(driver.page_source))
    graphql = [r for r in driver.requests if "/api/graphql" in r.url]
    print("graphql_requests:", len(graphql))
    for request in graphql[:12]:
        body = ""
        if request.response is not None:
            try:
                body = request.response.body.decode("utf-8", "replace")[:120]
            except Exception:  # noqa: BLE001
                body = "<no body>"
        print("  -", request.method, request.url[:100], "|", body.replace("\n", " ")[:100])
    buttons = driver.execute_script(
        """
        const out = [];
        for (const node of document.querySelectorAll('div[role="button"], span[role="button"]')) {
          const text = (node.innerText || '').trim();
          if (text && text.length < 60) out.push(text);
        }
        return [...new Set(out)].slice(0, 40);
        """
    )
    print("buttons:", json.dumps(buttons, ensure_ascii=False))
    print("has_comment_word:", "comment" in driver.page_source.lower() or "تعليق" in driver.page_source)
    source = driver.page_source
    print("typename_comment:", source.count('"__typename":"Comment"'))
    print("body_text:", source.count('"body":{"text"'))
    print("comment_list:", source.count("comment_list"))
    out_path = os.path.join(os.environ["TEMP"], "fb_post_source.html")
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(source)
    print("saved:", out_path)
finally:
    driver.quit()
