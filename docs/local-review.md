# Local implementation review

This setup runs the pinned implementation rubric with `codex / openai/gpt-6-astra / xhigh` as a disclosed alternate local reviewer. Upstream's default is `claude-code / anthropic/claude-sonnet-5`. It is not an unchanged hosted `/review` run, maintainer approval, or a guarantee of assignment acceptance.

Preparation uses the pinned `scripts/review/stage_task.py` and its exact instruction template, embeds all 35 criteria, and copies a snapshot of the chosen task into `/app/task-under-review/<task-name>`. The generated remote-fetch Dockerfile is replaced with a local `COPY` build; it neither publishes the task nor fetches a task repository. Normal working-tree preparation excludes documented caches; a verified frozen candidate retains its entire manifest inventory. Every reviewed file is hashed. The manifest records the pinned source hashes, snapshot checksum, reviewer model, and all local adaptations.

From PowerShell, set the Linux path of the final frozen candidate and prepare without starting Docker, a model, or an API call. Replace `CANDIDATE` with its actual freeze directory:

```powershell
$reviewCandidate = '/mnt/e/JOB/klavis-terminal-bench/artifacts/local/frozen/CANDIDATE/durable-ledger-repair'
wsl.exe -d Ubuntu-22.04 --cd /tmp --exec /root/.local/share/klavis-terminal-bench/runtime/venv/bin/python -B /mnt/e/JOB/klavis-terminal-bench/evaluation/prepare_review.py --task $reviewCandidate --native-stage --cached-python-base --preinstalled-codex
```

`--native-stage` places the review task and Docker context under `$HOME/.local/state/klavis-terminal-bench/reviews/<label>/review-task`; config and manifest remain in repository artifacts. It rejects symlinks and refuses to reuse an existing stage. This avoids the detached DrvFS working-directory failure seen while preparing Docker builds. Without the flag, staging remains under repository artifacts.

`--cached-python-base` selects the locally cached image `python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26` in place of the default `ubuntu:24.04` review runtime. APT installs only `ca-certificates curl git procps`; Python is already in the base. The manifest records the exact base image, packages, and adaptation. These options change the review runtime and staging only: the task-under-review bytes, all 35 rubric criteria, and reviewer model settings remain unchanged.

`--preinstalled-codex` adds the official standalone linux-x64 Codex 0.157.1 release and its bundled ripgrep, preserving the whole platform directory. The Dockerfile downloads the public npm archive with SHA-256 `7f12677740f439fe4884c7031d9d703e571cecf5ea9fa3a05abd1bbccc2162a8` and checks the CLI version. Harbor detects the existing binary and skips its Node/npm dependency installation. The release URL, hash, version and platform are recorded in the manifest. Without this option Harbor performs its normal installation. This option requires an x86-64 Linux Docker host. The image includes no account credentials or state copied from an agent container.

The script validates the pinned Harbor version, source provenance, task schema, and job schema. It prints one absolute config path beneath ignored `artifacts/local/review/`. Each preparation produces a new snapshot, `config.json`, and `manifest.json`. A later task edit does not update an existing review snapshot; prepare again when the task changes. Compare the manifest's reviewed task checksum and file inventory with the intended final submission before interpreting a review.

The manifest distinguishes `source_task_checksum_at_prepare` (the original task tree used by normal trials), `reviewed_task_checksum` (the copied snapshot), and `review_task_checksum` (the enclosing review meta-task). These use the same `dirhash` SHA-256 algorithm as Harbor's `TrialResult.task_checksum`; they are not `TrialLock.task.digest`, which uses a different digest format. A frozen candidate must match its sibling source manifest's complete inventory, file sizes, file hashes and tree hash; `source_freeze` records that manifest's SHA-256 and tree hash. Its source and reviewed checksums match. For a normal working-tree task, source and snapshot checksums can differ because of the explicitly listed `excluded_source_files`. Every included source file is hash-checked against its snapshot copy. Preparation never deletes caches or changes the source task, including during ongoing trials.

When intentionally starting a model review, use the printed config path in WSL:

```bash
project_root=/mnt/e/JOB/klavis-terminal-bench
source "$project_root/artifacts/environment/runtime-env.sh"
export CODEX_AUTH_JSON_PATH=/mnt/c/Users/MSN/.codex/auth.json
bash "$project_root/scripts/preflight-models.sh" --provider codex
review_config=/absolute/path/printed/by/prepare_review.py
env_args=()
if [[ -f "$project_root/.env" ]]; then
  env_args=(--env-file "$project_root/.env")
fi
runtime_cwd="$HOME/.local/state/klavis-terminal-bench"
mkdir -p "$runtime_cwd"
cd "$runtime_cwd"
harbor run --config "$review_config" "${env_args[@]}"
```

Only the final `harbor run` command invokes the reviewer. Keep its working directory on the Linux filesystem because WSL drive remounts have detached existing `/mnt/e` cwd references. All task, config, and job paths are absolute. No hosted launcher or GitHub operation is used.

`agents[0].override_setup_timeout_sec = 1800` changes only setup time. The staged review task independently allows 7200 seconds of agent execution. One attempt runs with no retry; it is review evidence and does not count toward the standard or adversarial trial matrix.

The pinned review verifier only rewards the existence of a nonempty `/app/verdicts.json`. Reward 1 does **not** mean the task passed the rubric. Inspect the captured verdict artifact for exactly the manifest's 35 criterion names, valid `pass`/`fail`/`not_applicable` outcomes, and substantive explanations. Record failures and fix the task before reviewing a fresh snapshot. Neither preparation nor artifact existence establishes rubric success.

Retain the review job's result, trajectory, verdict artifact, manifest, config, and explanations. Report the actual model and this local adaptation alongside the findings. Credentials remain in ignored local configuration and must not be copied into published evidence. The general trial reporter expects CTRF from benchmark verifier runs; this upstream review meta-task uses an artifact-existence verifier without CTRF, so assess its result and verdicts separately.
