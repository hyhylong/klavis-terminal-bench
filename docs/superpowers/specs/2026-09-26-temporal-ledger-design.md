# Temporal ledger repair design

The user authorized implementation on 2026-09-26. The selected design is an original CPU-only data-recovery task: reconstruct historical entitlement timelines from a delivered CDC journal. The alternative build-cache repair task would need a larger starter repository; SQLite forensics would risk being solvable by a standard recovery utility. This design makes arrival order, atomic publication, source order, valid time, and retroactive correction independently observable.

## Deliverable

One Harbor task, `tasks/temporal-ledger-repair`, containing an explicit protocol, deterministic input journal and requested cutoffs, task metadata, agent environment, reference solution, and a separate verifier image. The submitted artifact is `/app/output/reconstruction.json`; the verifier parses data and never executes agent-produced code.

## Core behavior

At each delivery cutoff, classify transactions using only the received prefix. Deduplicate identical fragments, quarantine conflicting fragments, enforce commit seals and schema availability, and expose only complete committed transactions. Resolve eligible historical amendments before replaying ordinary rows in their original commit slots. Materialize half-open intervals with PUT/PATCH/DELETE, schema-defined defaults and codecs, per-field provenance, explicit tombstones, and provenance-sensitive coalescing.

The authoritative task contract is `tasks/temporal-ledger-repair/environment/spec/protocol.md`. Both implementations consume it independently. Oracle uses interval splitting and ordered mutation. Verifier uses elementary intervals and independent pointwise replay. Small hand-calculated fixtures plus metamorphic and mutation checks cross-check both.

## Evidence and scope

Runtime setup and upstream CI extraction run independently. Pin upstream commit and Harbor version. Run static checks, build both images, oracle reward 1 and nop reward 0. Record rubric, standard, cheat and trajectory analysis separately, never count infrastructure errors or timeouts as model failures. User selected Codex plus the permitted DeepSeek substitution. No result may be invented when credentials or model access are missing.

## Security

Ground truth and verifier logic only enter the separate verifier image. The agent image has the protocol and inputs only. Strict JSON parser rejects duplicate keys, non-finite numbers, oversized artifacts and extra schema fields through exact structural equality. Verify data types without Python bool/int equivalence. Agent container is torn down before trusted validation; only the declared JSON artifact crosses the boundary.

## Completion requirements

- Original task and all protocol behaviors implemented and exercised.
- Independent oracle/verifier agreement on hand fixtures and generated cases; faulty outputs rejected.
- All pinned required static checks pass; Docker, Harbor oracle and nop evidence captured.
- Required model trials and reviews completed on a frozen task with genuine results and failure analysis.
- Reproducible repository and honest author/review metadata ready for submission; external publishing requires the requested repository destination.

The exact 0/3 model outcome is an empirical requirement, not assumed from the design. If a model succeeds, inspect its trajectory and improve substantive task quality without changing the verifier to reject valid solutions.
