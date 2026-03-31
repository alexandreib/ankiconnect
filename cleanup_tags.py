"""Clean up myhsk1_data.json:
1. Apply manual fixes from fixes.json
2. Remove '(1 char)' / '(1char)' / '（1 char）' from English definitions
3. POS lookup + enrich short definitions with Google Translate alternatives
4. Check for similar English definitions across cards
5. Add 'single'/'double' tag for character count; preserve 'leech', 'lesson'
6. Decompose multi-char words: write missing single chars to pick_words.txt

Usage:
  python cleanup_tags.py                           # All operations, all words
  python cleanup_tags.py --mode translation        # Update translations only
  python cleanup_tags.py --mode tags               # Update tags only
  python cleanup_tags.py --scope new               # Process new words only
  python cleanup_tags.py --scope existing          # Process existing words only
  python cleanup_tags.py --mode tags --scope new   # Update tags for new words only
"""
import argparse
import json
import os
import re
import time

from shared import (
    JSON_FILE, PICK_FILE, PRESERVE_TAGS,
    is_cjk, load_deck_records, save_deck_records,
    load_pos_cache, save_pos_cache,
    load_char_info_cache, save_char_info_cache,
    load_never_propose, load_fixes, lookup_full,
    google_translate, build_definition,
)

BACKUP_FILE = os.path.join(os.path.dirname(__file__), "data", "myhsk1_data.bak.json")

# Words to ignore when comparing English definitions for similarity
STOP_WORDS = {
    "a", "an", "the", "to", "of", "in", "on", "at", "is", "it", "be",
    "and", "or", "for", "not", "with", "as", "by", "from", "that", "this",
}


def definition_words(english):
    """Extract meaningful words from an English definition for similarity check."""
    words = set()
    for w in re.split(r'[,;/\s]+', english.lower()):
        w = w.strip("()")
        if w and w not in STOP_WORDS and len(w) > 1:
            words.add(w)
    return words


def build_definition_index(records):
    """Build a map: english_word -> list of (chinese, full_english) for collision detection."""
    index = {}
    for r in records:
        chinese = r["fields"].get("中文", "")
        english = r["fields"].get("English", "")
        if not english:
            continue
        for w in definition_words(english):
            if w not in index:
                index[w] = []
            index[w].append((chinese, english))
    return index


def check_similar_definitions(chinese, english, def_index):
    """Return list of (other_chinese, other_english) with similar definitions."""
    words = definition_words(english)
    if not words:
        return []
    # Count overlap with each other card
    overlap_count = {}
    overlap_eng = {}
    for w in words:
        for other_zh, other_eng in def_index.get(w, []):
            if other_zh == chinese:
                continue
            if other_zh not in overlap_count:
                overlap_count[other_zh] = 0
                overlap_eng[other_zh] = other_eng
            overlap_count[other_zh] += 1
    similar = []
    for other_zh, count in overlap_count.items():
        other_words = definition_words(overlap_eng[other_zh])
        if not other_words:
            continue
        # Proportion of shared words relative to the smaller definition
        similarity = count / min(len(words), len(other_words))
        if similarity >= 0.5:
            similar.append((other_zh, overlap_eng[other_zh]))
    return similar


def differentiate_definition(chinese, current_english, alts, other_english_set):
    """Rebuild a definition preferring alternatives that don't appear in other_english_set.

    other_english_set: set of definition_words from the conflicting card(s).
    Returns a new English string, or the original if no improvement found.
    """
    if not alts:
        return current_english

    other_words = set()
    for eng in other_english_set:
        other_words |= definition_words(eng)

    # Split current definition parts
    current_parts = [p.strip() for p in current_english.split(",")]
    primary = current_parts[0]

    # Score alternatives: prefer ones whose words DON'T overlap with the other card
    def uniqueness(alt):
        alt_words = definition_words(alt)
        if not alt_words:
            return 0
        unique = sum(1 for w in alt_words if w not in other_words)
        return unique / len(alt_words)

    # Collect unique alternatives not already in current definition
    current_lower = {p.strip().lower() for p in current_parts}
    unique_alts = []
    for alt in alts:
        if alt.strip().lower() not in current_lower and uniqueness(alt) > 0:
            unique_alts.append(alt)

    # Sort by uniqueness score (most unique first)
    unique_alts.sort(key=uniqueness, reverse=True)

    if not unique_alts:
        return current_english

    # Rebuild: primary + up to 3 best unique alternatives
    parts = [primary]
    seen = {primary.lower().strip()}
    for alt in unique_alts:
        if alt.lower().strip() not in seen:
            seen.add(alt.lower().strip())
            parts.append(alt)
            if len(parts) >= 4:
                break
    return ", ".join(parts)


def load_backup_note_ids():
    """Load noteIds from backup file to determine existing vs new words."""
    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {r["noteId"] for r in data if r.get("noteId")}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def main():
    parser = argparse.ArgumentParser(description="Clean up myhsk1_data.json")
    parser.add_argument("--mode", choices=["translation", "retranslate", "tags", "all"], default="all",
                        help="What to update: translation (enrich short), retranslate (replace all), tags, or all (default: all)")
    parser.add_argument("--scope", choices=["new", "existing", "all"], default="all",
                        help="Which words to process: new, existing, or all (default: all)")
    args = parser.parse_args()

    do_translation = args.mode in ("translation", "retranslate", "all")
    do_retranslate = args.mode == "retranslate"
    do_tags = args.mode in ("tags", "all")
    records = load_deck_records()
    pos_cache = load_pos_cache()
    initial_cache_size = len(pos_cache)

    # ── Scope filtering ──────────────────────────────────────────────────
    backup_ids = set()
    if args.scope != "all":
        backup_ids = load_backup_note_ids()
        if backup_ids:
            print(f"  Backup has {len(backup_ids)} notes for scope filtering")
        else:
            print("  ⚠ No backup file found — treating all words as new")

    def in_scope(record):
        if args.scope == "all":
            return True
        note_id = record.get("noteId")
        if args.scope == "existing":
            return note_id in backup_ids
        else:  # new
            return note_id not in backup_ids

    def is_lesson(record):
        return "lesson" in record.get("tags", [])

    scoped_count = sum(1 for r in records if in_scope(r))
    lesson_count = sum(1 for r in records if is_lesson(r))
    print(f"  Mode: {args.mode} | Scope: {args.scope} — {scoped_count}/{len(records)} notes selected")
    if lesson_count:
        print(f"  Skipping field changes for {lesson_count} lesson-tagged card(s)")

    # ── Step 1: Apply fixes.json ─────────────────────────────────────────
    fixes = load_fixes()
    fixes_applied = 0
    for r in records:
        if not in_scope(r) or is_lesson(r):
            continue
        zh = r["fields"].get("中文", "")
        if zh in fixes:
            for field, value in fixes[zh].items():
                old = r["fields"].get(field, "")
                if old != value:
                    r["fields"][field] = value
                    fixes_applied += 1

    # ── Step 2: Strip (1 char) from English ──────────────────────────────
    stripped = 0
    for r in records:
        if not in_scope(r) or is_lesson(r):
            continue
        eng = r["fields"].get("English", "")
        new_eng = re.sub(r"\s*[（(]1\s*char[)）]", "", eng).strip()
        if new_eng != eng:
            r["fields"]["English"] = new_eng
            stripped += 1

    # ── Step 3: POS lookup + translate/enrich definitions ─────────────
    total = len(records)
    fetched = 0
    tags_changed = 0
    enriched = 0
    retranslated = 0
    for i, r in enumerate(records, 1):
        chinese = r["fields"].get("中文", "")
        eng = r["fields"].get("English", "")
        scoped = in_scope(r)
        lesson = is_lesson(r)
        needs_retranslate = do_retranslate and scoped and not lesson and chinese
        needs_enrich = (do_translation and not do_retranslate and scoped and not lesson
                        and eng and "," not in eng and len(eng.split()) <= 3)

        if chinese in pos_cache and not needs_enrich and not needs_retranslate:
            # POS cached & definition doesn't need work — skip API call
            pos_tags = pos_cache[chinese]
        else:
            # Full API call: get POS + alternatives in one request
            try:
                gt_eng, _pin, pos_tags, alts = google_translate(chinese)
            except RuntimeError as e:
                print(f"  ✗ {e}")
                pos_tags = pos_cache.get(chinese, [])
                gt_eng = ""
                alts = []
            if chinese not in pos_cache:
                pos_cache[chinese] = pos_tags
                fetched += 1
                time.sleep(0.3)
            # Retranslate: replace entire definition with fresh Google Translate
            if needs_retranslate and gt_eng:
                new_eng = build_definition(gt_eng, alts)
                if new_eng != eng:
                    r["fields"]["English"] = new_eng
                    retranslated += 1
            # Enrich: only extend short definitions with alternatives
            elif needs_enrich and alts:
                new_eng = build_definition(eng, alts)
                if new_eng != eng:
                    r["fields"]["English"] = new_eng
                    enriched += 1

        # ── Step 4: Build new tags ───────────────────────────────────────
        if do_tags and scoped:
            new_tags = [t for t in r["tags"] if t in PRESERVE_TAGS]
            for t in pos_tags:
                if t not in new_tags:
                    new_tags.append(t)
            # Character count tags
            if len(chinese) == 1 and "single" not in new_tags:
                new_tags.append("single")
            elif len(chinese) == 2 and "double" not in new_tags:
                new_tags.append("double")

            if sorted(new_tags) != sorted(r["tags"]):
                tags_changed += 1
            r["tags"] = new_tags

        if i % 50 == 0:
            save_pos_cache(pos_cache)
            print(f"  [{i}/{total}] ({fetched} fetched, {i - fetched} cached)")

    save_pos_cache(pos_cache)

    # ── Step 4b: Auto-fix similar definitions ──────────────────────────
    similarity_warnings = []
    similarity_fixed = 0
    if do_translation:
        print("\n  Checking for similar definitions...")
        def_index = build_definition_index(records)
        seen_pairs = set()

        # Build a lookup: chinese -> record
        zh_to_record = {}
        for r in records:
            zh = r["fields"].get("中文", "")
            if zh:
                zh_to_record[zh] = r

        for r in records:
            if not in_scope(r):
                continue
            chinese = r["fields"].get("中文", "")
            english = r["fields"].get("English", "")
            if not english:
                continue
            similar = check_similar_definitions(chinese, english, def_index)
            for other_zh, other_eng in similar:
                key = tuple(sorted([chinese, other_zh]))
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    similarity_warnings.append((chinese, english, other_zh, other_eng))

        if similarity_warnings:
            print(f"\n  ⚠ {len(similarity_warnings)} similar definition pair(s) — auto-fixing...")
            for zh1, eng1, zh2, eng2 in similarity_warnings:
                # Fetch alternatives for both words
                try:
                    _, _, _, alts1 = google_translate(zh1)
                except RuntimeError:
                    alts1 = []
                try:
                    _, _, _, alts2 = google_translate(zh2)
                except RuntimeError:
                    alts2 = []
                time.sleep(0.3)

                # Differentiate each using the other's definition
                new_eng1 = differentiate_definition(zh1, eng1, alts1, {eng2})
                new_eng2 = differentiate_definition(zh2, eng2, alts2, {eng1})

                r1 = zh_to_record.get(zh1)
                r2 = zh_to_record.get(zh2)

                changed = False
                if r1 and new_eng1 != eng1 and not is_lesson(r1):
                    r1["fields"]["English"] = new_eng1
                    changed = True
                if r2 and new_eng2 != eng2 and not is_lesson(r2):
                    r2["fields"]["English"] = new_eng2
                    changed = True

                if changed:
                    similarity_fixed += 1
                    print(f"    {zh1}: {eng1} → {new_eng1}")
                    print(f"    {zh2}: {eng2} → {new_eng2}")
                else:
                    print(f"    {zh1} ({eng1})  ↔  {zh2} ({eng2})  [no better alternatives found]")

            # Rebuild index after fixes for accurate final report
            def_index = build_definition_index(records)
        else:
            print("  No similar definitions found.")

    # ── Step 5: Decompose multi-char words ───────────────────────────────
    existing_chars = {r["fields"].get("中文", "") for r in records}
    never_propose = load_never_propose()
    if never_propose:
        print(f"  Excluding {len(never_propose)} entry/entries from never_propose_words.txt")

    missing_chars = set()
    for r in records:
        chinese = r["fields"].get("中文", "")
        if len(chinese) > 1:
            for ch in chinese:
                if is_cjk(ch) and ch not in existing_chars and ch not in never_propose:
                    missing_chars.add(ch)

    new_cards = 0
    if missing_chars:
        print(f"\n  Decomposing: {len(missing_chars)} missing single-character card(s)")
        char_cache = load_char_info_cache()
        char_fetched = 0

        pick_lines = [
            "# Single characters extracted from multi-char words.",
            "# Delete the lines you DON'T want, keep the ones you do.",
            "# Then run:  python anki_hsk.py pick",
            "# Lines starting with # are ignored.",
            "# Format: 中文 | Pinyin | English",
            "",
        ]

        for ch in sorted(missing_chars):
            english, pinyin, pos_tags, alts, was_cached = lookup_full(ch, pos_cache, char_cache)
            if not was_cached:
                char_fetched += 1
                time.sleep(0.3)

            definition = build_definition(english, alts)
            pick_lines.append(f"{ch} | {pinyin} | {definition}")
            existing_chars.add(ch)
            new_cards += 1
            print(f"    + {ch}  {pinyin:10} {definition:40} [{', '.join(pos_tags)}]")

        with open(PICK_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(pick_lines) + "\n")

        save_char_info_cache(char_cache)
        save_pos_cache(pos_cache)
        print(f"  Fetched {char_fetched}, cached {len(missing_chars) - char_fetched}")
        print(f"\n  → Wrote {new_cards} characters to {PICK_FILE}")
        print(f"    Edit it, then run:  python anki_hsk.py pick")

    # ── Step 6: Save ─────────────────────────────────────────────────────
    save_deck_records(records)

    print(f"\nDone — {total} notes processed ({scoped_count} in scope).")
    print(f"  Fixes applied: {fixes_applied}")
    print(f"  '(1 char)' stripped: {stripped}")
    if do_translation:
        if do_retranslate:
            print(f"  Definitions retranslated: {retranslated}")
        else:
            print(f"  Definitions enriched: {enriched}")
        print(f"  Similar pairs found: {len(similarity_warnings)}, auto-fixed: {similarity_fixed}")
    if do_tags:
        print(f"  Tags changed: {tags_changed}")
    print(f"  Google lookups: {fetched} (cache: {initial_cache_size} → {len(pos_cache)})")
    print(f"  Single-char candidates: {new_cards}")
    print(f"\nNow run:  python anki_hsk.py import")
    if new_cards:
        print(f"Then edit {PICK_FILE} and run:  python anki_hsk.py pick")


if __name__ == "__main__":
    main()
