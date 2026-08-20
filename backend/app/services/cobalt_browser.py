"""Browser-driven multi-site media downloader.

GitHub Actions launches Chrome, visits a list of browser download sites, submits
 the YouTube URL, and accepts the first real media file that lands in the
 runner's download directory. Sites are isolated so one broken downloader does
not prevent the next one from being tried.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import quote

_CHROME_BINARY = os.environ.get("DBYT_CHROME_BINARY", "/usr/bin/google-chrome")
_DEFAULT_TIMEOUT = 90
_MIN_BYTES = 50_000

# Ordered by current preference. Community/public instances and simple
# paste-and-download sites are kept as fallbacks because availability changes.
_SITES = [
    ("cobalt", "https://cobalt.tools/"),
    ("youtubegrab", "https://youtubegrab.com/"),
    ("notube", "https://notube.video/"),
    ("notube_sarl", "https://notube.sarl/"),
    ("ytgot", "https://ytgot.com/"),
    ("savetube", "https://savetube.online/"),
    ("cobalt_meowing", "https://cobalt.meowing.de/"),
    ("y2down", "https://y2down.cc/"),
    ("y2meta", "https://y2meta.tube/"),
    ("yt5s", "https://yt5s.biz/"),
    ("ddownr", "https://ddownr.com/"),
    ("pastedownload", "https://pastedownload.com/"),
]


def _site_list() -> list[tuple[str, str]]:
    """Allow a custom comma/newline-separated site list for emergency overrides."""
    raw = os.environ.get("DBYT_BROWSER_SITES", "").strip()
    if not raw:
        return list(_SITES)
    pairs: list[tuple[str, str]] = []
    for index, value in enumerate(re.split(r"[,\n]", raw), start=1):
        url = value.strip()
        if not url:
            continue
        name = re.sub(r"[^a-z0-9]+", "_", url.lower()).strip("_") or f"site_{index}"
        pairs.append((name, url if url.endswith("/") else url + "/"))
    return pairs or list(_SITES)


def _clear_download_dir(download_dir: Path) -> None:
    for path in download_dir.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def _wait_for_download(download_dir: Path, timeout: int = _DEFAULT_TIMEOUT) -> Path:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        partials = list(download_dir.glob("*.crdownload")) + list(download_dir.glob("*.tmp"))
        candidates = [
            path
            for path in download_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() not in {".crdownload", ".tmp", ".part", ".json", ".txt"}
            and path.stat().st_size >= _MIN_BYTES
        ]
        if candidates and not partials:
            return max(candidates, key=lambda path: path.stat().st_mtime)
        time.sleep(1)
    raise TimeoutError("No completed media download appeared before timeout")


def _configure_chrome(download_dir: Path):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.binary_location = _CHROME_BINARY
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1100")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
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
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Browser.setDownloadBehavior",
        {
            "behavior": "allow",
            "downloadPath": str(download_dir.resolve()),
            "eventsEnabled": True,
        },
    )
    return driver


def _visible_text(driver) -> str:
    try:
        return (driver.find_element("tag name", "body").text or "").lower()
    except Exception:
        return ""


def _pick_input(driver):
    from selenium.webdriver.common.by import By

    inputs = driver.find_elements(By.CSS_SELECTOR, "input")
    best = None
    for element in inputs:
        if not element.is_displayed() or not element.is_enabled():
            continue
        typ = (element.get_attribute("type") or "").lower()
        placeholder = (element.get_attribute("placeholder") or "").lower()
        aria = (element.get_attribute("aria-label") or "").lower()
        score = 0
        if typ in {"url", "text", "search", ""}:
            score += 2
        if any(word in placeholder for word in ("url", "link", "video", "paste", "youtube")):
            score += 5
        if any(word in aria for word in ("url", "link", "video", "paste", "youtube")):
            score += 5
        if score and (best is None or score > best[0]):
            best = (score, element)
    return best[1] if best else None


def _click_download(driver) -> bool:
    from selenium.webdriver.common.by import By

    controls = driver.find_elements(By.CSS_SELECTOR, "button, a, input[type='submit']")
    for control in controls:
        if not control.is_displayed() or not control.is_enabled():
            continue
        label = " ".join(
            part
            for part in (
                control.text,
                control.get_attribute("aria-label"),
                control.get_attribute("title"),
                control.get_attribute("value"),
                control.get_attribute("download"),
            )
            if part
        ).lower()
        if any(word in label for word in ("download", "convert", "get video", "save file", "mp4")):
            try:
                control.click()
                return True
            except Exception:
                continue
    return False


def _submit_site(driver, site_name: str, site_url: str, youtube_url: str) -> None:
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait

    # First try hash-prefill where supported, which avoids brittle selectors.
    driver.get(f"{site_url}#{quote(youtube_url, safe=':/?=&%_-.,')}")
    wait = WebDriverWait(driver, 20)
    try:
        field = wait.until(lambda d: _pick_input(d))
        field.click()
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(youtube_url)
        field.send_keys(Keys.ENTER)
    except Exception:
        # Some sites expose the URL only through a textarea/contenteditable.
        from selenium.webdriver.common.by import By
        areas = driver.find_elements(By.CSS_SELECTOR, "textarea, [contenteditable='true']")
        if areas:
            area = next((a for a in areas if a.is_displayed() and a.is_enabled()), None)
            if area is not None:
                area.click()
                area.send_keys(youtube_url)
                area.send_keys(Keys.ENTER)
        else:
            raise RuntimeError(f"{site_name}: input field not found")

    # Give the site a moment to populate format choices, then click a download
    # control. If it auto-downloads, this simply returns false and the waiter
    # below will pick up the file.
    time.sleep(2)
    if not _click_download(driver):
        time.sleep(2)
        _click_download(driver)


def _normalise_download(result: Path, out_dir: Path, site_name: str) -> Path:
    extension = re.sub(r"[^a-z0-9]", "", result.suffix.lower().lstrip(".")) or "mp4"
    destination = out_dir / f"source.{extension}"
    if destination.exists():
        destination.unlink()
    shutil.move(str(result), str(destination))
    (out_dir / "download-source.txt").write_text(site_name, encoding="utf-8")
    return destination


def download_via_browser(url: str, out_dir: Path, timeout: int = _DEFAULT_TIMEOUT) -> Path:
    """Try every configured browser downloader until one produces a media file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    for site_name, site_url in _site_list():
        _clear_download_dir(out_dir)
        driver = None
        try:
            print(f"[browser-downloader] trying {site_name}: {site_url}")
            driver = _configure_chrome(out_dir)
            _submit_site(driver, site_name, site_url, url)
            result = _wait_for_download(out_dir, timeout)
            if result.stat().st_size < _MIN_BYTES:
                raise RuntimeError(f"returned file is too small ({result.stat().st_size} bytes)")
            print(f"[browser-downloader] SUCCESS {site_name}: {result.name} ({result.stat().st_size} bytes)")
            return _normalise_download(result, out_dir, site_name)
        except Exception as exc:  # noqa: BLE001 - continue to next site
            message = str(exc).replace("\n", " ")[:300]
            errors.append(f"{site_name}: {message}")
            print(f"[browser-downloader] FAIL {site_name}: {message}")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    raise RuntimeError("All browser download sites failed: " + " | ".join(errors))


__all__ = ["download_via_browser"]
