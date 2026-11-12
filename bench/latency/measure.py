"""Latency: from the end of a sentence said to its text at the cursor.

    ~/.local/share/whisper-desk/venv/bin/python bench/latency/measure.py
    ~/.local/share/whisper-desk/venv/bin/python bench/latency/measure.py --src /tmp/before/src

Needs numpy, ffmpeg and the models already downloaded, so whisper-desk's own
Python; LD_LIBRARY_PATH on the venv's nvidia/*/lib for CUDA. --src runs another
copy of whisper-desk — `git archive origin/main src | tar -x -C /tmp/before`
gives the one to compare with.

The sentences are the control recordings of the other benches, as listed in
bench/whisper/corpus.tsv, taken three at a time in each language to make the dictations, each
played in real time — 100 ms of sound every 100 ms — into whisper-desk's own
dictation (the daemon's Session, its Recorder and its Transcriber, numbered
lists off: a sentence that may open one waits for the next on purpose), over
the noise of a quiet room:

    0.5 s of room, sentence A, 1 s of pause, sentence B, 0.45 s of breath,
    sentence C, then the shortcut pressed 0.2 s, 0.45 s or 1.2 s after it.

A and B+C are two sentences for whisper-desk: the 1 s pause ends A, the
0.45 s breath does not end B (the pause is 0.6 s). The latency of a sentence is
the time from the end of its voice to its text handed to the output. The first
dictation runs on a model just loaded, as the first one of the day does.
"""

from __future__ import annotations

import argparse
import copy
import csv
import re
import statistics
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
RATE = 16000
CHUNK = 1600
NOISE_RMS = 16.0                       # -66 dBFS, a laptop microphone in a quiet room
VOICE_RMS = 1640.0                     # an ordinary voice, its loud parts at -26 dBFS
PAUSE, BREATH = 1.0, 0.45
STOPS = (0.2, 0.45, 1.2)


def corpus() -> list[dict[str, str]]:
    with (BENCH / "whisper" / "corpus.tsv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def decode(source: str) -> np.ndarray:
    bench, name = source.split("/")
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(BENCH / bench / "audio" / f"{name}.opus"),
         "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.int16).astype(np.float64)


def loud_level(signal: np.ndarray) -> float:
    usable = len(signal) - len(signal) % CHUNK
    levels = np.sqrt(np.mean(np.square(signal[:usable].reshape(-1, CHUNK)), axis=1))
    return float(np.percentile(levels, 90))


def trimmed(voice: np.ndarray) -> np.ndarray:
    """The clip from its first word to its last, the synthesizer's silences cut.

    A word starts or ends where the voice is no more than 20 dB under its loud
    parts; 50 ms are left on either side.
    """
    frame = RATE // 100
    usable = len(voice) - len(voice) % frame
    levels = np.sqrt(np.mean(np.square(voice[:usable].reshape(-1, frame)), axis=1))
    loud = np.nonzero(levels >= loud_level(voice) * 0.1)[0]
    start = max(int(loud[0]) * frame - RATE // 20, 0)
    end = min((int(loud[-1]) + 1) * frame + RATE // 20, len(voice))
    return voice[start:end]


def dictation(voices: list[np.ndarray], stop: float, rng: np.random.Generator):
    """The PCM played, the times sentences A and C end, and when the key is pressed."""
    parts, cursor, ends = [np.zeros(RATE // 2)], 0.5, []
    for index, voice in enumerate(voices):
        if index:
            gap = PAUSE if index == 1 else BREATH
            parts.append(np.zeros(int(gap * RATE)))
            cursor += gap
        voice = trimmed(voice)
        voice = voice * (VOICE_RMS / loud_level(voice))
        parts.append(voice)
        cursor += len(voice) / RATE
        ends.append(cursor - 0.05)
    parts.append(np.zeros(int((stop + 3.0) * RATE)))
    signal = np.concatenate(parts)
    signal = signal + rng.standard_normal(len(signal)) * NOISE_RMS
    pcm = np.clip(np.round(signal), -32768, 32767).astype("<i2").tobytes()
    return pcm, [ends[0], ends[2]], ends[2] + stop


class Playback:
    """A capture tool that hands each 100 ms of sound once it has been said."""

    def __init__(self, pcm: bytes):
        self.pcm = pcm
        self.position = 0
        self.started = time.monotonic()
        self.closed = threading.Event()
        self.stdout = self

    def read(self, size: int) -> bytes:
        chunk = self.pcm[self.position:self.position + size]
        self.position += len(chunk)
        due = self.started + self.position / 2 / RATE
        while not self.closed.is_set() and time.monotonic() < due:
            time.sleep(min(0.005, max(due - time.monotonic(), 0.0)))
        return b"" if self.closed.is_set() else chunk

    def close(self) -> None:
        self.closed.set()

    def terminate(self) -> None:
        self.closed.set()

    kill = terminate

    def wait(self, timeout=None) -> int:
        return 0


def words(text: str) -> list[str]:
    return re.findall(r"[\w'’]+", text.lower())


def distance(reference: list[str], hypothesis: list[str]) -> int:
    row = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, 1):
        previous, row[0] = row[0], i
        for j, hyp in enumerate(hypothesis, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (ref != hyp))
    return row[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(BENCH.parent / "src"))
    parser.add_argument("--model", default="large-v3-turbo:cuda")
    parser.add_argument("--limit", type=int, default=0, help="the first N dictations only")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, args.src)
    from whisper_desk import config, daemon, recorder, transcriber

    rows = corpus()
    rng = np.random.default_rng(2026)
    groups = []
    for lang in dict.fromkeys(row["lang"] for row in rows):
        said = [row for row in rows if row["lang"] == lang]
        groups += [said[index:index + 3] for index in range(0, len(said) - 2, 3)]
    groups = groups[:args.limit] if args.limit else groups

    settings = copy.deepcopy(config.DEFAULTS)
    name, device = args.model.split(":")
    settings["model"].update(name=name, device=device)
    # A sentence that may open a numbered list waits for the next on purpose:
    # a wait of its own, not the latency measured here.
    settings["model"]["lists"] = False
    settings["overlay"]["enabled"] = False
    settings["output"]["history"] = False
    model = transcriber.Transcriber(settings)
    model.load()
    passes = 0
    transcribe = model.transcribe

    def counted(*args, **kwargs) -> str:
        nonlocal passes
        passes += 1
        return transcribe(*args, **kwargs)

    model.transcribe = counted

    playing: list[Playback] = []
    recorder.subprocess = types.SimpleNamespace(
        Popen=lambda *a, **k: playing[-1], PIPE=-1, DEVNULL=-3,
        TimeoutExpired=subprocess.TimeoutExpired,
    )
    recorder.capture.build = lambda *a, **k: recorder.capture.Capture("bench", ["bench"])

    latencies: dict[str, list[float]] = {"A": [], **{f"C+{stop}": [] for stop in STOPS}}
    first: float | None = None
    errors = total = missing = 0
    for number, group in enumerate(groups):
        stop = STOPS[number % len(STOPS)]
        pcm, ends, press = dictation([decode(row["source"]) for row in group], stop, rng)
        settings["model"]["language"] = group[0]["lang"]
        service = types.SimpleNamespace(
            config=settings, transcriber=model, state="", finish=lambda _session: None,
        )
        session = daemon.Session(service, capture=True)
        inserted: list[tuple[float, str]] = []
        insert = session._insert

        def timed(text: str, insert=insert, inserted=inserted) -> None:
            inserted.append((time.monotonic(), text))
            insert(text)

        session._insert = timed
        playing.append(Playback(pcm))
        start = playing[-1].started
        threading.Timer(max(press - (time.monotonic() - start), 0.0), session.stop).start()
        session.run()

        times = [moment - start for moment, _text in inserted]
        for label, end in zip(("A", f"C+{stop}"), ends):
            after = [moment for moment in times if moment > end]
            if not after:
                missing += 1
                continue
            latencies[label].append(after[0] - end)
            if number == 0 and label == "A":
                first = after[0] - end
        reference = words(" ".join(row["text"] for row in group))
        heard = words(session.text)
        errors += distance(reference, heard)
        total += len(reference)
        if args.verbose:
            print(f"{number:2d} stop+{stop}: {[round(t, 2) for t in times]} ends "
                  f"{[round(e, 2) for e in ends]} | {session.text}")

    print(f"{name} on {device}, {args.src}")
    print(f"  first sentence after the load: {first:.2f} s")
    for label, values in latencies.items():
        values = values[1:] if label == "A" else values
        print(f"  {label:7s} n={len(values):2d}  median {statistics.median(values):.2f} s  "
              f"mean {statistics.mean(values):.2f} s  max {max(values):.2f} s")
    print(f"  WER {100 * errors / total:.1f} % ({errors}/{total} words), "
          f"{missing} sentence(s) never inserted")
    print(f"  {passes} passes through the model for {2 * len(groups)} sentences")


if __name__ == "__main__":
    main()
