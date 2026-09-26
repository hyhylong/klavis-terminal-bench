# Local implementation review

This setup runs the pinned implementation rubric with `codex / openai/gpt-6-astra / xhigh` as a disclosed alternate local reviewer. Upstream's default is `claude-code / anthropic/claude-sonnet-5`. It is not an unchanged hosted `/review` run, maintainer approval, or a guarantee of assignment acceptance.

Preparation uses the pinned `scripts/review/stage_task.py` and its exact instruction template, embeds all 35 criteria, and copies a snapshot of the local task into `/app/task-under-review/temporal-ledger-repair`. The generated remote-fetch Dockerfile is replaced with a local `COPY` build; it neither publishes the task nor fetches a task repository. Python caches and Git metadata are excluded and every reviewed file is hashed. The manifest records the pinned source hashes, snapshot checksum, reviewer model, and all local adaptations.

From PowerShell, prepare without starting Docker, a model, or an API call:

```powershell
wsl.exe -d Ubuntu-22.04 -- /root/.local/share/klavis-terminal-bench/runtime/venv/bin/python /mnt/e/JOB/klavis-terminal-bench/evaluation/prepare_review.py
```

The script validates the pinned Harbor version, source provenance, task schema, and job schema. It prints one absolute config path beneath ignored `artifacts/local/review/`. Each preparation produces a new snapshot, `config.json`, and `manifest.json`. A later task edit does not update an existing review snapshot; prepare again when the task changes. Compare the manifest's reviewed task checksum and file inventory with the intended final submission before interpreting a review.

The manifest distinguishes `source_task_checksum_at_prepare` (the original task tree used by normal trials), `reviewed_task_checksum` (the cache-filtered snapshot), and `review_task_checksum` (the enclosing review meta-task). These use the same `dirhash` SHA-256 algorithm as Harbor's `TrialResult.task_checksum`; they are not `TrialLock.task.digest`, which uses a different digest format. The source and snapshot checksums can differ solely because of the explicitly listed `excluded_source_files`. In the current task, those exclusions are only interpreter caches: all task instructions, data, solution, tests, and metadata remain byte-identical. Every included source file is hash-checked against its snapshot copy. Preparation never deletes caches or changes the source task, including during ongoing trials.

When intentionally starting a model review, use the printed config path in WSL:

```bash
project_root=/mnt/e/JOB/klavis-terminal-bench
source "$project_root/artifacts/environment/runtime-env.sh"
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
