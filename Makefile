.PHONY: validate truth fmt check-rust check-rust-features clippy clippy-features test test-features self-check check

validate:
	python3 tools/validate_module_documentation.py
	python3 tools/validate_repository.py
	python3 tools/validate_contract_foundation.py
	python3 tools/validate_s04_transport_custody.py
	python3 -m unittest discover -s tests -p 'test_contract_foundation.py'
	python3 -m unittest discover -s tests -p 'test_s04_transport_custody.py'
	python3 -m unittest discover -s tests -p 'test_module_documentation.py'

truth:
	python3 tools/validate_project_truth.py
	python3 -m unittest discover -s tests -p 'test_project_truth_status_documents.py'

fmt:
	cargo fmt --all --check

check-rust:
	cargo check --workspace --all-targets --locked

check-rust-features:
	cargo check --workspace --all-targets --all-features --locked

clippy:
	cargo clippy --workspace --all-targets --locked -- -D warnings

clippy-features:
	cargo clippy --workspace --all-targets --all-features --locked -- -D warnings

test:
	cargo test --workspace --all-targets --locked

test-features:
	cargo test --workspace --all-targets --all-features --locked

self-check:
	cargo run --locked -p hepta-browserd -- --self-check
	cargo run --locked -p hepta-agent-portd --bin hepta-agent-portd -- --self-check
	cargo run --locked -p hepta-agent-portd --features fixture --bin hepta-agent-port-fixture -- --self-check

check: validate truth fmt check-rust check-rust-features clippy clippy-features test test-features self-check
