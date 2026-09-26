"""Run every pinned upstream static gate, preserving each exit code and log."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / ".cache/upstream"
PIN = "4def1f367467b34b18e0dbdc086400ba71c3e037"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', default='tasks/temporal-ledger-repair')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/static')
    args = parser.parse_args()
    actual = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    if actual != PIN:
        raise SystemExit(f"Wrong upstream checkout: expected {PIN}, got {actual}")
    checks = sorted((UPSTREAM / "scripts/checks").glob("check-*.sh"))
    if len(checks) != 25:
        raise SystemExit(f"Expected 25 pinned checks, found {len(checks)}")
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, FIX_DIRS="", BASE_DIR="")
    # The pinned gates invoke python3 internally (including stdlib tomllib).
    # Keep them on the same configured runtime as this wrapper.
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    results = []
    for check in checks:
        command = ["bash", str(check), args.task]
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        (output / f"{check.stem}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        results.append({"check": check.name, "exit_code": result.returncode})
        print(f"{'PASS' if result.returncode == 0 else 'FAIL'} {check.name}", flush=True)
    passed = sum(r["exit_code"] == 0 for r in results)
    (output / "summary.json").write_text(json.dumps({
        "upstream_commit": PIN, "passed": passed, "total": len(results), "checks": results
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{passed}/{len(results)} passed; logs: {output}")
    return int(passed != len(results))


if __name__ == "__main__":
    sys.exit(main())
