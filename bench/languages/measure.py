"""A dictation in French and English: the language of each sentence, then its words.

    ~/.local/share/whisper-desk/venv/bin/python bench/languages/measure.py
    ~/.local/share/whisper-desk/venv/bin/python bench/languages/measure.py --models small:cpu

Needs numpy and ffmpeg, so whisper-desk's own Python, and the models already
downloaded; LD_LIBRARY_PATH on the venv's nvidia/*/lib for CUDA.

Two sets of sentences, French and English, said by the voices of the other
benches:

- short: 50 replies of a few words (corpus.tsv), half of the French ones laden
  with English words — "Je push le fix ce soir" —, where Whisper's detection is
  at its weakest;
- plain: the 84 control recordings of the other benches, which bench/whisper/
  lists, ordinary sentences.

Each set is dictated as one bilingual dictation, French and English sentences
in turn, each one through the Transcriber with what came before as its context,
as the daemon does. It is dictated once per `language` setting: "fr" (the
default, one language forced), "auto" (Whisper picks among all it knows) and
"fr, en" (Whisper picks between the two). For each: the sentences transcribed
in a language other than the one spoken, the word error rate (case and
punctuation aside), and the seconds the Transcriber took per sentence.
"""

from __future__ import annotations

import argparse
import copy
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from whisper_desk import config, transcriber  # noqa: E402

SETTINGS = ("fr", "auto", "fr, en")


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def interleaved(sentences: list[dict[str, str]]) -> list[dict[str, str]]:
    """French and English sentences in turn, as a bilingual user switches."""
    french = [s for s in sentences if s["lang"] == "fr"]
    english = [s for s in sentences if s["lang"] == "en"]
    mixed = []
    for index in range(max(len(french), len(english))):
        mixed += french[index:index + 1] + english[index:index + 1]
    return mixed


def sets() -> dict[str, list[dict[str, str]]]:
    short = [
        {"lang": r["lang"], "audio": str(HERE / "audio" / f"{r['id']}.opus"), "text": r["spoken"]}
        for r in rows(HERE / "corpus.tsv")
    ]
    plain = [
        {"lang": r["lang"], "audio": str(BENCH / bench / "audio" / f"{name}.opus"), "text": r["text"]}
        for r in rows(BENCH / "whisper" / "corpus.tsv")
        for bench, name in [r["source"].split("/")]
    ]
    return {"short": interleaved(short), "plain": interleaved(plain)}


def decode(path: str) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True, check=True,
    ).stdout


def words(text: str) -> list[str]:
    return re.findall(r"[\w'’]+", text.lower().replace("’", "'"))


def distance(reference: list[str], hypothesis: list[str]) -> int:
    row = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, 1):
        previous, row[0] = row[0], i
        for j, hyp in enumerate(hypothesis, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (ref != hyp))
    return row[-1]


def dictate(model: transcriber.Transcriber, sentences: list[dict[str, str]],
            audio: dict[str, bytes], verbose: bool) -> tuple[int, float, float]:
    """Wrong languages, word error rate and seconds per sentence of one dictation."""
    heard: list[str] = []
    languages: list[str] = []
    whisper = model._model
    plain_transcribe = whisper.transcribe

    def transcribe(*args, **kwargs):
        segments, info = plain_transcribe(*args, **kwargs)
        languages.append(info.language)
        return segments, info

    whisper.transcribe = transcribe
    errors = total = wrong = 0
    started = time.monotonic()
    try:
        for sentence in sentences:
            text = model.transcribe(audio[sentence["audio"]], " ".join(heard))
            heard.append(text)
            errors += distance(words(sentence["text"]), words(text))
            total += len(words(sentence["text"]))
            if languages[-1] != sentence["lang"]:
                wrong += 1
                if verbose:
                    print(f"    {sentence['lang']} -> {languages[-1]}: {sentence['text']!r} "
                          f"-> {text!r}")
    finally:
        whisper.transcribe = plain_transcribe
    return wrong, errors / max(1, total), (time.monotonic() - started) / len(sentences)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="small:cpu,large-v3-turbo:cuda")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    dictations = sets()
    audio = {s["audio"]: decode(s["audio"]) for d in dictations.values() for s in d}
    for spec in args.models.split(","):
        name, device = spec.split(":")
        settings = copy.deepcopy(config.DEFAULTS)
        settings["model"].update(name=name, device=device)
        model = transcriber.Transcriber(settings)
        model.load()
        # The first sentence through a model pays for its warming up.
        model.transcribe(audio[dictations["short"][0]["audio"]])
        for language in SETTINGS:
            model.config["language"] = language
            for label, sentences in dictations.items():
                wrong, rate, seconds = dictate(model, sentences, audio, args.verbose)
                print(f"{name} ({device})  {language!r:<9} {label:<6}"
                      f"  wrong language {wrong:>3}/{len(sentences)}"
                      f"  WER {rate:6.1%}  {seconds:5.2f} s/sentence", flush=True)


if __name__ == "__main__":
    main()
