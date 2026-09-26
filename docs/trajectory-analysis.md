# Local trajectory analysis

`evaluation/analyze_trials.py` runs the installed, pinned Harbor `analyze` workflow against a completed local trial or job. It explicitly supplies the pinned upstream `docs/prompts/trial-analysis.toml`; the built-in two-criterion default is not used. The six criteria are task specification, reward hacking, difficulty crux, near miss, refusals, and low timeout.

The selected analyzer is `codex / openai/gpt-6-astra / xhigh`. This replaces the upstream default Claude analyzer; upstream documents `analyze_agent` and `analyze_model` overrides. This review does not change which models solved the benchmark or their rewards.

In WSL, with the project runtime active:

```bash
project_root=/mnt/e/JOB/klavis-terminal-bench
source "$project_root/artifacts/environment/runtime-env.sh"
export CODEX_AUTH_JSON_PATH=/mnt/c/Users/MSN/.codex/auth.json
# Prepare and validate without invoking a model:
python "$project_root/evaluation/analyze_trials.py" /absolute/path/to/completed/job --prepare-only
# Invoke the analyzer:
python "$project_root/evaluation/analyze_trials.py" /absolute/path/to/completed/job
```

Only paths under this project's `artifacts/jobs` are accepted, and a completed `result.json` is required. The wrapper records the exact command, rubric hash, criteria, and reviewer deviation in ignored `artifacts/local/analysis-invocations`. Analysis jobs go to `artifacts/local/analysis-jobs`, separate from benchmark results. Harbor also writes analysis records alongside the original trials. It does not publish to any service.

The base config disables job-level retries and multiplies **setup time only** by five, giving the default 360-second Codex installation stage 1800 seconds. The analyzer's own task execution settings are otherwise Harbor defaults; this does not change the original benchmark's 7200-second solve limit. Harbor analyze reconstructs its agent list, so an agent-level override in a base config would be discarded; the job-level setup multiplier is intentional.

Read every criterion and its explanation. Reward 1 on an analysis job means a valid analysis artifact was produced, not that the original task satisfies the assignment. Confirm failures against the original trajectory, verifier output, and declared protocol; infrastructure failures and refusals do not establish task difficulty.

Source: [pinned analysis options](https://github.com/harbor-framework/terminal-bench/blob/4def1f367467b34b18e0dbdc086400ba71c3e037/docs/TASK_REVIEW_AUTOMATION.md#overriding-defaults).
