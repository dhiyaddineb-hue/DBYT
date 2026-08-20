#!/usr/bin/env python3
"""Minimal ffprobe shim for the DBYT sandbox.

The bundled imageio-ffmpeg ships only the `ffmpeg` binary (no `ffprobe`).
This shim translates the two ffprobe invocations DBYT uses into ffmpeg calls:

  1) `ffprobe -v error -show_entries format=duration
        -of default=noprint_wrappers=1:nokey=1 <file>`   -> prints duration (sec)
  2) `ffprobe -v error -select_streams v:0 -show_entries stream=codec_type
        -of csv=p=0 <file>`                              -> prints "video" or ""
"""
import re
import subprocess
import sys


def ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def probe_info(path):
    """Run `ffmpeg -i path` and return (duration_seconds, has_video)."""
    proc = subprocess.run(
        [ffmpeg(), "-i", path], stderr=subprocess.PIPE, stdout=subprocess.DEVNULL
    )
    err = proc.stderr.decode("utf-8", "replace")
    dur = None
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
    if m:
        h, mn, s = m.groups()
        dur = int(h) * 3600 + int(mn) * 60 + float(s)
    has_video = "Video:" in err
    return dur, has_video


def main():
    args = sys.argv[1:]
    # Extract the (last) positional file argument
    files = [a for a in args if not a.startswith("-")]
    if not files:
        sys.exit(1)
    path = files[-1]

    if "-show_entries" in args and "format=duration" in " ".join(args):
        dur, _ = probe_info(path)
        print(f"{dur:.6f}" if dur is not None else "N/A")
    elif "-select_streams" in args and "v:0" in " ".join(args):
        _, has_video = probe_info(path)
        print("video" if has_video else "")
    else:
        # Default: just probe duration
        dur, _ = probe_info(path)
        print(f"{dur:.6f}" if dur is not None else "N/A")


if __name__ == "__main__":
    main()
