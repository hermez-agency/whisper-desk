"""Numbered lists said aloud, before and after they are written as lists.

    python3 bench/lists/measure.py              # on the written sentences
    python3 bench/lists/measure.py --audio      # through faster-whisper

Two ways each recording reaches the rules: whole, as when the as-you-go dictation
is off, and cut after each sentence, as the as-you-go dictation does when the
speaker pauses after every item. Two figures: the lists laid out exactly as
expected (same lines, same numbers), and the error rate on words, marks, line
breaks and item numbers. --audio needs the whisper-desk venv (whisper-desk's own
Python) and the recordings next to this file; the models are those already
downloaded. "Before" is the text whisper-desk wrote until now, corrections,
hesitations, spoken punctuation and developer syntax included; "after" adds the
lists.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from whisper_desk import backtrack, casing, hesitations, lists, punctuation  # noqa: E402


def corpus() -> list[dict[str, str]]:
    with (HERE / "corpus.tsv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for row in rows:
        row["expected"] = row["expected"].replace("\\n", "\n")
    return rows


def tokens(text: str) -> list[str]:
    return re.findall(r"\n|[0-9]+\.(?= )|[\w'’-]+|[:?!]", text.lower())


def layout(text: str) -> list[str]:
    """Each line reduced to its item number, or to a dot when it is no item."""
    return [m[1] if (m := re.match(r"([0-9]+)\. ", line)) else "·" for line in text.split("\n")]


def distance(reference: list[str], hypothesis: list[str]) -> int:
    row = list(range(len(hypothesis) + 1))
    for i, ref in enumerate(reference, 1):
        previous, row[0] = row[0], i
        for j, hyp in enumerate(hypothesis, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (ref != hyp))
    return row[-1]


def error_rate(pairs: list[tuple[str, str]]) -> float:
    errors = sum(distance(tokens(ref), tokens(hyp)) for ref, hyp in pairs)
    return errors / max(1, sum(len(tokens(ref)) for ref, _ in pairs))


def today(text: str) -> str:
    return casing.apply(punctuation.apply(hesitations.apply(backtrack.apply(text))))


def sentences(text: str) -> list[str]:
    # Not after "1.": Whisper writes the item number and its item together.
    return [s for s in re.split(r"(?<=[.?!])(?<![0-9]\.)\s+", text.strip()) if s]


def dictated(pieces: list[str], listed: bool) -> str:
    """The pieces inserted one after the other, as the daemon does."""
    parts: list[str] = []
    pending = lists.Pending()
    for piece in pieces:
        piece = today(piece)
        if listed:
            piece = pending.feed(piece, punctuation.join(parts))
            if piece is None:
                continue
        parts.append(piece)
    if pending.held:
        parts.append(pending.flush())
    return punctuation.join(parts)


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
    groups = (
        ("lists fr", lambda r: r["id"].startswith("fr")),
        ("lists en", lambda r: r["id"].startswith("en")),
        ("controls", lambda r: r["id"].startswith("ctl")),
    )
    for cut, split in (("whole", lambda t: [t]), ("by sentence", sentences)):
        for group, keep in groups:
            chosen = [r for r in rows if keep(r)]
            before = [(r["expected"], dictated(split(raw[r["id"]]), False)) for r in chosen]
            after = [(r["expected"], dictated(split(raw[r["id"]]), True)) for r in chosen]
            laid_before = sum(layout(e) == layout(h) for e, h in before)
            laid = sum(layout(e) == layout(h) for e, h in after)
            exact = sum(tokens(e) == tokens(h) for e, h in after)
            line = (f"{label:<26} {cut:<11} {group:<9} errors {error_rate(before):6.1%} -> "
                    f"{error_rate(after):6.1%}   laid out {laid_before} -> {laid}/{len(chosen)}"
                    f"   exact {exact}/{len(chosen)}")
            if group == "controls":
                changed = sum(b != a for (_, b), (_, a) in zip(before, after))
                line += f"   changed {changed}/{len(chosen)}"
            print(line)
            if verbose:
                for row, (expected, written) in zip(chosen, after):
                    if tokens(expected) != tokens(written):
                        print(f"    {row['id']}: {raw[row['id']]!r} -> {written!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", action="store_true")
    parser.add_argument("--models", default="small:cpu,large-v3-turbo:cuda")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    if not args.audio:
        report("written sentences", {r["id"]: r["spoken"] for r in corpus()}, args.verbose)
        return
    for spec in args.models.split(","):
        model, device = spec.split(":")
        report(f"{model} ({device})", transcripts(model, device), args.verbose)


if __name__ == "__main__":
    main()
