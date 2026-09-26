# Cutover observation windows and delayed migration

This is an independent read-only analysis of frozen candidate
`online-order-cutover-20260926T212539311430Z`, tree SHA-256
`1aac8e715145982a0dd45ccb13e5e602cc3888142ff5de1f9f61af95a41f3c3f`.
It does not use the rubric agent's unfinished output. No task files were changed,
no models were called, and no duplicate Docker counterexample campaign was run.
The earlier frozen review did not identify this coverage weakness.

## What the code establishes

`tests/controller.py:24,298-324` gives every observation a two-second window.
An expired observation is returned as metadata. Several callers also use it as
the event that removes a fault or ends the concurrent part of the workload.
The final SQL comparisons remain real, but the adverse interleaving may never
have happened. **Absence of a private phase must not fail a valid solution;
absence also cannot be counted as proof that the corresponding fault was tested.**

| Check | Effect of a sufficiently long startup delay | Still checked |
| --- | --- | --- |
| Live backfill, `test_outputs.py:174-189` | At two seconds the target SHARE lock is released. All four business calls can finish before the migration starts copying. A migration that would stop source writers while that lock is held no longer encounters that condition. | Later target contents, historical receipts, retirement and restart. |
| Kill and concurrent restart, `:199-212` | The first process can be killed during its sleep. The only new business request can finish while both replacement migrators sleep. This does not exercise termination after copying or writes overlapping recovery. | Concurrent-invocation convergence and final state, provided the replacement algorithm actually starts. |
| Delayed commit, `:224-249` | The target lock is removed after the first observation. Additional finite observation windows eventually release the source receipt placeholder. If migration begins later, both slow and fast business transactions are already committed when its first snapshot is taken. | Final state and receipts. A sequence-watermark bug is not necessarily exercised. |
| Lost COMMIT ACK, `:265-294` | `live` is false after observation expiry, so all four source mutations are skipped. The later COMMIT proxy still injects its fault, but an incremental catch-up transaction may never be created or selected. | Genuine observed COMMIT-ACK loss, retry, preservation of later target writes, and source retirement. Sleep does **not** bypass these remaining checks. |
| Delayed source connection, `:315-330` | The gate is released when the two-second migration-completion observation expires. The delayed source write can commit before migration takes its snapshot. A missing routing recheck need not be exercised. | Final acknowledged state, including inspection before a receipt retry could repair it. |

The relevant delays are not a universal fixed number. They include actual HTTP,
connection and query time. For example, an eight-to-ten-second prelude could
outlast the short observation sequence on these small fixtures, while remaining
under the sixty-second post-release migration guard. This is a concrete static
schedule argument, **not a report that a particular complete wrong solution has
passed all frozen tests**. The independent rubric counterexample must supply
that evidence separately.

The basic API/SQL cases, strict receipt identity tests, service HTTP unknown-
response recovery and source-retirement checks are not removed by adding sleep
to `migrate`. A complete failing implementation must still satisfy those parts.

## Minimum practical repair for a later revision

Use one shared lifecycle driver instead of treating observation timeout as a
phase transition. Retain the existing public SQL, health and process observers.

1. Start a single, model-tracked writer before launching migration and keep it
   active until the migration process has finished. Continue after releasing a
   fixture and during restart attempts. Use bounded create/replace/delete and
   read operations on a small set of orders, with explicit unique request IDs.
   A gentle cadence, such as one mutation per second, fits within the published
   200-new-mutation bound for the contemplated lifecycle. Compute the actual
   upper bound before freezing; do not silently exhaust the workload before the
   migrator starts. The monitor must not concurrently mutate the same model.
2. Hold the public target SHARE lock while observing process exit, public route
   and PostgreSQL blocking. Two seconds becomes a polling/diagnostic interval,
   **not** a release event. If the public route is target or migration has
   successfully finished, release immediately and check final state. This
   accepts fast completion, views, dual writes and post-activation maintenance.
3. If the public relation actually blocks the migrator while the route is source,
   require a newly completed business operation and read while the lock is still
   held, then release it. A success from before the blocking observation must
   not satisfy this handshake. The existing fifteen-second progress rule governs
   these unrelated source operations; it is not a new throughput score.
4. Apply the same lifecycle to ACK discovery/replays. Keep the proxy's actual
   observed COMMIT numbering. Do not skip all live changes merely because no
   lock wait appeared in the first two seconds. A fault that happens before a
   barrier is reached still goes directly to recovery, as before.
5. For crash recovery, kill after an observed public blocking condition when
   available; otherwise label the crash point unknown. Keep the writer running
   across both replacement processes rather than issuing one pre-copy mutation.

Continuous traffic alone is insufficient: a very short incorrect copy can fit
between requests. The public lock/progress handshake is what makes the specific
global-pause defect reproducible when that condition is observable.

## Delayed receipt and connection details

For the delayed-commit case, retain the temporary source receipt until one of
these public events occurs: the fast receipt is visible on the target; migration
is observably waiting for the slow source transaction; target activation or
successful completion occurs; or the documented lifecycle fallback is reached.
Then roll back the placeholder and verify both independent business outcomes.
Do not require a private sequence number, capture table, trigger or CDC design.
The migration-waits-on-writer release condition preserves legitimate final full
recopy: that algorithm may need the pending source writer to finish before its
last snapshot, without ever publishing the fast receipt earlier on the target.

The intentionally blocked slow request cannot retain the current ordinary
`answer()` timer unchanged when the fixture may be held longer. Otherwise the
test itself exhausts its fifteen seconds. Give this one request an explicitly
documented injected-pause budget and the ordinary response/retry budget after
release. Unrelated requests continue to have the real fifteen-second bound.

For the source connection gate, prefer public target activation over waiting
only for CLI exit: successful activation may precede post-activation cleanup.
Keep the gate until that event, an observed completion, or a documented safe
fallback. A connection timeout, pool reuse or a request ending before activation
still means the desired stale-route interleaving was not observed. Do not fail
those strategies just to force this optional probe. Continuous background
operations preserve ordinary concurrent migration coverage, but do not turn an
absent gate interleaving into positive stale-route evidence.

## Deadline and fairness boundary

The present contract (`CONTRACT.md:179-184,214-219`) explicitly permits missing
observations and starts the sixty-second completion wait after fixtures are
released. Consequently, simply changing two seconds to another magic duration
does not close the class of delay-based evasions. A migrator can outwait another
finite observation window, and resetting a fresh sixty-second budget while also
stopping the writer repeats the current weakness.

A later revision should publish the lifecycle accounting before evaluation:
normal migration/runtime budget, maximum injected hold, when blocked-request
budgets pause, and the remaining completion budget after release. Preserve a
no-fixture run against the normal migration bound; arbitrary startup sleep is
charged there. Keep the background writer running throughout any fallback.
Use a substantially longer lifecycle observation bound rather than a hidden
two-second assumption, but report an exhausted optional observation honestly.

There is a real black-box limitation: a legitimate implementation may use
NOWAIT retries or private staging, so PostgreSQL may expose no blocking edge;
a target-table lock may stop final publication rather than initial backfill.
One cannot infer a private stage from its absence or turn that absence into an
automatic model failure. If the task intends source requests to progress for
the *entire* externally-held public-table fixture, including publication waits,
say that operational requirement explicitly. If it intends only an internal
initial-copy phase, no universal stage detector follows from the current public
interface. These are different contracts and must not be silently conflated.

The qualification criterion belongs at the benchmark-authoring level: the
revised controller should accept the reference, the legitimate full-recopy
alternative and fast/view or NOWAIT variants, while rejecting a known
stop-writers-during-blocked-copy mutant both immediately and with a startup delay.
It should also retain its delayed-commit and stale-route discrimination when
those interleavings are actually observed. If a known incorrect control still
passes by losing coverage, do not call the benchmark qualified; do not convert
the missing optional phase into a failure of a legitimate solution.

No new frozen revision or implementation change is recommended before the
current pilot and rubric outcomes are recorded. These findings concern test
coverage and do not establish either model success or model failure.
