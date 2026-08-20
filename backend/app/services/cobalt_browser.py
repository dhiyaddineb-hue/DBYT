"""Browser-driven multi-site video downloader."""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import quote

_CHROME_BINARY = os.environ.get("DBYT_CHROME_BINARY", "/usr/bin/google-chrome")

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

_VIDEO_EXTENSIONS = {".mp4", ".m4v", ".webm", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".ts", ".m2ts"}
_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac"}
_IGNORED_EXTENSIONS = {".crdownload", ".tmp", ".part", ".html", ".htm", ".txt", ".json"}


def _sites():
    raw = os.environ.get("DBYT_DOWNLOADER_SITES", "").strip()
    if not raw:
        return DEFAULT_SITES
    parsed = []
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
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
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
    driver.set_page_load_timeout(25)
    driver.set_script_timeout(20)
    driver.execute_cdp_cmd("Browser.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": str(download_dir.resolve()),
        "eventsEnabled": True,
    })
    return driver


def _clear_download_dir(download_dir: Path):
    download_dir.mkdir(parents=True, exist_ok=True)
    for path in list(download_dir.iterdir()):
        if path.is_file():
            path.unlink(missing_ok=True)


def _media_files(download_dir: Path):
    files = []
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


def _wait_for_media(download_dir: Path, timeout: int, label: str):
    deadline = time.monotonic() + timeout
    next_report = time.monotonic() + 5
    while time.monotonic() < deadline:
        media = _media_files(download_dir)
        partials = list(download_dir.glob("*.crdownload")) + list(download_dir.glob("*.part"))
        if media and not partials:
            return media[0]
        if time.monotonic() >= next_report:
            print(f"⏳ [{label}] still waiting for a download… {max(0, int(deadline - time.monotonic()))}s left", flush=True)
            next_report = time.monotonic() + 5
        time.sleep(1)
    raise TimeoutError(f"No completed media download within {timeout}s")


def _candidate_input(driver):
    from selenium.webdriver.common.by import By
    candidates = driver.find_elements(By.CSS_SELECTOR, "input, textarea")
    scored = []
    for element in candidates:
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            text = " ".join(str(value or "") for value in (
                element.get_attribute("placeholder"),
                element.get_attribute("aria-label"),
                element.get_attribute("name"),
                element.get_attribute("type"),
            )).lower()
            score = sum(5 for marker in ("url", "link", "video", "youtube", "paste") if marker in text)
            if (element.get_attribute("type") or "").lower() in {"url", "search", "text", ""}:
                score += 1
            scored.append((score, element))
        except Exception:
            continue
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored else None


def _native_set_value(driver, field, value: str):
    """Set a React/Vue controlled input without clicking it."""
    script = """
    const el = arguments[0];
    const value = arguments[1];
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    if (desc && desc.set) {
      desc.set.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event('input', {bubbles:true, composed:true}));
    el.dispatchEvent(new Event('change', {bubbles:true, composed:true}));
    el.dispatchEvent(new Event('blur', {bubbles:true, composed:true}));
    return el.value;
    """
    return driver.execute_script(script, field, value)


def _cobalt_submit(driver, youtube_url: str, label: str) -> bool:
    """Special Cobalt path: never click the input; mutate the controlled input and submit."""
    field = driver.find_element("css selector", "#link-area")
    value = _native_set_value(driver, field, youtube_url)
    print(f"🧩 [{label}] DOM value set={value == youtube_url}", flush=True)

    submitted = driver.execute_script("""
    const input = arguments[0];
    const form = input.closest('form');
    if (form) {
      if (typeof form.requestSubmit === 'function') form.requestSubmit();
      else form.submit();
      return 'form';
    }
    for (const root of [document, ...Array.from(document.querySelectorAll('*'))]) {
      const nodes = root.shadowRoot ? Array.from(root.shadowRoot.querySelectorAll('button')) : [];
      for (const b of nodes) {
        const t = (b.innerText || b.getAttribute('aria-label') || '').toLowerCase();
        if (t.includes('download') || t.includes('submit')) { b.click(); return 'shadow-button'; }
      }
    }
    for (const b of document.querySelectorAll('button')) {
      const t = (b.innerText || b.getAttribute('aria-label') || '').toLowerCase();
      if (t.includes('download') || t.includes('submit') || t.includes('go')) { b.click(); return 'button'; }
    }
    input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    input.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
    return 'enter';
    """, field)
    print(f"🧩 [{label}] submission method={submitted}", flush=True)
    return submitted not in (None, "")


def _click_download(driver) -> bool:
    from selenium.webdriver.common.by import By
    best = None
    best_score = -1
    for element in driver.find_elements(By.CSS_SELECTOR, "button, a"):
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            label = " ".join(str(value or "") for value in (
                element.text,
                element.get_attribute("aria-label"),
                element.get_attribute("title"),
                element.get_attribute("download"),
                element.get_attribute("href"),
            )).lower()
            if any(marker in label for marker in ("sponsor", "advert", "casino", "popup")):
                continue
            score = sum(4 for marker in ("download", "mp4", "video", "save", "get file") if marker in label)
            href = (element.get_attribute("href") or "").lower()
            if any(ext in href for ext in (".mp4", ".webm", ".m4a", ".mp3")):
                score += 10
            if element.get_attribute("download") is not None:
                score += 8
            if score > best_score:
                best_score, best = score, element
        except Exception:
            continue
    if best is None or best_score < 4:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", best)
        return True
    except Exception:
        try:
            best.click()
            return True
        except Exception:
            return False


def _try_submit(driver, youtube_url: str, label: str) -> None:
    field = _candidate_input(driver)
    if field is None:
        raise RuntimeError("URL input field not found")
    print(f"📝 [{label}] URL field found; submitting", flush=True)
    if label in {"COBALT", "COBALT-COMMUNITY"} and (field.get_attribute("id") or "").lower() == "link-area":
        _cobalt_submit(driver, youtube_url, label)
        return

    # Generic sites: normal click is fine, but use JS fallback when an overlay intercepts it.
    try:
        field.click()
    except Exception:
        driver.execute_script("arguments[0].focus(); arguments[0].scrollIntoView({block:'center'});", field)
    try:
        field.clear()
    except Exception:
        driver.execute_script("arguments[0].value='';", field)
    try:
        field.send_keys(youtube_url)
    except Exception:
        _native_set_value(driver, field, youtube_url)
    try:
        field.send_keys("\ue007")
    except Exception:
        driver.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));", field)
    time.sleep(2)
    clicked = _click_download(driver)
    print(f"🖱️ [{label}] download button clicked={clicked}", flush=True)


def _diagnostic_screenshot(driver, diagnostics_dir: Path, name: str):
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    try:
        path = diagnostics_dir / f"{name}.png"
        driver.save_screenshot(str(path))
        print(f"📸 Screenshot: {path}", flush=True)
    except Exception as exc:
        print(f"⚠️ Screenshot failed: {exc}", flush=True)


def _visit_site(driver, name: str, site_url: str, youtube_url: str, download_dir: Path, diagnostics_dir: Path):
    _clear_download_dir(download_dir)
    label = name.upper()
    target = f"{site_url.rstrip('/')}/#{quote(youtube_url, safe=':/?=&%_-.,')}"
    print(f"➡️ [{label}] Opening {site_url}", flush=True)
    try:
        driver.get(target)
    except Exception as exc:
        print(f"⚠️ [{label}] page load timeout/error: {str(exc)[:180]}", flush=True)
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    print(f"✅ [{label}] page reached: title={driver.title[:100]!r}", flush=True)
    print(f"🌐 [{label}] waiting for automatic download (20s)", flush=True)
    try:
        return _wait_for_media(download_dir, 20, label)
    except TimeoutError:
        pass
    _try_submit(driver, youtube_url, label)
    print(f"🌐 [{label}] waiting for browser download (40s)", flush=True)
    try:
        return _wait_for_media(download_dir, 40, label)
    except TimeoutError:
        _diagnostic_screenshot(driver, diagnostics_dir, f"{name}-timeout")
        raise


def download_via_browser(url: str, out_dir: Path, timeout: int | None = None) -> Path:
    del timeout
    out_dir.mkdir(parents=True, exist_ok=True)
    download_dir = out_dir / ".browser-download"
    diagnostics_dir = out_dir / ".browser-diagnostics"
    download_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    driver = _configure_chrome(download_dir)
    failures = []
    sites = _sites()
    try:
        print(f"🌐 Browser downloader pool: {len(sites)} sites", flush=True)
        for index, (name, site_url) in enumerate(sites, 1):
            print(f"\n===== SITE {index}/{len(sites)}: {name} =====", flush=True)
            try:
                result = _visit_site(driver, name, site_url, url, download_dir, diagnostics_dir)
                safe_ext = re.sub(r"[^a-z0-9]", "", result.suffix.lower().lstrip(".")) or "mp4"
                destination = out_dir / f"source.{safe_ext}"
                shutil.copy2(result, destination)
                print(f"✅ Browser downloader succeeded: {name} -> {destination.name} ({destination.stat().st_size} bytes)", flush=True)
                return destination
            except Exception as exc:
                message = str(exc).replace("\n", " ")[:220]
                failures.append(f"{name}: {message}")
                print(f"❌ [{name}] FAILED: {message}", flush=True)
                try:
                    driver.delete_all_cookies()
                except Exception:
                    pass
                try:
                    driver.get("about:blank")
                except Exception:
                    pass
        summary = " | ".join(failures[-10:])
        raise RuntimeError(f"All browser downloader sites failed. Last failures: {summary}")
    finally:
        driver.quit()
        shutil.rmtree(download_dir, ignore_errors=True)


__all__ = ["download_via_browser", "DEFAULT_SITES"]
