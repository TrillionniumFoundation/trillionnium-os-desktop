import sys
sys.dont_write_bytecode=True
FIXTURE_PINS = {'s43-result.original.json': {'bytes': 52573, 'sha256': '96c6931181555e575bffa3e626d704b93254298441095f318691d9d3ab70cb11'}, 's43-terminal.original.json': {'bytes': 733, 'sha256': 'c42a9fd1a5bbf4f6d6ac7e335e0f3d0545379ce754c54fd9f6c99f0ba96e9076'}, 's42-failed-result.original.json': {'bytes': 51004, 'sha256': '996845dad5c91bd67f16706561d42417ed370ab000f26ac9b16a7d1832576e0c'}, 'scope47.original.json': {'bytes': 58854, 'sha256': '44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f'}}
WRONG_VENDOR_ACTUAL_SIGNATURE = {'cryptographic_verification_performed': True, 'verified': True, 'signer_certificate_sha256': ['d85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44'], 'schemes': {'v1 scheme (JAR signing)': True, 'v2 scheme (APK Signature Scheme v2)': True, 'v3 scheme (APK Signature Scheme v3)': False, 'v3.1 scheme (APK Signature Scheme v3.1)': False, 'v4 scheme (APK Signature Scheme v4)': False}, 'API_minimum_override_used': False, 'integrity_check_bypassed': False}
WRONG_VENDOR_ACTUAL_SOURCE = {'bytes': 25448, 'sha256': '3ba6894d1d084f8d95b4ebfb342a3710990ce3b0aadf0e17710e9f608f8228a6', 'path': 'official_source_scripts/s38_szzc_operator_signature/actual/stdout.original.json'}

def main():
    import copy
    import hashlib
    import json
    import types
    from pathlib import Path
    root = Path(__file__).parent
    worker_bytes = (root / 'install_successor_native.py').read_bytes()
    worker = types.ModuleType('offline_reviewed_zbj_installer')
    worker.__file__ = str(root / 'install_successor_native.py')
    exec(compile(worker_bytes, worker.__file__, 'exec'), worker.__dict__)
    values = {}
    for name, pin in FIXTURE_PINS.items():
        raw = (root / name).read_bytes()
        assert len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], name
        values[name] = json.loads(raw)
    actual = values['s43-result.original.json']
    terminal = values['s43-terminal.original.json']
    scope = values['scope47.original.json']
    checks = []
    def rejects(label, call):
        try:
            call()
        except worker.Rejected:
            checks.append({'name': label, 'pass': True, 'kind': 'local_negative_control'})
            return
        raise AssertionError('negative control admitted: ' + label)
    candidate = worker.qualify_s43_observation(actual, terminal)
    assert candidate['original_receipt_schema'] == actual['schema']
    assert candidate['apk']['stat']['st_ctime_ns'] == int(actual['candidate']['identity']['st_ctime_ns'])
    assert str(candidate['apk']['stat']['st_ctime_ns']) == actual['candidate']['identity']['st_ctime_ns']
    assert candidate['manifest']['version_code'] == 370 and candidate['production_ready'] is False
    checks.append({'name': 'actual_S43_normalizes_losslessly_without_legacy_receipt', 'pass': True,
                   'kind': 'pure_reinterpretation_of_archived_actual_host_evidence'})
    rejects('actual_S42_failure_not_reclassified',
            lambda: worker.qualify_s43_observation(values['s42-failed-result.original.json'], terminal))
    changed = copy.deepcopy(actual)
    changed['candidate_signature_observation'] = WRONG_VENDOR_ACTUAL_SIGNATURE
    assert changed['candidate_signature_observation']['verified'] is True
    rejects('valid_cryptography_from_other_vendor_not_an_update',
            lambda: worker.qualify_s43_observation(changed, terminal))
    changed = copy.deepcopy(actual)
    changed['commands'][0]['joined'] = False
    rejects('zero_exit_with_unretired_child_rejected', lambda: worker.qualify_s43_observation(changed, terminal))
    changed = copy.deepcopy(actual)
    changed['command_parser_health'][0]['diagnostics']['unrecognized_badging_lines'] = [{'raw_line': 'unknown-row'}]
    rejects('unknown_manifest_output_rejected', lambda: worker.qualify_s43_observation(changed, terminal))
    changed_terminal = copy.deepcopy(terminal)
    changed_terminal['output_durable'] = False
    rejects('undurable_completion_rejected', lambda: worker.qualify_s43_observation(actual, changed_terminal))
    worker.qualify_explicit47_scope(scope, scope['runtime_epoch_sha256'])
    checks.append({'name': 'actual_explicit47_scope_keys_accepted_without_freshness_claim', 'pass': True,
                   'kind': 'pure_shape_check_of_archived_actual_scope'})
    missing = copy.deepcopy(scope)
    del missing['apps']['org.droidloom.qa.successor.p8f89f253350ba2fa.r1']
    rejects('old46_scope_missing_new_helper_rejected',
            lambda: worker.qualify_explicit47_scope(missing, scope['runtime_epoch_sha256']))
    replaced = copy.deepcopy(missing)
    replaced['apps']['org.example.unreviewed'] = {}
    rejects('same_count_foreign_scope_rejected',
            lambda: worker.qualify_explicit47_scope(replaced, scope['runtime_epoch_sha256']))
    rejects('stale_runtime_epoch_rejected', lambda: worker.qualify_explicit47_scope(scope, '0'*64))
    changed_request = copy.deepcopy(worker.REVIEWED_ZBJ_REQUEST)
    changed_request['package'] = 'tv.danmaku.bili'
    rejects('new_revision_cannot_select_another_app', lambda: worker.validate_request(changed_request))
    worker.validate_request(copy.deepcopy(worker.REVIEWED_ZBJ_REQUEST))
    result = {'schema': 'pocket4-zbj-r3-local-qualification-controls-v1', 'ok': True, 'checks': checks,
              'runtime_worker_called': False, 'native_or_Android_commands': 0, 'Main_reads_or_locks': 0,
              'installs': 0, 'actual_host_child_spawns': 0, 'fresh_runtime_or_app_scope_proved': False,
              'production_ready': False, 'cleanup_eligible': False}
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
