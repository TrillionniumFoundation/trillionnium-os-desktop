#!/usr/bin/env python3
"""Stable D6 capability/egress facade with deterministic refusal precedence.

The bulk reference implementation remains in ``capability_egress_reference_impl``.
This facade keeps the public import/CLI path stable while making two security
classification rules explicit and version-independent:

* a sole permit for the wrong portal reports ``AUDIENCE_MISMATCH`` rather than
  being hidden behind a cardinality error;
* narrow non-global IP classes are classified before Python's broader and
  version-dependent ``is_global``/``is_private`` predicates.

The module remains a pure source reference and performs no network or external
effect.
"""
from __future__ import annotations

import ipaddress
from typing import Any

import capability_egress_reference_impl as _impl
from capability_egress_reference_impl import *  # noqa: F401,F403


def validate_public_ip(value: Any) -> ipaddress._BaseAddress:
    """Return a global address or fail with one stable, specific reason code."""

    if not isinstance(value, str):
        _impl.fail("INVALID_IP_ADDRESS")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise _impl.PolicyError("INVALID_IP_ADDRESS", value) from error

    canonical = address.compressed.lower()
    if canonical in _impl.METADATA_ADDRESSES or value.lower() in _impl.METADATA_ADDRESSES:
        _impl.fail("METADATA_IP_FORBIDDEN", canonical)

    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            _impl.fail("IPV4_MAPPED_IPV6_FORBIDDEN", canonical)
        if address.sixtofour is not None:
            _impl.fail("SIX_TO_FOUR_FORBIDDEN", canonical)
        if address.teredo is not None:
            _impl.fail("TEREDO_FORBIDDEN", canonical)

    # Check narrow semantic classes unconditionally.  Python 3.13 deliberately
    # reports some multicast addresses as global, while Python releases also
    # differ in which special-purpose ranges satisfy ``is_private``.  Stable
    # policy reason codes must not depend on those broad predicates.
    if address.is_loopback:
        _impl.fail("LOOPBACK_IP_FORBIDDEN", canonical)
    if address.is_link_local:
        _impl.fail("LINK_LOCAL_IP_FORBIDDEN", canonical)
    if address.is_unspecified:
        _impl.fail("UNSPECIFIED_IP_FORBIDDEN", canonical)
    if address.is_multicast:
        _impl.fail("MULTICAST_IP_FORBIDDEN", canonical)
    if address.is_reserved:
        _impl.fail("RESERVED_IP_FORBIDDEN", canonical)
    if address.is_private:
        _impl.fail("PRIVATE_IP_FORBIDDEN", canonical)
    if not address.is_global:
        _impl.fail("NON_GLOBAL_IP_FORBIDDEN", canonical)
    return address


def authorize(
    permits: list[dict[str, Any]],
    request: dict[str, Any],
    trust: dict[str, Any],
    runtime_subject: dict[str, Any],
    contract: dict[str, Any],
    ledger: _impl.DecisionLedger,
    *,
    now_epoch: int,
) -> dict[str, Any]:
    """Authorize one pure reference request with precise fail-closed errors."""

    if not permits:
        _impl.fail("PERMIT_REQUIRED")
    verified = [
        _impl.verify_permit(item, trust, runtime_subject, contract, now_epoch=now_epoch)
        for item in permits
    ]
    for item in verified:
        ledger.available(item)

    kind = request.get("kind") if isinstance(request, dict) else None
    if kind == "file":
        if len(verified) != 1:
            _impl.fail("SINGLE_FILE_PERMIT_REQUIRED")
        details = _impl.authorize_file(verified[0], request)
        consumed = verified
    elif kind == "notification":
        if len(verified) != 1:
            _impl.fail("SINGLE_NOTIFICATION_PERMIT_REQUIRED")
        details = _impl.authorize_notification(verified[0], request)
        consumed = verified
    elif kind == "audio":
        if len(verified) != 1:
            _impl.fail("SINGLE_AUDIO_PERMIT_REQUIRED")
        details = _impl.authorize_audio(verified[0], request)
        consumed = verified
    elif kind == "network":
        network_permits = [
            item for item in verified if item["audience"] == "portal:network"
        ]
        if len(network_permits) != 1:
            if len(verified) == 1:
                # Delegate once so the stable, more specific audience error is
                # emitted for a sole wrong-portal permit.
                _impl.authorize_network(verified[0], request, contract, now_epoch)
                raise AssertionError("authorize_network returned for wrong audience")
            _impl.fail("SINGLE_NETWORK_PERMIT_REQUIRED")

        details = _impl.authorize_network(
            network_permits[0], request, contract, now_epoch
        )
        consumed = [network_permits[0]]
        if request.get("action") == "download":
            file_permits = [
                item for item in verified if item["audience"] == "portal:file"
            ]
            if len(file_permits) != 1:
                _impl.fail("DOWNLOAD_REQUIRES_FILE_PERMIT")
            target = network_permits[0]["constraints"].get("download_target")
            if not isinstance(target, dict):
                _impl.fail("DOWNLOAD_TARGET_CONSTRAINT_REQUIRED")
            _impl.authorize_file(file_permits[0], target)
            details["file_handle_id"] = target["handle_id"]
            consumed.append(file_permits[0])
    else:
        _impl.fail("UNKNOWN_PORTAL_REQUEST")

    return ledger.commit(consumed, request, details, now_epoch)


# Functions defined in the implementation resolve globals in that module.  Pin
# both corrected entry points there as well so its self-test and CLI exercise
# the exact same policy as importers of this facade.
_impl.validate_public_ip = validate_public_ip
_impl.authorize = authorize


if __name__ == "__main__":
    raise SystemExit(_impl.main())
