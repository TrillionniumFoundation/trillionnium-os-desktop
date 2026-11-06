"""Inserted into the existing fixed snapshot; not a standalone entry point."""

def expected_from_baseline(baseline):
    runtime = baseline['runtime']
    binding = runtime['held']['process_snapshot']['binding']
    extra = runtime['held']['extra']
    required = {'daemon', 'launcher', 'android_init', 'presenter', 'surfaceflinger', 'zygote64', 'system_server', 'composer'}
    need(set(binding['processes']) == set(extra) == required, 'TYPED_EIGHT_ROLES_REQUIRED')
    rows = {}
    for role, value in binding['processes'].items():
        item = extra[role]
        proc = item['held_proc']
        need(value['host_pid'] == proc['pid'] and value['start_ticks'] == int(proc['start']) and
             value['parent_host_pid'] == proc['ppid'] and value['uids'] == [int(v) for v in proc['uid']] and
             value['namespace_pids'] == [int(v) for v in proc['nspid']] and
             value['cgroup'] == proc['cgroup'].splitlines() and
             all(value['namespaces'][name] == item['namespaces'][name] for name in value['namespaces']),
             'TYPED_BASELINE_ROLE_RECORDS_DISAGREE')
        rows[role] = {'pid': value['host_pid'], 'start_ticks': value['start_ticks'],
                      'ppid': value['parent_host_pid'], 'uids': value['uids'],
                      'namespace_pids': value['namespace_pids'], 'cgroup': proc['cgroup'],
                      'namespaces': {name: item['namespaces'][name] for name in ('mnt', 'pid', 'user')},
                      'root_identity': item['root']}
    return rows


def qualify_baseline(baseline):
    runtime_raw = json.dumps(baseline['runtime'], sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode()
    need(baseline['schema'] == 'pocket4-successor-runtime-baseline-v1' and
         baseline['runtime_epoch_sha256'] == sha(runtime_raw) == RUNTIME_EPOCH_SHA and
         baseline['framework_epoch']['sha256'] == FRAMEWORK_EPOCH_SHA and
         baseline['runtime']['held']['process_snapshot']['binding']['boot_id'] == BOOT_ID and
         baseline['production_ready'] is False and baseline['UI_or_install_runtime_admitted'] is False,
         'TYPED_RUNTIME_BASELINE_CHANGED')
    need(expected_from_baseline(baseline) == EXPECTED, 'TYPED_BASELINE_PROTECTED_ROLES_CHANGED')
    need(baseline['runtime']['limits'] == LIMITS and baseline['runtime']['cell_config']['sha256'] == CELL_SHA,
         'TYPED_BASELINE_CONFIG_OR_LIMITS_CHANGED')


def qualify_scope_reference(pin, packages):
    need(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'} and
         type(pin['path']) is str and pin['path'].startswith('/home/alex/work/') and
         all(part not in ('', '.', '..') for part in pin['path'][1:].split('/')) and
         type(pin['bytes']) is int and 0 < pin['bytes'] <= 4 * 1024 * 1024 and
         type(pin['sha256']) is str and len(pin['sha256']) == 64 and
         all(c in '0123456789abcdef' for c in pin['sha256']) and
         type(packages) is list and 0 < len(packages) <= 128 and
         all(type(name) is str and name for name in packages) and packages == sorted(set(packages)),
         'FINAL_APP_SCOPE_PIN_REQUIRED')
    return pin


def qualify_typed_guard(receipt):
    need(receipt.get('schema') == 'pocket4-successor-main-guard-v1' and
         receipt.get('baseline_sha256') == IDENTITY_SOURCE_SHA and
         receipt.get('runtime_epoch_sha256') == RUNTIME_EPOCH_SHA and
         receipt.get('Main_epoch_sha256') == FRAMEWORK_EPOCH_SHA and
         receipt.get('eight_roles_including_composer_match') is True and
         receipt.get('complete_paired_classpath_matches') is True and
         receipt.get('resource_limits_match') is True and
         receipt.get('runtime_only_app_scopes_checked_separately') is True and
         receipt.get('UI_or_install_runtime_admitted') is False and receipt.get('production_ready') is False,
         'TYPED_GUARD_RECEIPT_REJECTED')


def qualify_scope_receipt(receipt, pin, packages):
    qualify_scope_reference(pin, packages)
    need(receipt.get('schema') == 'pocket4-app-scope-guard-v1' and
         receipt.get('runtime_epoch_sha256') == RUNTIME_EPOCH_SHA and
         receipt.get('app_scope_sha256') == pin['sha256'] and receipt.get('packages') == packages and
         receipt.get('current_apk_paths_and_file_identities_match') is True and
         receipt.get('new_signature_verification_performed') is False and
         receipt.get('UI_or_install_runtime_admitted') is False,
         'CURRENT_APP_SCOPE_RECEIPT_REJECTED')


def load_current_guard():
    raw = read_regular(CURRENT_GUARD_PIN['path'])
    need(len(raw) == CURRENT_GUARD_PIN['bytes'] and sha(raw) == CURRENT_GUARD_PIN['sha256'], 'CURRENT_GUARD_SOURCE_PIN')
    scope = {'__name__': 'normal05_exact_current_typedguard', '__file__': CURRENT_GUARD_PIN['path']}
    exec(compile(raw, CURRENT_GUARD_PIN['path'], 'exec'), scope, scope)
    need(scope['PINS'] == CURRENT_GUARD_PINS, 'CURRENT_GUARD_AUTHORITY_PINS')
    return scope
