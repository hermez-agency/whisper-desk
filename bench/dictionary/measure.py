"""Does a correction made once teach whisper-desk the name for the next time?

    python3 bench/dictionary/measure.py              # the corrections written
    python3 bench/dictionary/measure.py --audio      # through faster-whisper

Written: for each correction in corrections.tsv, the words learned against
those a user would want learned. --audio: each name of corpus.tsv is said in
a first dictation, transcribed with an empty vocabulary and corrected into
the sentence said, as a user would in the history; what the correction
teaches joins the vocabulary, one name after the other. The name is then
said in another sentence: is it written right, before and after? The control
sentences check that the vocabulary grown on the way mars nothing else.

--replacements goes one step further, as Wispr Flow's "Correct a misspelling":
the first dictation is said again with the vocabulary learned; where the
name is still written wrong, the user saves what Whisper wrote and the name
as a replacement. Is the name right in the other sentence, said apart, with
the vocabulary and the replacements — and do the controls stay as they were?

--audio needs the whisper-desk venv (whisper-desk's own Python) and the
recordings next to this file; the models are those already downloaded. On
CUDA, the venv's own NVIDIA libraries go in LD_LIBRARY_PATH, as bin/whisper-desk
puts them.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from whisper_desk import replacements, vocabulary  # noqa: E402


def rows(name: str) -> list[dict[str, str]]:
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


def written(verbose: bool) -> None:
    corrections = rows("corrections.tsv")
    wanted = learned = right = exact = 0
    for row in corrections:
        expected = [word for word in row["learned"].split("|") if word]
        got = vocabulary.learned(row["before"], row["after"])
        wanted, learned = wanted + len(expected), learned + len(got)
        right += len(set(got) & set(expected))
        exact += got == expected
        if verbose and got != expected:
            print(f"    {row['id']}: {got} instead of {expected}")
    teaching = [row for row in corrections if row["learned"]]
    quiet = sum(not vocabulary.learned(r["before"], r["after"])
                for r in corrections if not r["learned"])
    print(f"{'written corrections':<28} learned {right}/{wanted} wanted words, "
          f"{learned - right} unwanted   exact {exact}/{len(corrections)}   "
          f"controls quiet {quiet}/{len(corrections) - len(teaching)}")


def transcribe(whisper, row: dict[str, str], part: str, hotwords: str | None) -> str:
    segments, _ = whisper.transcribe(
        str(HERE / "audio" / f"{row['id']}-{part}.opus"), language=row["lang"],
        beam_size=5, vad_filter=True, condition_on_previous_text=False,
        hotwords=hotwords or None,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


TOKEN = re.compile(r"\w+")


def misspelled(heard: str, said: str, term: str) -> str | None:
    """What Whisper wrote where the sentence said `term`, if it is not the term."""
    if term in heard:
        return None
    heard_tokens = list(TOKEN.finditer(heard))
    said_words = [word.casefold() for word in TOKEN.findall(said)]
    term_words = [word.casefold() for word in TOKEN.findall(term)]
    start = next((i for i in range(len(said_words))
                  if said_words[i:i + len(term_words)] == term_words), None)
    if start is None:
        return None
    end = start + len(term_words)
    matcher = difflib.SequenceMatcher(
        None, said_words, [token.group().casefold() for token in heard_tokens], autojunk=False)
    span = [j for tag, i1, i2, j1, j2 in matcher.get_opcodes()
            if i1 < end and i2 > start for j in range(j1, j2)]
    # Nothing written for it, or a whole stretch of the sentence: no entry to save.
    if not span or len(span) > len(term_words) + 3:
        return None
    return heard[heard_tokens[span[0]].start():heard_tokens[span[-1]].end()]


def audio(model: str, device: str, verbose: bool, with_replacements: bool) -> None:
    from faster_whisper import WhisperModel

    whisper = WhisperModel(model, device=device,
                           compute_type="float16" if device == "cuda" else "int8")
    corpus = rows("corpus.tsv")
    names = [row for row in corpus if row["term"]]
    controls = [row for row in corpus if not row["term"]]

    # One user per language: the French names do not help the English ones.
    learned_vocabulary: dict[str, str] = {}
    taught = misheard = 0
    for row in names:
        heard = transcribe(whisper, row, "first", None)
        learned_vocabulary[row["lang"]], added = vocabulary.merge(
            learned_vocabulary.get(row["lang"], ""), vocabulary.learned(heard, row["first"]))
        misheard += row["term"] not in heard
        taught += row["term"] in added
        if verbose:
            print(f"    {row['id']}: {heard!r} taught {added}")

    # The replacements a user saves from the first dictation, said again with
    # the vocabulary learned: what Whisper still writes for the name.
    learned_replacements: dict[str, dict[str, str]] = {}
    if with_replacements:
        for row in names:
            heard = transcribe(whisper, row, "first", learned_vocabulary.get(row["lang"]))
            wrong = misspelled(heard, row["first"], row["term"])
            if wrong:
                learned_replacements.setdefault(row["lang"], {})[wrong] = row["term"]
            if verbose:
                print(f"    {row['id']}: {heard!r} -> {wrong!r}")

    for label, rows_, kind in (("names", names, "names"), ("controls", controls, "controls")):
        before = [transcribe(whisper, row, "next", None) for row in rows_]
        after = [transcribe(whisper, row, "next", learned_vocabulary.get(row["lang"]))
                 for row in rows_]
        if with_replacements:
            after = [replacements.apply(text, learned_replacements.get(row["lang"], {}))
                     for row, text in zip(rows_, after)]
            label += "+repl"
        pairs_before = [(row["next"], text) for row, text in zip(rows_, before)]
        pairs_after = [(row["next"], text) for row, text in zip(rows_, after)]
        line = f"{model + ' (' + device + ')':<28} {label:<9} WER {wer(pairs_before):6.1%} -> {wer(pairs_after):6.1%}"
        if kind == "names":
            hits_before = sum(row["term"] in text for row, text in zip(rows_, before))
            hits_after = sum(row["term"] in text for row, text in zip(rows_, after))
            line += (f"   name written {hits_before}/{len(rows_)} -> {hits_after}/{len(rows_)}"
                     f"   misheard first {misheard}, taught {taught}")
        else:
            changed = sum(a != b for a, b in zip(before, after))
            line += f"   changed {changed}/{len(rows_)}"
        print(line)
        if verbose:
            for row, old, new in zip(rows_, before, after):
                if old != new or words(new) != words(row["next"]):
                    print(f"    {row['id']}: {old!r} -> {new!r}")
    if verbose:
        for lang, learned in learned_vocabulary.items():
            print(f"    vocabulary learned ({lang}): {learned}")
        for lang, table in learned_replacements.items():
            print(f"    replacements saved ({lang}): {table}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", action="store_true")
    parser.add_argument("--models", default="small:cpu,large-v3-turbo:cuda")
    parser.add_argument("--replacements", action="store_true",
                        help="with --audio: the misspellings left saved as replacements")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    written(args.verbose)
    if args.audio:
        for spec in args.models.split(","):
            model, device = spec.split(":")
            audio(model, device, args.verbose, args.replacements)


if __name__ == "__main__":
    main()
