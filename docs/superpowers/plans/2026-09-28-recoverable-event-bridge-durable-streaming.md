# Recoverable Event Bridge Durable Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace full-stream replay with a bounded streaming scanner and durable journal recovery that is functionally verified after hard interruption.

**Architecture:** Keep the public framed event protocol and independent replay model. Implement the submitted artifact as one standard-library `bridge.py` using a chunked segment reader, SQLite journal, durable checkpoint, and atomic output publication. Extend hidden fixtures and verifier tests to exercise large input, failpoints, SIGKILL recovery, journal truncation, and exact byte outputs.

**Tech Stack:** Python 3.13 standard library, SQLite WAL, pytest, Docker/Harbor.

---

### Task 1: Add contract-level recovery expectations

**Files:**
- Modify: `tasks/recoverable-event-bridge/environment/CONTRACT.md`
- Modify: `tasks/recoverable-event-bridge/instruction.md`
- Test: `tasks/recoverable-event-bridge/tests/test_outputs.py`

- [ ] **Step 1: Add a failing checkpoint-schema assertion**

Extend `_assert_outputs` so a complete checkpoint must contain exactly
`schema_version`, `offset`, `frames_scanned`, `source_sha256`,
`journal_sha256`, and `complete`; assert both digests are lowercase SHA-256
strings and match the input/journal evidence copied from the worker output.

- [ ] **Step 2: Run the focused test and verify the expected failure**

Run from WSL:

```bash
source /mnt/e/JOB/klavis-terminal-bench/artifacts/environment/runtime-env.sh
cd /mnt/e/JOB/klavis-terminal-bench
pytest -q tasks/recoverable-event-bridge/tests/test_outputs.py::test_clean_run_matches_independent_replay
```

Expected result: the current reference artifact fails because its checkpoint
does not contain the new digest fields.

- [ ] **Step 3: Document only observable requirements**

Describe chunked input, `.bridge-state`, checkpoint digests, failpoints, and
restart behavior in `CONTRACT.md` and `instruction.md`. Do not require a
specific database schema or source-code string.

- [ ] **Step 4: Commit the contract/test red state**

```bash
git add tasks/recoverable-event-bridge/environment/CONTRACT.md tasks/recoverable-event-bridge/instruction.md tasks/recoverable-event-bridge/tests/test_outputs.py
git commit -m "test: specify durable streaming recovery contract"
```

### Task 2: Build independent large and crash fixtures

**Files:**
- Modify: `tasks/recoverable-event-bridge/environment/input_builder.py`
- Modify: `tasks/recoverable-event-bridge/tests/fixture_builder.py`
- Modify: `tasks/recoverable-event-bridge/tests/hidden_cases.py`
- Test: `tasks/recoverable-event-bridge/tests/test_outputs.py`

- [ ] **Step 1: Add a deterministic large builder to both fixture files**

Keep the two builder files byte-identical. Add `large(root)` that emits at
least 8 MiB of small valid frames across at least 32 segment files, with a
deterministic mixture of interleaved transactions, duplicate events, commit
records before events, cutovers, and corrupt frames. Use a fixed loop and no
randomness so expected bytes are reproducible.

- [ ] **Step 2: Add a hidden-case registration test**

Add `"large"` to `case_builders()` and assert its manifest has the expected
segment count and stream size. Run the focused test and confirm the current
artifact fails the new bounded-memory/recovery assertions before changing the
solution.

- [ ] **Step 3: Add failpoint and SIGKILL test helpers**

Create a helper that starts `/app/bridge.py` in the existing unprivileged
worker tree, sets `BRIDGE_FAILPOINT`, waits for a nonzero exit, kills the
process group if needed, then invokes the normal command again. Preserve the
clean-run bytes and compare every public output after recovery.

- [ ] **Step 4: Commit fixture and test red state**

```bash
git add tasks/recoverable-event-bridge/environment/input_builder.py tasks/recoverable-event-bridge/tests/fixture_builder.py tasks/recoverable-event-bridge/tests/hidden_cases.py tasks/recoverable-event-bridge/tests/test_outputs.py
git commit -m "test: add large streaming and crash recovery fixtures"
```

### Task 3: Implement the bounded segment scanner

**Files:**
- Modify: `tasks/recoverable-event-bridge/solution/bridge.py`
- Test: `tasks/recoverable-event-bridge/tests/test_outputs.py`

- [ ] **Step 1: Define the scanner interface**

Implement `iter_stream_bytes(input_root, chunk_size=65536)` yielding chunks
and a `scan_chunks(input_root, start_offset, stop_after)` generator yielding
`(offset, payload_or_none, quarantine_or_none, scanned_count, next_offset)`.
The scanner must retain no more than `MAX_PAYLOAD + 12` bytes of incomplete
frame data and must preserve absolute offsets across segment boundaries.

- [ ] **Step 2: Run the large fixture test and verify the memory-related red state**

Run:

```bash
pytest -q tasks/recoverable-event-bridge/tests/test_outputs.py -k large
```

Expected result: the current `read_input(...).read_bytes()` implementation
fails the large-fixture contract or exceeds the test process address-space
limit.

- [ ] **Step 3: Replace full-stream scanning with chunk scanning**

Reuse the existing payload validation rules and quarantine reasons, but read
manifest segments one at a time and emit records as soon as a complete frame
or unrecoverable wire error is available. Preserve the existing resynchronizing
magic search behavior.

- [ ] **Step 4: Run all existing semantic and wire tests**

```bash
pytest -q tasks/recoverable-event-bridge/tests/test_outputs.py -k 'not crash and not large'
```

Expected result: all previous exact replay, stop/resume, idempotence, and
read-only tests pass.

### Task 4: Implement durable SQLite journal and checkpoint recovery

**Files:**
- Modify: `tasks/recoverable-event-bridge/solution/bridge.py`
- Test: `tasks/recoverable-event-bridge/tests/test_outputs.py`

- [ ] **Step 1: Add journal schema and checkpoint helpers**

Create the `.bridge-state` directory with SQLite WAL mode and tables for
`frames(offset PRIMARY KEY, payload, reason, txn, kind)`, `meta(key PRIMARY KEY,
value)`, and `publish(marker PRIMARY KEY, value)`. Store the source digest,
last durable offset, scanned-frame count, and journal digest in one committed
transaction.

- [ ] **Step 2: Add the recovery test before the implementation is complete**

For each failpoint (`after_journal`, `after_checkpoint`, `after_publish`) and
selected stop counts, kill or stop the process, restart it, and assert exact
clean-run outputs plus a complete checkpoint. Run the test and capture the
failure against the incomplete journal implementation.

- [ ] **Step 3: Implement tail rollback and idempotent restart**

At startup validate `source_sha256` and `journal_sha256`; delete journal rows
whose offsets are at or beyond the checkpoint, resume at the checkpoint offset,
and commit each emitted frame and checkpoint update atomically. A repeated
frame at the same offset must not create a duplicate journal row.

- [ ] **Step 4: Implement failpoints and atomic publication**

Flush and fsync journal/checkpoint state before `after_journal`, flush the
checkpoint before `after_checkpoint`, and use temporary output files plus
directory fsync before `after_publish`. A restart must clean incomplete
temporary publication and converge to the clean-run bytes.

- [ ] **Step 5: Run the crash suite**

```bash
pytest -q tasks/recoverable-event-bridge/tests/test_outputs.py -k 'restart or crash or failpoint'
```

Expected result: every failpoint and stop boundary recovers with zero test
failures and no infrastructure exceptions.

### Task 5: Stream semantic replay and final output

**Files:**
- Modify: `tasks/recoverable-event-bridge/solution/bridge.py`
- Modify: `tasks/recoverable-event-bridge/tests/reference.py`
- Test: `tasks/recoverable-event-bridge/tests/test_outputs.py`

- [ ] **Step 1: Extend the independent model for state-digest expectations**

Keep `reference.py` independent from the SQLite schema. Add only helpers that
calculate expected source and logical journal digests from the input records;
do not import functions from `solution/bridge.py`.

- [ ] **Step 2: Implement SQL-backed transaction replay**

Iterate journal rows grouped by transaction and operations sorted by
`(commit_no, txn, input_offset)`. Preserve every existing sequence, conflict,
cutover, quarantine, and duplicate-operation rule while writing canonical
NDJSON records incrementally to temporary files.

- [ ] **Step 3: Run the complete local verifier suite**

```bash
pytest -q tasks/recoverable-event-bridge/tests/test_outputs.py
```

Expected result: all public, hidden, large, stop/resume, crash, idempotence,
and security tests pass.

### Task 6: Resource calibration and verifier isolation

**Files:**
- Modify: `tasks/recoverable-event-bridge/tests/test_outputs.py`
- Modify: `tasks/recoverable-event-bridge/tests/test.sh`
- Modify: `tasks/recoverable-event-bridge/README.md`

- [ ] **Step 1: Apply a calibrated address-space limit only to the large test**

Use the existing subprocess pre-exec hook to apply a disclosed, generous
`RLIMIT_AS` to the submitted process. Record the clean reference solution's
peak and margin in the README; do not use a wall-clock threshold.

- [ ] **Step 2: Add hostile artifact and state-path checks**

Reject symlinks, writes outside the worker output tree, modified input files,
and missing/invalid state digests. Keep verifier logs protected and preserve
temporary stdout/stderr capture and process-group cleanup.

- [ ] **Step 3: Document the difficulty, solution, verification, and relevant
experience sections**

Describe the incremental recovery problem and exact behavioral checks in
first-person factual prose, without claiming unrun model results.

- [ ] **Step 4: Run static checks and task-local controls**

```bash
wsl.exe -d Ubuntu-22.04 -- bash -lc 'source /mnt/e/JOB/klavis-terminal-bench/artifacts/environment/runtime-env.sh && cd /mnt/e/JOB/klavis-terminal-bench && python scripts/check_static.py'
```

Expected result: 25/25 static checks pass.

### Task 7: Freeze and requalify the changed task

**Files:**
- Create: `artifacts/local/frozen/<new-timestamp>/recoverable-event-bridge/`
- Create: `artifacts/validation/recoverable-event-bridge-durable-streaming.json`

- [ ] **Step 1: Commit the implementation and tests**

```bash
git add tasks/recoverable-event-bridge docs/superpowers/specs/2026-09-28-recoverable-event-bridge-durable-streaming-design.md docs/superpowers/plans/2026-09-28-recoverable-event-bridge-durable-streaming.md
git commit -m "feat: require durable streaming event bridge recovery"
```

- [ ] **Step 2: Freeze from the committed task tree**

Exclude runtime caches, copy every task file byte-for-byte, and record the
source commit, file inventory, and Harbor dirhash. Use the frozen path for all
subsequent commands; do not run controls against the mutable task directory.

- [ ] **Step 3: Run Harbor oracle and nop with explicit absolute jobs directory**

Record oracle reward 1.0 and nop reward 0.0, both with zero exceptions and the
same `task_checksum` as the frozen manifest.

- [ ] **Step 4: Run a fresh implementation-rubric review**

Prepare a new review config from the frozen path, run the configured reviewer,
and inspect all 35 outcomes. Treat any reviewer authentication/quota failure
as missing evidence, not a pass.

- [ ] **Step 5: Run standard and cheat trials only after controls pass**

Use the current configured model substitutions and record every trial's
trajectory, CTRF, reward, exception, runtime, and exact checksum. Do not mix
results from earlier checksums.

