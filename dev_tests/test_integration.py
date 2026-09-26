"""Independent algorithms, metamorphic checks, and corrupted artifact rejection."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "tasks/temporal-ledger-repair"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = load("integration_oracle", TASK / "solution/reconstruct.py")
        cls.verifier = load("integration_verifier", TASK / "tests/reference.py")
        cls.generator = load("integration_generator", ROOT / "tools/generate_corpus.py")

    def test_independent_algorithms_agree_across_incidents(self):
        for seed in [20260926, 7, 41, 101, 137, 2026, 8675309, 999999]:
            with self.subTest(seed=seed):
                events, checkpoints = self.generator.build_corpus(seed)
                expected = self.verifier.reconstruct(events, checkpoints)
                actual = self.oracle.reconstruct(events, checkpoints)
                self.verifier.compare_output(actual, expected)

    def test_later_deliveries_never_change_earlier_knowledge(self):
        events, checkpoints = self.generator.build_corpus()
        for checkpoint in checkpoints[::3]:
            with self.subTest(checkpoint=checkpoint["id"]):
                prefix = [e for e in events if e["arrival"] <= checkpoint["cutoff"]]
                for implementation in (self.oracle, self.verifier):
                    self.assertEqual(implementation.reconstruct(events, [checkpoint]),
                                     implementation.reconstruct(prefix, [checkpoint]))

    def test_identical_redelivery_is_idempotent(self):
        events, _ = self.generator.build_corpus()
        duplicates = [dict(deepcopy(e), arrival=len(events) + i) for i, e in enumerate(events, 1)]
        for implementation in (self.oracle, self.verifier):
            before = implementation.reconstruct(events, [{"id": "same", "cutoff": len(events)}])
            after = implementation.reconstruct(events + duplicates, [{"id": "same", "cutoff": 2 * len(events)}])
            self.assertEqual(before, after)

    def test_trusted_fixture_is_byte_identical_to_public_incident(self):
        for filename in ("feed.jsonl", "checkpoints.json"):
            self.assertEqual((TASK / "environment/data" / filename).read_bytes(),
                             (TASK / "tests/fixtures" / filename).read_bytes())

    def test_wrong_recoveries_are_rejected(self):
        events, checkpoints = self.generator.build_corpus()
        expected = self.oracle.reconstruct(events, checkpoints)
        mutations = []
        for key, value in [("from", 999999), ("to", -999999), ("deleted", 0)]:
            wrong = deepcopy(expected)
            wrong["checkpoints"][1]["entities"][0]["segments"][0][key] = value
            mutations.append((key, wrong))
        wrong = deepcopy(expected)
        wrong["checkpoints"][1]["entities"][0]["segments"][0]["origins"]["quota"] = "forged/0"
        mutations.append(("forged provenance", wrong))
        wrong = deepcopy(expected)
        wrong["checkpoints"][-1]["transactions"][0]["state"] = "pending"
        mutations.append(("wrong eligibility", wrong))
        wrong = deepcopy(expected)
        wrong["checkpoints"][-1]["entities"].pop()
        mutations.append(("omitted entity", wrong))
        wrong = deepcopy(expected)
        wrong["checkpoints"].reverse()
        mutations.append(("wrong checkpoint order", wrong))
        for label, wrong in mutations:
            with self.subTest(mutation=label):
                with self.assertRaises(ValueError):
                    self.verifier.compare_output(wrong, expected)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answer.json"
            path.write_text(json.dumps(expected), encoding="utf-8")
            self.verifier.validate_output(path, expected)


if __name__ == "__main__":
    unittest.main()
