"""Hand-calculated protocol cases and hostile JSON artifacts for the independent verifier."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REFERENCE = Path(__file__).resolve().parents[1] / "tasks/temporal-ledger-repair/tests/reference.py"
FIELDS = ("tier", "region", "quota", "enabled", "note")
DEFAULTS = {"tier": "basic", "region": "eu", "quota": 1000, "enabled": True, "note": None}


def schema(epoch="e", decimal=False):
    codecs = ("text", "text", "decimal_milli" if decimal else "integer", "boolean", "nullable_text")
    return {"epoch": epoch, "fields": {
        key: {"name": key, "codec": codec, "default": "1" if decimal and key == "quota" else DEFAULTS[key]}
        for key, codec in zip(FIELDS, codecs)
    }}


def action(op="put", start=0, end=10, values=None, epoch="e", entity="a"):
    result = {"op": op, "entity": entity, "from": start, "to": end}
    if op != "delete":
        result.update(epoch=epoch, values=values or {})
    return result


def row(tx, part, act):
    return {"tx": tx, "part": part, "action": act}


def commit(tx, seq, rows):
    payload = json.dumps(sorted(rows, key=lambda r: r["part"]), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {"tx": tx, "seq": seq, "parts": len(rows), "sha256": hashlib.sha256(payload.encode()).hexdigest()}


def feed(*records):
    return [{"arrival": i + 1, "kind": kind, "body": body} for i, (kind, body) in enumerate(records)]


def transaction(tx, state="applied", reason="complete"):
    return {"tx": tx, "state": state, "reason": reason}


def segment(start, end, origin, values=None, deleted=False, origins=None):
    vals = {} if deleted else DEFAULTS | (values or {})
    return {"from": start, "to": end, "deleted": deleted, "values": vals,
            "origins": {"$delete": origin} if deleted else origins or dict.fromkeys(FIELDS, origin)}


class VerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = None
        if REFERENCE.exists():
            spec = importlib.util.spec_from_file_location("independent_reference", REFERENCE)
            cls.reference = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.reference)

    def ref(self):
        self.assertIsNotNone(self.reference, "Independent verifier has not been implemented")
        return self.reference

    def reconstruct(self, events, cutoffs):
        return self.ref().reconstruct(events, [{"id": str(c), "cutoff": c} for c in cutoffs])["checkpoints"]

    def test_schema_visibility_precedes_digest_and_duplicates_do_not_change_seal(self):
        r = row("t", 0, action(values={"note": "line\nquoted \"value\""}))
        good = commit("t", 2, [r])
        events = feed(("row", r), ("row", r), ("commit", good), ("schema", schema()))
        before, after = self.reconstruct(events, [3, 4])
        self.assertEqual(before["transactions"], [transaction("t", "pending", "missing_schema")])
        self.assertEqual(before["entities"], [])
        self.assertEqual(after["transactions"], [transaction("t")])
        self.assertEqual(after["entities"], [{"entity": "a", "segments": [segment(0, 10, "t/0", {"note": 'line\nquoted "value"'})]}])
        events[2]["body"] = good | {"sha256": "0" * 64}
        before, after = self.reconstruct(events, [3, 4])
        self.assertEqual(before["transactions"][0]["reason"], "missing_schema")
        self.assertEqual(after["transactions"], [transaction("t", "quarantined", "digest_mismatch")])

    def test_classification_priority_and_all_visible_ids(self):
        r = row("x", 0, action())
        c = commit("x", 1, [r])
        events = feed(("row", r), ("row", r | {"action": action(end=12)}),
                      ("commit", c), ("commit", c | {"parts": 2}), ("abort", {"tx": "x"}),
                      ("abort", {"tx": "a"}), ("row", row("z", 5, action())))
        results = self.reconstruct(events, [2, 3, 4, 5, 7])
        self.assertEqual([x["transactions"][0]["reason"] for x in results[:4]],
                         ["conflicting_row", "conflicting_row", "conflicting_commit", "abort"])
        self.assertEqual(results[-1]["transactions"], [transaction("a", "aborted", "abort"),
                         transaction("x", "aborted", "abort"), transaction("z", "pending", "missing_commit")])

    def test_out_of_range_precedes_missing_parts_and_missing_schema(self):
        r = row("t", 2, action())
        events = feed(("row", r), ("commit", {"tx": "t", "seq": 3, "parts": 2, "sha256": "0" * 64}))
        self.assertEqual(self.reconstruct(events, [2])[0]["transactions"],
                         [transaction("t", "quarantined", "out_of_range_part")])
        events[0]["body"] = row("t", 0, action())
        self.assertEqual(self.reconstruct(events, [2])[0]["transactions"],
                         [transaction("t", "pending", "missing_parts")])

    def test_replay_is_source_order_patch_only_live_and_tombstones_cover_gaps(self):
        p = row("put", 0, action(start=0, end=10))
        d = row("delete", 0, action("delete", 5, 15))
        q = row("patch", 0, action("patch", -2, None, {"quota": 2400}))
        events = feed(("schema", schema()), ("row", q), ("commit", commit("patch", 3, [q])),
                      ("row", d), ("commit", commit("delete", 2, [d])),
                      ("row", p), ("commit", commit("put", 1, [p])))
        early, final = self.reconstruct(events, [3, 7])
        self.assertEqual(early["entities"], [])
        expected = [segment(0, 5, "put/0", {"quota": 2400}, origins=dict.fromkeys(FIELDS, "put/0") | {"quota": "patch/0"}),
                    segment(5, 15, "delete/0", deleted=True)]
        self.assertEqual(final["entities"], [{"entity": "a", "segments": expected}])

    def test_amendment_replays_at_target_slot_with_amendment_provenance(self):
        p = row("base", 0, action())
        q = row("later", 0, action("patch", 0, 10, {"quota": 7000}))
        a = row("fix", 0, {"op": "amend", "target": {"tx": "base", "part": 0},
                            "replacement": action(start=-2, end=20, values={"tier": "pro"})})
        events = feed(("schema", schema()), ("row", a), ("commit", commit("fix", 3, [a])),
                      ("row", q), ("commit", commit("later", 2, [q])),
                      ("row", p), ("commit", commit("base", 1, [p])))
        early, final = self.reconstruct(events, [5, 7])
        self.assertEqual(early["entities"], [])
        self.assertEqual(final["entities"], [{"entity": "a", "segments": [
            segment(-2, 0, "fix/0", {"tier": "pro"}),
            segment(0, 10, "fix/0", {"tier": "pro", "quota": 7000}, origins=dict.fromkeys(FIELDS, "fix/0") | {"quota": "later/0"}),
            segment(10, 20, "fix/0", {"tier": "pro"})]}])

    def test_latest_amendment_part_null_and_late_abort_reveal_previous_version(self):
        p = row("base", 0, action())
        older = row("old", 0, {"op": "amend", "target": {"tx": "base", "part": 0}, "replacement": action(end=None)})
        newer = [row("new", i, {"op": "amend", "target": {"tx": "base", "part": 0}, "replacement": rep})
                 for i, rep in enumerate([action(end=30), None])]
        events = feed(("schema", schema()), ("row", p), ("commit", commit("base", 1, [p])),
                      ("row", older), ("commit", commit("old", 2, [older])),
                      ("row", newer[1]), ("row", newer[0]), ("commit", commit("new", 3, newer)),
                      ("abort", {"tx": "new"}))
        suppressed, restored = self.reconstruct(events, [8, 9])
        self.assertEqual(suppressed["entities"], [])
        self.assertEqual(restored["entities"], [{"entity": "a", "segments": [segment(0, None, "old/0")]}])

    def test_same_values_different_origins_stay_split_but_overwritten_boundaries_merge(self):
        rows = [row("t", i, a) for i, a in enumerate([action(end=5), action(start=5), action("patch", 2, 8, {} )])]
        events = feed(("schema", schema()), *(("row", r) for r in rows), ("commit", commit("t", 1, rows)))
        result = self.reconstruct(events, [5])[0]
        self.assertEqual(result["entities"][0]["segments"], [segment(0, 5, "t/0"), segment(5, 10, "t/1")])
        put = row("u", 0, action())
        events += [{"arrival": 6, "kind": "row", "body": put}, {"arrival": 7, "kind": "commit", "body": commit("u", 2, [put])}]
        self.assertEqual(self.reconstruct(events, [7])[0]["entities"][0]["segments"], [segment(0, 10, "u/0")])

    def test_historical_epoch_decodes_decimal_exactly_and_defaults_receive_origin(self):
        s = schema(decimal=True)
        s["fields"]["quota"]["default"] = "-0.001"
        p = row("t", 0, action(values={"quota": "+9007199254741.991"}))
        events = feed(("schema", s), ("row", p), ("commit", commit("t", 1, [p])))
        output = self.reconstruct(events, [3])[0]["entities"][0]["segments"][0]
        self.assertEqual(output["values"]["quota"], 9007199254741991)
        self.assertEqual(output["origins"], dict.fromkeys(FIELDS, "t/0"))

    def test_old_wire_names_and_new_epoch_defaults_remain_independent(self):
        first = schema("old", decimal=True)
        first["fields"] = {"wire_" + key: value for key, value in first["fields"].items()}
        first["fields"]["wire_quota"]["default"] = "-0.001"
        second = schema("new")
        second["fields"]["enabled"].update(codec="zero_one", default=0)
        second["fields"]["region"]["default"] = "us"
        a = row("oldput", 0, action(values={"wire_note": "old"}, epoch="old"))
        b = row("newpatch", 0, action("patch", 0, 10, {"enabled": 1, "note": None}, "new"))
        events = feed(("schema", first), ("schema", second), ("row", b), ("commit", commit("newpatch", 2, [b])),
                      ("row", a), ("commit", commit("oldput", 1, [a])))
        actual = self.reconstruct(events, [6])[0]["entities"][0]["segments"]
        self.assertEqual(actual, [segment(0, 10, "oldput/0", {"quota": -1},
                         origins=dict.fromkeys(FIELDS, "oldput/0") | {"enabled": "newpatch/0", "note": "newpatch/0"})])

    def test_ineligible_newer_amendment_does_not_hide_eligible_older_amendment(self):
        base = row("b", 0, action())
        fixes = [row(name, 0, {"op": "amend", "target": {"tx": "b", "part": 0}, "replacement": replacement})
                 for name, replacement in [("old", action(end=20)), ("new", action(end=30, epoch="later"))]]
        events = feed(("schema", schema()), ("row", base), ("commit", commit("b", 1, [base])),
                      ("row", fixes[0]), ("commit", commit("old", 2, [fixes[0]])),
                      ("row", fixes[1]), ("commit", commit("new", 3, [fixes[1]])), ("schema", schema("later")))
        before, after = self.reconstruct(events, [7, 8])
        self.assertEqual(before["entities"][0]["segments"], [segment(0, 20, "old/0")])
        self.assertEqual(after["entities"][0]["segments"], [segment(0, 30, "new/0")])

    def test_null_amendment_needs_no_schema_but_unusable_original_row_still_does(self):
        base = row("b", 0, action(epoch="later"))
        fix = row("fix", 0, {"op": "amend", "target": {"tx": "b", "part": 0}, "replacement": None})
        events = feed(("row", base), ("commit", commit("b", 1, [base])),
                      ("row", fix), ("commit", commit("fix", 2, [fix])))
        self.assertEqual(self.reconstruct(events, [4])[0], {
            "id": "4", "transactions": [transaction("b", "pending", "missing_schema"), transaction("fix")], "entities": []})

    def test_tombstone_origins_absent_gaps_empty_checkpoint_and_requested_order(self):
        rows = [row("t", i, a) for i, a in enumerate([
            action("delete", -10, -5, entity="z"), action("delete", -5, 0, entity="z"),
            action("delete", 3, None, entity="z"), action("delete", -1, 1, entity="a")])]
        events = feed(*(("row", r) for r in reversed(rows)), ("commit", commit("t", 1, rows)))
        late, early = self.reconstruct(events, [5, 0])
        self.assertEqual(early, {"id": "0", "transactions": [], "entities": []})
        self.assertEqual(late["entities"], [
            {"entity": "a", "segments": [segment(-1, 1, "t/3", deleted=True)]},
            {"entity": "z", "segments": [segment(-10, -5, "t/0", deleted=True),
             segment(-5, 0, "t/1", deleted=True), segment(3, None, "t/2", deleted=True)]}])

    def test_json_validator_accepts_object_order_but_rejects_typed_or_structural_changes(self):
        expected = {"checkpoints": [{"id": "x", "number": 1, "enabled": True, "items": [1, 2]}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "answer.json"
            path.write_text(json.dumps(expected, sort_keys=True), encoding="utf-8")
            self.ref().validate_output(path, expected)
            malformed = [
                '{"checkpoints":[],"checkpoints":[]}', '{"x":{"a":1,"a":1}}',
                '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e9999}', '{} {}',
                json.dumps(expected).replace('"number": 1', '"number": true'),
                json.dumps(expected).replace('"enabled": true', '"enabled": 1'),
                json.dumps(expected).replace('"number": 1', '"number": 1.0'),
                json.dumps(expected).replace('[1, 2]', '[2, 1]'),
                json.dumps(expected).replace('"id": "x", ', ''),
                json.dumps(expected | {"extra": 0}),
            ]
            for raw in malformed:
                with self.subTest(raw=raw):
                    path.write_text(raw, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        self.ref().validate_output(path, expected)
            path.write_bytes(b'\xff')
            with self.assertRaises(ValueError):
                self.ref().validate_output(path, expected)
            path.write_bytes(b' ' * (32 * 1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                self.ref().validate_output(path, expected)


if __name__ == "__main__":
    unittest.main()
