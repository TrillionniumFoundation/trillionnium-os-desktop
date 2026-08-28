#!/usr/bin/env python3
"""Create a clean D0C-05 product branch from current main using validated files."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
TARGET_BRANCH = "codex/d0c05-product-clean-v1"
PRODUCT_PATHS = (
    "Cargo.toml",
    "Cargo.lock",
    "apps/hepta-agent-portd/Cargo.toml",
    "apps/hepta-agent-portd/src/main.rs",
    "crates/hepta-peer-attestation/Cargo.toml",
    "crates/hepta-peer-attestation/src/lib.rs",
    "contracts/agent-port-custody.v1.json",
    "docs/CURRENT_STATE.md",
    "docs/MANIFEST.json",
    "docs/architecture/AGENT_PORT_SYSTEMD_CUSTODY.md",
    "docs/evidence/2026-08-28-d0c05-systemd-agent-port-custody.md",
    "docs/evidence/generated/d0c05-rust193-host-result.json",
    "manifests/repository-state.json",
    "packaging/debian/systemd/hepta-browserd-agent.socket",
    "packaging/debian/systemd/hepta-browserd-agent@.service",
    "packaging/debian/sysusers.d/trillionnium-desktop.conf",
    "packaging/debian/tmpfiles.d/trillionnium-desktop.conf",
    "packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
    "packaging/debian/hepta-agent-portd.install",
    "tools/verify_systemd_socket_custody.py",
    "tools/validate_repository.py",
)


class BranchError(RuntimeError):
    pass


def api(method: str, path: str, payload: object | None = None) -> object:
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repository:
        raise BranchError("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}{path}",
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "trillionnium-d0c05-clean-branch",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            encoded = response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise BranchError(f"GitHub API {method} {path}: {error.code} {body}") from error
    return {} if not encoded else json.loads(encoded)


def full_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40:
        raise BranchError(f"{label} is not one full SHA")
    return value


def main() -> int:
    main_ref = api("GET", "/git/ref/heads/main")
    if not isinstance(main_ref, dict) or not isinstance(main_ref.get("object"), dict):
        raise BranchError("main ref response is malformed")
    main_sha = full_sha(main_ref["object"].get("sha"), "main head")
    main_commit = api("GET", f"/git/commits/{main_sha}")
    if not isinstance(main_commit, dict) or not isinstance(main_commit.get("tree"), dict):
        raise BranchError("main commit response is malformed")
    main_tree = full_sha(main_commit["tree"].get("sha"), "main tree")

    entries: list[dict[str, object]] = []
    for relative in PRODUCT_PATHS:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise BranchError(f"missing validated product file: {relative}")
        blob = api(
            "POST",
            "/git/blobs",
            {
                "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                "encoding": "base64",
            },
        )
        if not isinstance(blob, dict):
            raise BranchError(f"malformed blob response for {relative}")
        entries.append(
            {
                "path": relative,
                "mode": "100644",
                "type": "blob",
                "sha": full_sha(blob.get("sha"), f"blob {relative}"),
            }
        )

    tree = api("POST", "/git/trees", {"base_tree": main_tree, "tree": entries})
    if not isinstance(tree, dict):
        raise BranchError("tree response is malformed")
    tree_sha = full_sha(tree.get("sha"), "clean product tree")
    commit = api(
        "POST",
        "/git/commits",
        {
            "message": "feat: add host-validated default-disabled D0C-05 custody",
            "tree": tree_sha,
            "parents": [main_sha],
        },
    )
    if not isinstance(commit, dict):
        raise BranchError("commit response is malformed")
    commit_sha = full_sha(commit.get("sha"), "clean product commit")
    try:
        created = api(
            "POST",
            "/git/refs",
            {"ref": f"refs/heads/{TARGET_BRANCH}", "sha": commit_sha},
        )
    except BranchError as error:
        if "Reference already exists" not in str(error):
            raise
        current = api("GET", f"/git/ref/heads/{quote(TARGET_BRANCH, safe='/')}")
        if not isinstance(current, dict) or not isinstance(current.get("object"), dict):
            raise BranchError("existing clean branch ref is malformed") from error
        existing_sha = full_sha(current["object"].get("sha"), "existing clean branch")
        existing_commit = api("GET", f"/git/commits/{existing_sha}")
        if not isinstance(existing_commit, dict) or not isinstance(existing_commit.get("parents"), list):
            raise BranchError("existing clean branch commit is malformed") from error
        parents = existing_commit["parents"]
        parent_shas = [item.get("sha") for item in parents if isinstance(item, dict)]
        if main_sha not in parent_shas:
            raise BranchError(
                f"refusing to replace clean branch not derived from current main: {existing_sha}"
            ) from error
        created = api(
            "PATCH",
            f"/git/refs/heads/{quote(TARGET_BRANCH, safe='/')}",
            {"sha": commit_sha, "force": True},
        )
    if not isinstance(created, dict) or not isinstance(created.get("object"), dict):
        raise BranchError("clean branch response is malformed")
    actual = full_sha(created["object"].get("sha"), "clean branch head")
    if actual != commit_sha:
        raise BranchError(f"clean branch points to {actual}, expected {commit_sha}")
    print(
        json.dumps(
            {
                "main": main_sha,
                "tree": tree_sha,
                "branch": TARGET_BRANCH,
                "commit": commit_sha,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
