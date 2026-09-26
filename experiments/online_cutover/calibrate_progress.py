"""Authoring measurements and a known-bad pause control, never model trials.

Run in the trusted Linux runtime from the repository root. Submitted code stays
under the application identity; the controller alone observes pg_stat_activity.
No timing threshold is derived from one machine or imposed by this experiment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import time
import unittest

try:
    from . import test_cutover as integration
except ImportError:
    import test_cutover as integration


PAUSED_MAIN = '''
def main(source_dsn, target_dsn):
    ensure_routing(source_dsn, target_dsn)
    with psycopg.connect(target_dsn, autocommit=True) as target:
        target.execute("SELECT pg_advisory_lock(%s,2)", (NAMESPACE,))
        if is_active(target):
            return
        with psycopg.connect(source_dsn, autocommit=True) as fence:
            fence.execute("SELECT pg_advisory_lock(%s,1)", (NAMESPACE,))
            copy_snapshot(source_dsn, target)
            with target.transaction():
                target.execute("UPDATE app.bridge_state SET active=true WHERE singleton=1")
'''


class ProgressMeasurement(integration.CutoverChecks):
    # Explicitly load one inherited scenario; unittest discovery doesn't load
    # this measurement script. It is not a second set of correctness tests.
    package_parent = integration.ROOT

    def setUp(self):
        self.measurements = []
        super().setUp()

    def migrate(self):
        return self.rt.run_as_app(
            [sys.executable, "-B", "-m", "orderbridge", "migrate",
             "--source", self.rt.source_dsn, "--target", self.rt.target_dsn],
            env={"PYTHONPATH": str(self.package_parent)})

    def call(self, body):
        started = time.monotonic()
        item = {"op": body["op"]}
        try:
            actual = super().call(body)
            item["returned"] = True
            return actual
        except Exception as exc:
            item.update(returned=False, exception=type(exc).__name__)
            # Only catalog metadata; never run application-owned SQL as admin.
            with self.rt.admin_connect("postgres") as conn:
                item["database_waits"] = [
                    {"database": database, "wait_type": wait_type, "wait": wait, "count": count}
                    for database, wait_type, wait, count in conn.execute(
                        "SELECT datname,wait_event_type,wait_event,count(*) FROM pg_stat_activity "
                        "WHERE usename='orderbridge_app' AND wait_event_type='Lock' "
                        "GROUP BY datname,wait_event_type,wait_event ORDER BY datname,wait_event")]
            raise
        finally:
            item["elapsed_seconds"] = round(time.monotonic() - started, 6)
            self.measurements.append(item)


def run_case(package_parent):
    case = ProgressMeasurement("test_blocked_backfill_allows_live_changes_delete_recreate_and_retry")
    case.package_parent = package_parent
    result = unittest.TestResult()
    started = time.monotonic()
    case.run(result)
    return {"passed": result.wasSuccessful(), "test_count": result.testsRun,
            "failure_count": len(result.failures), "error_count": len(result.errors),
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "requests": case.measurements}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10:
        parser.error("--repetitions must be between 1 and 10")
    reference = [run_case(integration.ROOT) for _ in range(args.repetitions)]
    with tempfile.TemporaryDirectory(prefix="cutover-paused-control-") as directory:
        parent = Path(directory)
        parent.chmod(0o755)
        shutil.copytree(integration.ROOT / "orderbridge", parent / "orderbridge")
        module = parent / "orderbridge" / "migrate.py"
        source = module.read_text()
        marker = "\ndef main(source_dsn, target_dsn):"
        if source.count(marker) != 1:
            raise RuntimeError("Reference entry point changed; update this authoring control")
        module.write_text(source.split(marker)[0] + "\n" + PAUSED_MAIN)
        paused = run_case(parent)
    successful = [request["elapsed_seconds"] for run in reference
                  for request in run["requests"] if request["returned"]]
    errors = [request for request in paused["requests"] if not request["returned"]]
    detected = (not paused["passed"] and any(
        item.get("exception") == "TimeoutError"
        and any(row["database"] == "source_db" and row["wait"] == "advisory"
                for row in item.get("database_waits", []))
        and any(row["database"] == "target_db" and row["wait"] == "relation"
                for row in item.get("database_waits", [])) for item in errors))
    report = {"kind": "authoring_progress_control", "model_trial": False,
              "reference_runs": reference, "global_pause_control": paused,
              "known_pause_detected": detected,
              "successful_request_count": len(successful),
              "reference_request_median_seconds": statistics.median(successful) if successful else None,
              "reference_request_max_seconds": max(successful, default=None),
              "existing_per_request_guard_seconds": 5,
              "scope": "Small synthetic fixture; measures a deterministic held-lock schedule, not production throughput or model difficulty."}
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0 if all(run["passed"] for run in reference) and detected else 1


if __name__ == "__main__":
    raise SystemExit(main())
