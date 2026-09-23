import importlib.util
import sys
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location("slide_reset_seed", Path(__file__).with_name("seed_workspace.py"))
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def deck(count=10, prefix="page"):
    return {"slides": [{"objectId": f"{prefix}-{i}", "pageElements": [
        {"objectId": f"{prefix}-{i}-{kind}", "shape": {"text": {
            "textElements": [{"textRun": {"content": kind}}]
        }}} for kind in ("title", "body")
    ]} for i in range(count)]}


class SlideResetTests(unittest.TestCase):
    def setUp(self):
        self.slides = Mock()
        self.presentations = self.slides.presentations.return_value
        self.drive = Mock()

    def test_intact_deck_keeps_existing_text_only_reset(self):
        self.presentations.get.return_value.execute.return_value = deck()
        seed.reset_deck_baseline(self.slides, "same-deck", drive=self.drive)
        self.presentations.get.assert_called_once_with(presentationId="same-deck")
        self.drive.files.assert_not_called()
        self.assertEqual(32, len(self.presentations.batchUpdate.call_args.kwargs["body"]["requests"]))

    def test_new_design_refreshes_even_when_slide_count_matches(self):
        self.presentations.get.return_value.execute.side_effect = [deck(), deck(prefix="redesigned")]
        with patch("googleapiclient.http.MediaFileUpload"):
            seed.reset_deck_baseline(self.slides, "same-deck", drive=self.drive, restore_template=True)
        self.assertEqual("same-deck", self.drive.files().update.call_args.kwargs["fileId"])
        self.drive.files().create.assert_not_called()
        self.drive.files().delete.assert_not_called()
        for request in self.presentations.batchUpdate.call_args.kwargs["body"]["requests"]:
            value = request.get("insertText", request.get("deleteText"))
            self.assertTrue(value["objectId"].startswith("redesigned-"))

    def test_new_deck_records_template_fingerprint(self):
        result = {"id": "new-deck", "url": "https://example.test/new-deck"}
        with patch.object(seed, "upload_template", return_value=result.copy()):
            created = seed.create_slides(self.drive, "folder")
        self.assertEqual(result["id"], created["id"])
        self.assertEqual(result["url"], created["url"])
        self.assertEqual(seed.deck_template_hash(), created["template_sha256"])

    def test_added_or_deleted_slides_restore_template_in_same_file(self):
        for count in (0, 7, 9, 11):
            with self.subTest(count=count), patch("googleapiclient.http.MediaFileUpload") as media:
                self.slides.reset_mock()
                self.drive.reset_mock()
                self.presentations.get.return_value.execute.side_effect = [deck(count), deck(prefix="restored")]
                seed.reset_deck_baseline(self.slides, "keep-this-id", drive=self.drive)
                self.drive.files().update.assert_called_once_with(
                    fileId="keep-this-id", body={"mimeType": "application/vnd.google-apps.presentation"},
                    media_body=media.return_value, fields="id",
                )
                media.assert_called_once_with(
                    str(seed.ROOT / "demo" / "templates" / "rtx-spark-exec-review.pptx"),
                    mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation", resumable=False,
                )
                self.drive.files().create.assert_not_called()
                self.drive.files().delete.assert_not_called()
                write = self.presentations.batchUpdate.call_args.kwargs
                self.assertEqual("keep-this-id", write["presentationId"])
                for request in write["body"]["requests"]:
                    value = request.get("insertText", request.get("deleteText"))
                    self.assertTrue(value["objectId"].startswith("restored-"))

    def test_expected_count_comes_from_template_not_ten(self):
        template_xml = '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldIdLst>'
        template_xml += ''.join(f'<p:sldId id="{i}"/>' for i in range(12))
        template_xml += '</p:sldIdLst></p:presentation>'
        self.presentations.get.return_value.execute.side_effect = [deck(10), deck(12)]
        with patch.object(seed, "ZipFile") as archive, patch("googleapiclient.http.MediaFileUpload"):
            archive.return_value.__enter__.return_value.read.return_value = template_xml.encode()
            seed.reset_deck_baseline(self.slides, "same-deck", drive=self.drive)
        self.drive.files().update.assert_called_once()

    def test_structure_mismatch_without_drive_stops_before_text_write(self):
        self.presentations.get.return_value.execute.return_value = deck(9)
        with self.assertRaisesRegex(RuntimeError, "reset needs Drive access"):
            seed.reset_deck_baseline(self.slides, "deck")
        self.presentations.batchUpdate.assert_not_called()

    def test_failed_import_does_not_write_text_using_shifted_slide_numbers(self):
        self.presentations.get.return_value.execute.return_value = deck(9)
        self.drive.files().update.return_value.execute.side_effect = RuntimeError("Drive unavailable")
        with patch("googleapiclient.http.MediaFileUpload"), self.assertRaisesRegex(RuntimeError, "Drive unavailable"):
            seed.reset_deck_baseline(self.slides, "deck", drive=self.drive)
        self.presentations.batchUpdate.assert_not_called()

    def test_incomplete_import_stops_before_baseline_text_write(self):
        self.presentations.get.return_value.execute.side_effect = [deck(9), deck(9)]
        with patch("googleapiclient.http.MediaFileUpload"), self.assertRaisesRegex(RuntimeError, "not fully restored"):
            seed.reset_deck_baseline(self.slides, "deck", drive=self.drive)
        self.presentations.batchUpdate.assert_not_called()

    def test_deck_restore_failure_precedes_other_reset_writes(self):
        state = {"slides": {"id": "deck"}}
        svc = {"slides": self.slides, "drive": self.drive}
        with patch.object(seed, "services", return_value=svc), \
             patch.object(seed, "reset_deck_baseline", side_effect=RuntimeError("restore failed")), \
             patch.object(seed, "clear_seeded_tasks") as tasks, patch.object(seed, "remove_dynamic_items") as remove:
            with self.assertRaisesRegex(RuntimeError, "restore failed"):
                seed.reset_in_place(state, date(2026, 9, 14))
        tasks.assert_not_called()
        remove.assert_not_called()
        self.assertNotIn("template_sha256", state["slides"])

    def test_reset_preserves_file_state_and_all_references(self):
        state = {
            "slides": {"id": "same-deck", "url": "https://example.test/same-deck"},
            "sheet": {"id": "sheet", "url": "https://example.test/sheet"},
            "doc": {"id": "doc", "url": "https://example.test/doc"},
            "folder": {"id": "folder"}, "week_of": "2026-09-14",
        }
        original_slides = deepcopy(state["slides"])
        svc = {name: Mock() for name in ("tasks", "slides", "drive", "gmail", "calendar", "sheets")}
        with patch.object(seed, "services", return_value=svc), \
             patch.object(seed, "reset_deck_baseline") as restore, \
             patch.object(seed, "clear_seeded_tasks"), patch.object(seed, "remove_dynamic_items"), \
             patch.object(seed, "create_emails", return_value=([{"id": "new-mail"}], {})) as emails, \
             patch.object(seed, "create_tasks") as tasks, patch.object(seed, "reset_sheet_baseline") as sheet, \
             patch.object(seed, "reset_original_sheet") as original, \
             patch.object(seed, "create_calendar", return_value=[]) as calendar, patch.object(seed, "state_path") as path:
            result = seed.reset_in_place(state, date(2026, 9, 14))
        restore.assert_called_once_with(svc["slides"], "same-deck", drive=svc["drive"], restore_template=True)
        self.assertEqual({**original_slides, "template_sha256": seed.deck_template_hash()}, result["slides"])
        self.assertEqual(original_slides["url"], emails.call_args.args[1])
        self.assertEqual(original_slides["url"], calendar.call_args.args[2])
        self.assertEqual(result["slides"], tasks.call_args.args[1]["slides"])
        self.assertEqual(result["slides"], sheet.call_args.args[1]["slides"])
        path().write_text.assert_called_once()
        original.assert_called_once_with(svc["drive"], svc["sheets"], state, {}, sheet.call_args.args[3])

    def test_only_missing_or_changed_template_fingerprint_triggers_design_refresh(self):
        current = seed.deck_template_hash()
        for previous in (None, "older-template", current):
            with self.subTest(previous=previous):
                state = {"slides": {"id": "same-deck", "url": "deck-url"},
                         "sheet": {"id": "sheet", "url": "sheet-url"},
                         "doc": {"id": "doc", "url": "doc-url"}}
                if previous is not None:
                    state["slides"]["template_sha256"] = previous
                svc = {name: Mock() for name in ("tasks", "slides", "drive", "gmail", "calendar", "sheets")}
                with patch.object(seed, "services", return_value=svc), \
                     patch.object(seed, "reset_deck_baseline") as restore, \
                     patch.object(seed, "clear_seeded_tasks"), patch.object(seed, "remove_dynamic_items"), \
                     patch.object(seed, "create_emails", return_value=([], {})), \
                     patch.object(seed, "create_tasks"), patch.object(seed, "reset_sheet_baseline"), \
                     patch.object(seed, "reset_original_sheet"), \
                     patch.object(seed, "create_calendar", return_value=[]), patch.object(seed, "state_path"):
                    seed.reset_in_place(state, date(2026, 9, 14))
                self.assertEqual(previous != current, restore.call_args.kwargs["restore_template"])
                self.assertEqual(current, state["slides"]["template_sha256"])

    def test_template_text_order_matches_the_reset_contract(self):
        self.presentations.get.return_value.execute.return_value = deck()
        seed.reset_deck_baseline(self.slides, "same-deck", drive=self.drive)
        writes = {request["insertText"]["objectId"]: request["insertText"]["text"]
                  for request in self.presentations.batchUpdate.call_args.kwargs["body"]["requests"]
                  if "insertText" in request}
        ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
              "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        with seed.ZipFile(seed.ROOT / "demo" / "templates" / "rtx-spark-exec-review.pptx") as archive:
            for number in range(3, 11):
                slide = seed.ElementTree.fromstring(archive.read(f"ppt/slides/slide{number}.xml"))
                texts = ["\n".join("".join(p.itertext()) for p in shape.findall("p:txBody/a:p", ns))
                         for shape in slide.findall("p:cSld/p:spTree/p:sp", ns)]
                texts = [text for text in texts if text.strip()]
                self.assertEqual(writes[f"page-{number - 1}-title"], texts[0])
                self.assertEqual(writes[f"page-{number - 1}-body"], texts[1])

    def test_merge_source_has_customer_example_and_destination_stays_pending(self):
        self.presentations.get.return_value.execute.return_value = deck()
        seed.reset_deck_baseline(self.slides, "deck", drive=self.drive)
        writes = {r["insertText"]["objectId"]: r["insertText"]["text"]
                  for r in self.presentations.batchUpdate.call_args.kwargs["body"]["requests"]
                  if "insertText" in r}
        source = writes["page-5-body"]
        for phrase in ("local product catalog", "customer follow-up", "reviews the draft", "stay on the device"):
            self.assertIn(phrase, source)
        self.assertNotIn("appendix", source)
        self.assertNotIn("Cut this", source)
        destination = writes["page-6-body"]
        self.assertIn("CUSTOMER EXAMPLE", destination)
        self.assertIn("still to be summarized", destination)
        self.assertIn("No selection is approved yet", destination)


if __name__ == "__main__":
    unittest.main()
