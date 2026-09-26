# Durable ledger repair candidate

Status: implementation experiment, not a qualified final task. V1 was solved by both configured models. User authorized continued implementation informed by public failure analyses. Preserve v1 and its successful trajectories.

## Goal and scope

Repair a running single-writer temporal ledger projection library across append, historical correction, compaction, and crash recovery. Reuse v1's event semantics exactly; do not introduce new codecs, transaction types, sharding, or concurrency. Difficulty should arise from keeping durable source facts, eligibility indexes, and cached projections consistent.

The agent may replace the implementation. A complete-log replay solution is valid if it meets the published behavior and calibrated workload contract. First implement and measure that baseline. Do not introduce performance limits until a correct efficient implementation and the baseline have been measured with ample variance margin.

## Public API

`from ledgerstore import Store`; `Store(fs)` opens or creates the store through the supplied filesystem interface.

* `ingest(event) -> None`: accept one v1 JSON envelope. New arrivals increase strictly. Retrying an already known arrival with structurally identical JSON is idempotent. A different envelope at the same arrival, or a previously unseen older arrival, raises `ValueError` without changing the store. Successful return acknowledges durability.
* `snapshot(cutoff) -> dict`: return a v1 checkpoint object with exactly `id='snapshot'`, `transactions` and `entities`. Only accepted events with arrival <= cutoff contribute; the cutoff is an argument, not an output field.
* `lookup(entity, valid_time) -> dict | None`: read the current accepted prefix. Return `None` for an absent time; otherwise return the complete matching v1 segment (including interval endpoints, tombstone, values and origins). This must agree with `snapshot(latest_arrival)`.
* `compact() -> None`: install a durable consolidated source checkpoint, retire superseded WAL records, and preserve every supported historical snapshot and future correction. Compaction may retain source lineage; projected values alone are insufficient. Repeated compaction is idempotent in observable behavior.
* `close() -> None`: release transient resources; never needed to make an already acknowledged ingest durable.

No threads or concurrent callers. A new process constructs a new Store after a crash. An unacknowledged last ingest may be present or absent after restart, but must be atomic; its identical retry must converge. Every acknowledged event survives. Existing accepted v1 storage images (defined by the implementation plan before grading) must open unchanged.

## Filesystem interface

All persistent bytes belong to the injected namespace. Plain filenames match `[A-Za-z0-9_.-]{1,96}`; no path components. Calls:

* `read(name) -> bytes`, raising `FileNotFoundError` when absent.
* `write(name, data: bytes)`: replace or create volatile file contents.
* `append(name, data: bytes)`: append, creating if absent.
* `fsync(name)`: persist that inode's current contents, not directory entries.
* `replace(source, destination)`: atomic volatile rename, replacing destination.
* `unlink(name)`: remove volatile directory entry; absent names raise `FileNotFoundError`.
* `list_files() -> list[str]`: sorted visible names.
* `fsync_dir()`: persist the current name-to-inode mapping, not file contents.

The trusted simulator keeps volatile and durable inode contents and directory mappings separately. Crash restores the durable mapping and each referenced inode's durable contents. Unflushed new files may be absent or empty according to the recorded directory state. Old inode contents remain available while referenced by a durable directory entry. Faults occur immediately after a filesystem operation and before its reply. A killed client cannot change the simulator's durable state afterwards.

## Independent verification and isolation

Semantic truth remains v1's independently implemented endpoint replay verifier. New store implementation must not import it. Differential checks compare snapshots and lookups across ingestion prefixes, duplicate retries, compaction, reopen, late schema/row/commit/amendment/abort, and injected crashes.

Submitted Python code runs as an unprivileged child, with stdout/stderr captured to bounded temporary files. A Unix socket protocol transports public Store requests and filesystem calls. The root parent alone owns expected results, simulated durable state, fault scheduling, and reward. Do not import submitted code into root pytest. Tests and expected data are inaccessible to the child; submitted code is allowed to read only its package, runtime libraries, and the explicitly supplied interface. Bound socket frames, execution time and process lifetime; kill the process group on failure. The child cannot mutate test modules, expected results, or reward files.

## Performance experiment

Measure a workload of many entities and transactions, followed by late corrections and point lookups. Repeated full reconstruction should be measured explicitly, not silently forbidden. Compare a naive correct persistent replay store with an incremental implementation. Declare any eventual workload size and timing contract in the public task and provide a runnable calibration workload. Include multiple correct runs and a broad margin; reject a threshold whose apparent hardness is a near miss or host noise.

## Qualification

1. Hand-computed durability tests and v1 semantic differential tests pass.
2. Naive and incremental correct implementations agree; workload calibration is recorded.
3. Broken starter fails for explained cross-layer defects; no missing dependency or undisclosed output constraint.
4. Separate verifier isolation and malicious-artifact checks pass.
5. Pinned static gates, oracle/nop and 35-criterion review pass, subject to actual author input.
6. Pilot real models before spending on the complete 3+3 normal and 1+1 cheat matrix. A success falsifies the required difficulty; retain it honestly.
