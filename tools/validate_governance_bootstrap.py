#!/usr/bin/env python3
"""Run the governance validator during the pre-promotion bootstrap phase."""
from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("validate_governance_integrity.py")
spec = importlib.util.spec_from_file_location("governance_integrity", MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("could not load governance integrity validator")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
# D0A/D1/D2I/D3 permanent workflows become unconditional as each candidate is
# replayed on the governed main. During bootstrap, enforce that property for the
# new governance workflow while still auditing every workflow for write
# authority, mutable actions, and ambiguous check identities.
module.PROMOTION_WORKFLOWS = {"governance-integrity.yml"}
raise SystemExit(module.main())
