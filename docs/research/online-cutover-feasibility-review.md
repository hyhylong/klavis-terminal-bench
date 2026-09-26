# Online cutover feasibility review

Independent local review, 2026-09-26 UTC. This is authoring evidence, not a model
trial or a qualified difficulty result. Reference application and test files
were not edited. Exact reviewed hashes, probe outcomes and timings are in
`artifacts/environment/cutover-runtime/review-probe.json`; the sanitized runtime
summary is `artifacts/validation/cutover-runtime.json`.

## Reference crash and routing assessment

No concrete committed-state loss was found in the reviewed reference. The target
session advisory lock serializes migrators. Initial copying runs outside the
source writer fence. Refresh commits target data before deleting precisely the
observed source change IDs, preserving an uncommitted lower sequence and allowing
replay after a lost acknowledgement. Final draining occurs behind the source
fence; target activation commits before releasing it. A source request rechecks
target activation after obtaining its shared fence. Startup and an already-active
migration use target state without requiring the retired source.

These observations concern `migrate.py` lines 95–170 and `backend.py` lines
146–162 as reviewed. They are not a proof for arbitrary failures. In particular,
new commit-acknowledgement and protocol fault tests being authored concurrently
were outside this probe's four executed scenarios.

## Shorter legal migration passes the current scenarios

A disposable 19-line controller replaced only the migration orchestration in
memory. It used unchanged `copy_snapshot` (33 lines), `is_active` (3 lines), and
`ensure_routing` (8 lines): approximately **63 physical lines for coordination,
copying and routing initialization**, in addition to the existing business
service/API. It did not use capture triggers, a change queue or sequence numbers.

Its algorithm is: acquire the target migration coordinator; exit if active; make
an initial full copy outside the source fence; acquire the source fence; make a
fresh full copy; commit target activation; release the fence. On a crash before
activation, repeat. On a crash after activation, use the durable target flag.
The unchanged service still supplies source fencing and idempotent receipts.

It passed all three original `CutoverChecks` and the delayed-commit ordering test:
source retirement and receipt replay; live changes while initial backfill is
blocked; killed/concurrent migration restart; and delayed low-sequence commit.
Final fence durations on the three small original fixtures were **10.12, 12.55,
and 13.52 ms**. These timings measure successful fence acquisition through target
activation, not acquisition wait or HTTP latency. They do not establish behavior
at arbitrary data size or sustained write rates.

This is concrete evidence that the present semantic contract and small tests do
not require CDC bookkeeping. A large-data outage measurement could distinguish
this strategy on a meaningful published workload; an undisclosed algorithm ban
or a timer selected merely to reject it would be unfair. The current reference
migration is 170 lines, and its business/backend, transport and validation add
291 lines. The experiment is a moderate cross-component exercise; there is no
evidence yet that it meets the requested frontier-model difficulty.

## Representation-specific blocker can reject valid alternatives

The reviewed initial `test_cutover.py` requires an observed PostgreSQL lock wait
(lines 194 and 223), then asserts that the service is still on source. The public
contract allows extra private relations and does not prescribe a physical layout.
A legal implementation that finishes without using the blocked physical relation
would fail those phase assumptions even if all API and SQL outcomes were correct.

The concrete SQL probe renamed the target line storage to `app.stored_lines` and
exposed all declared `app.order_lines` columns through a SECURITY INVOKER,
function-backed view. While another connection held `LOCK TABLE app.order_lines
IN SHARE MODE`, an insert into the actual storage completed and was visible
through the public relation. Thus the selected public lock is not a universal
backfill barrier for permitted representations. This was a representation probe,
not a complete alternative application.

Treat a missing blocked phase as coverage information, release the barrier in a
bounded way, and inspect final business outcomes. The newer ordering test already
uses this approach. Its separately documented receipt-placeholder limitation
(extra mandatory private columns can prevent the fixture INSERT) must likewise
remain a setup incompatibility until the public SQL test interface is settled.

## Runtime and trust qualification

The runtime suite passed 11 checks, with a further targeted transactional-inspector
regression passing after its fix. Application roles can use TEMP tables and own
their business schema; they cannot retire databases or read server files. Use
`inspect_connect()` for artifact-controlled business relations, since a superuser
SELECT can execute a malicious view's invoker function. Administrator connections
belong only in trusted bootstrap, catalog monitoring and lifecycle code.

The default role remains NOREPLICATION. The separate native-decoding probe proved
that a REPLICATION grant also permits database-mode physical-slot creation and
BASE_BACKUP despite physical-mode HBA rejection, and exposes table changes beyond
SELECT ACLs. No expected values or privileged secrets may reside inside such a
cluster if that broader route is offered. Full detail is recorded in
`artifacts/environment/cutover-runtime/logical-permissions.md`.
