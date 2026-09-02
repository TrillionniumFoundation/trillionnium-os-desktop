#!/usr/bin/env python3
"""Ordinary-module facade for the D3 development-profile validator."""

from __future__ import annotations

import functools
import importlib.util
import inspect
from pathlib import Path
import sys
from typing import Any, Callable

_IMPL_PATH = Path(__file__).with_name("_validate_d3_development_profile_impl.py")
_SPEC = importlib.util.spec_from_file_location("_trillionnium_d3_profile_impl", _IMPL_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load D3 profile validator implementation: {_IMPL_PATH}")
_impl = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _impl
_SPEC.loader.exec_module(_impl)

_CANONICAL_ROOT = _impl.ROOT
_CANONICAL_ERRORS = _impl.ERRORS
_base_session = _impl.check_session_daemon
_base_fixture = _impl.check_fixture_and_journal


def _sync() -> None:
    root = globals().get("ROOT", _CANONICAL_ROOT)
    _impl.ROOT = root if isinstance(root, Path) else Path(root)
    errors = globals().get("ERRORS", _CANONICAL_ERRORS)
    if not isinstance(errors, list):
        raise RuntimeError("D3 validator ERRORS override must remain a list")
    _impl.ERRORS = errors


def _must(path: str, required: tuple[str, ...], forbidden: tuple[str, ...] = ()) -> str:
    text = _impl.read_text(path)
    for marker in required:
        if marker not in text:
            _impl.fail(f"{path} is missing {marker!r}")
    for marker in forbidden:
        if marker in text:
            _impl.fail(f"{path} contains forbidden marker {marker!r}")
    return text


def check_session_daemon() -> None:
    _sync()
    _base_session()
    runtime = _must(
        "crates/hepta-d3-development/src/sessiond/runtime.rs",
        (
            "pub(crate) struct AtomicFixtureRuntime",
            "fn dispatch_page_act",
            "caller_bound_target_revalidated",
            "snapshot.coordinates != *current",
            "snapshot.target != *target",
            "semantic_snapshot_mutation_epoch",
            "effect_applied_exactly_once",
            "servo_adapter_exercised",
        ),
    )
    if runtime.count("control.ensure_active()?;") < 3:
        _impl.fail("atomic PageAct runtime must check cancellation/deadline at dispatch and commit boundaries")
    _must(
        "crates/hepta-d3-development/src/bin/sessiond.rs",
        (
            "mod runtime;",
            '\\"atomic_semantic_page_act_wired\\":true',
            '\\"caller_bound_target_revalidation\\":true',
            '\\"servo_adapter_exercised\\":false',
        ),
    )
    _must(
        "crates/hepta-d3-development/src/sessiond/service.rs",
        (
            "type D3Actor = BrowserActor<AtomicFixtureRuntime>;",
            "BrowserActor::new(binding, AtomicFixtureRuntime::default())",
        ),
        (
            "actor: BrowserActor<DeterministicLocalRuntime>",
            "BrowserActor::new(binding, DeterministicLocalRuntime::default())",
        ),
    )


def check_fixture_and_journal() -> None:
    _sync()
    _base_fixture()
    fixture = _impl._joined_sources(
        (
            "crates/hepta-d3-development/src/bin/fixture.rs",
            "crates/hepta-d3-development/src/fixture/client.rs",
            "crates/hepta-d3-development/src/fixture/corpus.rs",
            "crates/hepta-d3-development/src/fixture/model.rs",
        )
    )
    for marker in (
        "d3-page-act-atomic",
        "element_reference_field",
        "atomic_semantic_resolver_exercised",
        "caller_bound_target_revalidated",
        "effect_applied_exactly_once",
        '\\"atomic_semantic_page_act_exercised\\":true',
        '\\"servo_adapter_exercised\\":false',
    ):
        if marker not in fixture:
            _impl.fail(f"D3 atomic TaskFlow corpus is missing {marker!r}")
    for marker in ("page_act_without_servo_resolver_rejected", "client::error(&acted"):
        if marker in fixture:
            _impl.fail(f"D3 atomic TaskFlow corpus retains obsolete path {marker!r}")


_impl.check_session_daemon = check_session_daemon
_impl.check_fixture_and_journal = check_fixture_and_journal


def _proxy(function: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(function)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        _sync()
        return function(*args, **kwargs)

    return invoke


for _name, _value in vars(_impl).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = (
        _proxy(_value)
        if inspect.isfunction(_value) and _value.__module__ == _impl.__name__
        else _value
    )

ROOT = _CANONICAL_ROOT
ERRORS = _CANONICAL_ERRORS

if __name__ == "__main__":
    raise SystemExit(main())
