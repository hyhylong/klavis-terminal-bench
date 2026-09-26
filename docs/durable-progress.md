# Durable ledger candidate: development evidence

This candidate's required difficulty was falsified by a successful normal Codex
pilot: reward 1, 26/26 checks, no exception, and a 0.365-second stream median
against the 3.0-second limit. It is not a completed assignment or a qualified hard
task. The six-failure/two-cheat campaign will not continue for this candidate.
V1 was also solved by both configured models. Preserve both versions and all
successful evidence; V1 source remains in commit `89fb5d8` and the original task
directory. See the [pilot analysis](durable-pilot-analysis.md).

## Why this candidate

The [primary-source research](research/task-difficulty-2026-09-27.md) suggests
investigating repairs across interacting state and persistence paths. It does
not establish that these particular models will fail this new task. Increasing
the number of independent rules in the original replay problem did not suffice.

The new starter has a coherent incomplete optimization: it retains only the
current amendment head and loses the old effective entity during invalidation;
its optional checkpoint restores those incomplete derived indexes. All source
events remain durably available, so the task is recoverable. Public smoke tests
expose the central invariant. Rebuilding derived data and replacing the
implementation are permitted.

## Observed development results

- WSL pinned Python: 103 component development tests passed, covering the original task,
  durable filesystem, replay store, incremental index and persistent wrapper.
- The incremental index also matched independent replay on 3,076 shuffled
  delivery prefixes in a separate review experiment.
- Isolated worker: 13 checks passed under both system Python 3.10 and pinned
  Python 3.12, including denial of protected file reads and reward writes. A
  final verifier also probes nested input/output ownership inside the child.
- Public smoke: correct implementation 4/4; starter 2 semantic failures and
  2 passes, with no runtime error. Across the original corpus, the starter
  mismatched 14/21 snapshots while retaining fully recoverable source history.
- The starter's second compaction was interrupted at each of 24 filesystem
  operations; all recoverable source generations remained complete.

The final semantic verifier passes all 25 tests for both correct implementations.
Removing ingest fsync or returning shared snapshot data causes the relevant
regression to fail. These are correctness checks, not model difficulty evidence.

## Calibration, before any threshold

The workload contains 192 entities, 12 source versions, 180 correction rounds
and 12 point queries per round. The baseline memoizes one full reconstruction
per accepted revision; it does not recompute separately for every point query.
The incremental implementation invalidates affected entity timelines. Both
retain identical durable source data and return identical result hashes.

Three native WSL measurements gave full-replay stream times of 7.15–8.04 seconds
and incremental times of 0.052–0.055 seconds. One isolated RPC measurement gave
8.551 and 0.355 seconds respectively, with matching answers. Three full
snapshots were also checked using the independent endpoint replay verifier.
These are exploratory host observations, not a published task threshold.

Actual Docker calibration used a 1-CPU CFS quota, 2 GiB memory, default seccomp
and no network. Incremental stream samples were 0.542, 0.418 and 0.521 seconds;
memoized replay samples were 9.385, 10.452 and 12.792 seconds. All answer hashes
matched. The published median budget is 3.0 seconds, over 5.5 times the slowest
correct sample; the final verifier has a 2-CPU quota. The exact workload and
isolated public driver ship with the task. Any implementation meeting the
contract is accepted. A successful model pilot invalidates the required
difficulty even if all engineering checks pass.

## Runtime issue resolved

Docker Desktop could not start because it failed to remove stale runtime socket
entries. Recovery quarantines the specifically identified entries with backups;
it does not require deleting task data, resetting Docker, or changing network
settings. Docker server 29.4.0 is now running and the previous image tags remain.
The existing logs contain an earlier reset action but do not establish its
initiator or prove image-data deletion. WSL-only development continued during
recovery. The actual Docker isolation checks passed 13/13.

## Container and Harbor controls

The frozen candidate under `durable-ledger-repair-20260926T193933080719Z`
has Harbor task checksum
`440b57b209c8ee7c28177c2a6c0755ec8ae7c37713abe60c60c1d35ff49b8cc0`.
Harbor `durable-oracle-v2` received reward 1 with 26/26 checks passed;
`durable-nop-v2` received reward 0 with 20 passed and six semantic failures.
Neither trial has an execution exception. The oracle's stream median was
0.402 seconds. Both controls used the same checksum.

An earlier negative control was cancelled because pytest tried to render a
large repetitive JSON string diff. The verifier now reports the first
structural mismatch. The old cancellation remains recorded and is not a
difficulty result. Direct negative verification after the fix completed in
29.09 seconds with six semantic failures.

The clean snapshot passes 24/25 pinned static checks. The remaining check
requires the author's real GitHub handle; all author fields and four human
sections still need genuine author input. Placeholders do not satisfy that
substantive requirement even where the static script only checks headings.

## Qualification history before the successful pilot

Codex pilot `standard-codex-20260926T194253144614Z` failed during dependency
installation with `NetworkConnectionError`, before a model answered. Debian
package downloads failed; it is not a genuine task failure. The next setup
used verified official standalone CLI artifacts to avoid the unnecessary
Node/npm distribution dependency chain. Two attempted rubric jobs also failed
before model execution: one DrvFS working-directory error, then an Ubuntu
registry timeout. Native Linux staging and a disclosed cached Python base are
available for the local reviewer, with the same 35 criteria and model settings.

An independent audit then demonstrated a compaction-test false positive:
appending a duplicate WAL frame passed the old retirement check. The working
candidate was updated to check the published format-1 post-compaction state explicitly;
both correct implementations pass and that mutant fails. The storage
read/write interface was clarified publicly; the new freeze and controls are
recorded below. A trusted harness preflight was added to separate platform
failures from solution failures before reward generation. A future qualifying
candidate still needs the requested real trial evidence, author metadata and
human sections, analyses and GitHub delivery. Environment errors, timeouts and
cancelled runs do not qualify; this candidate's later success does not either.

## Requalified runtime and working candidate

The next frozen task, `durable-ledger-repair-20260926T200157076022Z`, includes
the clarified compaction checks, trusted platform preflight and the official
standalone Codex 0.157.1 binary in the agent image. Its Harbor checksum is
`52200606da8644eb9d948784f20b1369bafcaea4702d0190f0e03f1a4708b957`.
The public linux-x64 archive is checksum-pinned in the portable Dockerfile;
the full platform bundle and bundled ripgrep are preserved. Registry integrity
and signatures were verified, then the actual pinned Harbor setup was exercised
offline: it detects the CLI and skips Node/npm installation. No authenticated
container state or credentials were included. This runtime is for x86-64 Linux.
The compact evidence is `artifacts/validation/codex-runtime-0.157.1.json`.

Harbor `durable-oracle-v3` and `durable-nop-v3` use that exact checksum and both
pass the trusted preflight with no trial exception. Oracle passes 26/26 with
reward 1 and stream median 0.449 seconds; nop has 20 passing and six semantic
failures with reward 0. See `artifacts/validation/durable-controls-v3.json`.
Independent direct Docker controls also pass/fail as intended at 2 CPU/2 GiB.
The refreshed static checks remain 24/25, with author GitHub missing; 121
development tests pass under the pinned Linux Python runtime.

## Successful normal pilot: reject this difficulty hypothesis

`standard-codex-20260926T200419294708Z`, trial
`durable-ledger-repair__Z3p4gpg`, completed with Codex 0.157.1 /
`openai/gpt-6-astra` / xhigh. It has reward 1, no trial exception, a passed trusted
preflight and 26/26 independent checks. Its three measured stream times are
0.344291, 0.369361 and 0.364649 seconds; the median is 0.364649 against 3.0 seconds.
The job took 483.338 seconds; agent execution took 410.030 of the available
7200 seconds. This is a genuine success, not an infrastructure result.

The submitted repair keeps `storage.py` and `domain.py` byte-identical to the
frozen starter, retains all amendment candidates, invalidates the old effective
entity, and discards the optional persisted projection cache. It rebuilds that
index from complete source history on open, outside the published timed region.
This lawful simplification leaves the realtime incremental query path fast.
Public smoke passed about 101 seconds into agent execution; the agent then added
regression and differential tests. The [analysis](durable-pilot-analysis.md) and
[filtered result record](../artifacts/validation/durable-codex-pilot.json) retain
step evidence and original-file hashes.

Do not continue this candidate's formal six-normal-failure/two-cheat campaign,
hide its reproduction, tighten the budget after seeing the result, or discard
the successful run. One pilot does not estimate population success probability;
it does falsify treating this candidate as having demonstrated the required
difficulty.

`implementation-review-codex-20260926T200212311524Z` reviewed the same frozen
candidate using native Linux staging, the pinned Python base and preinstalled
CLI. Its exact 35 outcomes were independently checked: **23 pass, 11 fail,
1 not applicable**. The rubric did not pass; review reward 1 means only that a
nonempty verdict artifact was delivered. The [rubric analysis](durable-rubric-analysis.md)
and [filtered summary](../artifacts/validation/durable-rubric-v3/summary.json)
separate a demonstrated WAL writer-format coverage gap, other explicit rubric
defects, known author placeholders and an upstream schema-version inconsistency.
The submitted pilot kept the storage writer unchanged, so its success does not
depend on the demonstrated format gap. Neither review experiments nor review
reward count as formal normal-failure or cheat trials.
