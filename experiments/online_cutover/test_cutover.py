"""Independent SQL and API checks for the authoring migration experiment."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg
from psycopg.conninfo import conninfo_to_dict
try:
    from .model import Model
    from .runtime import DatabaseRuntime
except ImportError:  # unittest discovery also loads these as top-level modules.
    from model import Model
    from runtime import DatabaseRuntime


ROOT = Path(__file__).resolve().parent


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request(port, body, timeout=5):
    wire = json.dumps(body, ensure_ascii=True).encode()
    req = Request(f"http://127.0.0.1:{port}/rpc", data=wire,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def source_state(connection):
    """Read independently of the submitted/reference backend's serializer."""
    with connection.cursor() as cur:
        cur.execute("SELECT order_id,customer,revision,lines FROM app.orders ORDER BY order_id")
        orders = [{"order_id": key, "customer": customer, "revision": revision,
                   "lines": lines,
                   "total_cents": sum(line["quantity"] * line["unit_price_cents"] for line in lines)}
                  for key, customer, revision, lines in cur.fetchall()]
        cur.execute("SELECT sku,capacity,available FROM app.inventory ORDER BY sku")
        stock = [dict(zip(("sku", "capacity", "available"), row)) for row in cur.fetchall()]
        cur.execute("SELECT request_id,body,response FROM app.receipts ORDER BY request_id")
        receipts = [dict(zip(("request_id", "body", "response"), row)) for row in cur.fetchall()]
    return {"orders": orders, "stock": stock, "receipts": receipts}


def target_state(connection):
    with connection.cursor() as cur:
        cur.execute("SELECT order_id,customer,revision FROM app.orders ORDER BY order_id")
        headers = cur.fetchall()
        cur.execute("SELECT order_id,position,sku,quantity,unit_price_cents "
                    "FROM app.order_lines ORDER BY order_id,position")
        groups = {}
        for key, position, sku, quantity, price in cur.fetchall():
            rows = groups.setdefault(key, [])
            if position != len(rows):
                raise AssertionError(f"Noncontiguous line positions for {key}")
            rows.append({"sku": sku, "quantity": quantity, "unit_price_cents": price})
        orders = []
        for key, customer, revision in headers:
            lines = groups.pop(key, [])
            if not lines:
                raise AssertionError(f"Order has no lines: {key}")
            orders.append({"order_id": key, "customer": customer, "revision": revision,
                           "lines": lines, "total_cents": sum(
                               line["quantity"] * line["unit_price_cents"] for line in lines)})
        if groups:
            raise AssertionError("Orphan target lines")
        cur.execute("SELECT sku,capacity,available FROM app.inventory ORDER BY sku")
        stock = [dict(zip(("sku", "capacity", "available"), row)) for row in cur.fetchall()]
        cur.execute("SELECT request_id,body,response FROM app.receipts ORDER BY request_id")
        receipts = [dict(zip(("request_id", "body", "response"), row)) for row in cur.fetchall()]
    return {"orders": orders, "stock": stock, "receipts": receipts}


def model_state(model):
    """Build independent expected relations, including historical receipts."""
    orders, receipts = model.orders, model.receipts
    return {"orders": [orders[key] for key in sorted(orders)],
            "stock": model.apply({"op": "inventory"})["stock"],
            "receipts": [dict(request_id=key, **receipts[key]) for key in sorted(receipts)]}


class CutoverChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cutover-check-")
        self.addCleanup(self.temporary.cleanup)
        Path(self.temporary.name).chmod(0o755)
        self.rt = DatabaseRuntime(root=Path(self.temporary.name) / "runtime")
        self.rt.__enter__()
        self.addCleanup(self.rt.__exit__, None, None, None)
        self.rt.seed({"A": 100, "B": 80, "C": 50})
        self.model = Model({"A": 100, "B": 80, "C": 50})
        self.observed_phases = []
        self.port, self.server = self.start_server()

    def start_server(self):
        port = free_port()
        proc = self.rt.run_as_app(
            [sys.executable, "-m", "orderbridge", "serve", "--source", self.rt.source_dsn,
             "--target", self.rt.target_dsn, "--host", "127.0.0.1", "--port", str(port)],
            env={"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if proc.returncode is not None:
                self.fail("Server exited: " + proc.stderr_path.read_text(errors="replace")[-2000:])
            try:
                request(port, {"op": "health"}, timeout=0.5)
                return port, proc
            except (OSError, HTTPError, URLError):
                time.sleep(0.05)
        self.fail("Server did not become healthy")

    def migrate(self):
        return self.rt.run_as_app(
            [sys.executable, "-m", "orderbridge", "migrate", "--source", self.rt.source_dsn,
             "--target", self.rt.target_dsn],
            env={"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})

    def finish(self, process):
        code = process.wait(timeout=30)
        self.assertEqual(code, 0, process.stderr_path.read_text(errors="replace")[-3000:])

    def call(self, body):
        actual = request(self.port, body)
        if body.get("op") != "health":
            self.assertEqual(actual, self.model.apply(body))
        return actual

    def create(self, request_id, order_id, quantity=2):
        body = {"op": "create", "request_id": request_id, "order_id": order_id,
                "customer": "Synthetic customer",
                "lines": [{"sku": "A", "quantity": quantity, "unit_price_cents": 125}]}
        response = self.call(body)
        self.assertTrue(response["ok"], response)
        return body, response

    def compare_databases(self):
        # A relation can contain an application-owned view/function. Inspect
        # business data as the app role, never as PostgreSQL superuser.
        # A legal migration can activate before a scheduling barrier is seen.
        # Source no longer has to track subsequent target mutations.
        with self.rt.inspect_connect("target") as target:
            self.assertEqual(target_state(target), model_state(self.model))

    def observe_target_wait(self, process):
        """A missing implementation phase is coverage information, not failure."""
        deadline = time.monotonic() + 2
        with self.rt.admin_connect("postgres") as monitor:
            while time.monotonic() < deadline:
                if process.returncode is not None:
                    self.finish(process)
                    phase = "completed_without_lock_wait"
                    break
                waiting = monitor.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname=%s AND wait_event_type='Lock'",
                    (conninfo_to_dict(self.rt.target_dsn)["dbname"],)).fetchone()[0]
                if waiting:
                    phase = "target_lock_wait"
                    break
                time.sleep(.02)
            else:
                phase = "no_lock_wait_observed"
        self.observed_phases.append(phase)
        return phase

    def assert_target_survives_retirement(self, original_body, original_response):
        self.assertEqual(self.call({"op": "health"}), {"ok": True, "backend": "target"})
        self.rt.retire_source()
        self.server.terminate()
        self.server.wait(timeout=10)
        self.port, self.server = self.start_server()
        self.assertEqual(self.call(original_body), original_response)
        self.create("after-retirement", "after-retirement", 3)
        self.finish(self.migrate())
        self.assertEqual(self.call({"op": "health"}), {"ok": True, "backend": "target"})
        with self.rt.inspect_connect("target") as target:
            self.assertEqual(target_state(target), model_state(self.model))

    def test_migration_preserves_business_and_receipts_after_source_retirement(self):
        body, response = self.create("first", "one", 3)
        rejected = {"op": "delete", "request_id": "rejected", "order_id": "absent",
                    "expected_revision": 1}
        self.assertEqual(self.call(rejected), {"ok": False, "error": "missing"})
        self.finish(self.migrate())
        self.compare_databases()
        self.assert_target_survives_retirement(body, response)
        self.assertEqual(self.call(rejected), {"ok": False, "error": "missing"})

    def test_blocked_backfill_allows_live_changes_delete_recreate_and_retry(self):
        old_body, old_response = self.create("original", "one", 3)
        with psycopg.connect(self.rt.target_dsn) as lock:
            lock.execute("LOCK TABLE app.order_lines IN SHARE MODE")
            migrating = self.migrate()
            phase = self.observe_target_wait(migrating)
            if phase != "target_lock_wait":
                lock.commit()
            self.assertIn(self.call({"op": "health"}),
                          ({"ok": True, "backend": "source"}, {"ok": True, "backend": "target"}))
            deletion = {"op": "delete", "request_id": "delete", "order_id": "one",
                        "expected_revision": 1}
            self.assertEqual(self.call(deletion), {"ok": True, "deleted": "one", "revision": 2})
            self.create("recreate", "one", 7)
            self.create("parallel", "two", 4)
            self.assertEqual(self.call(old_body), old_response)
            self.assertEqual(self.call({"op": "get", "order_id": "one"})["order"]["lines"][0]["quantity"], 7)
            lock.commit()
        self.finish(migrating)
        self.compare_databases()
        self.assert_target_survives_retirement(old_body, old_response)

    def test_killed_blocked_migration_and_concurrent_restart_converge(self):
        body, response = self.create("original", "one", 3)
        with psycopg.connect(self.rt.target_dsn) as lock:
            lock.execute("LOCK TABLE app.order_lines IN SHARE MODE")
            first = self.migrate()
            phase = self.observe_target_wait(first)
            if phase == "target_lock_wait" and first.returncode is None:
                # A completion race is legal; do not require a nonzero exit.
                first.kill()
            else:
                lock.commit()
            self.create("during-restart", "two", 5)
            second, third = self.migrate(), self.migrate()
            lock.commit()
        self.finish(second)
        self.finish(third)
        if phase != "target_lock_wait":
            self.finish(first)
        self.compare_databases()
        self.assert_target_survives_retirement(body, response)


if __name__ == "__main__":
    unittest.main(verbosity=2)
