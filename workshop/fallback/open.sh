#!/usr/bin/env bash
# Open a kept run in the page with no model and no network.
#   workshop/fallback/open.sh BLOCK [PORT] [LAYER]
# BLOCK is a folder here (0-setup, 1-plan, 2-build, 3-answers, 4-marks, 4-call, 5-review).
# It works on a copy under my/var/fallback/, so the kept run stays as it was. LAYER overrides the layer the page
# runs at: open the same kept run one layer lower to show the "before" (for example `open.sh 3-answers 8765 2`).
set -euo pipefail
cd "$(dirname "$0")/../.."
block="${1:-}"; port="${2:-8765}"
if [ -z "$block" ] || [ ! -d "workshop/fallback/$block" ]; then
  echo "usage: workshop/fallback/open.sh BLOCK [PORT] [LAYER]; blocks:" $(cd workshop/fallback && ls -d */ | tr -d /) >&2; exit 1
fi
copy="my/var/fallback/$block"
rm -rf "$copy"; mkdir -p "$copy"; cp -R "workshop/fallback/$block/." "$copy/"
layer="${3:-$(cat "$copy/LAYER")}"
echo "Kept run $block at layer $layer: http://127.0.0.1:$port/  (read-only: the model is off; Ctrl+C to stop)"
HARNESS_DB="$copy/harness.db" HARNESS_BRIEF_DIR="$copy/brief" HARNESS_MODULES_DIR="$copy/modules" \
HARNESS_LAYERS="$layer" HARNESS_REVIEW=off HARNESS_MODEL_PROVIDER=scripted \
  exec uv run python -m harness ui --port "$port" --no-browser
