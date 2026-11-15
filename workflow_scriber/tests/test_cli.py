import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_scriber.__main__ import _latest_flow, build_parser


class LatestFlowTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        patcher = patch("workflow_scriber.__main__.RECORDED_FLOWS_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, mtime):
        path = self.dir / name
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (mtime, mtime))
        return path

    def test_no_recordings(self):
        self.assertIsNone(_latest_flow())

    def test_newest_recording_wins(self):
        self.write("workflow_old.json", 100)
        newest = self.write("workflow_new.json", 200)
        self.assertEqual(_latest_flow(), newest)

    def test_replayed_copies_are_not_recordings(self):
        recording = self.write("workflow_1.json", 100)
        self.write("workflow_1.replayed.json", 200)
        self.assertEqual(_latest_flow(), recording)


class ParserTest(unittest.TestCase):
    def test_flow_argument_is_optional(self):
        self.assertIsNone(build_parser().parse_args(["extract"]).flow)
        self.assertEqual(build_parser().parse_args(["extract", "a.json"]).flow, "a.json")


if __name__ == "__main__":
    unittest.main()