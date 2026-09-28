# Recoverable event bridge local validation (2026-09-27)

## Validation gates

- Static checks: 24/25 under WSL. The only failure is `check-task-fields.sh`
  because the author name, email, and GitHub fields are intentionally still
  placeholders. No author identity was fabricated.
- Oracle: reward 1.0, no exceptions. Job:
  `artifacts/jobs/corrected-oracle2/2026-09-27__18-33-48`.
- Nop: reward 0.0, no exceptions. Job:
  `artifacts/jobs/corrected-nop/2026-09-27__18-34-27`.

## DeepSeek pilot

The corrected one-attempt pilot used `terminus-2` with
`deepseek/deepseek-flash` and completed successfully:

- Job directory: `artifacts/jobs/standard-deepseek-20260927T103533937104Z`.
- Reward: 1.0; exceptions: 0; tests: 7 passed, 0 failed, 0 skipped.
- Cost reported by Harbor: USD 0.531276084.
- The verifier checked the public replay, stop/restart, byte idempotence,
  read-only input, semantic hidden fixture, wire-corruption hidden fixture,
  and all hidden stop boundaries.

## Verifier correction history

The earlier pilot at
`artifacts/jobs/standard-deepseek-20260927T091606778911Z` initially reported
reward 0 because the hidden stop test required exit 75 even when the requested
stop point was exactly the final frame. The oracle legitimately returned 0 at
that boundary after producing a complete durable result, which the contract
allows. The test now requires 75 for early boundaries and accepts 0 or 75 for
the final boundary. The earlier extracted DeepSeek artifact also passes the
corrected hidden cases locally; its initial 0 must therefore not be counted as
a model failure.

This pilot establishes one successful DeepSeek solve. It does not establish the
three-failure requirement for the assignment, and Codex formal trials remain
blocked by the unavailable Codex quota. More independent normal attempts are
needed before claiming that this candidate is a valid low-accuracy task.

## Cheat trial

The one-attempt red-team run at
`artifacts/jobs/cheat-deepseek-20260927T111647328780Z` finished with reward
0.0 and no exceptions. Its public-only hardcoded artifact passed 4 public
tests, but failed both hidden fixtures and an intermediate stop boundary; the
CTRF summary is 4 passed, 3 failed, 0 skipped. This is the required evidence
that a visible-input shortcut does not pass the independent verifier.

## Cutover hardening

The candidate was then revised using the stateful mechanisms observed in
Terminal-Bench v3 migration and recovery tasks. The public contract now has a
`cutover` control record: it validates a canonical digest, advances an exact
tenant/stream sequence frontier without emitting an event, and participates in
the same `(commit_no, txn)` ordering as ordinary commits. Transactions cannot
mix commits and cutovers; repeated controls are idempotent, while conflicting
controls, stale frontiers, and bad digests are quarantined.

The independent replay, public builder, hidden fixtures, and solution were
updated together. The public fixture produces 13 accepted events and 7
quarantine records. The explicit hidden cutover fixture produces 9 accepted
events and 10 quarantine records, including same-number ordering,
commit-before-event delivery, duplicate controls, conflicting controls,
mixed operations, abort/retry, digest mismatch, and sequence gaps. The
candidate output matches the independent replay byte-for-byte at all hidden
stop/resume boundaries.

Fresh container controls for this revision are in
`artifacts/jobs/cutover-oracle` (reward 1.0, no exceptions) and
`artifacts/jobs/cutover-nop` (reward 0.0, no exceptions). The fresh red-team
DeepSeek run is
`artifacts/jobs/cheat-deepseek-20260927T132040411543Z`: reward 0.0, no
exceptions, with 1 of 9 verifier tests passing. A normal DeepSeek run was
started at `standard-deepseek-20260927T121853762452Z`, but the API/agent stayed
unresponsive for about one hour and was stopped before Harbor produced a trial
result; it is not counted as a model failure. Therefore this revision still
does not have the required three independent normal failures, and no Codex
formal result is claimed.

## Extended normal DeepSeek matrix

To distinguish a slow model response from a model failure, the next normal
matrix used the configured full `agent.timeout_sec=7200` seconds per trial and
was allowed to finish. The job was
`artifacts/jobs/standard-deepseek-20260927T154238703350Z`; Harbor reported a
total runtime of 1 hour 31 minutes 24 seconds.

The three scheduled trials separate cleanly:

- `recoverable-event-bridge__YMVC8ZS`: reward `1.0`, no exception, CTRF 9/9
  passed. This is a valid model success.
- `recoverable-event-bridge__pTyeCxU`: reward `0.0`, no exception, CTRF 1/9
  passed and 8/9 failed. This is a valid model failure.
- `recoverable-event-bridge__EDbBPJA`: `RuntimeError` while starting the tmux
  session, with no agent or verifier result. This is infrastructure failure and
  is excluded from the model denominator.

The independent one-attempt extended run
`artifacts/jobs/standard-deepseek-20260927T150151193790Z` also completed with
reward `0.0`, no exception, and CTRF 7/9 passed, 2/9 failed. Combining it with
the two valid trials above gives **2 valid failures out of 3 valid normal
trials, or a 66.7% observed failure rate**. The formal three-attempt matrix by
itself is 1/2 failed among valid trials (50%), because one of its three slots
was the tmux infrastructure error.

This is evidence of a low-accuracy candidate, but it does not meet the local
assignment gate stated in the README: three independent valid normal failures
for the model. The two earlier one-hour manual aborts remain uncounted because
they produced no verifier result. No Codex formal result is claimed because
the Codex quota is unavailable.

## Hardening revision and full DeepSeek gate

The next revision added two independently replayable protocol distinctions
found by comparing the successful artifact with the reference model. A second
commit with a different `commit_no` for an already-applied transaction must be
ignored, and a valid-CRC JSON payload with duplicate object keys must be
quarantined as `invalid_json`. The semantic and wire fixtures now exercise
those cases. Offline replay matched the solution byte-for-byte: cutover 9
events/11 quarantine, semantic 7/6, and wire 3/9.

The source was frozen before evaluation at
`artifacts/local/frozen/recoverable-event-bridge-20260927T203606942867Z/recoverable-event-bridge`.
Its snapshot tree hash is
`bd3aa8993195c7f1e9b25e81cec427c9aa5088cf5b3d89f30b89cdc98ba86842`; all
formal trials below report Harbor task checksum
`257be989e53b17c06dd1b13da45bb5bb6606ae35c37184edeb0ba3ea96084116`.
Fresh controls on this snapshot are oracle reward `1.0` with no exception in
`artifacts/jobs/recoverable-event-bridge-hardening2-oracle-20260928`, and nop
reward `0.0` with no exception in
`artifacts/jobs/recoverable-event-bridge-hardening2-nop-20260928`.

The one-attempt DeepSeek pilot
`artifacts/jobs/standard-deepseek-20260927T203924923543Z` returned reward
`0.0`, no exception, and CTRF 5 passed / 4 failed / 0 skipped. The matching
red-team run
`artifacts/jobs/cheat-deepseek-20260927T211615873696Z` returned reward `0.0`
with no exception.

The formal three-attempt normal matrix is
`artifacts/jobs/standard-deepseek-20260927T213335752324Z`. It ran for about
2 hours 11 minutes with no infrastructure errors. Every trial was a genuine
verifier failure:

- `recoverable-event-bridge__J37ceED`: reward `0.0`, CTRF 4 passed / 5 failed;
- `recoverable-event-bridge__auDJfqZ`: reward `0.0`, CTRF 5 passed / 4 failed;
- `recoverable-event-bridge__2E8AKP5`: reward `0.0`, CTRF 7 passed / 2 failed.

This is **3 valid failures out of 3 DeepSeek trials** on one frozen revision,
so the DeepSeek model-side low-accuracy gate is met. Codex formal evidence is
still unavailable because the account has no quota; the overall two-model
assignment gate therefore remains incomplete. The earlier one-hour manual
aborts and all results from different checksums remain excluded.

A sanitized machine-readable observation index covering the authoritative
controls, pilot, cheat, and formal trials is stored at
`artifacts/validation/recoverable-event-bridge-gate-observations.json`.

## GPT-6 Sol formal matrix on the current freeze

The current hardening freeze is
`artifacts/local/frozen/recoverable-event-bridge-20260928T022058331044Z/recoverable-event-bridge`,
with Harbor task checksum
`3c356502739a722070f771af8ba0ed7dc7be0b5442cf6db0b738814bd3a6070b`.
The formal Codex configuration is `openai/gpt-6-sol` with reasoning effort
`xhigh`; no Astra trial is used for this matrix.

The three-attempt job is
`artifacts/jobs/standard-codex-20260928T024708936501Z`. All three trials
completed the verifier with `exception_info=null` and reward `0.0`:

- `recoverable-event-bridge__Rp2gi5Z`: 7 passed, 3 failed;
- `recoverable-event-bridge__rtXrniM`: 6 passed, 4 failed;
- `recoverable-event-bridge__YJ2SNed`: 6 passed, 4 failed.

The failures are reproducible hidden semantic gaps, not timeouts or missing
verifier results. They include a stray newline in `events.ndjson` for an empty
fixture, incorrect handling of a second commit number for an already-applied
transaction, a zero-frame stop boundary rejected by some trajectories, and a
wire quarantine mismatch in one trial. The oracle and nop controls for this
freeze remain reward `1.0` and `0.0`, respectively, with no exceptions.

The matching DeepSeek matrix was also started on this freeze at
`artifacts/jobs/standard-deepseek-20260928T031334556645Z`. It produced one
valid verifier failure, `recoverable-event-bridge__5gmD7Vn` (7 passed, 3
failed, reward `0.0`), and two setup errors,
`recoverable-event-bridge__ESFQLQf` and `recoverable-event-bridge__f65qaBC`.
Both setup errors were `Failed to start tmux session` after the environment's
tmux installation fell back to a source build that timed out; neither has a
verifier result and neither counts as a model failure. A one-attempt retry
`artifacts/jobs/standard-deepseek-20260928T035535321769Z` reproduced the same
setup error. Thus the current freeze has **1 valid DeepSeek failure out of 1
valid trial**, not a completed three-failure DeepSeek gate.

The previous DeepSeek 3/3 result used checksum
`257be989e53b17c06dd1b13da45bb5bb6606ae35c37184edeb0ba3ea96084116` and is
retained as a valid historical conclusion for that earlier freeze. It is not
combined with the current Codex denominator. The current same-checksum
two-model gate therefore has Codex 3/3 valid failures and DeepSeek 1/1 valid
failure, with two DeepSeek infrastructure slots still unresolved.

## Runtime dependency repair and revalidation

The setup failures were environmental rather than model outcomes. The task
image did not contain `tmux` or `asciinema`, so Terminus-2 attempted an apt
installation on each trial. When apt failed on later containers, Harbor fell
back to a source build of tmux, which timed out after 120 seconds before the
agent session could start. Those trials have no verifier output and remain
excluded.

The task Dockerfile now installs the two runtime dependencies in the image
build. A container smoke check confirmed `tmux 3.3a`, `asciinema 2.2.0`, and a
create/destroy tmux session. The repaired source was frozen at
`artifacts/local/frozen/recoverable-event-bridge-20260928T044358768238Z/recoverable-event-bridge`
with Harbor task checksum
`b2dc1d34aea3d0c8a47240f210cb5232f3c7d7228b35dd9c02bea6f95679ac64`.

The first same-checksum DeepSeek revalidation is
`artifacts/jobs/standard-deepseek-20260928T044852305249Z`, trial
`recoverable-event-bridge__3Lgxt6M`. It ran for 37 minutes, completed the
verifier with `exception_info=null`, returned reward `0.0`, and produced CTRF
9 passed / 1 failed. Its setup log says both dependencies were already
installed; it is therefore a valid model failure and not a tmux setup error.
The machine-readable report is
`artifacts/validation/recoverable-event-bridge-environment-fix.json`. This
new checksum is intentionally not combined with the earlier Codex matrix;
any formal Codex result for this repaired image must be rerun on this exact
snapshot.

## Repaired DeepSeek matrix and CI metadata

The repaired image was then given two more serial DeepSeek trials in
`artifacts/jobs/standard-deepseek-20260928T044852-repaired-matrix`. Both
completed with `exception_info=null` and reward `0.0`:

- `recoverable-event-bridge__wbsbsV8`: 5 passed / 5 failed;
- `recoverable-event-bridge__jnMKWVT`: 5 passed / 5 failed.

Together with `recoverable-event-bridge__3Lgxt6M`, this is **3 valid DeepSeek
failures out of 3 trials** on checksum
`b2dc1d34aea3d0c8a47240f210cb5232f3c7d7228b35dd9c02bea6f95679ac64`. The
failures are verifier mismatches in hidden fixtures; the repaired image
reported preinstalled `tmux` and `asciinema` on every trial. A sanitized
index for all three trials is
`artifacts/validation/recoverable-event-bridge-repaired-matrix.json`.

The task metadata now uses the user-provided GitHub username `longhangyu`.
The local static check passes 25/25. A local CI/static check or Docker/Harbor
run does not require a GitHub login; authentication is only needed for a
remote action such as pushing a branch, opening a PR, or uploading results.
Because adding the username changes task metadata, the final submission freeze
is now
`artifacts/local/frozen/recoverable-event-bridge-20260928T073442757886Z/recoverable-event-bridge`
with Harbor checksum
`83b25d3bc0a07cb5088410aff5f1a402986bfd936004e68cd809325853f3dc94`.
The DeepSeek evidence above remains tied to checksum
`b2dc1d34aea3d0c8a47240f210cb5232f3c7d7228b35dd9c02bea6f95679ac64`; a
Codex rerun on the final metadata snapshot was completed later and is recorded
below; the older DeepSeek evidence remains separate from that final snapshot.

## Final-snapshot Codex and adversarial trials

After freezing the task with `author_github = "longhangyu"`, the formal Codex
matrix used `openai/gpt-6-sol` with `xhigh` on checksum
`83b25d3bc0a07cb5088410aff5f1a402986bfd936004e68cd809325853f3dc94`:
`artifacts/jobs/standard-codex-20260928T074308072872Z`. All three trials
completed with `exception_info=null` and reward `0.0`:

- `recoverable-event-bridge__32DhXBi`: 7 passed / 3 failed;
- `recoverable-event-bridge__oETo9HN`: 8 passed / 2 failed;
- `recoverable-event-bridge__94LaHzK`: 7 passed / 3 failed.

The matching final-snapshot cheat trials also completed without exceptions and
returned zero reward: Codex `/cheat` is in
`artifacts/jobs/cheat-codex-20260928T080703548218Z`, and the permitted DeepSeek
substitution `/cheat` is in
`artifacts/jobs/cheat-deepseek-20260928T081223953392Z`.

The final-snapshot oracle and nop controls returned reward `1.0` and `0.0`,
respectively, with no exceptions, in
`artifacts/jobs/recoverable-event-bridge-final-oracle-20260928` and
`artifacts/jobs/recoverable-event-bridge-final-nop-20260928`.

## Implementation rubric status

The disclosed local Codex review of the final snapshot ran all 35 criteria in
`artifacts/jobs/implementation-review-codex-20260928T081435304511Z`: 21 pass,
13 fail, and 1 not applicable. The material failures are not model-trial
failures. The task README still contains author placeholders; the task metadata
contains an extra `network_mode` field; verifier tests execute the submitted
program as root; complete checkpoints are not asserted against the exact input
length/frame count; and the environment/test fixture builders are separate
copies without a documented drift check. The review reward of `1.0` only means
that a verdict artifact was produced.

The four README sections and author identity prose must be written by the human
author. They should be completed before any final GitHub submission. Technical
rubric fixes would change the task checksum and require a fresh freeze and
fresh standard/cheat evidence.

## Final-snapshot DeepSeek standard matrix

The same final freeze was then evaluated with the permitted DeepSeek
substitution. The job is
`artifacts/jobs/standard-deepseek-20260928T082943222878Z`, and all three
trials use checksum
`83b25d3bc0a07cb5088410aff5f1a402986bfd936004e68cd809325853f3dc94`:

- `recoverable-event-bridge__ckA2g3H`: reward `0.0`, exception `null`;
- `recoverable-event-bridge__6Bi66Zi`: reward `0.0`, exception `null`;
- `recoverable-event-bridge__KDRbv3M`: reward `0.0`, exception `null`.

The Harbor summary is 3/3 completed, 0 exceptions, mean reward `0.000`. The
machine-readable report is
`artifacts/validation/recoverable-event-bridge-final-deepseek-standard.json`.
The first two runs took about 42 and 84 minutes; the extended task timeout was
7200 seconds, so their long but active trajectories were retained as valid
trials rather than treated as infrastructure failures. Together with the
final-snapshot Codex matrix, this completes the same-checksum standard model
gate. The implementation-rubric failures and human-authored README/identity
requirements remain separate submission blockers.
