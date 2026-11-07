#!/usr/bin/env python3
"""Hash-bound in-memory loader. Only the explicit execute entry may touch Main."""
import base64
import hashlib
import json
import types

NAMES = ('binding.json', 'prior-main-identity-original.json', 'read_main_identity.py',
         'restore_main.py', 'stage_execute.py')
OUTPUT_MAX = 1024 * 1024
TOTAL_MAX = 196608


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def module(body, name):
    result = types.ModuleType(name)
    result.__file__ = '<verified-in-memory-' + name + '>'
    exec(compile(body, result.__file__, 'exec'), result.__dict__)
    return result


def inspect_packet(packet, expected_manifest):
    require(set(packet) == {'schema', 'manifest', 'files'} and packet['schema'] == 1, 'PACKET_SCHEMA')
    manifest_raw = packet['manifest'].encode('ascii')
    require(hashlib.sha256(manifest_raw).hexdigest() == expected_manifest, 'EXTERNAL_MANIFEST_PIN')
    manifest = json.loads(manifest_raw)
    require(manifest['schema'] == 1 and manifest['revision'] == 1 and
            manifest['purpose'] == 'restore-original-main-tasksmax-only', 'MANIFEST_PURPOSE')
    require(set(packet['files']) == set(manifest['files']) == set(NAMES), 'EXACT_FIVE_PACKET_FILES')
    files = {}
    total = 0
    for name in NAMES:
        body = base64.b64decode(packet['files'][name], validate=True)
        row = manifest['files'][name]
        require(set(row) == {'bytes', 'sha256'} and 0 < len(body) <= 131072 and
                len(body) == row['bytes'] and hashlib.sha256(body).hexdigest() == row['sha256'],
                'EXACT_FILE_PIN:' + name)
        body.decode('utf-8')
        total += len(body)
        require(total <= TOTAL_MAX, 'TOTAL_SOURCE_BOUND')
        files[name] = body
    require(len(files['read_main_identity.py']) == 18537 and
            hashlib.sha256(files['read_main_identity.py']).hexdigest() ==
            '4b955afce019418e98282aa4af549ab1089afc040a5c8990b7713be5f8b4585e',
            'ORIGINAL_IDENTITY_COLLECTOR_BYTE_EXACT')
    binding = json.loads(files['binding.json'])
    driver = module(files['restore_main.py'], 'fixed_main_tasksmax_restore')
    # Pure validation, before any claim, filesystem access, process or mutation.
    driver.validate_binding(binding, files['prior-main-identity-original.json'])
    return files, manifest, binding, driver


def main(packet, expected_manifest, execute=False):
    result = dict(schema=1, state='NOT_READY', ok=False, error=None,
                  runtime_authorized=False, source_manifest_sha256=expected_manifest,
                  execution_attempted=False, Android_UI_actions=0)
    try:
        files, manifest, binding, driver = inspect_packet(packet, expected_manifest)
        result['source_files'] = manifest['files']
        result['actual_identity_pin'] = binding['prior_identity']
        if not execute:
            result.update(state='PLAN_ONLY_ACTUAL_BOUND', ok=True, plan=driver.plan())
        else:
            identity = module(files['read_main_identity.py'], 'unchanged_identity_collector')
            result['execution_attempted'] = True
            result['transaction'] = driver.execute_once(identity, binding,
                                                        files['prior-main-identity-original.json'])
            result['ok'] = result['transaction']['ok']
            result['state'] = result['transaction']['state']
    except Exception as error:
        result['error'] = dict(type=type(error).__name__, message=str(error),
                              errno=getattr(error, 'errno', None), notes=list(getattr(error, '__notes__', ())))
        result['ok'] = False
        result['state'] = 'MAIN_RESTORE_NOT_QUALIFIED'
    raw = (json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
    require(len(raw) <= OUTPUT_MAX, 'COMPLETE_OUTPUT_BOUND_NO_TRUNCATION')
    print(raw.decode('ascii'), end='', flush=True)
    return 0 if result['ok'] else 1
