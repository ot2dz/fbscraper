import json
import os
import sys

from app.comments_runner import _extract_comment, _walk

path = os.path.join(os.environ["TEMP"], "fb_post_source.html")
source = open(path, encoding="utf-8").read()

decoder = json.JSONDecoder()
found = []
index = 0
while True:
    position = source.find('{"__typename":"Comment"', index)
    if position == -1:
        break
    try:
        obj, end = decoder.raw_decode(source[position:])
    except ValueError:
        index = position + 1
        continue
    _walk(obj, found)
    index = position + end

unique = {}
for comment in found:
    if comment["comment_id"] and comment["text"].strip():
        unique[comment["comment_id"]] = comment

print("parsed objects:", len(found), "unique comments:", len(unique))
for comment in list(unique.values())[:8]:
    print("-", comment["author"], "|", comment["likes"], "|", comment["created_time"], "|", comment["text"][:70].replace("\n", " "))
