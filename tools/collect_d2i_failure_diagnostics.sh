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

MAX_CONSOLE_BYTES = 256 * 1024
MAX_CONSOLE_BYTES_PER_FILE = 64 * 1024
MAX_CONSOLE_LINES_PER_FILE = 200


def diagnostic_priority(record: dict[str, object]) -> tuple[int, str]:
    copied = str(record.get("copied_path", ""))
    source = str(record.get("source", ""))
    name = Path(source).name.lower()
    score = 100
    if name == "serial.log":
        score = 0
    elif name == "runtime-journal.txt":
        score = 1
    elif name in {"guest-acceptance.json", "runtime-ready.json"}:
        score = 2
    elif name == "qemu.log":
        score = 3
    elif "acceptance" in name or "runtime" in name or "boot" in name:
        score = 10
    elif "/qemu/" in source:
        score = 20
    return score, copied


def bounded_console_summary() -> tuple[list[str], int]:
    selected: list[str] = []
    emitted = 0
    seen_sources: set[str] = set()
    for record in sorted(records, key=diagnostic_priority):
        copied = record.get("copied_path")
        source = record.get("source")
        if not isinstance(copied, str) or not isinstance(source, str):
            continue
        if source in seen_sources:
            continue
        priority, _ = diagnostic_priority(record)
        if priority >= 100:
            continue
        seen_sources.add(source)
        path = DESTINATION / copied
        try:
            data = path.read_bytes()
        except OSError:
            continue
        data = data[-MAX_CONSOLE_BYTES_PER_FILE:]
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()[-MAX_CONSOLE_LINES_PER_FILE:]
        payload = (
            f"--- D2I_DIAGNOSTIC_TAIL source={source} copied={copied} ---\n"
            + "\n".join(lines)
            + "\n--- END_D2I_DIAGNOSTIC_TAIL ---\n"
        ).encode("utf-8", errors="replace")
        remaining = MAX_CONSOLE_BYTES - emitted
        if remaining <= 0:
            break
        if len(payload) > remaining:
            payload = payload[-remaining:]
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        emitted += len(payload)
        selected.append(source)
    return selected, emitted


selected_console_sources, console_summary_bytes = bounded_console_summary()
manifest = {
    "schema": "trillionnium.desktop.d2i-failure-diagnostics.v1",
    "status": "BOUNDED_FAILURE_DIAGNOSTICS_CAPTURED",
    "maximum_bytes_per_file": MAX_BYTES,
    "maximum_console_bytes": MAX_CONSOLE_BYTES,
    "maximum_console_bytes_per_file": MAX_CONSOLE_BYTES_PER_FILE,
    "maximum_console_lines_per_file": MAX_CONSOLE_LINES_PER_FILE,
    "console_summary_bytes": console_summary_bytes,
    "console_summary_sources": selected_console_sources,
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
