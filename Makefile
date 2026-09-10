.PHONY: validate truth fmt check-rust clippy test self-check check

validate:
	python3 tools/validate_repository.py
	python3 tools/validate_contract_foundation.py
	python3 -m unittest discover -s tests -p 'test_contract_foundation.py'

truth:
	python3 tools/validate_project_truth.py
	python3 -m unittest discover -s tests -p 'test_project_truth_status_documents.py'

fmt:
	cargo fmt --all --check

check-rust:
	cargo check --workspace --all-targets --locked

clippy:
	cargo clippy --workspace --all-targets --locked -- -D warnings

test:
	cargo test --workspace --all-targets --locked

self-check:
	cargo run --locked -p hepta-browserd -- --self-check

check: validate truth fmt check-rust clippy test self-check
