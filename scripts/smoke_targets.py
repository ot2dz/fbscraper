import os

os.environ.setdefault("DATA_DIR", os.path.join(os.environ["TEMP"], "fbtargets"))

from app.scraper_runner import normalize_target

cases = {
    "https://www.facebook.com/AZmaisondedeco": "AZmaisondedeco",
    "https://www.facebook.com/AZmaisondedeco/": "AZmaisondedeco",
    "https://m.facebook.com/AZmaisondedeco?locale=fr_FR": "AZmaisondedeco",
    "https://web.facebook.com/AZmaisondedeco/posts/12345": "AZmaisondedeco",
    "https://mbasic.facebook.com/AZmaisondedeco": "AZmaisondedeco",
    "facebook.com/AZmaisondedeco": "AZmaisondedeco",
    "www.facebook.com/AZmaisondedeco": "AZmaisondedeco",
    "@AZmaisondedeco": "AZmaisondedeco",
    "AZmaisondedeco": "AZmaisondedeco",
    "100088686736411": "100088686736411",
    "https://www.facebook.com/profile.php?id=100088686736411": "100088686736411",
    "https://www.facebook.com/profile.php?id=100088686736411&mibextid=abc": "100088686736411",
    "https://www.facebook.com/people/Rawas-Gifts/100088686736411/": "100088686736411",
    "https://www.facebook.com/people/%D8%B1%D9%88%D8%A7%D8%B3/100088686736411": "100088686736411",
    "https://www.facebook.com/pages/Rawas-Gifts/100088686736411": "100088686736411",
    "https://www.facebook.com/pages/category/Gift-Shop/Rawas-100088686736411/": "100088686736411",
    "https://www.facebook.com/123456789": "123456789",
    "https://l.facebook.com/l.php?u=https%3A%2F%2Fwww.facebook.com%2FAZmaisondedeco&h=abc": "AZmaisondedeco",
    "https://www.facebook.com/AZmaisondedeco?mibextid=LQQJ4d&ref=share": "AZmaisondedeco",
    "https://fb.com/AZmaisondedeco": "AZmaisondedeco",
    "https://www.facebook.com/share/AbCdEf123/": "https://www.facebook.com/share/AbCdEf123/",
    "https://fb.me/AbCdEf123": "https://fb.me/AbCdEf123",
    "https://www.facebook.com/AZmaisondedeco/photos/a.1/2": "AZmaisondedeco",
}

failures = 0
for raw, expected in cases.items():
    try:
        got = normalize_target(raw)
    except Exception as exc:  # noqa: BLE001
        got = f"ERROR: {exc}"
    ok = got == expected
    failures += 0 if ok else 1
    print(("OK  " if ok else "FAIL"), raw, "->", got, "" if ok else f"(expected {expected})")

bad = [
    "https://www.facebook.com/groups/123456",
    "https://www.facebook.com/watch/?v=123",
    "https://www.facebook.com/reel/123",
    "https://example.com/page",
    "https://www.facebook.com/",
    "",
    "مرحبا",
]
for raw in bad:
    try:
        got = normalize_target(raw)
        print("FAIL expected error:", raw, "->", got)
        failures += 1
    except ValueError as exc:
        print("OK   rejected:", raw, "->", exc)

print("failures:", failures)
