#!/usr/bin/env python3
"""Secured entry point for the D0C-03 codec source/evidence audit.

The historical deterministic audit is retained as an import-only compatibility
module. This entry point replaces all evidence I/O and JSON serialization with
strict, pinned-directory-descriptor helpers and runs structural contract checks
before delegating to the historical projection.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Direct script execution places tools/ rather than the repository root first.
# Prepend the reviewed repository root so `from tools ...` cannot resolve an
# unrelated ambient namespace package.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from tools import browser_codec_reference_legacy_audit as _legacy
    from tools.browser_codec_reference_contract import (
        validate_codec_contract_data,
        validate_root as validate_structural_contract,
    )
    from tools.browser_codec_reference_security import (
        ROOT,
        STRICT_JSON,
        _open_regular,
        git_blob_sha1,
        load_json_nofollow,
        load_json_strict,
        open_regular_beneath,
        read_bytes_beneath,
        read_bytes_nofollow,
        read_text_nofollow,
        regular_file_exists_nofollow,
        repo_path,
        sha256,
        strict_json_dumps,
    )
except ModuleNotFoundError:
    import browser_codec_reference_legacy_audit as _legacy  # type: ignore[no-redef]
    from browser_codec_reference_contract import (  # type: ignore[no-redef]
        validate_codec_contract_data,
        validate_root as validate_structural_contract,
    )
    from browser_codec_reference_security import (  # type: ignore[no-redef]
        ROOT,
        STRICT_JSON,
        _open_regular,
        git_blob_sha1,
        load_json_nofollow,
        load_json_strict,
        open_regular_beneath,
        read_bytes_beneath,
        read_bytes_nofollow,
        read_text_nofollow,
        regular_file_exists_nofollow,
        repo_path,
        sha256,
        strict_json_dumps,
    )

# Python resolves module globals at call time. Patch every legacy input/output
# edge before its main function is invoked; the old lstat-then-open helper and
# permissive JSON module are therefore unreachable through this entry point.
_legacy.ROOT = ROOT
_legacy.json = STRICT_JSON
_legacy._open_regular = _open_regular
_legacy.load_json_strict = load_json_strict
_legacy.load_json_nofollow = load_json_nofollow
_legacy.read_text_nofollow = read_text_nofollow
_legacy.read_bytes_nofollow = read_bytes_nofollow
_legacy.regular_file_exists_nofollow = regular_file_exists_nofollow
_legacy.repo_path = repo_path
_legacy.sha256 = sha256
_legacy.git_blob_sha1 = git_blob_sha1

# Preserve helpers intentionally consumed by regression tests/workflow snippets.
index_lock_packages = _legacy.index_lock_packages
one_lock_package = _legacy.one_lock_package
git_head_sha = _legacy.git_head_sha
HISTORICAL_HOST_SOURCE_SHA = _legacy.HISTORICAL_HOST_SOURCE_SHA
CODEC_CAPABILITY_STATUS = _legacy.CODEC_CAPABILITY_STATUS
STALE_EVIDENCE_LIFECYCLE = _legacy.STALE_EVIDENCE_LIFECYCLE


def main() -> int:
    structural_errors = validate_structural_contract(ROOT)
    if structural_errors:
        for error in structural_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            "browser codec structural validation failed before source audit",
            file=sys.stderr,
        )
        return 1
    return _legacy.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"D0C-03 Rust source audit failed: {error}", file=sys.stderr)
        raise
