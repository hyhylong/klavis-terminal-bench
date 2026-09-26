# Online order-service cutover: feasibility design

Status: original v3 feasibility experiment, not a qualified task. The user has
authorized continued local implementation informed by failure research. This
continues that scope; it does not authorize publishing, inventing an author, or
claiming difficulty without trials. Both preceding candidates were solved.

## Decision and stop conditions

Try a real PostgreSQL service migration with ongoing requests. The alternatives
are another storage-library repair (already contradicted twice) and global
production planning (credible but easily reduced to a standard CP-SAT model).
The current official cutover failure signal supports investigation, not an
expected failure rate for this different task.

First implement the simplest correct reference and an independent verifier in
`experiments/online_cutover/`. Do not package another benchmark until genuine
cross-component obligations, reproducible schedules and generous resource
margins have been demonstrated. A short legal solution is welcome evidence;
do not ban libraries or tighten limits after observing a successful pilot.

## One business operation, two representations

The service manages synthetic orders and shared inventory. The existing source
database stores each order's line items as JSON; the destination exposes orders
and ordered line items as normalized SQL relations. Both include inventory and
request receipts. One trusted PostgreSQL cluster hosts two databases, owned by
the trusted administrator, with a restricted application role owning only the
business schemas. Source retirement disables that database and terminates its
connections while the destination remains available.

Each order has an ID, customer, integer revision, and an ordered nonempty list
of distinct SKU lines. A line contains a SKU, positive integer quantity and
nonnegative integer unit price in cents. SKU inventory has fixed capacity and
current available units. The invariant is capacity minus quantities reserved
by existing orders. Deleting an order releases its reservations. Recreating a
deleted ID is allowed. The public API serializes each mutation atomically.

Requests use JSON over a local HTTP service. The supported commands are:

* `create(request_id, order_id, customer, lines)`;
* `replace(request_id, order_id, expected_revision, customer, lines)`;
* `delete(request_id, order_id, expected_revision)`;
* `get(order_id)`, `inventory()`, and `health()`.

Every mutation records its exact validated request and response in the same
database transaction as its business effects. An identical request ID returns
the original response even after later mutations. Reusing it with different
content returns a request-conflict response without replacing its receipt.
Business rejections are also durable receipts. Missing orders, stale revision,
duplicate orders and insufficient stock have explicit precedence and response
schemas in the API contract written before implementation. Input-validation
errors occur before receipt creation. Money never uses floating-point values.

`get` returns either the complete order or an explicit missing response.
`inventory` returns the complete sorted stock state from one committed view.
Concurrent operations may return any result consistent with serial execution
and real-time ordering. Tests must not equate request-send order with commit
order. Business data, receipts and routing state must survive process restart.

## Deliverable and lifecycle

The eventual submission is a Python package containing the existing service
plus its migration implementation. The public commands start the HTTP service
and run an idempotent migration CLI. Both receive explicit source/destination
DSNs and listen addresses; no hidden environment discovery is required.
Migration runs independently from request-serving processes and can be killed
and restarted. More than one migration invocation must not corrupt state.

Initially reads/writes use the source. During backfill they must continue to
make progress. Successful migration switches new and already-running service
instances to the target. Restarting all application processes with empty local
working directories must preserve the result; durable metadata belongs in the
databases. After the trusted driver disables the source database, requests and
idempotent migration retries must operate from the target alone.

The final destination SQL interface is normative and independently inspected.
Its exact schema and readable response shapes will be written before coding;
internal replication records, algorithms and phases are implementation choices.
Any equivalent method using the published capabilities is accepted, including
triggers, outbox records or library assistance. Native logical replication is
an additional authoring investigation: the present prototype has not granted
replication privileges and must not promise that route until it is supported
and its trust boundary verified.

## Minimal reference hypothesis

Try transactional change capture, a consistent initial copy, idempotent
refresh of changed business keys and receipts, then a brief writer fence to
finish synchronization and publish durable routing. Transactional sequence
allocation is not commit order; an uncommitted low sequence must not disappear
behind a larger copied watermark. Target data commit must precede retiring
source change records. Concurrent migration processes require coordination.

Every source writer must participate in the cutover boundary, including a
request that chose its backend before waiting on another transaction. A target
activation record committed immediately before a migration crash must not
allow such a stale writer to acknowledge an uncopied source mutation. Requests
with unknown outcomes converge by retrying their existing request IDs.

These are implementation hypotheses for the author, not hidden requirements or
solution instructions for the evaluated model. If the simplest approach
satisfies the public contract, accept it.

## Reproducible verification

The verifier initializes fresh, trusted databases from its own synthetic seeds
and copies only the submitted package. It never inherits an agent database.
A separate pure Python business model checks deterministic request histories;
small concurrent schedules enumerate legal serial outcomes. Independent SQL
reads check target relations, totals and request receipts.

Use PostgreSQL locks and client barriers to construct observable schedules,
rather than hoping a random sleep hits a race. For example, hold a target table
lock that blocks backfill writes and replacement of that table, start the
migration, and require unrelated source requests to complete before releasing
it. This tests continued service without prescribing a replication mechanism.
Other schedules cover committed updates/deletes/recreation around the copy,
delayed source commits, killed migration processes, request retries across
cutover, concurrent migration starts, and source retirement.

Allow a documented retry response during the final cutover boundary. Measure
reference latency and a naive full-copy-under-fence baseline before publishing
any numeric outage/latency limit. Do not use a tight timer merely to make the
task difficult. If robust progress conditions cannot distinguish acceptable
online behavior without a fragile timer, revise or abandon this design.

Add targeted invalid implementations: lost low-sequence commit, checkpoint
before target commit, omitted receipts, stale backend choice, partial order
application, global write lock during blocked backfill, and dependence on the
retired source. Each must fail an observable requirement. Oracle/nop and these
mutations are quality checks, never evidence of model difficulty.

## Trust boundary and runtime

Root controls tests, expected values, database lifecycle and reward. Protect
`/tests` and `/logs/verifier` with mode 700 before executing submitted code.
PostgreSQL runs under its own UID. Submitted code runs under a different
unprivileged UID and can authenticate only as the restricted application role;
it cannot gain database ownership, superuser, server-file access or SQL program
execution. Admin authentication and credentials must remain inaccessible.

Use fresh process groups, file-backed stdout/stderr capture, explicit resource
limits and cleanup. The submitted package cannot modify trusted Python imports
or startup files. A known-good trusted preflight checks runtime and role
boundaries before grading, with no reward on platform failure. Hostile fixtures
probe expected-answer reads, reward writes and PostgreSQL privilege escalation.
Passing them does not establish a security proof.

Prefer a digest-pinned supported PostgreSQL 17 Bookworm image and a pinned
Python driver, all installed at build time. No broker, Kubernetes, extra cloud
account, privileged container or runtime network download is needed. Initial
calibration target is 2 CPUs and 4 GiB; final resources and timeouts depend on
measurement. Reuse the verified Codex setup only with its runtime adaptation
explicitly recorded. Preserve all old candidates and their successful trials.

## Qualification after feasibility

Only after the reference, independent verifier, controls and generous resource
margin work should the task be packaged and frozen. Run one genuine Codex
pilot first. A normal success invalidates the required all-fail matrix for
that candidate; do not hide it or rewrite the contract mid-run. A failure must
be traced to a task defect in the submitted solution rather than infrastructure
or a verifier issue before investing in the full two-model matrix.

Real author metadata, four human-authored README sections, the pinned static
checks, all 35 rubric criteria and eventual repository delivery remain separate
requirements. No current design decision supplies those missing artifacts.
