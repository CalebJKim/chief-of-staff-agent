import importlib.util
import io
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    "slides_actions", Path(__file__).resolve().parents[1] / "scripts" / "actions.py"
)
actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(actions)


class SlidesActionTests(unittest.TestCase):
    def setUp(self):
        self.api = Mock()
        self.presentations = self.api.presentations.return_value
        self.presentations.batchUpdate.return_value.execute.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 1}}]
        }

    def run_action(self, *arguments):
        args = actions.build_parser().parse_args(["slides", *arguments])
        with patch.object(actions, "service", return_value=self.api), patch.object(actions, "emit") as emit:
            args.func(args)
        return emit.call_args.args[0]

    def test_existing_deck_wide_replacement_remains_supported(self):
        result = self.run_action("replace-text", "any-deck", "--find", "Old", "--replace", "New", "--confirm")
        self.presentations.batchUpdate.assert_called_once_with(
            presentationId="any-deck", body={"requests": [{"replaceAllText": {
                "containsText": {"text": "Old", "matchCase": False}, "replaceText": "New",
            }}]},
        )
        self.assertEqual(1, result["occurrences_changed"])
        self.presentations.get.assert_not_called()

    def test_replacement_can_target_one_arbitrary_slide(self):
        self.run_action("replace-text", "budget-deck", "--slide-id", "page-z9",
                        "--find", "Pending", "--replace", "Supplier’s revised plan\nCosts confirmed",
                        "--match-case", "--confirm")
        request = self.presentations.batchUpdate.call_args.kwargs["body"]["requests"][0]["replaceAllText"]
        self.assertEqual(["page-z9"], request["pageObjectIds"])
        self.assertEqual({"text": "Pending", "matchCase": True}, request["containsText"])
        self.assertEqual("Supplier’s revised plan\nCosts confirmed", request["replaceText"])

    def test_both_mutations_require_confirmation_before_any_api_call(self):
        for arguments in (
            ["replace-text", "deck", "--find", "old", "--replace", "new"],
            ["delete", "deck", "--slide-id", "page"],
        ):
            with self.subTest(arguments=arguments), patch.object(actions, "service") as service:
                args = actions.build_parser().parse_args(["slides", *arguments])
                with self.assertRaisesRegex(RuntimeError, "without --confirm"):
                    args.func(args)
                service.assert_not_called()

    def test_empty_slide_target_does_not_fall_back_to_deck_wide_replacement(self):
        for identifier in ("", "  "):
            with self.subTest(identifier=identifier), patch.object(actions, "service") as service:
                with self.assertRaisesRegex(RuntimeError, "cannot be empty"):
                    args = actions.build_parser().parse_args([
                        "slides", "replace-text", "deck", "--slide-id", identifier,
                        "--find", "old", "--replace", "new", "--confirm",
                    ])
                    args.func(args)
                service.assert_not_called()

    def test_zero_match_is_not_reported_as_a_success(self):
        for response in ({"replies": [{"replaceAllText": {"occurrencesChanged": 0}}]}, {"replies": []}):
            with self.subTest(response=response):
                self.presentations.batchUpdate.return_value.execute.return_value = response
                with self.assertRaisesRegex(RuntimeError, "No matching slide text"):
                    self.run_action("replace-text", "deck", "--slide-id", "target",
                                    "--find", "missing", "--replace", "new", "--confirm")

    def test_delete_validates_slide_membership_and_guards_the_revision(self):
        self.presentations.get.return_value.execute.return_value = {
            "revisionId": "read-revision", "slides": [{"objectId": "keep"}, {"objectId": "remove"}]
        }
        result = self.run_action("delete", "deck", "--slide-id", "remove", "--confirm")
        self.presentations.get.assert_called_once_with(presentationId="deck", fields="revisionId,slides(objectId)")
        self.presentations.batchUpdate.assert_called_once_with(
            presentationId="deck", body={
                "requests": [{"deleteObject": {"objectId": "remove"}}],
                "writeControl": {"requiredRevisionId": "read-revision"},
            },
        )
        self.assertEqual("deleted", result["status"])
        self.assertEqual("remove", result["slide_id"])

    def test_missing_slide_display_number_and_shape_ids_cannot_be_deleted(self):
        self.presentations.get.return_value.execute.return_value = {
            "slides": [{"objectId": "page-a", "pageElements": [{"objectId": "shape-b"}]}]
        }
        for identifier in ("not-in-this-deck", "1", "shape-b", ""):
            with self.subTest(identifier=identifier), self.assertRaisesRegex(RuntimeError, "Slide not found"):
                self.run_action("delete", "deck", "--slide-id", identifier, "--confirm")
        self.presentations.batchUpdate.assert_not_called()

    def test_delete_works_when_revision_is_not_returned(self):
        self.presentations.get.return_value.execute.return_value = {"slides": [{"objectId": "page-a"}]}
        self.run_action("delete", "deck", "--slide-id", "page-a", "--confirm")
        self.assertEqual({"requests": [{"deleteObject": {"objectId": "page-a"}}]},
                         self.presentations.batchUpdate.call_args.kwargs["body"])

    def test_delete_requires_an_explicit_slide_identifier(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            actions.build_parser().parse_args(["slides", "delete", "deck", "--confirm"])

    def test_api_failures_do_not_emit_success(self):
        self.presentations.get.return_value.execute.return_value = {"slides": [{"objectId": "page-a"}]}
        self.presentations.batchUpdate.return_value.execute.side_effect = RuntimeError("API unavailable")
        for arguments in (
            ["replace-text", "deck", "--slide-id", "page-a", "--find", "a", "--replace", "b", "--confirm"],
            ["delete", "deck", "--slide-id", "page-a", "--confirm"],
        ):
            with self.subTest(arguments=arguments), patch.object(actions, "service", return_value=self.api), patch.object(actions, "emit") as emit:
                args = actions.build_parser().parse_args(["slides", *arguments])
                with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                    args.func(args)
                emit.assert_not_called()

    def test_read_merge_read_delete_read_flow_preserves_unrelated_content(self):
        def page(identifier, text):
            return {"objectId": identifier, "pageElements": [{"shape": {"text": {
                "textElements": [{"textRun": {"content": text}}]
            }}}]}

        deck = {"title": "Supplier review", "slides": [
            page("intro", "Intro"), page("detail", "Delivery confirmed"),
            page("summary", "Decision pending"), page("other", "Decision pending"),
        ]}
        self.presentations.get.return_value.execute.side_effect = lambda: deepcopy(deck)

        def update(*, presentationId, body):
            replies = []
            for request in body["requests"]:
                if "deleteObject" in request:
                    deck["slides"] = [p for p in deck["slides"] if p["objectId"] != request["deleteObject"]["objectId"]]
                    replies.append({})
                else:
                    replacement = request["replaceAllText"]
                    count = 0
                    for p in deck["slides"]:
                        if p["objectId"] not in replacement["pageObjectIds"]:
                            continue
                        run = p["pageElements"][0]["shape"]["text"]["textElements"][0]["textRun"]
                        old = replacement["containsText"]["text"]
                        count += run["content"].count(old)
                        run["content"] = run["content"].replace(old, replacement["replaceText"])
                    replies.append({"replaceAllText": {"occurrencesChanged": count}})
            return Mock(execute=Mock(return_value={"replies": replies}))

        self.presentations.batchUpdate.side_effect = update
        before = self.run_action("get", "supplier-deck")
        self.assertEqual("summary", before["slides"][2]["object_id"])
        self.run_action("replace-text", "supplier-deck", "--slide-id", "summary",
                        "--find", "Decision pending", "--replace", "Delivery confirmed; approve the order.", "--confirm")
        verified = self.run_action("get", "supplier-deck")
        self.assertIn("Delivery confirmed", verified["slides"][2]["text"])
        self.run_action("delete", "supplier-deck", "--slide-id", "detail", "--confirm")
        after = self.run_action("get", "supplier-deck")
        self.assertEqual(["intro", "summary", "other"], [p["object_id"] for p in after["slides"]])
        self.assertEqual(2, after["slides"][1]["number"])
        self.assertEqual("Delivery confirmed; approve the order.", after["slides"][1]["text"])
        self.assertEqual("Decision pending", after["slides"][2]["text"])


if __name__ == "__main__":
    unittest.main()
