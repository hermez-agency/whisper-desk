"""Word error rate of the backtrack corpus, before and after the corrections.

    python3 bench/backtrack/measure.py              # on the written sentences
    python3 bench/backtrack/measure.py --audio      # through faster-whisper
    python3 bench/backtrack/measure.py --pauses     # a correction after a pause
    python3 bench/backtrack/measure.py --pauses --audio
    python3 bench/backtrack/measure.py --discard    # "efface ça" after a pause
    python3 bench/backtrack/measure.py --discard --audio
    python3 bench/backtrack/measure.py --clear      # "efface tout" after two sentences
    python3 bench/backtrack/measure.py --clear --audio

--audio needs the whisper-desk venv (whisper-desk's own Python) and the
recordings next to this file; the models are those already downloaded.

--pauses reads pauses.tsv: a sentence, the pause that ends it, then its
correction ("On se voit mardi." … "Non, plutôt mercredi."). With --audio each
half goes through whisper-desk's Transcriber, the second with the first as its
context, as the daemon does. Before: the two sentences typed one after the
other; after: the first one corrected by the second.

--discard reads discard.tsv: a sentence, the pause that ends it, then "efface
ça" / "scratch that" — alone, or with the sentence meant in its place — and ten
controls that only look like one. Before: the two sentences typed one after the
other; after: what the daemon leaves at the cursor.

--clear reads clear.tsv: two sentences, each ended by a pause, then "efface
tout" / "scratch all that" — alone, or with the text meant in their place — and
ten controls that only look like one. Each sentence goes through the
Transcriber with those before it as its context. Before: the three sentences
typed one after the other; after: what the daemon leaves at the cursor.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from whisper_desk import backtrack, punctuation  # noqa: E402


def corpus(name: str = "corpus.tsv") -> list[dict[str, str]]:
    with (HERE / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def words(text: str) -> list[str]:
    return re.findall(r"[\w'’]+", text.lower())


def distance(reference: list[str], hypothesis: list[str]) -> int:
    row = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, 1):
        previous, row[0] = row[0], i
        for j, hyp in enumerate(hypothesis, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (ref != hyp))
    return row[-1]


def wer(pairs: list[tuple[str, str]]) -> float:
    errors = sum(distance(words(ref), words(hyp)) for ref, hyp in pairs)
    return errors / max(1, sum(len(words(ref)) for ref, _ in pairs))


def transcripts(model: str, device: str) -> dict[str, str]:
    from faster_whisper import WhisperModel

    compute = "float16" if device == "cuda" else "int8"
    whisper = WhisperModel(model, device=device, compute_type=compute)
    out = {}
    for row in corpus():
        segments, _ = whisper.transcribe(
            str(HERE / "audio" / f"{row['id']}.opus"), language=row["lang"],
            beam_size=5, vad_filter=True, condition_on_previous_text=False,
        )
        out[row["id"]] = " ".join(s.text.strip() for s in segments).strip()
    return out


def report(label: str, raw: dict[str, str], verbose: bool) -> None:
    rows = corpus()
    for group, keep in (("corrections", lambda r: not r["id"].startswith("ctl")),
                        ("controls", lambda r: r["id"].startswith("ctl"))):
        chosen = [r for r in rows if keep(r)]
        before = [(r["expected"], raw[r["id"]]) for r in chosen]
        after = [(r["expected"], backtrack.apply(raw[r["id"]])) for r in chosen]
        exact = sum(words(e) == words(h) for e, h in after)
        print(f"{label:<28} {group:<12} WER {wer(before):6.1%} -> {wer(after):6.1%}"
              f"   exact {exact}/{len(chosen)}")
        if verbose:
            for row, (expected, fixed) in zip(chosen, after):
                if words(expected) != words(fixed):
                    print(f"    {row['id']}: {raw[row['id']]!r} -> {fixed!r}")


def decode(path: Path) -> bytes:
    import subprocess

    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path),
         "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True, check=True,
    ).stdout


def paused_transcripts(model: str, device: str,
                       name: str = "pauses.tsv") -> dict[str, tuple[str, str]]:
    import copy

    from whisper_desk import config, transcriber

    settings = copy.deepcopy(config.DEFAULTS)
    settings["model"].update(name=model, device=device)
    out = {}
    for lang in ("fr", "en"):
        settings["model"]["language"] = lang
        whisper = transcriber.Transcriber(settings)
        whisper.load()
        for row in corpus(name):
            if row["lang"] != lang:
                continue
            said: list[str] = []
            for half in range(1, 3 if "third" not in row else 4):
                audio = decode(HERE / "audio" / f"{row['id']}-{half}.opus")
                said.append(whisper.transcribe(audio, " ".join(said)))
            out[row["id"]] = tuple(said)
    return out


def report_pauses(label: str, raw: dict[str, tuple[str, str]], verbose: bool) -> None:
    rows = corpus("pauses.tsv")
    for group, keep in (("corrections", lambda r: "ctl" not in r["id"]),
                        ("controls", lambda r: "ctl" in r["id"])):
        chosen = [r for r in rows if keep(r)]
        typed = {r["id"]: punctuation.join(list(raw[r["id"]])) for r in chosen}
        corrected = {r["id"]: backtrack.across(*raw[r["id"]]) for r in chosen}
        fixed = {r["id"]: corrected[r["id"]] or typed[r["id"]] for r in chosen}
        rewritten = sum(corrected[r["id"]] is not None for r in chosen)
        before = [(r["expected"], typed[r["id"]]) for r in chosen]
        after = [(r["expected"], fixed[r["id"]]) for r in chosen]
        exact_before = sum(words(e) == words(h) for e, h in before)
        exact = sum(words(e) == words(h) for e, h in after)
        print(f"{label:<28} {group:<12} WER {wer(before):6.1%} -> {wer(after):6.1%}"
              f"   exact {exact_before}/{len(chosen)} -> {exact}/{len(chosen)}"
              f"   rewritten {rewritten}/{len(chosen)}")
        if verbose:
            for row in chosen:
                if words(row["expected"]) != words(fixed[row["id"]]):
                    print(f"    {row['id']}: {raw[row['id']]!r} -> {fixed[row['id']]!r}")


def at_cursor(first: str, second: str) -> tuple[str, bool]:
    """What the daemon leaves at the cursor, and whether the command was carried out."""
    rest = backtrack.discarded(second)
    if rest is None:
        return punctuation.join([first, second]), False
    return rest, True


def report_discard(label: str, raw: dict[str, tuple[str, str]], verbose: bool) -> None:
    rows = corpus("discard.tsv")
    for group, keep in (("commands", lambda r: "ctl" not in r["id"]),
                        ("controls", lambda r: "ctl" in r["id"])):
        chosen = [r for r in rows if keep(r)]
        typed = {r["id"]: punctuation.join(list(raw[r["id"]])) for r in chosen}
        after = {r["id"]: at_cursor(*raw[r["id"]]) for r in chosen}
        carried = sum(after[r["id"]][1] for r in chosen)
        exact_before = sum(words(r["expected"]) == words(typed[r["id"]]) for r in chosen)
        exact = sum(words(r["expected"]) == words(after[r["id"]][0]) for r in chosen)
        print(f"{label:<28} {group:<10} exact at the cursor {exact_before}/{len(chosen)}"
              f" -> {exact}/{len(chosen)}   carried out {carried}/{len(chosen)}")
        if verbose:
            for row in chosen:
                if words(row["expected"]) != words(after[row["id"]][0]):
                    print(f"    {row['id']}: {raw[row['id']]!r} -> {after[row['id']][0]!r}")


def cleared_at_cursor(said: tuple[str, ...]) -> tuple[str, bool]:
    """What the daemon leaves at the cursor after "efface tout", and whether it was carried out."""
    rest = backtrack.cleared(said[-1])
    if rest is None:
        return punctuation.join(list(said)), False
    return rest, True


def report_clear(label: str, raw: dict[str, tuple[str, ...]], verbose: bool) -> None:
    rows = corpus("clear.tsv")
    for group, keep in (("commands", lambda r: "ctl" not in r["id"]),
                        ("controls", lambda r: "ctl" in r["id"])):
        chosen = [r for r in rows if keep(r)]
        typed = {r["id"]: punctuation.join(list(raw[r["id"]])) for r in chosen}
        after = {r["id"]: cleared_at_cursor(raw[r["id"]]) for r in chosen}
        carried = sum(after[r["id"]][1] for r in chosen)
        exact_before = sum(words(r["expected"]) == words(typed[r["id"]]) for r in chosen)
        exact = sum(words(r["expected"]) == words(after[r["id"]][0]) for r in chosen)
        print(f"{label:<28} {group:<10} exact at the cursor {exact_before}/{len(chosen)}"
              f" -> {exact}/{len(chosen)}   carried out {carried}/{len(chosen)}")
        if verbose:
            for row in chosen:
                if words(row["expected"]) != words(after[row["id"]][0]):
                    print(f"    {row['id']}: {raw[row['id']]!r} -> {after[row['id']][0]!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", action="store_true")
    parser.add_argument("--pauses", action="store_true")
    parser.add_argument("--discard", action="store_true")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--models", default="small:cpu,large-v3-turbo:cuda")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    if args.clear:
        report_clear("written sentences",
                     {r["id"]: (r["first"], r["second"], r["third"])
                      for r in corpus("clear.tsv")},
                     args.verbose)
        if args.audio:
            for spec in args.models.split(","):
                model, device = spec.split(":")
                report_clear(f"{model} ({device})",
                             paused_transcripts(model, device, "clear.tsv"), args.verbose)
        return
    if args.discard:
        report_discard("written sentences",
                       {r["id"]: (r["first"], r["second"]) for r in corpus("discard.tsv")},
                       args.verbose)
        if args.audio:
            for spec in args.models.split(","):
                model, device = spec.split(":")
                report_discard(f"{model} ({device})",
                               paused_transcripts(model, device, "discard.tsv"), args.verbose)
        return
    if args.pauses:
        report_pauses("written sentences",
                      {r["id"]: (r["first"], r["second"]) for r in corpus("pauses.tsv")},
                      args.verbose)
        if args.audio:
            for spec in args.models.split(","):
                model, device = spec.split(":")
                report_pauses(f"{model} ({device})", paused_transcripts(model, device),
                              args.verbose)
        return
    report("written sentences", {r["id"]: r["spoken"] for r in corpus()}, args.verbose)
    if args.audio:
        for spec in args.models.split(","):
            model, device = spec.split(":")
            report(f"{model} ({device})", transcripts(model, device), args.verbose)


if __name__ == "__main__":
    main()
