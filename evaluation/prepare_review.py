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
CODEX_RELEASE = {
    "version": "0.157.1",
    "url": "https://registry.npmjs.org/@openai/codex/-/codex-0.157.1-linux-x64.tgz",
    "sha256": "7f12677740f439fe4884c7031d9d703e571cecf5ea9fa3a05abd1bbccc2162a8",
    "platform": "linux-x64",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def task_files(task, *, exclude_caches=True):
    """Inventory task files, optionally excluding documented local Python caches."""
    result = {}
    for path in sorted(task.rglob("*")):
        relative = path.relative_to(task)
        if exclude_caches and (any(part in SKIPPED_DIRS for part in relative.parts)
                               or path.suffix == ".pyc"):
            continue
        if path.is_symlink():
            raise ValueError(f"Task snapshots do not follow symlinks: {relative}")
        if path.is_file():
            result[relative.as_posix()] = sha256(path)
    return result


def validate_review_source(task):
    """Allow a normal task or verify every byte of one of our frozen candidates."""
    task = Path(task).resolve()
    if task.parent == (ROOT / "tasks").resolve():
        return None
    frozen_root = (ROOT / "artifacts/local/frozen").resolve()
    try:
        relative = task.relative_to(frozen_root)
    except ValueError:
        raise ValueError("Review a direct tasks child or a verified local frozen candidate") from None
    if len(relative.parts) != 2 or not task.is_dir():
        raise ValueError("Frozen candidates must have the layout frozen/<container>/<task>")
    manifest_path = task.parent / "source-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Frozen candidate requires a regular sibling source-manifest.json")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (type(manifest) is not dict or manifest.get("source") != f"tasks/{task.name}"
            or type(manifest.get("files")) is not list):
        raise ValueError("Frozen manifest does not describe this task")
    declared = {}
    for item in manifest["files"]:
        if (type(item) is not dict or set(item) != {"path", "bytes", "sha256"}
                or type(item["path"]) is not str or type(item["bytes"]) is not int
                or item["bytes"] < 0 or type(item["sha256"]) is not str
                or item["path"] in declared):
            raise ValueError("Frozen manifest has an invalid or duplicate file entry")
        declared[item["path"]] = item
    actual = {}
    for path in task.rglob("*"):
        if path.is_symlink():
            raise ValueError("Frozen candidates must not contain symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Frozen candidates must contain only regular files")
        actual[path.relative_to(task).as_posix()] = path
    if set(actual) != set(declared):
        raise ValueError("Frozen candidate file inventory differs from its manifest")
    tree = hashlib.sha256()
    for name in sorted(actual):
        data = actual[name].read_bytes()
        entry = declared[name]
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Frozen candidate file differs from its manifest: {name}")
        tree.update(name.encode("utf-8") + b"\0" + data + b"\0")
    if tree.hexdigest() != manifest.get("snapshot_tree_sha256"):
        raise ValueError("Frozen candidate tree checksum differs from its manifest")
    return {"manifest_path": str(manifest_path),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "snapshot_tree_sha256": tree.hexdigest()}


def create_native_review_parent(label):
    """Reserve a fresh review directory under the native Linux home state tree."""
    parent = Path.home() / ".local/state/klavis-terminal-bench/reviews" / label
    for component in (parent, *parent.parents):
        if component.is_symlink():
            raise ValueError(f"Native review staging must not follow symlinks: {component}")
    parent.mkdir(parents=True, exist_ok=False)
    return parent


def review_runtime(cached_python_base=False):
    """Select the disclosed review runtime without changing the reviewed task."""
    if cached_python_base:
        return {
            "base_image": "python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26",
            "apt_packages": ["ca-certificates", "curl", "git", "procps"],
            "cached_python_base": True,
        }
    return {
        "base_image": "ubuntu:24.04",
        "apt_packages": ["ca-certificates", "curl", "git", "nodejs", "npm", "procps", "python3"],
        "cached_python_base": False,
    }


def review_dockerfile(runtime, *, preinstalled_codex=False):
    """Prepare portable CLI assets from the public, checksum-pinned release."""
    base = runtime["base_image"]
    packages = list(runtime["apt_packages"])
    prefix, install = "", ""
    if preinstalled_codex:
        packages = [package for package in packages if package not in {"nodejs", "npm"}]
        prefix = (
            f"FROM {base} AS codex-assets\n"
            f"ADD --checksum=sha256:{CODEX_RELEASE['sha256']} {CODEX_RELEASE['url']} /tmp/codex.tgz\n"
            "RUN tar -xzf /tmp/codex.tgz -C /tmp && "
            "mv /tmp/package/vendor/x86_64-unknown-linux-musl /opt/codex\n"
        )
        install = (
            "COPY --from=codex-assets /opt/codex /opt/codex\n"
            "RUN ln -s /opt/codex/bin/codex /usr/local/bin/codex && "
            "ln -s /opt/codex/codex-path/rg /usr/local/bin/rg && "
            f'test "$(codex --version)" = "codex-cli {CODEX_RELEASE["version"]}" && rg --version\n'
        )
    return (
        prefix + f"FROM {base}\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends "
        f"{' '.join(packages)} && rm -rf /var/lib/apt/lists/*\n"
        + install + "COPY task-under-review /app/task-under-review\n"
        "COPY rubric.toml /app/rubric.toml\nWORKDIR /app\n"
    )


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


def prepare(task=DEFAULT_TASK, *, native_stage=False, cached_python_base=False,
            preinstalled_codex=False):
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
    source_freeze = validate_review_source(task)
    Task(task)  # Validate the actual source task before copying it.
    exclude_caches = source_freeze is None
    inventory = task_files(task, exclude_caches=exclude_caches)
    source_checksum = dirhash(task, "sha256")
    excluded = sorted(path.relative_to(task).as_posix() for path in task.rglob("*")
                      if path.is_file() and path.relative_to(task).as_posix() not in inventory)
    rubric = tomllib.loads((UPSTREAM / RUBRIC).read_text(encoding="utf-8"))
    criteria = [criterion["name"] for criterion in rubric["criteria"]]
    if len(criteria) != 35 or len(set(criteria)) != 35:
        raise ValueError("The pinned implementation rubric must contain exactly 35 unique criteria")

    label = "implementation-review-codex-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = (ROOT / "artifacts/local/review" / label).resolve()
    staging_parent = create_native_review_parent(label) if native_stage else destination
    destination.mkdir(parents=True, exist_ok=False)
    review_task = staging_parent / "review-task"

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
    if (task_files(task, exclude_caches=exclude_caches) != inventory
            or task_files(snapshot, exclude_caches=exclude_caches) != inventory
            or dirhash(task, "sha256") != source_checksum
            or validate_review_source(task) != source_freeze):
        raise RuntimeError("Task files changed during preparation; discard this snapshot and prepare again")
    shutil.copyfile(UPSTREAM / RUBRIC, environment / "rubric.toml")
    runtime = review_runtime(cached_python_base)
    if preinstalled_codex:
        runtime["codex_release"] = dict(CODEX_RELEASE)
        runtime["apt_packages"] = [package for package in runtime["apt_packages"]
                                   if package not in {"nodejs", "npm"}]
    (environment / "Dockerfile").write_text(
        review_dockerfile(runtime, preinstalled_codex=preinstalled_codex),
        encoding="utf-8", newline="\n",
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
    if native_stage:
        for path in (review_task, *review_task.parents, *review_task.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Native review staging contains a symlink: {path}")

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
        "review_runtime": runtime,
        "staging": {"native_linux": native_stage, "review_task": str(review_task),
                    "metadata_directory": str(destination)},
        "source_freeze": source_freeze,
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
            ("Review the verified frozen local candidate rather than fetch a published task repository"
             if source_freeze else
             "Review the local working-tree snapshot rather than fetch a published task repository"),
            "Use Codex instead of the upstream default Claude reviewer; omit its baked Claude CLI",
            "Use public network for reviewer setup and model access",
            "Allow 1800 seconds for agent setup and independently 7200 seconds for review execution",
            ("Preserve the complete verified frozen candidate file inventory"
             if source_freeze else
             "Exclude .git, __pycache__, .pytest_cache directories and .pyc files from the snapshot"),
        ],
        "reward_meaning": "Upstream verifier only checks a nonempty verdict artifact; inspect all 35 outcomes",
        "acceptance_status": "not_assessed",
    }
    if native_stage:
        manifest["adaptations"].append(
            "Stage the review task and Docker context in the native Linux home state directory "
            "to avoid detached DrvFS working directories; keep config and manifest in repository artifacts"
        )
    if cached_python_base:
        manifest["adaptations"].append(
            "Use the pinned locally cached Python 3.13 slim-bookworm image for the review runtime "
            "instead of Ubuntu; Python is supplied by the base. "
            "The task-under-review bytes, rubric and reviewer model are unchanged"
        )
    if preinstalled_codex:
        manifest["adaptations"].append(
            "Preinstall the official standalone linux-x64 Codex 0.157.1 release and bundled ripgrep "
            "using a pinned archive SHA-256; Harbor detects the CLI and skips its Node/npm setup. "
            "No credentials or agent container state are included in this image"
        )
    config = destination / "config.json"
    config.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, default=DEFAULT_TASK)
    parser.add_argument("--native-stage", action="store_true",
                        help="Stage the review Docker context under the native Linux home state directory")
    parser.add_argument("--cached-python-base", action="store_true",
                        help="Use the pinned locally cached Python 3.13 slim-bookworm review runtime")
    parser.add_argument("--preinstalled-codex", action="store_true",
                        help="Preinstall the checksum-pinned official standalone Codex 0.157.1 CLI")
    args = parser.parse_args()
    print(prepare(args.task, native_stage=args.native_stage,
                  cached_python_base=args.cached_python_base,
                  preinstalled_codex=args.preinstalled_codex))
