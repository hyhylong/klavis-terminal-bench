#!/usr/bin/env bash
# Local checks only. No login, network requests, agent runs, or credential output.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ! -f "$project_root/artifacts/environment/runtime-env.sh" ]]; then
  echo 'Runtime is missing; run bash scripts/setup-local.sh first.' >&2
  exit 2
fi
source "$project_root/artifacts/environment/runtime-env.sh"
exec "$HARBOR_PYTHON" "$project_root/evaluation/preflight.py" "$@"
