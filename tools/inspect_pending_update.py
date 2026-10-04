#!/usr/bin/env python3
"""Read-only update diagnostics; stdout contains static enums, never identity."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys

_spec = importlib.util.spec_from_file_location("hepta_update_boot_observer_cli", Path(__file__).resolve().parents[1] / "platform/update_boot_observer.py")
if _spec is None or _spec.loader is None:
    raise RuntimeError("bundled observer unavailable")
observer = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = observer
_spec.loader.exec_module(observer)


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, "update_observer_arguments_refused\n")


def _private_output(value, output, state, slots):
    """Explicit new private output only; never create inside authority roots."""
    output_parts = observer._path(output)
    data = value.private_json() + b"\n"
    if len(data) > observer.MAX_DIAGNOSTIC_BYTES:
        raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
    for authority in (state, slots):
        parts = observer._path(authority)
        if output_parts[:len(parts)] == parts:
            raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
    reader = observer._Reader()
    try:
        parent = reader.root(output.parent)
        # A lexical alias must not let output add a file to the scanned roots.
        forbidden = set()
        for authority in (state, slots):
            try:
                root = reader.root(authority)
            except (OSError, observer._Refused):
                continue
            forbidden.add(observer._directory(os.fstat(root.fd))[:2])
        for _, _, child, _ in reader.directories:
            if observer._directory(os.fstat(child.fd))[:2] in forbidden and child is parent:
                raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
        # The parent's entire retained chain must stay outside the authority
        # roots, including a bind-mount alias of an authority directory.
        output_chain = []
        current = parent
        while True:
            output_chain.append(current)
            links = [entry for entry in reader.directories if entry[2] is current]
            if not links:
                break
            current = links[0][0]
        if any(observer._directory(os.fstat(item.fd))[:2] in forbidden for item in output_chain):
            raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
        owned = observer._Descriptor()
        reader.owners.append(owned)
        owned._owned = [os.open(output.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=parent.fd)]
        metadata = os.fstat(owned.fd)
        if metadata.st_nlink != 1 or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
            raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
        position = 0
        while position < len(data):
            reader._check()
            count = os.write(owned.fd, data[position:])
            if count <= 0:
                raise OSError("output_write_refused")
            position += count
        os.fsync(owned.fd)
        if os.pread(owned.fd, len(data) + 1, 0) != data:
            raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
        reader.confirm((parent,))
        retained = os.fstat(owned.fd)
        named = os.stat(output.name, dir_fd=parent.fd, follow_symlinks=False)
        if observer._regular(retained) != observer._regular(named) or retained.st_size != len(data):
            raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
        os.fsync(parent.fd)
    finally:
        reader.close()


def main(arguments=None):
    parser = _Parser(description="Read-only source diagnostics; no update continuation authority.")
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--slot-root", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Explicit new private diagnostic file in a pre-existing private directory.")
    args = parser.parse_args(arguments)
    try:
        value = observer.inspect_pending_update(args.state_root, args.slot_root)
        if args.output is not None:
            _private_output(value, args.output, args.state_root, args.slot_root)
        print(value.public_json().decode("ascii"))
        return 0 if value.status is observer.ObservationStatus.NO_PENDING_UPDATE else 2
    except (OSError, ValueError, observer._Refused):
        print("update_observer_output_refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
