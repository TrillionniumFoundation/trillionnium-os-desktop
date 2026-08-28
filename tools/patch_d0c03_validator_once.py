#!/usr/bin/env python3
"""One-shot fail-closed repository-validator upgrade for D0C-03.

This file is removed by the promotion workflow after it has produced and
validated the tested source commit.
"""
from __future__ import annotations

from pathlib import Path

PATH = Path(__file__).resolve().with_name("validate_repository.py")
text = PATH.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one validator marker, found {count}: {old!r}")
    text = text.replace(old, new, 1)


replace_once(
    '    "crates/hepta-agent-transport",\n    "crates/trillionnium-contract-core",',
    '    "crates/hepta-agent-transport",\n    "crates/hepta-browser-codec",\n    "crates/trillionnium-contract-core",',
)
replace_once(
    '    "contracts/agent-transport.v1.json",\n',
    '    "contracts/agent-transport.v1.json",\n'
    '    "contracts/browser-codec.v1.json",\n'
    '    "contracts/browser-wire.v1.schema.json",\n'
    '    "contracts/browser-response.v1.schema.json",\n',
)
replace_once(
    '    "crates/hepta-agent-transport/src/lib.rs",\n',
    '    "crates/hepta-agent-transport/src/lib.rs",\n'
    '    "crates/hepta-browser-codec/Cargo.toml",\n'
    '    "crates/hepta-browser-codec/src/lib.rs",\n',
)
replace_once(
    '    "docs/architecture/AUTHENTICATED_AGENT_TRANSPORT.md",\n',
    '    "docs/architecture/AUTHENTICATED_AGENT_TRANSPORT.md",\n'
    '    "docs/architecture/CANONICAL_BROWSER_CODEC.md",\n'
    '    "docs/architecture/RUST_BROWSER_CODEC.md",\n',
)
replace_once(
    '    "docs/evidence/2026-08-28-d0c02-authenticated-uds.md",\n',
    '    "docs/evidence/2026-08-28-d0c02-authenticated-uds.md",\n'
    '    "docs/evidence/2026-08-28-d0c03-rust-product-codec-source.md",\n'
    '    "tools/validate_rust_browser_codec.py",\n',
)
replace_once(
    '    if len(schema_ids) != 4:\n        fail(f"expected 4 JSON schemas, found {len(schema_ids)}")',
    '    if len(schema_ids) != 6:\n        fail(f"expected 6 JSON schemas, found {len(schema_ids)}")',
)

PATH.write_text(text, encoding="utf-8")
print("D0C-03 repository-validator upgrade applied")
