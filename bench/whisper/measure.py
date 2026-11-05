"""Dictation said quietly or whispered: heard by the recorder, then transcribed.

    ~/.local/share/whisper-desk/venv/bin/python bench/whisper/measure.py           # recorder only
    ~/.local/share/whisper-desk/venv/bin/python bench/whisper/measure.py --audio   # + faster-whisper

Needs numpy and ffmpeg, so whisper-desk's own Python; --audio needs the models
already downloaded, and LD_LIBRARY_PATH on the venv's nvidia/*/lib for CUDA.

The sentences are the control recordings of the other benches (corpus.tsv names
them), plain sentences that no rule of whisper-desk changes. Each is played at
three levels, over the same steady background noise (-66 dBFS):

- ordinary: an ordinary voice, its loud parts at -26 dBFS;
- low: the same voice 24 dB lower, said under the breath;
- whispered: the voice without its vocal folds — its spectral envelope over a
  noise, as a whisper is made — at the same low level.

Each recording goes through whisper-desk's Recorder as it would from the
microphone (0.5 s of room noise first, then 3 s after it, the as-you-go
dictation on), and each sentence it sends goes through the Transcriber with what
came before as context, as the daemon does. "before" is whisper-desk with its
former threshold floor (180), no hold and no gain.

Two checks that hearing more did not break the rest: 42 pairs of sentences said
1 s apart, ordinary and low, in a steady room and in one whose noise swells and
ebbs by 10 dB — the pause must still split them and the silence after them end
the dictation; and 40 recordings of room noise alone, steady or fluctuating, from
-78 to -54 dBFS, in which nothing must be heard.
"""

from __future__ import annotations

import argparse
import copy
import csv
import re
import subprocess
import sys
import tempfile
import types
from contextlib import contextmanager
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from whisper_desk import capture, config, recorder, transcriber  # noqa: E402

RATE = 16000
NOISE_RMS = 16.0                       # -66 dBFS, a laptop microphone in a quiet room
LEVELS = {"ordinary": 1640.0, "low": 104.0, "whispered": 104.0}
FORMER_THRESHOLD = 180.0


def corpus() -> list[dict[str, str]]:
    with (HERE / "corpus.tsv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def decode(source: str) -> np.ndarray:
    bench, name = source.split("/")
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(HERE.parent / bench / "audio" / f"{name}.opus"),
         "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, np.int16).astype(np.float64)


def whispered(voice: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """The voice's spectral envelope laid over noise: a voice without its pitch."""
    size, hop = 512, 128
    window = np.hanning(size)
    padded = np.concatenate([np.zeros(size), voice, np.zeros(size)])
    frames = np.lib.stride_tricks.sliding_window_view(padded, size)[::hop] * window
    magnitude = np.abs(np.fft.rfft(frames, axis=1)) + 1e-6
    cepstrum = np.fft.irfft(np.log(magnitude), axis=1)
    cepstrum[:, 30:-30] = 0.0           # the envelope, without the harmonics
    envelope = np.exp(np.fft.rfft(cepstrum, axis=1).real)
    noise = np.fft.rfft(rng.standard_normal(frames.shape) * window, axis=1)
    out_frames = np.fft.irfft(envelope * noise / (np.abs(noise) + 1e-9), n=size, axis=1) * window
    out = np.zeros(len(padded) + size)
    for index, frame in enumerate(out_frames):
        out[index * hop:index * hop + size] += frame
    return out[size:size + len(voice)]


def loud_level(signal: np.ndarray) -> float:
    """RMS of the loud tenth of the 100 ms frames: the voice, not its pauses."""
    usable = len(signal) - len(signal) % 1600
    levels = np.sqrt(np.mean(np.square(signal[:usable].reshape(-1, 1600)), axis=1))
    return float(np.percentile(levels, 90))


def room(samples: int, rng: np.random.Generator, fluctuating: bool = False) -> np.ndarray:
    """The noise of the room: steady, or swelling and ebbing by 10 dB like a fan."""
    noise = rng.standard_normal(samples) * NOISE_RMS
    if fluctuating:
        time = np.arange(samples) / RATE
        noise *= 1 + 0.5 * np.sin(2 * np.pi * rng.uniform(0.3, 3.0) * time + rng.uniform(0, 7))
    return noise


def recording(voices: list[np.ndarray], level: float, rng: np.random.Generator,
              fluctuating: bool = False) -> bytes:
    """The voices at this level, 1 s apart, after 0.5 s of room and before 3 s."""
    parts = [np.zeros(RATE // 2)]
    for index, voice in enumerate(voices):
        if index:
            parts.append(np.zeros(RATE))
        parts.append(voice * (level / loud_level(voice)))
    parts.append(np.zeros(3 * RATE))
    signal = np.concatenate(parts)
    signal = signal + room(len(signal), rng, fluctuating)
    return np.clip(np.round(signal), -32768, 32767).astype("<i2").tobytes()


@contextmanager
def former(enabled: bool):
    """whisper-desk as it was: threshold floor at 180, no hold, no gain."""
    saved = recorder.MIN_THRESHOLD, recorder.HOLD, transcriber.voice_gain
    if enabled:
        recorder.MIN_THRESHOLD, recorder.HOLD = FORMER_THRESHOLD, 1.0
        transcriber.voice_gain = lambda levels, peak: 1.0
    try:
        yield
    finally:
        recorder.MIN_THRESHOLD, recorder.HOLD, transcriber.voice_gain = saved


def listen(pcm: bytes) -> tuple[list[bytes], str]:
    """The sentences the Recorder sends for this recording, and why it stopped."""
    with tempfile.NamedTemporaryFile(suffix=".raw") as handle:
        handle.write(pcm)
        handle.flush()
        clock = types.SimpleNamespace(now=0.0)

        def monotonic() -> float:
            # Read once at the start, then once per 100 ms frame: the
            # recording's own time, however fast the file is read.
            clock.now += 0.1
            return clock.now

        sent: list[bytes] = []
        settings = copy.deepcopy(config.DEFAULTS)
        instance = recorder.Recorder(settings, on_segment=sent.append)
        build, timer = recorder.capture.build, recorder.time
        recorder.capture.build = lambda *a, **k: capture.Capture("file", ["cat", handle.name])
        recorder.time = types.SimpleNamespace(monotonic=monotonic)
        try:
            rest = instance.record()
        finally:
            recorder.capture.build, recorder.time = build, timer
    return sent + ([rest] if rest else []), instance.reason


def words(text: str) -> list[str]:
    return re.findall(r"[\w'’]+", text.lower())


def distance(reference: list[str], hypothesis: list[str]) -> int:
    row = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, 1):
        previous, row[0] = row[0], i
        for j, hyp in enumerate(hypothesis, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (ref != hyp))
    return row[-1]


def dictate(model: transcriber.Transcriber, sentences: list[bytes], lang: str) -> str:
    model.config["language"] = lang
    heard: list[str] = []
    for sentence in sentences:
        text = model.transcribe(sentence, " ".join(heard))
        if text:
            heard.append(text)
    return " ".join(heard)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", action="store_true")
    parser.add_argument("--models", default="small:cpu,large-v3-turbo:cuda")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    rows = corpus()
    rng = np.random.default_rng(2026)
    voices = {row["id"]: decode(row["source"]) for row in rows}
    recordings = {
        name: {
            row["id"]: recording(
                [whispered(voices[row["id"]], rng) if name == "whispered" else voices[row["id"]]],
                level, rng,
            )
            for row in rows
        }
        for name, level in LEVELS.items()
    }
    # Two sentences said one after the other with a pause between them must
    # stay two, and the silence after them must end the dictation.
    pairs = {
        (name, fluctuating): [
            recording([voices[first["id"]], voices[second["id"]]], LEVELS[name], rng, fluctuating)
            for first, second in zip(rows[0::2], rows[1::2])
        ]
        for name in ("ordinary", "low") for fluctuating in (False, True)
    }
    silences = [
        np.clip(np.round(room(10 * RATE, rng, fluctuating) * floor / NOISE_RMS), -32768, 32767)
        .astype("<i2").tobytes()
        for fluctuating in (False, True)
        for floor in (4.0, 8.0, 16.0, 32.0, 64.0) for _ in range(4)
    ]

    heard: dict[tuple[str, str], dict[str, list[bytes]]] = {}
    for label, is_former in (("before", True), ("after", False)):
        with former(is_former):
            for name in LEVELS:
                sent = {row["id"]: listen(recordings[name][row["id"]])[0] for row in rows}
                heard[label, name] = sent
                missed = sum(not s for s in sent.values())
                cut = sum(len(s) > 1 for s in sent.values())
                print(f"recorder {label:<7} {name:<10} heard whole {len(rows) - missed - cut}/"
                      f"{len(rows)}   cut {cut}   missed {missed}")
            for (name, fluctuating), played in pairs.items():
                results = [listen(pcm) for pcm in played]
                two = sum(len(sent) == 2 for sent, _ in results)
                ended = sum(reason == "silence" for _, reason in results)
                noise = "fluctuating" if fluctuating else "steady"
                print(f"recorder {label:<7} {name:<10} two sentences, {noise} room: split at "
                      f"the pause {two}/{len(played)}   ended by the silence {ended}/{len(played)}")
            noise = [listen(pcm)[0] for pcm in silences]
            heard[label, "silence"] = {str(i): s for i, s in enumerate(noise)}
            print(f"recorder {label:<7} {'silence':<10} heard {sum(bool(s) for s in noise)}"
                  f"/{len(noise)} (half of them fluctuating)")

    if not args.audio:
        return
    for spec in args.models.split(","):
        name, device = spec.split(":")
        settings = copy.deepcopy(config.DEFAULTS)
        settings["model"].update(
            name=name, device=device, compute_type="float16" if device == "cuda" else "int8"
        )
        model = transcriber.Transcriber(settings)
        for level in LEVELS:
            results = []
            for label, is_former in (("before", True), ("after", False)):
                with former(is_former):
                    errors = total = exact = 0
                    for row in rows:
                        text = dictate(model, heard[label, level][row["id"]], row["lang"])
                        wrong = distance(words(row["text"]), words(text))
                        errors += wrong
                        total += len(words(row["text"]))
                        exact += wrong == 0
                        if args.verbose and wrong and label == "after":
                            print(f"    {row['id']}: {text!r}")
                    results.append((errors / total, exact))
            (wer_before, exact_before), (wer_after, exact_after) = results
            print(f"{name} ({device}) {level:<10} WER {wer_before:6.1%} -> {wer_after:6.1%}"
                  f"   exact {exact_before}/{len(rows)} -> {exact_after}/{len(rows)}")
        for label, is_former in (("before", True), ("after", False)):
            with former(is_former):
                spoken = [
                    dictate(model, sent, "fr") for sent in heard[label, "silence"].values()
                ]
            print(f"{name} ({device}) silence {label:<7} text written "
                  f"{sum(bool(t) for t in spoken)}/{len(spoken)}")


if __name__ == "__main__":
    main()
