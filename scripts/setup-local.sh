#!/usr/bin/env bash
# Reproducible, isolated Linux/WSL Harbor setup. No model runs or credential reads.
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
runtime_root=${KTB_RUNTIME_ROOT:-"$HOME/.local/share/klavis-terminal-bench/runtime"}
harbor_version=0.23.1.dev202609170426
uv_version=0.9.28
python_version=3.12.12
smoke_image=alpine:3.21.3@sha256:a8560b36e8b8210634f77d9f7f9efd7ffa463e380b75e2e74aff4511df3ef88c
artifact_dir="$project_root/artifacts/environment"
mkdir -p "$runtime_root/bin" "$artifact_dir"
exec > >(tee -a "$artifact_dir/setup-local.log") 2>&1
printf '\nSetup started: %s\n' "$(date -u +%FT%TZ)"
printf 'Project: %s\nRuntime: %s\n' "$project_root" "$runtime_root"

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
  echo 'This setup script currently supports Linux x86_64 (including WSL2).'
  exit 1
fi
for executable in python3 docker; do
  command -v "$executable" >/dev/null || { echo "Missing prerequisite: $executable"; exit 1; }
done

export UV_CACHE_DIR="$runtime_root/cache"
export UV_PYTHON_INSTALL_DIR="$runtime_root/python"
export UV_LINK_MODE=copy
export PATH="$runtime_root/bin:$PATH"

if [[ ! -x "$runtime_root/bin/uv" ]] || [[ $("$runtime_root/bin/uv" --version) != "uv $uv_version"* ]]; then
  # The official PyPI wheel avoids requiring GitHub connectivity just to get uv.
  python3 - "$uv_version" "$runtime_root/bin" <<'PY'
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import urllib.request
import zipfile

version, target = sys.argv[1:]
with urllib.request.urlopen(f"https://pypi.org/pypi/uv/{version}/json", timeout=60) as r:
    release = json.load(r)
filename = f"uv-{version}-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
wheel = next(item for item in release["urls"] if item["filename"] == filename)
with urllib.request.urlopen(wheel["url"], timeout=120) as r:
    data = r.read()
assert hashlib.sha256(data).hexdigest() == wheel["digests"]["sha256"], "uv wheel checksum mismatch"
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    for name in ("uv", "uvx"):
        member = next(m for m in archive.namelist() if m.endswith(f".data/scripts/{name}"))
        destination = Path(target) / name
        destination.write_bytes(archive.read(member))
        os.chmod(destination, 0o755)
print(f"Installed official uv {version} wheel; sha256={wheel['digests']['sha256']}")
PY
fi

"$runtime_root/bin/uv" --version
if [[ -n ${KTB_PYTHON_ARCHIVE:-} ]]; then
  # Optional offline transfer of Astral's CPython standalone install_only archive.
  # The caller must verify the download against the matching published SHA256.
  mkdir -p "$runtime_root/standalone"
  tar -xzf "$KTB_PYTHON_ARCHIVE" -C "$runtime_root/standalone"
  python_executable="$runtime_root/standalone/python/bin/python3.12"
  [[ $("$python_executable" --version) == "Python $python_version" ]] || {
    echo "Expected Python $python_version in KTB_PYTHON_ARCHIVE"; exit 1;
  }
else
  python_executable="$python_version"
fi

if [[ ! -x "$runtime_root/venv/bin/python" ]]; then
  "$runtime_root/bin/uv" venv --python "$python_executable" "$runtime_root/venv"
fi
if [[ $("$runtime_root/venv/bin/python" --version) != "Python $python_version" ]]; then
  echo "Existing runtime uses a different Python version; choose a new KTB_RUNTIME_ROOT."
  exit 1
fi
"$runtime_root/bin/uv" pip install --python "$runtime_root/venv/bin/python" "harbor==$harbor_version"
"$runtime_root/bin/uv" pip freeze --python "$runtime_root/venv/bin/python" > "$artifact_dir/runtime-freeze.txt"

printf 'export KTB_RUNTIME_ROOT=%q\n' "$runtime_root" > "$artifact_dir/runtime-env.sh"
printf 'export HARBOR_PYTHON=%q\n' "$runtime_root/venv/bin/python" >> "$artifact_dir/runtime-env.sh"
printf 'export PATH=%q:%q:"$PATH"\n' "$runtime_root/venv/bin" "$runtime_root/bin" >> "$artifact_dir/runtime-env.sh"

"$runtime_root/venv/bin/python" --version
"$runtime_root/venv/bin/harbor" --version
docker version --format '{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}'
docker compose version
# A separate, short-lived container; no published ports or existing service changes.
docker run --rm --network none "$smoke_image" sh -ec 'test "$(uname -m)" = x86_64; printf "KTB_DOCKER_SMOKE_OK\n"'
printf 'Setup completed: %s\n' "$(date -u +%FT%TZ)"
printf 'For subsequent shells: source %q\n' "$artifact_dir/runtime-env.sh"
