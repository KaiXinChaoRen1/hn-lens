import importlib.machinery
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock
import requests


ROOT = Path(__file__).resolve().parents[1]
HN_PATH = ROOT / "hn"


def load_hn_module():
    name = "hn_under_test"
    loader = importlib.machinery.SourceFileLoader(name, str(HN_PATH))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class DummyScreen:
    def __init__(self):
        self._timeout = None

    def getmaxyx(self):
        return (30, 100)

    def timeout(self, value):
        self._timeout = value

    def keypad(self, enabled):
        return None

    def erase(self):
        return None

    def addnstr(self, *args, **kwargs):
        return None

    def refresh(self):
        return None

    def noutrefresh(self):
        return None

    def attron(self, *args, **kwargs):
        return None

    def attroff(self, *args, **kwargs):
        return None

    def getch(self):
        return -1


class ImmediateThread:
    def __init__(self, target=None, daemon=None):
        self.target = target

    def start(self):
        if self.target:
            self.target()


class HNViewerTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_hn_module()
        self.screen = DummyScreen()
        self.patches = [
            mock.patch.object(
                self.mod,
                "load_config",
                return_value={
                    "url": "https://example.com",
                    "key": "test-key",
                    "model": "test-model",
                    "prompt_item": "{text}",
                },
            ),
            mock.patch.object(self.mod, "load_cache", return_value={}),
            mock.patch.object(self.mod, "load_stories_cache", return_value={}),
            mock.patch.object(self.mod, "save_cache"),
            mock.patch.object(self.mod, "save_stories_cache"),
            mock.patch.object(self.mod.curses, "color_pair", return_value=0),
            mock.patch.object(self.mod.curses, "has_colors", return_value=False),
        ]
        for patcher in self.patches:
            patcher.start()
        self.addCleanup(self._cleanup_patches)

    def _cleanup_patches(self):
        for patcher in reversed(self.patches):
            patcher.stop()

    def make_viewer(self):
        return self.mod.HNViewer(self.screen)

    def make_story(self, object_id="1", title="Story"):
        return self.mod.Story(
            title=title,
            author="author",
            points=10,
            num_comments=5,
            url="https://example.com/story",
            object_id=object_id,
            created_at=1,
        )

    def test_force_refresh_keeps_existing_stories_on_fetch_error(self):
        viewer = self.make_viewer()
        viewer.stories = [self.make_story()]
        viewer.story_has_more = True
        viewer.story_next_offset = 1

        with mock.patch.object(self.mod, "fetch_stories", return_value=([], False, "boom")):
            viewer.load_stories("top", force_refresh=True)

        self.assertEqual([story.object_id for story in viewer.stories], ["1"])
        self.assertTrue(viewer.story_has_more)
        self.assertEqual(viewer.story_next_offset, 1)
        self.assertIn("Refresh failed", viewer.status)

    def test_enter_and_exit_search_ignore_curs_set_errors(self):
        with mock.patch.object(self.mod.curses, "curs_set", side_effect=self.mod.curses.error):
            viewer = self.make_viewer()
            viewer.enter_search()
            viewer.exit_search()

        self.assertFalse(viewer.search_mode)

    def test_translation_errors_are_not_cached(self):
        viewer = self.make_viewer()
        cache_key = self.mod.get_cache_key("hello")

        with mock.patch.object(self.mod, "call_llm", return_value="[错误] timeout"), mock.patch.object(
            self.mod.threading, "Thread", ImmediateThread
        ):
            viewer.start_translation("hello")

        self.assertEqual(viewer.trans_result, "[错误] timeout")
        self.assertNotIn(cache_key, viewer.cache)

    def test_stale_error_cache_is_ignored_and_replaced(self):
        viewer = self.make_viewer()
        cache_key = self.mod.get_cache_key("hello")
        viewer.cache[cache_key] = "[错误] stale"

        with mock.patch.object(self.mod, "call_llm", return_value="translated"), mock.patch.object(
            self.mod.threading, "Thread", ImmediateThread
        ):
            viewer.start_translation("hello")

        self.assertEqual(viewer.trans_result, "translated")
        self.assertEqual(viewer.cache[cache_key], "translated")

    def test_translation_pane_defaults_closed(self):
        viewer = self.make_viewer()
        self.assertFalse(viewer.article_pane_open)

    def test_pane_translation_shares_cache_key_with_popup(self):
        # The pane and the `T` popup must hit the same cache entry so a
        # paragraph translated one way shows up instantly the other way.
        viewer = self.make_viewer()
        viewer.article_paragraphs = [{"text": "hello article"}]
        viewer.article_selected = 0
        self.assertEqual(
            viewer._selected_paragraph_key(),
            self.mod.get_cache_key("hello article"),
        )

    def test_open_pane_translates_selected_paragraph_and_caches(self):
        viewer = self.make_viewer()
        viewer.article_pane_open = True
        viewer.article_paragraphs = [{"text": "hello article"}]
        viewer.article_selected = 0
        key = self.mod.get_cache_key("hello article")

        with mock.patch.object(self.mod, "call_llm", return_value="译文"), mock.patch.object(
            self.mod.threading, "Thread", ImmediateThread
        ):
            viewer._ensure_selected_paragraph_translation()

        self.assertEqual(viewer.cache[key], "译文")
        self.assertNotIn(key, viewer.article_pane_inflight)
        self.assertEqual(viewer._build_selected_article_translation_lines(60), ["译文"])

    def test_closed_pane_does_not_translate(self):
        viewer = self.make_viewer()
        viewer.article_pane_open = False
        viewer.article_paragraphs = [{"text": "hello article"}]
        viewer.article_selected = 0

        with mock.patch.object(self.mod, "call_llm") as llm, mock.patch.object(
            self.mod.threading, "Thread", ImmediateThread
        ):
            viewer._ensure_selected_paragraph_translation()

        llm.assert_not_called()

    def test_pane_translation_error_is_surfaced_but_not_cached(self):
        viewer = self.make_viewer()
        viewer.article_pane_open = True
        viewer.article_paragraphs = [{"text": "hello article"}]
        viewer.article_selected = 0
        key = self.mod.get_cache_key("hello article")

        with mock.patch.object(self.mod, "call_llm", return_value="[错误] timeout"), mock.patch.object(
            self.mod.threading, "Thread", ImmediateThread
        ):
            viewer._ensure_selected_paragraph_translation()

        self.assertNotIn(key, viewer.cache)
        self.assertEqual(viewer.article_pane_errors[key], "[错误] timeout")
        self.assertEqual(viewer._build_selected_article_translation_lines(60)[0], "[错误] timeout")

    def test_article_extraction_prefers_summary_over_full_body_noise(self):
        desired = "Important article sentence. " * 12
        noisy = "FILLERMARKER " * 300
        html = f"<html><body><div><p>{desired}</p></div><div>{noisy}</div></body></html>"

        class FakeResponse:
            text = html

            def raise_for_status(self):
                return None

        class FakeDocument:
            def __init__(self, source_html):
                self.source_html = source_html

            def summary(self):
                return f"<div><p>{desired}</p></div>"

        fake_readability = types.SimpleNamespace(Document=FakeDocument)

        with mock.patch.object(self.mod.requests, "get", return_value=FakeResponse()), mock.patch.dict(
            sys.modules, {"readability": fake_readability}
        ):
            extracted = self.mod.fetch_article_text("https://example.com/article")

        self.assertIn("Important article sentence.", extracted)
        self.assertNotIn("FILLERMARKER", extracted)

    def test_prepare_article_lines_filters_top_metadata_blocks(self):
        text = "\n".join(
            [
                "8 hours ago",
                "",
                "Sofia Ferreira Santos",
                "",
                "# Headline",
                "",
                "Real article paragraph starts here with substance.",
            ]
        )

        prepared = self.mod.prepare_article_lines(text, 60)

        joined = "\n".join(prepared)
        self.assertNotIn("8 hours ago", joined)
        self.assertNotIn("Sofia Ferreira Santos", joined)
        self.assertIn("# Headline", joined)
        self.assertIn("Real article paragraph starts here", joined)

    def test_short_lowercase_opening_sentence_is_not_filtered_as_byline(self):
        # Regression: re.IGNORECASE used to defeat the byline pattern's
        # capitalization anchor, silently dropping real opening sentences.
        self.assertFalse(self.mod.is_noise_article_block(["this changes everything"], 0))
        self.assertFalse(self.mod.is_noise_article_block(["The cat sat on the mat today"], 0))

    def test_real_bylines_and_timestamps_are_still_filtered(self):
        self.assertTrue(self.mod.is_noise_article_block(["Sofia Ferreira Santos"], 0))
        self.assertTrue(self.mod.is_noise_article_block(["By Jane Doe"], 0))
        self.assertTrue(self.mod.is_noise_article_block(["8 hours ago"], 0))
        self.assertTrue(self.mod.is_noise_article_block(["Updated 3 days ago"], 1))

    def test_prepare_article_lines_wraps_list_items_cleanly(self):
        text = "• This is a long bullet point that should wrap onto the next line without losing its visual structure."

        prepared = self.mod.prepare_article_lines(text, 32)

        self.assertTrue(prepared[0].startswith("• "))
        self.assertTrue(any(line.startswith("  ") for line in prepared[1:]))

    def test_wrap_by_width_keeps_english_words_intact(self):
        wrapped = self.mod.wrap_by_width("hello world translation test", 12)
        self.assertEqual(wrapped, ["hello world", "translation", "test"])

    def test_wrap_by_width_still_breaks_very_long_tokens(self):
        wrapped = self.mod.wrap_by_width("supercalifragilisticexpialidocious", 10)
        self.assertGreater(len(wrapped), 1)
        self.assertTrue(all(self.mod.get_display_width(part) <= 10 for part in wrapped))

    def test_time_ago_clamps_future_timestamps(self):
        future = self.mod.time.time() + 120
        self.assertEqual(self.mod.time_ago(int(future)), "0s ago")

    def test_strip_html_decodes_html_entities_in_urls(self):
        text = "https:&#x2F;&#x2F;github.com&#x2F;openclaw"
        self.assertEqual(self.mod.strip_html(text), "https://github.com/openclaw")

    def test_prepare_article_lines_marks_link_lines(self):
        prepared = self.mod.prepare_article_lines("https://example.com/path", 60, filter_noise=False)
        self.assertEqual(prepared[0], "[link] https://example.com/path")

    def test_adjust_article_scroll_shows_full_selected_paragraph_when_it_fits(self):
        selected = {"start": 8, "end": 11}
        adjusted = self.mod.adjust_article_scroll_for_selection(0, selected, 10)
        self.assertEqual(adjusted, 2)

    def test_adjust_article_scroll_keeps_long_paragraph_top_aligned(self):
        selected = {"start": 8, "end": 20}
        adjusted = self.mod.adjust_article_scroll_for_selection(0, selected, 10)
        self.assertEqual(adjusted, 8)

    def test_call_llm_http_error_includes_api_message(self):
        response = mock.Mock()
        response.status_code = 400
        response.json.return_value = {
            "error": {
                "message": "context length exceeded",
                "type": "invalid_request_error",
                "code": "context_length_exceeded",
            }
        }
        http_error = requests.exceptions.HTTPError(response=response)

        with mock.patch.object(self.mod.requests, "post", side_effect=http_error):
            result = self.mod.call_llm("hello", self.mod.load_config())

        self.assertIn("API 请求失败 (400)", result)
        self.assertIn("context length exceeded", result)


if __name__ == "__main__":
    unittest.main()
