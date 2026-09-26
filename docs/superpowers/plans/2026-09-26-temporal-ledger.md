# Temporal Ledger Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement bounded tasks and independent review. The user has authorized continuous implementation.

**Goal:** Build and validate a reproducible original Terminal-Bench task satisfying the Klavis assignment.

**Architecture:** Versioned public protocol and deterministic journal feed; interval-based oracle; independent pointwise verifier in a separate container; host-side evidence scripts.

**Tech Stack:** Python standard library, pytest, Docker, WSL2, pinned Harbor.

## Task 1: Contract and runtime

- [x] Pin upstream commit `4def1f367467b34b18e0dbdc086400ba71c3e037`, fetch only docs/scripts/workflows, summarize required gates in `docs/upstream-contract.md`.
- [x] Install pinned Harbor in an isolated Linux runtime via `scripts/setup-local.sh`; verify version and Docker smoke test, record `docs/runtime.md`.
- [x] Write design and this plan; initialize a local implementation branch with secret/runtime exclusions.

## Task 2: Public protocol and oracle

- [x] Write full journal, eligibility, amendment, interval, codec and output rules in `tasks/temporal-ledger-repair/environment/spec/protocol.md`.
- [x] Add hand-computed tests for atomic visibility, late earlier commits, amendment replay, schema waits, conflicting duplicate quarantine, tombstone/patch behavior, and provenance coalescing in `dev_tests/test_oracle.py`. Run them against an unimplemented oracle and confirm failure.
- [x] Implement `solution/reconstruct.py` using interval splitting; `solution/solve.sh` writes the declared artifact. Run hand tests to green.

## Task 3: Independent verifier and corpus

- [x] Implement `tests/reference.py` independently by partitioning time at every active operation boundary and replaying each elementary segment. Check against the same hand-computed contracts.
- [x] Build `tools/generate_corpus.py` with named regressions plus deterministic randomized transaction graphs, delivery lag, schema lag, seals, duplicates, aborts and historical amendments. Write feed and checkpoint data under `environment/data/`.
- [x] Implement strict JSON validation and exact type-aware structural comparison in `tests/test_outputs.py`; mutate values, provenance, classifications, segment boundaries and shape and confirm rejection.
- [x] Differentially compare implementations and metamorphic properties (irrelevant arrival suffix, identical duplicate delivery, independent entities, stable replay) in `dev_tests/`.

## Task 4: Harbor integration

- [x] Add `instruction.md`, `task.toml`, both Dockerfiles and `tests/test.sh` matching pinned upstream requirements, canary comments and timeout suffix.
- [ ] Run pinned `scripts/checks/check-*.sh` on this task, fix actual failures. (24/25 pass; real author metadata is still required.)
- [x] Build images and run Harbor oracle then nop with absolute task/jobs paths. Confirm rewards 1 and 0 from trial result JSON. Current LF-normalized task checksum: `44dd9c660becb8d373dd1bfbaa5bf42573dd938c31cb02e1411266ba481a2d51`.

## Task 5: Evidence and evaluations

- [x] Add reproducible commands/configuration, preflight credentials check without disclosure, and result classification that distinguishes model failures from infrastructure errors.
- [ ] Run implementation rubric and standard/cheat trials with Codex plus DeepSeek, using pinned settings and prompts, only after task content is frozen. Keep full local trajectories and sanitized result summaries.
- [ ] Review task/verifier independently, analyze actual model failures, and record unresolved gates explicitly.
- [ ] Update root README with run instructions and gate status, author metadata supplied by user, and deliver repository only when all required evidence exists.
