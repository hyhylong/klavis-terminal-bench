"""Run local Codex trajectory review with the six pinned upstream criteria.

This invokes a model unless --prepare-only is given. It does not publish results.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def prepare(source: Path) -> tuple[list[str], Path]:
    source = source.resolve(strict=True)
    if not source.is_relative_to((ROOT / "artifacts/jobs").resolve()):
        raise ValueError("Select a local trial or job under artifacts/jobs")
    result_path = source / "result.json"
    if not result_path.is_file():
        raise ValueError("No completed result.json at the selected path")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if not result.get("finished_at"):
        raise ValueError("Wait for the selected trial or job to finish")
    rubric = ROOT / ".cache/upstream/docs/prompts/trial-analysis.toml"
    from harbor.models.job.config import JobConfig
    config = ROOT / "evaluation/analysis-codex.json"
    base = JobConfig.model_validate_json(config.read_text())
    if base.agent_setup_timeout_multiplier != 5.0:
        raise ValueError("Unexpected analysis setup timeout multiplier")
    # Parse the exact source with the same loader Harbor analyze uses.
    from harbor.analyze.models import load_rubric
    criteria = load_rubric(rubric).criteria
    expected = {"task_specification", "reward_hacking", "difficulty_crux",
                "near_miss", "refusals", "low_timeout"}
    if {item.name for item in criteria} != expected:
        raise ValueError("Unexpected upstream analysis criteria")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    job_name = "analysis-codex-" + stamp
    jobs = ROOT / "artifacts/local/analysis-jobs"
    command = ["harbor", "analyze", str(source), "--agent", "codex", "--model",
               "openai/gpt-6-astra", "--ak", "reasoning_effort=xhigh", "--env", "docker",
               "--rubric", str(rubric), "--config", str(config), "--n-concurrent", "1",
               "--n-attempts", "1", "--jobs-dir", str(jobs), "--job-name", job_name]
    manifest_dir = ROOT / "artifacts/local/analysis-invocations"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_dir / f"{job_name}.json"
    manifest.write_text(json.dumps({
        "source": str(source), "command": command,
        "reviewer_deviation": "Codex replaces upstream default Claude analyzer",
        "rubric_sha256": hashlib.sha256(rubric.read_bytes()).hexdigest(),
        "criteria": sorted(expected),
    }, indent=2) + "\n", encoding="utf-8")
    return command, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    command, manifest = prepare(args.source)
    print(f"Analysis invocation: {manifest}", flush=True)
    if args.prepare_only:
        return 0
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    subprocess.run([sys.executable, str(ROOT / "evaluation/preflight.py"),
                    "--provider", "codex"], check=True)
    native_cwd = Path.home() / ".local/state/klavis-terminal-bench"
    native_cwd.mkdir(parents=True, exist_ok=True)
    os.chdir(native_cwd)
    os.execvp(command[0], command)


if __name__ == "__main__":
    raise SystemExit(main())
