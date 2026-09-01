#!/usr/bin/env python3
"""Load the reviewed D3 validator from fixed, non-executable source fragments."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

_PARTS = (
    "_validate_d3_development_profile_impl.000.part",
    "_validate_d3_development_profile_impl.001.part",
    "_validate_d3_development_profile_impl.002.part",
)
_EXPECTED_SHA256 = "72cac859b6517395da344e94a66fb6dd3849c4b794610c446d282569ec385787"


def _read_fragment(name: str) -> bytes:
    path = Path(__file__).with_name(name)
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"D3 validator fragment is not a regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


_source = b"".join(_read_fragment(name) for name in _PARTS)
_actual = hashlib.sha256(_source).hexdigest()
if _actual != _EXPECTED_SHA256:
    raise RuntimeError(
        f"D3 validator source digest mismatch: expected {_EXPECTED_SHA256}, observed {_actual}"
    )
exec(compile(_source, __file__, "exec"), globals())

# Extend the frozen validator without weakening its historical API or digest.
# The original functions still execute first; these wrappers add the new
# caller-bound atomic PageAct invariants while the fragment migration remains
# separately reviewable.
_fragment_check_session_daemon = check_session_daemon
_fragment_check_fixture_and_journal = check_fixture_and_journal


def check_session_daemon() -> None:
    _fragment_check_session_daemon()
    runtime = require_text(
        "crates/hepta-d3-development/src/sessiond/runtime.rs",
        "pub(crate) struct AtomicFixtureRuntime",
        "fn dispatch_page_act",
        "caller_bound_target_revalidated",
        "snapshot.coordinates != *current",
        "snapshot.target != *target",
        "semantic_snapshot_mutation_epoch",
        "effect_applied_exactly_once",
        "servo_adapter_exercised",
    )
    if runtime.count("control.ensure_active()?;") < 3:
        fail("atomic PageAct runtime must check cancellation/deadline at dispatch and commit boundaries")

    sessiond = read_text("crates/hepta-d3-development/src/bin/sessiond.rs")
    for marker in (
        'mod runtime;',
        '\\"atomic_semantic_page_act_wired\\":true',
        '\\"caller_bound_target_revalidation\\":true',
        '\\"servo_adapter_exercised\\":false',
    ):
        if marker not in sessiond:
            fail(f"D3 session daemon is missing atomic runtime marker {marker!r}")

    service = read_text("crates/hepta-d3-development/src/sessiond/service.rs")
    for marker in (
        "type D3Actor = BrowserActor<AtomicFixtureRuntime>;",
        "BrowserActor::new(binding, AtomicFixtureRuntime::default())",
    ):
        if marker not in service:
            fail(f"D3 service is missing atomic runtime wiring {marker!r}")
    for forbidden in (
        "actor: BrowserActor<DeterministicLocalRuntime>",
        "BrowserActor::new(binding, DeterministicLocalRuntime::default())",
    ):
        if forbidden in service:
            fail(f"D3 service still instantiates the non-atomic runtime: {forbidden}")


def check_fixture_and_journal() -> None:
    _fragment_check_fixture_and_journal()
    fixture = _joined_sources(
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
            fail(f"D3 atomic TaskFlow corpus is missing {marker!r}")
    for forbidden in (
        "page_act_without_servo_resolver_rejected",
        "client::error(&acted",
    ):
        if forbidden in fixture:
            fail(f"D3 atomic TaskFlow corpus retains obsolete rejection path {forbidden!r}")
