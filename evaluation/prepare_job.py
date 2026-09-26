"""Resolve portable evaluation templates without invoking an agent or API."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ("standard-codex", "cheat-codex", "standard-deepseek", "cheat-deepseek")


def prepare(label: str) -> Path:
    payload = json.loads((ROOT / "evaluation" / f"{label}.json").read_text())
    payload["tasks"][0]["path"] = str((ROOT / payload["tasks"][0]["path"]).resolve())
    payload["jobs_dir"] = str((ROOT / "artifacts" / "jobs").resolve())
    payload["job_name"] = label + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = ROOT / "artifacts" / "local" / "evaluation"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{payload['job_name']}.json"
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", choices=LABELS)
    print(prepare(parser.parse_args().label))
