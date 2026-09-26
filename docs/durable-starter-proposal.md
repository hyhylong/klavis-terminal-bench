# Durable ledger starter proposal

Status: proposed experiment, not an implemented starter or a qualified hard
task. Both configured models solved v1. No result currently establishes that
this design will defeat either model.

## Recommended scope

Build the starter around one failed optimization: treating the current
effective action and rendered projection as sufficient retained state for
future corrections. This is plausible for an append-only projection, but the
existing ledger permits later ingestion retractions and historical amendments.
The optimization discards amendment candidates and the previous effective
action needed to invalidate a cached timeline.

Keep the durable source journal and format-1 checkpoints complete. All supplied
storage images must contain enough original source facts to reconstruct every
supported cutoff. The failure must be in how the implementation maintains and
restores derived indexes, not in asking the agent to recover information that
is no longer present anywhere.

Keep `domain.py`, codec semantics, seals, classification priority, and the
filesystem simulator correct. Preserve the correct generation publication and
fsync ordering in `replay_store.py`. Deliberately removing an fsync would add an
independent storage bug without making this central repair more coherent.

## Concrete differences from the correct implementation

Use a separate starter implementation; do not mutate the correct calibration
implementations. The following differences should be presented as one
incomplete checkpoint/cache optimization, not hidden typo mutations.

1. **One amendment head per target.** Replace the correct
   `ProjectionIndex.amendments[target][amendment_row_id]` candidate collection
   with a single winning amendment record. Installing a later amendment
   replaces that record; an older arriving amendment is ignored. Removing the
   winner removes the head and exposes the original ordinary action. This
   incorrectly assumes that superseded amendments can never become relevant
   again. Removing a non-winning amendment should be a deliberate no-op, not a
   `KeyError` or another accidental runtime defect.

2. **Dirty entities derived only after changing the head.** Replace `_refresh`'s
   before/after effective-action union with invalidation based on the new head
   alone. When a null amendment suppresses a target, there is no new effective
   action from which to discover the entity. The previous rendered timeline
   remains cached. This is the second consequence of discarding the previous
   contribution, not a different business rule. Ordinary newly installed live
   actions still invalidate their entity normally.

3. **Persist and restore that incomplete derived checkpoint.** A checkpoint
   optimization stores the same head-only index and rendered timeline cache in
   a generation-specific optional projection file. On reopening, it restores
   those heads and caches without rebuilding their lost dependencies from the
   full source checkpoint. The authoritative format-1 source checkpoint and
   WAL remain unchanged and recoverable. Source-only legacy images continue
   to open by rebuilding the index. Any optional projection cache must be
   documented as derived, discardable data associated with its source
   generation, never a replacement for the source checkpoint.

The exact optional-cache serialization should be settled before authoring the
starter. It should contain the starter's actual runtime index state, not a
special fixture answer. Missing or unusable optional cache data must fall back
to source reconstruction. Do not introduce an additional cache-generation
mix-up merely to make more tests fail.

These changes create a recognizable architectural repair: retain reversible
source contributions, remember both old and new effective actions when
invalidating projections, and ensure the checkpoint restore path reconstructs
the same dependency state as live ingestion.

## Public behavior and small reproducer

The starter should pass ordinary in-order PUT/PATCH/DELETE ingestion, exact
duplicate retries, full-source historical replay, source-only legacy opening,
and basic compaction/reopening without amendments. This establishes that the
task is repairing an operating library rather than filling empty methods.

Publish a small reproducer with an explicit expected result. All transactions
below are complete and use a visible schema; source sequence increases as
listed. Default fields are unchanged.

| Transaction | Ordinary action or amendment |
| --- | --- |
| `base`, seq 10 | PUT entity `a`, `[0,10)`, tier `basic`, quota 1000 |
| `patch`, seq 20 | PATCH `a`, `[3,7)`, quota 2000 |
| `gold`, seq 30 | Amend `base/0` to PUT `[0,10)`, tier `gold`, quota 1500 |
| `void`, seq 40 | Amend `base/0` to null |

Query after `gold` to populate the cache. The expected intervals are
`[0,3)` gold/1500, `[3,7)` gold/2000, and `[7,10)` gold/1500. All origins are
`gold/0`, except the middle quota origin, which is `patch/0`.

After `void`, there are no entity intervals: the base action is suppressed and
PATCH cannot create a record. This exposes invalidation that loses the old
entity when a new effective action is null.

Compact and reopen, then ingest an abort of `void`. The three gold intervals
must return with the same origins. `gold` is still applied and becomes the
winning amendment again. Falling back to `base` is incorrect. This exposes
lost amendment candidates in both live and restored dependency state.

Previously requested cutoff snapshots remain unchanged throughout. Repeat
the sequence without compaction and with reopening at each boundary. Their
public results must agree. Include this failure example in public tests; the
benchmark must not depend on hiding the central invariant from the agent.

## Expected repair surface and verification

A natural repair touches contribution retention, effective-action selection,
cache invalidation, and derived-checkpoint serialization/restoration. A valid
alternative may instead discard the derived cache and rebuild from the full
source history. No private class, field name, patch shape, or exact number of
changed files should be graded.

Verify public API behavior with the independent v1 endpoint replay model.
Exercise candidate reactivation after abort/conflicting delivery, late target
eligibility, null winners, and old cutoffs. Every scenario follows existing v1
semantics; no new event variants are needed.

Retain the deterministic crash sweeps as regression checks. The source journal
and generation protocol should already preserve acknowledged events in the
starter. A submitted repair must preserve that property while changing
checkpoint contents or restoration. Crashes before and after compaction
publication must recover a complete source generation, and subsequent late
corrections must work in either case. These are genuine persistence
interactions without inserting an unrelated fsync-order defect.

## Shortcut risks and falsification

The existing cached full-replay baseline is a legitimate repair strategy.
Keeping all amendment candidates and replaying only affected entities is also
legitimate. Discarding all optional derived caches on open is valid if it meets
the final public workload. Do not ban these approaches or grade internal data
structures to force the intended fix.

Because `domain.py` already implements the source semantics correctly, an
agent may implement a sound wrapper quickly. The head-retention and
before/after invalidation errors may also be easy to localize from the public
reproducer. This proposal is more coherent than a collection of mutations,
but coherence is not evidence of sufficient difficulty.

Run calibrated workload comparisons before deciding whether a performance
contract is warranted. Publish the workload and any accepted contract; use
ample host-variance margin. If full replay meets that contract, accept it.

A model pilot that repairs the task and passes the independent correctness and
workload checks falsifies the required difficulty. Preserve the successful
trajectory. Do not react by hiding the reproduction, adding incidental
formatting requirements, weakening time allowances, or planting unrelated
bugs. If additional complexity is needed, reassess the engineering objective
rather than changing the meaning of this repair.
