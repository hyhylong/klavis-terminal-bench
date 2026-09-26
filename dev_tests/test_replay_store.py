"""Behavior, legacy-format, and deterministic crash tests for replay storage."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import unittest

from experiments.durable_ledger.durablefs import MemoryDurableFS
from experiments.durable_ledger.replay_store import Store


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = ROOT / "tasks" / "temporal-ledger-repair" / "tests" / "reference.py"
SPEC = importlib.util.spec_from_file_location("independent_storage_reference", REFERENCE_PATH)
REFERENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REFERENCE)

FIELDS = ("tier", "region", "quota", "enabled", "note")
SCHEMA = {"epoch": "one", "fields": {
    "t": {"name": "tier", "codec": "text", "default": "basic"},
    "r": {"name": "region", "codec": "text", "default": "eu"},
    "q": {"name": "quota", "codec": "integer", "default": 1000},
    "e": {"name": "enabled", "codec": "boolean", "default": True},
    "n": {"name": "note", "codec": "nullable_text", "default": None},
}}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def delivery(arrival, kind, body):
    return {"arrival": arrival, "kind": kind, "body": body}


def row(tx, operation):
    return {"tx": tx, "part": 0, "action": operation}


def commit(tx, seq, body):
    return {"tx": tx, "seq": seq, "parts": 1, "sha256": hashlib.sha256(canonical([body])).hexdigest()}


def delete_history():
    body = row("delete", {"op": "delete", "entity": "a", "from": -3, "to": 7})
    return [delivery(2, "row", body), delivery(5, "commit", commit("delete", 1, body))]


def correction_history():
    put = row("base", {"op": "put", "entity": "a", "from": 0, "to": 10, "epoch": "one", "values": {}})
    patch = row("patch", {"op": "patch", "entity": "a", "from": 2, "to": 8, "epoch": "one", "values": {"t": "gold"}})
    amend = row("void", {"op": "amend", "target": {"tx": "base", "part": 0}, "replacement": None})
    return [delivery(1, "schema", SCHEMA), delivery(2, "row", put), delivery(3, "commit", commit("base", 1, put)),
            delivery(4, "row", patch), delivery(5, "commit", commit("patch", 2, patch)),
            delivery(6, "row", amend), delivery(7, "commit", commit("void", 3, amend)),
            delivery(8, "abort", {"tx": "void"})]


def live(start, end, patch=False):
    values = dict(tier="basic", region="eu", quota=1000, enabled=True, note=None)
    origins = dict.fromkeys(FIELDS, "base/0")
    if patch:
        values["tier"] = "gold"
        origins["tier"] = "patch/0"
    return {"from": start, "to": end, "deleted": False, "values": values, "origins": origins}


def expected_delete():
    return {"id": "snapshot", "transactions": [{"tx": "delete", "state": "applied", "reason": "complete"}],
            "entities": [{"entity": "a", "segments": [{"from": -3, "to": 7, "deleted": True,
                                                       "values": {}, "origins": {"$delete": "delete/0"}}]}]}


def expected_patched(include_abort=False):
    statuses = [{"tx": tx, "state": "applied", "reason": "complete"} for tx in ("base", "patch")]
    if include_abort:
        statuses.append({"tx": "void", "state": "aborted", "reason": "abort"})
    return {"id": "snapshot", "transactions": statuses, "entities": [{"entity": "a", "segments": [
        live(0, 2), live(2, 8, True), live(8, 10)]}]}


def frame(event):
    """Encode the documented legacy format independently of Store helpers."""
    payload = canonical(event)
    return struct.pack(">I", len(payload)) + payload + hashlib.sha256(payload).digest()


def legacy_image(checkpoint_events, wal_bytes):
    return {
        "MANIFEST": canonical({"format": 1, "generation": 7, "checkpoint": "checkpoint-7.json", "wal": "wal-7.log"}) + b"\n",
        "checkpoint-7.json": canonical({"format": 1, "generation": 7, "events": checkpoint_events}) + b"\n",
        "wal-7.log": wal_bytes,
    }


class PowerLoss(Exception):
    pass


def fail_at(operation_count):
    def after_operation(name, count):
        if count == operation_count:
            raise PowerLoss(f"interrupted after {name} #{count}")
    return after_operation


class ReplayStoreTests(unittest.TestCase):
    maxDiff = None

    def assertJsonEqual(self, actual, expected):
        self.assertEqual(canonical(actual), canonical(expected))

    def test_open_empty_store_and_reopen(self):
        fs = MemoryDurableFS()
        store = Store(fs)
        self.assertJsonEqual(store.snapshot(100), {"id": "snapshot", "transactions": [], "entities": []})
        self.assertIsNone(store.lookup("missing", 0))
        self.assertIn("MANIFEST", fs.export_image())
        store.close()
        fs.crash()
        self.assertJsonEqual(Store(fs).snapshot(0), {"id": "snapshot", "transactions": [], "entities": []})

    def test_acknowledged_ingest_survives_without_close(self):
        fs = MemoryDurableFS()
        store = Store(fs)
        first, second = delete_history()
        store.ingest(first)
        self.assertJsonEqual(store.snapshot(2), {"id": "snapshot", "transactions": [
            {"tx": "delete", "state": "pending", "reason": "missing_commit"}], "entities": []})
        store.ingest(second)
        fs.crash()
        reopened = Store(fs)
        self.assertJsonEqual(reopened.snapshot(5), expected_delete())
        self.assertJsonEqual(reopened.lookup("a", -3), expected_delete()["entities"][0]["segments"][0])
        self.assertIsNone(reopened.lookup("a", -4))
        self.assertIsNone(reopened.lookup("a", 7))

    def test_retry_is_structural_idempotent_and_input_is_owned(self):
        fs = MemoryDurableFS()
        store = Store(fs)
        first, second = delete_history()
        store.ingest(first)
        first["body"]["action"]["entity"] = "changed-after-return"
        store.ingest(second)
        image = fs.export_image()
        for event in reversed(delete_history()):
            store.ingest(dict(reversed(list(event.items()))))
        self.assertEqual(len(store._events), 2)
        self.assertEqual(fs.export_image(), image)
        self.assertJsonEqual(store.snapshot(5), expected_delete())
        returned = store.lookup("a", 0)
        self.assertIsNotNone(returned)
        returned["origins"]["$delete"] = "caller-edited"
        self.assertJsonEqual(store.snapshot(5), expected_delete())

    def test_conflicting_retry_and_unseen_old_arrival_are_rejected_without_change(self):
        fs = MemoryDurableFS()
        store = Store(fs)
        for event in delete_history():
            store.ingest(event)
        image = fs.export_image()
        changed = copy.deepcopy(delete_history()[0])
        changed["body"]["action"]["from"] = -4
        with self.assertRaises(ValueError):
            store.ingest(changed)
        with self.assertRaises(ValueError):
            store.ingest(delivery(3, "abort", {"tx": "delete"}))
        self.assertEqual(fs.export_image(), image)
        self.assertJsonEqual(store.snapshot(5), expected_delete())

    def test_compaction_restart_late_retraction_and_abort_preserve_old_cutoffs(self):
        fs = MemoryDurableFS()
        store = Store(fs)
        events = correction_history()
        for event in events[:5]:
            store.ingest(event)
        self.assertJsonEqual(store.snapshot(5), expected_patched())
        store.compact()
        fs.crash()
        store = Store(fs)
        for event in events[5:7]:
            store.ingest(event)
        self.assertJsonEqual(store.snapshot(7), {"id": "snapshot", "transactions": [
            {"tx": tx, "state": "applied", "reason": "complete"} for tx in ("base", "patch", "void")], "entities": []})
        store.compact()
        store.compact()
        fs.crash()
        store = Store(fs)
        store.ingest(events[7])
        self.assertJsonEqual(store.snapshot(8), expected_patched(True))
        self.assertJsonEqual(store.snapshot(5), expected_patched())
        self.assertJsonEqual(store.lookup("a", 4), live(2, 8, True))

    def test_compaction_retires_superseded_wal_and_keeps_history(self):
        fs = MemoryDurableFS()
        store = Store(fs)
        for event in delete_history():
            store.ingest(event)
        before = fs.export_image()
        self.assertTrue(any(name.endswith(".log") and data for name, data in before.items()))
        store.compact()
        after = fs.export_image()
        self.assertEqual(len([name for name in after if name.endswith(".log")]), 1)
        self.assertTrue(all(data == b"" for name, data in after.items() if name.endswith(".log")))
        self.assertTrue(any(name not in after for name in before if name.endswith(".log")))
        fs.crash()
        self.assertJsonEqual(Store(fs).snapshot(5), expected_delete())

    def test_documented_legacy_image_opens_and_compacts(self):
        events = delete_history()
        fs = MemoryDurableFS.from_image(legacy_image(events[:1], frame(events[1])))
        store = Store(fs)
        self.assertEqual(store._events, events)
        self.assertJsonEqual(store.snapshot(5), expected_delete())
        store.compact()
        fs.crash()
        self.assertJsonEqual(Store(fs).snapshot(5), expected_delete())

    def test_incomplete_wal_tail_is_removed_before_next_append(self):
        events = delete_history()
        fs = MemoryDurableFS.from_image(legacy_image([], frame(events[0]) + b"\x00\x00\x00"))
        store = Store(fs)
        self.assertEqual(store._events, events[:1])
        store.ingest(events[1])
        fs.crash()
        self.assertJsonEqual(Store(fs).snapshot(5), expected_delete())

    def test_complete_corrupt_wal_frame_is_not_silently_dropped(self):
        encoded = bytearray(frame(delete_history()[0]))
        encoded[-1] ^= 1
        fs = MemoryDurableFS.from_image(legacy_image([], bytes(encoded)))
        with self.assertRaises(ValueError):
            Store(fs)

    def test_initial_generation_install_survives_every_operation_interruption(self):
        trace = []
        Store(MemoryDurableFS(after_operation=lambda name, count: trace.append((name, count))))
        self.assertGreater(len(trace), 3)
        for _, count in trace:
            with self.subTest(operation=count):
                fs = MemoryDurableFS(after_operation=fail_at(count))
                with self.assertRaises(PowerLoss):
                    Store(fs)
                fs.crash()
                store = Store(fs)
                for event in delete_history():
                    store.ingest(event)
                fs.crash()
                self.assertJsonEqual(Store(fs).snapshot(5), expected_delete())

    def test_ingest_interruption_is_atomic_and_identical_retry_converges(self):
        original = MemoryDurableFS()
        store = Store(original)
        first, second = delete_history()
        store.ingest(first)
        image = original.export_image()
        trace = []
        measured_fs = MemoryDurableFS.from_image(image, after_operation=lambda name, count: trace.append((name, count)))
        Store(measured_fs).ingest(second)
        self.assertTrue(any(name == "append" for name, _ in trace))
        for _, count in trace:
            with self.subTest(operation=count):
                fs = MemoryDurableFS.from_image(image, after_operation=fail_at(count))
                with self.assertRaises(PowerLoss):
                    Store(fs).ingest(second)
                fs.crash()
                recovered = Store(fs)
                self.assertIn(canonical(recovered._events), [canonical([first]), canonical([first, second])])
                recovered.ingest(second)
                recovered.ingest(second)
                fs.crash()
                final = Store(fs)
                self.assertEqual(len(final._events), 2)
                self.assertJsonEqual(final.snapshot(5), expected_delete())

    def test_compaction_interruption_keeps_generation_complete_and_lineage_replayable(self):
        original = MemoryDurableFS()
        store = Store(original)
        events = correction_history()
        for event in events[:5]:
            store.ingest(event)
        image = original.export_image()
        trace = []
        measured_fs = MemoryDurableFS.from_image(image, after_operation=lambda name, count: trace.append((name, count)))
        Store(measured_fs).compact()
        self.assertTrue(any(name == "replace" for name, _ in trace))
        self.assertTrue(any(name == "unlink" for name, _ in trace))
        for _, count in trace:
            with self.subTest(operation=count):
                fs = MemoryDurableFS.from_image(image, after_operation=fail_at(count))
                with self.assertRaises(PowerLoss):
                    Store(fs).compact()
                fs.crash()
                recovered = Store(fs)
                self.assertJsonEqual(recovered.snapshot(5), expected_patched())
                for event in events[5:]:
                    recovered.ingest(event)
                recovered.compact()
                fs.crash()
                final = Store(fs)
                self.assertJsonEqual(final.snapshot(8), expected_patched(True))
                self.assertJsonEqual(final.snapshot(5), expected_patched())

    def test_corpus_semantics_match_independent_verifier_across_recovery(self):
        data = ROOT / "tasks" / "temporal-ledger-repair" / "environment" / "data"
        events = [json.loads(line) for line in (data / "feed.jsonl").read_text(encoding="utf-8").splitlines()]
        checkpoints = json.loads((data / "checkpoints.json").read_text(encoding="utf-8"))
        expected = REFERENCE.reconstruct(events, [{"id": "snapshot", "cutoff": item["cutoff"]} for item in checkpoints])["checkpoints"]
        fs = MemoryDurableFS()
        store = Store(fs)
        for index, event in enumerate(events, 1):
            store.ingest(event)
            if index % 17 == 0:
                store.ingest(copy.deepcopy(event))
            if index % 113 == 0:
                store.compact()
            if index % 97 == 0:
                fs.crash()
                store = Store(fs)
        for query, answer in zip(checkpoints, expected):
            self.assertJsonEqual(store.snapshot(query["cutoff"]), answer)
        current = REFERENCE.reconstruct(events, [{"id": "snapshot", "cutoff": events[-1]["arrival"]}])["checkpoints"][0]
        for record in current["entities"]:
            segment = record["segments"][0]
            self.assertJsonEqual(store.lookup(record["entity"], segment["from"]), segment)


if __name__ == "__main__":
    unittest.main()
