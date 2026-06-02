"""Tests for config loading, the translation cache, and the network layer.

These functions are the trust boundary with the outside world: the LLM API,
the Algolia feed, and the on-disk cache/config. They translate flaky external
responses into the typed values the UI relies on, so their error handling and
field mapping deserve direct coverage.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

import requests

from hnmod import load_hn_module

mod = load_hn_module()


class LoadConfigTests(unittest.TestCase):
    def test_maps_api_fields_to_short_keys(self):
        raw = {
            "api_url": "https://api.test/v1",
            "api_key": "sk-123",
            "api_model": "test-model",
            "prompt_item": "{text}",
        }
        with mock.patch.object(mod, "ensure_config", return_value=raw):
            cfg = mod.load_config()
        self.assertEqual(cfg["url"], "https://api.test/v1")
        self.assertEqual(cfg["key"], "sk-123")
        self.assertEqual(cfg["model"], "test-model")
        self.assertEqual(cfg["prompt_item"], "{text}")

    def test_missing_fields_fall_back_to_defaults(self):
        with mock.patch.object(mod, "ensure_config", return_value={}):
            cfg = mod.load_config()
        self.assertEqual(cfg["url"], mod.DEFAULT_CONFIG["api_url"])
        self.assertEqual(cfg["key"], "")
        self.assertEqual(cfg["model"], mod.DEFAULT_CONFIG["api_model"])


class CacheRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._patches = [
            mock.patch.object(mod, "CONFIG_DIR", self.tmp.name),
            mock.patch.object(mod, "CACHE_FILE", os.path.join(self.tmp.name, "cache.json")),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def test_save_then_load_returns_same_data(self):
        mod.save_cache({"k": "译文"})
        self.assertEqual(mod.load_cache(), {"k": "译文"})

    def test_missing_file_loads_empty(self):
        self.assertEqual(mod.load_cache(), {})

    def test_corrupt_file_loads_empty(self):
        with open(mod.CACHE_FILE, "w") as f:
            f.write("{ not json")
        self.assertEqual(mod.load_cache(), {})


class CacheKeyAndErrorTests(unittest.TestCase):
    def test_cache_key_is_stable_md5(self):
        self.assertEqual(mod.get_cache_key("hello"), mod.get_cache_key("hello"))
        self.assertNotEqual(mod.get_cache_key("a"), mod.get_cache_key("b"))

    def test_is_error_text_detects_marker(self):
        self.assertTrue(mod.is_error_text("[错误] timeout"))
        self.assertTrue(mod.is_error_text("  [错误] padded"))
        self.assertFalse(mod.is_error_text("正常翻译"))
        self.assertFalse(mod.is_error_text(""))


class FormatApiErrorTests(unittest.TestCase):
    def _resp(self, status, payload=None, text=""):
        resp = mock.Mock()
        resp.status_code = status
        resp.text = text
        if payload is None:
            resp.json.side_effect = ValueError("no json")
        else:
            resp.json.return_value = payload
        return resp

    def test_structured_error_object_is_joined(self):
        resp = self._resp(400, {"error": {"message": "too long", "type": "invalid", "code": "ctx"}})
        out = mod.format_api_error(resp)
        self.assertIn("API 请求失败 (400)", out)
        self.assertIn("too long", out)
        self.assertIn("invalid", out)

    def test_top_level_message_used_when_no_error_object(self):
        resp = self._resp(401, {"message": "bad key"})
        self.assertIn("bad key", mod.format_api_error(resp))

    def test_falls_back_to_raw_text(self):
        resp = self._resp(500, payload=None, text="Internal Server Error")
        self.assertIn("Internal Server Error", mod.format_api_error(resp))

    def test_long_detail_is_truncated(self):
        resp = self._resp(400, {"message": "x" * 500})
        out = mod.format_api_error(resp)
        self.assertIn("...", out)
        self.assertLess(len(out), 300)

    def test_no_detail_still_reports_status(self):
        resp = self._resp(503, payload=None, text="")
        self.assertEqual(mod.format_api_error(resp), "[错误] API 请求失败 (503)")


class CallLlmTests(unittest.TestCase):
    CFG = {"url": "https://api.test", "key": "k", "model": "m"}

    def test_success_returns_message_content(self):
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": [{"message": {"content": "hi"}}]}
        with mock.patch.object(mod.requests, "post", return_value=resp):
            self.assertEqual(mod.call_llm("p", self.CFG), "hi")

    def test_timeout_message(self):
        with mock.patch.object(mod.requests, "post", side_effect=requests.exceptions.Timeout):
            self.assertIn("请求超时", mod.call_llm("p", self.CFG, timeout=7))

    def test_connection_error_message(self):
        with mock.patch.object(mod.requests, "post", side_effect=requests.exceptions.ConnectionError):
            self.assertIn("无法连接", mod.call_llm("p", self.CFG))

    def test_http_error_includes_api_detail(self):
        resp = mock.Mock()
        resp.status_code = 400
        resp.json.return_value = {"error": {"message": "context length exceeded"}}
        err = requests.exceptions.HTTPError(response=resp)
        with mock.patch.object(mod.requests, "post", side_effect=err):
            out = mod.call_llm("p", self.CFG)
        self.assertIn("API 请求失败 (400)", out)
        self.assertIn("context length exceeded", out)

    def test_malformed_success_payload_is_reported(self):
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"unexpected": True}
        with mock.patch.object(mod.requests, "post", return_value=resp):
            self.assertIn("返回格式异常", mod.call_llm("p", self.CFG))


class FetchStoriesTests(unittest.TestCase):
    def _resp(self, payload):
        resp = mock.Mock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = payload
        return resp

    def test_parses_hits_and_reports_more_pages(self):
        payload = {
            "hits": [
                {"title": "A", "objectID": "1", "points": 5, "num_comments": 2, "url": "http://a"},
            ],
            "page": 0,
            "nbPages": 3,
        }
        with mock.patch.object(mod.requests, "get", return_value=self._resp(payload)):
            stories, has_more, error = mod.fetch_stories("top", 0, 20)
        self.assertIsNone(error)
        self.assertTrue(has_more)
        self.assertEqual(stories[0].title, "A")

    def test_last_page_has_no_more(self):
        payload = {"hits": [{"title": "A", "objectID": "1"}], "page": 2, "nbPages": 3}
        with mock.patch.object(mod.requests, "get", return_value=self._resp(payload)):
            _, has_more, error = mod.fetch_stories("top", 40, 20)
        self.assertIsNone(error)
        self.assertFalse(has_more)

    def test_network_error_is_returned_as_string(self):
        with mock.patch.object(mod.requests, "get", side_effect=Exception("down")):
            stories, has_more, error = mod.fetch_stories("top")
        self.assertEqual(stories, [])
        self.assertFalse(has_more)
        self.assertEqual(error, "down")

    def test_unknown_feed_falls_back_to_front_page_tag(self):
        captured = {}

        def fake_get(url, **kwargs):
            captured["url"] = url
            return self._resp({"hits": [], "page": 0, "nbPages": 1})

        with mock.patch.object(mod.requests, "get", side_effect=fake_get):
            mod.fetch_stories("nonsense")
        self.assertIn("tags=front_page", captured["url"])


class StoryFromApiTests(unittest.TestCase):
    def test_maps_fields_and_blank_url_becomes_none(self):
        story = mod.Story.from_api(
            {"title": "T", "author": "x", "points": 9, "num_comments": 3,
             "url": "", "objectID": "42", "created_at_i": 1000, "_tags": ["ask_hn"]}
        )
        self.assertEqual(story.object_id, "42")
        self.assertIsNone(story.url)
        self.assertEqual(story.story_type, "ask_hn")
        self.assertEqual(story.hn_url, "https://news.ycombinator.com/item?id=42")

    def test_missing_fields_get_defaults(self):
        story = mod.Story.from_api({})
        self.assertEqual(story.title, "")
        self.assertEqual(story.points, 0)
        self.assertEqual(story.story_type, "story")


class FlattenCommentsTests(unittest.TestCase):
    def test_recurses_and_records_depth(self):
        item = {
            "type": "story",
            "children": [
                {"type": "comment", "text": "top", "author": "a", "created_at_i": 1,
                 "children": [
                     {"type": "comment", "text": "nested", "author": "b", "created_at_i": 2, "children": []}
                 ]},
            ],
        }
        flat = mod.flatten_comments(item)
        self.assertEqual([c.text for c in flat], ["top", "nested"])
        self.assertEqual([c.depth for c in flat], [1, 2])

    def test_skips_deleted_comments_without_text(self):
        item = {"type": "story", "children": [{"type": "comment", "text": "", "children": []}]}
        self.assertEqual(mod.flatten_comments(item), [])

    def test_handles_none_safely(self):
        self.assertEqual(mod.flatten_comments(None), [])


class TimeAgoTests(unittest.TestCase):
    def _at(self, seconds_ago):
        return int(mod.time.time()) - seconds_ago

    def test_thresholds(self):
        self.assertEqual(mod.time_ago(self._at(10)), "10s ago")
        self.assertEqual(mod.time_ago(self._at(120)), "2m ago")
        self.assertEqual(mod.time_ago(self._at(7200)), "2h ago")
        self.assertEqual(mod.time_ago(self._at(172800)), "2d ago")
        self.assertEqual(mod.time_ago(self._at(1209600)), "2w ago")

    def test_future_timestamp_is_clamped(self):
        self.assertEqual(mod.time_ago(int(mod.time.time()) + 500), "0s ago")


if __name__ == "__main__":
    unittest.main()
