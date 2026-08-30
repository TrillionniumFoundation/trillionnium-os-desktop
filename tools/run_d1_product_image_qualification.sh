#!/usr/bin/env bash
# Bind the fixture-free product daemon into the legacy D1 image-input slot.
#
# The D1 request server remains the separate hepta-agent-d1-fixture selected by
# the image-local systemd drop-in. This adapter exists because the historical
# pipeline names its image input after qualificationd even though the guest
# acceptance contract requires /usr/libexec/hepta-agent-portd to contain the
# default product binary.
set -euo pipefail

workspace=${GITHUB_WORKSPACE:-}
if [[ -z "$workspace" ]]; then
  workspace=$(git rev-parse --show-toplevel)
fi
workspace=$(readlink -f -- "$workspace")
if [[ ! -d "$workspace" ]]; then
  echo "D1 workspace is not a directory: $workspace" >&2
  exit 1
fi
if [[ "$(git -C "$workspace" rev-parse --show-toplevel)" != "$workspace" ]]; then
  echo "D1 workspace is not the canonical Git root" >&2
  exit 1
fi

product_binary="$workspace/target/release/hepta-agent-portd"
qualification_binary="$workspace/target/release/hepta-agent-port-qualificationd"
legacy_image_slot=$qualification_binary
fixture_binary="$workspace/target/release/hepta-agent-d1-fixture"
runner="$workspace/tools/run_d1_final_qualification.sh"

for binary in "$product_binary" "$qualification_binary" "$fixture_binary"; do
  if [[ ! -f "$binary" || ! -x "$binary" || -L "$binary" ]]; then
    echo "D1 binary is missing or unsafe: $binary" >&2
    exit 1
  fi
done
if [[ ! -f "$runner" || ! -x "$runner" || -L "$runner" ]]; then
  echo "D1 qualification runner is missing or unsafe: $runner" >&2
  exit 1
fi

product_sha256=$(sha256sum -- "$product_binary" | awk '{print $1}')
qualification_sha256=$(sha256sum -- "$qualification_binary" | awk '{print $1}')
if [[ "$product_sha256" == "$qualification_sha256" ]]; then
  echo "product and qualification daemons unexpectedly have identical bytes" >&2
  exit 1
fi

scratch_parent=${RUNNER_TEMP:-${TMPDIR:-/tmp}}
scratch=$(mktemp -d -- "$scratch_parent/d1-product-image-binding.XXXXXX")
backup="$scratch/hepta-agent-port-qualificationd"
self_check="$scratch/product-self-check.json"
slot_self_check="$scratch/image-slot-self-check.json"
install -m 0755 -- "$qualification_binary" "$backup"

cleanup() {
  local status=$?
  if [[ -f "$backup" ]]; then
    install -m 0755 -- "$backup" "$legacy_image_slot" || status=1
  fi
  rm -rf -- "$scratch" || status=1
  exit "$status"
}
trap cleanup EXIT

"$product_binary" --self-check > "$self_check"
python3 - "$self_check" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
value = json.loads(path.read_text(encoding="utf-8"))
if value.get("ok") is not True:
    raise SystemExit("product daemon self-check is not healthy")
if value.get("product_handler_connected") is not False:
    raise SystemExit("product daemon unexpectedly links a request handler")
if value.get("fixture_handler_linked") is not False:
    raise SystemExit("product daemon unexpectedly links a qualification fixture")
if value.get("activation_fail_closed") is not True:
    raise SystemExit("product daemon activation is not fail-closed")
PY

# The old pipeline injects this path as /usr/libexec/hepta-agent-portd. Replace
# its bytes only for the duration of the image build, then restore the distinct
# qualification binary through the EXIT trap.
install -m 0755 -- "$product_binary" "$legacy_image_slot"
if [[ "$(sha256sum -- "$legacy_image_slot" | awk '{print $1}')" != "$product_sha256" ]]; then
  echo "D1 image slot does not contain the exact product binary" >&2
  exit 1
fi
"$legacy_image_slot" --self-check > "$slot_self_check"
cmp --silent -- "$self_check" "$slot_self_check" || {
  echo "D1 image slot self-check differs from the product binary" >&2
  exit 1
}

"$runner" run-pipeline
