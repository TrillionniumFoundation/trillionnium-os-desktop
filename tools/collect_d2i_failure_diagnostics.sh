#!/usr/bin/env bash
# Collect bounded, text-only diagnostics from every D2I stage. This helper is
# deliberately best-effort and must not replace the original failure status.
set -euo pipefail

root=/tmp/trillionnium-d2i
destination="$root/evidence/failure-diagnostics"
mkdir -p "$destination"

{
  printf 'github_run_id=%s\n' "${GITHUB_RUN_ID:-unknown}"
  printf 'github_run_attempt=%s\n' "${GITHUB_RUN_ATTEMPT:-unknown}"
  printf 'github_job=%s\n' "${GITHUB_JOB:-unknown}"
  printf 'github_sha=%s\n' "${GITHUB_SHA:-unknown}"
  printf 'github_ref=%s\n' "${GITHUB_REF:-unknown}"
  df -P -B1 / "$RUNNER_TEMP" /tmp 2>&1 || true
} > "$destination/runner-storage.txt"

{
  for path in \
    "$GITHUB_WORKSPACE" \
    "$GITHUB_WORKSPACE/target" \
    "$GITHUB_WORKSPACE/servo-source" \
    /tmp/trillionnium-d1 \
    /tmp/trillionnium-d1-artifact \
    /tmp/trillionnium-d2i \
    /tmp/trillionnium-d2i-artifact; do
    if [[ -e $path ]]; then
      du -s -B1 "$path" 2>&1 || true
    else
      printf 'absent\t%s\n' "$path"
    fi
  done
} > "$destination/workspace-usage.txt"

python3 - "$destination" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

DESTINATION = Path(sys.argv[1])
MAX_BYTES = 4 * 1024 * 1024
ALLOWED_SUFFIXES = {".json", ".jsonl", ".log", ".txt", ".tsv", ".sha256"}
ROOTS = [
    Path("/tmp/trillionnium-d1"),
    Path("/tmp/trillionnium-d1-artifact"),
    Path("/tmp/trillionnium-d2i"),
    Path("/tmp/trillionnium-d2i-artifact"),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


records: list[dict[str, object]] = []
for root in ROOTS:
    if not root.is_dir() or root == DESTINATION or DESTINATION in root.parents:
        continue
    for source in sorted(root.rglob("*")):
        try:
            if not source.is_file() or source.is_symlink():
                continue
            if DESTINATION == source or DESTINATION in source.parents:
                continue
            if source.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            size = source.stat().st_size
            relative = source.relative_to(root)
            target = DESTINATION / root.name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            truncated = size > MAX_BYTES
            if truncated:
                with source.open("rb") as stream:
                    stream.seek(-MAX_BYTES, os.SEEK_END)
                    data = stream.read(MAX_BYTES)
                target.write_bytes(data)
            else:
                shutil.copyfile(source, target)
                data = target.read_bytes()
            records.append(
                {
                    "source": str(source),
                    "copied_path": str(target.relative_to(DESTINATION)),
                    "source_bytes": size,
                    "copied_bytes": len(data),
                    "copied_sha256": digest(data),
                    "tail_truncated": truncated,
                }
            )
        except OSError as error:
            records.append(
                {
                    "source": str(source),
                    "copy_error": str(error),
                }
            )

manifest = {
    "schema": "trillionnium.desktop.d2i-failure-diagnostics.v1",
    "status": "BOUNDED_FAILURE_DIAGNOSTICS_CAPTURED",
    "maximum_bytes_per_file": MAX_BYTES,
    "record_count": len(records),
    "records": records,
    "claim_ceiling": "diagnostics_only_not_qualification_evidence",
}
(DESTINATION / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

printf 'D2I bounded failure diagnostics captured at %s\n' "$destination"
