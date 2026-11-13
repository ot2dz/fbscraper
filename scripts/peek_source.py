import os

source = open(os.path.join(os.environ["TEMP"], "fb_post_source.html"), encoding="utf-8").read()
needle = '{"__typename":"Comment"'
first = source.find(needle)
print(source[first:first + 900])
print("---- second ----")
second = source.find(needle, first + 10)
print(source[second:second + 600])
