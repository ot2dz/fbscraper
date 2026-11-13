import os
import re
import time

import brotli

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from fb_graphql_scraper.base.base_page import BasePage


def decode(raw):
    if not raw:
        return ""
    try:
        if raw[:4] == b"\x28\xb5\x2f\xfd":
            import zstandard

            return zstandard.ZstdDecompressor().decompress(raw, max_output_size=128 * 1024 * 1024).decode("utf-8", "replace")
        if raw[:2] == b"\x1f\x8b":
            import gzip

            return gzip.decompress(raw).decode("utf-8", "replace")
        text = raw.decode("utf-8")
        return text
    except UnicodeDecodeError:
        try:
            return brotli.decompress(raw).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return ""


page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/1118927064107626")
    time.sleep(8)
    js_requests = [r for r in driver.requests if ".js" in r.url and r.response is not None]
    print("js requests:", len(js_requests))
    total = 0
    hits = []
    for request in js_requests:
        text = decode(request.response.body)
        total += len(text)
        for needle in ("CometCommentsListPaginationQuery", "comments_list", "CommentsListPagination", "commentsAfterCursor"):
            if needle in text:
                hits.append((needle, request.url, text.find(needle)))
    print("total js chars:", total)
    print("hits:", hits[:10])
    if hits:
        needle, url, position = hits[0]
        for request in js_requests:
            if request.url == url:
                text = decode(request.response.body)
                print("CTX:", text[max(0, position - 300):position + 500].replace("\n", " "))
                break
finally:
    driver.quit()
