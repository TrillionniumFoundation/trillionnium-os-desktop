#!/usr/bin/env bash
set -euo pipefail

cat \
  .bootstrap-d0c-v2/part-00 \
  .bootstrap-d0c-v2/part-01 \
  .bootstrap-d0c-v2/part-02 \
  .bootstrap-d0c-v2/part-03a \
  .bootstrap-d0c-v2/part-03b \
  .bootstrap-d0c-v2/part-04 \
  .bootstrap-d0c-v2/part-05 \
  > /tmp/d0c-materialize.tar.gz.b64

test "$(wc -c < /tmp/d0c-materialize.tar.gz.b64)" -eq 32428
base64 -d /tmp/d0c-materialize.tar.gz.b64 > /tmp/d0c-materialize.tar.gz
echo "7e5ebc89218dbc2e262dad1610633bcab992151ff335c0e46a763e64d5c7749d  /tmp/d0c-materialize.tar.gz" | sha256sum -c -
rm -rf /tmp/d0c-bundle
mkdir -p /tmp/d0c-bundle
tar -xzf /tmp/d0c-materialize.tar.gz -C /tmp/d0c-bundle

python3 /tmp/d0c-bundle/apply_to_checkout.py "$GITHUB_WORKSPACE" \
  --apply --allow-dirty \
  --report /tmp/d0c-overlay-application.json

python3 - <<'PY'
from pathlib import Path

codec = Path("crates/hepta-browser-codec/src/lib.rs")
text = codec.read_text()
old = """    if let Some(port) = port {\n        if port == 0 {\n            return Err(CodecError::InvalidUrl);\n        }\n    }\n"""
new = """    if port == Some(0) {\n        return Err(CodecError::InvalidUrl);\n    }\n"""
if old not in text:
    raise SystemExit("reviewed zero-port block was not found exactly")
codec.write_text(text.replace(old, new, 1))

browserd = Path("apps/hepta-browserd/src/lib.rs")
text = browserd.read_text()
old_stage = "D0R_D0C04_RUST_SOURCE_UNEXECUTED"
if old_stage not in text:
    raise SystemExit("expected browserd source-stage marker was not found exactly")
browserd.write_text(text.replace(old_stage, "D0R_D0C04_RUST_HOST_VALIDATED", 1))

markdown = Path("docs/architecture/RUST_BROWSER_CODEC_AND_AGENT_PORT.md")
value = markdown.read_text()
markdown.write_text("\n".join(line.rstrip() for line in value.splitlines()) + "\n")

# Canonical wire vectors are byte contracts and must have no trailing newline.
for path in Path("contracts/golden").glob("*.wire.json"):
    path.write_bytes(path.read_bytes().rstrip(b"\r\n"))
PY

rustup toolchain install 1.93.0 --profile minimal --component rustfmt,clippy
rustup default 1.93.0
rustc --version --verbose
cargo --version --verbose

cargo generate-lockfile
cargo fmt --all
cargo fmt --all --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
cargo test --locked -p hepta-browser-codec
cargo test --locked -p hepta-agent-port
cargo run --locked -p hepta-browserd -- --self-check | tee /tmp/browserd-self-check.json

python3 /tmp/d0c-bundle/toolchain/tools/verify_cargo_lock_allowlist.py \
  --lock Cargo.lock \
  --baseline /tmp/d0c-bundle/toolchain/manifests/cargo-external-allowlist-d0c02-baseline.json \
  --write-candidate manifests/cargo-external-allowlist.d0c-candidate.json

rm -rf .bootstrap-d0c .bootstrap-d0c-v2
rm -f .github/workflows/materialize-d0c-rust-product.yml
rm -f .github/workflows/materialize-d0c-rust-product-v2.yml
rm -f .github/workflows/materialize-d0c-rust-product-final.yml
rm -f tools/materialize_d0c_rust_product.sh

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A
git diff --cached --check
git commit -m "feat: implement and host-test D0C-03/D0C-04 Rust product path"
git push origin HEAD:codex/d0c-rust-product-v1
