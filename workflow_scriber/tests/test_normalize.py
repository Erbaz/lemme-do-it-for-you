import unittest

from workflow_scriber.normalize import key_text, normalize
from workflow_scriber.tests._fixtures import flow


class KeyTextTest(unittest.TestCase):
    def test_printable_and_shifted_letters(self):
        self.assertEqual(key_text("t"), "t")
        self.assertEqual(key_text("+t"), "T")
        self.assertEqual(key_text("1"), "1")
        self.assertEqual(key_text("{SPACE}"), " ")

    def test_command_keys_are_not_text(self):
        for key in ("{ENTER}", "{TAB}", "^c", "%{F4}", "+1", "+", "{", ""):
            self.assertIsNone(key_text(key), key)


class NormalizeTest(unittest.TestCase):
    def setUp(self):
        self.result = normalize(flow())
        self.by_n = {a["n"]: a for a in self.result["actions"]}

    def test_typing_span_breaks_on_command_key(self):
        spans = self.result["typing_spans"]
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["actions"], [4, 5, 6, 7])
        self.assertEqual(spans[0]["text"], "Test")

    def test_typing_span_ignores_edit_name_changing_with_text(self):
        f = flow()
        for i, name in zip(range(3, 7), ("T", "Te", "Tes", "Test")):
            f["actions"][i]["focus"] = dict(f["actions"][i]["focus"], name=name)
        result = normalize(f)
        self.assertEqual([s["actions"] for s in result["typing_spans"]], [[4, 5, 6, 7]])
        self.assertIsNone(result["actions"][4]["focus_after"])

    def test_typing_span_breaks_on_focus_change(self):
        f = flow()
        f["actions"][5]["focus"] = dict(f["actions"][5]["focus"], class_name="Other")
        spans = normalize(f)["typing_spans"]
        self.assertEqual([s["actions"] for s in spans], [[4, 5], [6], [7]])

    def test_identity_conflict_and_foreground_target(self):
        self.assertFalse(self.by_n[1]["identity_conflict"])
        self.assertTrue(self.by_n[2]["identity_conflict"])
        self.assertEqual(self.by_n[2]["foreground_target"]["name"], "New")

    def test_replayable(self):
        replayable = [n for n, a in self.by_n.items() if a["replayable"]]
        self.assertEqual(replayable, [1, 2, 4, 5, 6, 7, 8, 9])
        self.assertTrue(self.by_n[10]["redacted"])
        self.assertNotIn("text", self.by_n[10])

    def test_focus_after_only_when_changed(self):
        self.assertEqual(self.by_n[3]["focus_after"]["control_type"], "EditControl")
        self.assertIsNone(self.by_n[4]["focus_after"])
        self.assertEqual(self.by_n[9]["focus_after"]["name"], "Password")

    def test_window_change_and_gap(self):
        self.assertTrue(self.by_n[1]["window_changed"])
        self.assertFalse(self.by_n[2]["window_changed"])
        self.assertEqual(self.by_n[2]["gap_s"], 1.0)
        self.assertEqual(self.by_n[1]["gap_s"], 0.0)

    def test_old_recording_without_n_or_focus(self):
        old = {"actions": [{"tool": "press_key", "args": {"key": "a"}},
                           {"tool": "press_key", "args": {"key": "b"}}]}
        result = normalize(old)
        self.assertEqual([a["n"] for a in result["actions"]], [1, 2])
        self.assertEqual(result["typing_spans"][0]["text"], "ab")


if __name__ == "__main__":
    unittest.main()
