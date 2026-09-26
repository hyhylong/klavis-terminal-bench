"""Public-relation delayed-commit schedule checked against the independent model.

Only the new scenario is collected. A CutoverChecks instance supplies lifecycle
helpers through composition, without inheriting its three existing tests.
Observed scheduling phases improve fault coverage; they are never requirements
on the submitted migration algorithm. Missing phases cause a bounded release.
This authoring schedule assumes the three-column receipt INSERT is supported.
The current readable-column contract alone does not guarantee that when extra
private NOT NULL columns exist. OrderingSetupIncompatible is a fixture error,
not a semantic failure or model-difficulty observation; packaging must disclose
this SQL test interface or provide another barrier.
"""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import sys
import time
import unittest
from urllib.error import URLError

import psycopg
from psycopg.types.json import Jsonb

try:
    from . import test_cutover as integration
    from .model import Model
except ImportError:  # Also support running discovery from this directory.
    import test_cutover as integration
    from model import Model


CAPACITIES = {"A": 100, "B": 80, "C": 50}


class OrderingSetupIncompatible(RuntimeError):
    """The placeholder fixture could not be installed; no semantic judgment."""


def insert_placeholder(connection, body):
    try:
        connection.execute("INSERT INTO app.receipts(request_id,body,response) VALUES (%s,%s,%s)",
                           (body["request_id"], Jsonb(body), Jsonb({"ok": False, "error": "missing"})))
    except psycopg.Error as exc:
        raise OrderingSetupIncompatible(
            "Receipt-placeholder setup unavailable (SQLSTATE %s); this is not a task correctness verdict. "
            "The eventual contract must explicitly permit this transactional INSERT or use a different barrier."
            % exc.sqlstate) from exc


def start_migration(runtime, package_parent):
    return runtime.run_as_app(
        [sys.executable, "-B", "-m", "orderbridge", "migrate",
         "--source", runtime.source_dsn, "--target", runtime.target_dsn],
        env={"PYTHONPATH": str(package_parent), "PYTHONDONTWRITEBYTECODE": "1"})


def observe(predicate, seconds):
    """Return observed evidence or None; an absent phase never fails a task."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.01)
    return None


def expected_sql(model):
    orders, receipts = model.orders, model.receipts
    return {"orders": [orders[key] for key in sorted(orders)],
            "stock": model.apply({"op": "inventory"})["stock"],
            "receipts": [{"request_id": key, **receipts[key]} for key in sorted(receipts)]}


class OrderingChecks(unittest.TestCase):
    phase_wait_seconds = 3.0  # Scheduling observation only, not a scored latency.
    migration_parent = integration.ROOT

    def setUp(self):
        self.harness = integration.CutoverChecks()
        self.addCleanup(self.harness.doCleanups)
        self.harness.setUp()
        self.rt = self.harness.rt
        self.evidence = {}

    def call_until_answer(self, body):
        """Retry an unchanged request after retry or an unknown lost response."""
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                response = integration.request(self.harness.port, body, timeout=30)
                if response != {"ok": False, "error": "retry"}:
                    return response
            except (OSError, URLError, http.client.HTTPException):
                pass
            time.sleep(.01)
        self.fail("Public request did not complete after its transactional barriers were released")

    def test_delayed_commit_preserves_all_business_state(self):
        slow = {"op": "create", "request_id": "slow", "order_id": "slow-order",
                "customer": "Slow", "lines": [{"sku": "A", "quantity": 3, "unit_price_cents": 11}]}
        fast = {"op": "create", "request_id": "fast", "order_id": "fast-order",
                "customer": "Fast", "lines": [{"sku": "B", "quantity": 4, "unit_price_cents": 13}]}
        model = Model(CAPACITIES)
        # The requests use disjoint orders and stocks, so either serialization
        # order yields these same responses and relations.
        fast_expected, slow_expected = model.apply(fast), model.apply(slow)
        initial_wait = slow_wait = fast_before_release = False
        reason = "bounded_release_no_intermediate_phase"

        # Even LOCK and the uncommitted placeholder use the app role. A future
        # package may replace business relations with views/functions; trusted
        # admin authority is confined to pg_catalog monitoring below.
        with psycopg.connect(self.rt.target_dsn) as target_lock:
            target_lock.execute("LOCK TABLE app.order_lines IN SHARE MODE")
            blocker = target_lock.execute("SELECT pg_catalog.pg_backend_pid()").fetchone()[0]
            migrating = start_migration(self.rt, self.migration_parent)
            with self.rt.admin_connect("postgres") as monitor:
                initial_wait = bool(observe(lambda: monitor.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_stat_activity "
                    "WHERE %s=ANY(pg_catalog.pg_blocking_pids(pid)))", (blocker,)).fetchone()[0],
                    self.phase_wait_seconds))
                with psycopg.connect(self.rt.source_dsn) as placeholder, ThreadPoolExecutor(max_workers=2) as pool:
                    # This row is never committed or an expected business event.
                    # It makes the real service's receipt INSERT wait for a
                    # public unique constraint, after preceding business writes.
                    insert_placeholder(placeholder, slow)
                    placeholder_pid = placeholder.execute("SELECT pg_catalog.pg_backend_pid()").fetchone()[0]
                    future_slow = pool.submit(self.call_until_answer, slow)
                    try:
                        waiting = observe(lambda: monitor.execute(
                            "SELECT pid FROM pg_catalog.pg_stat_activity "
                            "WHERE %s=ANY(pg_catalog.pg_blocking_pids(pid))", (placeholder_pid,)).fetchall(),
                            self.phase_wait_seconds)
                        slow_wait = bool(waiting)
                        slow_pid = waiting[0][0] if waiting else None
                        future_fast = pool.submit(self.call_until_answer, fast)
                        fast_before_release = bool(observe(future_fast.done, self.phase_wait_seconds))
                        target_lock.commit()

                        with self.rt.inspect_connect("target") as observer:
                            observer.execute("SET statement_timeout='250ms'")

                            def release_observation():
                                if slow_pid is not None and monitor.execute(
                                    "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_stat_activity "
                                    "WHERE %s=ANY(pg_catalog.pg_blocking_pids(pid)))", (slow_pid,)).fetchone()[0]:
                                    return "migration_waits_on_slow_transaction"
                                try:
                                    if observer.execute("SELECT EXISTS(SELECT 1 FROM app.receipts WHERE request_id='fast')").fetchone()[0]:
                                        return "fast_receipt_visible_at_target"
                                except psycopg.errors.QueryCanceled:
                                    pass
                                if migrating.returncode is not None:
                                    return "migration_exited_before_release"
                                return None

                            observed = observe(release_observation, self.phase_wait_seconds)
                            if observed:
                                reason = observed
                    finally:
                        # Always unblock the writer, including for an algorithm
                        # whose drain uses application polling rather than a
                        # PostgreSQL lock or an observable intermediate copy.
                        placeholder.rollback()
                        target_lock.rollback()
                    self.assertEqual(future_fast.result(timeout=35), fast_expected)
                    self.assertEqual(future_slow.result(timeout=35), slow_expected)

        self.harness.finish(migrating)
        expected = expected_sql(model)
        with self.rt.inspect_connect("target") as target:
            actual = integration.target_state(target)
        self.evidence = {
            "initial_backfill_wait_observed": initial_wait,
            "slow_receipt_wait_observed": slow_wait,
            "fast_answer_before_backfill_release": fast_before_release,
            "release_reason": reason,
            "delayed_commit_fault_observed": bool(initial_wait and slow_wait and fast_before_release and reason in {
                "fast_receipt_visible_at_target", "migration_waits_on_slow_transaction"}),
            "expected_order_ids": [row["order_id"] for row in expected["orders"]],
            "actual_order_ids": [row["order_id"] for row in actual["orders"]],
            "expected_stock": expected["stock"], "actual_stock": actual["stock"],
            "actual_receipt_ids": [row["request_id"] for row in actual["receipts"]],
            "target_matches_model": actual == expected,
        }
        print(json.dumps({"experiment": "delayed_commit_ordering", **self.evidence}), flush=True)
        self.assertEqual(actual, expected, "Target SQL differs from the independent business model")
        self.assertEqual(self.call_until_answer(slow), slow_expected)
        self.assertEqual(self.call_until_answer(fast), fast_expected)
        self.assertEqual(self.call_until_answer({"op": "inventory"}), model.apply({"op": "inventory"}))
        self.assertEqual(self.call_until_answer({"op": "health"}), {"ok": True, "backend": "target"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
