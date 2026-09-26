"""Protocol peers plus opt-in real PostgreSQL commit-acknowledgement tests.

Set RUN_PG_PROXY_INTEGRATION=1 inside the trusted runtime image for real PG.
No submitted service or business oracle is imported.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import struct
import tempfile
import time
import unittest

try:
    from experiments.online_cutover.pg_fault_proxy import PostgresFaultProxy
except ModuleNotFoundError as error:
    if error.name != "experiments.online_cutover.pg_fault_proxy":
        raise
    PostgresFaultProxy = None


MAX_FRAME = 16 * 1024 * 1024
# A normal startup payload has no message-type byte.
STARTUP = struct.pack("!II", 20, 196608) + b"user\0probe\0\0"


def packet(kind, payload=b""):
    return kind + struct.pack("!I", 4 + len(payload)) + payload


def receive(connection, size):
    chunks = bytearray()
    while len(chunks) < size:
        part = connection.recv(size - len(chunks))
        if not part:
            raise AssertionError("connection closed before expected synthetic frame")
        chunks.extend(part)
    return bytes(chunks)


def is_closed(connection):
    try:
        return connection.recv(1) == b""
    except (ConnectionResetError, ConnectionAbortedError):
        return True


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PostgresFaultProxy, "PostgreSQL fault proxy is not implemented")

    @contextmanager
    def upstream(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(2)
            yield listener

    @contextmanager
    def pair(self, listener, proxy):
        with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
            # Bytewise sending exercises arbitrary stream fragmentation.
            for value in STARTUP:
                client.sendall(bytes([value]))
            server, _ = listener.accept()
            with server:
                server.settimeout(2)
                self.assertEqual(receive(server, len(STARTUP)), STARTUP)
                yield client, server

    def test_startup_authentication_and_all_noncommit_frames_are_transparent(self):
        with self.upstream() as listener, PostgresFaultProxy("127.0.0.1", listener.getsockname()[1]) as proxy:
            with self.pair(listener, proxy) as (client, server):
                backend = (packet(b"R", struct.pack("!I", 10) + b"SCRAM-SHA-256\0\0")
                    + packet(b"R", struct.pack("!I", 11) + b"synthetic-challenge")
                    + packet(b"R", struct.pack("!I", 12) + b"synthetic-proof")
                    + packet(b"R", struct.pack("!I", 0))
                    + packet(b"S", b"client_encoding\0UTF8\0")
                    + packet(b"K", struct.pack("!II", 123, 456))
                    + packet(b"D", b"COMMIT\0")
                    + packet(b"N", b"MCOMMIT\0\0")
                    + packet(b"C", b"ROLLBACK\0") + packet(b"Z", b"I"))
                server.sendall(backend)
                self.assertEqual(receive(client, len(backend)), backend)
                frontend = (packet(b"p", b"synthetic-auth") + packet(b"Q", b"SELECT 1\0")
                    + packet(b"P", b"synthetic-parse") + packet(b"B", b"synthetic-bind")
                    + packet(b"D", b"synthetic-describe") + packet(b"E", b"synthetic-execute")
                    + packet(b"H") + packet(b"S") + packet(b"d", b"synthetic-copy"))
                client.sendall(frontend)
                self.assertEqual(receive(server, len(frontend)), frontend)
                self.assertEqual(proxy.events, [])

    def test_only_selected_commit_ack_is_lost_and_reconnection_is_normal(self):
        with self.upstream() as listener, PostgresFaultProxy("127.0.0.1", listener.getsockname()[1], fail_commit=2) as proxy:
            with self.pair(listener, proxy) as (client, server):
                first = packet(b"C", b"COMMIT\0") + packet(b"Z", b"I")
                server.sendall(first)
                self.assertEqual(receive(client, len(first)), first)
                rollback = packet(b"C", b"ROLLBACK\0")
                server.sendall(rollback)
                self.assertEqual(receive(client, len(rollback)), rollback)
                # ACK and ReadyForQuery may share one TCP read: neither may leak.
                server.sendall(first)
                self.assertTrue(is_closed(client))
                self.assertTrue(is_closed(server))
            with self.pair(listener, proxy) as (client, server):
                server.sendall(first)
                self.assertEqual(receive(client, len(first)), first)
            commits = [event for event in proxy.events if event["event"] == "commit"]
            self.assertEqual([e["ordinal"] for e in commits], [1, 2, 3])
            self.assertEqual([e["ack_dropped"] for e in commits], [False, True, False])
            self.assertEqual(set(commits[0]), {"event", "connection", "ordinal", "ack_dropped"})
            copied = proxy.events
            copied[0]["ordinal"] = -1
            self.assertEqual(proxy.events[0]["ordinal"], 1)

    def test_commit_tag_requires_exact_message_type_and_nul_terminated_tag(self):
        with self.upstream() as listener, PostgresFaultProxy("127.0.0.1", listener.getsockname()[1], fail_commit=1) as proxy:
            with self.pair(listener, proxy) as (client, server):
                unchanged = packet(b"C", b"COMMIT PREPARED\0") + packet(b"C", b"COMMIT") + packet(b"D", b"COMMIT\0")
                server.sendall(unchanged)
                self.assertEqual(receive(client, len(unchanged)), unchanged)
                self.assertEqual(proxy.events, [])
                for byte in packet(b"C", b"COMMIT\0"):
                    server.sendall(bytes([byte]))
                self.assertTrue(is_closed(client))
                self.assertEqual(proxy.events[0]["ordinal"], 1)

    def test_startup_cancel_request_is_forwarded_without_authentication_or_commit(self):
        with self.upstream() as listener, PostgresFaultProxy("127.0.0.1", listener.getsockname()[1]) as proxy:
            with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
                cancel = struct.pack("!IIII", 16, 80877102, 123, 456)
                client.sendall(cancel)
                server, _ = listener.accept()
                with server:
                    server.settimeout(2)
                    self.assertEqual(receive(server, len(cancel)), cancel)
                self.assertTrue(is_closed(client))
                self.assertEqual(proxy.events, [])

    def test_ssl_and_gss_startups_are_explicitly_rejected(self):
        for code, reason in [(80877103, "ssl_not_supported"), (80877104, "gss_not_supported")]:
            with self.subTest(code=code), self.upstream() as listener, PostgresFaultProxy("127.0.0.1", listener.getsockname()[1]) as proxy:
                with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
                    client.sendall(struct.pack("!II", 8, code))
                    self.assertTrue(is_closed(client))
                self.assertEqual(proxy.events[0]["event"], "protocol_error")
                self.assertEqual(proxy.events[0]["reason"], reason)

    def test_invalid_startup_lengths_are_rejected_before_payload_allocation(self):
        for size in [0, 4, 7, MAX_FRAME + 1, 2**32 - 1]:
            with self.subTest(size=size), self.upstream() as listener, PostgresFaultProxy("127.0.0.1", listener.getsockname()[1]) as proxy:
                with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
                    client.sendall(struct.pack("!I", size))
                    self.assertTrue(is_closed(client))
                self.assertEqual(proxy.events[0]["reason"], "invalid_startup_length")

    def test_invalid_frontend_and_backend_lengths_close_only_that_pair(self):
        for direction in ["frontend", "backend"]:
            for size in [0, 3, MAX_FRAME + 1]:
                with self.subTest(direction=direction, size=size), self.upstream() as listener, PostgresFaultProxy("127.0.0.1", listener.getsockname()[1]) as proxy:
                    with self.pair(listener, proxy) as (client, server):
                        sender = client if direction == "frontend" else server
                        sender.sendall(b"Q" + struct.pack("!I", size))
                        self.assertTrue(is_closed(client))
                        self.assertTrue(is_closed(server))
                    error = proxy.events[0]
                    self.assertEqual(error["reason"], "invalid_frame_length")
                    self.assertEqual(error["direction"], direction)

    def test_close_is_bounded_with_idle_and_partial_frame_connections(self):
        with self.upstream() as listener:
            proxy = PostgresFaultProxy("127.0.0.1", listener.getsockname()[1])
            proxy.__enter__()
            self.addCleanup(proxy.close)
            with self.pair(listener, proxy) as (client, server):
                server.sendall(b"C\0\0")
                with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as unfinished:
                    unfinished.sendall(b"\0\0")
                    began = time.monotonic()
                    proxy.close()
                    self.assertLess(time.monotonic() - began, 2)
                    self.assertTrue(is_closed(client))
                    self.assertTrue(is_closed(server))
                    self.assertTrue(is_closed(unfinished))
                    proxy.close()  # Idempotent cleanup.

    def test_fault_ordinal_must_be_positive_integer_or_none(self):
        for invalid in [0, -1, True, 1.0, "1"]:
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                PostgresFaultProxy("127.0.0.1", 5432, fail_commit=invalid)


@unittest.skipUnless(os.environ.get("RUN_PG_PROXY_INTEGRATION") == "1", "set RUN_PG_PROXY_INTEGRATION=1 in the trusted PG image")
class RealPostgresTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PostgresFaultProxy, "PostgreSQL fault proxy is not implemented")
        import psycopg
        from experiments.online_cutover.runtime import DatabaseRuntime
        self.psycopg = psycopg
        directory = tempfile.TemporaryDirectory(prefix="klavis-proxy-test-")
        self.addCleanup(directory.cleanup)
        self.runtime = DatabaseRuntime(root=Path(directory.name))
        self.runtime.__enter__()
        self.addCleanup(self.runtime.close)
        with psycopg.connect(self.runtime.target_dsn, autocommit=True) as connection:
            connection.execute("CREATE TABLE app.proxy_probe (id integer PRIMARY KEY)")
            self.assertEqual(connection.execute("SHOW synchronous_commit").fetchone(), ("on",))

    def dsn(self, proxy):
        from psycopg.conninfo import make_conninfo
        return make_conninfo(self.runtime.target_dsn, host="127.0.0.1", port=proxy.port,
                             sslmode="disable", gssencmode="disable")

    def test_lost_commit_ack_is_a_client_error_but_insert_is_committed(self):
        with PostgresFaultProxy("127.0.0.1", self.runtime.port, fail_commit=1) as proxy:
            connection = self.psycopg.connect(self.dsn(proxy))
            try:
                connection.execute("INSERT INTO app.proxy_probe VALUES (%s)", (7,), prepare=True)
                with self.assertRaises(self.psycopg.OperationalError):
                    connection.commit()
            finally:
                connection.close()
            # Bypass the proxy and the application: inspect committed SQL state.
            with self.runtime.admin_connect("target") as check:
                self.assertEqual(check.execute("SELECT id FROM app.proxy_probe").fetchall(), [(7,)])
            with self.psycopg.connect(self.dsn(proxy)) as subsequent:
                subsequent.execute("INSERT INTO app.proxy_probe VALUES (%s)", (9,), prepare=True)
            with self.runtime.admin_connect("target") as check:
                self.assertEqual(check.execute("SELECT id FROM app.proxy_probe ORDER BY id").fetchall(), [(7,), (9,)])
            self.assertEqual([(e["ordinal"], e["ack_dropped"]) for e in proxy.events if e["event"] == "commit"], [(1, True), (2, False)])

    def test_extended_commit_counts_but_simple_and_extended_rollbacks_do_not(self):
        with PostgresFaultProxy("127.0.0.1", self.runtime.port) as proxy:
            with self.psycopg.connect(self.dsn(proxy), autocommit=True) as connection:
                self.assertEqual(connection.execute("SELECT %s::text", ("COMMIT",), prepare=True).fetchone(), ("COMMIT",))
                connection.execute("BEGIN; INSERT INTO app.proxy_probe VALUES (1); ROLLBACK", prepare=False)
                connection.execute("BEGIN", prepare=True)
                connection.execute("INSERT INTO app.proxy_probe VALUES (%s)", (2,), prepare=True)
                connection.execute("ROLLBACK", prepare=True)
                self.assertEqual(proxy.events, [])
                connection.execute("BEGIN", prepare=True)
                connection.execute("INSERT INTO app.proxy_probe VALUES (%s)", (3,), prepare=True)
                connection.execute("COMMIT", prepare=True)
                self.assertEqual(connection.execute("SELECT id FROM app.proxy_probe").fetchall(), [(3,)])
            self.assertEqual([(e["ordinal"], e["ack_dropped"]) for e in proxy.events], [(1, False)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
