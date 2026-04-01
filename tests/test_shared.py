"""Tests for translation, pinyin handling, and English matching utilities."""
import os
import sys
import unittest

# Add src/ to path so we can import shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from shared import (
    strip_pinyin_tones,
    remove_pinyin_from_definition,
    build_definition,
    strip_html,
    is_cjk,
)


class TestStripPinyinTones(unittest.TestCase):
    """Test tone mark and tone number removal from pinyin."""

    def test_tone_marks(self):
        self.assertEqual(strip_pinyin_tones("shū"), "shu")
        self.assertEqual(strip_pinyin_tones("liú"), "liu")
        self.assertEqual(strip_pinyin_tones("nǚ"), "nü")
        self.assertEqual(strip_pinyin_tones("lǜ"), "lü")

    def test_tone_numbers(self):
        self.assertEqual(strip_pinyin_tones("shu1"), "shu")
        self.assertEqual(strip_pinyin_tones("liu2"), "liu")
        self.assertEqual(strip_pinyin_tones("ma3"), "ma")

    def test_uppercase(self):
        self.assertEqual(strip_pinyin_tones("Shū"), "shu")
        self.assertEqual(strip_pinyin_tones("LIÚ"), "liu")

    def test_multi_syllable(self):
        self.assertEqual(strip_pinyin_tones("péngyou"), "pengyou")
        self.assertEqual(strip_pinyin_tones("zhōngguó"), "zhongguo")

    def test_no_tones(self):
        self.assertEqual(strip_pinyin_tones("ma"), "ma")
        self.assertEqual(strip_pinyin_tones("shu"), "shu")

    def test_empty(self):
        self.assertEqual(strip_pinyin_tones(""), "")


class TestRemovePinyinFromDefinition(unittest.TestCase):
    """Test detection and removal of English words that match pinyin."""

    def test_basic_removal(self):
        eng, removed = remove_pinyin_from_definition("shu, comfortable, cozy", "shū")
        self.assertEqual(eng, "comfortable, cozy")
        self.assertEqual(removed, ["shu"])

    def test_no_removal_safe_word(self):
        # "he" is a common English word, should NOT be removed
        eng, removed = remove_pinyin_from_definition("he, him", "tā")
        self.assertEqual(eng, "he, him")
        self.assertEqual(removed, [])

    def test_no_removal_safe_word_she(self):
        eng, removed = remove_pinyin_from_definition("she, her", "tā")
        self.assertEqual(eng, "she, her")
        self.assertEqual(removed, [])

    def test_removal_liu(self):
        eng, removed = remove_pinyin_from_definition("liu, willow", "liú")
        self.assertEqual(eng, "willow")
        self.assertEqual(removed, ["liu"])

    def test_no_removal_different_pinyin(self):
        eng, removed = remove_pinyin_from_definition("can, able to", "néng")
        self.assertEqual(eng, "can, able to")
        self.assertEqual(removed, [])

    def test_no_removal_when_no_match(self):
        eng, removed = remove_pinyin_from_definition("big, large", "dà")
        self.assertEqual(eng, "big, large")
        self.assertEqual(removed, [])

    def test_removal_among_multiple(self):
        eng, removed = remove_pinyin_from_definition("chi, eat, consume", "chī")
        self.assertEqual(eng, "eat, consume")
        self.assertEqual(removed, ["chi"])

    def test_empty_english(self):
        eng, removed = remove_pinyin_from_definition("", "shū")
        self.assertEqual(eng, "")
        self.assertEqual(removed, [])

    def test_empty_pinyin(self):
        eng, removed = remove_pinyin_from_definition("book, letter", "")
        self.assertEqual(eng, "book, letter")
        self.assertEqual(removed, [])

    def test_single_word_removal_leaves_empty(self):
        # If the only word IS the pinyin lookalike and it's removed, should be empty
        eng, removed = remove_pinyin_from_definition("shu", "shū")
        self.assertEqual(eng, "")
        self.assertEqual(removed, ["shu"])

    def test_safe_words_not_removed(self):
        """Ensure common English words in the safe list are never removed."""
        # "ban" is both English and pinyin — should be safe
        eng, removed = remove_pinyin_from_definition("ban, prohibit", "bàn")
        self.assertEqual(eng, "ban, prohibit")
        self.assertEqual(removed, [])

    def test_case_insensitive(self):
        eng, removed = remove_pinyin_from_definition("Shu, comfortable", "shū")
        self.assertEqual(removed, ["Shu"])


class TestBuildDefinition(unittest.TestCase):
    """Test combining primary translation with alternatives."""

    def test_no_alternatives(self):
        self.assertEqual(build_definition("book", []), "book")

    def test_with_alternatives(self):
        result = build_definition("book", ["letter", "document"])
        self.assertEqual(result, "book, letter, document")

    def test_dedup(self):
        result = build_definition("book", ["book", "letter"])
        self.assertEqual(result, "book, letter")

    def test_max_total(self):
        result = build_definition("a", ["b", "c", "d", "e", "f"], max_total=3)
        self.assertEqual(result, "a, b, c")


class TestStripHtml(unittest.TestCase):
    """Test HTML tag and entity removal."""

    def test_basic_tags(self):
        self.assertEqual(strip_html("<b>hello</b>"), "hello")

    def test_nbsp(self):
        self.assertEqual(strip_html("hello&nbsp;world"), "hello world")

    def test_no_html(self):
        self.assertEqual(strip_html("plain text"), "plain text")


class TestIsCjk(unittest.TestCase):
    """Test CJK character detection."""

    def test_cjk(self):
        self.assertTrue(is_cjk("中"))
        self.assertTrue(is_cjk("舒"))

    def test_non_cjk(self):
        self.assertFalse(is_cjk("a"))
        self.assertFalse(is_cjk("1"))
        self.assertFalse(is_cjk(" "))


if __name__ == "__main__":
    unittest.main()
