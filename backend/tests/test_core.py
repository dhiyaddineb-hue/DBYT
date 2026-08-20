"""Offline unit tests for the pure-Python parts of the pipeline.

These do not need ffmpeg, Whisper models, or network access.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import emotion, youtube
from app.services.pipeline import _map_target_words, split_words


def test_extract_video_id():
    assert youtube.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube.extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube.extract_video_id("https://www.youtube.com/shorts/abcDEF12345") == "abcDEF12345"
    assert youtube.extract_video_id("https://example.com") is None
    assert youtube.extract_video_id("") is None


def test_is_valid_youtube_url():
    assert youtube.is_valid_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not youtube.is_valid_youtube_url("https://example.com/video")


def test_slugify_project_name():
    assert youtube._slugify("My Amazing Video! (2024)") == "My-Amazing-Video-2024"
    assert youtube._slugify("   ") == "project"
    assert youtube._slugify("Arabic: فيديو رائع") == "Arabic-فيديو-رائع"


def test_emotion_detection():
    # Anger
    r = emotion.analyze("I am so angry about this unfair situation", "en")
    assert r.emotion == "angry"
    assert r.rate > 1.0  # anger speaks faster
    # Sadness
    r = emotion.analyze("I'm really sad, I lost everything", "en")
    assert r.emotion == "sad"
    assert r.pitch < 0  # sadness drops pitch
    # Neutral
    r = emotion.analyze("The meeting starts at nine o'clock.", "en")
    assert r.emotion == "neutral"
    assert r.rate == 1.0


def test_emotion_preserve_disabled():
    r = emotion.analyze("I am angry!!!", "en", preserve=False)
    assert r.emotion == "neutral"


def test_bark_emotion_prefix():
    assert emotion.bark_emotion_prefix("happy") == "[laughter] "
    assert emotion.bark_emotion_prefix("neutral") == ""


def test_split_words():
    assert split_words("hello world") == ["hello", "world"]
    assert split_words("  a   b  ") == ["a", "b"]
    assert split_words("") == []


def test_map_target_words_equal_count():
    assert _map_target_words(["bonjour", "le", "monde"], 3) == ["bonjour", "le", "monde"]


def test_map_target_words_fewer_words():
    # 2 target words fill 4 source slots by repeating
    out = _map_target_words(["hi", "there"], 4)
    assert len(out) == 4
    assert out[0] == "hi" and out[1] == "there"


def test_map_target_words_more_words():
    # 6 target words squeezed into 3 slots -> chunks of 2
    out = _map_target_words(["a", "b", "c", "d", "e", "f"], 3)
    assert len(out) == 3
    assert out[0] == "a b" and out[2] == "e f"


def test_map_target_words_empty():
    assert _map_target_words([], 3) == ["", "", ""]
    assert _map_target_words(["x"], 0) == ["x"]


def test_cookie_file_validation():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cookies.txt"
        path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        assert not youtube._has_usable_cookies(path)
        path.write_text(
            "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tYSC\ttest\n",
            encoding="utf-8",
        )
        assert youtube._has_usable_cookies(path)


def test_downloaded_file_resolves_merged_mp4():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        merged = out_dir / "abc12345678.mp4"
        merged.write_bytes(b"video")
        resolved = youtube._downloaded_file(
            {"id": "abc12345678"},
            str(out_dir / "abc12345678.webm"),
            out_dir,
            prefer_audio=False,
        )
        assert resolved == merged


def test_configured_proxies():
    import os

    previous = os.environ.get("DBYT_YOUTUBE_PROXIES")
    try:
        os.environ["DBYT_YOUTUBE_PROXIES"] = (
            " socks5h://proxy-a:1080,\nhttp://proxy-b:8080 "
        )
        assert youtube._configured_proxies() == (
            "socks5h://proxy-a:1080",
            "http://proxy-b:8080",
        )
    finally:
        if previous is None:
            os.environ.pop("DBYT_YOUTUBE_PROXIES", None)
        else:
            os.environ["DBYT_YOUTUBE_PROXIES"] = previous


def test_configured_frontends_and_cobalt():
    import os

    previous = {
        name: os.environ.get(name)
        for name in (
            "DBYT_INVIDIOUS_INSTANCES",
            "DBYT_COBALT_URL",
            "DBYT_COBALT_API_KEY",
        )
    }
    try:
        os.environ["DBYT_INVIDIOUS_INSTANCES"] = (
            " https://one.example,\nhttps://two.example/ "
        )
        os.environ["DBYT_COBALT_URL"] = " https://cobalt.example/ "
        os.environ["DBYT_COBALT_API_KEY"] = "secret-value"
        assert youtube._configured_frontends() == (
            "https://one.example",
            "https://two.example",
        )
        assert youtube._configured_cobalt() == (
            "https://cobalt.example",
            "secret-value",
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_cobalt_key_not_forwarded_to_external_tunnel():
    same_host = youtube._cobalt_headers(
        "https://cobalt.example", "secret", "https://cobalt.example/tunnel/1"
    )
    external_host = youtube._cobalt_headers(
        "https://cobalt.example", "secret", "https://googlevideo.example/file"
    )
    assert same_host["Authorization"] == "Api-Key secret"
    assert "Authorization" not in external_host


def test_cobalt_audio_tunnel_payload():
    import json
    import tempfile
    from unittest.mock import patch

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "status": "tunnel",
                "url": "https://cobalt.example/tunnel/1",
                "filename": "source.mp3",
            }).encode("utf-8")

    with tempfile.TemporaryDirectory() as tmp, patch.object(
        youtube.urllib.request, "urlopen", return_value=Response()
    ) as open_url, patch.object(youtube, "_download_url") as download_url:
        output = youtube._download_via_cobalt(
            "https://www.youtube.com/watch?v=CAwRm-VO-kU",
            Path(tmp),
            True,
            "https://cobalt.example",
            "secret",
        )

    request = open_url.call_args.args[0]
    assert json.loads(request.data.decode("utf-8"))["audioFormat"] == "mp3"
    assert request.get_header("Authorization") == "Api-Key secret"
    assert output.name == "CAwRm-VO-kU.mp3"
    download_url.assert_called_once()


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}:")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
