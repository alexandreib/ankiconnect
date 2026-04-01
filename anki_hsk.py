"""
AnkiConnect HSK1 Deck Manager
==============================
Export, modify, and re-import your myhsk1 deck via AnkiConnect.

Requirements:
  - Anki running with AnkiConnect plugin installed (default port 8765)

Usage:
  python anki_hsk.py export              # Export myhsk1 deck to myhsk1_data.json
  python anki_hsk.py export --format csv # Export to myhsk1_data.csv
  python anki_hsk.py import              # Re-import modified myhsk1_data.json
  python anki_hsk.py import --format csv # Re-import modified myhsk1_data.csv
  python anki_hsk.py pick                # Add selected words from pick_words.txt
  python anki_hsk.py models              # List note types and fields
"""

import argparse
import csv
import json
import os
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError

from shared import strip_html, load_pos_cache, PICK_FILE, JSON_FILE

ANKI_CONNECT_URL = "http://localhost:8765"
DECK_NAME = "myhsk1"
BACKUP_FILE = os.path.join(os.path.dirname(__file__), "data", "myhsk1_data.bak.json")
CSV_FILE = os.path.join(os.path.dirname(__file__), "data", "myhsk1_data.csv")


def anki_request(action, **params):
    """Send a request to AnkiConnect and return the result."""
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    request = Request(ANKI_CONNECT_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        response = json.loads(urlopen(request).read())
    except URLError:
        print("ERROR: Cannot connect to AnkiConnect. Is Anki running with the AnkiConnect plugin?")
        sys.exit(1)
    if response.get("error"):
        raise RuntimeError(f"AnkiConnect error: {response['error']}")
    return response["result"]


# ── Export ───────────────────────────────────────────────────────────────────

def export_deck(fmt):
    """Export all notes from the deck to a JSON or CSV file."""
    # Find all note IDs in the deck
    note_ids = anki_request("findNotes", query=f'"deck:{DECK_NAME}"')
    if not note_ids:
        print(f"No notes found in deck '{DECK_NAME}'.")
        return

    # Fetch full note info
    notes_info = anki_request("notesInfo", notes=note_ids)

    # Build a clean list of dicts, stripping HTML from fields (except Comment)
    records = []
    preserve_fields = {"Comment", "my_english"}
    for note in notes_info:
        record = {
            "noteId": note["noteId"],
            "modelName": note["modelName"],
            "tags": note["tags"],
            "fields": {
                name: val["value"] if name in preserve_fields else strip_html(val["value"])
                for name, val in note["fields"].items()
            },
        }
        records.append(record)

    if fmt == "csv":
        _save_csv(records)
    else:
        _save_json(records)


def _save_json(records):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    # Save a backup for diff-based import
    import shutil
    shutil.copy2(JSON_FILE, BACKUP_FILE)
    print(f"Exported {len(records)} notes to {JSON_FILE}")


def _save_csv(records):
    if not records:
        return
    # Collect all unique field names across all notes
    all_field_names = []
    seen = set()
    for r in records:
        for name in r["fields"]:
            if name not in seen:
                all_field_names.append(name)
                seen.add(name)

    fieldnames = ["noteId", "modelName", "tags"] + all_field_names
    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = {
                "noteId": r["noteId"],
                "modelName": r["modelName"],
                "tags": ";".join(r["tags"]),
            }
            for name in all_field_names:
                row[name] = r["fields"].get(name, "")
            writer.writerow(row)
    print(f"Exported {len(records)} notes to {CSV_FILE}")


# ── Import (update existing + add new) ──────────────────────────────────────

def import_deck(fmt):
    """Re-import only changed/new notes from JSON or CSV back into Anki."""
    if fmt == "csv":
        records = _load_csv()
    else:
        records = _load_json()

    # Load backup to detect changes
    original = {}
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            for r in json.load(f):
                nid = r.get("noteId")
                if nid:
                    original[nid] = r

    # Separate into updates vs adds, skip unchanged
    to_update = []   # (note_id, fields, tags)
    to_add = []      # (model_name, fields, tags)
    skipped = 0

    for r in records:
        note_id = r.get("noteId")
        fields = r["fields"]
        tags = r["tags"] if isinstance(r["tags"], list) else r["tags"].split(";")
        tags = [t for t in tags if t]
        model_name = r["modelName"]

        if note_id:
            orig = original.get(note_id)
            if orig:
                orig_tags = orig["tags"] if isinstance(orig["tags"], list) else orig["tags"].split(";")
                orig_tags = sorted([t for t in orig_tags if t])
                if orig["fields"] == fields and orig_tags == sorted(tags):
                    skipped += 1
                    continue
            to_update.append((note_id, fields, tags))
        else:
            to_add.append((model_name, fields, tags))

    print(f"Found {len(to_update)} to update, {len(to_add)} to add, {skipped} unchanged.")

    # ── Batch update fields ──────────────────────────────────────────────
    errors = []
    BATCH = 50
    if to_update:
        print(f"Updating fields in batches of {BATCH}...")
        for i in range(0, len(to_update), BATCH):
            batch = to_update[i:i+BATCH]
            actions = [{"action": "updateNoteFields", "params": {"note": {"id": nid, "fields": flds}}}
                       for nid, flds, _ in batch]
            results = anki_request("multi", actions=actions)
            for j, res in enumerate(results):
                if isinstance(res, dict) and res.get("error"):
                    errors.append(f"Update noteId={batch[j][0]}: {res['error']}")
            print(f"  fields: {min(i+BATCH, len(to_update))}/{len(to_update)}")

    # ── Batch sync tags ──────────────────────────────────────────────────
    if to_update:
        all_update_ids = [nid for nid, _, _ in to_update]

        # Collect all possible tags to remove in one call
        all_tags_set = set()
        for _, _, tags in to_update:
            all_tags_set.update(tags)
        for nid in all_update_ids:
            orig = original.get(nid)
            if orig:
                ot = orig["tags"] if isinstance(orig["tags"], list) else orig["tags"].split(";")
                all_tags_set.update(t for t in ot if t)

        # Remove all known tags from updated notes in one call
        if all_tags_set:
            print("Clearing old tags...")
            anki_request("removeTags", notes=all_update_ids, tags=" ".join(all_tags_set))

        # Group notes by their target tag set, then addTags per group
        from collections import defaultdict
        tag_groups = defaultdict(list)
        for nid, _, tags in to_update:
            tag_groups[tuple(sorted(tags))].append(nid)

        print(f"Setting new tags ({len(tag_groups)} unique tag sets)...")
        for tag_tuple, nids in tag_groups.items():
            if tag_tuple:
                anki_request("addTags", notes=nids, tags=" ".join(tag_tuple))

    updated = len(to_update) - sum(1 for e in errors if "Update " in e)

    # ── Add new notes (batched) ──────────────────────────────────────────
    added = 0
    if to_add:
        print(f"Adding {len(to_add)} new notes...")
        for i in range(0, len(to_add), BATCH):
            batch = to_add[i:i+BATCH]
            actions = [{"action": "addNote", "params": {"note": {
                "deckName": DECK_NAME, "modelName": mn, "fields": flds,
                "tags": tgs, "options": {"allowDuplicate": False},
            }}} for mn, flds, tgs in batch]
            results = anki_request("multi", actions=actions)
            for j, res in enumerate(results):
                if isinstance(res, dict) and res.get("error"):
                    errors.append(f"Add new note: {res['error']}")
                else:
                    added += 1
            print(f"  added: {min(i+BATCH, len(to_add))}/{len(to_add)}")

    print(f"\nImport complete: {updated} updated, {added} added, {skipped} unchanged (skipped).")
    if errors:
        print(f"{len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")


def _load_json():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_csv():
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        meta_cols = {"noteId", "modelName", "tags"}
        records = []
        for row in reader:
            note_id = row.get("noteId")
            record = {
                "noteId": int(note_id) if note_id else None,
                "modelName": row["modelName"],
                "tags": row.get("tags", ""),
                "fields": {k: v for k, v in row.items() if k not in meta_cols},
            }
            records.append(record)
        return records


# ── Pick: add words from edited pick_words.txt ─────────────────────────────

def pick_words():
    """Read pick_words.txt and add each remaining word to the deck."""
    try:
        with open(PICK_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"File not found: {PICK_FILE}")
        print("Run 'python generate_new_words.py' first to create it.")
        return

    pos_cache = load_pos_cache()

    words = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: 中文 | Pinyin | English  (or just 中文)
        parts = [p.strip() for p in line.split("|")]
        chinese = parts[0]
        pinyin = parts[1] if len(parts) > 1 else ""
        english = parts[2] if len(parts) > 2 else ""
        words.append((chinese, pinyin, english))

    if not words:
        print("No words found in pick_words.txt (all lines commented out or deleted).")
        return

    print(f"Adding {len(words)} selected words...")
    added = 0
    errors = []
    for chinese, pinyin, english in words:
        tags = []
        if len(chinese) == 1:
            tags.append("single")
        elif len(chinese) == 2:
            tags.append("dual")
        # Add POS tags from cache
        for t in pos_cache.get(chinese, []):
            if t not in tags:
                tags.append(t)
        try:
            anki_request("addNote", note={
                "deckName": DECK_NAME,
                "modelName": "Basic",
                "fields": {"中文": chinese, "English": english, "my_english": "", "Pinyin": pinyin, "Comment": ""},
                "tags": tags,
                "options": {"allowDuplicate": False},
            })
            added += 1
        except RuntimeError as e:
            errors.append(f"{chinese}: {e}")

    print(f"Added {added} new note(s).")
    if errors:
        print(f"{len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")


# ── List models & fields (helper) ───────────────────────────────────────────

def list_models():
    """Print available note types and their fields so you know what to use."""
    models = anki_request("modelNames")
    for model in models:
        fields = anki_request("modelFieldNames", modelName=model)
        print(f"  {model}: {', '.join(fields)}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Manage myhsk1 Anki deck via AnkiConnect")
    sub = parser.add_subparsers(dest="command")

    exp = sub.add_parser("export", help="Export deck to file")
    exp.add_argument("--format", choices=["json", "csv"], default="json")

    imp = sub.add_parser("import", help="Re-import modified file into Anki")
    imp.add_argument("--format", choices=["json", "csv"], default="json")

    sub.add_parser("pick", help=f"Add selected words from {PICK_FILE}")
    sub.add_parser("models", help="List available note types and fields")

    args = parser.parse_args()

    if args.command == "export":
        export_deck(args.format)
    elif args.command == "import":
        import_deck(args.format)
    elif args.command == "pick":
        pick_words()
    elif args.command == "models":
        list_models()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
