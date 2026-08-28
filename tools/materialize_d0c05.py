#!/usr/bin/env python3
"""Apply the D0C-05 default-disabled socket-custody checkpoint."""

from __future__ import annotations

import json
import re
from pathlib import Path


def append_once(path: Path, marker: str, block: str) -> None:
    current = path.read_text(encoding="utf-8")
    if marker not in current:
        path.write_text(
            current.rstrip() + "\n\n" + block.strip() + "\n",
            encoding="utf-8",
        )


def add_workspace_member(path: Path, member: str) -> None:
    text = path.read_text(encoding="utf-8")
    token = f'"{member}"'
    if token not in text:
        text = text.replace("members = [\n", f"members = [\n  {token},\n", 1)
    path.write_text(text, encoding="utf-8")


def add_required_path(path: Path, required: str) -> None:
    text = path.read_text(encoding="utf-8")
    if required in text:
        return
    match = re.search(r"(REQUIRED_PATHS\s*=\s*\[)(.*?)(\n\])", text, flags=re.S)
    if match is None:
        raise RuntimeError("REQUIRED_PATHS list not found")
    body = match.group(2) + f'\n    "{required}",'
    path.write_text(
        text[: match.start(2)] + body + text[match.end(2) :],
        encoding="utf-8",
    )


def patch_peer_fixture(root: Path) -> None:
    path = root / "crates/hepta-peer-attestation/src/lib.rs"
    text = path.read_text(encoding="utf-8")
    replacements = {
        "S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 {start_time} 21 22\\n":
        "S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 {start_time} 20 21\\n",
        "S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 123456 21":
        "S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 123456 20",
    }
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new, 1)
        elif new not in text:
            raise RuntimeError(f"peer fixture patch target is absent: {old}")
    path.write_text(text, encoding="utf-8")


def patch_service(root: Path) -> None:
    path = root / "packaging/debian/systemd/hepta-browserd-agent@.service"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "SystemCallFilter=~@clock @cpu-emulation",
        "SystemCallFilter=~@cpu-emulation",
    )
    path.write_text(text, encoding="utf-8")


def patch_custody_validator(root: Path) -> None:
    path = root / "tools/verify_systemd_socket_custody.py"
    text = path.read_text(encoding="utf-8")
    old = (
        '    if contract["effect_policy"] if "effect_policy" in contract else False:\n'
        '        raise CustodyError("custody contract must not embed semantic effect policy")\n'
    )
    new = (
        '    if "effect_policy" in contract:\n'
        '        raise CustodyError("custody contract must not embed semantic effect policy")\n'
    )
    if old in text:
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def update_checkpoint(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "id": "TOS-D0C-05",
        "status": "IMPLEMENTED_HOST_VALIDATED_DEFAULT_DISABLED",
        "evidence": "docs/evidence/2026-08-28-d0c05-systemd-socket-custody.md",
        "contract": "contracts/agent-port-custody.v1.json",
        "listener_enabled": False,
    }
    checkpoints = data.setdefault("implementation_checkpoints", [])
    existing = next(
        (
            item
            for item in checkpoints
            if isinstance(item, dict) and item.get("id") == checkpoint["id"]
        ),
        None,
    )
    if existing is None:
        checkpoints.append(checkpoint)
    else:
        existing.clear()
        existing.update(checkpoint)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    root = Path.cwd()
    patch_peer_fixture(root)
    patch_service(root)
    patch_custody_validator(root)
    add_workspace_member(root / "Cargo.toml", "apps/hepta-agent-portd")
    add_workspace_member(root / "Cargo.toml", "crates/hepta-peer-attestation")

    append_once(
        root / "README.md",
        "## D0C-05 default-disabled socket custody",
        """
## D0C-05 default-disabled socket custody

The repository now carries dedicated browser/Agent service identities,
pidfd/procfs/cgroup runtime attestation, a hardened per-connection systemd
service, and an AF_UNIX socket unit. The package preset is `disable` and the
required `/etc/hepta/enable-agent-port` marker is deliberately not shipped, so
this checkpoint does not activate a listener.
""",
    )
    append_once(
        root / "docs/CURRENT_STATE.md",
        "## 2026-08-28 D0C-05 checkpoint",
        """
## 2026-08-28 D0C-05 checkpoint

systemd socket/service definitions and dedicated identities are implemented
with default-disabled activation. The inherited connection service verifies the
locked pathname, kernel peer credentials, pidfd liveness, uniform procfs IDs,
stable start time and exact cgroup-v2/systemd unit before serving one request.
Actual PID-1 activation remains a Debian QEMU gate; the enable marker is absent.
""",
    )
    append_once(
        root / "docs/DESKTOP_PLAN-2026-08-28-d5.md",
        "### D0C-05 implementation checkpoint",
        """
### D0C-05 implementation checkpoint

The local AgentPort now has installable but default-disabled systemd custody,
dedicated service accounts and pidfd/procfs/cgroup runtime identity checks. One
accepted connection maps to one short-lived hardened service and one request.
D1 must prove real socket activation under the pinned Debian image. The listener
may not be enabled until the BrowserActor, durable receipts and recovery gates
are complete.
""",
    )

    update_checkpoint(root / "manifests/repository-state.json")
    update_checkpoint(root / "docs/MANIFEST.json")

    validator = root / "tools/validate_repository.py"
    for required in (
        "apps/hepta-agent-portd/Cargo.toml",
        "apps/hepta-agent-portd/src/main.rs",
        "crates/hepta-peer-attestation/Cargo.toml",
        "crates/hepta-peer-attestation/src/lib.rs",
        "contracts/agent-port-custody.v1.json",
        "packaging/debian/systemd/hepta-browserd-agent.socket",
        "packaging/debian/systemd/hepta-browserd-agent@.service",
        "packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
        "tools/verify_systemd_socket_custody.py",
        "docs/architecture/SYSTEMD_AGENT_PORT_CUSTODY.md",
    ):
        add_required_path(validator, required)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
