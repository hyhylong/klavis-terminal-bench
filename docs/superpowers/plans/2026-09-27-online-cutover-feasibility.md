# Online cutover feasibility implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish an original online order-service migration reference and
independent deterministic verification before investing in another task pilot.

**Architecture:** A Python HTTP service uses source JSON orders or normalized
target orders in two real PostgreSQL databases. A separate migration process
copies and synchronizes state while requests continue. Trusted tests create
fresh databases, compare an independent business model and SQL relations, and
own process/permission boundaries.

**Tech Stack:** Digest-pinned PostgreSQL 17.11 Bookworm, Python 3.13.15,
psycopg 3.3.6, standard-library HTTP/client/testing and Linux process controls.

## Boundaries and work ownership

The normative feasibility API is `experiments/online_cutover/CONTRACT.md`.
The design is `docs/superpowers/specs/2026-09-27-online-cutover-design.md`.
Old tasks and frozen trials remain untouched. The first milestone contains no
new task package, deadline, performance score or claim of model difficulty.

* `model.py`: independent in-memory business oracle; never imported by service.
* `orderbridge/api.py`: public shape/type validation and response construction.
* `orderbridge/backend.py`: transactional source/target business operations.
* `orderbridge/service.py`, `__main__.py`: HTTP/CLI transport and lifecycle.
* `orderbridge/migrate.py`: reference change capture, copy and cutover.
* `runtime.py`, `Dockerfile`, `schema.sql`: trusted development-only fresh PG
  startup, roles, schema provisioning and cleanup; never submitted application.
* `test_model.py`, `test_service.py`, `test_cutover.py`: domain, SQL and lifecycle
  checks. Tests read public SQL independently of application adapters.

## Task 1: Close contract and test the business oracle

- [x] Specify command names, response shapes, receipt precedence and SQL interface.
- [x] Review concurrent correctness and validation boundaries for contradictions.
- [x] Write manual golden tests: inventory release/re-reservation, failed writes,
  exact and conflicting retries, historical receipt replay and ID recreation.
- [x] Implement `model.py` independently from SQL service implementation.
- [x] Run golden tests and randomized invariant checks; 17 tests pass, with
  12 seeds and 1,800 fresh mutations plus receipt replays.

## Task 2: Make fresh trusted PostgreSQL provisioning reusable

- [x] Prove pinned PostgreSQL/Python/driver runtime and separate cluster identity.
- [x] Convert the disposable proof into `runtime.py` and a portable Dockerfile;
  initialize two administrator-owned databases with application-owned schemas.
- [x] Explicitly test only necessary trigger/DDL privileges and reject database
  ownership, superuser, file/program execution and admin authentication.
- [x] Use private test/log directories, distinct PG/application UIDs, file output
  capture, process groups and cleanup; make environment failure diagnostic.
- [x] Prove a fresh run needs only code plus trusted seeds, not prior PGDATA.

## Task 3: Implement existing service behavior in both representations

- [x] Write SQL/service golden tests before implementation (the separate oracle
  was developed independently, not imported into service code).
- [x] Implement validation and source/target transactions, with receipt and order
  conflict coordination and consistent inventory lock ordering.
- [x] Expose the public HTTP/CLI interface; limit bodies and return exact errors.
- [x] Verify reads are one committed view, retries preserve historical responses,
  and concurrent same-ID requests cannot apply twice.
- [x] Compare business/receipt SQL relations independently in the service checks.

## Task 4: Implement the simplest correct migration

- [x] Write the no-writer migration/retired-source test before the migration
  implementation; dependencies were not ready for a meaningful RED execution.
- [x] Install transactional key capture without losing changes during setup.
- [x] Copy a consistent source view, normalize lines and include receipts.
- [x] Refresh captured keys idempotently; target commit precedes source cleanup.
- [x] Coordinate multiple migrators and publish target activation behind a writer
  fence honored by existing and newly starting request processes.
- [x] Verify restart and source retirement with empty local working directories.

## Task 5: Exercise online behavior and failures

- [x] Hold a target relation lock and require source requests to continue while
  backfill is blocked; release it and verify final SQL plus API results.
- [x] Add create/replace/delete/recreate and receipt replay around that schedule.
- [x] Kill/restart a copying migrator and run two concurrent migration commands.
- [ ] Design delayed-commit/stale-route barriers from observable SQL behavior;
  do not add hidden solution-specific phase assumptions.
- [ ] Show deliberately invalid implementations fail the intended obligation,
  including target checkpoint-before-commit and lost low-sequence changes.

## Task 6: Decide whether to package

- [ ] Review the complete simplest solution and actual repair/build surface.
- [ ] Measure correct and naive baseline service interruption across repeated runs.
- [ ] Reject timing-dependent tests without generous reference margin.
- [ ] Review trust boundaries with hostile artifacts and independent reviewers.
- [ ] If the experiment has a substantive, fair challenge, write a separate
  packaging plan with public examples and precise resources. Otherwise record
  the counter-evidence and reassess the direction before more model runs.

Verification commands and exact run manifests will be recorded when runtime
paths are established. Do not report unexecuted tests as passing. Preserve
intermediate failures and distinguish authoring bugs from candidate-model errors.
