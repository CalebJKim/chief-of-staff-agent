from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = ROOT / "plugins" / "chief-of-staff-scope-guard" / "__init__.py"
SPEC = importlib.util.spec_from_file_location("chief_of_staff_scope_guard", PLUGIN_PATH)
assert SPEC and SPEC.loader
scope_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope_guard)


def terminal_args(operation: str) -> dict[str, str]:
    return {
        "command": (
            'bash "$HERMES_HOME/skills/productivity/chief-of-staff/scripts/action.sh" '
            + operation
        )
    }


class ScopeGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        scope_guard._reset_state_for_tests()

    def authorize_write(
        self,
        message: str = "Update the requested Workspace item.",
        *,
        turn: str = "turn-1",
    ) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            turn_id=turn,
            user_message=message,
        )

    def call(
        self,
        operation: str,
        *,
        turn: str = "turn-1",
        call: str = "call-1",
        status: str = "ok",
        result: str = (
            '{"output":"{\\"confirmation_markdown\\":\\"**Updated.**\\"}",'
            '"exit_code":0,"error":null}'
        ),
    ):
        return {
            "tool_name": "terminal",
            "args": terminal_args(operation),
            "session_id": "session-1",
            "turn_id": turn,
            "tool_call_id": call,
            "status": status,
            "result": result,
        }

    def test_recognizes_generic_mutations_but_not_reads(self) -> None:
        mutations = (
            "gmail draft --to person@example.com --confirm",
            "gmail reply-draft --message-id abc --confirm",
            "calendar create --title Review --confirm",
            "calendar move --event-id abc --confirm",
            "calendar reschedule --event-id abc --confirm",
            "docs append --file-id abc --text hello --confirm",
            "docs replace-text --file-id abc --old x --new y --confirm",
            "sheets update --file-id abc --range A1 --values '[[1]]' --confirm",
            "sheets set-cell --file-id abc --cell C7 --value Done --confirm",
            "slides replace-text --file-id abc --old x --new y --confirm",
        )
        for operation in mutations:
            with self.subTest(operation=operation):
                self.assertTrue(scope_guard._managed_mutation("terminal", terminal_args(operation)))
        self.assertFalse(scope_guard._managed_mutation("terminal", terminal_args("docs get --file-id abc")))
        self.assertFalse(scope_guard._managed_mutation("terminal", {"command": "echo slides replace-text"}))
        self.assertFalse(scope_guard._managed_mutation("browser", terminal_args(mutations[0])))

    def test_write_authorization_comes_only_from_an_explicit_current_request(self) -> None:
        explicit = (
            "Update the overview slide.",
            "Can you mark the tracker as done?",
            "For the review, put those bullets on the Introduction slide.",
            "I want you to draft a reply to the sender.",
            "Let's reschedule the meeting.",
            "Help me prepare by updating the presentation.",
        )
        read_only = (
            "Help me prepare for the review.",
            "What should I work on today?",
            "Summarize the linked document.",
            "Show me what needs to be updated.",
            "Can you tell me what to change in the tracker?",
            "I want to know how to update the presentation.",
        )
        for message in explicit:
            with self.subTest(message=message):
                self.assertTrue(scope_guard._explicit_write_request(message))
        for message in read_only:
            with self.subTest(message=message):
                self.assertFalse(scope_guard._explicit_write_request(message))

    def test_blocks_a_mutation_without_explicit_current_authorization(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            turn_id="turn-1",
            user_message="Help me prepare for the review.",
        )

        blocked = scope_guard.pre_tool_call(
            **self.call("slides replace-text --file-id abc --confirm")
        )

        self.assertEqual("block", blocked["action"])
        self.assertIn("read-only preparation", blocked["message"])

    def test_blocks_a_mutation_without_a_user_boundary(self) -> None:
        call = self.call("slides replace-text --file-id abc --confirm")
        call.pop("session_id")

        blocked = scope_guard.pre_tool_call(**call)

        self.assertEqual("block", blocked["action"])
        self.assertIn("no current user authorization boundary", blocked["message"])

    def test_blocks_a_second_mutation_in_the_same_turn(self) -> None:
        self.authorize_write()
        first = self.call("slides replace-text --file-id abc --confirm")
        second = self.call("sheets set-cell --file-id def --confirm", call="call-2")

        self.assertIsNone(scope_guard.pre_tool_call(**first))
        blocked = scope_guard.pre_tool_call(**second)

        self.assertEqual("block", blocked["action"])
        self.assertIn("already ran", blocked["message"])

    def test_allows_a_mutation_in_the_next_turn(self) -> None:
        self.authorize_write()
        self.assertIsNone(scope_guard.pre_tool_call(**self.call("slides replace-text --confirm")))
        scope_guard.pre_llm_call(
            session_id="session-1",
            turn_id="turn-2",
            user_message="Mark the tracker done.",
        )
        self.assertIsNone(
            scope_guard.pre_tool_call(
                **self.call("sheets set-cell --confirm", turn="turn-2", call="call-2")
            )
        )

    def test_failed_first_mutation_releases_the_turn(self) -> None:
        self.authorize_write()
        failed = self.call("slides replace-text --confirm", status="error")
        self.assertIsNone(scope_guard.pre_tool_call(**failed))
        scope_guard.post_tool_call(**failed)

        retry = self.call("slides replace-text --confirm", call="call-2")
        self.assertIsNone(scope_guard.pre_tool_call(**retry))

    def test_explicit_write_read_result_tells_model_not_to_reconfirm(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            user_message="Put the approved wording on the overview slide.",
        )
        read = self.call(
            "slides get presentation-1",
            result=(
                '{"output":"{\\"id\\":\\"presentation-1\\",\\"slides\\":[]}",'
                '"exit_code":0,"error":null}'
            ),
        )

        transformed = scope_guard.transform_tool_result(**read)

        self.assertIn("already authorized", transformed)
        self.assertIn("execute exactly one matching managed mutation", transformed)
        self.assertIn("Do not ask for confirmation", transformed)

    def test_failed_read_does_not_tell_model_to_write(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            user_message="Update the overview slide.",
        )
        failed_read = self.call(
            "slides get presentation-1",
            result='{"output":"not found","exit_code":1,"error":null}',
        )

        self.assertIsNone(scope_guard.transform_tool_result(**failed_read))

    def test_structured_prewrite_rejection_allows_one_corrected_attempt(self) -> None:
        self.authorize_write("Draft a reply to the sender.")
        rejected = self.call(
            "gmail reply-draft message-1 --confirm",
            result=(
                '{"output":"{\\"status\\":\\"rejected\\",\\"created\\":false,'
                '\\"reason\\":\\"body fact missing\\"}","exit_code":0,"error":null}'
            ),
        )
        self.assertIsNone(scope_guard.pre_tool_call(**rejected))

        transformed = scope_guard.transform_tool_result(**rejected)

        self.assertIn("No Workspace write occurred", transformed)
        self.assertIn("retry", transformed)
        corrected = self.call(
            "gmail reply-draft message-1 --body corrected --confirm",
            call="call-2",
        )
        self.assertIsNone(scope_guard.pre_tool_call(**corrected))

    def test_second_structured_rejection_stops_additional_attempts(self) -> None:
        self.authorize_write("Draft a reply to the sender.")
        first = self.call(
            "gmail reply-draft message-1 --confirm",
            result='{"status":"rejected","created":false,"reason":"first rejection"}',
        )
        self.assertIsNone(scope_guard.pre_tool_call(**first))
        scope_guard.transform_tool_result(**first)
        second = self.call(
            "gmail reply-draft message-1 --body corrected --confirm",
            call="call-2",
            result='{"status":"rejected","created":false,"reason":"second rejection"}',
        )
        self.assertIsNone(scope_guard.pre_tool_call(**second))

        transformed = scope_guard.transform_tool_result(**second)

        self.assertIn("one allowed correction", transformed)
        third = self.call(
            "gmail reply-draft message-1 --body another --confirm",
            call="call-3",
        )
        blocked = scope_guard.pre_tool_call(**third)
        self.assertEqual("block", blocked["action"])

    def test_temporary_google_failure_stops_and_returns_user_message(self) -> None:
        self.authorize_write("Update the tracker status.")
        temporary = self.call(
            "sheets set-cell sheet-1 --confirm",
            result=(
                '{"status":"temporarily_unavailable","ok":false,'
                '"user_message":"Google Workspace timed out. This is a temporary Google-side issue; '
                'please try again later."}'
            ),
        )
        self.assertIsNone(scope_guard.pre_tool_call(**temporary))

        transformed = scope_guard.transform_tool_result(**temporary)

        self.assertIn("Make no more tool calls", transformed)
        self.assertIn("user_message", transformed)

    def test_doc_read_link_is_preserved_when_model_omits_it(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            user_message="Summarize the linked document.",
        )
        read = self.call(
            "docs get document-1",
            result=(
                '{"output":"{\\"title\\":\\"Live Product Brief\\",\\"url\\":'
                '\\"https://docs.google.com/document/d/document-1/edit\\",'
                '\\"text\\":\\"Source\\"}","exit_code":0,"error":null}'
            ),
        )

        scope_guard.transform_tool_result(**read)
        transformed = scope_guard.transform_llm_output(
            session_id="session-1",
            response_text="- First summary point\n- Second summary point",
        )

        self.assertTrue(transformed.endswith(
            "[Live Product Brief](https://docs.google.com/document/d/document-1/edit)"
        ))

    def test_requested_bullet_summary_normalizes_prose_and_keeps_live_link(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            user_message="Summarize the linked brief into a few bullet points.",
        )
        read = self.call(
            "docs get document-1",
            result=(
                '{"output":"{\\"title\\":\\"Live Operations Brief\\",\\"url\\":'
                '\\"https://docs.google.com/document/d/document-1/edit\\",'
                '\\"text\\":\\"Source\\"}","exit_code":0,"error":null}'
            ),
        )
        scope_guard.transform_tool_result(**read)

        transformed = scope_guard.transform_llm_output(
            session_id="session-1",
            response_text=(
                "Here's a summary of the brief: Teams reduced manual coordination. "
                "Managers kept approval control. The review asks for a pilot decision."
            ),
        )

        self.assertEqual(3, len(re.findall(r"(?m)^- ", transformed)))
        self.assertIn("- Teams reduced manual coordination.", transformed)
        self.assertTrue(transformed.endswith(
            "[Live Operations Brief](https://docs.google.com/document/d/document-1/edit)"
        ))

    def test_existing_bullet_summary_passes_through(self) -> None:
        response = "- First point\n- Second point"
        self.assertEqual(response, scope_guard._bullet_summary_only(response))

    def test_doc_read_link_is_not_duplicated(self) -> None:
        scope_guard.pre_llm_call(session_id="session-1", user_message="Read the document.")
        read = self.call(
            "docs get document-1",
            result=(
                '{"output":"{\\"title\\":\\"Live Product Brief\\",\\"url\\":'
                '\\"https://docs.google.com/document/d/document-1/edit\\",'
                '\\"text\\":\\"Source\\"}","exit_code":0,"error":null}'
            ),
        )
        scope_guard.transform_tool_result(**read)
        response = "Summary: https://docs.google.com/document/d/document-1/edit"

        self.assertIsNone(scope_guard.transform_llm_output(
            session_id="session-1",
            response_text=response,
        ))

    def test_successful_result_tells_model_to_stop(self) -> None:
        self.authorize_write()
        first = self.call("slides replace-text --confirm")
        self.assertIsNone(scope_guard.pre_tool_call(**first))

        transformed = scope_guard.transform_tool_result(**first)

        self.assertIn(first["result"], transformed)
        self.assertIn("Make no more tool calls", transformed)
        self.assertIn("confirmation_markdown", transformed)
        self.assertEqual(
            "**Updated.**",
            scope_guard.transform_llm_output(session_id="session-1"),
        )

    def test_new_turn_clears_a_stale_confirmation(self) -> None:
        self.authorize_write()
        first = self.call("slides replace-text --confirm")
        self.assertIsNone(scope_guard.pre_tool_call(**first))
        scope_guard.transform_tool_result(**first)

        scope_guard.pre_llm_call(session_id="session-1")

        self.assertIsNone(scope_guard.transform_llm_output(session_id="session-1"))

    def test_registers_all_hooks(self) -> None:
        registered = []

        class Context:
            def register_hook(self, name, callback):
                registered.append((name, callback))

        scope_guard.register(Context())

        self.assertEqual(
            [
                "pre_llm_call",
                "pre_tool_call",
                "post_tool_call",
                "transform_tool_result",
                "transform_llm_output",
            ],
            [name for name, _callback in registered],
        )

    def test_preparation_turn_allows_one_read_and_neutralizes_more_reads(self) -> None:
        context = scope_guard.pre_llm_call(
            session_id="session-1",
            turn_id="turn-1",
            user_message="Help me prepare for tomorrow's review.",
        )
        self.assertIn("exactly one", context["context"])
        first = self.call("gmail thread message-1")
        self.assertIsNone(scope_guard.pre_tool_call(**first))
        transformed = scope_guard.transform_tool_result(**first)
        self.assertIn("Return only the tasks", transformed)
        self.assertIn("final answer with zero tool calls", transformed)
        self.assertIn("Do not open linked files", transformed)

        second_read = self.call("docs get file-1", call="call-2")
        neutralized_read = scope_guard.pre_tool_call(**second_read)
        self.assertEqual("modify", neutralized_read["action"])
        self.assertIn("PREPARATION_COMPLETE", neutralized_read["args"]["command"])
        self.assertEqual(5, neutralized_read["args"]["timeout"])

        write = self.call("slides replace-text --confirm", call="call-3")
        blocked_write = scope_guard.pre_tool_call(**write)
        self.assertEqual("block", blocked_write["action"])
        self.assertIn("read-only preparation", blocked_write["message"])

    def test_preparation_sanitizes_trailing_flags_from_the_focused_thread_read(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            user_message="Help me prepare for the review.",
        )
        call = self.call(
            "gmail thread live-message-id --unsupported-read-flag value"
        )

        modified = scope_guard.pre_tool_call(**call)

        self.assertEqual("modify", modified["action"])
        self.assertTrue(modified["args"]["command"].endswith(
            "gmail thread live-message-id"
        ))
        self.assertNotIn("unsupported-read-flag", modified["args"]["command"])

    def test_preparation_final_keeps_only_numbered_tasks(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            turn_id="turn-1",
            user_message="Help me prepare for tomorrow's review.",
        )
        response = (
            "Extra preamble.\n\n"
            "1. Read the linked brief.\n"
            "2. Update the presentation.\n"
            "3. Mark the tracker done.\n\n"
            "Want me to continue?"
        )

        transformed = scope_guard.transform_llm_output(
            session_id="session-1",
            response_text=response,
        )

        self.assertEqual(
            "1. Read the linked brief.\n"
            "2. Update the presentation.\n"
            "3. Mark the tracker done.",
            transformed,
        )

    def test_preparation_restores_exact_live_links_to_linkless_tasks(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-prep",
            user_message="Help me prepare for tomorrow's review.",
        )
        result = self.call(
            "gmail thread message-1",
            result=json.dumps({
                "output": json.dumps({
                    "thread_id": "thread-1",
                    "messages": [{
                        "body": (
                            "Product summary: https://docs.google.com/document/d/doc-1/edit\n"
                            "Executive review deck: https://docs.google.com/presentation/d/deck-1/edit\n"
                            "Prep tracker: https://docs.google.com/spreadsheets/d/sheet-1/edit"
                        )
                    }],
                }),
                "exit_code": 0,
                "error": None,
            }),
        )
        result["session_id"] = "session-prep"
        scope_guard.pre_tool_call(**result)
        scope_guard.transform_tool_result(**result)

        transformed = scope_guard.transform_llm_output(
            session_id="session-prep",
            response_text=(
                "1. Read the product summary (link already in the message).\n"
                "2. Replace the placeholder on the deck.\n"
                "3. Mark the prep tracker done."
            ),
        )

        self.assertIn("https://docs.google.com/document/d/doc-1/edit", transformed)
        self.assertIn("https://docs.google.com/presentation/d/deck-1/edit", transformed)
        self.assertIn("https://docs.google.com/spreadsheets/d/sheet-1/edit", transformed)

    def test_preparation_rebuild_restores_a_link_from_discarded_model_text(self) -> None:
        transformed = scope_guard._numbered_tasks_only(
            (
                "1. Read the source [Source](https://docs.google.com/document/d/doc-1/edit)\n"
                "2. Begin the next task"
            ),
            [
                ("Source", "https://docs.google.com/document/d/doc-1/edit"),
                ("Presentation", "https://docs.google.com/presentation/d/deck-1/edit"),
                ("Tracker", "https://docs.google.com/spreadsheets/d/sheet-1/edit"),
            ],
            [
                "Read the source",
                "Update the presentation",
                "Mark the tracker complete",
            ],
        )

        self.assertIn("https://docs.google.com/document/d/doc-1/edit", transformed)
        self.assertIn("https://docs.google.com/presentation/d/deck-1/edit", transformed)
        self.assertIn("https://docs.google.com/spreadsheets/d/sheet-1/edit", transformed)

    def test_requested_bullet_summary_splits_collapsed_inline_numbering(self) -> None:
        transformed = scope_guard._bullet_summary_only(
            (
                "Here's the summary: 1) **First:** One point."
                "2) **Second:** Another point."
                "3) **Third:** Final point. "
                "Source: https://docs.google.com/document/d/doc-1/edit"
            ),
        )

        self.assertEqual(3, len(re.findall(r"(?m)^- ", transformed)))
        self.assertIn("- **First:** One point.", transformed)
        self.assertIn("- **Third:** Final point.", transformed)
        self.assertIn("https://docs.google.com/document/d/doc-1/edit", transformed)

    def test_preparation_uses_explicit_live_request_clauses_when_model_merges_tasks(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-prep",
            user_message="Help me prepare for tomorrow's review.",
        )
        result = self.call(
            "gmail thread message-1",
            result=json.dumps({
                "output": json.dumps({
                    "thread_id": "thread-1",
                    "messages": [{
                        "body": (
                            "Before the review, please read the research brief. "
                            "Then use it to replace the overview slide. "
                            "Once the slide is updated, mark the readiness tracker complete.\n\n"
                            "Research brief: https://docs.google.com/document/d/doc-2/edit\n"
                            "Overview slide: https://docs.google.com/presentation/d/deck-2/edit\n"
                            "Readiness tracker: https://docs.google.com/spreadsheets/d/sheet-2/edit"
                        )
                    }],
                }),
                "exit_code": 0,
                "error": None,
            }),
        )
        result["session_id"] = "session-prep"
        scope_guard.pre_tool_call(**result)
        scope_guard.transform_tool_result(**result)

        transformed = scope_guard.transform_llm_output(
            session_id="session-prep",
            response_text=(
                "1. Read the research brief and update the overview slide.\n"
                "2. Mark the tracker complete, then confirm with the sender."
            ),
        )

        self.assertEqual(3, len(re.findall(r"(?m)^\d+\. ", transformed)))
        self.assertIn("1. Read the research brief", transformed)
        self.assertIn("2. Use it to replace the overview slide", transformed)
        self.assertIn("3. Mark the readiness tracker complete", transformed)
        self.assertNotIn("confirm with the sender", transformed)
        self.assertIn("https://docs.google.com/document/d/doc-2/edit", transformed)
        self.assertIn("https://docs.google.com/presentation/d/deck-2/edit", transformed)
        self.assertIn("https://docs.google.com/spreadsheets/d/sheet-2/edit", transformed)

    def test_preparation_uses_live_request_clauses_when_model_returns_no_list(self) -> None:
        transformed = scope_guard._numbered_tasks_only(
            "The materials are ready. Is there anything else you need?",
            [
                ("Research brief", "https://docs.google.com/document/d/doc-3/edit"),
                ("Overview slide", "https://docs.google.com/presentation/d/deck-3/edit"),
                ("Readiness tracker", "https://docs.google.com/spreadsheets/d/sheet-3/edit"),
            ],
            [
                "Read the research brief",
                "Update the overview slide",
                "Mark the readiness tracker complete",
            ],
        )

        self.assertEqual(3, len(re.findall(r"(?m)^\d+\. ", transformed)))
        self.assertIn("1. Read the research brief", transformed)
        self.assertIn("2. Update the overview slide", transformed)
        self.assertIn("3. Mark the readiness tracker complete", transformed)
        self.assertNotIn("anything else", transformed)
        self.assertIn("https://docs.google.com/document/d/doc-3/edit", transformed)
        self.assertIn("https://docs.google.com/presentation/d/deck-3/edit", transformed)
        self.assertIn("https://docs.google.com/spreadsheets/d/sheet-3/edit", transformed)

    def test_daily_brief_final_keeps_only_the_contract_shape(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-brief",
            user_message="What should I work on today? Give me the top three things.",
        )
        transformed = scope_guard.transform_llm_output(
            session_id="session-brief",
            response_text=(
                "Here are your three priorities for today:\n\n"
                "1. **Prepare the review** — The meeting moved to today. [Mail](https://example.test/1)\n\n"
                "Extra detail that should not become another paragraph.\n\n"
                "2. **Review feedback** — A decision is needed today. [Mail](https://example.test/2)\n\n"
                "Another extra paragraph.\n\n"
                "3. **Check the briefing** — It is ready for review. [Mail](https://example.test/3)\n\n"
                "Would you like help?"
            ),
        )

        self.assertEqual(
            "Here are your three priorities for today:\n\n"
            "1. **Prepare the review**\n"
            "   - **Context:** The meeting moved to today. [Mail](https://example.test/1)\n\n"
            "2. **Review feedback**\n"
            "   - **Context:** A decision is needed today. [Mail](https://example.test/2)\n\n"
            "3. **Check the briefing**\n"
            "   - **Context:** It is ready for review. [Mail](https://example.test/3)",
            transformed,
        )

    def test_daily_brief_caps_extra_model_items_at_requested_top_n(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-brief",
            user_message="What should I work on today? Give me the top three things.",
        )
        transformed = scope_guard.transform_llm_output(
            session_id="session-brief",
            response_text=(
                "Here are your priorities for today:\n\n"
                "1. **First item** — First context.\n\n"
                "2. **Second item** — Second context.\n\n"
                "3. **Third item** — Third context.\n\n"
                "4. **Extra item** — Extra context."
            ),
        )

        self.assertEqual(3, len(re.findall(r"(?m)^\d+\. ", transformed)))
        self.assertEqual(3, transformed.count("**Context:**"))
        self.assertNotIn("Extra item", transformed)

        scope_guard.pre_llm_call(
            session_id="session-brief-four",
            user_message="What are my top 4 priorities today?",
        )
        transformed_four = scope_guard.transform_llm_output(
            session_id="session-brief-four",
            response_text=(
                "1. **First item** — First context.\n\n"
                "2. **Second item** — Second context.\n\n"
                "3. **Third item** — Third context.\n\n"
                "4. **Fourth item** — Fourth context."
            ),
        )
        self.assertIn("4. **Fourth item**", transformed_four)

    def test_daily_brief_uses_only_packet_backed_mail_labels_and_urls(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-brief",
            user_message="What should I work on today? Give me the top three things.",
        )
        packet = {
            "recent_files": [
                {
                    "url": (
                        "https://docs.google.com/spreadsheets/d/"
                        "live-sheet-id-abc/edit"
                    )
                }
            ],
            "mail": [
                {
                    "from": "Maya Patel <maya@example.test>",
                    "url": "https://mail.google.com/mail/u/0/#all/maya",
                    "selection_order": 1,
                },
                {
                    "from": "Priya Shah <priya@example.test>",
                    "url": "https://mail.google.com/mail/u/0/#all/priya",
                    "selection_order": 2,
                },
                {
                    "from": "Elena Torres <elena@example.test>",
                    "url": "https://mail.google.com/mail/u/0/#all/elena",
                    "selection_order": 3,
                },
            ]
        }
        tool_result = {
            "tool_name": "terminal",
            "args": {
                "command": (
                    'bash "$HERMES_HOME/skills/productivity/chief-of-staff/'
                    'scripts/start_day.sh"'
                )
            },
            "session_id": "session-brief",
            "tool_call_id": "start-day-1",
            "status": "ok",
            "result": json.dumps({"output": json.dumps(packet), "exit_code": 0, "error": None}),
        }
        scope_guard.transform_tool_result(**tool_result)

        transformed = scope_guard.transform_llm_output(
            session_id="session-brief",
            response_text=(
                "Here are your priorities:\n\n"
                "1. **Prepare the review** — Review prep. "
                "[Sheet](https://docs.google.com/spreadsheets/d/live-sheet-id-ab/edit) "
                "[Mail — Jordan Lee](https://mail.google.com/mail/u/0/#all/priya)\n\n"
                "2. **Review feedback** — Decide the next step. "
                "[Mail — Priya Shah](https://mail.google.com/mail/u/0/#all/priya)\n\n"
                "3. **Check the briefing** — Confirm the story. "
                "[Mail — Elena Torres](https://mail.google.com/mail/u/0/#all/elena)"
            ),
        )

        self.assertIn(
            "[Mail — Maya Patel](https://mail.google.com/mail/u/0/#all/maya)",
            transformed,
        )
        self.assertNotIn("Jordan Lee", transformed)
        self.assertIn(
            "[Sheet](https://docs.google.com/spreadsheets/d/live-sheet-id-abc/edit)",
            transformed,
        )

    def test_preparation_repairs_a_strong_unique_live_url_match(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-prep",
            user_message="Help me prepare for the review.",
        )
        exact_url = "https://docs.google.com/document/d/live-document-id-xyz/edit"
        result = self.call(
            "gmail thread message-1",
            result=json.dumps({
                "output": json.dumps({
                    "messages": [{"body": f"Product summary: {exact_url}"}],
                }),
                "exit_code": 0,
                "error": None,
            }),
        )
        result["session_id"] = "session-prep"
        scope_guard.pre_tool_call(**result)
        scope_guard.transform_tool_result(**result)

        transformed = scope_guard.transform_llm_output(
            session_id="session-prep",
            response_text=(
                "1. Read the product summary "
                "[Doc](https://docs.google.com/document/d/live-document-id-xy/edit)"
            ),
        )

        self.assertIn(f"[Doc]({exact_url})", transformed)

    def test_concrete_preparation_request_is_not_forced_read_only(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            turn_id="turn-1",
            user_message="Help me prepare by updating the slide.",
        )

        write = self.call("slides replace-text --confirm")

        self.assertIsNone(scope_guard.pre_tool_call(**write))

    def test_new_message_clears_preparation_even_if_turn_id_is_reused(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-1",
            turn_id="reused-turn",
            user_message="Help me prepare for tomorrow's review.",
        )
        first = self.call("gmail thread message-1", turn="reused-turn")
        self.assertIsNone(scope_guard.pre_tool_call(**first))

        context = scope_guard.pre_llm_call(
            session_id="session-1",
            turn_id="reused-turn",
            user_message="Summarize the linked document.",
        )
        second = self.call("docs get file-1", turn="reused-turn", call="call-2")

        self.assertIsNone(scope_guard.pre_tool_call(**second))
        self.assertIn("new authorization boundary", context["context"])
        self.assertIn("historical", context["context"])

    def test_daily_brief_without_preamble_gets_a_short_opening(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-brief",
            user_message="What should I work on today?",
        )
        transformed = scope_guard.transform_llm_output(
            session_id="session-brief",
            response_text=(
                "1. **Prepare the review**\n"
                "   - **Context:** The meeting moved to today.\n"
                "2. **Review feedback**\n"
                "   - **Context:** A decision is needed."
            ),
        )

        self.assertTrue(transformed.startswith("Here are your priorities for today:\n\n1."))

    def test_daily_brief_numbers_bold_items_when_model_omits_numbers(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-brief",
            user_message="What should I work on today?",
        )
        transformed = scope_guard.transform_llm_output(
            session_id="session-brief",
            response_text=(
                "Three items need attention today.\n\n"
                "**Prepare the review**\n"
                "- **Context:** The deck needs an update.\n\n"
                "**Review pilot feedback**\n"
                "- **Context:** A decision is pending.\n\n"
                "**Check the briefing**\n"
                "- **Context:** The owner review is pending."
            ),
        )

        self.assertEqual(3, len(re.findall(r"(?m)^\d+\. \*\*", transformed)))
        self.assertIn("1. **Prepare the review**", transformed)
        self.assertIn("3. **Check the briefing**", transformed)

    def test_daily_brief_numbers_plain_headings_followed_by_context(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-brief",
            user_message="What should I work on today?",
        )
        transformed = scope_guard.transform_llm_output(
            session_id="session-brief",
            response_text=(
                "Prepare the review\n"
                "- **Context:** The deck needs an update.\n\n"
                "Review pilot feedback\n"
                "- **Context:** A decision is pending.\n\n"
                "Check the briefing\n"
                "- **Context:** The owner review is pending."
            ),
        )

        self.assertEqual(3, len(re.findall(r"(?m)^\d+\. \*\*", transformed)))
        self.assertIn("1. **Prepare the review**", transformed)
        self.assertIn("3. **Check the briefing**", transformed)

    def test_daily_brief_numbers_standalone_headings_followed_by_plain_bullets(self) -> None:
        transformed = scope_guard._daily_brief_only(
            (
                "Here are your priorities for today:\n\n"
                "EXECUTIVE REVIEW PREP\n"
                "- Update the review materials. [Mail](https://mail.google.com/mail/u/0/#all/one)\n\n"
                "CUSTOMER PILOT DECISION\n"
                "- Review the open decision points. [Mail](https://mail.google.com/mail/u/0/#all/two)\n\n"
                "PARTNER BRIEFING REVIEW\n"
                "- Confirm the practical framing. [Mail](https://mail.google.com/mail/u/0/#all/three)"
            ),
            max_items=3,
        )

        self.assertEqual(3, len(re.findall(r"(?m)^\d+\. ", transformed)))
        self.assertEqual(3, transformed.count("**Context:**"))
        self.assertIn("1. **EXECUTIVE REVIEW PREP**", transformed)
        self.assertIn("2. **CUSTOMER PILOT DECISION**", transformed)
        self.assertIn("3. **PARTNER BRIEFING REVIEW**", transformed)
        self.assertNotIn("**Context:** - ", transformed)

    def test_daily_brief_numbers_bold_inline_items_with_punctuation(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-brief",
            user_message="What should I work on today? Give me the top three things.",
        )
        transformed = scope_guard.transform_llm_output(
            session_id="session-brief",
            response_text=(
                "**Prepare the review.** Read the current brief before the meeting. "
                "[Mail — Sender One](https://mail.google.com/mail/u/0/#all/one)\n\n"
                "**Review customer feedback.** Decide which requests move forward. "
                "[Mail — Sender Two](https://mail.google.com/mail/u/0/#all/two)\n\n"
                "**Check the partner briefing.** Confirm the story is ready. "
                "[Mail — Sender Three](https://mail.google.com/mail/u/0/#all/three)"
            ),
        )

        self.assertEqual(3, len(re.findall(r"(?m)^\d+\. ", transformed)))
        self.assertEqual(3, transformed.count("**Context:**"))
        self.assertIn("1. **Prepare the review.**", transformed)
        self.assertIn("3. **Check the partner briefing.**", transformed)

    def test_daily_brief_normalizes_bold_number_headings_and_plain_context(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-brief",
            user_message="What should I work on today? Give me the top three things.",
        )
        transformed = scope_guard.transform_llm_output(
            session_id="session-brief",
            response_text=(
                "**1. Prepare the review**\n\n"
                "The meeting moved to today. Read the source before the meeting. "
                "Next step: update the deck.\n\n"
                "**2. Review feedback**\n\n"
                "Customer feedback needs a decision.\n\n"
                "**3. Check the briefing**\n\n"
                "The briefing is ready for review."
            ),
        )

        self.assertEqual(3, len(re.findall(r"(?m)^\d+\. \*\*", transformed)))
        self.assertEqual(3, transformed.count("- **Context:**"))
        self.assertNotIn("Next step:", transformed)

    def test_daily_brief_normalizes_unbolded_context_label(self) -> None:
        scope_guard.pre_llm_call(
            session_id="session-brief",
            user_message="What should I work on today? Give me the top two things.",
        )
        transformed = scope_guard.transform_llm_output(
            session_id="session-brief",
            response_text=(
                "Two items need attention.\n\n"
                "1. **Prepare the review**\n"
                "- Context: The meeting moved to today.\n\n"
                "2. **Review feedback**\n"
                "- Context: A decision is pending."
            ),
        )

        self.assertEqual(2, transformed.count("- **Context:**"))
        self.assertNotIn("- Context:", transformed)


if __name__ == "__main__":
    unittest.main()
