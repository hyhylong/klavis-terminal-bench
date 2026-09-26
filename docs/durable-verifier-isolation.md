# Durable Store verifier isolation prototype

Status: a runnable Linux isolation experiment, not a production security claim or a qualified benchmark verifier. No Docker or model run is part of this check.

The trusted controller keeps the simulator, expected answers, fault schedule, and any eventual reward calculation in its own process. It never imports `ledgerstore`. It copies a frozen submitted package as data, starts the trusted bootstrap, and returns the worker's JSON values for an independent oracle comparison. A returned value or exception cannot itself award reward.

## Run the checks

On Linux x86-64 as root, with Python 3.10+ and `libseccomp.so.2`:

```sh
python3 -B experiments/durable_ledger/controller.py -v
```

From this Windows workspace, use a stable Linux working directory and absolute paths:

```powershell
wsl -d Ubuntu-22.04 --cd /root -- python3 -B /mnt/e/JOB/klavis-terminal-bench/experiments/durable_ledger/controller.py -v
```

The tested WSL kernel is `6.6.87.2-microsoft-standard-WSL2`, with Landlock ABI 3. The initial six tests failed before `WorkerSession` existed. After implementation and independent review, thirteen tests passed under both Ubuntu Python 3.10 and the pinned managed Python 3.12. Regression tests first exposed host fault-hook errors being incorrectly returned to the Store, both in the controller hook and the simulator hook; they now terminate the worker. A separate integration check loaded the current replay baseline and passed empty snapshot, compaction, close, crash, and reopen under the restrictions. The real RPC calibration also completed under the managed runtime with matching replay/incremental output hashes.

The checks exercise binary round trips and all eight filesystem operations; public Store calls and typed exceptions; reading a protected but world-readable answer; writing a world-writable reward; writing the submitted package; accessing the parent's process memory; creating a network socket; forking and leaving the process group; inherited environment secrets; isolation during module import; symlink rejection; malformed frame sizes; attempted host-only filesystem helpers; write quotas; bounded output and wall time; and a new worker recovering a real simulator image after a cut before the final filesystem reply. The reward fixture remains `0`.

## Controller interface

The submitted directory contains either `ledgerstore.py` or `ledgerstore/__init__.py`, exporting `Store(fs)`. Pass the directory **containing** `ledgerstore`, not the package directory itself. It must be frozen before constructing the session. Relative package imports work. Python standard-library modules and modules bundled in the submitted package are supported; site initialization and implicit external installed dependencies are disabled. Imports do not grant additional operating-system access: threads, subprocesses, network access, and persistent host-file writes are outside this single-process interface.

```python
from experiments.durable_ledger.controller import WorkerSession, InjectedCrash
from experiments.durable_ledger.durablefs import MemoryDurableFS

def cut(operation, successful_operation_count):
    if successful_operation_count == chosen_cut:
        raise InjectedCrash("scheduled power cut")

fs = MemoryDurableFS(after_operation=cut)
try:
    with WorkerSession(frozen_package, fs, timeout_sec=30) as worker:
        worker.call("ingest", event)
        actual = worker.call("snapshot", cutoff)
        # Compare actual with an independently computed expected value here.
except InjectedCrash:
    # WorkerSession has already killed and reaped the worker process group.
    fs.crash()
```

Construct another `WorkerSession` over the recovered simulator to restart. Public calls are `ingest(event)`, `snapshot(cutoff)`, `lookup(entity, valid_time)`, `compact()`, and `close()`. Explicit `call("close")` invokes submitted cleanup. Context exit and `abort()` kill without invoking it, so cleanup cannot make a simulated crash more durable. `fs.crash()` is deliberately a separate trusted action after termination.

Use `InjectedCrash` from a simulator's `after_operation` hook. The simulator counts successful filesystem operations; hook exceptions occur after an operation completes but before its reply. The controller checks this count to distinguish even a hook's ordinary `ValueError`/`OSError` from a public filesystem error; a completed-operation failure kills the worker. Alternatively, the controller's optional `after_fs(operation, rpc_request_count)` runs after successful dispatch; its count includes earlier failed RPC attempts. Do not install both fault schedules unintentionally. A custom simulator with internal hooks must expose the same monotonic `operation_count` or wrap host faults in a dedicated exception such as `InjectedCrash`.

`RemoteStoreError` preserves the submitted exception type in `remote_type`; it is still untrusted evidence. Protocol violations, premature exit, and resource failures are harness failures. The caller must distinguish these outcomes from a wrong semantic answer, and must not treat an infrastructure failure as proof of task difficulty.

## Boundary and bounds

* The bootstrap uses isolated Python without site initialization. Before importing submitted code it installs Landlock, drops supplementary groups and root identity to UID/GID 65534, disables core dumps and privilege gain, and installs a seccomp syscall allowlist. Unsupported isolation features fail closed.
* Landlock permits file contents only under the copied package and Python/shared-library runtime directories. These paths are read-only. The worker inherits only stdin pointing at `/dev/null`, bounded stdout/stderr temporary files, and its connected Unix socket. The trusted bootstrap opens one additional read-only standard-library directory handle, used through `/proc/self/fd` so runtimes beneath a private `/root` prefix remain traversable without exposing their ancestors. No test, expected-answer, simulator, or reward descriptor is passed.
* Seccomp permits the operations needed by this single-process Python interface, including I/O on existing descriptors. It denies process creation, exec, session changes, new sockets/connections, mount, ptrace, and signalling other processes. Parent death sends `SIGKILL`; controller failures kill and reap the process group.
* The Unix socket uses a four-byte unsigned big-endian length followed by UTF-8 JSON. The parent rejects unknown message shapes, duplicate keys, nonfinite JSON, unexpected sequence numbers, and frames larger than the bound. Only the eight public filesystem methods can be dispatched. Binary file content uses validated base64. Plain namespace names exclude path separators and `.`/`..`.
* Defaults are 1 MiB per frame, 256 KiB per output stream, 256 MiB worker address space, 120 CPU seconds per worker, five seconds per request, 100,000 filesystem requests, and 64 MiB total submitted filesystem writes. These are prototype safety bounds, not calibrated task difficulty limits. Adjust and disclose them before grading. Package snapshots are limited to 32 MiB, 1,024 entries, and 16 directory levels; symlinks and special files are rejected.

## Remaining limits

Landlock limits file contents, not all metadata observations: it does not make arbitrary path names or `stat` information invisible. This is not a VM or kernel exploit boundary. Runtime library directories are trusted and must never contain verifier secrets. The original submitted package must be immutable during snapshot copying; concurrent hostile writers are outside this prototype's copy contract. The controller must use a trusted Python installation and trusted simulator and oracle modules.

The smoke checks do not prove resistance to every Linux attack, or test every valid submitted implementation and dependency. A final verifier still needs an isolated container or equivalent deployment boundary, independent review, the full semantic/crash suite, representative correct implementations, and calibrated resource limits. No task qualification, rubric pass, or model-failure claim follows from these isolation results.
