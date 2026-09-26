#!/usr/bin/env bash
# Explicit evaluation launcher: this script DOES invoke the selected model.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
case "${1:-}" in
  standard-codex|cheat-codex) provider=codex ;;
  standard-deepseek|cheat-deepseek) provider=deepseek ;;
  *) echo 'Usage: bash evaluation/run.sh {standard-codex|cheat-codex|standard-deepseek|cheat-deepseek}' >&2; exit 2 ;;
esac
source "$project_root/artifacts/environment/runtime-env.sh"
bash "$project_root/scripts/preflight-models.sh" --provider "$provider"
resolved_config=$("$HARBOR_PYTHON" "$project_root/evaluation/prepare_job.py" "$@")
printf 'Starting evaluation with resolved config: %s\n' "$resolved_config"
env_args=()
if [[ -f "$project_root/.env" ]]; then
  env_args=(--env-file "$project_root/.env")
fi
# DrvFS remounts can detach an existing process cwd while the absolute path
# remains readable. Keep Harbor's cwd on Linux; task/config/jobs paths are absolute.
runtime_cwd="$HOME/.local/state/klavis-terminal-bench"
mkdir -p "$runtime_cwd"
cd "$runtime_cwd"
exec harbor run --config "$resolved_config" "${env_args[@]}"
