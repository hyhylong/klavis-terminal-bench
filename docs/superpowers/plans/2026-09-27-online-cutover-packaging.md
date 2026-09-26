# Online order cutover: candidate packaging plan

Status: approved local continuation of the existing assignment, not a qualified
submission. This follows the feasibility design and the user's repeated request
to continue. No publication or invented author metadata is authorized.

## Evidence and decision

The first combined run passed 61 authoring checks in 122.014 seconds with real
PostgreSQL, two CPUs and 4 GiB. It includes independent model/SQL checks, lost
COMMIT acknowledgements and a delayed-commit counterexample that the first three
integration checks missed. The ordinary progress control handled 33 requests
with a maximum observed latency of 0.027693 seconds; holding the source writer
gate during a blocked initial copy reproducibly prevented service progress.

A shorter double-copy solution is valid under the current contract. Its 19-line
controller reuses 44 lines of helpers and the existing complete service; it is
not a 19-line complete task solution. It passed four small schedules. Accept
this algorithm. Do not add a CDC requirement, larger inputs or a tighter timer
to exclude it. There is no evidence yet that the new task meets model difficulty.

Proceed with a reviewable experimental package whose supplied legacy service
implements only source behavior. Target normalization, routing across processes,
migration and recovery must be delivered together. The starter must not include
the correct target router/fence/migration and leave only two localized bugs.
One honest Codex pilot decides whether further qualification is justified.

## Files and ownership

Candidate: `tasks/online-order-cutover`, deliverable `/app/orderbridge` only.

- Environment owner: portable pinned Dockerfiles, public fresh-database harness,
  source-only legacy package and public smoke driver. No reference or private
  expected results in the agent image. No runtime downloads.
- Verification owner: trusted independent model, public SQL readers, black-box
  service/cutover schedules and platform preflight. Root never imports submitted
  modules; application and PostgreSQL have distinct unprivileged OS identities.
- Root: contract/instruction/metadata/README placeholders, reference solve script,
  artifact transport, independent integration review and actual Harbor controls.

Any copied shared controller/schema must be byte-identical between public and
private contexts unless an explicit difference is documented. Keep development
mutants and research evidence outside the task directory.

## Before a pilot

- [x] Adapt target-lock observation: completed correct alternatives are accepted;
  missing observed phases lower coverage rather than fail correct solutions.
- [x] Specify the SQL fixture interface explicitly, including a rolled-back
  receipt INSERT, or exclude that schedule from scoring until supported fairly.
- [x] Preserve all normal valid alternatives, including full double copy.
- [x] Publish generous process/request bounds and exact available dependencies.
- [x] Run submitted code only as the application UID; protect `/tests` and
  `/logs/verifier` with 0700 before any execution and use private file capture.
- [x] Inspect application SQL as the application role, with read-only bounded
  queries; never execute an application view/function with admin privileges.
- [x] Use only independent public-contract tests for reward. Reference-specific
  routing activations and direct Python validation-unit imports stay in authoring.
- [x] Build both images, run reference and starter directly, verify listed hostile
  artifact probes cannot read expected results or forge reward, and run the legitimate
  double-copy alternative through the packaged verifier.
- [x] Run pinned static checks; missing real author data remains a reported fail.
- [x] Freeze exact files, then run Harbor oracle/nop on the same snapshot.
- [x] Launch one genuine Codex pilot. Preserve any success or infrastructure
  failure; do not reinterpret it as a model failure or alter the frozen task.

## Remaining qualification

A passing oracle and failing starter are implementation checks, not difficulty.
Only after a genuine task failure has been analyzed should the two-model
three-attempt matrix and meaningful cheat attempts proceed. The 35-criterion
implementation review can run alongside the first pilot to identify independent
contract/verifier problems before any further model trials.
Author identity and four human-authored README sections remain human input.
No current evidence resolves those requirements.

2026-09-27 checkpoint: frozen Harbor checksum
`96461fe05ddf2c6b2aac03e9cbcf440aa94a61e08d90900590b857dc92c5ce3a`;
oracle23/23 reward1, nop9/23 reward0, both no exceptions. Packaged legal
double-copy23/23 reward1. Frozen permission probes passed; missing trusted model
produced infrastructure exit70 with no reward. Static24/25 (real author GitHub
missing). Pilot and independent rubric review running; difficulty unassessed.
