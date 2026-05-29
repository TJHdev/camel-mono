#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vendor/commit-mono"

if [[ -d "$VENDOR/.git" ]]; then
    echo "Updating Commit Mono in $VENDOR"
    git -C "$VENDOR" pull --ff-only
else
    echo "Cloning Commit Mono into $VENDOR"
    git clone --depth 1 https://github.com/eigilnikolajsen/commit-mono.git "$VENDOR"
fi

echo "Source fonts:"
ls "$VENDOR/src/fonts/fontlab"/CommitMono*-400Regular.otf
