# -*- coding:utf-8 -*-
import os
from urllib.parse import quote, unquote, urlparse

from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service


def _seleniumwire_options():
    """Route the browser through FB_PROXY (upstream proxy for selenium-wire)."""
    proxy = os.environ.get("FB_PROXY")
    if not proxy:
        return {}
    parsed = urlparse(proxy if "://" in proxy else f"http://{proxy}")
    if not parsed.hostname:
        return {}
    scheme = parsed.scheme or "http"
    auth = ""
    if parsed.username:
        password = unquote(parsed.password or "")
        auth = f"{quote(unquote(parsed.username), safe='')}:{quote(password, safe='')}@"
    address = f"{scheme}://{auth}{parsed.hostname}:{parsed.port or 8080}"
    return {"proxy": {"http": address, "https": address, "no_proxy": "localhost,127.0.0.1"}}


class BasePage:
    def __init__(self, driver_path: str, open_browser: bool = False):
        chrome_options = self._build_options(open_browser)
        service = Service(driver_path)
        self.driver = webdriver.Chrome(
            service=service,
            options=chrome_options,
            seleniumwire_options=_seleniumwire_options(),
        )
        if open_browser:
            self.driver.maximize_window()
        else:
            self.driver.set_window_size(1920, 1080)

    @staticmethod
    def _build_options(open_browser: bool) -> webdriver.ChromeOptions:
        options = webdriver.ChromeOptions()
        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin:
            options.binary_location = chrome_bin
        options.add_argument("--disable-blink-features")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        if not open_browser:
            options.add_argument("--headless=new")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        return options
