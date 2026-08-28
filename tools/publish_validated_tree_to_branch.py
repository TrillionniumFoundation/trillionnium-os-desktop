#!/usr/bin/env python3
"""Atomically publish the validated D0C-05 product file set with GitHub Git Data API."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "codex/d0c05-host-validated-v3"
PRODUCT_PATHS = (
    "Cargo.toml",
    "Cargo.lock",
    ".github/workflows/agent-port-custody.yml",
    "apps/hepta-agent-portd/Cargo.toml",
    "apps/hepta-agent-portd/src/main.rs",
    "crates/hepta-peer-attestation/Cargo.toml",
    "crates/hepta-peer-attestation/src/lib.rs",
    "contracts/agent-port-custody.v1.json",
    "docs/architecture/AGENT_PORT_SYSTEMD_CUSTODY.md",
    "docs/evidence/2026-08-28-d0c05-systemd-agent-port-custody.md",
    "packaging/debian/systemd/hepta-browserd-agent.socket",
    "packaging/debian/systemd/hepta-browserd-agent@.service",
    "packaging/debian/sysusers.d/trillionnium-desktop.conf",
    "packaging/debian/tmpfiles.d/trillionnium-desktop.conf",
    "packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
    "packaging/debian/hepta-agent-portd.install",
    "tools/verify_systemd_socket_custody.py",
    "tools/validate_repository.py",
)
DELETE_PATHS = (
    "tools/materialize_d0c05_current_main.py",
    "tools/fix_d0c05_peer_attestation_clippy.py",
    "tools/publish_validated_tree_to_branch.py",
)


class ApiError(RuntimeError):
    pass


def api(method: str, path: str, payload: object | None = None) -> object:
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repository:
        raise ApiError("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
    url = f"https://api.github.com/repos/{repository}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "trillionnium-d0c05-publisher",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            encoded = response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise ApiError(f"GitHub API {method} {path} failed: {error.code} {body}") from error
    return {} if not encoded else json.loads(encoded)


def require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40:
        raise ApiError(f"{label} is not one full commit/blob SHA")
    return value


def main() -> int:
    ref = api("GET", f"/git/ref/heads/{quote(BRANCH, safe='/')}")
    if not isinstance(ref, dict) or not isinstance(ref.get("object"), dict):
        raise ApiError("branch ref response is malformed")
    base_sha = require_sha(ref["object"].get("sha"), "branch head")
    expected_sha = os.environ.get("GITHUB_SHA")
    if expected_sha and base_sha != expected_sha:
        raise ApiError(f"branch moved during validation: expected {expected_sha}, actual {base_sha}")
    commit = api("GET", f"/git/commits/{base_sha}")
    if not isinstance(commit, dict) or not isinstance(commit.get("tree"), dict):
        raise ApiError("base commit response is malformed")
    base_tree = require_sha(commit["tree"].get("sha"), "base tree")

    entries: list[dict[str, object]] = []
    for relative in PRODUCT_PATHS:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise ApiError(f"validated product file is missing or symlinked: {relative}")
        blob = api(
            "POST",
            "/git/blobs",
            {
                "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                "encoding": "base64",
            },
        )
        if not isinstance(blob, dict):
            raise ApiError(f"blob response is malformed for {relative}")
        entries.append(
            {
                "path": relative,
                "mode": "100644",
                "type": "blob",
                "sha": require_sha(blob.get("sha"), f"blob {relative}"),
            }
        )
    for relative in DELETE_PATHS:
        entries.append({"path": relative, "mode": "100644", "type": "blob", "sha": None})

    tree = api("POST", "/git/trees", {"base_tree": base_tree, "tree": entries})
    if not isinstance(tree, dict):
        raise ApiError("tree response is malformed")
    tree_sha = require_sha(tree.get("sha"), "product tree")
    new_commit = api(
        "POST",
        "/git/commits",
        {
            "message": "feat: integrate default-disabled D0C-05 socket custody",
            "tree": tree_sha,
            "parents": [base_sha],
        },
    )
    if not isinstance(new_commit, dict):
        raise ApiError("commit response is malformed")
    new_sha = require_sha(new_commit.get("sha"), "product commit")
    updated = api(
        "PATCH",
        f"/git/refs/heads/{quote(BRANCH, safe='/')}",
        {"sha": new_sha, "force": False},
    )
    if not isinstance(updated, dict) or not isinstance(updated.get("object"), dict):
        raise ApiError("updated ref response is malformed")
    actual = require_sha(updated["object"].get("sha"), "updated branch head")
    if actual != new_sha:
        raise ApiError(f"updated branch points to {actual}, expected {new_sha}")
    print(json.dumps({"base": base_sha, "tree": tree_sha, "commit": new_sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
