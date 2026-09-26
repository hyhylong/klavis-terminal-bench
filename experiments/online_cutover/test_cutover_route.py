"""Opaque TCP gate tests and opt-in stale-route discrimination experiment.

This is an authoring coverage probe, not an unconditional task requirement.
No new source connection, an already finished request, or migration needing
that held connection yields coverage_absent. The temporary mutant is tied to
the author reference solely to demonstrate the schedule's discrimination;
the schedule and TCP gate do not inspect SQL, private tables, or lock IDs.
"""

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError

try:
    from experiments.online_cutover.connection_gate import ConnectionGate
except ModuleNotFoundError as error:
    if error.name != "experiments.online_cutover.connection_gate":
        raise
    ConnectionGate = None


ROOT = Path(__file__).resolve().parent


def receive(stream, size):
    result = bytearray()
    while len(result) < size:
        chunk = stream.recv(size - len(result))
        if not chunk:
            raise AssertionError("synthetic stream closed early")
        result.extend(chunk)
    return bytes(result)


class ConnectionGateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(ConnectionGate, "Connection gate is not implemented")

    @contextmanager
    def upstream(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(2)
            yield listener

    def test_only_next_new_connection_waits_existing_and_later_streams_pass(self):
        with self.upstream() as listener, ConnectionGate("127.0.0.1", listener.getsockname()[1]) as gate:
            with socket.create_connection(("127.0.0.1", gate.port), timeout=2) as existing:
                original, _ = listener.accept()
                with original:
                    original.settimeout(2)
                    gate.arm()
                    with socket.create_connection(("127.0.0.1", gate.port), timeout=2) as held:
                        held.sendall(b"opaque-auth-and-data\x00\xff")
                        self.assertTrue(gate.wait_held(2))
                        listener.settimeout(.1)
                        with self.assertRaises(socket.timeout):
                            listener.accept()
                        # The gate does not stall a preexisting connection.
                        existing.sendall(b"before")
                        self.assertEqual(receive(original, 6), b"before")
                        original.sendall(b"reply")
                        self.assertEqual(receive(existing, 5), b"reply")
                        gate.release()
                        listener.settimeout(2)
                        resumed, _ = listener.accept()
                        with resumed:
                            resumed.settimeout(2)
                            self.assertEqual(receive(resumed, 22), b"opaque-auth-and-data\x00\xff")
                            resumed.sendall(b"continued")
                            self.assertEqual(receive(held, 9), b"continued")
                    with socket.create_connection(("127.0.0.1", gate.port), timeout=2) as later:
                        passed, _ = listener.accept()
                        with passed:
                            later.sendall(b"later")
                            self.assertEqual(receive(passed, 5), b"later")
            self.assertEqual([event["held"] for event in gate.events if event["event"] == "accepted"], [False, True, False])
            self.assertEqual([event["event"] for event in gate.events].count("released"), 1)
            snapshot = gate.events
            snapshot[0]["connection"] = -1
            self.assertEqual(gate.events[0]["connection"], 1)

    def test_release_before_interception_cancels_pending_arm(self):
        with self.upstream() as listener, ConnectionGate("127.0.0.1", listener.getsockname()[1]) as gate:
            gate.arm()
            self.assertFalse(gate.wait_held(.02))
            gate.release()
            with socket.create_connection(("127.0.0.1", gate.port), timeout=2) as client:
                server, _ = listener.accept()
                with server:
                    client.sendall(b"pooled-strategy-coverage-absent")
                    self.assertEqual(receive(server, 31), b"pooled-strategy-coverage-absent")
            self.assertFalse(gate.wait_held(.02))

    def test_close_unblocks_held_connection_and_is_bounded_and_idempotent(self):
        with self.upstream() as listener:
            gate = ConnectionGate("127.0.0.1", listener.getsockname()[1])
            gate.__enter__()
            self.addCleanup(gate.close)
            gate.arm()
            with socket.create_connection(("127.0.0.1", gate.port), timeout=2) as held:
                self.assertTrue(gate.wait_held(2))
                began = time.monotonic()
                gate.close()
                self.assertLess(time.monotonic() - began, 2)
                self.assertEqual(held.recv(1), b"")
                gate.close()

    def test_one_shot_arm_and_metadata_do_not_contain_payload(self):
        with self.upstream() as listener, ConnectionGate("127.0.0.1", listener.getsockname()[1]) as gate:
            gate.arm()
            with self.assertRaises(RuntimeError):
                gate.arm()
            gate.release()
            with self.assertRaises(RuntimeError):
                gate.arm()
            self.assertEqual(gate.events, [])


@unittest.skipUnless(os.environ.get("RUN_PG_PROXY_INTEGRATION") == "1",
                     "set RUN_PG_PROXY_INTEGRATION=1 in the trusted PG image")
class StaleRouteScheduleTests(unittest.TestCase):
    def launch_server(self, runtime, source_dsn, package_parent):
        from experiments.online_cutover.test_cutover import free_port, request
        port = free_port()
        process = runtime.run_as_app(
            [sys.executable, "-m", "orderbridge", "serve", "--source", source_dsn,
             "--target", runtime.target_dsn, "--host", "127.0.0.1", "--port", str(port)],
            env={"PYTHONPATH": str(package_parent)})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self.assertIsNone(process.poll(), "Service exited; inspect private logs")
            try:
                if request(port, {"op": "health"}, timeout=.5).get("ok"):
                    return port, process
            except (OSError, HTTPError, URLError):
                pass
            time.sleep(.03)
        self.fail("Service startup exceeded development hang guard")

    def wait_process(self, process, timeout=30):
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Do not leak the application's DSN-bearing argv via the exception.
            return None

    def run_schedule(self, package_parent):
        from psycopg.conninfo import make_conninfo
        from experiments.online_cutover.model import Model
        from experiments.online_cutover.runtime import DatabaseRuntime
        from experiments.online_cutover.test_cutover import model_state, request, source_state, target_state
        record = {"status": "running", "coverage": "absent"}
        began = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="cutover-route-") as directory:
                Path(directory).chmod(0o755)
                with DatabaseRuntime(root=Path(directory) / "runtime") as runtime:
                    model = Model({"A": 20, "B": 15})
                    body = {"op": "create", "request_id": "delayed-create", "order_id": "delayed-order",
                            "customer": "Crossing activation", "lines": [
                                {"sku": "B", "quantity": 3, "unit_price_cents": 41},
                                {"sku": "A", "quantity": 2, "unit_price_cents": 113}]}
                    runtime.seed(model.capacities)
                    with ConnectionGate("127.0.0.1", runtime.port) as gate:
                        source_dsn = make_conninfo(runtime.source_dsn, host="127.0.0.1", port=gate.port,
                                                  sslmode="disable", gssencmode="disable")
                        port, _ = self.launch_server(runtime, source_dsn, package_parent)
                        observer, _ = self.launch_server(runtime, runtime.source_dsn, package_parent)
                        gate.arm()
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            pending = executor.submit(request, port, body, 40)
                            try:
                                # A finished request without a newly intercepted
                                # connection is valid; this fixture cannot cover it.
                                deadline = time.monotonic() + 2
                                while not gate.wait_held(.02) and not pending.done() and time.monotonic() < deadline:
                                    pass
                                if not gate.wait_held(0):
                                    record.update(status="coverage_absent", reason="no_new_source_connection")
                                    return record
                                if pending.done():
                                    record.update(status="coverage_absent", reason="request_completed_before_gate")
                                    return record
                                migrating = runtime.run_as_app(
                                    [sys.executable, "-m", "orderbridge", "migrate", "--source", runtime.source_dsn,
                                     "--target", runtime.target_dsn], env={"PYTHONPATH": str(package_parent)})
                                code = self.wait_process(migrating, timeout=3)
                                if code is None:
                                    # A correct strategy may hold a migration fence
                                    # before opening this connection. Release it;
                                    # missing this interleaving is not a task failure.
                                    gate.release()
                                    self.assertEqual(self.wait_process(migrating), 0, "Migration failed after gate release")
                                    record.update(status="coverage_absent", reason="activation_not_observed_while_held")
                                    return record
                                self.assertEqual(code, 0, "Migration failed; inspect private logs")
                                self.assertEqual(request(observer, {"op": "health"}), {"ok": True, "backend": "target"})
                                if pending.done():
                                    record.update(status="coverage_absent", reason="request_ended_before_activation")
                                    return record
                                record["coverage"] = "held_source_connection_across_activation"
                            finally:
                                gate.release()
                            response = pending.result(timeout=10)
                        record["first_response_ok"] = response.get("ok")
                        if response == {"ok": False, "error": "retry"}:
                            # An explicit no-mutation retry is a valid response.
                            with runtime.inspect_connect("target") as inspection:
                                self.assertEqual(target_state(inspection), model_state(model))
                            response = request(port, body)
                        self.assertEqual(response, model.apply(body))
                        # Never retry an acknowledged body before this SQL check:
                        # a retry might conceal a source-only acknowledged write.
                        with runtime.inspect_connect("target") as inspection:
                            actual_target = target_state(inspection)
                        expected = model_state(model)
                        record["target_matches_model"] = actual_target == expected
                        if actual_target != expected:
                            with runtime.inspect_connect("source") as inspection:
                                record["source_matches_model"] = source_state(inspection) == expected
                            record.update(status="acknowledged_write_missing_from_target", target_order_count=len(actual_target["orders"]))
                            return record
                        self.assertEqual(request(observer, {"op": "get", "order_id": "delayed-order"}), model.apply({"op": "get", "order_id": "delayed-order"}))
                        self.assertEqual(request(port, body), response)
                        runtime.retire_source()
                        fresh, _ = self.launch_server(runtime, runtime.source_dsn, package_parent)
                        self.assertEqual(request(fresh, body), response)
                        with runtime.inspect_connect("target") as inspection:
                            self.assertEqual(target_state(inspection), expected)
                        record.update(status="passed", source_retired=True, receipt_count=len(model.receipts))
                        return record
        finally:
            record["elapsed_seconds"] = round(time.monotonic() - began, 6)
            if "gate" in locals():
                record["gate_events"] = gate.events
            print("CUTOVER_ROUTE_CASE " + json.dumps(record, sort_keys=True), flush=True)

    def test_reference_rechecks_a_source_route_delayed_across_activation(self):
        result = self.run_schedule(ROOT)
        if result["status"] == "coverage_absent":
            self.skipTest("Stale-route schedule coverage absent: " + result["reason"])
        self.assertEqual(result["status"], "passed")

    def test_author_only_missing_recheck_mutant_is_discriminated(self):
        # This is the only reference-specific transformation. It lives outside
        # the opaque schedule and is never applied to a candidate submission.
        with tempfile.TemporaryDirectory(prefix="cutover-route-mutant-") as directory:
            parent = Path(directory)
            parent.chmod(0o755)
            shutil.copytree(ROOT / "orderbridge", parent / "orderbridge", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            backend = parent / "orderbridge" / "backend.py"
            source = backend.read_text()
            needle = "                    if not _active(self.target_dsn):\n"
            self.assertEqual(source.count(needle), 1, "Author mutant requires reevaluation after reference change")
            backend.write_text(source.replace(needle, "                    if True:  # Author-only missing routing recheck mutant.\n"))
            result = self.run_schedule(parent)
        self.assertEqual(result["coverage"], "held_source_connection_across_activation")
        self.assertEqual(result["status"], "acknowledged_write_missing_from_target")
        self.assertTrue(result["first_response_ok"])
        self.assertTrue(result["source_matches_model"])
        self.assertFalse(result["target_matches_model"])
        self.assertEqual(result["target_order_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
