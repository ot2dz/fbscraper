# -*- coding: utf-8 -*-
import argparse
import json
import sys

import fb_graphql_scraper.facebook_graphql_scraper as scraper_module
from fb_graphql_scraper.facebook_graphql_scraper import FacebookGraphqlScraper as fb_graphql_scraper

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def stop_after_posts(spider, posts_limit):
    """Make the scraper stop as soon as posts_limit posts were parsed."""
    original = scraper_module.compare_timestamp

    def patched(timestamp, days_limit, display_progress=True):
        collected = len(spider.requests_parser.collect_posts())
        if collected >= posts_limit:
            print(f"Reached posts limit ({collected} >= {posts_limit}), stopping.")
            return True
        return original(timestamp=timestamp, days_limit=days_limit, display_progress=display_progress)

    scraper_module.compare_timestamp = patched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", help="Facebook page/username/user id")
    parser.add_argument("--days", type=int, default=7, help="only keep posts newer than N days")
    parser.add_argument("--posts", type=int, default=0, help="stop after N posts (0 = no limit)")
    parser.add_argument("--driver", default=None, help="chromedriver path (None = auto via Selenium Manager)")
    parser.add_argument("--browser", action="store_true", help="show the browser window")
    parser.add_argument("--out", default="result.json")
    args = parser.parse_args()

    days_limit = max(args.days, 3650) if args.posts else args.days

    spider = fb_graphql_scraper(driver_path=args.driver, open_browser=args.browser)
    try:
        if args.posts:
            stop_after_posts(spider, args.posts)
        res = spider.get_user_posts(
            fb_username_or_userid=args.target,
            days_limit=days_limit,
            display_progress=True,
        )
    finally:
        try:
            spider.page_optional.quit_driver()
        except Exception:
            pass

    data = res.get("data", [])
    if args.posts:
        data = data[: args.posts]
        res["data"] = data

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2, default=str)

    print("=== profile:", res.get("profile"))
    print("=== posts:", len(data))
    for p in data[:5]:
        print(
            p.get("published_date2"),
            p.get("reaction_count.count"),
            "likes /",
            p.get("comment_rendering_instance.comments.total_count"),
            "comments /",
            p.get("share_count.count"),
            "shares |",
            str(p.get("context") or "")[:60].replace("\n", " "),
        )
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    sys.exit(main())
