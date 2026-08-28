# Contributing

1. Read the active plan and applicable ADRs.
2. Keep changes inside the desktop product graph; do not add Android/mobile
   path dependencies or direct shell/ADB authority.
3. Update schemas, golden vectors, Rust types, tests, and documentation together
   when changing a contract.
4. Run `python3 tools/validate_repository.py` and all Rust checks.
5. Preserve explicit non-claims; do not promote source-only work to a boot,
   hardware, security, or release statement.
6. Use focused commits and pull requests. Security, origin, sandbox, capability,
   update, and signing changes require designated owner review.
