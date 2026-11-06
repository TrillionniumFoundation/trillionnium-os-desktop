    baseline = json.loads(packet['actual-current-runtime-baseline.json'])
    good('actual_baseline_derives_eight_roles', lambda: snapshot['qualify_baseline'](baseline))
    missing = copy.deepcopy(baseline)
    missing['runtime']['held']['extra'].pop('composer')
    bad('missing_composer_rejected', lambda: snapshot['expected_from_baseline'](missing), 'TYPED_EIGHT_ROLES_REQUIRED')
    stale = copy.deepcopy(baseline)
    stale['runtime_epoch_sha256'] = '0' * 64
    bad('stale_runtime_baseline_rejected', lambda: snapshot['qualify_baseline'](stale), 'TYPED_RUNTIME_BASELINE_CHANGED')
    bad('missing_final_scope_pin_rejected', lambda: snapshot['qualify_scope_reference'](None, None), 'FINAL_APP_SCOPE_PIN_REQUIRED')
    guard_receipt = {
        'schema': 'pocket4-successor-main-guard-v1', 'baseline_sha256': snapshot['IDENTITY_SOURCE_SHA'],
        'runtime_epoch_sha256': snapshot['RUNTIME_EPOCH_SHA'], 'Main_epoch_sha256': snapshot['FRAMEWORK_EPOCH_SHA'],
        'eight_roles_including_composer_match': True, 'complete_paired_classpath_matches': True,
        'resource_limits_match': True, 'runtime_only_app_scopes_checked_separately': True,
        'UI_or_install_runtime_admitted': False, 'production_ready': False,
    }
    for name, key, value in [
        ('wrong_guard_baseline_receipt_rejected', 'baseline_sha256', '0' * 64),
        ('wrong_guard_runtime_receipt_rejected', 'runtime_epoch_sha256', '0' * 64),
        ('guard_cannot_grant_ui', 'UI_or_install_runtime_admitted', True),
    ]:
        bad(name, lambda key=key, value=value: snapshot['qualify_typed_guard']({**guard_receipt, key: value}), 'TYPED_GUARD_RECEIPT_REJECTED')
    # Deliberately synthetic small fixture; never emitted as an actual app scope.
    scope_pin = {'path': '/home/alex/work/pure-control-only/app-scope.json', 'bytes': 1, 'sha256': '1' * 64}
    packages = ['synthetic.one', 'synthetic.two']
    scope_receipt = {
        'schema': 'pocket4-app-scope-guard-v1', 'runtime_epoch_sha256': snapshot['RUNTIME_EPOCH_SHA'],
        'app_scope_sha256': scope_pin['sha256'], 'packages': packages,
        'current_apk_paths_and_file_identities_match': True, 'new_signature_verification_performed': False,
        'UI_or_install_runtime_admitted': False,
    }
    for name, key, value in [
        ('scope_receipt_old_epoch_rejected', 'runtime_epoch_sha256', '0' * 64),
        ('scope_receipt_wrong_apk_scope_rejected', 'app_scope_sha256', '0' * 64),
        ('scope_receipt_missing_package_rejected', 'packages', ['synthetic.one']),
        ('scope_cannot_claim_signature_verification', 'new_signature_verification_performed', True),
    ]:
        bad(name, lambda key=key, value=value: snapshot['qualify_scope_receipt']({**scope_receipt, key: value}, scope_pin, packages),
            'CURRENT_APP_SCOPE_RECEIPT_REJECTED')
    changed_scope = copy.deepcopy(base)
    changed_scope['app_scope_sha256'] = '0' * 64
    need(fence['compare'](base, changed_scope)['main_fence_pass'] is False, 'CONTROL_STALE_SCOPE_FENCE')
    passed.append('stale_scope_fails_outer_fence')
    changed_qualification = copy.deepcopy(base)
    changed_qualification['current_qualification_sha256'] = '0' * 64
    need(fence['compare'](base, changed_qualification)['main_fence_pass'] is False, 'CONTROL_STALE_QUALIFICATION_FENCE')
    passed.append('old_qualification_fails_outer_fence')
