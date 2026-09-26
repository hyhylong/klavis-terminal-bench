# Local Harbor runtime

This project uses WSL2 Ubuntu-22.04 and Docker Desktop's Linux daemon. The setup is isolated from the system Python and other projects. It installs no host agent CLI and makes no model calls.

## Install or repair

From PowerShell in this checkout:

```powershell
wsl.exe -d Ubuntu-22.04 -- bash /mnt/e/JOB/klavis-terminal-bench/scripts/setup-local.sh
```

On another Linux x86_64 machine, run `bash scripts/setup-local.sh` from its checkout. Prerequisites are `python3`, Docker with Compose, and network access to PyPI, GitHub release assets, and Docker Hub. No `sudo`, system package installation, or shell profile changes are required.

The script pins:

| Component | Version |
| --- | --- |
| uv | 0.9.28 |
| Python | 3.12.12 |
| Harbor | 0.23.1.dev202609170426 |
| Docker smoke image | alpine:3.21.3, pinned by manifest SHA256 in the setup script |

The Harbor version is taken from [the pinned Terminal-Bench commit](https://github.com/harbor-framework/terminal-bench/blob/4def1f367467b34b18e0dbdc086400ba71c3e037/.github/harbor-version). The uv wheel comes from official PyPI and is checked against the SHA256 published in PyPI metadata. uv retrieves its managed CPython distribution from Astral's `python-build-standalone` releases.

By default, runtime files go to `$HOME/.local/share/klavis-terminal-bench/runtime` within Linux. On this machine the WSL user is `root`, making the actual directory `/root/.local/share/klavis-terminal-bench/runtime`. This avoids slow package access on `/mnt/e`. To choose another location, set `KTB_RUNTIME_ROOT` before running the script.

## Use

Open WSL, then load the generated environment:

```bash
cd /mnt/e/JOB/klavis-terminal-bench
source artifacts/environment/runtime-env.sh
harbor --version
```

The environment file adds the isolated virtual environment and uv binaries to `PATH`, and sets `HARBOR_PYTHON` to the virtual environment's interpreter. It does not contain credentials. Subsequent WSL shells must source it again.

The absolute executable is `/root/.local/share/klavis-terminal-bench/runtime/venv/bin/harbor`. The system Python remains unchanged.

## Evidence and scope

Setup writes local evidence under `artifacts/environment/`:

- `setup-local.log`: timestamped installation output, exact versions, Docker server/Compose versions, and container smoke result.
- `runtime-freeze.txt`: resolved installed Python package versions.
- `runtime-env.sh`: generated environment activation command exports.
- `upstream-harbor-version.txt`: upstream version pin retrieved for this setup.
- `docker-smoke.log`: initial independent container probe, when run during setup investigation.
- `final-verification.log`: activation-path check, installed Harbor version, dependency consistency check, and unchanged system Python version.

These generated files are gitignored. A successful setup ends with `KTB_DOCKER_SMOKE_OK` and `Setup completed`. The smoke container uses no network or published ports, is removed afterward, and does not change existing services.

Verified on 2026-09-26: Harbor `0.23.1.dev202609170426`, managed Python `3.12.12`, uv `0.9.28`, Docker Engine `29.4.0` (`linux/amd64`), and Docker Compose `5.1.1`. All 89 installed packages passed `uv pip check`; the system interpreter remains Python `3.10.12`. A repeat setup invocation completed successfully. Setup logs append each invocation, so use the latest completed invocation when inspecting status.

Runtime availability does not establish model authentication, oracle correctness, verifier correctness, or benchmark acceptance. Those require the separate task-validation and evaluation steps. No credentials were read during runtime setup.

## Network observations

During the 2026-09-26 setup, WSL emitted a warning that the Windows localhost proxy could not be mirrored into WSL NAT networking. PyPI metadata was reachable, while short GitHub connection probes timed out. Larger official downloads subsequently progressed using the normal WSL path; allow enough time for installation rather than changing global proxy settings.

For a machine that cannot download CPython directly, `KTB_PYTHON_ARCHIVE` can point to a separately downloaded Astral Python 3.12.12 `install_only` archive. Verify that file against the checksum published with that exact release before invoking the script. That optional path does not change networking or system settings.
