"""Golden HTTP/SQL tests, independent of the business model implementation."""
from concurrent.futures import ThreadPoolExecutor
import copy
import http.client
import importlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest

import psycopg


def line(sku="A", quantity=2, price=7):
    return {"sku": sku, "quantity": quantity, "unit_price_cents": price}


def create(rid="r1", oid="o1", lines=None, customer="Customer"):
    return {"op": "create", "request_id": rid, "order_id": oid,
            "customer": customer, "lines": lines if lines is not None else [line()]}


def order(oid="o1", revision=1, lines=None, customer="Customer"):
    lines = lines if lines is not None else [line()]
    return {"order_id": oid, "customer": customer, "revision": revision,
            "lines": lines, "total_cents": sum(x["quantity"] * x["unit_price_cents"] for x in lines)}


class ValidationTests(unittest.TestCase):
    def api(self):
        try:
            return importlib.import_module("experiments.online_cutover.orderbridge.api")
        except ModuleNotFoundError:
            self.fail("Public request validation has not been implemented")

    def test_preserves_unicode_array_order_and_detaches_input(self):
        api = self.api()
        request = create(lines=[line("B", 1, 0), line("A", 3, 10)], customer="  ÅΩ🐙 ")
        actual = api.validate_request(request)
        self.assertEqual(actual, request)
        request["lines"][0]["quantity"] = 99
        self.assertEqual(actual["lines"][0]["quantity"], 1)

    def test_invalid_shapes_types_ranges_and_text_are_rejected(self):
        api = self.api()
        bad = [None, [], {}, {"op": "health", "request_id": "r"},
               {"op": "inventory", "extra": 1}, {"op": "get", "order_id": "x.y"},
               {"op": "delete", "request_id": "r", "order_id": "o", "expected_revision": True},
               {"op": "delete", "request_id": "r", "order_id": "o", "expected_revision": 2**63-1}]
        for key, values in {"request_id": ["", "x"*65, "a b", 1],
                            "customer": ["", "x"*121, None, "a\x00b", "\ud800"],
                            "lines": [[], [line(), line()], [dict(line(), extra=1)]]}.items():
            bad.extend(dict(create(), **{key: value}) for value in values)
        for key, values in {"quantity": [False, 0, -1, 1.0, 1000001],
                            "unit_price_cents": [True, -1, 1.5, 1000000001]}.items():
            bad.extend(create(lines=[dict(line(), **{key: value})]) for value in values)
        for request in bad:
            with self.subTest(request=repr(request)), self.assertRaises(api.InvalidRequest):
                api.validate_request(request)

    def test_all_public_operations_and_integer_endpoints_validate(self):
        api = self.api()
        values = [create(lines=[line("A", 1000000, 1000000000)]),
                  dict(create(), op="replace", expected_revision=2**63-2),
                  {"op": "delete", "request_id": "d", "order_id": "o", "expected_revision": 1},
                  {"op": "get", "order_id": "o"}, {"op": "health"}, {"op": "inventory"}]
        for request in values:
            self.assertEqual(api.validate_request(request), request)


class ServiceTests(unittest.TestCase):
    """Run the actual service as the restricted application identity."""
    def setUp(self):
        from experiments.online_cutover.runtime import DatabaseRuntime
        self.tmp = tempfile.TemporaryDirectory(prefix="orderbridge-service-")
        self.addCleanup(self.tmp.cleanup)
        self.rt = DatabaseRuntime(root=Path(self.tmp.name))
        self.rt.__enter__()
        self.addCleanup(self.rt.__exit__, None, None, None)
        self.rt.seed({"A": 10, "B": 5, "C": 0})
        self.child = None
        self.start_service()

    def start_service(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.child = self.rt.run_as_app(
            [sys.executable, "-B", "-m", "orderbridge", "serve", "--source", self.rt.source_dsn,
             "--target", self.rt.target_dsn, "--host", "127.0.0.1", "--port", str(self.port)],
            env={"PYTHONPATH": str(Path(__file__).resolve().parent)})
        self.addCleanup(self.child.terminate)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if self.rpc({"op": "health"})[0] == 200:
                    return
            except (OSError, http.client.HTTPException):
                pass
            if self.child.returncode is not None:
                self.fail("Service exited during startup: " + self.child.stderr_path.read_text())
            time.sleep(.02)
        self.fail("Service did not become ready")

    def rpc(self, request, timeout=10):
        client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            payload = json.dumps(request, ensure_ascii=True).encode()
            client.request("POST", "/rpc", payload, {"Content-Type": "application/json"})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def call(self, request):
        status, response = self.rpc(request)
        self.assertEqual(status, 200)
        return response

    def rows(self, database, query, params=()):
        with self.rt.inspect_connect(database) as conn:
            return conn.execute(query, params).fetchall()

    def activate_target(self):
        # This development-only fixture targets the reference route explicitly.
        # Even fixture writes must not execute app-owned triggers as an admin.
        with psycopg.connect(self.rt.target_dsn) as conn:
            conn.execute("UPDATE app.bridge_state SET active=true WHERE singleton=1")

    def assert_inventory(self, database, a=10, b=5, c=0):
        self.assertEqual(self.rows(database, "SELECT sku,capacity,available FROM app.inventory ORDER BY sku COLLATE \"C\""),
                         [("A", 10, a), ("B", 5, b), ("C", 0, c)])

    def test_source_create_replace_delete_and_receipts_are_atomic(self):
        request = create(lines=[line("B", 1, 11), line("A", 2, 7)])
        expected = order(lines=request["lines"])
        self.assertEqual(self.call(request), {"ok": True, "order": expected})
        self.assert_inventory("source", a=8, b=4)
        replacement = dict(create("r2", lines=[line("A", 9, 2)]), op="replace", expected_revision=1)
        self.assertEqual(self.call(replacement), {"ok": True, "order": order(revision=2, lines=replacement["lines"])})
        self.assert_inventory("source", a=1)
        self.assertEqual(self.call(request), {"ok": True, "order": expected})
        deleted = {"op": "delete", "request_id": "r3", "order_id": "o1", "expected_revision": 2}
        self.assertEqual(self.call(deleted), {"ok": True, "deleted": "o1", "revision": 3})
        self.assert_inventory("source")
        self.assertEqual(self.call({"op": "get", "order_id": "o1"}), {"ok": True, "order": None})
        self.assertEqual(self.rows("source", "SELECT body,response FROM app.receipts WHERE request_id='r1'"),
                         [(request, {"ok": True, "order": expected})])
        self.assertEqual(self.call(create("recreate")), {"ok": True, "order": order()})

    def test_target_stores_ordered_relations_and_releases_reservations(self):
        self.activate_target()
        req = create(lines=[line("B", 2, 8), line("A", 3, 10)], customer="  ÅΩ🐙 ")
        self.assertEqual(self.call(req), {"ok": True, "order": order(lines=req["lines"], customer=req["customer"])})
        self.assertEqual(self.rows("target", "SELECT order_id,position,sku,quantity,unit_price_cents FROM app.order_lines ORDER BY position"),
                         [("o1", 0, "B", 2, 8), ("o1", 1, "A", 3, 10)])
        self.assert_inventory("target", a=7, b=3)
        req2 = dict(create("r2", lines=[line("A", 10, 1)]), op="replace", expected_revision=1)
        self.assertTrue(self.call(req2)["ok"])
        self.assert_inventory("target", a=0)
        self.assertEqual(self.rows("target", "SELECT position,sku,quantity FROM app.order_lines"), [(0, "A", 10)])
        self.assertTrue(self.call({"op": "delete", "request_id": "r3", "order_id": "o1", "expected_revision": 2})["ok"])
        self.assertEqual(self.rows("target", "SELECT * FROM app.order_lines"), [])
        self.assert_inventory("target")
        self.assertEqual(self.rows("source", "SELECT * FROM app.orders"), [])

    def test_rejected_receipt_stays_historical_and_validation_precedes_receipts(self):
        self.assertTrue(self.call(create(lines=[line("A", 8)]))["ok"])
        rejected = create("r2", "o2", [line("A", 3)])
        self.assertEqual(self.call(rejected), {"ok": False, "error": "insufficient_stock"})
        self.assertEqual(self.call(dict(rejected, order_id="o1")), {"ok": False, "error": "request_conflict"})
        self.assertEqual(self.call(create("exists", "o1", [line("C", 1)])), {"ok": False, "error": "exists"})
        bad = dict(create("r2"), lines=[line("UNKNOWN")])
        self.assertEqual(self.rpc(bad), (400, {"ok": False, "error": "invalid_request"}))
        self.call({"op": "delete", "request_id": "del", "order_id": "o1", "expected_revision": 1})
        self.assertEqual(self.call(rejected), {"ok": False, "error": "insufficient_stock"})
        self.assertTrue(self.call(dict(rejected, request_id="new"))["ok"])
        self.assert_inventory("source", a=7)
        self.assertEqual(self.rows("source", "SELECT count(*) FROM app.receipts"), [(5,)])

    def test_missing_and_stale_precede_insufficient_and_no_validation_receipt(self):
        missing = dict(create("m", "absent", [line("C", 1)]), op="replace", expected_revision=1)
        self.assertEqual(self.call(missing), {"ok": False, "error": "missing"})
        self.call(create())
        stale = dict(create("s", lines=[line("C", 1)]), op="replace", expected_revision=2)
        self.assertEqual(self.call(stale), {"ok": False, "error": "stale_revision"})
        invalid = create("invalid", lines=[line(quantity=True)])
        self.assertEqual(self.rpc(invalid), (400, {"ok": False, "error": "invalid_request"}))
        self.assertEqual(self.rows("source", "SELECT count(*) FROM app.receipts WHERE request_id='invalid'"), [(0,)])
        self.assert_inventory("source", a=8)

    def test_duplicate_concurrent_request_reserves_stock_only_once(self):
        req = create(lines=[line("A", 7)])
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(self.call, [copy.deepcopy(req) for _ in range(8)]))
        self.assertEqual(results, [{"ok": True, "order": order(lines=req["lines"])}] * 8)
        self.assert_inventory("source", a=3)
        self.assertEqual(self.rows("source", "SELECT count(*) FROM app.receipts"), [(1,)])

    def test_conflicting_request_ids_and_inventory_competition_serialize(self):
        reqs = [create("shared", "left", [line("A", 7)]), create("shared", "right", [line("A", 6)])]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.call, reqs))
        self.assertEqual(sum(r["ok"] for r in results), 1)
        self.assertEqual(next(r for r in results if not r["ok"]), {"ok": False, "error": "request_conflict"})
        winner = next(r["order"] for r in results if r["ok"])
        self.assert_inventory("source", a=10-winner["lines"][0]["quantity"])
        reqs2 = [create("left2", "left2", [line("B", 4)]), create("right2", "right2", [line("B", 4)])]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results2 = list(pool.map(self.call, reqs2))
        self.assertEqual(sum(r["ok"] for r in results2), 1)
        self.assertEqual(next(r for r in results2 if not r["ok"]), {"ok": False, "error": "insufficient_stock"})
        self.assert_inventory("source", a=10-winner["lines"][0]["quantity"], b=1)

    def test_replacements_lock_inventory_without_order_dependent_deadlocks(self):
        self.activate_target()
        self.call(create("l", "l", [line("A", 1), line("B", 1)]))
        self.call(create("r", "r", [line("B", 1), line("A", 1)]))
        reqs = [dict(create("l2", "l", [line("B", 2), line("A", 2)]), op="replace", expected_revision=1),
                dict(create("r2", "r", [line("A", 2), line("B", 2)]), op="replace", expected_revision=1)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertTrue(all(r["ok"] for r in pool.map(self.call, reqs)))
        self.assert_inventory("target", a=6, b=1)

    def test_source_keeps_serving_while_target_business_tables_are_locked(self):
        with psycopg.connect(self.rt.target_dsn) as blocker:
            blocker.execute("LOCK TABLE app.inventory, app.orders, app.order_lines IN ACCESS EXCLUSIVE MODE")
            self.assertTrue(self.call(create())["ok"])
            self.assertEqual(self.call({"op": "get", "order_id": "o1"}), {"ok": True, "order": order()})
            self.assertEqual(self.call({"op": "health"}), {"ok": True, "backend": "source"})

    def test_waiting_source_request_rechecks_routing_after_writer_fence(self):
        with psycopg.connect(self.rt.source_dsn, autocommit=True) as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            blocker.execute("SELECT pg_advisory_lock(731902,1)")
            try:
                future = pool.submit(self.call, create())
                deadline = time.monotonic()+5
                waiting = False
                while time.monotonic() < deadline:
                    waiting = bool(self.rows("source", "SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event='advisory'"))
                    if waiting:
                        break
                    time.sleep(.01)
                self.assertTrue(waiting, "Source operation never waited behind the writer fence")
                self.activate_target()
            finally:
                blocker.execute("SELECT pg_advisory_unlock(731902,1)")
            self.assertTrue(future.result(timeout=5)["ok"])
        self.assertEqual(self.rows("source", "SELECT * FROM app.orders"), [])
        self.assertEqual(self.rows("target", "SELECT order_id FROM app.orders"), [("o1",)])

    def test_active_target_needs_no_source_even_after_service_restart(self):
        self.activate_target()
        self.rt.retire_source()
        self.assertEqual(self.call({"op": "health"}), {"ok": True, "backend": "target"})
        expected = self.call(create())
        self.assertTrue(expected["ok"])
        self.child.terminate()
        self.child.wait(timeout=5)
        self.start_service()
        self.assertEqual(self.call(create()), expected)
        self.assert_inventory("target", a=8)

    def test_http_rejects_malformed_json_wrong_media_type_and_oversized_body(self):
        for data, headers in [(b'{', {"Content-Type": "application/json"}),
                              (b'\xff', {"Content-Type": "application/json"}),
                              (b'{}', {"Content-Type": "text/plain"})]:
            client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            try:
                client.request("POST", "/rpc", data, headers)
                res = client.getresponse()
                self.assertEqual((res.status, json.loads(res.read())), (400, {"ok": False, "error": "invalid_request"}))
            finally:
                client.close()
        client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            client.putrequest("POST", "/rpc")
            client.putheader("Content-Type", "application/json")
            client.putheader("Content-Length", str(1048577))
            client.endheaders()
            res = client.getresponse()
            self.assertEqual((res.status, json.loads(res.read())), (400, {"ok": False, "error": "invalid_request"}))
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
