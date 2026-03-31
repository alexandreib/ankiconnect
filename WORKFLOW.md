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
| `cleanup_tags.py` | Clean deck data: enrich definitions, POS tags, similarity check, decompose multi-char words |
| `generate_new_words.py` | Extract new vocabulary from `.pptx` / `.doc` / `.txt` → `pick_words.txt` |
| `go.py` | One-command: export deck then generate pick list |
| `never_propose_words.txt` | Characters / words to exclude from proposals (supports `char` or `char \| pinyin \| english`) |
| `pick_words.txt` | Human-editable word list (intermediate, generated) |
| `data/` | Deck data: `myhsk1_data.json`, `.bak.json`, `.csv` |
| `cache/` | Auto-generated caches: `pos_cache.json`, `char_info_cache.json` |
| `templates/` | Anki card templates: `anki_card_preview.html`, `anki_card_templates.txt` |
| `newwords/` | Input files (`.pptx`, `.doc`, `.txt`) for new vocabulary extraction |

---

## Workflow 1 — Add New Words

Drop `.pptx`, `.doc`, or `.txt` files into `newwords/`, then:

```
python go.py                  # 1. Export deck + generate pick_words.txt
                              #    (also decomposes single chars + collision warnings)
# edit pick_words.txt         # 2. Delete unwanted lines, fix definitions
python anki_hsk.py pick       # 3. Add remaining words to Anki
python cleanup_tags.py        # 4. (optional) Enrich definitions & set POS tags
python anki_hsk.py import     # 5. (optional) Push enriched data back to Anki
```

| Step | Command | What it does |
|------|---------|--------------|
| 1 | `python go.py` | Exports current deck to `myhsk1_data.json`, extracts new words from `newwords/`, looks up pinyin/English/POS via Google Translate, decomposes multi-char words into single-char candidates, writes everything to `pick_words.txt`, warns about definition collisions |
| 2 | *(manual)* | Open `pick_words.txt` — delete lines you don't want, fix pinyin/translations. Lines starting with `#` are ignored. To permanently exclude entries, add them to `never_propose_words.txt` |
| 3 | `python anki_hsk.py pick` | Reads `pick_words.txt` and adds each remaining entry as a new Anki card (with POS tags from cache) |
| 4 | `python cleanup_tags.py` | *(optional)* Enriches short definitions (with similarity warnings), sets POS tags, adds `single`/`double` tags, decomposes any new multi-char words |
| 5 | `python anki_hsk.py import` | *(optional)* Pushes the enriched `myhsk1_data.json` back into Anki |

> **Input formats for `newwords/`:**
> - `.pptx` / `.doc` — Chinese segments are extracted and filtered against known-good characters
> - `.txt` (e.g. `mylist.txt`) — One Chinese word per line, `#` = comment. No garbage filter (trusted input)

---

## Workflow 2 — Clean Up Existing Deck

No new words — just fix definitions, tags, and extract missing single chars:

```
python anki_hsk.py export     # 1. Export deck to myhsk1_data.json
python cleanup_tags.py        # 2. Clean up: enrich, tag, decompose
python anki_hsk.py import     # 3. Push changes back to Anki
# edit pick_words.txt         # 4. (if single chars were found)
python anki_hsk.py pick       # 5. (if single chars were found)
```

| Step | Command | What it does |
|------|---------|--------------|
| 1 | `python anki_hsk.py export` | Dumps current deck to `myhsk1_data.json` (+ backup `.bak.json`) |
| 2 | `python cleanup_tags.py` | Applies `fixes.json` (if present), strips `(1 char)` from English, enriches short definitions (≤3 words, no commas) with Google Translate alternatives, **warns about similar English definitions**, sets POS tags (verb/noun/adjective/adverb), adds `single` tag for 1-char words and `double` tag for 2-char words, preserves `leech` and `lesson` tags, decomposes multi-char words → missing single chars written to `pick_words.txt` |
| 3 | `python anki_hsk.py import` | Pushes updated fields + tags back into Anki (only changed notes are updated) |
| 4 | *(manual)* | If `pick_words.txt` was generated, edit it to keep wanted single chars |
| 5 | `python anki_hsk.py pick` | Adds the selected single chars to Anki |

> First run fetches POS + alternatives from Google (~7 min for ~1400 words). Results are cached in `pos_cache.json` and `char_info_cache.json` — re-runs are instant.

### cleanup_tags.py options

`cleanup_tags.py` supports `--mode` and `--scope` flags to run selectively:

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--mode` | `translation`, `tags`, `all` | `all` | What to update |
| `--scope` | `new`, `existing`, `all` | `all` | Which words to process (new = not in backup, existing = in backup) |

**Examples:**

```bash
python cleanup_tags.py --mode translation              # Update translations only (all words)
python cleanup_tags.py --mode tags                     # Update tags only (all words)
python cleanup_tags.py --mode translation --scope new  # Update translations for new words only
python cleanup_tags.py --mode tags --scope existing    # Update tags for existing words only
```

**Similarity check:** When updating translations (`--mode translation` or `--mode all`), the script compares English definitions across all cards and warns about pairs that share ≥50% of their meaningful words. This helps distinguish cards with overlapping meanings.

**Character count tags:** All cards receive a `single` (1-char) or `double` (2-char) tag automatically.

---

## Other useful commands

| Command | What it does |
|---------|--------------|
| `python anki_hsk.py models` | List available note types and their fields |
