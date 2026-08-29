#!/usr/bin/env python3
from pathlib import Path

member = '  "crates/hepta-workspace-composition",\n'

cargo = Path("Cargo.toml")
text = cargo.read_text(encoding="utf-8")
anchor = '  "crates/hepta-session-core",\n'
if text.count(anchor) != 2:
    raise SystemExit(f"expected two workspace anchors, found {text.count(anchor)}")
text = text.replace(anchor, anchor + member)
cargo.write_text(text, encoding="utf-8")

validator = Path("tools/validate_repository.py")
text = validator.read_text(encoding="utf-8")
anchor = '    "crates/hepta-session-core",\n'
if text.count(anchor) != 1:
    raise SystemExit(f"expected one validator member anchor, found {text.count(anchor)}")
text = text.replace(anchor, anchor + '    "crates/hepta-workspace-composition",\n')
required_anchor = '    "tools/verify_systemd_socket_custody.py",\n'
if text.count(required_anchor) != 1:
    raise SystemExit("validator required-path anchor changed")
required = '''    "contracts/workspace-composition.v1.json",
    "crates/hepta-workspace-composition/Cargo.toml",
    "crates/hepta-workspace-composition/src/lib.rs",
    "crates/hepta-workspace-composition/src/model.rs",
    "crates/hepta-workspace-composition/src/tests.rs",
    "docs/architecture/TRUSTED_WORKSPACE_COMPOSITION.md",
'''
text = text.replace(required_anchor, required_anchor + required)
validator.write_text(text, encoding="utf-8")
