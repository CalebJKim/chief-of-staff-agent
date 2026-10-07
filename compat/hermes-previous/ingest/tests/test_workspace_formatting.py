import argparse
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(ROOT))
import workspace_formatting as f


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def paragraph(text="Alpha beta\n", start=1):
    end = start + f.utf16(text)
    return {"startIndex": start, "endIndex": end, "paragraph": {
        "elements": [{"startIndex": start, "endIndex": end, "textRun": {"content": text, "textStyle": {"fontSize": {"magnitude": 11, "unit": "PT"}}}}],
        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}}}


def document(text="Alpha beta\n"):
    return {"title": "Test doc", "revisionId": "r1", "tabs": [{"tabProperties": {"tabId": "tab1"},
            "documentTab": {"body": {"content": [paragraph(text)]}}}]}


def deck(text="Alpha beta\n"):
    return {"title": "Test deck", "revisionId": "r1", "slides": [{"objectId": "slide1", "pageElements": [{
        "objectId": "shape1", "shape": {"text": {"textElements": [
            {"startIndex": 0, "endIndex": f.utf16(text), "paragraphMarker": {"style": {}}},
            {"startIndex": 0, "endIndex": f.utf16(text), "textRun": {"content": text, "style": {"fontSize": {"magnitude": 18, "unit": "PT"}}}}
        ]}}}]}]}


class SelectionTests(unittest.TestCase):
    def test_unicode_ranges_are_utf16(self):
        matches = f.locate(f.doc_records(document("😀 Alpha\n")), "Alpha")
        self.assertEqual((4, 9), (matches[0]["start"], matches[0]["end"]))

    def test_ambiguity_requires_explicit_opt_in(self):
        records = f.doc_records(document("Alpha Alpha\n"))
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            f.locate(records, "Alpha")
        self.assertEqual(2, len(f.locate(records, "Alpha", True)))

    def test_missing_and_empty_matches_fail(self):
        for text in ("", " ", "missing", "alpha"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                f.locate(f.doc_records(document()), text)

    def test_matching_can_cross_contiguous_style_runs(self):
        records = f.doc_records(document())
        records[0]["runs"] = [{"start": 1, "end": 4, "text": "Alp", "style": {}},
                              {"start": 4, "end": 6, "text": "ha", "style": {"bold": True}}]
        self.assertEqual(6, f.locate(records, "Alpha")[0]["end"])
        records[0]["runs"][1]["start"] = 5
        with self.assertRaises(ValueError):
            f.locate(records, "Alpha")

    def test_doc_table_and_child_tabs_are_read(self):
        data = document()
        data["tabs"][0]["childTabs"] = [{"tabProperties": {"tabId": "child"}, "documentTab": {"body": {"content": [{
            "table": {"tableRows": [{"tableCells": [{"content": [paragraph("Cell\n", 7)]}]}]}}]}}}]
        records = f.doc_records(data)
        self.assertEqual(["tab1", "child"], [r["tab_id"] for r in records])
        self.assertEqual(7, f.locate(records, "Cell")[0]["start"])

    def test_doc_named_style_inheritance_is_used_for_verification(self):
        data = document()
        tab = data["tabs"][0]["documentTab"]
        tab["namedStyles"] = {"styles": [{"namedStyleType": "NORMAL_TEXT", "textStyle": {
            "bold": True, "weightedFontFamily": {"fontFamily": "Arial", "weight": 400}}}]}
        records = f.doc_records(data)
        f.verify("docs", f.locate(records, "Alpha"), records, {"bold": True, "font_family": "Arial"})
        self.assertNotIn("bold", records[0]["runs"][0]["explicit_style"])

    def test_slide_table_cells_and_groups_keep_identity(self):
        data = deck()
        items = data["slides"][0]["pageElements"]
        items.append({"objectId": "group", "elementGroup": {"children": [{"objectId": "table1", "table": {
            "tableRows": [{"tableCells": [{"text": items[0]["shape"]["text"]}]}]}}]}})
        records = f.slide_records(data)
        self.assertEqual(2, len(records))
        self.assertEqual({"rowIndex": 0, "columnIndex": 0}, records[1]["cell"])


class FormattingTests(unittest.TestCase):
    def test_invalid_styles_fail(self):
        for style in ({}, [], {"font_size": -1}, {"font_size": True}, {"bold": "true"},
                      {"heading": 7}, {"heading": True}, {"color": "blue"}, {"font_family": ""},
                      {"link": "javascript:bad"}, {"alignment": "LEFT"}, {"list": "anything"},
                      {"deleteObject": {}}, {"line_spacing": float("nan")}):
            with self.subTest(style=style), self.assertRaises(ValueError):
                f.style_requests(style, "docs")

    def test_field_masks_only_change_requested_properties(self):
        matches = f.locate(f.doc_records(document()), "Alpha")
        req = f.make_requests("docs", matches, {"bold": True})[0]["updateTextStyle"]
        self.assertEqual({"bold": True}, req["textStyle"])
        self.assertEqual("bold", req["fields"])
        self.assertEqual({"tabId": "tab1", "startIndex": 1, "endIndex": 6}, req["range"])

    def test_slide_specific_shape_and_cell_target(self):
        record = f.slide_records(deck())[0]
        record["cell"] = {"rowIndex": 2, "columnIndex": 1}
        req = f.make_requests("slides", f.locate([record], "Alpha"), {"bold": True})[0]["updateTextStyle"]
        self.assertEqual("shape1", req["objectId"])
        self.assertEqual(record["cell"], req["cellLocation"])
        self.assertEqual(0, req["textRange"]["startIndex"])

    def test_list_heading_and_font_apply_in_order(self):
        requests = f.make_requests("docs", f.locate(f.doc_records(document()), "Alpha"),
                                   {"list": "bulleted", "heading": 2, "font_family": "Arial", "font_size": 13, "color": "#204080"})
        self.assertEqual(["createParagraphBullets", "updateParagraphStyle", "updateTextStyle"], [next(iter(r)) for r in requests])
        self.assertEqual("HEADING_2", requests[1]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"])
        self.assertEqual({"fontFamily": "Arial"}, requests[2]["updateTextStyle"]["textStyle"]["weightedFontFamily"])

    def test_bullets_reject_leading_tabs_to_preserve_indices(self):
        with self.assertRaisesRegex(ValueError, "tab-indented"):
            f.make_requests("docs", f.locate(f.doc_records(document("\tAlpha\n")), "Alpha"), {"list": "bulleted"})

    def test_numbered_list_presets_match_google_discovery_schemas(self):
        from googleapiclient.discovery import build
        for kind, records in (("docs", f.doc_records(document())), ("slides", f.slide_records(deck()))):
            api = build(kind, "v1", developerKey="offline-schema-only", cache_discovery=False)
            allowed = api._rootDesc["schemas"]["CreateParagraphBulletsRequest"]["properties"]["bulletPreset"]["enum"]
            request = f.make_requests(kind, f.locate(records, "Alpha"), {"list": "numbered"})[0]
            self.assertIn(request["createParagraphBullets"]["bulletPreset"], allowed)

    def test_list_verification_distinguishes_numbers_and_bullets(self):
        records = f.doc_records(document())
        matches = f.locate(records, "Alpha")
        records[0]["bullet"] = {"listId": "some-list"}
        records[0]["list_kind"] = "bulleted"
        with self.assertRaisesRegex(RuntimeError, "list verification failed"):
            f.verify("docs", matches, records, {"list": "numbered"})

    def test_remove_link_keeps_mask_but_omits_value(self):
        records = f.slide_records(deck())
        records[0]["runs"][0]["style"]["foregroundColor"] = {"opaqueColor": {"rgbColor": {"red": 1}}}
        requests = f.make_requests("slides", f.locate(records, "Alpha"), {"link": None})
        req = requests[0]["updateTextStyle"]
        self.assertEqual("link", req["fields"])
        self.assertEqual({}, req["style"])
        self.assertEqual("foregroundColor,underline", requests[1]["updateTextStyle"]["fields"])
        self.assertEqual({"opaqueColor": {"rgbColor": {"red": 1}}}, requests[1]["updateTextStyle"]["style"]["foregroundColor"])

    def test_link_change_preserves_mixed_colors_per_run(self):
        records = f.doc_records(document())
        records[0]["runs"] = [{"start": 1, "end": 4, "text": "Alp", "style": {"foregroundColor": {"color": {"rgbColor": {"red": 1}}}}},
                              {"start": 4, "end": 6, "text": "ha", "style": {"foregroundColor": {"color": {"rgbColor": {"blue": 1}}}}}]
        requests = f.make_requests("docs", f.locate(records, "Alpha"), {"link": "https://example.com"})
        self.assertEqual(3, len(requests))
        self.assertEqual(4, requests[1]["updateTextStyle"]["range"]["endIndex"])
        self.assertEqual(4, requests[2]["updateTextStyle"]["range"]["startIndex"])

    def test_verify_rejects_missing_change_or_content_mutation(self):
        original = f.doc_records(document())
        matches = f.locate(original, "Alpha")
        with self.assertRaisesRegex(RuntimeError, "verification failed"):
            f.verify("docs", matches, original, {"bold": True})
        after = deepcopy(original)
        after[0]["runs"][0]["style"]["bold"] = True
        f.verify("docs", matches, after, {"bold": True})
        after[0]["runs"][0]["text"] = "Wrong text"
        with self.assertRaisesRegex(RuntimeError, "text/target changed"):
            f.verify("docs", matches, after, {"bold": True})

    def test_style_comparison_handles_google_omitted_zero_channels(self):
        self.assertTrue(f._same({"rgbColor": {"red": 1}}, {"rgbColor": {"red": 1, "green": 0, "blue": 0}}))


class CommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidates = [load(ROOT / "actions.py", "formatting_actions")]

    def test_existing_and_new_commands_parse(self):
        for module in self.candidates:
            for argv in (["gmail", "drafts"], ["docs", "get", "doc"], ["slides", "get", "deck"],
                         ["docs", "inspect", "doc"], ["slides", "format", "deck", "--slide-id", "slide1", "--find", "Alpha", "--style", '{"bold":true}', "--confirm"]):
                with self.subTest(module=module.__name__, argv=argv):
                    module.build_parser().parse_args(argv)

    def test_no_confirmation_or_bad_style_makes_no_api_calls(self):
        for argv in (["docs", "format", "doc", "--find", "Alpha", "--style", '{"bold":true}'],
                     ["docs", "format", "doc", "--find", "Alpha", "--style", '{"unknown":true}', "--confirm"]):
            module = self.candidates[0]
            with patch.object(module, "service") as service:
                args = module.build_parser().parse_args(argv)
                with self.assertRaises(ValueError):
                    args.func(args)
                service.assert_not_called()

    def test_style_json_can_arrive_over_stdin_without_shell_escaping(self):
        module = self.candidates[0]
        with patch.object(module, "service") as service, patch("sys.stdin", io.StringIO('{"unsupported":true}')):
            args = module.build_parser().parse_args(["docs", "format", "doc", "--find", "Alpha", "--style-file", "-", "--confirm"])
            with self.assertRaisesRegex(ValueError, "Unsupported style properties"):
                args.func(args)
            service.assert_not_called()

    def test_missing_pdf_dependency_fails_before_any_network_or_write(self):
        import builtins
        original_import = builtins.__import__
        def import_without_renderer(name, *args, **kwargs):
            if name == "pymupdf":
                raise ImportError("not installed")
            return original_import(name, *args, **kwargs)
        service = Mock()
        args = argparse.Namespace(kind="docs")
        with patch("builtins.__import__", side_effect=import_without_renderer), self.assertRaisesRegex(RuntimeError, "No export was attempted"):
            f.preview(args, service)
        service.assert_not_called()

    def test_read_write_read_uses_revision_and_verifies(self):
        for kind, data_fn in (("docs", document), ("slides", deck)):
            for module in self.candidates:
                before = data_fn()
                after = deepcopy(before)
                if kind == "docs":
                    after["tabs"][0]["documentTab"]["body"]["content"][0]["paragraph"]["elements"][0]["textRun"]["textStyle"]["bold"] = True
                else:
                    after["slides"][0]["pageElements"][0]["shape"]["text"]["textElements"][1]["textRun"]["style"]["bold"] = True
                api = Mock()
                resource = api.documents.return_value if kind == "docs" else api.presentations.return_value
                resource.get.return_value.execute.side_effect = [before, after]
                argv = [kind, "format", "id", "--find", "Alpha", "--style", '{"bold":true}', "--confirm"]
                if kind == "slides":
                    argv += ["--slide-id", "slide1"]
                with patch.object(module, "service", return_value=api), patch("sys.stdout", new_callable=io.StringIO) as output:
                    args = module.build_parser().parse_args(argv)
                    args.func(args)
                    self.assertEqual("formatting_verified", json.loads(output.getvalue())["status"])
                self.assertEqual({"requiredRevisionId": "r1"}, resource.batchUpdate.call_args.kwargs["body"]["writeControl"])
                self.assertEqual(2, resource.get.call_count)

    def test_stale_revision_failure_never_retries(self):
        module = self.candidates[0]
        api = Mock()
        api.documents.return_value.get.return_value.execute.return_value = document()
        api.documents.return_value.batchUpdate.return_value.execute.side_effect = RuntimeError("revision mismatch")
        with patch.object(module, "service", return_value=api):
            args = module.build_parser().parse_args(["docs", "format", "doc", "--find", "Alpha", "--style", '{"bold":true}', "--confirm"])
            with self.assertRaisesRegex(RuntimeError, "revision mismatch"):
                args.func(args)
        self.assertEqual(1, api.documents.return_value.batchUpdate.call_count)

    def test_inspection_is_bounded_and_reports_truncation(self):
        api = Mock()
        api.documents.return_value.get.return_value.execute.return_value = document("x" * 200 + "\n")
        args = argparse.Namespace(kind="docs", identifier="doc", tab_id=None, find=None, max_items=1, max_chars=100)
        result = f.inspect(args, Mock(return_value=api))
        self.assertTrue(result["truncated"])
        self.assertEqual([], result["records"])


class PreviewTests(unittest.TestCase):
    def test_page_selection(self):
        self.assertEqual([1, 2, 3], f.select_pages(None, 10))
        self.assertEqual([1, 3, 4], f.select_pages("1,3-4", 6))
        for value in ("0", "4-2", "1-30", "900", "../1", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                f.select_pages(value, 30)

    def test_output_is_confined_to_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(root / "previews", f.checked_output(root, "previews"))
            with self.assertRaises(ValueError):
                f.checked_output(root, "../escape")

    @unittest.skipUnless(importlib.util.find_spec("pymupdf"), "PyMuPDF not installed in this runtime")
    def test_render_real_pdf_selected_pages_only(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as folder, pymupdf.open() as pdf:
            for i in range(3):
                page = pdf.new_page()
                page.insert_text((50, 50), f"Preview page {i + 1}", fontsize=16)
            result = f.render_pdf(pdf.tobytes(), folder, "2", dpi=100)
            self.assertEqual([2], result["pages"])
            self.assertEqual(3, result["total_pages"])
            self.assertEqual(1, len(result["images"]))
            import struct
            image = Path(result["images"][0]).read_bytes()
            self.assertEqual(b"\x89PNG\r\n\x1a\n", image[:8])
            self.assertGreater(struct.unpack(">I", image[16:20])[0], 500)

    @unittest.skipUnless(importlib.util.find_spec("pymupdf"), "PyMuPDF not installed in this runtime")
    def test_bad_pdf_and_page_range_write_nothing(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as folder, pymupdf.open() as pdf:
            pdf.new_page()
            for payload, pages in ((b"not PDF", None), (pdf.tobytes(), "2")):
                with self.assertRaises(ValueError):
                    f.render_pdf(payload, folder, pages)
                self.assertEqual([], list(Path(folder).iterdir()))

    def test_download_rejects_insecure_url_and_wrong_content(self):
        with self.assertRaises(ValueError):
            f.download_png("http://example.com/image.png")
        response = Mock()
        response.geturl.return_value = "https://example.com/image.png"
        response.read.return_value = b"<html>wrong</html>"
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch("urllib.request.urlopen", return_value=context), self.assertRaises(ValueError):
            f.download_png("https://example.com/image.png")


if __name__ == "__main__":
    unittest.main()
