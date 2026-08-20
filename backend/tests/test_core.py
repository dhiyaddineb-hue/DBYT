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
