# 📘 Vocab Trainer

A small offline app to practice the vocabulary you collect in your daily markdown lessons.
No install, no internet — it runs in your browser.

## Folders

| Folder | What goes here |
|---|---|
| `daily/` | Your day-by-day lesson files — `Day2.md`, `Day3.md`, … Each has stories plus a vocab list. |
| `vocab/` | Your weekly round-up files — `vocab_week1.md`, `vocab_week2.md`, … Flat word lists, always with Vietnamese. |

## Files

| File | What it is |
|---|---|
| `vocab-trainer.html` | The app. Double-click to open it in your browser. |
| `add_vocab.py` | Parser — reads your `.md` files and builds the dictionary. |
| `dictionary.json` | Your master word list (readable, deduplicated, kept in sync automatically). |
| `dictionary.js` | Same data in the format the app loads. Don't edit by hand. |

## Daily workflow

### 1. Add new vocabulary

The same word often shows up twice — once in a `daily/DayN.md` lesson, again later in
that week's `vocab/vocab_weekN.md` round-up. The parser **deduplicates by word**, so you
never end up practicing the same word as two separate cards; it just merges the sources
and keeps whichever Vietnamese meaning is available (weekly files always have one).

**After adding a new file to `daily/` or `vocab/`**, run the parser with no arguments —
it rescans both folders completely and rebuilds the dictionary from a clean, deduplicated
slate:

```powershell
python add_vocab.py
```

Or just tell Claude Code: **"rebuild the vocab dictionary"**.

If you only want to add one specific file without rescanning everything, pass it explicitly:

```powershell
python add_vocab.py daily/Day8.md
python add_vocab.py vocab/vocab_week4.md daily/Day8.md
```

Words already in the dictionary are skipped (but a Vietnamese meaning is filled in
if the new file has one and the old entry didn't). Your markdown lines are recognized
as long as they look like:

```markdown
* **Word** (pos): English definition. *(Nghĩa tiếng Việt)*
```

The `*(Vietnamese)*` part is optional — Day-file lists without it work too, since the
matching weekly file usually fills it in later.

### 2. Practice

Start the server (above) and open **http://127.0.0.1:5000**. The app shows you an English
definition — type the word and press **Enter**:

- 🟩 **Green** — correct, moves on automatically
- 🟥 **Red + shake** — wrong, try again
- 🟨 **Yellow** — you're one letter off; fix your spelling

Controls:

- **🇻🇳 VN toggle** (top right) — also show the Vietnamese meaning under the definition.
  Your choice is remembered.
- **Source dropdown** — practice one file (grouped as *Daily lessons* / *Weekly summaries*)
  or all 150 words at once. A word learned in `Day5.md` and reviewed in `vocab_week2.md`
  shows up under both, but only ever as one card.
- **💡 Hint** — reveals the word one letter at a time.
- **👁 Show answer** — gives up on this word; it comes back a few cards later in the
  same session.
- **⏭ Skip** — skip the word (counted as a miss).

Keyboard shortcuts (no mouse needed):

| Key | Action |
|---|---|
| `Enter` | Check your answer |
| `Ctrl+Q` | Toggle Vietnamese mode |
| `Ctrl+H` | Hint (press again for more letters) |
| `Ctrl+Enter` | Show the answer |
| `Ctrl+→` | Skip the word |

### Translation and pronunciation (Python server)

Reading-mode translation and the spoken pronunciation both run in `tts_app/app.py`
(Flask). The HTML only draws the UI and calls `/translate` and `/speak`.

One-time setup (the venv and model files are not in git):

- **Windows:** double-click `tts_app\setup.bat`, then `tts_app\start.bat` to run the app.
- **macOS / Linux:** `bash tts_app/setup.sh`.

The setup installs whatever the laptop is missing: Git Bash (Windows, via winget), Python 3.12
(if no Python 3.10-3.12 is found; per-user, no admin rights), the Visual C++ runtime (Windows;
asks for permission once) and curl. It then creates the venv, installs the libraries (CUDA builds
when an NVIDIA GPU with its driver is present, otherwise CPU), downloads the Kokoro files and
converts the VinAI translation model to `tts_app/vinai-en2vi-ct2/` (that one-off conversion uses a
temporary venv with PyTorch, deleted afterwards). It is safe to run again. To start by hand:

```powershell
cd tts_app
.venv\Scripts\python app.py
```

Then open **http://127.0.0.1:5000** (the server also serves the page — no `http.server` needed).

- Translation: [VinAI Translate en→vi v2](https://huggingface.co/vinai/vinai-translate-en2vi-v2) (mBART, fine-tuned for English→Vietnamese; AGPL-3.0), run locally from `tts_app/vinai-en2vi-ct2/` with CTranslate2 (int8) on the GPU, or the CPU if there is none. Passages are split into sentences and translated as one batch. The terminal prints `Translator running on CUDA` or `CPU`.
- Speech: Kokoro-82M, run locally from `tts_app/kokoro-v1.0.onnx` + `voices-v1.0.bin`. Runs on the NVIDIA GPU (CUDA) when available, otherwise on the CPU. The terminal prints `Kokoro running on CUDA` or `CPU` at start-up.
- **Quiz mode** — the word is spoken when you get it right or show the answer.
- **Reading mode** — highlight text, then **🌐 Dịch** (`T`) or **🔊 Nghe** (`S`).

### Reading passages (`passages.jsonl`)

All reading passages live in one text file, **one JSON object per line**, so git diffs stay
small (deleting a passage = one removed line). Fields: `id`, `day` (empty for free passages),
`topic`, `title`, `level` (B1/B2/C1), `source` (`daily` or `claude`), `paragraphs`.

- 62 passages come from your daily lessons; 100 free-topic passages (20 topics × 5, TOEIC/IELTS styles).
- Reading mode: pick a **topic** (or all), **▶ Continue** jumps to a random passage in that topic.
- **🗑 Xóa bài này** removes the passage from `passages.jsonl` for good — use it once you know a passage by heart.
- To add your own, append a line to the file (copy an existing one and change the fields).
- `add_vocab.py` no longer touches passages; it only rebuilds the dictionary.
- Voice, model name and length limit are constants at the top of `app.py`.

### 3. Spaced repetition (automatic)

Every word sits in a level from 0 to 4. Answer correctly on the first try and it
moves up a level; miss it and it drops back to 0. The level decides when you see
it again:

| Level | 0 | 1 | 2 | 3 | 4 (mastered) |
|---|---|---|---|---|---|
| Comes back after | today | 1 day | 2 days | 4 days | 7 days |

Each day the app only quizzes you on **due** words — the header shows how many.
When nothing is due you can still press **"Practice all words anyway"**.

Progress is saved in your browser (localStorage), so keep using the same browser.
Clearing browser data resets your levels — the dictionary itself is safe in
`dictionary.json`.

## Tips

- Aim to clear the "Due" counter every day — that's the whole system.
- New words always start at level 0, so they appear the same day you add them.
- Rebuilding (`python add_vocab.py` with no arguments) is safe to run any time — it only
  regenerates `dictionary.json`/`dictionary.js` from your `daily/` and `vocab/` files.
  Your practice progress (levels/due dates) lives separately in the browser and is untouched.
- If a word was parsed wrong, fix the source `.md` file and rebuild, rather than editing
  `dictionary.json` by hand — a rebuild would overwrite manual edits.



