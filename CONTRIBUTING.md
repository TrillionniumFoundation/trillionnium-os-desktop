# Contributing

1. Read `manifests/project-state.v1.json`, `manifests/gates.v1.json`, the active
   plan, and applicable ADR/security documents before changing code.
2. Work in one isolated work-package branch and pull request. Revalidate the
   exact base SHA before every promotion step.
3. Keep changes inside the desktop product graph. Do not add Android/mobile,
   ADB, root-linux, or direct-shell dependencies or authority.
4. Update implementation and regression tests together. Update schemas/contracts,
   golden vectors, Rust types, machine truth, documentation and claim ceilings
   when the corresponding behavior, interface, inventory or claim changes.
   Internal refactors do not require no-op edits to every artifact. Preserve
   historical evidence; rerun invalidated gates instead of relabelling it.
5. Record PR head SHA, base SHA, tested merge SHA, workflow/input identities,
   and bounded output digests. A candidate pass is not an integrated-main pass.
6. Run:

   ```bash
   python3 tools/validate_module_documentation.py
   python3 tools/validate_s08_servo_runtime.py
   python3 tools/validate_repository.py
   python3 tools/validate_project_truth.py
   python3 -m unittest discover -s tests -v
   python3 -m unittest discover -s tests/d1 -v
   python3 -m unittest discover -s tests/transport -v
   cargo fmt --all --check
   cargo check --workspace --all-targets --locked
   cargo clippy --workspace --all-targets --locked -- -D warnings
   cargo test --workspace --all-targets --locked
   cargo test --workspace --doc --locked
   cargo run --locked -p hepta-browserd -- --self-check
   ```

7. Preserve explicit non-claims. Source-only work must not be promoted to
   headed runtime, QEMU, hardware, signing, update, or release truth.
8. Security, identity, origin, sandbox, capability, egress, receipt, update,
   signing, and release changes require independent designated review.
9. Authors must not self-certify repository-setting or release gates and must
   not merge their own PR.
10. Use focused commits. Generated evidence must be reproducible, bounded,
    privacy-reviewed, and linked to exact inputs.

Repository validation inspects product source, including newly added untracked
source files. It prunes only known local/generated trees such as `.git`, `target`,
root `build`/`dist`/`out`, caches and `evidence/local`; keep temporary evidence
there. JSON inputs are bounded, strictly decoded and read without following
symlinked parents. A successful source validator is separate from the full
Python/Rust tests and image qualification workflows.
