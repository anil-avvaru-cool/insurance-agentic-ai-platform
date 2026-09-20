import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import terraform_teardown as teardown


class TeardownTests(unittest.TestCase):
    @patch.dict("os.environ", {"AWS_ACCOUNT_ID": "123456789012", "AWS_REGION": "us-east-1"})
    def test_delayed_dlq_work_blocks_teardown(self):
        empty = {key: "0" for key in teardown.COUNTERS}
        empty["QueueArn"] = "arn:aws:sqs:us-east-1:123456789012:tasks"
        delayed = {**empty, "ApproximateNumberOfMessagesDelayed": "1"}
        outputs = {name: {"value": name} for name in
                   ("task_queue_url", "dead_letter_queue_url")}
        with patch.object(teardown, "run", return_value=json.dumps(outputs)), patch.object(
            teardown, "aws", side_effect=[{"Account": "123456789012"},
                                          {"Attributes": empty}, {"Attributes": delayed}]
        ), self.assertRaisesRegex(SystemExit, "messages remain"):
            teardown.check_queues()

    @patch.dict("os.environ", {"AWS_ACCOUNT_ID": "123456789012"})
    def test_wrong_account_blocks_before_reading_state(self):
        with patch.object(teardown, "aws", return_value={"Account": "999999999999"}), patch.object(
            teardown, "run"
        ) as run, self.assertRaisesRegex(SystemExit, "credentials do not match"):
            teardown.check_queues()
        run.assert_not_called()

    def test_prepare_reuses_snapshot_and_never_applies(self):
        with tempfile.TemporaryDirectory() as directory:
            variables = Path(directory) / "teardown.tfvars.json"
            with patch.object(teardown, "VARIABLES", variables), patch.object(
                teardown, "check_queues"
            ), patch("sys.argv", ["teardown", "prepare", "--reconciled"]), patch.object(
                teardown.subprocess, "run"
            ) as run:
                teardown.main()
                first = variables.read_text()
                teardown.main()
            self.assertEqual(first, variables.read_text())
            values = json.loads(first)
            self.assertFalse(values["db_deletion_protection"])
            self.assertRegex(values["final_snapshot_identifier"], "^[a-z][a-z0-9]{0,62}$")
            for call in run.call_args_list:
                self.assertEqual(call.args[0][2], "plan")
                self.assertIn(f"-var-file={variables}", call.args[0])

    def test_busy_queue_prevents_file_creation_or_plan(self):
        with patch("sys.argv", ["teardown", "prepare", "--reconciled"]), patch.object(
            teardown, "check_queues", side_effect=SystemExit("busy")
        ), patch.object(teardown.subprocess, "run") as run, self.assertRaises(SystemExit):
            teardown.main()
        run.assert_not_called()
