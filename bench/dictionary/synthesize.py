"""Records the dictionary corpus with Piper voices: one Opus file per sentence.

    python3 bench/dictionary/synthesize.py --piper path/to/piper --voices path/to/voices

Each row gives two recordings, `<id>-first.opus` (the dictation the user
corrects) and `<id>-next.opus` (the same name said later); the controls have
only the second. The voices are those of the other benches, chosen for their
licence: fr_FR-siwis-medium (SIWIS corpus, CC BY 4.0) and en_US-ljspeech-medium
(LJ Speech, public domain), from https://huggingface.co/rhasspy/piper-voices.
Needs ffmpeg.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VOICES = {"fr": "fr_FR-siwis-medium", "en": "en_US-ljspeech-medium"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--piper", default="piper")
    parser.add_argument("--voices", type=Path, required=True)
    parser.add_argument("--only", default="", help="comma-separated ids")
    args = parser.parse_args()
    only = set(filter(None, args.only.split(",")))
    with (HERE / "corpus.tsv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    (HERE / "audio").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        wav = Path(scratch) / "sentence.wav"
        for row in rows:
            if only and row["id"] not in only:
                continue
            voice = args.voices / f"{VOICES[row['lang']]}.onnx"
            for part in ("first", "next"):
                if not row[part]:
                    continue
                subprocess.run([*args.piper.split(), "-m", str(voice), "-f", str(wav)],
                               input=row[part].encode(), check=True, capture_output=True)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                                "-ac", "1", "-c:a", "libopus", "-b:a", "24k",
                                str(HERE / "audio" / f"{row['id']}-{part}.opus")], check=True)


if __name__ == "__main__":
    main()
