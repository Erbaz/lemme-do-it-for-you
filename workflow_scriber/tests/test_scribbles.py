import unittest

from workflow_scriber.normalize import normalize
from workflow_scriber.scribbles import (
    context_card, describe_scribbles, validate, workflow_flow,
)
from workflow_scriber.tests._fixtures import flow, valid_response


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.normalized = normalize(flow())
        self.response = valid_response()
        self.first = self.response["scribbles"][0]

    def errors(self):
        return validate(self.response, self.normalized)

    def assertError(self, fragment):
        errors = self.errors()
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_valid_response(self):
        self.assertEqual(self.errors(), [])

    def test_not_an_object(self):
        self.assertEqual(validate([], self.normalized), ["the answer must be a JSON object"])

    def test_missing_recording_summary(self):
        self.response["recording"]["summary"] = ""
        self.assertError("recording.title and recording.summary")

    def test_missing_annotation(self):
        self.response["annotations"].pop()
        self.assertError("actions not annotated: [10]")

    def test_duplicate_annotation(self):
        self.response["annotations"].append(dict(self.response["annotations"][0]))
        self.assertError("action 1 is annotated more than once")

    def test_annotation_unknown_action(self):
        self.response["annotations"][0]["action"] = 99
        self.assertError("99 is not a recorded action")

    def test_no_scribbles(self):
        self.response["scribbles"] = []
        self.assertError("scribbles must be a non-empty list")

    def test_bad_and_duplicate_ids(self):
        self.response["scribbles"][1]["id"] = "Bad Id"
        self.assertError("id must be snake_case")
        self.response["scribbles"][1]["id"] = "explorer_create_folder"
        self.assertError("is duplicated")

    def test_unknown_action(self):
        self.first["actions"].append(42)
        self.assertError("unknown action ids [42]")

    def test_out_of_order_actions(self):
        self.first["actions"] = [2, 1, 4, 5, 6, 7, 8]
        self.assertError("recording order")

    def test_unreplayable_action(self):
        self.first["actions"] = [1, 2, 3, 4, 5, 6, 7, 8]
        self.first["steps"][1]["actions"] = [2, 3]
        self.assertError("[3] are not replayable")

    def test_duplicate_action_set(self):
        self.response["scribbles"][1]["actions"] = list(self.first["actions"])
        self.response["scribbles"][1]["steps"] = [
            {"intent": "all", "actions": list(self.first["actions"])},
        ]
        self.assertError("has the same actions as scribble 'explorer_create_folder'")

    def test_steps_must_cover_actions_in_order(self):
        self.first["steps"].pop()
        self.assertError("steps must split")
        self.first["steps"] = [
            {"intent": "x", "actions": [2]},
            {"intent": "y", "actions": [1, 4, 5, 6, 7, 8]},
        ]
        self.assertError("steps must split")

    def test_step_without_intent(self):
        self.first["steps"][0]["intent"] = ""
        self.assertError("needs a non-empty intent")

    def test_long_description(self):
        self.first["description"] = "x" * 601
        self.assertError("at most 600 chars")


class ContextCardTest(unittest.TestCase):
    def test_drops_empty_fields_and_marks_unreplayable(self):
        card = context_card(normalize(flow()))
        by_n = {a["n"]: a for a in card["actions"]}
        self.assertEqual(card["recording"]["id"], "s_test")
        self.assertNotIn("replayable", by_n[1])
        self.assertIs(by_n[3]["replayable"], False)
        self.assertNotIn("identity_conflict", by_n[1])
        self.assertTrue(by_n[2]["identity_conflict"])
        self.assertEqual(by_n[1]["visible"], ["New [Button]"])
        self.assertEqual(card["typing_spans"][0]["text"], "Test")


class MaterializeTest(unittest.TestCase):
    def setUp(self):
        self.flow = flow()
        self.scribbles = describe_scribbles(valid_response())

    def test_describe_points_at_workflow_file(self):
        first, second = self.scribbles
        self.assertEqual(first["workflow"], "workflows/explorer_create_folder.json")
        self.assertEqual(second["workflow"], "workflows/open_file_explorer.json")

    def test_no_extra_fields(self):
        self.assertEqual(set(self.scribbles[0]), {
            "id", "title", "description", "actions", "steps", "workflow",
        })
        self.assertEqual(set(self.scribbles[0]["steps"][0]), {"intent", "actions"})

    def test_workflow_is_renumbered_subset(self):
        wf = workflow_flow(self.scribbles[0], self.flow, "rec", "rec.json")
        self.assertEqual([a["n"] for a in wf["actions"]], list(range(1, 8)))
        self.assertEqual([a["source_n"] for a in wf["actions"]], [1, 2, 4, 5, 6, 7, 8])
        self.assertEqual(wf["session"]["id"], "rec/explorer_create_folder")
        self.assertEqual(wf["session"]["source_flow"], "rec.json")
        self.assertNotIn("visible", wf["actions"][0])
        self.assertNotIn("pruned", wf["session"])

    def test_foreground_selectors_go_first(self):
        wf = workflow_flow(self.scribbles[0], self.flow, "rec", "rec.json")
        args = wf["actions"][1]["args"]
        self.assertEqual(args["selectors"], ["name:New", "class:Button", "name:Separator"])
        self.assertEqual(args["selector"], "name:New")

    def test_source_flow_untouched(self):
        workflow_flow(self.scribbles[0], self.flow, "rec", "rec.json")
        self.assertEqual(self.flow["actions"][1]["args"]["selector"], "name:Separator")
        self.assertIn("visible", self.flow["actions"][0])

    def test_pruned_source_stays_pruned(self):
        self.flow["session"]["pruned"] = True
        wf = workflow_flow(self.scribbles[1], self.flow, "rec", "rec.replayed.json")
        self.assertTrue(wf["session"]["pruned"])


if __name__ == "__main__":
    unittest.main()
