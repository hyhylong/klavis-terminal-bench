"""Black-box migration recovery after each observed target COMMIT ACK is lost.

Run in the trusted PG image with PYTHONPATH pointing at this directory and
RUN_PG_PROXY_INTEGRATION=1. Only migration target connections use the proxy.
The serving processes and app-role SQL inspection connect directly. There is
no assumed migration phase/table, SQL text inspection, or fixed commit count.
Timeouts are development hang guards, not published task latency thresholds.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

if __package__:
    from .model import Model
    from .pg_fault_proxy import PostgresFaultProxy
    from .runtime import DatabaseRuntime
    from .test_cutover import free_port, request, source_state, target_state
else:
    from model import Model
    from pg_fault_proxy import PostgresFaultProxy
    from runtime import DatabaseRuntime
    from test_cutover import free_port, request, source_state, target_state


ROOT = Path(__file__).resolve().parent
CAPACITIES = {"A": 100, "B": 80, "C": 50}


def line(sku, quantity, price):
    return {"sku": sku, "quantity": quantity, "unit_price_cents": price}


def create(request_id, order_id, customer, lines):
    return {"op": "create", "request_id": request_id, "order_id": order_id,
            "customer": customer, "lines": lines}


@unittest.skipUnless(os.environ.get("RUN_PG_PROXY_INTEGRATION") == "1",
                     "set RUN_PG_PROXY_INTEGRATION=1 in the trusted PG image")
class MigrationAcknowledgementTests(unittest.TestCase):
    def launch_server(self, runtime):
        port = free_port()
        process = runtime.run_as_app(
            [sys.executable, "-m", "orderbridge", "serve", "--source", runtime.source_dsn,
             "--target", runtime.target_dsn, "--host", "127.0.0.1", "--port", str(port)],
            env={"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.assertIsNone(process.poll(), "Serving process exited; inspect its private logs")
            try:
                response = request(port, {"op": "health"}, timeout=.5)
                if response in ({"ok": True, "backend": "source"},
                                {"ok": True, "backend": "target"}):
                    return port, process
            except (OSError, HTTPError, URLError):
                pass
            time.sleep(.03)
        self.fail("Serving process did not become healthy within development hang guard")

    def launch_migration(self, runtime, target_dsn):
        return runtime.run_as_app(
            [sys.executable, "-m", "orderbridge", "migrate", "--source", runtime.source_dsn,
             "--target", target_dsn],
            env={"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})

    def finish(self, process, require_success=True):
        try:
            code = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.terminate()
            # TimeoutExpired includes the argv, which contains application DSNs.
            raise AssertionError("Migration exceeded development hang guard; inspect private logs") from None
        if require_success:
            self.assertEqual(code, 0, "Migration recovery failed; inspect its private logs")
        return code

    def call(self, port, model, body):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            response = request(port, body, timeout=5)
            if response != {"ok": False, "error": "retry"}:
                self.assertEqual(response, model.apply(body))
                return response
            time.sleep(.03)
        self.fail("Business operation did not progress within development hang guard")

    def expected_sql(self, model):
        orders, receipts = model.orders, model.receipts
        return {
            "orders": [orders[key] for key in sorted(orders)],
            "stock": model.apply({"op": "inventory"})["stock"],
            "receipts": [{"request_id": key, **receipts[key]} for key in sorted(receipts)],
        }

    def check_public_state(self, runtime, port, model, database):
        self.call(port, model, {"op": "inventory"})
        for order_id in [*sorted(model.orders), "never-existed"]:
            self.call(port, model, {"op": "get", "order_id": order_id})
        # Recheck every historical success and rejection against the independent
        # oracle, including receipts whose orders were deleted or recreated.
        for receipt in model.receipts.values():
            self.call(port, model, receipt["body"])
        with runtime.inspect_connect(database, autocommit=False) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            actual = source_state(connection) if database == "source" else target_state(connection)
        self.assertEqual(actual, self.expected_sql(model))

    def seeded_model(self):
        model = Model(CAPACITIES)
        requests = [
            create("seed-create", "seed-order", "Original", [line("B", 2, 35), line("A", 3, 100)]),
            {"op": "replace", "request_id": "seed-replace", "order_id": "seed-order",
             "expected_revision": 1, "customer": "Seed state", "lines": [line("A", 4, 101), line("B", 1, 35)]},
            create("seed-gone", "gone", "Delete and recreate", [line("C", 2, 10)]),
            {"op": "delete", "request_id": "seed-rejection", "order_id": "future", "expected_revision": 1},
        ]
        for body in requests:
            model.apply(body)
        self.assertEqual(model.orders["seed-order"]["total_cents"], 439)
        self.assertEqual(model.receipts["seed-rejection"]["response"], {"ok": False, "error": "missing"})
        return model

    def changes_while_blocked(self, runtime, port, model):
        self.assertEqual(request(port, {"op": "health"}), {"ok": True, "backend": "source"})
        operations = [
            {"op": "replace", "request_id": "live-replace", "order_id": "seed-order",
             "expected_revision": 2, "customer": "During blocked copy", "lines": [line("B", 3, 42), line("A", 5, 117)]},
            {"op": "delete", "request_id": "live-delete", "order_id": "gone", "expected_revision": 1},
            create("live-recreate", "gone", "New incarnation", [line("C", 3, 19)]),
            create("live-future", "future", "Previously rejected", [line("A", 1, 23)]),
            create("live-new", "live-order", "Concurrent source", [line("A", 7, 13)]),
        ]
        for body in operations:
            self.call(port, model, body)
        self.check_public_state(runtime, port, model, "source")
        return len(operations)

    def wait_for_public_block_or_early_fault(self, runtime, process, proxy, blocker_pid):
        target_name = conninfo_to_dict(runtime.target_dsn)["dbname"]
        deadline = time.monotonic() + 15
        # Administrator access is confined to trusted PostgreSQL catalogs.
        with runtime.admin_connect("postgres") as monitor:
            while time.monotonic() < deadline:
                blocked = monitor.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_stat_activity a "
                    "WHERE a.datname=%s AND %s=ANY(pg_catalog.pg_blocking_pids(a.pid)))",
                    (target_name, blocker_pid)).fetchone()[0]
                if blocked:
                    return True
                if any(event.get("ack_dropped") for event in proxy.events):
                    # A setup transaction may have committed before the initial
                    # copy could reach the public table. Do not await a dead phase.
                    return False
                self.assertIsNone(process.poll(), "Migration exited before the public lock barrier without the selected fault")
                time.sleep(.03)
        self.fail("No observable public-table lock wait within development hang guard")

    def run_case(self, fail_commit):
        began = time.monotonic()
        record = {"fail_commit": fail_commit, "status": "running", "phase": "setup"}
        proxy = None
        try:
            with tempfile.TemporaryDirectory(prefix="cutover-ack-") as directory:
                Path(directory).chmod(0o755)
                with DatabaseRuntime(root=Path(directory) / "runtime") as runtime:
                    model = self.seeded_model()
                    seed = self.expected_sql(model)
                    runtime.seed(CAPACITIES, seed["orders"], seed["receipts"])
                    port, serving = self.launch_server(runtime)
                    self.check_public_state(runtime, port, model, "source")
                    with PostgresFaultProxy("127.0.0.1", runtime.port, fail_commit=fail_commit) as proxy:
                        target_dsn = make_conninfo(runtime.target_dsn, host="127.0.0.1", port=proxy.port,
                                                  sslmode="disable", gssencmode="disable")
                        record["phase"] = "initial_migration"
                        # The lock is owned by the restricted application role;
                        # no administrator executes artifact-owned business SQL.
                        with psycopg.connect(runtime.target_dsn, autocommit=False) as barrier:
                            blocker_pid = barrier.execute("SELECT pg_catalog.pg_backend_pid()").fetchone()[0]
                            barrier.execute("LOCK TABLE app.order_lines IN SHARE MODE")
                            first = self.launch_migration(runtime, target_dsn)
                            reached = self.wait_for_public_block_or_early_fault(runtime, first, proxy, blocker_pid)
                            record["public_barrier_reached"] = reached
                            record["source_mutations_while_blocked"] = self.changes_while_blocked(runtime, port, model) if reached else 0
                            barrier.commit()
                        # Either successful internal recovery or nonzero exit is
                        # allowed after an unknown commit; no exit code is forced.
                        record["initial_exit_code"] = self.finish(first, require_success=fail_commit is None)
                        initial = [event for event in proxy.events if event["event"] == "commit"]
                        record["initial_commit_ordinals"] = [event["ordinal"] for event in initial]
                        drops = [event for event in initial if event["ack_dropped"]]
                        self.assertEqual([event["ordinal"] for event in drops], [] if fail_commit is None else [fail_commit])

                        record["phase"] = "fresh_process_recovery"
                        record["recovery_exit_codes"] = [self.finish(self.launch_migration(runtime, target_dsn))]
                        self.assertEqual(request(port, {"op": "health"}), {"ok": True, "backend": "target"})
                        self.check_public_state(runtime, port, model, "target")

                        record["phase"] = "new_business_then_idempotent_retry"
                        revision = model.orders["seed-order"]["revision"]
                        self.call(port, model, {"op": "replace", "request_id": "post-recovery-replace",
                            "order_id": "seed-order", "expected_revision": revision, "customer": "New target state",
                            "lines": [line("C", 4, 211), line("A", 2, 37)]})
                        self.call(port, model, create("post-recovery-create", "after-fault", "Must survive retry", [line("B", 6, 53)]))
                        self.call(port, model, {"op": "delete", "request_id": "post-recovery-delete", "order_id": "gone",
                                              "expected_revision": model.orders["gone"]["revision"]})
                        self.call(port, model, create("post-recovery-recreate", "gone", "Target incarnation", [line("B", 2, 29)]))
                        record["recovery_exit_codes"].append(self.finish(self.launch_migration(runtime, target_dsn)))
                        self.check_public_state(runtime, port, model, "target")

                        record["phase"] = "retired_source_and_fresh_processes"
                        runtime.retire_source()
                        serving.terminate()
                        port, serving = self.launch_server(runtime)
                        self.assertEqual(request(port, {"op": "health"}), {"ok": True, "backend": "target"})
                        self.call(port, model, create("retired-source-write", "retired-source-order", "Target alone", [line("C", 2, 31)]))
                        record["recovery_exit_codes"].append(self.finish(self.launch_migration(runtime, target_dsn)))
                        self.check_public_state(runtime, port, model, "target")
                        self.assertFalse([event for event in proxy.events if event["event"] == "protocol_error"], "Proxy protocol error is a harness failure")
                        self.assertEqual(sum(bool(event.get("ack_dropped")) for event in proxy.events), 0 if fail_commit is None else 1)
                        record.update(status="passed", phase="complete", source_retired=True,
                                      expected_order_count=len(model.orders), expected_receipt_count=len(model.receipts))
            return record
        finally:
            if record["status"] != "passed":
                record["status"] = "failed"
            record["elapsed_seconds"] = round(time.monotonic() - began, 6)
            if proxy is not None:
                record["proxy_events"] = proxy.events
            # Evidence contains counters/outcomes only, never DSNs or SQL bodies.
            print("CUTOVER_ACK_CASE " + json.dumps(record, sort_keys=True), flush=True)

    def test_every_observed_initial_target_commit_ack_can_be_lost(self):
        baseline = self.run_case(None)
        ordinals = baseline["initial_commit_ordinals"]
        if not ordinals:
            self.skipTest("Correct baseline emitted no explicit COMMIT ACK; this fault fixture is not applicable")
        for ordinal in ordinals:
            with self.subTest(fail_commit=ordinal):
                self.run_case(ordinal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
