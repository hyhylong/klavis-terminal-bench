# Klavis Terminal-Bench Task

[English](README.md) | [简体中文](README.zh-CN.md)

This repository contains the final Terminal-Bench task for the Klavis AI coding assignment. The submitted task is `tasks/recoverable-event-bridge`, a recoverable event bridge that processes a segmented binary stream during a migration.

The task requires an agent to satisfy all of these constraints:

- incremental scanning, corruption recovery, and absolute offsets across segments
- transaction commits, duplicate delivery, aborts, cutover records, and sequence frontiers
- a private durable journal, checkpoint, and recovery after stop or failpoint interruption
- exact NDJSON, digest, count, and progress outputs
- execution inside a separate, unprivileged verifier under a 160 MiB address-space limit

## Final status

Final frozen Harbor task checksum:

`510db0ac8c1a0b656b88a578143684c2045ebf295a470613d2eeb6910eb4c92f`

The task tree matching this checksum is on the GitHub `main` branch. It passed 25/25 pinned static checks, received oracle reward `1.0` (17/17 verifier tests passed), and received nop reward `0.0`.

The implementation rubric was run with local Codex `gpt-6-sol/xhigh` as an explicitly disclosed alternate reviewer: 34 checks passed, 1 was `not_applicable` (`artifact_efficiency`), and 0 failed. This is local review evidence, not an upstream hosted review.

## Model trials

This submission uses the permitted Codex plus DeepSeek substitution pair. Every result below uses the same checksum; infrastructure errors are excluded from model-failure counts.

| Configuration | Standard `/run` | Adversarial `/cheat` |
| --- | --- | --- |
| Codex `openai/gpt-6-sol`, `xhigh` | 3/3 reward `0.0`, no exceptions | 1/1 reward `0.0`, no exceptions |
| DeepSeek `deepseek/deepseek-flash`, `max` | 3/3 reward `0.0`, no exceptions | 1/1 reward `0.0`, no exceptions |

DeepSeek is the permitted Claude-slot substitution; it is not identical to the upstream Claude configuration. Full job names, the checksum, and the failure analysis are in `docs/research/recoverable-event-bridge-rubric-review-2026-09-29.md`.

## Repository layout

- `tasks/recoverable-event-bridge/README.md`: task background, difficulty, reference solution, and verifier design.
- `tasks/recoverable-event-bridge/instruction.md`: the task instructions shown to an agent.
- `tasks/recoverable-event-bridge/environment/CONTRACT.md`: protocol, output format, and recovery semantics.
- `tasks/recoverable-event-bridge/solution/`: reference implementation used for oracle validation.
- `tasks/recoverable-event-bridge/tests/`: independent verifier, fixtures, and replay model.
- `docs/evaluation.md`: pinned Harbor version, configurations, commands, and credential boundaries.
- `docs/research/recoverable-event-bridge-rubric-review-2026-09-29.md`: final-checksum static, rubric, standard, and cheat evidence.

## Local verification

The following command runs the local static checks without calling a model:

```bash
cd /mnt/e/JOB/klavis-terminal-bench
source artifacts/environment/runtime-env.sh
python scripts/check_static.py --task tasks/recoverable-event-bridge
```

To run Harbor model trials, first follow `docs/evaluation.md` to configure local Codex or DeepSeek credentials, then use `evaluation/run.sh`. Credentials stay in ignored local configuration and must never be committed or written to logs.

## Design notes

1. Restoring output metrics is not enough to prove that data was recovered correctly. The verifier independently replays the stream and compares bytes, digests, and progress.
2. The private journal format is not prescribed. Only observable recovery behavior and the complete output contract are required.
3. Standard and adversarial trials must be interpreted against the same frozen checksum; results from different candidates must not be mixed.

No Terminal-Bench pull request is required. The GitHub repository is the assignment deliverable.
