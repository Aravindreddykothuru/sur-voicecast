"""Thin wrappers around ffmpeg/ffprobe -- the only place in the codebase
that shells out to media tooling, so provider/task code stays testable
without ffmpeg installed (tests monkeypatch these)."""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
from collections.abc import Iterator


def probe_duration_ms(path: str) -> int:
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(out.stdout or "{}")
        return int(float(data["format"]["duration"]) * 1000)
    except Exception:
        # ffprobe missing or file not a real media file (e.g. in a unit
        # test) -- callers treat 0 as "unknown", never a hard failure.
        return 0


def extract_audio_wav(video_path: str, out_path: str, sample_rate: int = 16000) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            out_path,
        ],
        check=True,
        capture_output=True,
    )


@contextlib.contextmanager
def extract_audio_slice(audio_path: str, start_ms: int, end_ms: int) -> Iterator[str]:
    """Cut [start_ms, end_ms) out of `audio_path` into a temp file, yielding
    its path; used by providers that only accept a single utterance at a
    time (faster-whisper, the emotion classifier)."""
    # NamedTemporaryFile(delete=True) keeps its handle open for the `with`
    # block's whole lifetime; on Windows (unlike POSIX) a second process can't
    # open that same path for writing while we still hold it, so ffmpeg's own
    # -y open would fail with a sharing violation. Create+close it up front
    # (delete=False) so ffmpeg can write to the bare path, then clean up
    # ourselves.
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                audio_path,
                "-ss",
                f"{start_ms / 1000:.3f}",
                "-to",
                f"{end_ms / 1000:.3f}",
                path,
            ],
            check=True,
            capture_output=True,
        )
        yield path
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)


def mux_timeline(video_path: str, placements: list[tuple[str, int]], out_path: str) -> None:
    """Lay each rendered segment's audio at its own start offset on a silent
    bed, then mux the result onto the original video's picture track.

    `placements` is [(local_wav_path, start_ms), ...].

    Concatenating the clips back-to-back instead (what this used to do) throws
    away every segment's timecode: it drops the leading offset and all the
    gaps between utterances, so the dub slides progressively out of sync with
    the picture -- the one thing a dubbing engine must not do. Delaying each
    clip to its real start keeps speech under the mouth it belongs to.
    """
    if not placements:
        raise ValueError("mux_timeline: no audio placements given")

    cmd = ["ffmpeg", "-y", "-i", video_path]
    for path, _ in placements:
        cmd += ["-i", path]

    # Each rendered clip is delayed to its own start_ms, then all of them are
    # mixed down onto one track. `all=1` applies the delay to every channel;
    # `normalize=0` keeps amix from attenuating each input by 1/N (which would
    # make a many-segment dub progressively quieter).
    filters = []
    labels = []
    for i, (_, start_ms) in enumerate(placements):
        stream = i + 1  # input 0 is the video
        label = f"a{i}"
        filters.append(f"[{stream}:a]adelay={max(start_ms, 0)}:all=1[{label}]")
        labels.append(f"[{label}]")
    # apad matters: without it the mixed track ends with the last utterance, and
    # -shortest then truncates the *video* to that point -- a 10s clip whose last
    # line lands at 6s came out 6s long. Padding with silence makes the video the
    # shortest stream again, so the picture survives intact.
    filters.append(
        f"{''.join(labels)}amix=inputs={len(placements)}:normalize=0:dropout_transition=0[amixed]"
    )
    filters.append("[amixed]apad[aout]")

    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
