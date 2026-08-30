.PHONY: validate truth fmt check-rust clippy test-python test self-check check

validate:
	python3 tools/validate_repository.py
	python3 -m unittest tests.test_validate_project_truth -v

truth:
	python3 tools/validate_project_truth.py

fmt:
	cargo fmt --all --check

check-rust:
	cargo check --workspace --all-targets --locked

clippy:
	cargo clippy --workspace --all-targets --locked -- -D warnings

test-python:
	python3 -m unittest discover -s tests -t . -p 'test_*.py'

test: test-python
	cargo test --workspace --all-targets --locked

self-check:
	cargo run --locked -p hepta-browserd -- --self-check

check: validate truth fmt check-rust clippy test self-check
