"""Browser-driven Cobalt downloader.

This intentionally uses the public Cobalt web UI rather than Cobalt's API:
GitHub Actions launches Chrome, opens cobalt.tools, submits the YouTube URL,
and waits for the browser download to land in the runner workspace.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import quote


_COBALT_URL = os.environ.get("DBYT_COBALT_URL", "https://cobalt.tools/")
_CHROME_BINARY = os.environ.get("DBYT_CHROME_BINARY", "/usr/bin/google-chrome")


def _wait_for_download(download_dir: Path, timeout: int = 180) -> Path:
    deadline = time.monotonic() + timeout
    last_candidates: list[Path] = []

    while time.monotonic() < deadline:
        partials = list(download_dir.glob("*.crdownload")) + list(download_dir.glob("*.tmp"))
        candidates = [
            path
            for path in download_dir.iterdir()
            if path.is_file() and path.suffix.lower() not in {".crdownload", ".tmp", ".part"}
        ]
        candidates = [path for path in candidates if path.stat().st_size > 0]
        if candidates and not partials:
            return max(candidates, key=lambda path: path.stat().st_mtime)
        last_candidates = candidates
        time.sleep(1)

    names = ", ".join(path.name for path in last_candidates) or "none"
    raise TimeoutError(f"Cobalt browser download timed out; completed files: {names}")


def _configure_chrome(download_dir: Path):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.binary_location = _CHROME_BINARY
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    )
    options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(download_dir.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    return webdriver.Chrome(options=options)


def _submit_in_ui(driver, youtube_url: str) -> None:
    """Use the visible Cobalt UI as a fallback when hash autoplay did not start."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait

    wait = WebDriverWait(driver, 25)
    inputs = wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, "input"))
    text_input = None
    for element in inputs:
        input_type = (element.get_attribute("type") or "").lower()
        placeholder = (element.get_attribute("placeholder") or "").lower()
        if input_type in {"text", "url", "search", ""} or "link" in placeholder:
            text_input = element
            break
    if text_input is None:
        raise RuntimeError("Cobalt input field was not found")

    text_input.click()
    text_input.send_keys(Keys.CONTROL, "a")
    text_input.send_keys(youtube_url)
    text_input.send_keys(Keys.ENTER)

    # Some revisions expose a separate "download" button after validating the URL.
    def click_download_button(d):
        buttons = d.find_elements(By.TAG_NAME, "button")
        for button in buttons:
            label = " ".join(
                part
                for part in (
                    button.text,
                    button.get_attribute("aria-label"),
                    button.get_attribute("title"),
                )
                if part
            ).lower()
            if "download" in label and button.is_enabled() and button.is_displayed():
                button.click()
                return True
        return False

    click_download_button(driver)


def download_via_browser(url: str, out_dir: Path, timeout: int = 180) -> Path:
    """Download a public YouTube video through cobalt.tools in real Chrome."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Keep this run isolated so we can reliably identify the new browser file.
    for path in out_dir.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)

    driver = _configure_chrome(out_dir)
    try:
        # Cobalt officially supports URL-prefill through the hash fragment and
        # automatically starts the save flow from that link.
        target = f"{_COBALT_URL}#{quote(url, safe=':/?=&%_-.,') }"
        driver.get(target)

        try:
            result = _wait_for_download(out_dir, timeout=25)
        except TimeoutError:
            # If a site revision does not autoplay from the fragment, use the
            # actual form/button just like a human visitor.
            _submit_in_ui(driver, url)
            result = _wait_for_download(out_dir, timeout)

        if result.stat().st_size < 50_000:
            raise RuntimeError(
                f"Cobalt returned an unexpectedly small file: {result.name} ({result.stat().st_size} bytes)"
            )

        # Normalise the workspace filename while preserving the real extension.
        safe_ext = re.sub(r"[^a-z0-9]", "", result.suffix.lower().lstrip(".")) or "mp4"
        destination = out_dir / f"source.{safe_ext}"
        shutil.move(str(result), str(destination))
        return destination
    finally:
        driver.quit()


__all__ = ["download_via_browser"]
