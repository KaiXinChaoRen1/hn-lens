"""Tests for the terminal text-measurement and wrapping helpers.

These functions decide how every line of stories, comments and articles is
laid out, so width miscalculations show up as visible corruption. They are
pure and deterministic, which makes them cheap to pin down tightly.
"""

import unittest

from hnmod import load_hn_module

mod = load_hn_module()


class GetDisplayWidthTests(unittest.TestCase):
    def test_ascii_is_one_column_each(self):
        self.assertEqual(mod.get_display_width("hello"), 5)

    def test_cjk_is_two_columns_each(self):
        self.assertEqual(mod.get_display_width("中文"), 4)

    def test_mixed_ascii_and_cjk(self):
        self.assertEqual(mod.get_display_width("a中b"), 4)

    def test_empty_string_is_zero(self):
        self.assertEqual(mod.get_display_width(""), 0)

    def test_fullwidth_punctuation_counts_as_two(self):
        self.assertEqual(mod.get_display_width("！"), 2)


class SplitWrapTokensTests(unittest.TestCase):
    def test_keeps_ascii_words_whole_and_cjk_per_char(self):
        self.assertEqual(
            mod.split_wrap_tokens("ab 中文"),
            ["ab", " ", "中", "文"],
        )

    def test_runs_of_whitespace_collapse_into_one_token(self):
        self.assertEqual(mod.split_wrap_tokens("a   b"), ["a", "   ", "b"])

    def test_empty_line_yields_no_tokens(self):
        self.assertEqual(mod.split_wrap_tokens(""), [])


class WrapLongTokenTests(unittest.TestCase):
    def test_breaks_token_to_fit_width(self):
        parts = mod.wrap_long_token("abcdef", 2)
        self.assertEqual(parts, ["ab", "cd", "ef"])
        self.assertTrue(all(mod.get_display_width(p) <= 2 for p in parts))

    def test_never_returns_empty_list(self):
        self.assertEqual(mod.wrap_long_token("", 5), [""])

    def test_cjk_token_respects_double_width(self):
        parts = mod.wrap_long_token("中文字", 2)
        self.assertEqual(parts, ["中", "文", "字"])


class WrapByWidthTests(unittest.TestCase):
    def test_keeps_english_words_intact(self):
        self.assertEqual(
            mod.wrap_by_width("hello world translation test", 12),
            ["hello world", "translation", "test"],
        )

    def test_breaks_overlong_single_token(self):
        wrapped = mod.wrap_by_width("supercalifragilistic", 10)
        self.assertGreater(len(wrapped), 1)
        self.assertTrue(all(mod.get_display_width(p) <= 10 for p in wrapped))

    def test_preserves_explicit_newlines_as_blank_lines(self):
        self.assertEqual(mod.wrap_by_width("a\n\nb", 10), ["a", "", "b"])

    def test_empty_text_returns_single_blank_line(self):
        self.assertEqual(mod.wrap_by_width("", 10), [""])

    def test_tiny_width_returns_text_unchanged(self):
        # width <= 1 cannot fit even a single CJK glyph, so it bails out.
        self.assertEqual(mod.wrap_by_width("anything", 1), ["anything"])

    def test_no_wrapped_line_exceeds_width(self):
        text = "the quick brown fox jumps over the lazy dog repeatedly"
        for line in mod.wrap_by_width(text, 15):
            self.assertLessEqual(mod.get_display_width(line), 15)

    def test_lines_are_right_trimmed(self):
        for line in mod.wrap_by_width("a b c d e f", 4):
            self.assertEqual(line, line.rstrip())


class NormalizeWhitespaceTests(unittest.TestCase):
    def test_collapses_runs_and_trims(self):
        self.assertEqual(mod.normalize_whitespace("  a   b\tc \n"), "a b c")

    def test_empty_input(self):
        self.assertEqual(mod.normalize_whitespace(""), "")


class StripHtmlTests(unittest.TestCase):
    def test_removes_tags_and_unescapes_entities(self):
        self.assertEqual(mod.strip_html("<b>a&amp;b</b>"), "a&b")

    def test_decodes_entities_in_urls(self):
        self.assertEqual(
            mod.strip_html("https:&#x2F;&#x2F;example.com&#x2F;x"),
            "https://example.com/x",
        )

    def test_collapses_excess_blank_lines(self):
        self.assertEqual(mod.strip_html("a\n\n\n\nb"), "a\n\nb")

    def test_empty_input(self):
        self.assertEqual(mod.strip_html(""), "")


class ExtractDomainTests(unittest.TestCase):
    def test_strips_scheme_path_and_www(self):
        self.assertEqual(mod.extract_domain("https://www.example.com/a/b"), "example.com")

    def test_keeps_subdomain_other_than_www(self):
        self.assertEqual(mod.extract_domain("https://blog.example.com/x"), "blog.example.com")

    def test_none_and_garbage_are_empty(self):
        self.assertEqual(mod.extract_domain(None), "")
        self.assertEqual(mod.extract_domain("not a url"), "")


class UrlPredicateTests(unittest.TestCase):
    def test_looks_like_url_text_accepts_bare_and_prefixed(self):
        self.assertTrue(mod.looks_like_url_text("https://example.com"))
        self.assertTrue(mod.looks_like_url_text("[link] https://example.com"))
        self.assertTrue(mod.looks_like_url_text("www.example.com"))

    def test_looks_like_url_text_rejects_sentences_with_a_url(self):
        self.assertFalse(mod.looks_like_url_text("see https://example.com now"))

    def test_contains_url_finds_embedded_url(self):
        self.assertTrue(mod.contains_url("read https://example.com please"))
        self.assertFalse(mod.contains_url("no link here"))


class IsStructuredArticleLineTests(unittest.TestCase):
    def test_recognises_markup_prefixes(self):
        for line in ("# Heading", "> quote", "• bullet", "    code", "1. item", "a | b"):
            self.assertTrue(mod.is_structured_article_line(line), line)

    def test_plain_text_is_unstructured(self):
        self.assertFalse(mod.is_structured_article_line("just a sentence"))
        self.assertFalse(mod.is_structured_article_line(""))


class _RecordingScreen:
    """Minimal stdscr stand-in that records addnstr spans."""

    def __init__(self):
        self.calls = []

    def addnstr(self, y, x, text, n):
        self.calls.append((x, text, n))

    def attron(self, *_):
        pass

    def attroff(self, *_):
        pass


class RenderTextWithUrlsTests(unittest.TestCase):
    def test_splits_prefix_url_and_suffix_into_separate_spans(self):
        screen = _RecordingScreen()
        mod.render_text_with_urls(screen, 0, 0, "see https://x.io now", 80)
        texts = [text for _, text, _ in screen.calls]
        self.assertEqual(texts, ["see ", "https://x.io", " now"])

    def test_advances_x_cursor_across_spans(self):
        screen = _RecordingScreen()
        mod.render_text_with_urls(screen, 0, 5, "see https://x.io now", 80)
        xs = [x for x, _, _ in screen.calls]
        self.assertEqual(xs, [5, 5 + len("see "), 5 + len("see https://x.io")])

    def test_non_positive_width_draws_nothing(self):
        screen = _RecordingScreen()
        mod.render_text_with_urls(screen, 0, 0, "anything", 0)
        self.assertEqual(screen.calls, [])

    def test_plain_text_without_url_is_one_span(self):
        screen = _RecordingScreen()
        mod.render_text_with_urls(screen, 0, 0, "no links here", 80)
        self.assertEqual([t for _, t, _ in screen.calls], ["no links here"])


if __name__ == "__main__":
    unittest.main()
