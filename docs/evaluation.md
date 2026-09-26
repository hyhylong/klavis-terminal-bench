# Evaluation configuration and credential preflight

The checked-in configurations target Harbor `0.23.1.dev202609170426` and Terminal-Bench commit `4def1f367467b34b18e0dbdc086400ba71c3e037`. They have been validated without invoking any model. Results from later model runs belong in the evidence report; configuration validation is not benchmark success.

| Config under `evaluation/` | Agent | Actual model identifier | Reasoning | Attempts |
| --- | --- | --- | --- | --- |
| `standard-codex.json` | `codex` | `openai/gpt-6-astra` | `xhigh` | 3 |
| `cheat-codex.json` | `codex` | `openai/gpt-6-astra` | `xhigh` | 1 |
| `standard-deepseek.json` | `terminus-2` | `deepseek/deepseek-flash` | `max` | 3 |
| `cheat-deepseek.json` | `terminus-2` | `deepseek/deepseek-flash` | `max` | 1 |

Every config uses Docker, serial trials, zero job-level automatic retries, and the task's own timeouts. Failed API calls, timeouts, setup failures, and missing rewards are not genuine verifier failures.

Both Codex configs set the agent-level `override_setup_timeout_sec` to `1800`. This changes only the dependency installation/setup allowance: the initial Codex attempt exceeded Harbor's default 360 seconds while downloading Node.js/npm packages, before model invocation. The task's solve allowance remains 7200 seconds, with no solve-time override or multiplier. Model, reasoning effort, and attempt counts remain as shown above. DeepSeek's setup allowance is unchanged. Preserve the original setup failure as infrastructure evidence; it is not a model task failure.

## DeepSeek mapping and compatibility

DeepSeek's official [release notes](https://api-docs.deepseek.com/updates/) identify `deepseek-flash` as DeepSeek V4.1 Flash. The [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) supports `reasoning_effort: max`. The `deepseek/` prefix selects LiteLLM's native provider; the API receives `deepseek-flash` at `https://api.deepseek.com`.

The selected integration is Harbor's built-in Terminus 2 agent. It reads `DEEPSEEK_API_KEY` in the host process. The templates leave temperature and output limits at provider defaults and preserve reasoning across turns using `interleaved_thinking: true`.

An inspected compatibility issue in installed LiteLLM `1.102.1` matters: its DeepSeek adapter maps the ordinary `reasoning_effort` parameter to an enabled/disabled thinking flag and discards the effort value. The templates therefore also pass this through Harbor's supported `llm_call_kwargs`:

```json
{"extra_body": {"reasoning_effort": "max", "thinking": {"type": "enabled"}}}
```

The offline preflight intercepts LiteLLM's prepared HTTP body before network dispatch and verifies that the final model and effort remain `deepseek-flash` and `max`. A socket guard prohibits network access. This validates serialization; provider authentication and successful live multi-turn execution remain unverified until actual trials run. No older DeepSeek alias is silently substituted.

DeepSeek also documents [Codex Responses integration](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/), including a custom model catalog. That integration is not used by these templates. Terminus 2 is a disclosed replacement agent, so the replacement slot is not identical to the upstream Claude agent/model pairing. Any aggregate cost estimate from LiteLLM may use peak pricing; DeepSeek's billing is authoritative.

## Local preflight

In WSL:

```bash
cd /mnt/e/JOB/klavis-terminal-bench
bash scripts/preflight-models.sh --config-only
bash scripts/preflight-models.sh --provider codex
bash scripts/preflight-models.sh --provider deepseek
```

The default provider selection is `all`. Exit status `0` means the selected local prerequisites are present, `2` means a selected credential is missing, and `1` means configuration validation failed. The sanitized report is written to `artifacts/environment/model-preflight.json` and a provider-specific `model-preflight-<provider>.json`; no credential values are printed. Preflight performs no login, authentication request, balance check, model request, or container invocation. A present cache/key is explicitly reported as unvalidated; it does not establish session freshness, quota, or model entitlement.

Preflight parses the ignored project `.env` with `python-dotenv` and `override=False`. The launcher passes that file to Harbor's `--env-file` when present; it never shell-sources the file. The installed Harbor CLI loads an explicit env file with `override=True`, so keep credential variable values consistent if a value is also exported in the shell. Values are not written into generated configs or preflight reports.

The current machine has a Windows Codex auth cache. Select it explicitly from WSL:

```bash
export CODEX_AUTH_JSON_PATH=/mnt/c/Users/MSN/.codex/auth.json
bash scripts/preflight-models.sh --provider codex
```

The installed Harbor adapter checks `CODEX_AUTH_JSON_PATH` first, then `CODEX_FORCE_AUTH_JSON`, then `OPENAI_API_KEY`. Its forced-default path is Linux `~/.codex/auth.json`; setting host `CODEX_HOME` does not change that Harbor lookup. The adapter uploads the selected auth cache to temporary container storage and gives Codex an isolated `/tmp/codex-home`. It does not import the host's global `config.toml`, so the Windows CLI's unsupported global `ultra` setting is not inherited. Do not modify the global configuration to run these evaluations.

Preflight reads only the nonsecret `auth_mode` label from the chosen cache and never outputs its contents. The selected Windows cache reported `chatgpt` on 2026-09-26. OpenAI documents [file-based cached login and headless reuse](https://learn.chatgpt.com/docs/auth). If the selected cache is absent or stale, sign in using a suitable Codex CLI with a separate local configuration, or use an OpenAI API key; model access still requires verification.

DeepSeek requires an actual API key in the WSL process. A web account alone is not a configured API credential. To enter it without putting it in command history:

```bash
read -rsp 'DeepSeek API key: ' DEEPSEEK_API_KEY; printf '\n'
export DEEPSEEK_API_KEY
bash scripts/preflight-models.sh --provider deepseek
```

The initial shell preflight found no `DEEPSEEK_API_KEY`; the user subsequently supplied a key for the ignored local `.env`. Rerun preflight to check its current presence. Keep keys out of JSON configs and committed files. The launcher fails preflight if `OPENAI_BASE_URL` is set for the standard Codex slot; clear that override or review a deliberate custom endpoint separately.

## Run the evaluations

The following commands **invoke models** and consume account usage. Execute them only when running the actual evaluations:

```bash
cd /mnt/e/JOB/klavis-terminal-bench
export CODEX_AUTH_JSON_PATH=/mnt/c/Users/MSN/.codex/auth.json
bash evaluation/run.sh standard-codex
bash evaluation/run.sh cheat-codex
# Requires DEEPSEEK_API_KEY in this same WSL process:
bash evaluation/run.sh standard-deepseek
bash evaluation/run.sh cheat-deepseek
```

Each launcher performs local preflight and resolves a unique job config under `artifacts/local/evaluation/`. Both task and jobs paths become absolute, and the evidence directory is `/mnt/e/JOB/klavis-terminal-bench/artifacts/jobs`. Before starting Harbor, the launcher changes to the stable Linux directory `$HOME/.local/state/klavis-terminal-bench`. WSL DrvFS remounts were observed to detach a long-running process's existing working directory even while the repository remained accessible by its absolute path; Harbor then failed at `Path.cwd()`. The native Linux working directory and absolute paths avoid that failure mode. Use the launcher, not `harbor run -c` against a portable template directly.

To prepare and inspect an absolute config without invoking a model:

```bash
source artifacts/environment/runtime-env.sh
python evaluation/prepare_job.py standard-codex
```

The printed file can be run explicitly with `harbor run --config /absolute/path/to/generated.json` from a stable Linux working directory, passing `--env-file /absolute/path/to/.env` when needed. Config generation and preflight never embed credentials. Harbor installs the Codex CLI in its task container; its effective CLI version must be retained in each trial's trajectory. The upstream matrix does not pin a Codex CLI version.

## Exact adversarial prompt and unavailable review stages

Both cheat configs contain the complete upstream `docs/prompts/hack-trial-prompt.md` text in `extra_instructions`. `evaluation/hack-trial-prompt.md` preserves the text returned by the upstream launcher's `Path.read_text()` (LF-normalized); `manifest.json` records its SHA256 and upstream commit. Preflight checks both embedded strings against that copy. Harbor appends the extra instructions after the task instruction; the task's legitimate instruction file is not edited for cheat runs.

The current upstream trial slot replaced by DeepSeek is `claude-code / anthropic/claude-fable-5-1 / max`. Its implementation reviewer and trajectory analyzer are both `claude-code / anthropic/claude-sonnet-5`. Codex and DeepSeek accounts do not establish access to these reviewer models. Any local/manual or alternative-model review must be labeled as a substitution and cannot be claimed as an exact upstream reviewer/analysis pass. See the [pinned contract](upstream-contract.md) for acceptance criteria and required evidence.
