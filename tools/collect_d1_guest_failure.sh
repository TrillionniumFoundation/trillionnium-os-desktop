#!/bin/bash
# D1 qualification-only, bounded diagnostics; never a PASS or product receipt.
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo 'Usage: collect_d1_guest_failure.sh RUN_IMAGE OUTPUT_DIRECTORY' >&2
  exit 2
fi
image=$1
destination=$2
[[ -f "$image" && ! -L "$image" ]] || exit 2
[[ -d "$destination" && ! -L "$destination" ]] || exit 2
# A trusted host caller supplies both paths after QEMU has terminated. Only the
# two fixed guest paths below may be inspected; no arbitrary directory export.
for name in acceptance.json agent-port-journal.txt; do
  # Never leave an older diagnostic looking like output from this attempt.
  rm -f -- "$destination/failure-$name"
  temporary=$(mktemp "$destination/.d1-failure.XXXXXX")
  set +e
  timeout --signal=TERM --kill-after=1s 5s \
    debugfs -R "cat /var/lib/trillionnium-d1/$name" "$image" 2>/dev/null \
    | head -c 65537 > "$temporary"
  statuses=("${PIPESTATUS[@]}")
  set -e
  if [[ "${statuses[0]}" -eq 0 && "${statuses[1]}" -eq 0 && -s "$temporary" ]] \
    && [[ $(wc -c < "$temporary") -le 65536 ]]; then
    chmod 0600 "$temporary"
    mv -fT "$temporary" "$destination/failure-$name"
  else
    rm -f "$temporary"
  fi
done
