import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault(
    "LOG_FILE",
    str(Path(tempfile.gettempdir()) / "aiops-deploy-history-test-app.jsonl"),
)

from agent import utils


class LoadDeployHistoryTests(unittest.TestCase):
    def test_loads_newline_and_concatenated_json_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "deploys.jsonl"
            history.write_text(
                '{"action":"deploy"}\n'
                '{"action":"rollback"}{"action":"deploy"}\n',
                encoding="utf-8",
            )

            with patch.object(utils, "DEPLOY_FILE", history):
                events = utils.load_deploy_history()

        self.assertEqual(
            events,
            [
                {"action": "deploy"},
                {"action": "rollback"},
                {"action": "deploy"},
            ],
        )

    def test_invalid_json_reports_file_and_line(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "deploys.jsonl"
            history.write_text('{"action":"deploy"}\nnot-json\n', encoding="utf-8")

            with patch.object(utils, "DEPLOY_FILE", history):
                with self.assertRaisesRegex(ValueError, r"deploys\.jsonl at line 2"):
                    utils.load_deploy_history()


if __name__ == "__main__":
    unittest.main()
