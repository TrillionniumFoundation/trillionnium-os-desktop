#!/usr/bin/env bash

# Shared by image/QEMU shell gates.  The callers must invoke this function on
# the raw CLI spelling before using readlink/realpath: resolving first erases
# the evidence that a path traversed a symlink.  Missing trailing components
# are allowed so callers can safely create a new output directory/file.
reject_symlink_path() {
  local raw_path=${1-}
  local label=${2:-path}
  local current
  local parent

  if [[ -z "$raw_path" ]]; then
    printf '%s must not be empty\n' "$label" >&2
    return 1
  fi

  current=$raw_path
  while [[ -n "$current" && "$current" != "." && "$current" != "/" ]]; do
    if [[ -L "$current" ]]; then
      printf '%s contains a symlink component: %s\n' "$label" "$raw_path" >&2
      return 1
    fi
    parent=$(dirname -- "$current") || {
      printf 'cannot inspect %s: dirname failed\n' "$label" >&2
      return 1
    }
    [[ "$parent" == "$current" ]] && break
    current=$parent
  done
}

# Validate a path that is expected to be a regular file.  Missing trailing
# components are allowed so callers can guard a destination before creating
# it; an existing directory, FIFO, socket, device, or symlink is rejected.
require_regular_path() {
  local raw_path=${1-}
  local label=${2:-file}
  reject_symlink_path "$raw_path" "$label" || return 1
  if [[ -e "$raw_path" && ! -f "$raw_path" ]]; then
    printf '%s is not a regular file: %s\n' "$label" "$raw_path" >&2
    return 1
  fi
}
