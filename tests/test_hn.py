import importlib.machinery
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


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
                    "prompt_word": "{word}",
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


if __name__ == "__main__":
    unittest.main()
