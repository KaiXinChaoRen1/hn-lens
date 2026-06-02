"""Tests for article extraction, block classification and paragraph labeling.

This is the most heuristic-heavy part of the app: it turns arbitrary web HTML
into clean, paragraph-numbered reading text and drives translation. Small
regressions here quietly drop or scramble article content, so the heuristics
are worth nailing down.
"""

import sys
import types
import unittest
from unittest import mock

from hnmod import load_hn_module

mod = load_hn_module()


class SplitArticleBlocksTests(unittest.TestCase):
    def test_blank_lines_separate_blocks(self):
        lines = ["a", "b", "", "c", "", ""]
        self.assertEqual(mod.split_article_blocks(lines), [["a", "b"], ["c"]])

    def test_trailing_block_without_blank_is_kept(self):
        self.assertEqual(mod.split_article_blocks(["only"]), [["only"]])

    def test_all_blank_yields_nothing(self):
        self.assertEqual(mod.split_article_blocks(["", "  ", ""]), [])


class ClassifyArticleBlockTests(unittest.TestCase):
    def test_heading(self):
        self.assertEqual(mod.classify_article_block(["# Title"]), "heading")

    def test_quote_requires_all_lines_quoted(self):
        self.assertEqual(mod.classify_article_block(["> a", "> b"]), "quote")
        self.assertEqual(mod.classify_article_block(["> a", "b"]), "paragraph")

    def test_code_block(self):
        self.assertEqual(mod.classify_article_block(["    x = 1", "    y = 2"]), "code")

    def test_list_accepts_bullets_and_numbers(self):
        self.assertEqual(mod.classify_article_block(["• a", "2. b"]), "list")

    def test_table_needs_enough_pipe_rows(self):
        self.assertEqual(mod.classify_article_block(["a | b", "c | d"]), "table")

    def test_plain_paragraph(self):
        self.assertEqual(mod.classify_article_block(["just text"]), "paragraph")

    def test_empty_block(self):
        self.assertEqual(mod.classify_article_block([]), "empty")


class LooksLikeBylineTests(unittest.TestCase):
    def test_capitalized_names_are_bylines(self):
        self.assertTrue(mod.looks_like_byline("Sofia Ferreira Santos"))
        self.assertTrue(mod.looks_like_byline("By Jane Doe"))
        self.assertTrue(mod.looks_like_byline("Cher"))

    def test_lowercase_sentences_are_not_bylines(self):
        self.assertFalse(mod.looks_like_byline("this changes everything"))
        self.assertFalse(mod.looks_like_byline("The cat sat on the mat today"))

    def test_too_many_words_is_not_a_byline(self):
        self.assertFalse(mod.looks_like_byline("One Two Three Four Five"))

    def test_empty_is_not_a_byline(self):
        self.assertFalse(mod.looks_like_byline(""))


class IsNoiseArticleBlockTests(unittest.TestCase):
    def test_timestamp_at_top_is_noise(self):
        self.assertTrue(mod.is_noise_article_block(["8 hours ago"], 0))
        self.assertTrue(mod.is_noise_article_block(["Updated 3 days ago"], 1))

    def test_noise_keyword_blocks(self):
        self.assertTrue(mod.is_noise_article_block(["Subscribe to our newsletter"], 5))

    def test_source_prefix_is_noise(self):
        self.assertTrue(mod.is_noise_article_block(["Source: Reuters"], 9))

    def test_empty_block_is_noise(self):
        self.assertTrue(mod.is_noise_article_block([""], 0))

    def test_real_paragraph_is_kept(self):
        block = ["This is a substantive opening paragraph with real content."]
        self.assertFalse(mod.is_noise_article_block(block, 0))

    def test_byline_only_filtered_near_the_top(self):
        # Same capitalized line is noise at the top but content lower down.
        self.assertTrue(mod.is_noise_article_block(["Sofia Ferreira Santos"], 0))
        self.assertFalse(mod.is_noise_article_block(["Sofia Ferreira Santos"], 5))


class WrapArticleBlockTests(unittest.TestCase):
    def test_quote_lines_keep_marker(self):
        out = mod.wrap_article_block(["> hello world"], 40)
        self.assertTrue(all(line.startswith("> ") for line in out))

    def test_code_lines_are_truncated_not_wrapped(self):
        out = mod.wrap_article_block(["    " + "x" * 100], 20)
        self.assertEqual(len(out), 1)
        self.assertLessEqual(len(out[0]), 20)

    def test_list_continuation_is_indented(self):
        out = mod.wrap_article_block(["• " + "word " * 20], 20)
        self.assertTrue(out[0].startswith("• "))
        self.assertTrue(any(line.startswith("  ") for line in out[1:]))

    def test_table_rows_get_bar_prefix(self):
        out = mod.wrap_article_block(["a | b", "c | d"], 40)
        self.assertTrue(all(line.startswith("│ ") for line in out))

    def test_bare_url_paragraph_is_marked_as_link(self):
        out = mod.wrap_article_block(["https://example.com/page"], 60)
        self.assertTrue(out[0].startswith("[link] "))


class PrepareArticleLinesTests(unittest.TestCase):
    def test_filters_top_metadata_but_keeps_heading_and_body(self):
        text = "\n".join(
            ["8 hours ago", "", "Sofia Ferreira Santos", "", "# Headline", "",
             "Real article paragraph starts here with substance."]
        )
        joined = "\n".join(mod.prepare_article_lines(text, 60))
        self.assertNotIn("8 hours ago", joined)
        self.assertNotIn("Sofia Ferreira Santos", joined)
        self.assertIn("# Headline", joined)
        self.assertIn("Real article paragraph starts here", joined)

    def test_blank_line_inserted_between_blocks(self):
        text = "First paragraph.\n\nSecond paragraph."
        out = mod.prepare_article_lines(text, 60, filter_noise=False)
        self.assertIn("", out)

    def test_link_line_marked_when_noise_filter_off(self):
        out = mod.prepare_article_lines("https://example.com/path", 60, filter_noise=False)
        self.assertEqual(out[0], "[link] https://example.com/path")


class ParagraphLabelingTests(unittest.TestCase):
    def test_labels_are_sequential(self):
        labeled = mod.label_article_paragraphs([{"text": "a"}, {"text": "b"}])
        self.assertEqual([p["pid"] for p in labeled], ["P1", "P2"])

    def test_build_display_lines_tracks_start_and_end(self):
        labeled = mod.label_article_paragraphs([{"text": "line one\nline two"}, {"text": "solo"}])
        lines, rendered = mod.build_article_display_lines(labeled)
        self.assertIn("[P1]", lines)
        first = rendered[0]
        self.assertEqual(lines[first["start"]], "[P1]")
        # start..end span covers the marker plus its text lines
        self.assertEqual(first["end"] - first["start"], 2)

    def test_display_lines_do_not_end_on_blank(self):
        labeled = mod.label_article_paragraphs([{"text": "only"}])
        lines, _ = mod.build_article_display_lines(labeled)
        self.assertTrue(lines[-1].strip())


class ScrollAdjustmentTests(unittest.TestCase):
    def test_short_paragraph_scrolls_fully_into_view(self):
        self.assertEqual(
            mod.adjust_article_scroll_for_selection(0, {"start": 8, "end": 11}, 10), 2
        )

    def test_long_paragraph_top_aligns(self):
        self.assertEqual(
            mod.adjust_article_scroll_for_selection(0, {"start": 8, "end": 20}, 10), 8
        )

    def test_no_selection_returns_clamped_scroll(self):
        self.assertEqual(mod.adjust_article_scroll_for_selection(-3, None, 10), 0)


class FetchArticleTextTests(unittest.TestCase):
    def _patched_fetch(self, html, summary):
        class FakeResponse:
            text = html

            def raise_for_status(self):
                return None

        class FakeDocument:
            def __init__(self, source):
                pass

            def summary(self):
                return summary

        fake_readability = types.SimpleNamespace(Document=FakeDocument)
        return mock.patch.object(mod.requests, "get", return_value=FakeResponse()), \
            mock.patch.dict(sys.modules, {"readability": fake_readability})

    def test_prefers_clean_summary_over_page_noise(self):
        desired = "Important article sentence. " * 12
        noisy = "FILLERMARKER " * 300
        html = f"<html><body><div><p>{desired}</p></div><div>{noisy}</div></body></html>"
        get_patch, mod_patch = self._patched_fetch(html, f"<div><p>{desired}</p></div>")
        with get_patch, mod_patch:
            extracted = mod.fetch_article_text("https://example.com/article")
        self.assertIn("Important article sentence.", extracted)
        self.assertNotIn("FILLERMARKER", extracted)

    def test_empty_url_returns_none(self):
        self.assertIsNone(mod.fetch_article_text(""))

    def test_network_failure_returns_none(self):
        with mock.patch.object(mod.requests, "get", side_effect=Exception("boom")):
            self.assertIsNone(mod.fetch_article_text("https://example.com"))


if __name__ == "__main__":
    unittest.main()
