"""Development-only evidence about test discrimination, never model trials.

Run from experiments/online_cutover in the trusted PostgreSQL runtime image.
Mutation implementations are copied into disposable directories, never edited
into the reference package. The normal ordering test does not inspect capture
tables or require any particular replication algorithm.
"""
import importlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import psycopg

try:
    from . import test_cutover as integration
except ImportError:  # Also support running discovery from this directory.
    import test_cutover as integration


INITIAL_TESTS = (
    "test_migration_preserves_business_and_receipts_after_source_retirement",
    "test_blocked_backfill_allows_live_changes_delete_recreate_and_retry",
    "test_killed_blocked_migration_and_concurrent_restart_converge",
)


def copy_high_watermark_mutant(parent):
    """Make a deliberately wrong consumer that treats allocation as commit order."""
    shutil.copytree(integration.ROOT / "orderbridge", parent / "orderbridge")
    path = parent / "orderbridge" / "migrate.py"
    text = path.read_text()
    edits = [
        ("BATCH = 256", "BATCH = 256\n_watermark = 0"),
        ("def refresh_batch(source_dsn, target):\n",
         "def refresh_batch(source_dsn, target):\n    global _watermark\n"),
        ('"ORDER BY change_id LIMIT %s", (BATCH,)).fetchall()',
         '"WHERE change_id>%s ORDER BY change_id LIMIT %s", (_watermark,BATCH)).fetchall()'),
        ("            # Target committed. Delete precisely",
         "            _watermark = max(change_id for change_id, _, _ in changes)\n"
         "            # Target committed. Delete precisely"),
    ]
    for old, new in edits:
        if text.count(old) != 1:
            raise AssertionError("Mutation precondition changed; update the development fixture")
        text = text.replace(old, new)
    path.write_text(text)


def run_case(case):
    result = unittest.TestResult()
    case.run(result)
    return result


class OrderingMutationTests(unittest.TestCase):
    def ordering(self):
        try:
            return importlib.import_module(".test_cutover_ordering", __package__) if __package__ else importlib.import_module("test_cutover_ordering")
        except ModuleNotFoundError:
            self.fail("The independent ordering test has not been implemented")

    def test_required_private_column_is_reported_as_fixture_incompatibility(self):
        """A setup limitation is not mislabeled as incorrect business state."""
        ordering = self.ordering()
        with tempfile.TemporaryDirectory(prefix="cutover-placeholder-compat-") as directory:
            with integration.DatabaseRuntime(root=Path(directory)) as runtime:
                runtime.seed({"A": 10})
                with psycopg.connect(runtime.source_dsn) as connection:
                    connection.execute("ALTER TABLE app.receipts ADD COLUMN private_required text NOT NULL")
                with psycopg.connect(runtime.source_dsn) as connection:
                    with self.assertRaisesRegex(ordering.OrderingSetupIncompatible, "not a task correctness verdict"):
                        ordering.insert_placeholder(connection, {"request_id": "probe"})

    def test_reference_passes_when_no_intermediate_phase_is_observed(self):
        """A bounded scheduling release is coverage metadata, not a failed task."""
        case = self.ordering().OrderingChecks("test_delayed_commit_preserves_all_business_state")
        case.phase_wait_seconds = 0
        result = run_case(case)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertEqual(case.evidence["release_reason"], "bounded_release_no_intermediate_phase")
        self.assertFalse(case.evidence["delayed_commit_fault_observed"])
        print(json.dumps({"experiment": "phase_free_reference", **case.evidence}), flush=True)

    def test_initial_three_accept_high_watermark_but_ordering_rejects_it(self):
        """The newly rejected outcome is missing committed business data."""
        ordering = self.ordering()
        with tempfile.TemporaryDirectory(prefix="cutover-watermark-mutant-") as directory:
            parent = Path(directory)
            parent.chmod(0o755)
            copy_high_watermark_mutant(parent)

            class InitialMutantChecks(integration.CutoverChecks):
                def migrate(inner):
                    return ordering.start_migration(inner.rt, parent)

            outcomes = []
            for name in INITIAL_TESTS:
                result = run_case(InitialMutantChecks(name))
                outcomes.append(result.wasSuccessful())
                self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
            case = ordering.OrderingChecks("test_delayed_commit_preserves_all_business_state")
            case.migration_parent = parent
            result = run_case(case)
            self.assertEqual(result.errors, [], result.errors)
            self.assertEqual(len(result.failures), 1, result.failures)
            self.assertIn("Target SQL differs from the independent business model", result.failures[0][1])
            self.assertTrue(case.evidence["delayed_commit_fault_observed"])
            self.assertEqual(case.evidence["actual_order_ids"], ["fast-order"])
            self.assertEqual(case.evidence["expected_order_ids"], ["fast-order", "slow-order"])
            print(json.dumps({"experiment": "high_watermark_mutant", "initial_three_passed": outcomes,
                              "ordering_rejected": True, **case.evidence}), flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
