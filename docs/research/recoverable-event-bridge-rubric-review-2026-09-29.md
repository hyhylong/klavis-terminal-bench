# Recoverable event bridge rubric review (2026-09-29)

This record covers the final local candidate after the rubric hardening pass.

## Candidate identity

- Source commit: `a9b4d970bf9ce32d612f56d9c4ea10404492a0c2`
- Frozen candidate: `artifacts/local/frozen/recoverable-event-bridge-20260928T192349565127Z/recoverable-event-bridge`
- Harbor task checksum: `510db0ac8c1a0b656b88a578143684c2045ebf295a470613d2eeb6910eb4c92f`

The review was run against this frozen candidate. Results from earlier
checksums were not reused.

## Static and verifier checks

- `scripts/check_static.py`: **25/25 passed** (`artifacts/static/recoverable-event-bridge-rubric-fix-7`)
- Oracle job: `artifacts/jobs/recoverable-event-bridge-rubricfix-oracle-20260929T053000000000Z`
  - reward **1.0**, exceptions **0**
  - CTRF: **17 tests, 17 passed, 0 failed**
- Nop job: `artifacts/jobs/recoverable-event-bridge-rubricfix-nop-20260929T053000000000Z`
  - reward **0.0**, exceptions **0**
  - CTRF: startup submission failure, **1 failed**

## Codex rubric review

The reviewer configuration used `codex / openai / gpt-6-sol / xhigh`:

- Job: `artifacts/jobs/implementation-review-codex-20260929T060000000000Z`
- Verdicts: `34 pass`, `1 not_applicable` (`artifact_efficiency`), `0 fail`
- Review reward: **1.0**, exceptions **0**
- Verdict file: `review-task__hsLmYSb/artifacts/app/verdicts.json`

The nine requested criteria all passed: `verifiable`, `difficult`,
`test_instruction_alignment`, `structured_data_schema`,
`difficulty_explanation_quality`, `verification_explanation_quality`,
`task_readme`, `verifier_execution_isolation`, and `ctrf_reporting`.

## Hardening changes

The prior review identified two documentation-contract gaps. The final pass
now states that `checkpoint.json` and `manifest.json` use compact sorted-key
JSON followed by exactly one newline, matching the byte assertions. It also
records the memory calibration: the bounded reference scanner passed at 96,
128, and 160 MiB; materializing the 192 MiB sparse segment raised
`MemoryError` at 160 and 192 MiB and succeeded at 256 MiB.

## Standard and adversarial trials

All model trials below use the same Harbor task checksum
`510db0ac8c1a0b656b88a578143684c2045ebf295a470613d2eeb6910eb4c92f`.
Infrastructure errors are excluded; every listed trial completed with
`exception_info: null`.

- Codex `openai/gpt-6-sol`, `xhigh`, standard `/run`: **3/3 reward 0.0**.
  Job: `artifacts/jobs/standard-codex-20260929T013342796857Z`.
- Codex `openai/gpt-6-sol`, `xhigh`, adversarial `/cheat`: **1/1 reward 0.0**.
  Job: `artifacts/jobs/cheat-codex-20260929T013518724775Z`.
- DeepSeek `deepseek/deepseek-flash`, `max`, standard `/run`: **3/3 reward 0.0**.
  Job: `artifacts/jobs/standard-deepseek-20260928T194006663196Z`.
- DeepSeek `deepseek/deepseek-flash`, `max`, adversarial `/cheat`: **1/1 reward 0.0**.
  Job: `artifacts/jobs/cheat-deepseek-20260929T014217870892Z`.

This is the disclosed Codex plus DeepSeek substitution pair. The four jobs
provide the required standard failures and adversarial zero rewards for the
same frozen task; they do not reuse results from another checksum.
