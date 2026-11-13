import json
import os
import re

source = open(os.path.join(os.environ["TEMP"], "fb_post_source.html"), encoding="utf-8").read()
print("application/json tags:", source.count('type="application/json"'))
print("data-sjs tags:", source.count("data-sjs"))
for match in re.finditer(r'<script type="application/json"[^>]*>', source):
    tag = match.group(0)
    print("TAG:", tag[:200])
    break

from bs4 import BeautifulSoup

soup = BeautifulSoup(source, "html.parser")
blocks = soup.find_all("script", {"type": "application/json"})
print("blocks:", len(blocks))
found = []
for block in blocks:
    raw = block.string or block.get_text() or ""
    try:
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        print("parse fail:", str(exc)[:60], "len", len(raw))
        continue
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "body" in node and isinstance(node.get("body"), dict) and isinstance(node["body"].get("text"), str):
                found.append(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
print("candidate comments:", len(found))
if found:
    first = found[0]
    print("keys:", sorted(first.keys()))
    print("id:", first.get("id"))
    print("body:", first["body"]["text"][:80])
    print("author:", (first.get("author") or {}).get("name"))
    print("created:", first.get("created_time"))
