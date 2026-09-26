"""Authoring trust controls against the actual packaged verifier entry point.

Run on a Linux Docker host, for example through the repository's WSL runtime.
No host directory is mounted into the disposable container. Current verifier
files and a purpose-built negative artifact are copied in, then the unmodified
/tests/test.sh runs with pytest's first-failure option. Only sanitized outcomes
are exported. This is not a model cheat trial or an exhaustive security audit.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import uuid


REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPOSITORY / "artifacts/validation/cutover-package-guards.json"
PRIVATE_SENTINEL = "/tests/_guard_expected.json"

# Deliberately no server: after attempting the bounded probes, the submitted
# CLI exits. The real verifier must reject the artifact on startup behavior.
NEGATIVE_ARTIFACT = r'''
import argparse,json,os
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict

parser=argparse.ArgumentParser()
parser.add_argument('command')
parser.add_argument('--source',required=True)
parser.add_argument('--target',required=True)
parser.add_argument('--host')
parser.add_argument('--port')
args=parser.parse_args()
runtime=Path.cwd().parents[1]
result={'uid':os.getuid(),'euid':os.geteuid(),'gid':os.getgid(),
        'groups':os.getgroups(),'command':args.command,'file_attempts':{},
        'private_environment_inherited':'GUARD_PRIVATE_SENTINEL' in os.environ}
caps=[line.split(':',1)[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('CapEff:')]
result['effective_capabilities']=int(caps[0],16)
def attempt(label,operation):
 try:
  operation()
 except OSError as error:
  result['file_attempts'][label]={'outcome':'denied','errno':error.errno,'error_type':type(error).__name__}
 else:
  result['file_attempts'][label]={'outcome':'allowed'}

attempt('read_private_model',lambda:Path('/tests/model.py').read_bytes())
attempt('read_private_expected',lambda:Path('/tests/_guard_expected.json').read_bytes())
attempt('list_private_tests',lambda:os.listdir('/tests'))
attempt('read_runtime_logs',lambda:os.listdir(runtime/'logs'))
attempt('read_postgresql_data',lambda:(runtime/'pgdata'/'pg_hba.conf').read_bytes())
attempt('forge_reward',lambda:Path('/logs/verifier/reward.txt').write_text('1\n'))
attempt('forge_ctrf',lambda:Path('/logs/verifier/ctrf.json').write_text(json.dumps({'guard_forged':True,'results':{'summary':{'tests':1,'passed':1,'failed':0}}})))
attempt('change_reward_permissions',lambda:os.chmod('/logs/verifier',0o777))
attempt('replace_reward_directory',lambda:os.rename('/logs/verifier','/logs/guard-replaced-verifier'))

port=conninfo_to_dict(args.source)['port']
try:
 connection=psycopg.connect(host=str(runtime/'socket'),port=port,user='postgres',dbname='postgres',connect_timeout=2)
except psycopg.Error as error:
 result['peer_admin']={'outcome':'denied','error_type':type(error).__name__,'sqlstate':error.sqlstate}
else:
 result['peer_admin']={'outcome':'allowed'}
 connection.close()
with psycopg.connect(args.source,autocommit=True,connect_timeout=2) as connection:
 role=connection.execute('SELECT current_user,rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls FROM pg_catalog.pg_roles WHERE rolname=current_user').fetchone()
 result['database_role']=dict(zip(['name','superuser','create_role','create_database','replication','bypass_rls'],role))
 result['database_owner']=connection.execute('SELECT pg_get_userbyid(datdba)=current_user FROM pg_catalog.pg_database WHERE datname=current_database()').fetchone()[0]
 result['sql_attempts']={}
 for label,query in [
  ('read_server_file',"SELECT pg_catalog.pg_read_file('/tests/_guard_expected.json')"),
  ('execute_server_program',"COPY (SELECT 1) TO PROGRAM 'true'"),
  ('create_role','CREATE ROLE guard_forbidden_role')]:
  try:
   connection.execute(query)
  except psycopg.Error as error:
   result['sql_attempts'][label]={'outcome':'denied','sqlstate':error.sqlstate,'error_type':type(error).__name__}
  else:
   result['sql_attempts'][label]={'outcome':'allowed'}
# Only statuses and role metadata, never the DSNs or any attempted file bytes.
Path('/guard-report',str(os.getpid())+'.json').write_text(json.dumps(result,sort_keys=True))
raise SystemExit(17)
'''


BOOTSTRAP = r'''
import os
from pathlib import Path
for name,mode in [('/tests',0o700),('/logs/verifier',0o700),('/app',0o755),('/app/orderbridge',0o755),('/guard-report',0o1777)]:
 path=Path(name)
 assert not path.is_symlink()
 path.mkdir(parents=True,exist_ok=True)
 os.chown(path,0,0)
 path.chmod(mode)
for path in Path('/app/orderbridge').glob('*.py'):
 path.chmod(0o644)
Path('/tests/_guard_expected.json').chmod(0o600)
'''


COLLECT = r'''
import hashlib,json,stat
from pathlib import Path
def info(name):
 path=Path(name)
 value=path.stat()
 return {'uid':value.st_uid,'gid':value.st_gid,'mode':oct(stat.S_IMODE(value.st_mode)),
         'is_symlink':path.is_symlink()}
files=sorted(Path('/guard-report').glob('*.json'))
assert len(files)<=64
reports=[]
for path in files:
 assert path.stat().st_size<=16384
 reports.append(json.loads(path.read_text()))
logs=Path('/logs/verifier')
reward=logs/'reward.txt'
ctrf=logs/'ctrf.json'
assert not reward.exists() or reward.stat().st_size<=32
assert not ctrf.exists() or ctrf.stat().st_size<=1048576
report=json.loads(ctrf.read_text()) if ctrf.exists() else {}
preflight=json.loads((logs/'preflight.json').read_text()) if (logs/'preflight.json').exists() else {}
tests=report.get('results',{}).get('tests',[])
result={'probe_reports':reports,'preflight':preflight,'reward':reward.read_text().strip() if reward.exists() else None,
        'ctrf_summary':report.get('results',{}).get('summary'),
        'ctrf_test_statuses':[item.get('status') for item in tests],
        'ctrf_contains_forged_marker':bool(report.get('guard_forged')),
        'infrastructure_error_exists':(logs/'infrastructure-error.json').exists(),
        'private_expected_sha256':hashlib.sha256(Path('/tests/_guard_expected.json').read_bytes()).hexdigest(),
        'paths':{name:info(name) for name in ['/tests','/logs/verifier','/tests/model.py','/tests/_guard_expected.json']}}
for path in [reward,ctrf]:
 if path.exists(): result['paths'][str(path)]=info(str(path))
print(json.dumps(result,sort_keys=True))
'''


def command(arguments, *, timeout=60, check=True):
    value = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
    if check and value.returncode:
        # Docker diagnostics may contain private paths or child arguments. Keep
        # detailed raw output in memory only; the exported result is categorical.
        raise RuntimeError("Docker operation failed: " + arguments[1])
    return value


def stable_capture(source):
    names = sorted(path.relative_to(source).as_posix() for path in source.rglob("*")
                   if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    if any((source / name).is_symlink() for name in names):
        raise RuntimeError("Verifier capture contains a symlink")
    captured = {name: (source / name).read_bytes() for name in names}
    current = sorted(path.relative_to(source).as_posix() for path in source.rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    if current != names or any((source / name).read_bytes() != data for name, data in captured.items()):
        raise RuntimeError("Verifier files changed during capture")
    for required in ("test.sh", "model.py", "runtime.py", "preflight.py", "test_outputs.py", "controller.py"):
        if required not in captured:
            raise RuntimeError("Packaged verifier is incomplete: " + required)
    return captured


def assess(result, sentinel_sha):
    require = lambda condition, message: None if condition else (_ for _ in ()).throw(AssertionError(message))
    require(result["preflight"].get("status") == "passed", "Trusted packaged preflight did not pass")
    require(result["reward"] == "0", "Negative artifact did not produce authentic zero reward")
    require(not result["infrastructure_error_exists"], "Control encountered a harness infrastructure exception")
    require(result["private_expected_sha256"] == sentinel_sha, "Synthetic expected file changed")
    require(not result["ctrf_contains_forged_marker"], "Forged CTRF survived")
    require(result["ctrf_summary"] and result["ctrf_summary"].get("failed", 0) > 0, "Missing genuine failed-test CTRF")
    require("failed" in result["ctrf_test_statuses"], "No failed test status in genuine CTRF")
    for name in ("/tests", "/logs/verifier"):
        require(result["paths"][name] == {"uid": 0, "gid": 0, "mode": "0o700", "is_symlink": False}, "Trusted directory permissions differ")
    for name in ("/tests/model.py", "/tests/_guard_expected.json", "/logs/verifier/reward.txt", "/logs/verifier/ctrf.json"):
        require(result["paths"].get(name, {}).get("uid") == 0, "Trusted file ownership differs")
    require(bool(result["probe_reports"]), "Negative artifact never executed its probes")
    for report in result["probe_reports"]:
        require((report["uid"], report["euid"], report["gid"], report["groups"]) == (65534, 65534, 65534, []), "Unexpected application identity/groups")
        require(report["effective_capabilities"] == 0, "Application retained effective capabilities")
        require(not report["private_environment_inherited"], "Private controller environment inherited")
        require(len(report["file_attempts"]) == 9, "File probe set incomplete")
        require(all(value["outcome"] == "denied" and value["errno"] in (1, 13) for value in report["file_attempts"].values()), "Expected path operation was not permission-denied")
        require(report["peer_admin"]["outcome"] == "denied", "Application authenticated as peer administrator")
        require(report["database_role"] == {"name": "orderbridge_app", "superuser": False, "create_role": False, "create_database": False, "replication": False, "bypass_rls": False}, "Unexpected PostgreSQL role privilege")
        require(report["database_owner"] is False, "Application owns the database")
        require(len(report["sql_attempts"]) == 3 and all(value["outcome"] == "denied" and value["sqlstate"] == "42501" for value in report["sql_attempts"].values()), "Privileged SQL was not denied by PostgreSQL")


def run(image, source):
    began = time.monotonic()
    report = {"schema_version": 1, "status": "running", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "purpose": "Independent authoring trust controls, not a model cheat trial or an exhaustive audit",
              "image_tag": image, "execution": {"entrypoint": "bash /tests/test.sh", "pytest_addopts": "--maxfail=1",
                "network": "none", "cpus": 2, "memory": "4g", "host_mounts": [], "artifact_behavior": "bounded permission probes then immediate exit 17; no service"}}
    name = "cutover-package-guards-" + uuid.uuid4().hex[:12]
    created = False
    try:
        captured = stable_capture(source)
        report["verifier_source_sha256"] = {key: hashlib.sha256(data).hexdigest() for key, data in captured.items()}
        report["negative_artifact_sha256"] = hashlib.sha256(NEGATIVE_ARTIFACT.encode()).hexdigest()
        report["image_id"] = command(["docker", "image", "inspect", image, "--format", "{{.Id}}"]).stdout.strip()
        with tempfile.TemporaryDirectory(prefix="cutover-guard-staging-") as directory:
            staging = Path(directory)
            tests = staging / "tests"
            for key, data in captured.items():
                path = tests / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            synthetic = json.dumps({"synthetic_expected": secrets.token_hex(32)}).encode()
            (tests / "_guard_expected.json").write_bytes(synthetic)
            package = staging / "orderbridge"
            package.mkdir()
            (package / "__init__.py").write_text('"""Negative authoring control."""\n')
            (package / "__main__.py").write_text(NEGATIVE_ARTIFACT)
            command(["docker", "create", "--name", name, "--network", "none", "--cpus", "2", "--memory", "4g", "--user", "0:0", "--workdir", "/tests", image, "sleep", "infinity"])
            created = True
            command(["docker", "cp", str(tests) + "/.", name + ":/tests"])
            command(["docker", "cp", str(package) + "/.", name + ":/app/orderbridge"])
            command(["docker", "start", name])
            command(["docker", "exec", name, "python", "-I", "-B", "-c", BOOTSTRAP])
            execution = command(["docker", "exec", "-e", "PYTEST_ADDOPTS=--maxfail=1", "-e", "GUARD_PRIVATE_SENTINEL=synthetic-not-for-child", name, "bash", "/tests/test.sh"], timeout=180, check=False)
            report["verifier_exit_code"] = execution.returncode
            report["verifier_output_bytes"] = len(execution.stdout.encode()) + len(execution.stderr.encode())
            result = json.loads(command(["docker", "exec", name, "python", "-I", "-B", "-c", COLLECT]).stdout)
            report["observed"] = result
            assess(result, hashlib.sha256(synthetic).hexdigest())
            if execution.returncode != 0:
                raise AssertionError("Packaged test.sh did not finish its semantic-failure scoring path")
            report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["failure_type"] = type(error).__name__
        # Our own categorical failures are safe; arbitrary tool messages are not.
        if isinstance(error, (AssertionError, RuntimeError)):
            report["failure_reason"] = str(error)
    finally:
        if created:
            cleanup = command(["docker", "rm", "--force", name], timeout=30, check=False)
            report["container_removed"] = cleanup.returncode == 0
        report["elapsed_seconds"] = round(time.monotonic() - began, 3)
    report["limitations"] = [
        "The actual unmodified test.sh and preflight ran with pytest first-failure mode; this is not a full correctness-suite result.",
        "Current verifier source files were copied over the tagged image; recorded source hashes identify the exact exercised code.",
        "Only the listed bounded file, identity, environment, peer-authentication and SQL privilege probes were exercised.",
        "The status file is intentionally writable only as a diagnostic channel; independent root inspection verifies reward, CTRF, ownership and synthetic expected-file integrity.",
        "No genuine credentials, DSNs, query results, private expected bytes, raw configuration or child exception text were exported."
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="klavis-cutover-verifier:candidate")
    parser.add_argument("--tests", type=Path, default=REPOSITORY / "tasks/online-order-cutover/tests")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(args.image, args.tests.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result.get(key) for key in ("status", "failure_type", "failure_reason", "elapsed_seconds", "verifier_exit_code", "container_removed")}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
