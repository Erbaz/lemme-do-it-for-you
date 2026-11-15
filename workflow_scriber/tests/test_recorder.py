import unittest

from workflow_scriber.discovery import DiscoveredElement, DiscoveryIndex
from workflow_scriber.fingerprint import Fingerprint
from workflow_scriber.recorder import Recorder

EXPLORER_TITLE = "Docs - File Explorer"
EXPLORER = {"title": EXPLORER_TITLE, "pid": 100, "process": "explorer.exe"}


def _el(name, control_type, rect, pid, title):
    fp = Fingerprint(control_type=control_type, name=name, automation_id="",
                     class_name="", rect=rect, pid=pid, is_password=False)
    return DiscoveredElement(selector=f"name:{name}", rect=rect, fingerprint=fp,
                             control_type=control_type, depth=3,
                             window_title=title, window_pid=pid)


class StaticIndex(DiscoveryIndex):
    def __init__(self, elements):
        super().__init__()
        self._elements = elements
        self.refreshes = 0

    def maybe_refresh(self, min_interval=0.0):
        self.refreshes += 1
        return False

    def refresh(self):
        self.refreshes += 1
        return len(self._elements)


def _elements():
    return [
        _el("Separator", "ButtonControl", (0, 0, 10, 10), 200, "Chrome"),
        _el("Address", "EditControl", (0, 30, 200, 50), 100, EXPLORER_TITLE),
        _el("New", "ButtonControl", (0, 0, 50, 20), 100, EXPLORER_TITLE),
        _el("New", "ButtonControl", (60, 0, 90, 20), 100, EXPLORER_TITLE),
    ]


class DiscoveryIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = StaticIndex(_elements())

    def test_find_at_pid_filter(self):
        self.assertEqual(self.index.find_at(5, 5).fingerprint.name, "Separator")
        self.assertEqual(self.index.find_at(5, 5, pid=100).fingerprint.name, "New")
        self.assertIsNone(self.index.find_at(5, 5, pid=999))

    def test_visible_sorted_and_deduplicated(self):
        visible = self.index.visible(EXPLORER_TITLE)
        self.assertEqual([v["name"] for v in visible], ["New", "Address"])
        self.assertEqual(visible[0]["selector"], "name:New")
        self.assertEqual(len(self.index.visible(EXPLORER_TITLE, limit=1)), 1)
        self.assertTrue(self.index.has_window("Chrome"))
        self.assertFalse(self.index.has_window("Other"))

    def test_visible_skips_icon_font_glyphs(self):
        glyphs = ["\ue72b", "\ue72a", " \ue72c ", "\u0000"]
        self.index._elements += [
            _el(name, "TextControl", (0, 60 + i, 10, 70 + i), 100, EXPLORER_TITLE)
            for i, name in enumerate(glyphs)
        ]
        names = [v["name"] for v in self.index.visible(EXPLORER_TITLE)]
        self.assertEqual(names, ["New", "Address"])


class RecorderContextTest(unittest.TestCase):
    def setUp(self):
        self.index = StaticIndex(_elements())
        self.focus = None
        self.recorder = Recorder(self.index, focus=lambda: self.focus)
        self.t = 0.0

    def click(self, x, y, window):
        self.t += 10.0
        self.recorder.on_mouse_down(x, y, t=self.t, ts="ts")
        return self.recorder.on_mouse_up(x, y, t=self.t, ts="ts", window=window)

    def test_foreground_alternative_on_process_conflict(self):
        record = self.click(5, 5, EXPLORER)
        self.assertEqual(record.args["selector"], "name:Separator")
        self.assertEqual(record.foreground["element"]["name"], "New")
        self.assertEqual(record.foreground["selectors"][0], "name:New")

    def test_no_alternative_without_conflict(self):
        record = self.click(100, 40, EXPLORER)
        self.assertEqual(record.args["selector"], "name:Address")
        self.assertIsNone(record.foreground)

    def test_visible_once_per_window_change(self):
        first = self.click(100, 40, EXPLORER)
        second = self.click(100, 40, EXPLORER)
        self.assertEqual([v["name"] for v in first.visible], ["New", "Address"])
        self.assertIsNone(second.visible)
        self.assertEqual(self.index.refreshes, 0)

    def test_unknown_window_triggers_refresh(self):
        record = self.click(100, 40, {"title": "Other", "pid": 100})
        self.assertIsNone(record.visible)
        self.assertEqual(self.index.refreshes, 1)

    def test_untitled_window_is_skipped(self):
        record = self.click(100, 40, {"title": "", "pid": 100})
        self.assertIsNone(record.visible)
        self.assertEqual(self.index.refreshes, 0)

    def test_focus_recorded_on_clicks_and_keys(self):
        self.focus = {"control_type": "EditControl", "name": "Address", "is_password": False}
        record = self.click(100, 40, EXPLORER)
        key = self.recorder.on_key("a", frozenset(), ts="ts")
        self.assertEqual(record.focus["name"], "Address")
        self.assertEqual(key.focus["name"], "Address")
        self.assertEqual(key.args["key"], "a")
        self.assertFalse(key.redacted)

    def test_password_text_is_redacted(self):
        self.focus = {"control_type": "EditControl", "name": "Password", "is_password": True}
        lower = self.recorder.on_key("a", frozenset(), ts="ts")
        upper = self.recorder.on_key("a", frozenset({"shift"}), ts="ts")
        enter = self.recorder.on_key("enter", frozenset(), ts="ts")
        for record in (lower, upper):
            self.assertTrue(record.redacted)
            self.assertEqual(record.args["key"], "")
            self.assertIn("redacted", record.note)
        self.assertFalse(enter.redacted)
        self.assertEqual(enter.args["key"], "{ENTER}")

    def test_failing_focus_provider(self):
        def boom():
            raise RuntimeError("uia")

        recorder = Recorder(self.index, focus=boom)
        self.assertIsNone(recorder.on_key("a", frozenset(), ts="ts").focus)

    def test_no_focus_provider(self):
        recorder = Recorder(self.index)
        self.assertIsNone(recorder.on_key("a", frozenset(), ts="ts").focus)

    def test_scroll_rebuilds_index_before_next_click(self):
        self.recorder.on_scroll(100, 40, -1, ts="ts")
        self.assertEqual(self.index.refreshes, 0)
        self.click(100, 40, EXPLORER)
        self.assertEqual(self.index.refreshes, 1)
        self.click(100, 40, EXPLORER)
        self.assertEqual(self.index.refreshes, 1)

    def test_repeated_scrolls_do_not_rebuild(self):
        for _ in range(3):
            self.recorder.on_scroll(100, 40, -1, ts="ts")
        self.assertEqual(self.index.refreshes, 0)


if __name__ == "__main__":
    unittest.main()
