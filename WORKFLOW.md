# Anki HSK Vocabulary Workflow

## Prerequisites

Activate the virtual environment before running any command:

```bash
.venv\Scripts\activate
```

Anki must be running with the AnkiConnect plugin installed (default port 8765).

## Project structure

```
main.py                  # Entry point — dispatches all commands
src/                     # Python source code
  shared.py              #   Shared utilities (Google Translate, caches, constants)
  anki_hsk.py            #   AnkiConnect operations: export / import / pick / models
  cleanup_tags.py        #   Enrich definitions, POS tags, similar-def fix, decompose
  generate_new_words.py  #   Extract vocabulary from documents → pick_words.txt
  go.py                  #   Shortcut: export → generate pick list
  clean_empty.py         #   Shortcut: export → translate empty → tags → import
tests/                   # Unit tests
  test_shared.py         #   Tests for translation, pinyin, English matching
never_propose_words.txt  # Words to exclude (char or char | pinyin | english)
pick_words.txt           # Human-editable word list (generated, intermediate)
data/                    # Deck data
  myhsk1_data.json       #   Current deck export
  myhsk1_data.bak.json   #   Backup for diff-based import
  history/               #   Historical backups (one per day, auto-created on export)
cache/                   # Auto-generated caches
  pos_cache.json
  char_info_cache.json
templates/               # Anki card templates
newwords/                # Input files (.pptx, .doc, .txt) for new vocabulary
```

---

## Main workflow

Every session starts with an **export** and ends with an **import**. In between, pick optional steps as needed.

All commands are run through `main.py`:

```
python main.py export              # 1. Always first — export deck → myhsk1_data.json
                                   #    (also saves daily snapshot to data/history/)

# ── Optional: add new words ─────────────────────────────────────────
python main.py generate            # 2a. Extract words from newwords/ → pick_words.txt
# edit pick_words.txt              # 2b. Delete unwanted lines, fix definitions
python main.py pick                # 2c. Add remaining words to Anki

# ── Optional: clean up ──────────────────────────────────────────────
python main.py cleanup             # 3.  Enrich definitions + set POS/count tags
                                   #     (writes missing single chars to pick_words.txt)
# edit pick_words.txt              # 3b. (if single chars were found) keep wanted chars
python main.py pick                # 3c. (if single chars were found) add them

python main.py import              # 4. Always last — push changes back to Anki
```

| Step | Command | What it does |
|------|---------|--------------|
| 1 | `python main.py export` | Dumps deck to `myhsk1_data.json` (+ backup `.bak.json` + daily snapshot in `data/history/`). Always run first. |
| 2a | `python main.py generate` | *(optional)* Extracts new words from `newwords/`, looks up pinyin/English/POS, decomposes multi-char words, writes `pick_words.txt`, warns about collisions |
| 2b | *(manual)* | Open `pick_words.txt` — delete lines you don't want, fix pinyin/translations. `#` = comment. Permanent exclusions go in `never_propose_words.txt` |
| 2c | `python main.py pick` | *(optional)* Reads `pick_words.txt` and adds each entry as a new Anki card |
| 3 | `python main.py cleanup` | *(optional)* Enriches short definitions, auto-fixes similar definitions, removes pinyin lookalikes, sets POS tags, adds `single`/`dual` tags, decomposes multi-char words → missing single chars to `pick_words.txt`. See [options](#cleanup-options) below |
| 4 | `python main.py import` | Pushes updated fields + tags back to Anki (only changed notes are sent). Always run last. |

> **Input formats for `newwords/`:**
> - `.pptx` / `.doc` — Chinese segments are extracted and filtered against known-good characters
> - `.txt` (e.g. `mylist.txt`) — One Chinese word per line, `#` = comment. No garbage filter (trusted input)

---

## Shortcuts

| Command | Equivalent to | Use when |
|---------|--------------|----------|
| `python main.py go` | export → generate | You dropped files in `newwords/` and want a pick list |
| `python main.py clean-empty` | export → retranslate empty → tags → import | You have cards with Chinese but no English |

---

## Testing

```bash
python -m unittest discover -s tests -v
```

---

## Cleanup options

`cleanup` supports `--mode` and `--scope` flags to run selectively:

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--mode` | `translation`, `retranslate`, `tags`, `all` | `all` | What to update |
| `--scope` | `new`, `existing`, `empty`, `all` | `all` | Which words to process |

**Scope values:**
- `all` — Every card
- `new` — Cards not in the backup (added since last export)
- `existing` — Cards present in the backup
- `empty` — Cards with no English definition (Chinese-only)

**Examples:**

```bash
python main.py cleanup                                 # Enrich + tags for all words (default)
python main.py cleanup --mode translation              # Enrich short definitions only
python main.py cleanup --mode retranslate              # Replace ALL definitions with fresh Google Translate
python main.py cleanup --mode retranslate --scope new  # Retranslate new words only
python main.py cleanup --mode retranslate --scope empty # Translate cards with no English
python main.py cleanup --mode tags                     # Update tags only
python main.py cleanup --mode tags --scope existing    # Update tags for existing words only
```

**Modes explained:**
- `translation` — Only enriches short definitions (≤3 words, no commas) by appending Google Translate alternatives
- `retranslate` — **Replaces** all English definitions with a fresh Google Translate lookup (primary + up to 3 alternatives). Use this to clean up old/redundant definitions like `"Tall/high, tall, expensive, lofty"`
- `tags` — Only updates POS and character-count tags
- `all` — Enrich translations + update tags (default, same as running `translation` + `tags`)

**Pinyin lookalike removal:** When updating translations, English words that match the card's pinyin (ignoring tones) are automatically removed to avoid spoiling flashcard answers (e.g. "shu" removed from 舒/shū). Common English words like "he", "she", "can" are safe-listed and never removed.

**Similarity auto-fix:** When updating translations (`--mode translation` or `--mode all`), the script compares English definitions across all cards. Pairs sharing ≥50% of meaningful words are detected and automatically differentiated by fetching fresh Google Translate alternatives and preferring unique words that don't appear in the conflicting card's definition. Pairs that can't be improved are still reported.

**Character count tags:** All cards receive a `single` (1-char) or `dual` (2-char) tag automatically.

> First run fetches POS + alternatives from Google (~7 min for ~1400 words). Results are cached in `pos_cache.json` and `char_info_cache.json` — re-runs are instant.

---

## Historical backups

Every `export` automatically saves a daily snapshot to `data/history/myhsk1_data_YYYYMMDD.json`. Only one file per day is kept (later exports on the same day overwrite the earlier one).

---

## Other useful commands

| Command | What it does |
|---------|--------------|
| `python main.py models` | List available note types and their fields |
