"""Trusted Linux/container tests for fresh database and process boundaries."""
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

import psycopg

from experiments.online_cutover.runtime import DatabaseRuntime


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="klavis-runtime-test-")
        self.runtime = DatabaseRuntime(root=Path(self.directory.name))
        self.runtime.__enter__()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.runtime.close)

    def test_public_schema_seed_inventory_and_historical_receipt(self):
        order = {"order_id": "A", "customer": "old", "revision": 3,
                 "lines": [{"sku": "s", "quantity": 4, "unit_price_cents": 25}], "total_cents": 100}
        receipt = {"request_id": "r", "body": {"op": "delete"},
                   "response": {"ok": False, "error": "missing"}}
        self.runtime.seed({"s": 10, "t": 5}, orders=[order], receipts=[receipt])
        with self.runtime.admin_connect("source") as c:
            self.assertEqual(c.execute("SELECT sku,capacity,available FROM app.inventory ORDER BY sku").fetchall(), [("s", 10, 6), ("t", 5, 5)])
            self.assertEqual(c.execute("SELECT order_id,customer,revision,lines FROM app.orders").fetchone(), ("A", "old", 3, order["lines"]))
            self.assertEqual(c.execute("SELECT request_id,body,response FROM app.receipts").fetchone(), ("r", receipt["body"], receipt["response"]))
        with self.runtime.admin_connect("target") as c:
            self.assertEqual(c.execute("SELECT sku,capacity,available FROM app.inventory ORDER BY sku").fetchall(), [("s", 10, 10), ("t", 5, 5)])
            for table in ["orders", "order_lines", "receipts"]:
                self.assertEqual(c.execute(f"SELECT count(*) FROM app.{table}").fetchone(), (0,))
            self.assertEqual([r[0] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='app' AND table_name='order_lines' ORDER BY ordinal_position")], ["order_id", "position", "sku", "quantity", "unit_price_cents"])

    def test_app_owns_business_schema_can_add_ddl_and_trigger(self):
        with psycopg.connect(self.runtime.source_dsn, autocommit=True) as c:
            c.execute("CREATE TABLE app.audit(marker text)")
            c.execute("CREATE FUNCTION app.audit_order() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN INSERT INTO app.audit VALUES (NEW.order_id); RETURN NEW; END $$")
            c.execute("CREATE TRIGGER audit_order AFTER INSERT ON app.orders FOR EACH ROW EXECUTE FUNCTION app.audit_order()")
            c.execute("ALTER TABLE app.orders ADD COLUMN extra text")
            c.execute("INSERT INTO app.orders(order_id,customer,revision,lines) VALUES ('a','b',1,'[]')")
            self.assertEqual(c.execute("SELECT marker FROM app.audit").fetchall(), [("a",)])
            self.assertEqual(c.execute("SELECT pg_get_userbyid(datdba) = current_user FROM pg_database WHERE datname=current_database()").fetchone(), (False,))
            self.assertEqual(c.execute("SELECT nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) FROM pg_namespace WHERE nspname='app'").fetchone(), (True,))

    def test_app_cannot_administer_database_or_server(self):
        with psycopg.connect(self.runtime.target_dsn, autocommit=True) as c:
            for query in ["ALTER DATABASE source_db ALLOW_CONNECTIONS false", "CREATE DATABASE denied", "CREATE ROLE denied", "SELECT pg_read_file('/etc/passwd')", "COPY (SELECT 1) TO PROGRAM 'true'", "CREATE TABLE public.denied(x int)"]:
                with self.subTest(query=query), self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    c.execute(query)

    def test_app_can_use_transactional_temporary_scratch_tables(self):
        for dsn in [self.runtime.source_dsn, self.runtime.target_dsn]:
            with self.subTest(database=dsn.split("dbname=")[1].split()[0]):
                with psycopg.connect(dsn) as connection:
                    connection.execute("CREATE TEMP TABLE scratch(value integer) ON COMMIT DROP")
                    connection.execute("INSERT INTO scratch VALUES (7),(11)")
                    self.assertEqual(connection.execute("SELECT sum(value) FROM scratch").fetchone(), (18,))
                    connection.commit()
                    self.assertEqual(connection.execute("SELECT to_regclass('pg_temp.scratch')").fetchone(), (None,))

    def test_artifact_view_inspection_cannot_execute_as_postgres(self):
        with psycopg.connect(self.runtime.source_dsn, autocommit=True) as app:
            app.execute("DROP TABLE app.orders")
            app.execute("CREATE FUNCTION app.caller_identity() RETURNS text LANGUAGE sql SECURITY INVOKER AS 'SELECT current_user::text'")
            app.execute("CREATE VIEW app.orders AS SELECT app.caller_identity() AS order_id")
        with self.runtime.inspect_connect("source") as inspector:
            self.assertEqual(inspector.execute("SELECT order_id FROM app.orders").fetchone(), ("orderbridge_app",))
            self.assertEqual(inspector.execute("SHOW default_transaction_read_only").fetchone(), ("on",))
        with self.runtime.inspect_connect("source", autocommit=False) as inspector:
            self.assertEqual(inspector.execute("SHOW transaction_read_only").fetchone(), ("on",))
        with psycopg.connect(self.runtime.source_dsn, autocommit=True) as app:
            app.execute("CREATE OR REPLACE FUNCTION app.caller_identity() RETURNS text LANGUAGE sql SECURITY INVOKER AS $$ SELECT pg_read_file('/etc/passwd') $$")
        with self.runtime.inspect_connect("source") as inspector:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                inspector.execute("SELECT order_id FROM app.orders")
        with self.assertRaises(ValueError):
            self.runtime.inspect_connect("postgres")

    def test_source_retirement_terminates_connections_and_target_survives(self):
        source = psycopg.connect(self.runtime.source_dsn, autocommit=True)
        self.addCleanup(source.close)
        with psycopg.connect(self.runtime.target_dsn, autocommit=True) as target:
            self.runtime.retire_source()
            self.runtime.retire_source()
            with self.assertRaises(psycopg.OperationalError):
                source.execute("SELECT 1")
            with self.assertRaises(psycopg.OperationalError):
                psycopg.connect(self.runtime.source_dsn, connect_timeout=2)
            self.assertEqual(target.execute("SELECT 1").fetchone(), (1,))
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                target.execute("ALTER DATABASE source_db ALLOW_CONNECTIONS true")

    def test_inspection_times_out_an_application_owned_sleeping_view(self):
        with psycopg.connect(self.runtime.target_dsn, autocommit=True) as app:
            app.execute("CREATE FUNCTION app.slow_order() RETURNS text LANGUAGE plpgsql SECURITY INVOKER AS $$ BEGIN PERFORM pg_sleep(6); RETURN 'slow'; END $$")
            app.execute("CREATE VIEW app.slow_orders AS SELECT app.slow_order() AS order_id")
        with self.runtime.inspect_connect("target") as inspector:
            self.assertEqual(inspector.execute("SHOW statement_timeout").fetchone(), ("5s",))
            self.assertEqual(inspector.execute("SHOW lock_timeout").fetchone(), ("5s",))
            started = time.monotonic()
            with self.assertRaises(psycopg.errors.QueryCanceled):
                inspector.execute("SELECT order_id FROM app.slow_orders")
            self.assertLess(time.monotonic() - started, 6)

    def test_worker_identity_private_files_and_peer_auth(self):
        secret = self.runtime.tests_dir / "expected.json"
        secret.write_text("trusted-only")
        code = """import json,os,sys,psycopg
denied=[]
for path in sys.argv[1:]:
 try: open(path).read()
 except PermissionError: denied.append(path)
 else: raise AssertionError('private path readable')
try: psycopg.connect(host=os.environ['ADMIN_SOCKET'],port=os.environ['ADMIN_PORT'],user='postgres',dbname='postgres')
except psycopg.OperationalError: pass
else: raise AssertionError('admin peer impersonation allowed')
print(json.dumps({'uid':os.getuid(),'cwd_files':os.listdir('.'),'denied':denied,'inherited_sentinel':os.environ.get('PRIVATE_TEST_SENTINEL')}))
"""
        os.environ["PRIVATE_TEST_SENTINEL"] = "must-not-inherit"
        self.addCleanup(os.environ.pop, "PRIVATE_TEST_SENTINEL", None)
        process = self.runtime.run_as_app([sys.executable, "-c", code, str(secret), str(self.runtime.logs_dir)], env={"ADMIN_SOCKET": str(self.runtime.socket_dir), "ADMIN_PORT": str(self.runtime.port)})
        self.assertEqual(process.wait(timeout=10), 0, process.stderr_path.read_text())
        data = json.loads(process.stdout_path.read_text())
        self.assertEqual(data["uid"], 65534)
        self.assertEqual(data["cwd_files"], [])
        self.assertIsNone(data["inherited_sentinel"])
        self.assertEqual(stat.S_IMODE(self.runtime.tests_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.runtime.logs_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(process.stdout_path.stat().st_mode), 0o600)
        self.assertEqual(process.stdout_path.stat().st_uid, 0)

    def test_large_output_is_file_backed_and_fresh_cwd_on_restart(self):
        first = self.runtime.run_as_app([sys.executable, "-c", "open('local-marker','w').write('x'); print('x'*200000)"])
        self.assertEqual(first.wait(timeout=10), 0)
        self.assertGreater(first.stdout_path.stat().st_size, 200000)
        second = self.runtime.run_as_app([sys.executable, "-c", "import os; assert not os.path.exists('local-marker')"])
        self.assertEqual(second.wait(timeout=10), 0)

    def test_group_cleanup_reaps_descendant_after_parent_exit(self):
        child = self.runtime.run_as_app([sys.executable, "-c", "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(300)']); print(p.pid,flush=True)"])
        self.assertEqual(child.wait(timeout=10), 0)
        descendant = int(child.stdout_path.read_text())
        child.terminate()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status = Path(f"/proc/{descendant}/stat")
            if not status.exists() or status.read_text().split()[2] == "Z":
                break
            time.sleep(0.01)
        else:
            self.fail("descendant remained running after process-group cleanup")

    def test_timeout_terminates_worker(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.runtime.run_as_app([sys.executable, "-c", "import time; time.sleep(300)"], timeout=0.05)

    def test_fresh_cluster_has_different_identity_and_no_old_data(self):
        self.runtime.seed({"a": 1})
        with self.runtime.admin_connect("postgres") as c:
            old = c.execute("SELECT system_identifier FROM pg_control_system()").fetchone()
        with tempfile.TemporaryDirectory(prefix="klavis-runtime-second-") as other:
            with DatabaseRuntime(root=Path(other)) as second:
                with second.admin_connect("postgres") as c:
                    self.assertNotEqual(old, c.execute("SELECT system_identifier FROM pg_control_system()").fetchone())
                with second.admin_connect("source") as c:
                    self.assertEqual(c.execute("SELECT count(*) FROM app.inventory").fetchone(), (0,))


if __name__ == "__main__":
    unittest.main()
