#!/usr/bin/env python3
"""Finite v2 source/API checker; optional actual bounded supplier verification.

Default operation executes no downloaded tool, Cargo or native case. Source
shape is not cryptographic verification or installed/production qualification.
"""
from __future__ import annotations
import argparse
import inspect
import json
from pathlib import Path
import signal
import sys
try:
    from . import mozjs_authenticated_input as authenticated
    from . import build_mozjs_authenticated_native as build
    from . import verify_mozjs_secondary_input as old
except ImportError:
    import mozjs_authenticated_input as authenticated
    import build_mozjs_authenticated_native as build
    import verify_mozjs_secondary_input as old
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/mozjs-authenticated-input.v2.json"
EXPECTED = {'schema': 'trillionnium.mozjs-authenticated-input-custody.v2',
 'status': 'SOURCE_CANDIDATE_NOT_QUALIFIED',
 'manifest': 'manifests/mozjs-authenticated-input.v2.json',
 'api': {'verify_inputs': "(archive_path: 'Path', bundle_path: 'Path', tool_path: 'Path', evidence_parent: "
                          "'Path') -> 'dict'",
         'build_authenticated_native': "(upstream: 'Path', original_lock: 'Path', archive_path: 'Path', "
                                       "bundle_path: 'Path', tool_path: 'Path', target_parent: 'Path', "
                                       "profile: 'str') -> 'dict'"},
 'input_authority': 'paths select bytes only; no caller verification flags/stdout/token/roots/expiry '
                    'bypass/arbitrary Cargo argv',
 'custody': {'archive': 'original v1 SealedArchiveLease and unchanged 32 MiB bound',
             'bundle': 'original fixed index1 memfd four seals retained; child byte-identical readonly tmpfs '
                       'delivery snapshot is a distinct consuming inode',
             'tool': 'fixed official gh sealed binary actually execed through internally formed child '
                     'self-FD path; explicit inherited FD object/bytes bound to parent lease',
             'creator': 'original PID/thread/reentry/current-object readback checks',
             'maximum_bundle_bytes': 65536,
             'maximum_tool_bytes': 67108864,
             'maximum_policy_bytes': 16384,
             'maximum_each_output_bytes': 262144,
             'private_helper_expected_bytes': 'host tests only; public expectations source-defined',
             'release': 'after original Cargo leader waited and ordinary process group absent; unresolved '
                        'owner retains all three inputs',
             'supervisor_death_escaping_groups_qualified': False,
             'maximum_each_cargo_output_bytes': 16777216,
             'namespace': 'private child user+mount namespaces/current UID/GID map/private propagation; '
                          'fixed 64 KiB tmpfs readonly; internally owned directory FD across exec',
             'capability_retirement': 'drop complete bounded kernel capability bounding set, locked '
                                      'NOROOT/NO_SETUID_FIXUP/NO_AMBIENT securebits, empty capsets and '
                                      'no-new-privileges; actual gh status all five capability sets zero',
             'original_bundle_memfd_inode_consumption_proven': False,
             'snapshot_four_seals_claimed': False},
 'verification': {'tool_version': '2.102.0',
                  'tool_sha256': '7469124f706944133d6a169691dd1c6c3511b12e85878d255e044e2948df4c9b',
                  'tool_artifact_attestation_verified': False,
                  'default_authenticated_tuf_roots': True,
                  'caller_roots_or_expiry_bypass': False,
                  'timeout_seconds': 60,
                  'termination_grace_seconds': 2,
                  'json': 'bounded, duplicate-rejecting, finite JSON; one actual verified result',
                  'authenticated_certificate_fields': 22,
                  'signed_statement': 'actual verified statement equals DSSE payload; exactly one matching '
                                      'archive subject',
                  'der': 'exact DER of the same verified bundle; canonical bounded TokenSubject and '
                         'historical validity',
                  'display_issuer': 'empty wildcard display is not exact issuer authority',
                  'policy_parser_is_crypto_authority': False},
 'build': {'directory_selectors': 'both selectors are existing canonical absolute directories without parent or symlink aliases, checked before held input admission and allocation; target parent is outside upstream; concurrent path mutation is not qualified',
           'original_entry_helpers': 'verify_prepared/profile_environment/compile_argv unchanged; original '
                                     '_BuildProcess lifecycle owner and pending custody retained',
           'profiles': {'native-owner': 'trillionnium_product_owner',
                        'approved-startup': 'trillionnium_approved_connected'},
           'timeout_seconds': 10800,
           'termination_grace_seconds': 5,
           'new_target': 'exclusive initially empty outside upstream per invocation',
           'verification': 'entry performs actual verification internally and retains same '
                           'archive/bundle/tool across Cargo',
           'working_directory': 'private process cwd is separate from evidence; verifier defaults to fixed private evidence, Cargo uses the same upstream pathname checked by unchanged verify_prepared',
           'actual_archive_consumption_proven': False,
           'prepared_source_diagnostics': 'unchanged original helper runs in bounded private Python child; '
                                          'original Git bounds retained; interpreter/PATH/config trust not '
                                          'qualified'},
 'evidence': {'raw_verifier_outputs': 'bounded private stdout.raw/stderr.raw, retained even on verifier '
                                      'failure',
              'default_root_cache': 'original tool writes fresh private cache; bounded byte readback is '
                                    'diagnostic, not caller trust authority',
              'user_failure': 'fixed MOZJS_AUTHENTICATED_INPUT_REFUSED category; no error/stdout/env/auth '
                              'payload',
              'raw_cargo_outputs': 'private bounded stdout.raw/stderr.raw, 16 MiB each; original Cargo '
                                   'argv/10800/5 preserved',
              'namespace_channel': 'private bounded readonly-namespace.json and actual-gh-status.raw; no '
                                   'mixture with official verified JSON stdout'},
 'preservation': {'original_635_bytes_modes_blobs': True,
                  'old_v1_APIs_bodies_contracts_tests_claims': True,
                  'old_native_six_PIN_Cargo_workflows_budgets': True},
 'claims': {'source_custody_only': True,
            'new_source_whole_qualified': False,
            'actual_Cargo_archive_consumption': False,
            'native_cases_executed': False,
            'installed_qualified': False,
            'human_approval': False,
            'production_ready': False}}


def check() -> dict:
    authenticated.load_manifest(); old.check()
    raw = authenticated._read_regular(ROOT / CONTRACT, authenticated.MAX_POLICY_BYTES)
    actual = authenticated._bounded_json(raw, authenticated.MAX_POLICY_BYTES)
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(EXPECTED, sort_keys=True):
        raise ValueError("authenticated input contract differs")
    apis = {"verify_inputs": authenticated.verify_inputs, "build_authenticated_native": build.build_authenticated_native}
    if {key: str(inspect.signature(value)) for key, value in apis.items()} != EXPECTED["api"]:
        raise ValueError("authenticated public API differs")
    if len(authenticated.CERTIFICATE_FIELDS) != 22 or authenticated.original.TIMEOUT_SECONDS != 10800 or authenticated.original.GRACE_SECONDS != 5:
        raise ValueError("authenticated fixed profile differs")
    document = authenticated._read_regular(ROOT / "docs/architecture/MOZJS_AUTHENTICATED_INPUT.md", 32768).decode("utf-8", "strict")
    for marker in [CONTRACT, authenticated.MANIFEST, "TokenSubject", "22", "60", "635", "10800", "32 MiB", "incomplete", "checksum bootstrap", "wildcard", "initially empty"]:
        if marker not in document: raise ValueError("authenticated source document differs")
    return {"status": "PASS_FINITE_V2_SOURCE_API_ONLY", "actual_supplier_signature_verified": False,
            "tool_artifact_attestation_verified": False, "actual_cargo_archive_consumption_proven": False,
            "native_cases_executed": False, "installed_qualified": False, "production_ready": False}


def main() -> int:
    parser = authenticated._FixedArgumentParser(description=__doc__)
    for name in ["archive", "bundle", "tool", "evidence-parent"]: parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    selectors = [args.archive, args.bundle, args.tool, args.evidence_parent]
    if any(value is not None for value in selectors) and not all(value is not None for value in selectors):
        parser.error("actual verification requires all four byte/evidence selectors")
    previous = signal.signal(signal.SIGTERM, authenticated.original._cancel_from_signal)
    try:
        try:
            result = check()
            if args.archive is not None:
                result["actual_verification_observation"] = authenticated.verify_inputs(*selectors)
        except (Exception, KeyboardInterrupt):
            print("MOZJS_AUTHENTICATED_INPUT_REFUSED", file=sys.stderr)
            return 1
    finally: signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
