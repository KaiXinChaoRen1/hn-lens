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


class TruncateArticleTextTests(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(mod.truncate_article_text("short body"), "short body")

    def test_long_text_gets_truncation_marker(self):
        out = mod.truncate_article_text("x" * (mod.ARTICLE_CHAR_LIMIT + 500))
        self.assertTrue(out.endswith("已截断）"))
        # Body is capped at the limit; only the short marker is added past it.
        self.assertLessEqual(len(out), mod.ARTICLE_CHAR_LIMIT + 20)


class AttrKeywordHitTests(unittest.TestCase):
    noise = ("ad", "ads", "nav", "share", "related", "comment", "advert")

    def test_short_keyword_needs_word_boundary(self):
        # 'ad' must not match real content classes it merely sits inside.
        for blob in ("article-header", "reading-content", "story-header",
                     "thread", "headline", "breadcrumb"):
            self.assertFalse(mod.attr_keyword_hit(blob, self.noise), blob)

    def test_short_keyword_matches_whole_token(self):
        self.assertTrue(mod.attr_keyword_hit("ad-slot", self.noise))
        self.assertTrue(mod.attr_keyword_hit("main nav", self.noise))

    def test_long_keyword_matches_as_substring(self):
        self.assertTrue(mod.attr_keyword_hit("advertisement", self.noise))
        self.assertTrue(mod.attr_keyword_hit("comments-section", self.noise))
        self.assertTrue(mod.attr_keyword_hit("related-posts", self.noise))


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


class ParagraphDisplayTests(unittest.TestCase):
    def test_build_display_lines_tracks_start_and_end(self):
        paras = [{"text": "line one\nline two"}, {"text": "solo"}]
        lines, rendered = mod.build_article_display_lines(paras)
        first = rendered[0]
        # start points at the first text line (no [P1] marker any more)
        self.assertEqual(lines[first["start"]], "line one")
        self.assertEqual(lines[first["end"]], "line two")
        self.assertEqual(first["end"] - first["start"], 1)

    def test_paragraphs_separated_by_single_blank_line(self):
        lines, rendered = mod.build_article_display_lines([{"text": "a"}, {"text": "b"}])
        # one blank line sits between the two paragraphs, none trails the end
        self.assertEqual(lines, ["a", "", "b"])

    def test_display_lines_do_not_end_on_blank(self):
        lines, _ = mod.build_article_display_lines([{"text": "only"}])
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
            headers = {"Content-Type": "text/html; charset=utf-8"}

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
            extracted, error = mod.fetch_article_text("https://example.com/article")
        self.assertIsNone(error)
        self.assertIn("Important article sentence.", extracted)
        self.assertNotIn("FILLERMARKER", extracted)

    def test_empty_url_returns_reason(self):
        text, error = mod.fetch_article_text("")
        self.assertIsNone(text)
        self.assertTrue(error)

    def test_network_failure_returns_reason(self):
        with mock.patch.object(mod.requests, "get", side_effect=Exception("boom")):
            text, error = mod.fetch_article_text("https://example.com")
        self.assertIsNone(text)
        self.assertIn("boom", error)

    def test_missing_charset_triggers_encoding_sniff(self):
        # No charset in the header -> requests would default to ISO-8859-1, so
        # fetch should switch to the sniffed encoding before reading .text.
        class FakeResponse:
            headers = {"Content-Type": "text/html"}
            apparent_encoding = "utf-8"
            encoding = "ISO-8859-1"
            text = "<html><body><p>a real sentence with substance here.</p></body></html>"

            def raise_for_status(self):
                return None

        fake = FakeResponse()
        with mock.patch.object(mod.requests, "get", return_value=fake):
            mod.fetch_article_text("https://example.com")
        self.assertEqual(fake.encoding, "utf-8")

    def test_non_html_content_type_reports_reason(self):
        class FakeResponse:
            text = "%PDF-1.7 ..."
            headers = {"Content-Type": "application/pdf"}

            def raise_for_status(self):
                return None

        with mock.patch.object(mod.requests, "get", return_value=FakeResponse()):
            text, error = mod.fetch_article_text("https://example.com/file.pdf")
        self.assertIsNone(text)
        self.assertIn("application/pdf", error)


if __name__ == "__main__":
    unittest.main()
