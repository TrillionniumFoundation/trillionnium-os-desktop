.PHONY: validate fmt clippy test self-check check

validate:
	python3 tools/validate_repository.py

fmt:
	cargo fmt --all --check

clippy:
	cargo clippy --workspace --all-targets -- -D warnings

test:
	cargo test --workspace

self-check:
	cargo run -p hepta-browserd -- --self-check

check: validate fmt clippy test self-check
