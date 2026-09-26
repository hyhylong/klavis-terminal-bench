"""Resolve portable evaluation templates without invoking an agent or API."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = ("standard-codex", "cheat-codex", "standard-deepseek", "cheat-deepseek")


def prepare(label: str, task_path=None, attempts=None) -> Path:
    payload = json.loads((ROOT / "evaluation" / f"{label}.json").read_text())
    task = Path(task_path) if task_path is not None else ROOT / payload["tasks"][0]["path"]
    task = task.resolve()
    if not (task / 'task.toml').is_file() or not (task / 'instruction.md').is_file():
        raise ValueError('Task path must contain task.toml and instruction.md')
    payload["tasks"][0]["path"] = str(task)
    if attempts is not None:
        if attempts not in (1, 3):
            raise ValueError('Use one pilot/cheat attempt or three formal attempts')
        if label.startswith('cheat-') and attempts != 1:
            raise ValueError('Cheat configurations use one attempt')
        payload['n_attempts'] = attempts
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
    parser.add_argument('--task-path', type=Path, help='Immutable candidate task directory')
    parser.add_argument('--attempts', type=int, choices=(1, 3), help='One pilot or three formal attempts')
    args = parser.parse_args()
    print(prepare(args.label, args.task_path, args.attempts))
