"""Prepare a disclosed local Codex rubric review; never launch an agent or API."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / ".cache/upstream"
UPSTREAM_COMMIT = "4def1f367467b34b18e0dbdc086400ba71c3e037"
HARBOR_VERSION = "0.23.1.dev202609170426"
STAGE = "scripts/review/stage_task.py"
INSTRUCTION = "scripts/rubric-regression/templates/instruction.md"
RUBRIC = "docs/prompts/task-implementation.toml"
DEFAULT_TASK = ROOT / "tasks/temporal-ledger-repair"
SKIPPED_DIRS = {".git", "__pycache__", ".pytest_cache"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def task_files(task):
    """Inventory submission files while excluding documented local Python caches."""
    result = {}
    for path in sorted(task.rglob("*")):
        relative = path.relative_to(task)
        if any(part in SKIPPED_DIRS for part in relative.parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"Task snapshots do not follow symlinks: {relative}")
        if path.is_file():
            result[relative.as_posix()] = sha256(path)
    return result


def pinned_sources():
    """Verify source provenance locally; git show never fetches anything."""
    revision = subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True,
    ).strip()
    if revision != UPSTREAM_COMMIT:
        raise ValueError(f"Expected upstream commit {UPSTREAM_COMMIT}; found {revision}")
    for relative in (STAGE, INSTRUCTION, RUBRIC):
        original = subprocess.check_output(
            ["git", "-C", str(UPSTREAM), "show", f"{UPSTREAM_COMMIT}:{relative}"],
        ).decode("utf-8").replace("\r\n", "\n")
        if (UPSTREAM / relative).read_text(encoding="utf-8") != original:
            raise ValueError(f"Pinned review source has local modifications: {relative}")


def prepare(task=DEFAULT_TASK):
    """Write a new immutable snapshot/config and return its absolute config path."""
    if sys.platform != "linux":
        raise RuntimeError("Run this preparation script with the pinned Linux/WSL Harbor Python")
    installed = importlib.metadata.version("harbor")
    if installed != HARBOR_VERSION:
        raise RuntimeError(f"Expected Harbor {HARBOR_VERSION}; found {installed}")
    from harbor.models.job.config import JobConfig
    from harbor.models.task.task import Task
    from dirhash import dirhash

    pinned_sources()
    task = Path(task).resolve()
    if task.parent != (ROOT / "tasks").resolve():
        raise ValueError("The reviewed task must be directly under this project's tasks directory")
    Task(task)  # Validate the actual source task before copying it.
    inventory = task_files(task)
    source_checksum = dirhash(task, "sha256")
    excluded = sorted(path.relative_to(task).as_posix() for path in task.rglob("*")
                      if path.is_file() and path.relative_to(task).as_posix() not in inventory)
    rubric = tomllib.loads((UPSTREAM / RUBRIC).read_text(encoding="utf-8"))
    criteria = [criterion["name"] for criterion in rubric["criteria"]]
    if len(criteria) != 35 or len(set(criteria)) != 35:
        raise ValueError("The pinned implementation rubric must contain exactly 35 unique criteria")

    label = "implementation-review-codex-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = (ROOT / "artifacts/local/review" / label).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    review_task = destination / "review-task"

    spec = importlib.util.spec_from_file_location("pinned_review_stage", UPSTREAM / STAGE)
    stage = importlib.util.module_from_spec(spec)
    previous_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(stage)
    finally:
        sys.dont_write_bytecode = previous_bytecode
    # These identify the real staging-script provenance, not the local task's
    # origin. Its unbuilt remote-fetch Dockerfile is replaced immediately below.
    stage.stage_task("harbor-framework/terminal-bench", UPSTREAM_COMMIT,
                     f"tasks/{task.name}", review_task)

    environment = review_task / "environment"
    snapshot = environment / "task-under-review" / task.name
    for relative in inventory:
        copied = snapshot / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(task / relative, copied)
    if (task_files(task) != inventory or task_files(snapshot) != inventory
            or dirhash(task, "sha256") != source_checksum):
        raise RuntimeError("Task files changed during preparation; discard this snapshot and prepare again")
    shutil.copyfile(UPSTREAM / RUBRIC, environment / "rubric.toml")
    (environment / "Dockerfile").write_text(
        "FROM ubuntu:24.04\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends "
        "ca-certificates curl git nodejs npm procps python3 "
        "&& rm -rf /var/lib/apt/lists/*\n"
        "COPY task-under-review /app/task-under-review\n"
        "COPY rubric.toml /app/rubric.toml\n"
        "WORKDIR /app\n", encoding="utf-8", newline="\n",
    )
    (review_task / "task.toml").write_text(
        'schema_version = "1.0"\n'
        'artifacts = ["/app/verdicts.json"]\n\n'
        "[agent]\ntimeout_sec = 7200.0\n\n"
        '[environment]\nnetwork_mode = "public"\nbuild_timeout_sec = 1800.0\n',
        encoding="utf-8", newline="\n",
    )
    # Preserve the staged instruction/verifier text but ensure Unix shell bytes.
    for relative in ("instruction.md", "tests/test.sh"):
        path = review_task / relative
        path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

    payload = {
        "job_name": label, "jobs_dir": str((ROOT / "artifacts/jobs").resolve()),
        "n_attempts": 1, "n_concurrent_trials": 1, "retry": {"max_retries": 0},
        "environment": {"type": "docker"},
        "tasks": [{"path": str(review_task)}],
        "agents": [{"name": "codex", "model_name": "openai/gpt-6-astra",
                    "override_setup_timeout_sec": 1800.0,
                    "kwargs": {"reasoning_effort": "xhigh"}}],
    }
    validated = JobConfig.model_validate(payload)
    if validated.agents[0].override_setup_timeout_sec != 1800.0:
        raise RuntimeError("Installed Harbor did not retain the setup timeout override")
    Task(review_task)
    Task(snapshot)
    manifest = {
        "schema_version": 1, "kind": "alternate_local_implementation_review",
        "status": "prepared_not_run", "upstream_commit": UPSTREAM_COMMIT,
        "harbor_version": installed, "source_task": str(task),
        "source_task_checksum_at_prepare": source_checksum,
        "snapshot_task": str(snapshot), "reviewed_task_checksum": dirhash(snapshot, "sha256"),
        "review_task_checksum": dirhash(review_task, "sha256"),
        "checksum_algorithm": "dirhash sha256, matching Harbor TrialResult.task_checksum; not TrialLock.task.digest",
        "excluded_source_files": excluded,
        "reviewer": "codex/openai/gpt-6-astra/xhigh",
        "upstream_default_reviewer": "claude-code/anthropic/claude-sonnet-5",
        "criteria": criteria, "criterion_count": len(criteria),
        "pinned_source_sha256": {relative: sha256(UPSTREAM / relative)
                                 for relative in (STAGE, INSTRUCTION, RUBRIC)},
        "staged_instruction_sha256": sha256(review_task / "instruction.md"),
        "reviewed_files_sha256": inventory,
        "adaptations": [
            "Review the local working-tree snapshot rather than fetch a published task repository",
            "Use Codex instead of the upstream default Claude reviewer; omit its baked Claude CLI",
            "Use public network for reviewer setup and model access",
            "Allow 1800 seconds for agent setup and independently 7200 seconds for review execution",
            "Exclude .git, __pycache__, .pytest_cache directories and .pyc files from the snapshot",
        ],
        "reward_meaning": "Upstream verifier only checks a nonempty verdict artifact; inspect all 35 outcomes",
        "acceptance_status": "not_assessed",
    }
    config = destination / "config.json"
    config.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, default=DEFAULT_TASK)
    print(prepare(parser.parse_args().task))
