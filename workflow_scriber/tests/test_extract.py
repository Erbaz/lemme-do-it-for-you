import json
import tempfile
import unittest
from pathlib import Path

from workflow_scriber.extract import extract, parse_response, recording_id, write
from workflow_scriber.prompt import SYSTEM_PROMPT
from workflow_scriber.tests._fixtures import flow, valid_response


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, system, user):
        self.calls.append((system, user))
        return self.replies.pop(0)


class ParseResponseTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_response('{"a": 1}'), ({"a": 1}, None))

    def test_code_fence(self):
        self.assertEqual(parse_response('```json\n{"a": 1}\n```'), ({"a": 1}, None))

    def test_surrounding_prose(self):
        self.assertEqual(parse_response('Here it is:\n{"a": 1}\nDone.'), ({"a": 1}, None))

    def test_invalid(self):
        value, error = parse_response("{not json}")
        self.assertIsNone(value)
        self.assertIn("not valid JSON", error)
        self.assertEqual(parse_response("nothing"), (None, "the answer contains no JSON object"))


class RecordingIdTest(unittest.TestCase):
    def test_strips_replayed_suffix(self):
        self.assertEqual(recording_id(Path("a/workflow_1.json")), "workflow_1")
        self.assertEqual(recording_id(Path("workflow_1.replayed.json")), "workflow_1")


class ExtractTest(unittest.TestCase):
    def run_extract(self, *replies):
        llm = FakeLLM(*replies)
        result = extract(flow(), "rec", "rec.json", llm, model="fake")
        return result, llm

    def test_valid_first_answer(self):
        result, llm = self.run_extract(json.dumps(valid_response()))
        self.assertEqual(len(llm.calls), 1)
        system, user = llm.calls[0]
        self.assertEqual(system, SYSTEM_PROMPT)
        self.assertIn("RECORDING: id=s_test", user)
        bundle = result.bundle
        self.assertEqual(bundle["provenance"]["attempts"], 1)
        self.assertEqual(bundle["provenance"]["model"], "fake")
        self.assertEqual(set(result.workflows), {"explorer_create_folder", "open_file_explorer"})
        self.assertEqual(len(bundle["annotations"]), 10)

    def test_repair_after_invalid_answer(self):
        bad = valid_response()
        bad["scribbles"][0]["actions"].append(3)
        result, llm = self.run_extract(json.dumps(bad), json.dumps(valid_response()))
        self.assertEqual(len(llm.calls), 2)
        repair = llm.calls[1][1]
        self.assertIn("IT FAILED VALIDATION", repair)
        self.assertIn("not replayable", repair)
        self.assertEqual(result.bundle["provenance"]["attempts"], 2)
        self.assertEqual(len(result.responses), 2)

    def test_fails_after_two_invalid_answers(self):
        llm = FakeLLM("not json", "{}")
        with self.assertRaises(ValueError) as caught:
            extract(flow(), "rec", "rec.json", llm)
        self.assertEqual(len(llm.calls), 2)
        message = str(caught.exception)
        self.assertIn("no valid answer in 2 attempts", message)
        self.assertIn("the answer contains no JSON object", message)


class WriteTest(unittest.TestCase):
    def test_writes_library_and_replaces_old_workflows(self):
        result = extract(flow(), "rec", "rec.json", FakeLLM(json.dumps(valid_response())))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "rec"
            write(result, out)
            for name in ("context.json", "scribbles.json", "llm_responses.json"):
                self.assertTrue((out / name).is_file(), name)
            workflow = json.loads(
                (out / "workflows" / "explorer_create_folder.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(workflow["actions"]), 7)

            stale = out / "workflows" / "stale.json"
            stale.write_text("{}", encoding="utf-8")
            write(result, out)
            self.assertFalse(stale.exists())
            self.assertTrue((out / "workflows" / "open_file_explorer.json").is_file())


if __name__ == "__main__":
    unittest.main()
