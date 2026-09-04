.PHONY: validate truth module-docs component-docs d3-runtime-evidence custody late-stage fmt check-rust clippy test-python test self-check check

validate:
	python3 tools/validate_repository.py
	python3 tools/validate_module_documentation.py
	python3 tools/validate_component_documentation.py
	python3 -m unittest tests.test_validate_project_truth -v
	python3 -m unittest tests.test_component_documentation -v
	python3 -m unittest tests.test_validator_loader_stability -v

truth:
	python3 tools/validate_project_truth.py

module-docs:
	python3 tools/validate_module_documentation.py

component-docs:
	python3 tools/validate_component_documentation.py

d3-runtime-evidence:
	python3 tools/verify_d3_integrated_runtime_evidence.py --self-test
	python3 -m unittest tests.d3.test_d3_integrated_runtime_evidence -v

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

check: validate truth module-docs component-docs d3-runtime-evidence custody late-stage fmt check-rust clippy test self-check
