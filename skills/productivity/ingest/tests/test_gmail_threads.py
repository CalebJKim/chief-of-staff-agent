import base64
import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


scripts = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("thread_actions", scripts / "actions.py")
actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(actions)


def thread(identifier):
    return {"id": identifier, "messages": [
        {"id": f"{identifier}-{i}", "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "Subject", "value": "Meeting feedback"}],
            "body": {"data": base64.urlsafe_b64encode(f"Message {i}".encode()).decode()},
        }} for i in range(3)
    ]}


class GmailThreadsTests(unittest.TestCase):
    def run_command(self, api, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["actions.py", *arguments]), \
                patch.object(sys, "path", [str(scripts), *sys.path]), \
                patch.object(actions, "service", return_value=api) as service, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = actions.main()
        return code, [json.loads(line) for line in stdout.getvalue().splitlines()], stderr.getvalue(), service

    def test_multiple_threads_share_client_preserve_order_and_skip_duplicates(self):
        api = Mock()
        endpoint = api.users.return_value.threads.return_value
        endpoint.get.side_effect = lambda **kw: Mock(execute=Mock(return_value=thread(kw["id"])))
        code, output, error, service = self.run_command(api, "gmail", "threads", "b", "a", "b")
        self.assertEqual((0, ""), (code, error))
        service.assert_called_once_with("gmail", "v1")
        self.assertEqual(["b", "a"], [call.kwargs["id"] for call in endpoint.get.call_args_list])
        self.assertEqual(["b", "a"], [record["thread_id"] for record in output])
        self.assertEqual(3, len(output[0]["messages"]))

    def test_output_and_limits_match_individual_thread_reads(self):
        api = Mock()
        api.users.return_value.threads.return_value.get.return_value.execute.return_value = thread("a")
        arguments = ["a", "--max-messages", "1", "--max-chars", "4"]
        single = self.run_command(api, "gmail", "thread", *arguments)
        multiple = self.run_command(api, "gmail", "threads", *arguments)
        self.assertEqual(single[:3], multiple[:3])
        self.assertEqual("a-2", multiple[1][0]["messages"][0]["id"])
        self.assertEqual("Mess", multiple[1][0]["messages"][0]["body"])

    def test_failure_preserves_prior_results_stops_and_identifies_failed_thread(self):
        api = Mock()
        endpoint = api.users.return_value.threads.return_value
        endpoint.get.return_value.execute.side_effect = [thread("a"), RuntimeError("Access denied")]
        code, output, error, service = self.run_command(api, "gmail", "threads", "a", "b", "c")
        self.assertEqual(1, code)
        self.assertEqual(["a"], [record["thread_id"] for record in output])
        self.assertIn("thread b: Access denied", json.loads(error)["error"])
        self.assertEqual(["a", "b"], [call.kwargs["id"] for call in endpoint.get.call_args_list])
        service.assert_called_once_with("gmail", "v1")


if __name__ == "__main__":
    unittest.main()
