# Recoverable Event Bridge: frozen rubric review

This record covers the frozen task at
`artifacts/local/frozen/recoverable-event-bridge-20260928T121420537912Z/recoverable-event-bridge`.
The reviewed Harbor task checksum is
`1f8158452f13828f4ff8bb1bbde089eed6942cfd6df096b2575e59ccac583add`.

The local implementation review used Codex `openai/gpt-6-sol` with
`reasoning_effort=xhigh`, as the disclosed local alternate to the upstream
Claude reviewer. The review job is
`artifacts/jobs/implementation-review-codex-20260928T125617786751Z`; its
verdict is in
`review-task__XBSDLhz/artifacts/app/verdicts.json`. The reviewer completed
without an exception and produced all 35 criterion outcomes.

Results: **25 pass, 9 fail, 1 not applicable**. A reward of 1.0 for this job
only means that the verdict artifact was produced; it is not an all-pass
result.

The failed criteria are:

- `verifiable`: the independent reference stops at a truncated frame instead
  of exercising the contract's search for a later `EVB1` frame.
- `difficult`: the task remains a standard parser and in-memory replay problem
  whose restart path rescans the stream.
- `test_instruction_alignment`: the truncated-frame recovery is not covered,
  and the verifier's exact checkpoint schema is stricter than the contract.
- `structured_data_schema`: the exact checkpoint key set is not documented.
- `difficulty_explanation_quality`: the README does not assess synthetic data
  realism or identify the professional role for the task.
- `verification_explanation_quality` and `task_readme`: the README claims
  process-group cleanup after normal execution, while the harness only kills
  the group on timeout.
- `verifier_execution_isolation`: a normally exiting process can leave a
  background child alive because the group is not always killed.
- `ctrf_reporting`: the missing-artifact branch writes reward 0 without a
  CTRF report.

The same frozen directory was used for fresh controls:

- Oracle: `artifacts/jobs/recoverable-event-bridge-frozen-review-oracle-20260928`,
  reward `1.0`, zero exceptions.
- Nop: `artifacts/jobs/recoverable-event-bridge-frozen-review-nop-20260928`,
  reward `0.0`, zero exceptions.

No task files were changed after this freeze. The `difficult` redesign remains
paused by request; the other failures are documented as follow-up work rather
than being represented as passed.
