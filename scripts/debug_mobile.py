import os
import time

os.environ["DATA_DIR"] = os.path.join(os.environ["TEMP"], "fbcomments_test")

from fb_graphql_scraper.base.base_page import BasePage

page = BasePage(driver_path=None, open_browser=False)
driver = page.driver
try:
    for url in ("https://mbasic.facebook.com/1118927064107626", "https://m.facebook.com/1118927064107626"):
        driver.get(url)
        time.sleep(6)
        print("====", url)
        print("final:", driver.current_url)
        print("title:", driver.title)
        print("len:", len(driver.page_source))
        text = driver.find_element("tag name", "body").text
        print("text head:", text[:400].replace("\n", " | "))
        print("has_more:", "See more" in text or "المزيد" in text)
finally:
    driver.quit()
