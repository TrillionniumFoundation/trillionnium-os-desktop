#!/usr/bin/env python3
"""Check active Linux product pins and Cargo locks without qualifying runtime use.

Python 3.11+; historical evidence and independent kernel profiles are excluded.
The full Cargo graph/resource and clean-checkout gates remain separate.
"""
import argparse
import json
from pathlib import Path
import re
import tomllib

UPSTREAM = "https://github.com/TrillionniumFoundation/hepta-private-ci"
SOURCE = "support/ui/HEPTA_SHARED_PRESENTER.json"
LOCKS = ("ui/Cargo.lock", "services/hepta-session-host/Cargo.lock")
REQUIRED = {
    "ui/core/Cargo.toml": {"hepta-control-core", "hepta-robrix-ui"},
    "services/hepta-session-host/Cargo.toml": {
        "codex-hepta-agentd", "hepta-control-core", "codex-hepta-objective",
        "codex-hepta-operations", "codex-hepta-types", "codex-hepta-agent-protocol",
        "codex-hepta-memory",
    },
}
ORIGINAL_PATCHES = {
    "i18n-config", "secret-service", "zbus-secret-service-keyring-store", "anymap2",
    "imbl", "matrix-sdk-sqlite", "matrix-sdk-crypto",
}
NATIVE_PATCHES = {"accesskit", "accesskit_consumer", "accesskit_atspi_common", "accesskit_unix"}
REQUIRED_PATCHES = {
    "ui/Cargo.toml": ORIGINAL_PATCHES | NATIVE_PATCHES,
    "services/hepta-session-host/Cargo.toml": ORIGINAL_PATCHES,
}
# Some declared patches are unused for these feature graphs. Require resolved
# packages only for the actual product entrypoints and native adapter, while
# still checking every original lock source that is present below.
REQUIRED_LOCKED = {
    "ui/Cargo.lock": set().union(*REQUIRED.values()) | NATIVE_PATCHES,
    "services/hepta-session-host/Cargo.lock": REQUIRED["services/hepta-session-host/Cargo.toml"],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def tables(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from tables(child)
    elif isinstance(value, list):
        for child in value:
            yield from tables(child)


def verify(root):
    source = json.loads((root / SOURCE).read_bytes())
    require(source.get("repository") == "TrillionniumFoundation/hepta-private-ci",
            "source map names a different Hepta repository")
    commit, tree = source.get("commit", ""), source.get("tree", "")
    require(bool(re.fullmatch("[0-9a-f]{40}", commit))
            and bool(re.fullmatch("[0-9a-f]{40}", tree)), "source map needs full commit/tree")
    for relative in REQUIRED.keys() | REQUIRED_PATCHES.keys():
        require((root / relative).is_file(), f"missing required product manifest: {relative}")
    manifests = sorted((root / "ui").rglob("Cargo.toml"))
    manifests.append(root / "services/hepta-session-host/Cargo.toml")
    # Cargo targets and local dependency caches are not product source.
    manifests = [p for p in manifests if "target" not in p.relative_to(root).parts]
    declared = 0
    for path in manifests:
        relative = path.relative_to(root).as_posix()
        value = tomllib.loads(path.read_text())
        for name in REQUIRED.get(relative, set()):
            dep = value.get("dependencies", {}).get(name, {})
            require(isinstance(dep, dict) and dep.get("git") == UPSTREAM and dep.get("rev") == commit,
                    f"{relative}: {name} must use the selected original Hepta revision")
        for name in REQUIRED_PATCHES.get(relative, set()):
            patch = value.get("patch", {}).get("crates-io", {}).get(name, {})
            require(isinstance(patch, dict) and patch.get("git") == UPSTREAM
                    and patch.get("rev") == commit,
                    f"{relative}: required original Hepta patch {name} is missing or replaced")
        for entry in tables(value):
            url = entry.get("git")
            if isinstance(url, str) and url.removesuffix(".git") == UPSTREAM:
                require(url == UPSTREAM and entry.get("rev") == commit
                        and "branch" not in entry and "tag" not in entry,
                        f"{relative}: Hepta dependency/patch differs from the selected revision")
                declared += 1
    expected = f"git+{UPSTREAM}?rev={commit}#{commit}"
    locked = {}
    for relative in LOCKS:
        packages = tomllib.loads((root / relative).read_text()).get("package", [])
        selected = [p for p in packages if isinstance(p.get("source"), str)
                    and p["source"].startswith(f"git+{UPSTREAM}")]
        require(bool(selected), f"{relative}: missing original Hepta lock entries")
        require(all(p["source"] == expected for p in selected),
                f"{relative}: mixed or stale original Hepta lock entries")
        for name in REQUIRED_LOCKED[relative]:
            matches = [p for p in packages if p.get("name") == name]
            require(len(matches) == 1 and matches[0].get("source") == expected,
                    f"{relative}: required original package {name} is missing, duplicated or replaced")
        locked[relative] = len(selected)
    readme = (root / "README.md").read_text()
    links = re.findall(re.escape(UPSTREAM) + r"/(?:commit|blob)/([0-9a-f]{40})", readme)
    require(bool(links) and set(links) == {commit}, "README original Hepta links are stale")
    require(f"tree `{tree}`" in readme, "README original Hepta tree is stale")
    return {"schema": "trill.product-source-check.v1", "status": "passed",
            "hepta_commit": commit, "hepta_tree": tree, "manifests": len(manifests),
            "hepta_declarations": declared, "locked_packages": locked,
            "runtime_tests": "not_run_by_this_tool", "production_authority_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve()), indent=2))


if __name__ == "__main__":
    main()
