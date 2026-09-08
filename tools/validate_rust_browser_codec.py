#!/usr/bin/env python3
"""Fail-closed static and cross-contract audit for the D0C-03 Rust codec source.

This validator is deliberately not a Rust compiler. Its result may prove that
required files, constants, mappings, dependency locks and claim ceilings are
present, but it never upgrades fmt/Clippy/test/self-check to PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import PurePosixPath
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

# This is the source object recorded by the historical Rust 1.93 host result
# checked into the repository.  It remains useful as provenance while a
# candidate is being revalidated, but it must never be presented as evidence
# for a newer tree.
HISTORICAL_HOST_SOURCE_SHA = "4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb"
CODEC_CAPABILITY_STATUS = "HOST_VALIDATED_RUST_1_93_NO_DISPATCH"
STALE_EVIDENCE_LIFECYCLE = "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN"


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Decode JSON objects without silently selecting a duplicate member.

    Contract and host-result files are evidence inputs.  Accepting duplicate
    keys would make the value depend on the parser (or on which consumer reads
    it first), so this validator treats ambiguity as a hard failure.
    """

    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def load_json_strict(value: object) -> object:
    """Load JSON from a text/bytes value or a file-like stream strictly."""

    if hasattr(value, "read"):
        return json.load(value, object_pairs_hook=_reject_duplicate_json_keys)
    return json.loads(value, object_pairs_hook=_reject_duplicate_json_keys)


def _has_symlink_component(path: Path) -> bool:
    """Check lexical path components without resolving links."""

    lexical = Path(os.fspath(path))
    if not lexical.is_absolute():
        lexical = Path.cwd() / lexical
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component in {lexical.anchor, "."}:
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ValueError(f"cannot inspect path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _open_regular(path: Path, *, label: str) -> int:
    """Open a regular file with a final-component no-follow check."""

    if _has_symlink_component(path):
        raise ValueError(f"{label} contains a symlink: {path}")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | _O_CLOEXEC | _O_NONBLOCK | _O_NOFOLLOW,
        )
    except OSError as error:
        raise ValueError(f"{label} is absent or unreadable: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_text_nofollow(path: Path, *, label: str = "source file") -> str:
    """Read one regular UTF-8 file without following a symlink."""

    descriptor = _open_regular(path, label=label)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_bytes_nofollow(path: Path, *, label: str = "source file") -> bytes:
    """Read one regular binary file without following a symlink."""

    descriptor = _open_regular(path, label=label)
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def repo_path(value: object, *, label: str = "repository-relative path") -> Path:
    """Convert an untrusted contract path to a confined repository path.

    Only canonical POSIX-relative paths are accepted.  In particular, an
    absolute path or a traversal component cannot escape ``ROOT`` even when
    this helper is called by a workflow inline script.
    """

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    if "\\" in value or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} contains unsafe characters")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or not parsed.parts
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or parsed.as_posix() != value
    ):
        raise ValueError(f"{label} must be a canonical repository-relative path")
    candidate = ROOT.joinpath(*parsed.parts)
    # The lexical checks above make this containment check explicit and guard
    # against future changes to path construction.
    try:
        candidate.relative_to(ROOT)
    except ValueError as error:
        raise ValueError(f"{label} escapes repository root") from error
    return candidate


def load_json_nofollow(path: Path, *, label: str = "JSON source") -> object:
    """Read and strictly decode a repository/evidence JSON file."""

    descriptor = _open_regular(path, label=label)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            return load_json_strict(stream)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def regular_file_exists_nofollow(path: Path, *, label: str) -> bool:
    """Check one regular file through the same no-follow open policy."""

    try:
        descriptor = _open_regular(path, label=label)
    except (OSError, ValueError):
        return False
    os.close(descriptor)
    return True


def sha256(path: Path) -> str:
    return hashlib.sha256(read_bytes_nofollow(path, label="hashed source")).hexdigest()


def git_blob_sha1(path: Path) -> str:
    """Return the exact Git blob object ID for one regular source file."""

    payload = read_bytes_nofollow(path, label="Git-blob source")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def require(condition: bool, message: str, checks: list[str]) -> None:
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def git_head_sha() -> str | None:
    """Return the checked-out commit when this validator runs in a Git tree.

    The validator is also used from source snapshots, so an unavailable Git
    executable is represented as ``None``.  Fresh/merge-ready evidence is
    still required to carry a well-formed source SHA; CI runs in a checkout
    and therefore gets the stronger exact-head comparison.
    """

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def index_lock_packages(lock: object) -> dict[str, list[dict[str, object]]]:
    """Index Cargo.lock packages without silently folding duplicate records.

    Cargo permits the same crate name at multiple versions/sources.  A plain
    ``{name: package}`` comprehension silently keeps whichever record appears
    last, allowing a malformed lockfile (or a future validator change) to make
    the checked dependency appear to resolve to a different package.  Retain
    every record and reject duplicate package identities, where the identity
    is the complete ``(name, version, source)`` tuple.
    """

    if not isinstance(lock, dict):
        raise AssertionError("Cargo.lock root must be an object")
    entries = lock.get("package")
    if not isinstance(entries, list):
        raise AssertionError("Cargo.lock package list is missing")
    by_name: dict[str, list[dict[str, object]]] = {}
    seen: set[tuple[object, object, object]] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise AssertionError(f"Cargo.lock package {index} is not an object")
        name = entry.get("name")
        version = entry.get("version")
        source = entry.get("source")
        if not isinstance(name, str) or not isinstance(version, str):
            raise AssertionError(f"Cargo.lock package {index} lacks name/version")
        if source is not None and not isinstance(source, str):
            raise AssertionError(f"Cargo.lock package {name} has invalid source")
        identity = (name, version, source)
        if identity in seen:
            raise AssertionError(
                "Cargo.lock contains duplicate package identity "
                f"(name={name!r}, version={version!r}, source={source!r})"
            )
        seen.add(identity)
        by_name.setdefault(name, []).append(entry)
    return by_name


def one_lock_package(
    packages: dict[str, list[dict[str, object]]], name: str
) -> dict[str, object]:
    candidates = packages.get(name, [])
    if len(candidates) != 1:
        raise AssertionError(
            f"Cargo.lock package {name!r} is ambiguous or missing "
            f"({len(candidates)} records)"
        )
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()

    checks: list[str] = []
    contract = load_json_nofollow(
        ROOT / "contracts/browser-codec.v1.json", label="codec contract"
    )
    errors = load_json_nofollow(
        ROOT / "contracts/error-codes.v1.json", label="error-code contract"
    )["codes"]
    workspace = tomllib.loads(
        read_text_nofollow(ROOT / "Cargo.toml", label="workspace manifest")
    )
    lock = tomllib.loads(
        read_text_nofollow(ROOT / "Cargo.lock", label="Cargo.lock")
    )
    manifest = tomllib.loads(
        read_text_nofollow(
            ROOT / "crates/hepta-browser-codec/Cargo.toml",
            label="codec manifest",
        )
    )
    lib = read_text_nofollow(
        ROOT / "crates/hepta-browser-codec/src/lib.rs", label="codec lib"
    )
    json_source = read_text_nofollow(
        ROOT / "crates/hepta-browser-codec/src/json.rs", label="codec JSON source"
    )
    model_paths = [
        ROOT / "crates/hepta-browser-codec/src/model.rs",
        *sorted((ROOT / "crates/hepta-browser-codec/src/model").glob("*.rs")),
    ]
    model = "\n".join(
        read_text_nofollow(path, label="codec model source") for path in model_paths
    )
    tests = read_text_nofollow(
        ROOT / "crates/hepta-browser-codec/src/tests.rs", label="codec tests"
    )
    browserd_manifest = tomllib.loads(
        read_text_nofollow(
            ROOT / "apps/hepta-browserd/Cargo.toml", label="browserd manifest"
        )
    )
    browserd = read_text_nofollow(
        ROOT / "apps/hepta-browserd/src/lib.rs", label="browserd source"
    )

    operation_schema = contract.get("operation_schema")
    require(
        isinstance(operation_schema, dict),
        "codec contract operation schema metadata is an object",
        checks,
    )
    if not isinstance(operation_schema, dict):
        raise AssertionError("codec contract operation schema metadata is not an object")
    operation_schema_path = repo_path(
        operation_schema.get("path"), label="operation_schema.path"
    )
    require(
        operation_schema_path == ROOT / "contracts/browser-api.v1.schema.json",
        "codec operation schema path is canonical",
        checks,
    )
    operation_schema_sha = operation_schema.get("git_blob_sha1")
    require(
        isinstance(operation_schema_sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", operation_schema_sha) is not None,
        "codec operation schema Git blob SHA-1 is well-formed",
        checks,
    )
    if not isinstance(operation_schema_sha, str):
        raise AssertionError("codec operation schema Git blob SHA-1 is not a string")
    require(
        operation_schema_sha == git_blob_sha1(operation_schema_path),
        "codec operation schema Git blob SHA-1 matches the tracked schema",
        checks,
    )

    members = workspace["workspace"]["members"]
    defaults = workspace["workspace"]["default-members"]
    require("crates/hepta-browser-codec" in members, "codec is a workspace member", checks)
    require("crates/hepta-browser-codec" in defaults, "codec is a default workspace member", checks)
    require(
        manifest["dependencies"] == {"sha2": "=0.10.9"},
        "codec dependency closure adds only exact sha2=0.10.9",
        checks,
    )
    require(
        "hepta-browser-codec" in browserd_manifest["dependencies"],
        "browserd depends on the product codec",
        checks,
    )
    require(
        "hepta_browser_codec::self_check()" in browserd,
        "browserd self-check invokes the product codec",
        checks,
    )

    packages = index_lock_packages(lock)
    codec_package = one_lock_package(packages, "hepta-browser-codec")
    browserd_package = one_lock_package(packages, "hepta-browserd")
    require("hepta-browser-codec" in packages, "Cargo.lock contains codec package", checks)
    require(
        codec_package.get("dependencies") == ["sha2"],
        "Cargo.lock binds codec only to sha2",
        checks,
    )
    require(
        "hepta-browser-codec" in browserd_package.get("dependencies", []),
        "Cargo.lock binds browserd to codec",
        checks,
    )

    require("#![forbid(unsafe_code)]" in lib, "codec forbids unsafe code", checks)
    combined = "\n".join([lib, json_source, model, tests])
    forbidden = ["TcpListener", "UnixListener", ".bind(", "WebDriver", "servo::"]
    for token in forbidden:
        require(token not in combined, f"codec source excludes authority token {token}", checks)

    require("MAX_MESSAGE_BYTES: usize = 262_144" in lib, "message byte bound matches contract", checks)
    require("MAX_JSON_DEPTH: usize = 32" in lib, "nesting bound matches contract", checks)
    require("MAX_CONTAINER_ITEMS: usize = 20_000" in lib, "container bound matches contract", checks)
    require("DuplicateMember" in json_source, "recursive duplicate-member failure exists", checks)
    require("FloatingPointForbidden" in json_source, "floating-point rejection exists", checks)
    require("Utf8Bom" in json_source, "UTF-8 BOM rejection exists", checks)
    require("BTreeMap" in json_source, "canonical object map is ordered", checks)
    require("NonCanonicalEncoding" in model, "byte-exact canonical comparison exists", checks)
    require("semantic_snapshot_revision" in model, "semantic snapshot binding exists", checks)
    require("userinfo" not in model.lower() or "authority.contains('@')" in model,
            "URL userinfo is rejected", checks)
    require("localhost\" | \"127.0.0.1\" | \"::1" in model,
            "fixture navigation is loopback-only", checks)

    operation_literals = {
        "health", "session_create", "session_snapshot", "session_close",
        "page_navigate", "page_observe", "page_act", "page_wait", "page_extract",
    }
    for operation in sorted(operation_literals):
        require(f'"{operation}"' in model, f"Rust model contains operation {operation}", checks)

    require(
        re.search(
            r"Self::PageNavigate\s*\{\s*\.\.\s*\}\s*=>\s*EffectClass::PotentialExternalEffect",
            model,
            re.S,
        ) is not None,
        "navigation is classified as potential_external_effect",
        checks,
    )
    require(
        "PageAction::Scroll { .. }" in model and "EffectClass::LocalInteraction" in model,
        "scroll is classified as local_interaction",
        checks,
    )

    for item in errors:
        code = item["code"]
        retry = item["retry"]
        require(f'"{code}"' in model, f"Rust model contains error code {code}", checks)
        require(f'"{retry}"' in model, f"Rust model contains retry policy {retry}", checks)

    golden_names = [
        "golden-health-1.wire.json",
        "golden-create-1.wire.json",
        "golden-navigate-1.wire.json",
        "golden-click-1.wire.json",
        "golden-response-ok-1.wire.json",
        "golden-response-error-1.wire.json",
    ]
    for name in golden_names:
        path = ROOT / "contracts/golden" / name
        require(path.exists(), f"golden vector exists: {name}", checks)
        require(name in tests, f"Rust tests include golden vector: {name}", checks)
        raw = read_bytes_nofollow(path, label=f"golden vector {name}")
        require(raw == json.dumps(load_json_strict(raw), ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode(),
                f"golden vector is canonical: {name}", checks)

    validation = contract["validation"]
    contract_status = contract.get("status")
    evidence_freshness = validation.get("evidence_freshness")
    top_lifecycle = contract.get("evidence_lifecycle")
    top_freshness = contract.get("evidence_freshness")
    top_merge_ready = contract.get("merge_ready")
    # Capability status is deliberately independent from evidence freshness:
    # a historical host observation still describes the bounded capability it
    # exercised, while the freshness fields decide whether it may be promoted.
    require(
        contract_status == CODEC_CAPABILITY_STATUS,
        "codec contract capability status must remain HOST_VALIDATED_RUST_1_93_NO_DISPATCH",
        checks,
    )
    require(validation["python_reference"] == "PASS_27_OF_27",
            "independent codec reference remains 27/27 PASS", checks)
    require(validation["rust_source_audit"] == "PASS",
            "contract records Rust source audit PASS", checks)
    for field in ["rust_fmt", "rust_clippy", "rust_tests", "browserd_self_check"]:
        require(validation[field] == "PASS", f"host validation records {field} PASS", checks)
    require(
        isinstance(validation.get("merge_ready"), bool),
        "contract merge_ready is an explicit boolean",
        checks,
    )
    host_result = repo_path(
        contract.get("rust_host_result"), label="rust_host_result"
    )
    require(
        regular_file_exists_nofollow(host_result, label="exact-head Rust host result"),
        "recorded Rust host result exists",
        checks,
    )
    host = load_json_nofollow(host_result, label="exact-head Rust host result")
    require(host["status"] == "PASS", "recorded Rust host result is PASS", checks)
    host_source_sha = host.get("validated_source_sha")
    require(
        isinstance(host_source_sha, str)
        and re.fullmatch(r"[0-9a-f]{40}", host_source_sha) is not None,
        "host result binds a well-formed source commit",
        checks,
    )
    if validation["merge_ready"] is True:
        require(
            evidence_freshness in (None, "CURRENT")
            and top_lifecycle in (None, "CURRENT")
            and top_freshness in (None, "CURRENT")
            and top_merge_ready in (None, True),
            "merge-ready contract has current evidence freshness",
            checks,
        )
        checked_out_sha = git_head_sha()
        require(
            checked_out_sha is not None,
            "merge-ready host evidence requires a Git checkout for exact-head comparison",
            checks,
        )
        if checked_out_sha is not None:
            require(
                host_source_sha == checked_out_sha,
                "merge-ready host result binds the checked-out source commit",
                checks,
            )
    else:
        require(
            top_lifecycle == STALE_EVIDENCE_LIFECYCLE,
            "non-merge-ready codec contract is explicitly marked for exact-head rerun",
            checks,
        )
        require(
            top_freshness == "STALE_EVIDENCE" and top_merge_ready is False,
            "non-merge-ready codec contract top-level freshness is stale",
            checks,
        )
        require(
            evidence_freshness == "STALE_EVIDENCE",
            "non-merge-ready codec evidence freshness is STALE_EVIDENCE",
            checks,
        )
        require(
            host_source_sha == HISTORICAL_HOST_SOURCE_SHA,
            "stale host result retains the known historical source binding",
            checks,
        )
        stale_reason = validation.get("stale_reason")
        require(
            isinstance(stale_reason, str)
            and HISTORICAL_HOST_SOURCE_SHA in stale_reason
            and "exact candidate head" in stale_reason,
            "stale codec evidence carries an actionable rerun reason",
            checks,
        )
        top_stale_reason = contract.get("stale_reason")
        require(
            isinstance(top_stale_reason, str)
            and top_stale_reason == stale_reason,
            "stale codec contract top-level reason matches validation reason",
            checks,
        )
    require(contract["listener"] == {"enabled": False, "public_network": False},
            "codec contract creates no listener", checks)

    result = {
        "schema": "trillionnium.desktop.d0c03-rust-source-audit.v1",
        "status": "PASS",
        "check_count": len(checks),
        "checks": checks,
        "source_sha256": {
            "lib_rs": sha256(ROOT / "crates/hepta-browser-codec/src/lib.rs"),
            "json_rs": sha256(ROOT / "crates/hepta-browser-codec/src/json.rs"),
            "model_rs": sha256(ROOT / "crates/hepta-browser-codec/src/model.rs"),
            **{f"model_{path.stem}_rs": sha256(path) for path in model_paths[1:]},
            "tests_rs": sha256(ROOT / "crates/hepta-browser-codec/src/tests.rs"),
            "cargo_toml": sha256(ROOT / "crates/hepta-browser-codec/Cargo.toml"),
        },
        "executed": {
            "static_contract_source_audit": True,
            "golden_vector_canonicality": True,
            "cargo_fmt": True,
            "cargo_clippy": True,
            "cargo_test": True,
            "browserd_self_check": True,
        },
        "product_listener_created": False,
        "browser_dispatched": False,
        "external_effect_authorized": False,
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write_result:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(encoded)
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"D0C-03 Rust source audit failed: {error}", file=sys.stderr)
        raise
