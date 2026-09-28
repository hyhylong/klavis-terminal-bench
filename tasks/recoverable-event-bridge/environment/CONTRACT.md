# Recoverable event bridge contract, version 1

The program is `/app/bridge.py`. It must run with `python /app/bridge.py
--input /app/input --output /app/output`. It may also accept
`--stop-after-frame N`, a public test hook: after scanning N frames (valid or
corrupt), it must persist a resumable state and exit with status 75. A normal
run without that option must resume and finish. The hook is not required for a
normal run, and a program may finish earlier if its durable result is already
complete.

The input directory contains `manifest.json` and a `segments/` directory. The
manifest has exactly `{"schema_version":1,"segments":[...],"stream_sha256":"..."}`.
Concatenate the named segment files in listed order. Their bytes are one stream;
do not treat a segment boundary as a frame boundary. Input is read-only.

## Frames

Every frame is `MAGIC + LENGTH + PAYLOAD + CRC32`, where `MAGIC` is four ASCII
bytes `EVB1`, `LENGTH` is an unsigned little-endian 32-bit payload length, and
`CRC32` is an unsigned little-endian CRC-32 of the payload bytes. Payload is
UTF-8 JSON with no duplicate keys. Valid payloads are objects with `kind`:

* `event`: `txn`, `event_id`, `tenant`, `stream`, `seq`, `op`, and `value`.
  `op` is `upsert` or `delete`; `seq` is a positive integer; `value` is an
  object for `upsert` and null for `delete`.
* `commit`: `txn`, `commit_no`, `event_ids`, and `digest`. `event_ids` is a
  nonempty array of strings. `commit_no` is a positive integer. `digest` is
  lowercase SHA-256 hex of the UTF-8 bytes of canonical JSON
  `{"events":[<event object sorted by event_id>]}` using sorted keys,
  separators `(',', ':')`, and `ensure_ascii=false`.
* `abort`: `txn`.
* `cutover`: `txn`, `commit_no`, `tenant`, `stream`, `from_seq`, `to_seq`, and
  `digest`. It advances one stream frontier without emitting an event.

All identifier strings (`txn`, `event_id`, `tenant`, and `stream`) are
nonempty. A cutover advances or preserves its frontier, so `to_seq` must be
greater than or equal to `from_seq`.

Frames may be interleaved across transactions and streams. A frame with a bad
CRC, an invalid length (`0` or greater than `65536`), a truncated header/body,
invalid UTF-8, invalid JSON, or invalid magic is quarantined. A truncated
header/body is reported as `truncated_frame`; an invalid declared length is
reported as `invalid_length`. On a bad CRC or invalid payload, resume scanning
at the next byte after the frame's magic/declared body; otherwise scan forward
to the next occurrence of `EVB1`. The quarantine offset is the absolute byte
offset in the concatenated stream. A corrupt frame must not hide a later valid
frame.

## Transaction and sequence semantics

Collect valid event/commit/abort/cutover frames before applying operations.
Identical repeated event frames in the same transaction are idempotent. A different event
with an already-used `event_id` in that same transaction makes that transaction
invalid; event IDs may be reused by different transactions. An aborted
transaction is invalid. Apply valid operations in increasing `(commit_no, txn)`
order, with input order as the final tie breaker. A normal commit is valid only
if its event IDs exactly equal the transaction's unique events, its digest
matches, and every event advances its `(tenant,stream)` sequence by exactly one
from the last accepted sequence. Events within one transaction are checked by
`(tenant, stream, seq, event_id)` order. A cutover is valid only when its digest
is the lowercase SHA-256 of canonical JSON
`{"cutover":{"from_seq":...,"stream":...,"tenant":...,"to_seq":...,"txn":...}}`
and the current sequence frontier for that tenant/stream equals `from_seq`; it
then sets that frontier to `to_seq` without emitting an event. A transaction
may contain commits or cutovers, but not both. Repeating the exact cutover
operation is idempotent after the transaction is applied; differing cutovers
with one transaction conflict.

An invalid operation contributes one quarantine record with `offset` equal to
the operation frame offset, `reason` equal to one of `aborted`,
`conflicting_event`, `conflicting_cutover`, `event_set_mismatch`,
`digest_mismatch`, `sequence_gap`, `mixed_operation`,
`cutover_digest_mismatch`, or `cutover_sequence_gap`, and `txn`. Events from
invalid transactions are never output. A transaction without a commit or
cutover is ignored, even when it contains an abort record. A duplicate valid
operation is ignored after its transaction has already been applied.

Wire-level quarantine records use `invalid_magic`, `invalid_length`,
`truncated_frame`, `bad_crc`, `invalid_utf8`, `invalid_json`, or
`invalid_payload`; they contain only the absolute `offset` and `reason`.

## Output and persistence

Create `/app/output/events.ndjson`, `quarantine.ndjson`, `checkpoint.json`, and
`manifest.json`. Each non-empty NDJSON file ends with `\n`; an empty result is
represented by a zero-byte NDJSON file. Events are canonical JSON
objects sorted by `(tenant, stream, seq, event_id)` and contain exactly the input
event fields plus `commit_no`. Quarantine objects are sorted by `(offset,reason)`
and contain the fields defined above. Use sorted keys and compact JSON for every
output object. `checkpoint.json` must have `schema_version`, `offset`,
`frames_scanned`, and `complete`; a complete run has the concatenated byte
length, the number of scanned frames, and `complete: true`. A stopped run has
`complete: false` and a checkpoint offset that permits a later run to finish.

The output manifest has exactly `schema_version`, `accepted_count`,
`quarantine_count`, `events_sha256`, `quarantine_sha256`, and `complete`.
The two digests are SHA-256 of the exact UTF-8 bytes of their corresponding
NDJSON files. A successful run is idempotent: running it again in the same
output directory leaves the same bytes and counts.

The verifier may remove temporary files, run the stop hook, restart the program,
and run it repeatedly. Temporary files and internal state are not part of the
required public output. The verifier compares the complete output to an
independent replay model; it does not require a particular implementation or
checkpoint layout.

Public smoke command:

```text
python /app/bridge.py --input /app/input --output /app/output
```
