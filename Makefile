.PHONY: validate truth custody late-stage fmt check-rust clippy test-python test self-check check

validate:
	python3 tools/validate_repository.py
	python3 -m unittest tests.test_validate_project_truth -v

truth:
	python3 tools/validate_project_truth.py

custody:
	python3 tools/verify_systemd_socket_custody.py
	python3 tools/validate_agent_port_path_custody.py

late-stage:
	python3 tools/validate_late_stage_source_packages.py

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

check: validate truth custody late-stage fmt check-rust clippy test self-check
