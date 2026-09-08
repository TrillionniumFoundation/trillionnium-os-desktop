"""Repository adapter for integrated status plus non-promoting source inventory."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_TOOLS = Path(__file__).resolve().parent
_STATUS = _load("structured_status_base", _TOOLS / "structured_status.py")
_SOURCE = _load("source_state_model", _TOOLS / "source_state_model.py")

STATUS_REGISTRY_PATH = _STATUS.STATUS_REGISTRY_PATH
STATUS_REGISTRY_SCHEMA = _STATUS.STATUS_REGISTRY_SCHEMA
INTEGRATED_STATE_SCHEMA = _STATUS.INTEGRATED_STATE_SCHEMA
EXPECTED_WORKSPACE_MEMBERS = _STATUS.EXPECTED_WORKSPACE_MEMBERS
status_projection_errors = _STATUS.status_projection_errors
render_integrated_state = _STATUS.render_integrated_state
validate_integrated_state_record = _STATUS.validate_integrated_state_record
SOURCE_STATE_PATH = _SOURCE.SOURCE_STATE_PATH
SOURCE_STATE_SCHEMA = _SOURCE.SOURCE_STATE_SCHEMA
validate_source_state_record = _SOURCE.validate_record


def validate_repository(root: Path) -> list[str]:
    """Validate both truth domains without equating source presence to integration."""

    errors = _STATUS.validate_repository(root)
    legacy_mismatch = "integrated_state workspace_members differ from Cargo.toml"
    errors = [error for error in errors if error != legacy_mismatch]
    errors.extend(_SOURCE.validate_repository(root))
    return errors
