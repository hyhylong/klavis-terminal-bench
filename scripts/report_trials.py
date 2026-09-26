"""Summarize local Harbor trials without copying secrets or claiming model failures.

The output is an observation index. Trajectory, specification, reward-hacking,
and difficulty reviews remain separate work; a zero reward proves none of them.
Only explicitly selected result fields and local evidence paths are emitted.
"""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys


PHASES = ("environment_setup", "agent_setup", "agent_execution", "verifier")
EVIDENCE_DIRECTORIES = {"agent", "artifacts", "verifier", "steps"}
EVIDENCE = {
    "ctrf": "verifier/ctrf.json",
    "reward_text": "verifier/reward.txt",
    "reward_json": "verifier/reward.json",
    "verifier_stdout": "verifier/test-stdout.txt",
    "verifier_stderr": "verifier/test-stderr.txt",
    "artifact_manifest": "artifacts/manifest.json",
    "reconstruction": "artifacts/app/output/reconstruction.json",
    "trajectory": "agent/trajectory.json",
    "trial_log": "trial.log",
}


def text_value(value):
    return value if isinstance(value, str) else None


def timing(value):
    """Do not copy arbitrary additional keys from a timing object."""
    if not isinstance(value, dict):
        return None
    return {key: text_value(value.get(key)) for key in ("started_at", "finished_at")}


def reward_value(data):
    verifier = data.get("verifier_result")
    rewards = verifier.get("rewards") if isinstance(verifier, dict) else None
    reward = rewards.get("reward") if isinstance(rewards, dict) else None
    numeric = type(reward) is int or (type(reward) is float and math.isfinite(reward))
    return reward if numeric else None, numeric and reward in (0, 1)


def exception_summary(value, scope):
    """Messages and tracebacks can contain API keys or raw agent output."""
    result = {"scope": scope}
    if isinstance(value, dict):
        result.update(type=text_value(value.get("exception_type")),
                      occurred_at=text_value(value.get("occurred_at")))
    return result


def trial_observation(data, result_path):
    agent_info = data.get("agent_info") or {}
    raw_model = agent_info.get("model_info")
    model_info = raw_model if isinstance(raw_model, dict) else {}
    malformed = raw_model is not None and not isinstance(raw_model, dict)
    agent = text_value(agent_info.get("name"))
    folder = result_path.parent
    paths = {"result": str(result_path)}
    for name, relative in EVIDENCE.items():
        path = folder / relative
        if path.is_file():
            paths[name] = str(path)
    exceptions = []
    if data.get("exception_info") is not None:
        exceptions.append(exception_summary(data["exception_info"], "trial"))
    raw_steps = data.get("step_results")
    malformed = malformed or (raw_steps is not None and not isinstance(raw_steps, list))
    steps = raw_steps if isinstance(raw_steps, list) else []
    for index, step in enumerate(steps):
        malformed = malformed or not isinstance(step, dict)
        if isinstance(step, dict) and step.get("exception_info") is not None:
            exceptions.append(exception_summary(step["exception_info"], f"step[{index}]"))

    reward, valid_reward = reward_value(data)
    missing = [] if "ctrf" in paths else ["ctrf"]
    if exceptions:
        classification = "infrastructure_error"
    elif not data.get("finished_at"):
        classification = "incomplete"
    elif malformed or not valid_reward:
        classification = "invalid_result"
    elif missing:
        classification = "evidence_missing"
    elif agent == "oracle":
        classification = "oracle_pass" if reward == 1 else "oracle_failed"
    elif agent == "nop":
        classification = "nop_pass" if reward == 0 else "nop_failed"
    else:
        classification = "solved" if reward == 1 else "zero_reward_requires_trajectory_review"

    times = {key: text_value(data.get(key)) for key in ("started_at", "finished_at")}
    times.update({phase: timing(data.get(phase)) for phase in PHASES if data.get(phase) is not None})
    return {
        "trial_name": text_value(data.get("trial_name")),
        "task_name": text_value(data.get("task_name")),
        "task_checksum": text_value(data.get("task_checksum")),
        "agent": agent, "agent_version": text_value(agent_info.get("version")),
        "model": text_value(model_info.get("name")),
        "model_provider": text_value(model_info.get("provider")),
        "times": times, "reward": reward, "classification": classification,
        "exceptions": exceptions, "missing_evidence": missing,
        "analysis_status": "pending", "paths": paths,
    }


def build_report(roots):
    """Discover trial results recursively; ignore job aggregates and duplicate roots."""
    supplied = {Path(root).resolve() for root in roots}
    sources = sorted(path for path in supplied if not any(parent in supplied for parent in path.parents))
    candidates = set()
    issues = []
    for source in sources:
        if source.is_dir():
            candidates.update(path.resolve() for path in source.rglob("result.json")
                              if not any(part in EVIDENCE_DIRECTORIES
                                         for part in path.relative_to(source).parts[:-1]))
        else:
            issues.append({"path": str(source), "issue": "job_directory_missing"})

    trials = []
    trial_roots = set()
    for path in sorted(candidates, key=lambda item: (len(item.parts), str(item))):
        if any(parent in trial_roots for parent in path.parents):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError):
            issues.append({"path": str(path), "issue": "unreadable_result"})
            continue
        if not isinstance(data, dict):
            issues.append({"path": str(path), "issue": "unrecognized_result"})
            continue
        # JobResult has these aggregate fields but no trial identity.
        if "trial_name" not in data and any(key in data for key in ("stats", "n_total_trials", "trial_results")):
            continue
        if not (all(isinstance(data.get(key), str) for key in ("trial_name", "task_name", "task_checksum"))
                and isinstance(data.get("agent_info"), dict)):
            issues.append({"path": str(path), "issue": "unrecognized_result"})
            continue
        trial_roots.add(path.parent)
        trials.append(trial_observation(data, path))

    groups = Counter((item["task_checksum"], item["agent"], item["model"], item["classification"]) for item in trials)
    observations = [{"task_checksum": checksum, "agent": agent, "model": model,
                     "classification": classification, "count": count}
                    for (checksum, agent, model, classification), count in sorted(
                        groups.items(), key=lambda entry: tuple(value or "" for value in entry[0]))]
    return {"schema_version": 1, "requirements_status": "not_assessed",
            "analysis_status": "pending", "source_roots": [str(path) for path in sources],
            "trials": trials, "observations": observations, "scan_issues": issues}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", nargs="+", type=Path, help="Job directories or a directory containing jobs")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout")
    args = parser.parse_args(argv)
    report = json.dumps(build_report(args.jobs), indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    if args.output is None:
        sys.stdout.write(report)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
