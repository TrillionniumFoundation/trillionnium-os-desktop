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
    scope = values['scope48.original.json']
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
    worker.qualify_explicit48_scope(scope, scope['runtime_epoch_sha256'])
    checks.append({'name': 'actual_explicit48_scope_keys_accepted_without_freshness_claim', 'pass': True,
                   'kind': 'pure_shape_check_of_archived_actual_scope'})
    missing = copy.deepcopy(scope)
    del missing['apps']['org.droidloom.qa.successor.p8f89f253350ba2fa.r1']
    rejects('scope48_missing_owned_helper_rejected',
            lambda: worker.qualify_explicit48_scope(missing, scope['runtime_epoch_sha256']))
    replaced = copy.deepcopy(missing)
    replaced['apps']['org.example.unreviewed'] = {}
    rejects('same_count_foreign_scope_rejected',
            lambda: worker.qualify_explicit48_scope(replaced, scope['runtime_epoch_sha256']))
    rejects('stale_runtime_epoch_rejected', lambda: worker.qualify_explicit48_scope(scope, '0'*64))
    prior = values['scope47.original.json']
    assert all(scope['apps'][k] == v for k, v in prior['apps'].items())
    assert set(scope['apps']) - set(prior['apps']) == {'com.example.ndk_tests'}
    assert scope['apps']['com.example.ndk_tests']['fresh_signature_verification'] is False
    rejects('actual_old47_without_NDK_is_not_the_new48_scope',
            lambda: worker.qualify_explicit48_scope(prior, scope['runtime_epoch_sha256']))
    non_target = {k: v for k, v in scope['apps'].items() if k != worker.ZBJ_PACKAGE}
    worker.require_unchanged_non_target_rows(non_target, copy.deepcopy(non_target))
    changed_stat = copy.deepcopy(non_target)
    changed_stat['com.lianjia.beike']['apks'][0]['file']['st_ino'] += 1
    rejects('same_non_target_bytes_but_changed_inode_rejected',
            lambda: worker.require_unchanged_non_target_rows(non_target, changed_stat))
    changed_ndk = copy.deepcopy(non_target)
    changed_ndk['com.example.ndk_tests']['apks'][0]['file']['st_ino'] += 1
    rejects('same_NDK_bytes_but_replaced_inode_rejected',
            lambda: worker.require_unchanged_non_target_rows(non_target, changed_ndk))
    changed_request = copy.deepcopy(worker.REVIEWED_ZBJ_REQUEST)
    changed_request['package'] = 'tv.danmaku.bili'
    rejects('new_revision_cannot_select_another_app', lambda: worker.validate_request(changed_request))
    worker.validate_request(copy.deepcopy(worker.REVIEWED_ZBJ_REQUEST))
    result = {'schema': 'pocket4-zbj-full48-r4-local-qualification-controls-v1', 'ok': True, 'checks': checks,
              'runtime_worker_called': False, 'native_or_Android_commands': 0, 'Main_reads_or_locks': 0,
              'installs': 0, 'actual_host_child_spawns': 0, 'fresh_runtime_or_app_scope_proved': False,
              'production_ready': False, 'cleanup_eligible': False}
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
