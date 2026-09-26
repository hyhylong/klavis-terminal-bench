"""The shipped incident must be deterministic, sealed, and exercise every mechanism."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CorpusTests(unittest.TestCase):
    def test_shipped_inputs_have_portable_line_endings(self):
        for folder in ("environment/data", "tests/fixtures"):
            for name in ("feed.jsonl", "checkpoints.json"):
                data = (ROOT / "tasks/temporal-ledger-repair" / folder / name).read_bytes()
                self.assertFalse(b"\r\n" in data, "regeneration must produce identical bytes on Windows and Linux")

    def load_builder(self):
        path = ROOT / "tools" / "generate_corpus.py"
        self.assertTrue(path.exists(), "the reproducible incident generator is not implemented")
        spec = importlib.util.spec_from_file_location("corpus", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_deterministic_and_ordered(self):
        build = self.load_builder().build_corpus
        events, checkpoints = build()
        self.assertEqual((events, checkpoints), build())
        self.assertEqual([e["arrival"] for e in events], list(range(1, len(events) + 1)))
        self.assertEqual(checkpoints[0]["cutoff"], 0)
        self.assertEqual(checkpoints[-1]["cutoff"], len(events))
        self.assertGreater(len(events), 500)
        self.assertLess(len(events), 6000)
        self.assertEqual(len({c["id"] for c in checkpoints}), len(checkpoints))

    def test_seals_and_incident_mechanisms(self):
        events, _ = self.load_builder().build_corpus()
        self.assertEqual({e["kind"] for e in events}, {"row", "schema", "commit", "abort"})
        rows = [e["body"] for e in events if e["kind"] == "row"]
        self.assertEqual({r["action"]["op"] for r in rows}, {"put", "patch", "delete", "amend"})
        initial = [r for r in rows if r["tx"] == "seed"]
        commit = next(e["body"] for e in events if e["kind"] == "commit" and e["body"]["tx"] == "seed")
        seal = hashlib.sha256(json.dumps(initial, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(commit["sha256"], seal)
        self.assertTrue(any(r["action"]["op"] == "amend" and r["action"]["replacement"] is None for r in rows))
        ids = {r["tx"] for r in rows}
        self.assertTrue({"broken-seal", "missing-fragment", "conflicting-fragment", "missing-epoch", "conflicting-commit", "outside-parts"}.issubset(ids))


if __name__ == "__main__":
    unittest.main()
