"""Rebuild the synthetic delivery journal; never generates expected answers.

Seeded fixtures model an ingestion incident, not production/customer records.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tasks/temporal-ledger-repair/environment/data"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def seal(rows):
    return hashlib.sha256(canonical(sorted(rows, key=lambda r: r["part"])).encode()).hexdigest()


def schema(epoch, keys, codecs, defaults):
    names = ("tier", "region", "quota", "enabled", "note")
    return {"epoch": epoch, "fields": {
        key: {"name": name, "codec": codec, "default": default}
        for key, name, codec, default in zip(keys, names, codecs, defaults)
    }}


SCHEMAS = [
    schema("v1", ("plan", "zone", "limit", "active", "memo"),
           ("text", "text", "integer", "boolean", "nullable_text"),
           ("basic", "eu", 2500, False, None)),
    schema("v2", ("tier_name", "region_code", "quota_units", "is_on", "annotation"),
           ("text", "text", "decimal_milli", "zero_one", "nullable_text"),
           ("standard", "us", "2.500", 1, "migrated")),
    schema("v3", ("t", "r", "q", "e", "n"),
           ("text", "text", "decimal_milli", "boolean", "nullable_text"),
           ("archive", "ap", "-0.001", False, None)),
]


def action(op, entity="sample", start=0, end=None, epoch="v1", values=None):
    body = {"op": op, "entity": entity, "from": start, "to": end}
    if op != "delete":
        body.update(epoch=epoch, values={} if values is None else values)
    return body


def build_corpus(seed=20260926):
    rng = random.Random(seed)
    deliveries = []

    def emit(at, kind, body):
        deliveries.append((at, len(deliveries), kind, deepcopy(body)))

    def transaction(tx, seq, actions, at, row_times=None, commit_at=None, mode=None):
        rows = [{"tx": tx, "part": i, "action": a} for i, a in enumerate(actions)]
        commit = {"tx": tx, "seq": seq, "parts": len(rows), "sha256": seal(rows)}
        if mode == "digest":
            commit["sha256"] = "0" * 64
        for i, row in enumerate(rows):
            if mode == "missing_part" and i == len(rows) - 1:
                continue
            emit(at + i if row_times is None else row_times[i], "row", row)
        if mode != "missing_commit":
            emit(at + len(rows) if commit_at is None else commit_at, "commit", commit)
        return rows, commit

    emit(1, "schema", SCHEMAS[0])
    emit(22, "schema", SCHEMAS[1])
    emit(1600, "schema", SCHEMAS[2])
    emit(1800, "schema", SCHEMAS[1])
    transaction("seed", 10, [action("put", start=-10)], 2)
    transaction("patch-later", 40, [action("patch", start=0, end=20, values={"zone": "west"})], 4)
    transaction("split-delete", 50, [action("delete", start=8, end=12)], 6)
    transaction("crossing-patch", 60, [action("patch", start=6, end=16, values={"memo": "repaired", "active": True})], 8)
    transaction("late-base", 20, [action("put", start=0, end=10, values={"plan": "premium", "limit": -1251})], 13)
    transaction("atomic-pair", 30, [
        action("put", "pair-a", 0, 20),
        action("patch", "sample", 2, 15, values={"memo": "paired"})
    ], 15, row_times=[17, 30], commit_at=15)
    transaction("amend-restore", 80, [{"op": "amend", "target": {"tx": "split-delete", "part": 0},
        "replacement": action("put", start=7, end=13, epoch="v2", values={"quota_units": "1.001"})}], 18)
    transaction("amend-retract", 90, [{"op": "amend", "target": {"tx": "split-delete", "part": 0}, "replacement": None}], 24)
    emit(28, "abort", {"tx": "amend-retract"})
    rows, _ = transaction("conflicting-fragment", 100, [action("put", "conflict")], 32)
    emit(34, "row", rows[0])
    changed = deepcopy(rows[0])
    changed["action"]["values"] = {"plan": "conflicting"}
    emit(35, "row", changed)
    transaction("broken-seal", 110, [action("put", "broken")], 36, mode="digest")
    transaction("uncommitted", 120, [action("put", "uncommitted")], 38, mode="missing_commit")
    transaction("missing-fragment", 130, [action("put", "partial-a"), action("put", "partial-b")],
                39, commit_at=40, mode="missing_part")
    transaction("missing-epoch", 140, [action("put", "pending-epoch", epoch="unreleased")], 41)
    _, commit = transaction("conflicting-commit", 150, [action("put", "conflict-commit")], 43)
    conflicting = dict(commit, sha256="1" * 64)
    emit(45, "commit", conflicting)
    invalid_row = {"tx": "outside-parts", "part": 3, "action": action("put", "outside")}
    emit(46, "row", invalid_row)
    emit(47, "commit", {"tx": "outside-parts", "seq": 160, "parts": 1, "sha256": seal([invalid_row])})
    emit(48, "abort", {"tx": "outside-parts"})
    # Same value but different sources cannot coalesce. An empty patch creates no boundary.
    transaction("provenance", 170, [action("put", "origins", 0, 10), action("put", "origins", 10, 20),
                                   action("patch", "origins", 5, 15)], 50)
    transaction("tombstone", 180, [action("delete", "gaps", -5, 5), action("delete", "gaps", 5, 15),
                                  action("patch", "gaps", 0, None, values={"memo": "no resurrection"})], 56)

    def random_action(entity=None):
        epoch = rng.choice(SCHEMAS)
        start = rng.randrange(-100, 500)
        end = None if rng.random() < .12 else start + rng.randrange(1, 130)
        op = rng.choices(("put", "patch", "delete"), weights=(4, 5, 2))[0]
        values = {}
        for wire, field in epoch["fields"].items():
            if rng.random() > .5:
                continue
            name, codec = field["name"], field["codec"]
            if name == "tier":
                value = rng.choice(("basic", "team", "pro", "enterprise"))
            elif name == "region":
                value = rng.choice(("eu", "us", "ap", "local"))
            elif name == "quota":
                milli = rng.randint(-5000, 100000)
                value = milli if codec == "integer" else f'{"-" if milli < 0 else ""}{abs(milli)//1000}.{abs(milli)%1000:03d}'
            elif name == "enabled":
                value = bool(rng.getrandbits(1))
                if codec == "zero_one":
                    value = int(value)
            else:
                value = rng.choice((None, "", "hold", 'quoted "note"', "line\nbreak", "review"))
            values[wire] = value
        return action(op, entity or f"customer-{rng.randrange(24):02d}", start, end, epoch["epoch"], values)

    originals = []
    for i in range(220):
        tx = f"flow-{i:04d}"
        actions = [random_action() for _ in range(rng.randint(1, 4))]
        at = rng.randint(70, 2500)
        times = [at + rng.randrange(0, 650) for _ in actions]
        mode = None
        if i % 29 == 0:
            mode = "digest"
        elif i % 23 == 0:
            mode = "missing_part"
        elif i % 31 == 0:
            mode = "missing_commit"
        rows, commit = transaction(tx, 1000 + i, actions, at, times, at + rng.randrange(0, 600), mode)
        originals.extend(rows)
        if i % 19 == 0:
            emit(max(times) + 20, "row", rows[0])
            if mode != "missing_commit":
                emit(max(times) + 30, "commit", commit)
        if i % 17 == 0:
            emit(at + 700, "abort", {"tx": tx})
        if i % 37 == 0:
            other = deepcopy(rows[0])
            other["action"]["from"] -= 1
            emit(max(times) + 70, "row", other)

    for i in range(75):
        target = rng.choice(originals)
        replacement = None if i % 4 == 0 else random_action(target["action"]["entity"])
        amend = {"op": "amend", "target": {"tx": target["tx"], "part": target["part"]}, "replacement": replacement}
        acts = [amend]
        if i % 9 == 0:
            acts.append({"op": "amend", "target": deepcopy(amend["target"]), "replacement": None})
        at = rng.randint(100, 2900)
        transaction(f"correction-{i:03d}", 3000 + i, acts, at,
                    row_times=[at + rng.randrange(300) for _ in acts], commit_at=at + rng.randrange(500))
        if i % 21 == 0:
            emit(at + 550, "abort", {"tx": f"correction-{i:03d}"})

    deliveries.sort(key=lambda d: (d[0], d[1]))
    events = [{"arrival": i, "kind": kind, "body": body}
              for i, (_, _, kind, body) in enumerate(deliveries, 1)]
    cuts = [0, 3, 9, 14, 19, 22, 25, 28, 30, 34, 35, 47, 48, 65, 500, 1000, 1599, 1600, 2200, 2800]
    checkpoints = [{"id": f"delivery-window-{at:04d}", "cutoff": sum(d[0] <= at for d in deliveries)} for at in cuts]
    checkpoints.append({"id": "complete-delivery", "cutoff": len(events)})
    return events, checkpoints


def main():
    events, checkpoints = build_corpus()
    # The trusted image gets its own immutable copy, independent of agent edits.
    for directory in (DATA, ROOT / "tasks/temporal-ledger-repair/tests/fixtures"):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "feed.jsonl").write_text("".join(canonical(e) + "\n" for e in events), encoding="utf-8", newline="\n")
        (directory / "checkpoints.json").write_text(json.dumps(checkpoints, indent=2) + "\n", encoding="utf-8", newline="\n")
    digest = hashlib.sha256((DATA / "feed.jsonl").read_bytes()).hexdigest()
    print(json.dumps({"events": len(events), "checkpoints": len(checkpoints), "feed_sha256": digest}))


if __name__ == "__main__":
    main()
