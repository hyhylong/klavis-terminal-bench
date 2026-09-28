# Recoverable Event Bridge Durable Streaming Design

## Goal

Make the task's essential difficulty depend on a real incremental recovery
problem: a correct implementation must scan a large segmented stream with a
bounded frame buffer, persist enough state to resume after a hard process
kill, and publish the same exact result as the independent replay model.

## Why This Changes the Difficulty

The current reference reads the complete concatenated stream into memory and
replays it again after a stop. That is a valid parser exercise, but it does
not require durable incremental recovery. The revised contract makes the
recovery state observable through exact checkpoint and state-digest checks and
tests restart after failures at journal, checkpoint, and output-publish
boundaries. A solution that only rescans the input or keeps the whole stream
in memory cannot satisfy the contract under the hidden workload and memory
limit.

## Contract Changes

The public contract will retain the existing frame, transaction, cutover,
ordering, output, and idempotence semantics. It will add these requirements:

1. Input is read in chunks from the manifest-listed segments. The program may
   retain one bounded frame buffer, but must not concatenate the whole stream
   in memory.
2. The output directory contains an internal `.bridge-state/` directory. Its
   contents are implementation-private but must survive a stopped run and may
   be removed after a complete publish.
3. `checkpoint.json` contains `schema_version`, `offset`, `frames_scanned`,
   `source_sha256`, `journal_sha256`, and `complete`. `offset` and
   `frames_scanned` describe the last journal transaction known to be durable.
4. A restart validates the source digest and journal digest, discards any
   journal tail after the durable checkpoint, and continues at `offset`.
   Replaying an already durable frame must be idempotent.
5. The optional `BRIDGE_FAILPOINT` test variable accepts `after_journal`,
   `after_checkpoint`, or `after_publish`. At the selected boundary the
   program exits nonzero after flushing the corresponding durable state. The
   verifier may also send SIGKILL at those boundaries.
6. The implementation must stay within the verifier's disclosed address-space
   limit on the large hidden fixture. The limit is calibrated with a correct
   implementation and is not the sole difficulty signal.

The existing `--stop-after-frame N` hook remains public. It must commit the
same journal/checkpoint state before returning status 75 for an incomplete
stop.

## Architecture

The reference solution will use only Python's standard library. A streaming
segment reader exposes a logical byte stream without joining segments. A
bounded scanner carries at most the maximum frame payload plus framing bytes
between reads and emits `(offset, payload, wire_reason)` records.

Each emitted record is appended to a SQLite database in `.bridge-state` using
one transaction. The database stores frame offsets, payloads, wire quarantine
records, transaction membership, and the last durable checkpoint. The append
transaction and checkpoint update are committed together. On restart, rows
with offsets beyond the checkpoint are removed before scanning resumes.

After scanning reaches EOF, SQL iteration reconstructs transaction decisions
in commit order and streams canonical event and quarantine rows into temporary
files. A final manifest, checkpoint, and the two NDJSON files are published
with replace-and-fsync ordering. A publish marker makes a repeated complete
run byte-idempotent and lets recovery remove an interrupted temporary publish.

The verifier's `reference.py` remains an independent, simple replay model for
small and large fixtures. It does not import the solution or the journal
schema. It computes expected bytes from the logical input stream and compares
the public outputs plus checkpoint and state digests.

## Fixtures and Verification

The fixture builders will remain byte-identical. In addition to the existing
semantic and wire cases, the hidden large fixture will contain several
megabytes of small frames spread across many segments, interleaved
transactions, commit-before-event delivery, duplicate operations, conflicts,
cutovers, and corrupt frames. Its size is large enough that a complete
`read_bytes()` implementation exceeds the disclosed memory limit while a
bounded streaming implementation has a wide margin.

Tests will cover:

- clean large-fixture replay against the independent model;
- stop and restart at byte, frame, transaction, and cutover boundaries;
- SIGKILL or failpoint recovery after journal append, checkpoint commit, and
  output publish;
- corrupted or truncated journal tails and checkpoint digest mismatches;
- repeated complete runs with byte-identical public outputs;
- read-only input and protected verifier logs;
- no symlinks, process escapes, or writes outside the worker output tree.

Each crash test first records the expected output from a clean run, then
interrupts the submitted process, restarts it, and compares all public bytes,
the complete checkpoint, the journal digest, and the independent replay
result. Infrastructure failures are reported separately from a wrong answer.

## Non-goals

The task will not require a particular database schema, source-code pattern,
library outside the standard library, or an arbitrary wall-clock threshold.
The verifier will test behavior and calibrated resource usage rather than
matching implementation text.

