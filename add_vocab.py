"""
add_vocab.py — parse vocabulary markdown files and merge them into the trainer's dictionary.

Usage:
    python add_vocab.py                          (rebuild from scratch: daily/*.md + vocab/*.md)
    python add_vocab.py daily/Day8.md             (incrementally add one new file)
    python add_vocab.py vocab_week3.md Day6.md    (incrementally add several files)

With no arguments, every file in daily/ and vocab/ is (re)parsed and the dictionary
is rebuilt from a clean slate — words that appear in both a Day file and a week
summary are merged into a single entry (deduplicated by word, case-insensitive),
combining every source that mentions them and keeping whichever Vietnamese meaning
is available.

It looks for bullet lines shaped like:
    * **Word** (pos): English definition. *(Vietnamese meaning)*
The Vietnamese part is optional.

Output:
    dictionary.json  — human-readable master dictionary (kept for you)
    dictionary.js    — same data, loaded by vocab-trainer.html
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

DIR = Path(__file__).resolve().parent
DAILY_DIR = DIR / "daily"
VOCAB_DIR = DIR / "vocab"
JSON_PATH = DIR / "dictionary.json"
JS_PATH = DIR / "dictionary.js"

# * **Word** (pos): definition...
ENTRY_RE = re.compile(r"^\s*[*+-]\s+\*\*(.+?)\*\*\s*\(([^)]*)\)\s*:\s*(.+?)\s*$")
# trailing *(Vietnamese)* at the end of the definition
VI_RE = re.compile(r"\*\((.+?)\)\*\s*$")


def parse_file(path: Path):
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ENTRY_RE.match(line)
        if not m:
            continue
        word, pos, definition = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        vi = None
        vi_m = VI_RE.search(definition)
        if vi_m:
            vi = vi_m.group(1).strip()
            definition = definition[: vi_m.start()].strip()
        definition = definition.rstrip("*").strip()
        entries.append(
            {"word": word, "pos": pos, "en": definition, "vi": vi, "source": path.name}
        )
    return entries


def strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"\*(.+?)\*", r"\1", text)


def natural_key(path: Path):
    # sorts Day2 < Day3 < ... < Day10 instead of lexical Day10 < Day2
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", path.stem)]


def merge_entry(by_key, dictionary, e, counters):
    key = e["word"].lower()
    if key in by_key:
        existing = by_key[key]
        changed = False
        # fill in Vietnamese if we didn't have it before
        if e["vi"] and not existing.get("vi"):
            existing["vi"] = e["vi"]
            changed = True
        sources = existing.get("source", "").split(", ")
        if e["source"] not in sources:
            existing["source"] = ", ".join(sources + [e["source"]])
            changed = True
        counters["updated" if changed else "skipped"] += 1
    else:
        e["added"] = date.today().isoformat()
        by_key[key] = e
        dictionary.append(e)
        counters["added"] += 1


def main(argv):
    file_args = argv[1:]
    rebuild = not file_args

    if rebuild:
        # Full rescan: daily/*.md then vocab/*.md, so week summaries (which always
        # carry the Vietnamese meaning) fill in any gaps left by the Day files.
        paths = sorted(DAILY_DIR.glob("*.md"), key=natural_key) + \
                sorted(VOCAB_DIR.glob("*.md"), key=natural_key)
        dictionary, by_key = [], {}
        print(f"Rebuilding dictionary from {len(paths)} files in daily/ and vocab/ ...\n")
    else:
        paths = []
        for arg in file_args:
            path = Path(arg)
            if not path.is_absolute():
                path = DIR / path
            paths.append(path)
        dictionary = json.loads(JSON_PATH.read_text(encoding="utf-8")) if JSON_PATH.exists() else []
        by_key = {e["word"].lower(): e for e in dictionary}

    counters = {"added": 0, "updated": 0, "skipped": 0}
    for path in paths:
        if not path.exists():
            print(f"!! File not found: {path}")
            continue
        entries = parse_file(path)
        if not entries:
            print(f"!! No vocab lines recognized in {path.name}")
            continue
        for e in entries:
            merge_entry(by_key, dictionary, e, counters)
        print(f"Parsed {path.name}: {len(entries)} entries")

    JSON_PATH.write_text(
        json.dumps(dictionary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    js = "window.VOCAB = " + json.dumps(dictionary, ensure_ascii=False, indent=2) + ";\n"
    JS_PATH.write_text(js, encoding="utf-8")

    print(
        f"\nDone. {counters['added']} added, {counters['updated']} updated, "
        f"{counters['skipped']} already known. Dictionary now has {len(dictionary)} words."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
