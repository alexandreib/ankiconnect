# Anki HSK Vocabulary Workflow

## Prerequisites

Activate the virtual environment before running any command:

```bash
.venv\Scripts\activate
```

Anki must be running with the AnkiConnect plugin installed (default port 8765).

## File overview

| File / Directory | Purpose |
|------------------|---------|
| `shared.py` | Shared utilities (Google Translate, caches, document extraction, constants) |
| `anki_hsk.py` | AnkiConnect operations: export / import / pick / models |
| `cleanup_tags.py` | Clean deck data: enrich definitions, POS tags, auto-fix similar definitions, decompose multi-char words |
| `generate_new_words.py` | Extract new vocabulary from `.pptx` / `.doc` / `.txt` → `pick_words.txt` |
| `go.py` | Shortcut: export deck then generate pick list |
| `clean_empty.py` | Shortcut: export → translate empty cards → tags → import |
| `never_propose_words.txt` | Characters / words to exclude from proposals (supports `char` or `char \| pinyin \| english`) |
| `pick_words.txt` | Human-editable word list (intermediate, generated) |
| `data/` | Deck data: `myhsk1_data.json`, `.bak.json`, `.csv` |
| `cache/` | Auto-generated caches: `pos_cache.json`, `char_info_cache.json` |
| `templates/` | Anki card templates: `anki_card_preview.html`, `anki_card_templates.txt` |
| `newwords/` | Input files (`.pptx`, `.doc`, `.txt`) for new vocabulary extraction |

---

## Main workflow

Every session starts with an **export** and ends with an **import**. In between, pick optional steps as needed.

```
python anki_hsk.py export         # 1. Always first — export deck → myhsk1_data.json

# ── Optional: add new words ─────────────────────────────────────────
python generate_new_words.py      # 2a. Extract words from newwords/ → pick_words.txt
# edit pick_words.txt             # 2b. Delete unwanted lines, fix definitions
python anki_hsk.py pick           # 2c. Add remaining words to Anki

# ── Optional: clean up ──────────────────────────────────────────────
python cleanup_tags.py            # 3.  Enrich definitions + set POS/count tags
                                  #     (writes missing single chars to pick_words.txt)
# edit pick_words.txt             # 3b. (if single chars were found) keep wanted chars
python anki_hsk.py pick           # 3c. (if single chars were found) add them

python anki_hsk.py import         # 4. Always last — push changes back to Anki
```

| Step | Command | What it does |
|------|---------|--------------|
| 1 | `python anki_hsk.py export` | Dumps deck to `myhsk1_data.json` (+ backup `.bak.json`). Always run first. |
| 2a | `python generate_new_words.py` | *(optional)* Extracts new words from `newwords/`, looks up pinyin/English/POS, decomposes multi-char words, writes `pick_words.txt`, warns about collisions |
| 2b | *(manual)* | Open `pick_words.txt` — delete lines you don't want, fix pinyin/translations. `#` = comment. Permanent exclusions go in `never_propose_words.txt` |
| 2c | `python anki_hsk.py pick` | *(optional)* Reads `pick_words.txt` and adds each entry as a new Anki card |
| 3 | `python cleanup_tags.py` | *(optional)* Enriches short definitions, auto-fixes similar definitions, sets POS tags, adds `single`/`dual` tags, decomposes multi-char words → missing single chars to `pick_words.txt`. See [options](#cleanup_tagspy-options) below |
| 4 | `python anki_hsk.py import` | Pushes updated fields + tags back to Anki (only changed notes are sent). Always run last. |

> **Input formats for `newwords/`:**
> - `.pptx` / `.doc` — Chinese segments are extracted and filtered against known-good characters
> - `.txt` (e.g. `mylist.txt`) — One Chinese word per line, `#` = comment. No garbage filter (trusted input)

---

## Shortcuts

| Command | Equivalent to | Use when |
|---------|--------------|----------|
| `python go.py` | export → generate_new_words | You dropped files in `newwords/` and want a pick list |
| `python clean_empty.py` | export → retranslate empty → tags → import | You have cards with Chinese but no English |

---

## cleanup_tags.py options

`cleanup_tags.py` supports `--mode` and `--scope` flags to run selectively:

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
python cleanup_tags.py                                 # Enrich + tags for all words (default)
python cleanup_tags.py --mode translation              # Enrich short definitions only
python cleanup_tags.py --mode retranslate              # Replace ALL definitions with fresh Google Translate
python cleanup_tags.py --mode retranslate --scope new  # Retranslate new words only
python cleanup_tags.py --mode retranslate --scope empty # Translate cards with no English
python cleanup_tags.py --mode tags                     # Update tags only
python cleanup_tags.py --mode tags --scope existing    # Update tags for existing words only
```

**Modes explained:**
- `translation` — Only enriches short definitions (≤3 words, no commas) by appending Google Translate alternatives
- `retranslate` — **Replaces** all English definitions with a fresh Google Translate lookup (primary + up to 3 alternatives). Use this to clean up old/redundant definitions like `"Tall/high, tall, expensive, lofty"`
- `tags` — Only updates POS and character-count tags
- `all` — Enrich translations + update tags (default, same as running `translation` + `tags`)

**Similarity auto-fix:** When updating translations (`--mode translation` or `--mode all`), the script compares English definitions across all cards. Pairs sharing ≥50% of meaningful words are detected and automatically differentiated by fetching fresh Google Translate alternatives and preferring unique words that don't appear in the conflicting card's definition. Pairs that can't be improved are still reported.

**Character count tags:** All cards receive a `single` (1-char) or `dual` (2-char) tag automatically.

> First run fetches POS + alternatives from Google (~7 min for ~1400 words). Results are cached in `pos_cache.json` and `char_info_cache.json` — re-runs are instant.

---

## Other useful commands

| Command | What it does |
|---------|--------------|
| `python anki_hsk.py models` | List available note types and their fields |
