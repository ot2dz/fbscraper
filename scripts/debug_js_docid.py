import os
import re
import time

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
        return raw.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    driver.get("https://www.facebook.com/1118927064107626")
    time.sleep(8)
    hits = 0
    for request in list(driver.requests):
        if ".js" not in request.url or request.response is None:
            continue
        text = decode(request.response.body)
        if "CometCommentsListPaginationQuery" not in text:
            continue
        hits += 1
        position = text.find("CometCommentsListPaginationQuery")
        print("URL:", request.url[:100])
        print("CTX:", text[max(0, position - 150):position + 350].replace("\n", " "))
        for match in re.finditer(r'id:"(\d{10,})"', text):
            print("  doc_id candidate:", match.group(1))
        if hits >= 3:
            break
    print("hits:", hits)
finally:
    driver.quit()
