import json
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
        return raw.decode("utf-8")
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
    pattern = re.compile(r'__d\("([A-Za-z0-9_]+)_facebookRelayOperation",\[\],\(function\([^)]*\)\{[a-z]\.exports="(\d+)"\}')
    found = {}
    for request in [r for r in driver.requests if ".js" in r.url and r.response is not None]:
        text = decode(request.response.body)
        for match in pattern.finditer(text):
            name, doc_id = match.group(1), match.group(2)
            if "Comment" in name or "Feedback" in name or "Reply" in name:
                found[name] = doc_id
    for name in sorted(found):
        print(f"{name} -> {found[name]}")
    out = os.path.join(os.environ["TEMP"], "fb_comment_docids.json")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(found, handle, ensure_ascii=False, indent=2)
    print("saved:", out)
finally:
    driver.quit()
