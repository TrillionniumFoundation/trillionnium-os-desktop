#!/usr/bin/env bash
# Bind the fixture-free product daemon to the D1 image input.
#
# The D1 request server remains the separate hepta-agent-d1-fixture selected by
# the image-local systemd drop-in. The image builder receives the product path
# directly; qualification bytes are never copied over or temporarily renamed
# into the product slot.
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
trap 'rm -rf -- "$scratch"' EXIT
self_check="$scratch/product-self-check.json"

"$product_binary" --self-check > "$self_check"

python3 - "$self_check" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


EXPECTED_KEYS = {
    "schema",
    "ok",
    "listener_created",
    "expected_product_socket",
    "product_handler_connected",
    "fixture_handler_linked",
    "activation_fail_closed",
    "peer_pid",
    "peer_uid",
    "peer_gid",
}
EXPECTED_STABLE = {
    "schema": "trillionnium.desktop.agent-portd-self-check.v2",
    "ok": True,
    "listener_created": False,
    "expected_product_socket": "/run/hepta/browserd/agent.sock",
    "product_handler_connected": False,
    "fixture_handler_linked": False,
    "activation_fail_closed": True,
}


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member: {key}")
        value[key] = item
    return value


def load_report(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
    )
    if not isinstance(value, dict) or set(value) != EXPECTED_KEYS:
        raise SystemExit(f"unexpected product self-check schema: {path}")
    for key, expected in EXPECTED_STABLE.items():
        if type(value[key]) is not type(expected) or value[key] != expected:
            raise SystemExit(f"unexpected product self-check field {key}: {path}")
    for key in ("peer_pid", "peer_uid", "peer_gid"):
        item = value[key]
        if type(item) is not int or item < (1 if key == "peer_pid" else 0):
            raise SystemExit(f"invalid product self-check identity {key}: {path}")
    return value


load_report(Path(sys.argv[1]))
PY

# Bind the canonical product path explicitly. This prevents an inherited
# D1_AGENT_PORTD_BINARY from routing the build to a fixture or qualification
# binary.
D1_AGENT_PORTD_BINARY="$product_binary" "$runner" run-pipeline
