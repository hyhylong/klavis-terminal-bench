"""A reward alone must never become evidence of a genuine model failure."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/report_trials.py"


def trial(agent="codex", reward=0, finished=True):
    return {
        "id": "trial-id", "trial_name": "ledger__one", "task_name": "ledger",
        "task_checksum": "abc123", "agent_info": {
            "name": agent, "version": "1.2.3",
            "model_info": {"name": "provider/model", "provider": "provider"},
        },
        "started_at": "2026-09-26T01:00:00+00:00",
        "finished_at": "2026-09-26T01:02:00+00:00" if finished else None,
        "agent_execution": {
            "started_at": "2026-09-26T01:00:10+00:00",
            "finished_at": "2026-09-26T01:01:55+00:00" if finished else None,
        },
        "exception_info": None, "step_results": None,
        "verifier_result": {"rewards": {"reward": reward}},
    }


class TrialReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = None
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location("trial_reporting", SCRIPT)
            cls.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)

    def reporter(self):
        self.assertIsNotNone(self.module, "The sanitized trial reporter has not been implemented")
        return self.module

    def write_trial(self, root, data, name="ledger__one", ctrf=True):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "result.json").write_text(json.dumps(data), encoding="utf-8")
        if ctrf:
            verifier = folder / "verifier"
            verifier.mkdir(exist_ok=True)
            (verifier / "ctrf.json").write_text('{"results":{"tests":[]}}', encoding="utf-8")
        return folder

    def report_one(self, data, ctrf=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_trial(root, data, ctrf=ctrf)
            return self.reporter().build_report([root])

    def test_timeout_and_api_failure_override_zero_reward(self):
        for exception_type in ("AgentTimeoutError", "AuthenticationError"):
            with self.subTest(exception_type=exception_type):
                data = trial()
                data["exception_info"] = {
                    "exception_type": exception_type, "exception_message": "SECRET_API_KEY",
                    "exception_traceback": "SECRET_TRACEBACK",
                }
                report = self.report_one(data)
                item = report["trials"][0]
                self.assertEqual(item["classification"], "infrastructure_error")
                self.assertNotIn("SECRET", json.dumps(report))

    def test_step_exception_overrides_reward_and_unfinished_status(self):
        data = trial(finished=False)
        data["step_results"] = [{"exception_info": {"exception_type": "RuntimeError"}}]
        self.assertEqual(self.report_one(data)["trials"][0]["classification"], "infrastructure_error")

    def test_unfinished_precedes_missing_reward(self):
        data = trial(finished=False)
        data["verifier_result"] = None
        self.assertEqual(self.report_one(data)["trials"][0]["classification"], "incomplete")

    def test_absent_and_nonbinary_rewards_are_invalid(self):
        for verifier_result in (None, {"rewards": {}}, {"rewards": {"reward": None}},
                                {"rewards": {"reward": True}}, {"rewards": {"reward": -1}},
                                {"rewards": {"reward": 0.5}}, {"rewards": {"reward": "0"}},
                                {"rewards": {"reward": 10 ** 400}}):
            with self.subTest(verifier_result=verifier_result):
                data = trial()
                data["verifier_result"] = verifier_result
                self.assertEqual(self.report_one(data)["trials"][0]["classification"], "invalid_result")

    def test_completed_model_zero_still_requires_trajectory_review(self):
        report = self.report_one(trial())
        self.assertEqual(report["trials"][0]["classification"], "zero_reward_requires_trajectory_review")
        self.assertEqual(report["trials"][0]["analysis_status"], "pending")
        self.assertEqual(report["requirements_status"], "not_assessed")
        self.assertEqual(report["observations"][0]["count"], 1)
        self.assertNotIn("genuine_model_failure", json.dumps(report))

    def test_successful_standard_agent_is_solved(self):
        item = self.report_one(trial(reward=1.0))["trials"][0]
        self.assertEqual(item["classification"], "solved")
        self.assertEqual(item["analysis_status"], "pending")

    def test_oracle_and_nop_use_expected_binary_rewards(self):
        for agent, reward, expected in (("oracle", 1, "oracle_pass"), ("oracle", 0, "oracle_failed"),
                                        ("nop", 0, "nop_pass"), ("nop", 1, "nop_failed")):
            with self.subTest(agent=agent, reward=reward):
                self.assertEqual(self.report_one(trial(agent, reward))["trials"][0]["classification"], expected)

    def test_nop_missing_deliverable_test_failure_is_valid_zero_without_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = self.write_trial(root, trial("nop", 0))
            (folder / "verifier/test-stdout.txt").write_text("FAILED: required artifact missing", encoding="utf-8")
            (folder / "verifier/reward.txt").write_text("0\n", encoding="utf-8")
            self.assertEqual(self.reporter().build_report([root])["trials"][0]["classification"], "nop_pass")

    def test_missing_ctrf_is_evidence_missing_not_a_pass(self):
        for agent, reward in (("oracle", 1), ("nop", 0), ("codex", 1)):
            with self.subTest(agent=agent):
                item = self.report_one(trial(agent, reward), ctrf=False)["trials"][0]
                self.assertEqual(item["classification"], "evidence_missing")
                self.assertIn("ctrf", item["missing_evidence"])

    def test_discovery_skips_aggregates_deduplicates_roots_and_whitelists_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / "job"
            data = trial(reward=1)
            data.update(config={"env": {"API_KEY": "SECRET_CONFIG"}}, env={"SECRET_ENV": "x"},
                        agent_result={"text": "SECRET_AGENT_TEXT"}, unexpected="SECRET_EXTRA")
            data["agent_info"]["env"] = "SECRET_NESTED_ENV"
            data["agent_info"]["model_info"]["api_key"] = "SECRET_MODEL_KEY"
            data["agent_execution"]["config"] = "SECRET_TIME_CONFIG"
            folder = self.write_trial(job, data)
            (job / "result.json").write_text(json.dumps({"stats": {}, "config": "SECRET_JOB_CONFIG"}), encoding="utf-8")
            report = self.reporter().build_report([root, job])
            self.assertEqual(len(report["trials"]), 1)
            item = report["trials"][0]
            self.assertEqual(item["agent"], "codex")
            self.assertEqual(item["agent_version"], "1.2.3")
            self.assertEqual(item["model"], "provider/model")
            self.assertEqual(item["task_checksum"], "abc123")
            self.assertEqual(item["times"]["agent_execution"], trial()["agent_execution"])
            self.assertEqual(item["paths"]["result"], str((folder / "result.json").resolve()))
            self.assertNotIn("SECRET", json.dumps(report))

    def test_result_files_inside_trial_evidence_are_never_counted_as_trials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = self.write_trial(root, trial())
            for evidence in ("agent", "artifacts", "verifier", "steps"):
                self.write_trial(folder, trial("oracle", 1), name=evidence)
            report = self.reporter().build_report([root, folder / "agent"])
            self.assertEqual(len(report["trials"]), 1)
            self.assertEqual(report["trials"][0]["classification"], "zero_reward_requires_trajectory_review")

    def test_malformed_selected_fields_cannot_abort_other_trial_reporting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = trial()
            data["agent_info"]["model_info"] = "SECRET_INVALID_MODEL_INFO"
            self.write_trial(root, data, name="bad")
            self.write_trial(root, trial("oracle", 1), name="good")
            report = self.reporter().build_report([root])
            self.assertEqual(len(report["trials"]), 2)
            self.assertEqual(report["trials"][0]["classification"], "invalid_result")
            self.assertEqual(report["trials"][1]["classification"], "oracle_pass")
            self.assertNotIn("SECRET", json.dumps(report))

    def test_empty_jobs_do_not_claim_requirements_are_met(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.reporter().build_report([Path(directory)])
            self.assertEqual(report["trials"], [])
            self.assertEqual(report["observations"], [])
            self.assertEqual(report["requirements_status"], "not_assessed")

    def test_cli_stdout_and_output_file_contain_equivalent_json(self):
        self.reporter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_trial(root / "job", trial())
            command = [sys.executable, str(SCRIPT), str(root / "job")]
            stdout = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(stdout.returncode, 0, stdout.stderr)
            output = root / "report.json"
            saved = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
            self.assertEqual(saved.returncode, 0, saved.stderr)
            self.assertEqual(json.loads(stdout.stdout), json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
