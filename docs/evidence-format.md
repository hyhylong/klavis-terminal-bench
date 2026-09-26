# Sanitized trial observations

Run the reporter with one or more local Harbor job directories, or their parent:

```powershell
python scripts/report_trials.py artifacts/jobs
python scripts/report_trials.py artifacts/jobs/oracle-v1 artifacts/jobs/nop-v2-absolute --output artifacts/trial-observations.json
```

The same command works in Linux with local paths. The reporter recursively finds `result.json`, recognizes per-trial results by their trial identity fields, skips job aggregates, and deduplicates overlapping input directories. It excludes nested `agent`, `artifacts`, `verifier`, and `steps` directories and ignores descendants of recognized trial roots, so evidence files cannot add fabricated trial observations. Supply Harbor job directories, not agent-generated evidence directories. It follows the installed Harbor `0.23.1.dev202609170426` trial and verifier result schemas. Unreadable or unrecognized results are listed as `scan_issues`; a missing job directory is also reported there.

Each trial contains its name, task name and checksum, agent name and version, model name and provider, overall and phase timestamps, numeric reward, classification, exception type/time, and paths to available local evidence. It does not copy configurations, environment variables, API credentials, exception messages or tracebacks, agent responses, verifier output, or trajectory text. Evidence paths allow a separate reviewer to inspect those files privately. The reporter does not load credential/configuration files or make network calls.

Classification uses this priority:

1. A trial or step exception produces `infrastructure_error`, even when the recorded reward is zero.
2. A trial without `finished_at` produces `incomplete`.
3. A missing, nonnumeric, boolean, nonfinite, or nonbinary `verifier_result.rewards.reward` produces `invalid_result`.
4. A missing `verifier/ctrf.json` produces `evidence_missing`. This project always uses a CTRF-emitting verifier.
5. An oracle trial needs reward 1 for `oracle_pass`; reward 0 is `oracle_failed`. A nop trial needs reward 0 for `nop_pass`; reward 1 is `nop_failed`.
6. Other agents receive `solved` for reward 1 or `zero_reward_requires_trajectory_review` for reward 0.

The labels describe recorded local observations. CTRF presence is recorded; this script does not validate its contents or independently attest the result file. A failed verifier assertion caused by a missing deliverable is a valid nop zero if Harbor completed without an exception and captured CTRF. An artifact-transfer failure recorded as an exception is an infrastructure error.

`observations` groups trial counts by task checksum, agent, model, and classification. It does not establish that an expected evaluation matrix is complete. All reports retain `analysis_status: "pending"` and `requirements_status: "not_assessed"`. A completed zero reward does not establish a genuine model failure, a valid cheat attempt, or a difficulty result. Those conclusions require separate explicit trajectory and evidence review. No automatic completion flag or analysis approval is accepted by this script.
