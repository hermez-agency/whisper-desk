"""Records the corpus again with Piper voices: one Opus file per sentence.

    python3 bench/backtrack/synthesize.py --piper path/to/piper --voices path/to/voices

The two sentences of each row of pauses.tsv are recorded apart, <id>-1 and <id>-2:
the daemon hears them as two sentences, the pause between them having ended the first.

The voices are those of the recordings in audio/, chosen for their licence:
fr_FR-siwis-medium (SIWIS corpus, CC BY 4.0) and en_US-ljspeech-medium (LJ Speech,
public domain), from https://huggingface.co/rhasspy/piper-voices. Needs ffmpeg.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VOICES = {"fr": "fr_FR-siwis-medium", "en": "en_US-ljspeech-medium"}


def record(piper: str, voice: Path, text: str, wav: Path, target: Path) -> None:
    subprocess.run([piper, "-m", str(voice), "-f", str(wav)],
                   input=text.encode(), check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                    "-ac", "1", "-c:a", "libopus", "-b:a", "24k", str(target)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--piper", default="piper")
    parser.add_argument("--voices", type=Path, required=True)
    parser.add_argument("--only", default="", help="comma-separated ids")
    args = parser.parse_args()
    only = set(filter(None, args.only.split(",")))
    with (HERE / "corpus.tsv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    with (HERE / "pauses.tsv").open(encoding="utf-8") as handle:
        pauses = list(csv.DictReader(handle, delimiter="\t"))
    with tempfile.TemporaryDirectory() as scratch:
        wav = Path(scratch) / "sentence.wav"
        for row in rows:
            if only and row["id"] not in only:
                continue
            voice = args.voices / f"{VOICES[row['lang']]}.onnx"
            record(args.piper, voice, row["spoken"], wav, HERE / "audio" / f"{row['id']}.opus")
        for row in pauses:
            if only and row["id"] not in only:
                continue
            voice = args.voices / f"{VOICES[row['lang']]}.onnx"
            for half in ("1", "2"):
                text = row["first" if half == "1" else "second"]
                record(args.piper, voice, text, wav, HERE / "audio" / f"{row['id']}-{half}.opus")


if __name__ == "__main__":
    main()
