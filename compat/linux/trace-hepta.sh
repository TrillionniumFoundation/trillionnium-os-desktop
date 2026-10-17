#!/usr/bin/env bash
# Capture a REAL pinned Hepta Agentd run without touching production state.
# Trace contents may contain private arguments, file paths and credentials.
set -euo pipefail
if (( $# < 2 )); then
  echo 'usage: A04_EXPECTED_HEPTA_SHA256=<64hex> trace-hepta.sh /absolute/path/to/codex-hepta-agentd NEW_PRIVATE_OUTPUT_DIR [agentd flags...]' >&2
  exit 64
fi
binary="$1"; out="$2"; shift 2
if [[ "$binary" != /* || ! -f "$binary" || ! -x "$binary" ]]; then
  echo 'absolute path to executable fixed-commit Hepta binary required' >&2
  exit 66
fi
if [[ -e "$out" || -L "$out" ]]; then
  echo 'output directory exists; refusing to overwrite trace evidence' >&2
  exit 73
fi
for tool in strace readelf sha256sum timeout; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "missing $tool; real Hepta trace NOT obtained" >&2
    exit 78
  fi
done
# Verify before invoking ldd or the ELF: never execute an unpinned binary.
if [[ ! "${A04_EXPECTED_HEPTA_SHA256:-}" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo 'expected exact Hepta ELF SHA256 is mandatory' >&2
  exit 65
fi
actual_sha=$(sha256sum -- "$binary" | awk '{print $1}')
if [[ "${actual_sha,,}" != "${A04_EXPECTED_HEPTA_SHA256,,}" ]]; then
  echo 'Hepta ELF sha256 mismatch, execution refused' >&2
  exit 65
fi
umask 077
mkdir -m 0700 -- "$out"
printf '%s  %s\n' "$actual_sha" "$binary" > "$out/elf.sha256"
readelf -l -- "$binary" > "$out/elf-program-headers.txt"
readelf -d -- "$binary" > "$out/elf-dynamic.txt"
if command -v ldd >/dev/null 2>&1; then
  ldd -- "$binary" > "$out/host-ldd.txt" 2>&1 || true
fi
printf '%s\n' 'pinned_elf_verified=true' 'authenticated_tool_effect_verified=false' > "$out/session-facts.txt"
# Starting the daemon does NOT prove ObjectiveStart, App Server, or tool effects.
# A provisioned independent authenticated client must drive the real product
# invocation, and record an independently observed effect during this session.
set +e
timeout --signal=TERM --kill-after=5s "${A04_TRACE_TIMEOUT:-120}s" \
  strace -ff -ttt -yy -s 256 -o "$out/trace" -- "$binary" "$@" \
  > "$out/stdout.txt" 2> "$out/stderr.txt"
status=$?
set -e
printf '%d\n' "$status" > "$out/exit-status.txt"
find "$out" -type f -name 'trace.*' -print0 | sort -z | xargs -0 -r sha256sum > "$out/trace-files.sha256"
echo "Hepta trace exit=$status, all raw output PRIVATE; no E2E claim without authenticated tool effect evidence"
# 124=timeout; 137=SIGKILL. These are INCOMPLETE sessions, not ABI incompatibility.
exit "$status"
