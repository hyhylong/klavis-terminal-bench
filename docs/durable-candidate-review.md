# Durable ledger candidate review

Reviewed on 2026-09-27: the public contract, starter, source compatibility, isolated Store adapter, independent verifier, public benchmark, and evaluation preparation. This is an implementation review, not evidence that current models fail the task.

No unresolved substantive contract/oracle/benchmark mismatch was found in the inspected revision. Two publication issues were corrected during review. Full candidate qualification and model difficulty remain separate work.

## Findings corrected during review

1. **P2 — review preparation could not consume the frozen evaluation candidate.** The former direct-child restriction in `evaluation/prepare_review.py` rejected the frozen path accepted by `evaluation/prepare_job.py:13`. Reviewing the working tree separately could associate a review with different bytes from the evaluated candidate. `evaluation/prepare_review.py:46` now permits the normal `tasks/<slug>` path or exactly `artifacts/local/frozen/<container>/<slug>`. A frozen candidate needs its sibling source manifest, matching source slug, complete file inventory, byte counts, individual SHA-256 hashes, and complete tree hash. Added, missing, modified, duplicate, and symlinked files are rejected. The frozen inventory is preserved without another cache filter and validated again after copying; its manifest/tree hashes are recorded in the review manifest. The reviewer, model settings, and all 35 rubric criteria are unchanged.

2. **P2 — freeze publication could combine independently edited source versions.** The original `evaluation/freeze_task.py` read and copied files sequentially and read HEAD afterwards without a stability check. Another agent's edits could therefore create a mixed candidate with misleading commit provenance. The root agent corrected this at `evaluation/freeze_task.py:18`: capture HEAD, inventory and bytes; recheck them; then write only the captured bytes. No output is created when the stability check fails. The Git-ignore based selection excludes the observed untracked runtime caches; tracked files remain part of Git's selected source inventory.

## Evidence and scope

- **Public API and source compatibility:** `environment/app/SPEC.md:16` defines the submitted Store methods and exact checkpoint result, ownership, retries, and durability. `STORAGE.md` defines the existing checkpoint/WAL framing, duplicate handling, incomplete-tail recovery, active-manifest selection, and retirement ordering. The verifier calls those methods through a fresh worker. It does not require starter-private index attributes or optional projection-cache layout.
- **Independent truth:** `tests/reference.py:113` and `:135` partition endpoints and replay point states. The public domain implementation uses interval mutation at `environment/app/ledgerstore/domain.py:105`. `tests/helpers.py` imports only the verifier reference for expected answers, and `tests/reference.py:208` compares exact JSON types, keys, order, values and origins. Persistence tests derive expected source history independently of the submitted storage implementation.
- **Meaningful broken starter:** rerunning the public smoke suite produced two assertion failures and two passes, with no runtime errors. Null amendment invalidation and restoring an older eligible amendment after compaction fail. The packaged reference solution passed all four identical smoke cases. This establishes a coherent repair target; it does not establish difficulty.
- **Coverage additions communicated:** rejected-arrival cases now include zero, negative, boolean, string and float arrivals, and both rejection tests compare durable bytes before/after. Nested caller ownership is exercised by recursively mutating input and returned containers in the trusted worker (`tests/test_outputs.py:56`, `:73`, `:88`). Crash sweeps cover initialization, ingest, compaction, and partial-tail recovery (`:272`, `:288`, `:317`, `:337`).
- **Benchmark fairness:** public and private `workload.py` have identical SHA-256 `a0d2fc23052cd4e216f973cc1ccc44a047b3109f1d187672b7ca21606c656505`. `environment/app/benchmark.py:23` and `tests/test_performance.py:39` time the same correction/query stream after loading, compaction and reopening. Expected answers and final snapshot checks are outside timing. The finalized public contract discloses the 32-bit varying seed, dimensions, API/FS RPC overhead, worker bounds, three-run median, and 3.0-second limit; `tests/test_performance.py:18` uses that limit. Calibration claims in SPEC are the root agent's container measurements, not measurements independently repeated by this review.

## Preparation verification

Eight inline unittest cases first failed because frozen-source validation was absent, then passed. They are now preserved in `dev_tests/test_review_manifest.py` and pass with `python -B -m unittest dev_tests.test_review_manifest -v`. They cover valid frozen and canonical sources, unrelated paths, missing/added/modified files, six manifest inconsistencies, and preservation of a manifested cache file. They do not modify implementation or verifier tests owned by other agents.

The real pinned WSL preparation completed without invoking a model or API:

- Config: `artifacts/local/review/implementation-review-codex-20260926T193634437558Z/config.json`.
- Source: `artifacts/local/frozen/durable-ledger-repair-20260926T193632171132Z/durable-ledger-repair`.
- Source and reviewed snapshot dirhash: `67b7011c64d6221ee8f0312a50e5d3b88f71cb37e8420dfec628f2d932fa858c`.
- Freeze manifest SHA-256: `e97fd2e4a9c74031f6477930c807b44f1710279e2c572130e40622cc6af4d40b`.
- Freeze tree SHA-256: `0bf9eafdf532071a489dfa81c7da299f9520b3f5c5edbd81a2fd3391e6079c96`.
- Status: `prepared_not_run`; criterion count: 35.

That preparation demonstrates byte identity for its captured candidate only. The task changed during this review, including finalizing the timing contract. Freeze and prepare the final candidate again before associating formal review and model trials with it. Author identity, human effort estimate, full isolated reference/nop qualification, and the requested repeated model outcomes must still be completed or explicitly reported; no hardness claim follows from this review.

Subsequent verifier reporting fix: candidate `artifacts/local/frozen/durable-ledger-repair-20260926T193933080719Z/durable-ledger-repair` uses the independent structural comparator for performance answers and stops at the first mismatch (`tests/test_performance.py:72`). This avoids quadratic pytest diff rendering of large serialized JSON assertions on failing candidates. The public contract is unchanged. Control reruns are separate from the preparation evidence above; this note is not a new rubric review or a model result.

## Native review staging follow-up

The root agent reported that review attempt `194015674860Z` failed before its API call with Docker Compose `getwd: no such file or directory` while the Docker context was on DrvFS. `evaluation/prepare_review.py` now accepts `--native-stage`. It reserves a fresh directory under `$HOME/.local/state/klavis-terminal-bench/reviews/<label>/review-task` for the review task and Docker context, while config and manifest remain under repository artifacts. It rejects symlinked ancestors and descendants and refuses to reuse an existing stage. The default staging location is unchanged; the selected location and adaptation are recorded in the manifest.

Preparation with that flag succeeded for the exact frozen candidate ending `193933080719Z`. The config is `artifacts/local/review/implementation-review-codex-20260926T194435738194Z/config.json`; the Docker task is `/root/.local/state/klavis-terminal-bench/reviews/implementation-review-codex-20260926T194435738194Z/review-task`. Source and copied candidate dirhash both equal `440b57b209c8ee7c28177c2a6c0755ec8ae7c37713abe60c60c1d35ff49b8cc0`. The source freeze manifest/tree checks also passed, no native path symlinks were found, and all 35 criteria and reviewer model settings are unchanged. The full regression module now has eleven passing WSL tests, including three native-staging cases observed failing before the implementation. This preparation did not launch an agent or API and is not a new rubric verdict.
