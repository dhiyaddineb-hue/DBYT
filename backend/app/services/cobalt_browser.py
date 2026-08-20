"""Browser-driven multi-site video downloader.

DBYT uses a real Chromium session and a rotating list of public web download
pages. Each site gets the same workflow: open page -> paste YouTube URL ->
submit -> wait for a browser download. The first non-trivial media file wins.

This is intentionally UI-driven rather than calling third-party downloader APIs.
Only use it for media you are authorized to save.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import quote

_CHROME_BINARY = os.environ.get("DBYT_CHROME_BINARY", "/usr/bin/google-chrome")

# Large fallback pool. Availability changes frequently, so failures are expected
# and immediately advance to the next site. Some entries are mirrors/variants of
# the same service; keeping them increases resilience when a domain changes.
DEFAULT_SITES = (
    ("cobalt", "https://cobalt.tools/"),
    ("cobalt-community", "https://cobalt.meowing.de/"),
    ("cutyt", "https://www.cutyt.com/"),
    ("downloadclip", "https://www.downloadclip.pro/"),
    ("vid-save", "https://vid-save.com/yt-downloader"),
    ("savetube", "https://savetube.online/"),
    ("downloot", "https://downloot.net/youtube-video-downloader"),
    ("qvideos", "https://qvideos.org/"),
    ("vidogo", "https://vidogo.cc/"),
    ("openvideotools", "https://openvideotools.com/"),
    ("mp4yt", "https://mp4yt.com/"),
    ("9xbuddy", "https://9xbuddy.com/"),
    ("savefrom", "https://savefrom.net/"),
    ("y2mate", "https://www.y2mate.com/"),
    ("yt1s", "https://yt1s.com/"),
    ("ssvideodownloader", "https://ssvideodownloader.com/"),
    ("ytdown", "https://ytdown.to/"),
    ("seekin", "https://seekin.ai/"),
    ("tools-mart", "https://toolsmart.ai/"),
    ("mediamister", "https://www.mediamister.com/"),
    ("yt5s", "https://yt5s.biz/"),
    ("ytgot", "https://ytgot.com/"),
    ("notube", "https://notube.video/"),
    ("pastedownload", "https://pastedownload.com/"),
)

_VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".webm", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".ts", ".m2ts"
}
_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac"}
_IGNORED_EXTENSIONS = {".crdownload", ".tmp", ".part", ".html", ".htm", ".txt", ".json"}


def _sites() -> tuple[tuple[str, str], ...]:
    """Load an optional comma/newline-separated custom site list."""
    raw = os.environ.get("DBYT_DOWNLOADER_SITES", "").strip()
    if not raw:
        return DEFAULT_SITES

    parsed: list[tuple[str, str]] = []
    for index, item in enumerate(re.split(r"[,\n]", raw), 1):
        value = item.strip()
        if not value:
            continue
        if "|" in value:
            name, url = value.split("|", 1)
            parsed.append((name.strip() or f"custom-{index}", url.strip()))
        else:
            parsed.append((f"custom-{index}", value))
    return tuple(parsed) or DEFAULT_SITES


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
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    )
    options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
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


def _clear_download_dir(download_dir: Path) -> None:
    download_dir.mkdir(parents=True, exist_ok=True)
    for path in list(download_dir.iterdir()):
        if path.is_file():
            path.unlink(missing_ok=True)


def _media_files(download_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in download_dir.iterdir():
        if not path.is_file() or path.suffix.lower() in _IGNORED_EXTENSIONS:
            continue
        if path.suffix.lower() in _VIDEO_EXTENSIONS | _AUDIO_EXTENSIONS:
            try:
                if path.stat().st_size >= 50_000:
                    files.append(path)
            except OSError:
                pass
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _wait_for_media(download_dir: Path, timeout: int) -> Path:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        media = _media_files(download_dir)
        partials = list(download_dir.glob("*.crdownload")) + list(download_dir.glob("*.part"))
        if media and not partials:
            return media[0]
        time.sleep(1)
    raise TimeoutError(f"No completed media download within {timeout}s")


def _candidate_input(driver):
    """Find the most likely URL field without hard-coding a site's DOM."""
    from selenium.webdriver.common.by import By

    candidates = driver.find_elements(By.CSS_SELECTOR, "input, textarea")
    scored = []
    for element in candidates:
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            text = " ".join(
                str(value or "")
                for value in (
                    element.get_attribute("placeholder"),
                    element.get_attribute("aria-label"),
                    element.get_attribute("name"),
                    element.get_attribute("type"),
                )
            ).lower()
            score = 0
            for marker in ("url", "link", "video", "youtube", "paste"):
                if marker in text:
                    score += 5
            if (element.get_attribute("type") or "").lower() in {"url", "search", "text", ""}:
                score += 1
            scored.append((score, element))
        except Exception:
            continue
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _click_download(driver) -> bool:
    """Click a visible download/result button or link, avoiding obvious ads."""
    from selenium.webdriver.common.by import By

    candidates = driver.find_elements(By.CSS_SELECTOR, "button, a")
    best = None
    best_score = -1
    for element in candidates:
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            label = " ".join(
                str(value or "")
                for value in (
                    element.text,
                    element.get_attribute("aria-label"),
                    element.get_attribute("title"),
                    element.get_attribute("download"),
                    element.get_attribute("href"),
                )
            ).lower()
            if any(marker in label for marker in ("sponsor", "advert", "casino", "popup")):
                continue

            score = 0
            for marker in ("download", "mp4", "video", "save", "get file"):
                if marker in label:
                    score += 4
            href = (element.get_attribute("href") or "").lower()
            if any(ext in href for ext in (".mp4", ".webm", ".m4a", ".mp3")):
                score += 10
            if element.get_attribute("download") is not None:
                score += 8
            if score > best_score:
                best_score = score
                best = element
        except Exception:
            continue

    if best is None or best_score < 4:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", best)
        driver.execute_script("arguments[0].click();", best)
        return True
    except Exception:
        try:
            best.click()
            return True
        except Exception:
            return False


def _try_submit(driver, youtube_url: str) -> None:
    from selenium.webdriver.common.keys import Keys

    field = _candidate_input(driver)
    if field is None:
        raise RuntimeError("Could not find a URL input field")
    field.click()
    field.send_keys(Keys.CONTROL, "a")
    field.send_keys(youtube_url)
    field.send_keys(Keys.ENTER)
    time.sleep(2)
    _click_download(driver)


def _visit_site(driver, name: str, site_url: str, youtube_url: str, download_dir: Path) -> Path:
    """Attempt one site using several common URL-prefill conventions, then its UI."""
    _clear_download_dir(download_dir)
    attempts = [
        site_url,
        f"{site_url.rstrip('/')}/#{quote(youtube_url, safe=':/?=&%_-.,')}",
        f"{site_url.rstrip('/')}/?url={quote(youtube_url, safe='')}",
        f"{site_url.rstrip('/')}/?video={quote(youtube_url, safe='')}",
    ]
    last_error: Exception | None = None

    for target in attempts:
        try:
            driver.get(target)
            time.sleep(2)
            # The URL may already have been prefilled and triggered processing.
            try:
                return _wait_for_media(download_dir, timeout=12)
            except TimeoutError:
                pass

            _try_submit(driver, youtube_url)
            return _wait_for_media(download_dir, timeout=35)
        except Exception as exc:  # noqa: BLE001 - move to the next site/pattern
            last_error = exc
            _clear_download_dir(download_dir)
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass

    raise RuntimeError(f"{name}: {last_error}")


def download_via_browser(url: str, out_dir: Path, timeout: int | None = None) -> Path:
    """Try many public downloader sites in Chrome and return the first valid file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    timeout = timeout or int(os.environ.get("DBYT_DOWNLOADER_TIMEOUT", "60"))
    download_dir = out_dir / ".browser-download"
    download_dir.mkdir(parents=True, exist_ok=True)

    driver = _configure_chrome(download_dir)
    failures: list[str] = []
    try:
        sites = _sites()
        print(f"🌐 Browser downloader pool: {len(sites)} sites")
        for index, (name, site_url) in enumerate(sites, 1):
            print(f"🌐 [{index}/{len(sites)}] Trying {name}: {site_url}")
            try:
                result = _visit_site(driver, name, site_url, url, download_dir)
                safe_ext = re.sub(r"[^a-z0-9]", "", result.suffix.lower().lstrip(".")) or "mp4"
                destination = out_dir / f"source.{safe_ext}"
                shutil.copy2(result, destination)
                print(f"✅ Browser downloader succeeded: {name} -> {destination.name} ({destination.stat().st_size} bytes)")
                return destination
            except Exception as exc:  # noqa: BLE001 - this is the whole fallback strategy
                message = str(exc).replace("\n", " ")[:220]
                failures.append(f"{name}: {message}")
                print(f"⚠️ {name} failed: {message}")
                try:
                    driver.delete_all_cookies()
                except Exception:
                    pass

        summary = " | ".join(failures[-10:])
        raise RuntimeError(f"All browser downloader sites failed. Last failures: {summary}")
    finally:
        driver.quit()
        shutil.rmtree(download_dir, ignore_errors=True)


__all__ = ["download_via_browser", "DEFAULT_SITES"]
