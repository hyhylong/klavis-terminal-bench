#!/bin/bash
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
upstream="$project_root/.cache/upstream"
pin=4def1f367467b34b18e0dbdc086400ba71c3e037
mkdir -p "$upstream"
if [[ ! -d "$upstream/.git" ]]; then
    git init "$upstream"
    git -C "$upstream" remote add origin https://github.com/harbor-framework/terminal-bench.git
fi
git -C "$upstream" config core.autocrlf false
if ! git -C "$upstream" cat-file -e "$pin^{commit}" 2>/dev/null; then
    git -C "$upstream" fetch --depth=1 --filter=blob:none origin "$pin"
fi
git -C "$upstream" sparse-checkout init --cone
git -C "$upstream" sparse-checkout set .github docs scripts
git -C "$upstream" checkout --detach "$pin"
test "$(git -C "$upstream" rev-parse HEAD)" = "$pin"
printf 'Pinned upstream ready: %s\n' "$pin"
