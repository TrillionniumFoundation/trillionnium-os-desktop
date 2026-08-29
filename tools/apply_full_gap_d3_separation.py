#!/usr/bin/env python3
"""Compose D1 qualification fixtures with D3 product/fixture separation."""

from __future__ import annotations

import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
D3 = "bf6bba2ea1c49b36e11754bf27dc0c56e3da3bd1"
D1 = "95fe921c833dea9560d4b1492781795c589d6140"


def git_show(commit: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT, text=True
    )


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1))


# Product daemon and D0 fixture come from the reviewed separation candidate.
for path in (
    "apps/hepta-agent-portd/src/main.rs",
    "apps/hepta-agent-portd/src/bin/hepta-agent-port-fixture.rs",
    "contracts/agent-port-custody.v1.json",
    "tools/verify_systemd_socket_custody.py",
):
    write(path, git_show(D3, path))

# Preserve the previously-qualified one-connection handler, but move it behind
# the explicit fixture feature and out of the product executable path.
write(
    "apps/hepta-agent-portd/src/bin/hepta-agent-port-qualificationd.rs",
    git_show(D1, "apps/hepta-agent-portd/src/main.rs").replace(
        "//! One-connection systemd socket-activation service for the local AgentPort.",
        "//! Qualification-only one-connection AgentPort handler.",
        1,
    ).replace(
        "//! The binary never binds or listens. In product mode it duplicates the",
        "//! This feature-gated binary never binds or listens. It duplicates the",
        1,
    ).replace(
        "eprintln!(\"hepta-agent-portd: {error}\")",
        "eprintln!(\"hepta-agent-port-qualificationd: {error}\")",
        1,
    ),
)

write(
    "apps/hepta-agent-portd/Cargo.toml",
    '''[package]
name = "hepta-agent-portd"
version.workspace = true
edition.workspace = true
rust-version.workspace = true
license.workspace = true
repository.workspace = true
publish = false
default-run = "hepta-agent-portd"

[features]
default = []
fixture = ["dep:hepta-agent-port"]

[dependencies]
hepta-agent-port = { path = "../../crates/hepta-agent-port", optional = true }
hepta-agent-transport = { path = "../../crates/hepta-agent-transport" }
hepta-browser-codec = { path = "../../crates/hepta-browser-codec" }
hepta-peer-attestation = { path = "../../crates/hepta-peer-attestation" }
libc = "=0.2.186"

[[bin]]
name = "hepta-agent-portd"
path = "src/main.rs"

[[bin]]
name = "hepta-agent-port-fixture"
path = "src/bin/hepta-agent-port-fixture.rs"
required-features = ["fixture"]

[[bin]]
name = "hepta-agent-port-qualificationd"
path = "src/bin/hepta-agent-port-qualificationd.rs"
required-features = ["fixture"]

[[bin]]
name = "hepta-agent-d1-fixture"
path = "src/bin/hepta-agent-d1-fixture.rs"
required-features = ["fixture"]
''',
)

# D1 uses the feature-gated qualification handler, never the fail-closed product
# daemon, while keeping the production package graph unchanged.
replace_once(
    "tests/qemu/run-d1-pipeline.sh",
    'agent_portd="$workspace/target/release/hepta-agent-portd"\n',
    '# D1 is a qualification image: inject only the explicit feature-gated handler.\n'
    'agent_portd="$workspace/target/release/hepta-agent-port-qualificationd"\n',
)

# Deepen the static custody audit to cover every non-product binary.
replace_once(
    "tools/verify_systemd_socket_custody.py",
    'FIXTURE = ROOT / "apps/hepta-agent-portd/src/bin/hepta-agent-port-fixture.rs"\n',
    'FIXTURE = ROOT / "apps/hepta-agent-portd/src/bin/hepta-agent-port-fixture.rs"\n'
    'QUALIFICATION = ROOT / "apps/hepta-agent-portd/src/bin/hepta-agent-port-qualificationd.rs"\n'
    'D1_FIXTURE = ROOT / "apps/hepta-agent-portd/src/bin/hepta-agent-d1-fixture.rs"\n',
)
replace_once(
    "tools/verify_systemd_socket_custody.py",
    '    fixture = read(FIXTURE)\n    attestor = read(ATTESTOR)\n',
    '    fixture = read(FIXTURE)\n'
    '    qualification = read(QUALIFICATION)\n'
    '    d1_fixture = read(D1_FIXTURE)\n'
    '    attestor = read(ATTESTOR)\n',
)
replace_once(
    "tools/verify_systemd_socket_custody.py",
    '    for forbidden in ("UnixListener", "TcpListener", ".bind(", "listen("):\n'
    '        require(forbidden not in fixture, f"fixture contains listener primitive {forbidden!r}")\n\n'
    '    features = cargo.get("features", {})\n',
    '    for required in ("D0FixtureHandler", "serve_one", "qualification-only"):\n'
    '        require(required in qualification, f"qualification handler misses {required!r}")\n'
    '    require("hepta_browser_codec" in d1_fixture, "D1 client fixture lost typed codec binding")\n'
    '    for source_name, source in (("fixture", fixture), ("qualification", qualification), ("D1 fixture", d1_fixture)):\n'
    '        for forbidden in ("UnixListener", "TcpListener", ".bind(", "listen("):\n'
    '            require(forbidden not in source, f"{source_name} contains listener primitive {forbidden!r}")\n\n'
    '    features = cargo.get("features", {})\n',
)
replace_once(
    "tools/verify_systemd_socket_custody.py",
    '    fixture_bin = bins.get("hepta-agent-port-fixture", {})\n'
    '    require(product.get("path") == "src/main.rs", "product bin path changed")\n'
    '    require("required-features" not in product, "product binary unexpectedly feature-gated")\n'
    '    require(fixture_bin.get("path") == "src/bin/hepta-agent-port-fixture.rs", "fixture bin path changed")\n'
    '    require(fixture_bin.get("required-features") == ["fixture"], "fixture bin is not explicitly feature-gated")\n',
    '    fixture_bin = bins.get("hepta-agent-port-fixture", {})\n'
    '    qualification_bin = bins.get("hepta-agent-port-qualificationd", {})\n'
    '    d1_fixture_bin = bins.get("hepta-agent-d1-fixture", {})\n'
    '    require(product.get("path") == "src/main.rs", "product bin path changed")\n'
    '    require("required-features" not in product, "product binary unexpectedly feature-gated")\n'
    '    require(fixture_bin.get("path") == "src/bin/hepta-agent-port-fixture.rs", "fixture bin path changed")\n'
    '    require(fixture_bin.get("required-features") == ["fixture"], "fixture bin is not explicitly feature-gated")\n'
    '    require(qualification_bin.get("path") == "src/bin/hepta-agent-port-qualificationd.rs", "qualification bin path changed")\n'
    '    require(qualification_bin.get("required-features") == ["fixture"], "qualification handler is not feature-gated")\n'
    '    require(d1_fixture_bin.get("path") == "src/bin/hepta-agent-d1-fixture.rs", "D1 fixture path changed")\n'
    '    require(d1_fixture_bin.get("required-features") == ["fixture"], "D1 fixture is not feature-gated")\n',
)
replace_once(
    "tools/verify_systemd_socket_custody.py",
    '    require("hepta-agent-port-fixture" not in install, "production package installs fixture binary")\n',
    '    for forbidden_binary in ("hepta-agent-port-fixture", "hepta-agent-port-qualificationd", "hepta-agent-d1-fixture"):\n'
    '        require(forbidden_binary not in install, f"production package installs {forbidden_binary}")\n',
)

contract_path = ROOT / "contracts/agent-port-custody.v1.json"
contract = json.loads(contract_path.read_text())
contract["fixture_separation"]["qualification_binaries"] = [
    "hepta-agent-port-fixture",
    "hepta-agent-port-qualificationd",
    "hepta-agent-d1-fixture",
]
contract["fixture_separation"]["all_qualification_binaries_feature_gated"] = True
contract["fixture_separation"]["production_installation_excludes_all_qualification_binaries"] = True
contract_path.write_text(json.dumps(contract, indent=2) + "\n")

write(
    "docs/architecture/AGENT_PORT_PRODUCT_QUALIFICATION_SEPARATION.md",
    '''# AgentPort product and qualification separation

The default `hepta-agent-portd` binary contains no `D0FixtureHandler` and fails
closed before request decoding until D3 connects a real BrowserActor.

Three non-product binaries are available only through the non-default `fixture`
feature:

- `hepta-agent-port-fixture`: bounded D0 source/self-check fixture;
- `hepta-agent-port-qualificationd`: one-connection D1/QEMU handler;
- `hepta-agent-d1-fixture`: D1 client corpus.

None is present in the Debian production installation map. The D1 image builder
may inject the qualification handler into its explicitly test-only image. This
does not enable AgentPort in the production profile and grants no external
effect authority.
''',
)
