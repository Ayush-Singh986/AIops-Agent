import unittest
from unittest.mock import patch

from agent.remediation import (
    DRY_RUN,
    execute_remediation,
    finalize_diagnosis,
)


def make_state(action, root_cause, evidence=None, needs_more_evidence=False):
    return {
        "remediation_action": action,
        "diagnosed_root_cause": root_cause,
        "evidence_gathered": evidence or [],
        "needs_more_evidence": needs_more_evidence,
        "requires_approval": False,
        "approval_status": None,
        "remediation_result": None,
    }


class RemediationTests(unittest.TestCase):
    def test_dry_run_is_enabled_by_default(self):
        self.assertTrue(DRY_RUN)

    @patch("agent.remediation.subprocess.run")
    def test_dry_run_does_not_execute_compose_action(self, run):
        result = execute_remediation(make_state("scale_out", "process_cpu_rate"))

        run.assert_not_called()
        self.assertEqual(result["remediation_result"]["status"], "dry_run")

    def test_scale_out_requires_supported_root_cause_and_approval(self):
        state = make_state("scale_out", "process_cpu_rate")

        finalize_diagnosis(state)

        self.assertEqual(state["remediation_action"], "scale_out")
        self.assertTrue(state["requires_approval"])
        self.assertEqual(state["approval_status"], "pending")

    def test_scale_out_is_rejected_for_unrelated_root_cause(self):
        state = make_state("scale_out", "redis_average_latency_seconds")

        finalize_diagnosis(state)

        self.assertEqual(state["remediation_action"], "none")
        self.assertFalse(state["requires_approval"])

    def test_rollback_requires_recent_deploy_evidence_and_approval(self):
        state = make_state(
            "rollback_deploy",
            "app_p95_latency_seconds",
            [{"source": "deploy_history", "count": 1}],
        )

        finalize_diagnosis(state)

        self.assertEqual(state["remediation_action"], "rollback_deploy")
        self.assertTrue(state["requires_approval"])

    def test_rollback_is_rejected_without_recent_deploy(self):
        state = make_state("rollback_deploy", "app_p95_latency_seconds")

        finalize_diagnosis(state)

        self.assertEqual(state["remediation_action"], "none")
        self.assertFalse(state["requires_approval"])

    def test_rollback_is_rejected_for_unrelated_root_cause(self):
        state = make_state(
            "rollback_deploy",
            "redis_average_latency_seconds",
            [{"source": "deploy_history", "count": 1}],
        )

        finalize_diagnosis(state)

        self.assertEqual(state["remediation_action"], "none")

    def test_unknown_action_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Unsupported remediation action"):
            finalize_diagnosis(make_state("run_shell", "process_cpu_rate"))

    def test_missing_action_is_finalized_as_noop(self):
        state = make_state(None, None)

        finalize_diagnosis(state)

        self.assertEqual(state["remediation_action"], "none")
        self.assertFalse(state["requires_approval"])

    @patch("agent.remediation.subprocess.run")
    def test_scale_out_executes_bounded_compose_script(self, run):
        with patch("agent.remediation.DRY_RUN", False):
            result = execute_remediation(make_state("scale_out", "process_cpu_rate"))

        run.assert_called_once_with(
            ["bash", "scripts/scale-out-compose.sh"],
            check=True,
            timeout=120,
        )
        self.assertEqual(result["remediation_result"]["status"], "executed")

    @patch("agent.remediation.subprocess.run")
    def test_rollback_executes_compose_script(self, run):
        with patch("agent.remediation.DRY_RUN", False):
            result = execute_remediation(
                make_state("rollback_deploy", "app_p95_latency_seconds")
            )

        run.assert_called_once_with(
            ["bash", "scripts/rollback-compose.sh"],
            check=True,
            timeout=120,
        )
        self.assertEqual(result["remediation_result"]["status"], "executed")

    @patch("agent.remediation.subprocess.run", side_effect=FileNotFoundError("docker"))
    def test_execution_failure_is_visible_in_result(self, run):
        with patch("agent.remediation.DRY_RUN", False):
            result = execute_remediation(make_state("scale_out", "process_cpu_rate"))

        self.assertIn("failed:", result["remediation_result"]["status"])


if __name__ == "__main__":
    unittest.main()
