#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$BASE_DIR"

"$BASE_DIR/stop.sh" || true
sleep 1
"$BASE_DIR/run.sh"
