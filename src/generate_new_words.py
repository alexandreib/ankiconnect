"""Extract new vocabulary from .pptx / .doc files in newwords/ and write pick_words.txt.

Filters out OLE binary garbage by only keeping Chinese segments whose characters
all appear in the existing deck or in clean .pptx sources (plus a manual whitelist).
"""
import os
import re
import time

from shared import (
    NEWWORDS_DIR, PICK_FILE, POS_KEEP,
    is_cjk, load_existing_words, load_never_propose,
    load_pos_cache, save_pos_cache, google_translate, build_definition,
    load_char_info_cache, save_char_info_cache, lookup_full,
    load_deck_records, strip_html,
    extract_pptx_text, extract_doc_lines, remove_pinyin_from_definition,
)


# Characters known-good that may appear in .doc but not yet in deck/pptx
EXTRA_CHARS = (
    "燕麦奶片碗酸番茄酪菇针薯洋葱失眠佩猪乔治脊椎鲨豹颗"
    "礼购划掉澳利亚聊慢练流健康情景脏药推选择杯豆腐脑油条"
    "巴黎三明治披萨星巴克咖啡沫泡凑网站"
)

# Common OLE artifacts to skip
SKIP_WORDS = {"正文", "普通", "页眉", "页脚", "网站", "普通表格", "默认段落"}


def main():
    existing_words, existing_chars = load_existing_words()

    # Build known-good character set from existing deck + clean pptx files
    good_chars = set(existing_chars)
    for fname in sorted(os.listdir(NEWWORDS_DIR)):
        if fname.endswith(".pptx"):
            for t in extract_pptx_text(os.path.join(NEWWORDS_DIR, fname)):
                for c in t:
                    if is_cjk(c):
                        good_chars.add(c)
    for c in EXTRA_CHARS:
        if is_cjk(c):
            good_chars.add(c)

    # Extract all Chinese segments from documents
    all_segments = set()
    txt_words = set()  # manually curated words from .txt files (skip garbage filter)
    for fname in sorted(os.listdir(NEWWORDS_DIR)):
        fpath = os.path.join(NEWWORDS_DIR, fname)
        if fname.endswith(".pptx"):
            lines = extract_pptx_text(fpath)
        elif fname.endswith(".doc"):
            lines = extract_doc_lines(fpath)
        elif fname.endswith(".txt"):
            # Plain word lists: one Chinese word per line, # = comment
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        for seg in re.findall(r'[\u4e00-\u9fff]+', line):
                            txt_words.add(seg)
            continue
        else:
            continue
        for line in lines:
            for seg in re.findall(r'[\u4e00-\u9fff]+', line):
                all_segments.add(seg)

    # Load exclusion list
    never_propose = load_never_propose()
    if never_propose:
        print(f"  Excluding {len(never_propose)} entry/entries from never_propose_words.txt")

    # Keep only document segments where ALL characters are known-good, length 2-4
    clean_new = set()
    for seg in all_segments:
        if seg in existing_words or seg in SKIP_WORDS or seg in never_propose:
            continue
        if all(c in good_chars for c in seg) and 2 <= len(seg) <= 4:
            clean_new.add(seg)

    # Add manually curated .txt words (no garbage filter, any length)
    for seg in txt_words:
        if seg not in existing_words and seg not in never_propose:
            clean_new.add(seg)

    sorted_vocab = sorted(clean_new)
    print(f"Found {len(sorted_vocab)} clean new vocabulary candidates:\n")

    # Google Translate lookup for pinyin, English, POS
    pos_cache = load_pos_cache()
    dictionary = {}
    for w in sorted_vocab:
        try:
            english, pinyin, pos_tags, alts = google_translate(w)
        except RuntimeError as e:
            print(f"  \u2717 {e}")
            english, pinyin, pos_tags, alts = "", "", [], []
        pos_cache[w] = pos_tags
        definition = build_definition(english, alts)
        new_def, removed = remove_pinyin_from_definition(definition, pinyin)
        if removed:
            print(f"  \u26a0 Pinyin lookalike in {w} ({pinyin}): removed {removed}")
            definition = new_def
        dictionary[w] = (pinyin, definition, pos_tags)
        time.sleep(0.2)

    save_pos_cache(pos_cache)

    for w in sorted_vocab:
        py, en, pos = dictionary[w]
        tags_str = ", ".join(pos) if pos else ""
        print(f"  {w} | {py} | {en}  [{tags_str}]")

    # Write pick_words.txt
    with open(PICK_FILE, "w", encoding="utf-8") as f:
        f.write("# Delete the lines you DON'T want, keep the ones you do.\n")
        f.write("# Then run:  python anki_hsk.py pick\n")
        f.write("# Lines starting with # are ignored.\n")
        f.write("# Format: 中文 | Pinyin | English\n\n")
        if sorted_vocab:
            f.write("# ── New words from documents / mylist ──\n")
            for w in sorted_vocab:
                py, en, _ = dictionary[w]
                f.write(f"{w} | {py} | {en}\n")

    print(f"\nWrote {len(sorted_vocab)} new words to {PICK_FILE}")

    # ── Decompose: single chars from existing deck + new words ───────────
    # Collect all multi-char sources: existing deck words + new candidates
    all_multi = set()
    for w in existing_words:
        if len(w) > 1:
            all_multi.add(w)
    for w in sorted_vocab:
        if len(w) > 1:
            all_multi.add(w)

    # Find single chars that have no card yet
    missing_chars = set()
    char_lines = []
    for w in all_multi:
        for ch in w:
            if is_cjk(ch) and ch not in existing_words and ch not in never_propose:
                missing_chars.add(ch)

    if missing_chars:
        print(f"\n  Decomposing: {len(missing_chars)} missing single-character card(s)")
        char_cache = load_char_info_cache()
        char_fetched = 0
        char_lines = []

        for ch in sorted(missing_chars):
            english, pinyin, pos_tags, alts, was_cached = lookup_full(ch, pos_cache, char_cache)
            if not was_cached:
                char_fetched += 1
                time.sleep(0.3)
            definition = build_definition(english, alts)
            new_def, removed = remove_pinyin_from_definition(definition, pinyin)
            if removed:
                print(f"    \u26a0 Pinyin lookalike in {ch} ({pinyin}): removed {removed}")
                definition = new_def
            char_lines.append(f"{ch} | {pinyin} | {definition}")
            print(f"    + {ch}  {pinyin:10} {definition:40} [{', '.join(pos_tags)}]")

        # Append single chars section to pick_words.txt
        with open(PICK_FILE, "a", encoding="utf-8") as f:
            f.write("\n# ── Single characters (decomposed from multi-char words) ──\n")
            for line in char_lines:
                f.write(line + "\n")

        save_char_info_cache(char_cache)
        save_pos_cache(pos_cache)
        print(f"  Fetched {char_fetched}, cached {len(missing_chars) - char_fetched}")
        print(f"  → Added {len(missing_chars)} single chars to {PICK_FILE}")

    # ── Collision detection against existing deck ─────────────────────────
    # Load existing definitions and check for ambiguous primary English
    deck_defs = {}  # english_key → list of chinese words
    for note in load_deck_records():
        zh = strip_html(note["fields"].get("中文", ""))
        en = strip_html(note["fields"].get("English", ""))
        if zh and en:
            key = en.lower().split(",")[0].strip()
            deck_defs.setdefault(key, []).append(zh)

    # Check new words + single chars for collisions
    collisions = []
    all_new_defs = {}
    for w in sorted_vocab:
        _, en, _ = dictionary[w]
        key = en.lower().split(",")[0].strip()
        all_new_defs.setdefault(key, []).append(w)
    if missing_chars:
        for line in char_lines:
            parts = line.split("|")
            ch, en = parts[0].strip(), parts[2].strip()
            key = en.lower().split(",")[0].strip()
            all_new_defs.setdefault(key, []).append(ch)

    for key, new_words in all_new_defs.items():
        existing = deck_defs.get(key, [])
        all_words = existing + new_words
        if len(all_words) > 1:
            collisions.append((key, all_words))

    if collisions:
        print(f"\n⚠ {len(collisions)} potential definition collision(s) — review in pick_words.txt:")
        for key, words in sorted(collisions):
            print(f"  \"{key}\" → {', '.join(words)}")

    print("\n>> Edit pick_words.txt — delete words you don't want <<")
    print(">> Then run: python anki_hsk.py pick <<")


if __name__ == "__main__":
    main()
