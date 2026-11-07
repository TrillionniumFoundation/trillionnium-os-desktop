#!/usr/bin/env python3
"""Local source/packet checks only; no device, subprocess or namespace entry."""
import ast
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
ACTUAL = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence/qa-install-state02')


def load(name):
    path = HERE/name
    module = types.ModuleType('local_'+path.stem); module.__file__ = str(path)
    raw = path.read_bytes(); ast.parse(raw,filename=str(path))
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def main():
    entry,stage = load('owned_inspect.py'),load('stage_execute.py')
    load('make_request.py')
    plan = entry.fixed_plan()
    assert plan['operation'] == 'inspect' and set(plan) == {'schema','operation','nonces'}
    pins = (HERE/'SOURCE_PINS.json').read_bytes()
    expected = hashlib.sha256(pins).hexdigest()
    entry.verify_source(expected)
    request_raw = (HERE/'exact-request.json').read_bytes()
    request = json.loads(request_raw)
    packet,files = stage.checked_packet(request['stdin'].encode())
    assert packet['source_manifest_sha256'] == expected
    assert request['idempotency_key'] == 'pocket4-bilibili-owned-launch-inspect-01-20261105'
    assert request['timeout_seconds'] == 600 and request['memory_max_bytes'] == 536870912
    assert request['cpu_quota_percent'] == 100
    assert set(files) == entry.FILES|{'SOURCE_PINS.json'}
    # Fixed actual receipts are exercised until the deliberately unavailable
    # raw state-command input. This is not a substituted state-command PASS.
    mapping = {str(path):ACTUAL/({'worker_command':'worker-command-result'}.get(name,name)+'.json')
               for name,(path,_,_) in entry.INSTALL_RECORDS.items()}
    original_read = entry.read; visited = []
    class RawStateNotLocal(Exception):
        pass
    def actual_read(path,maximum=1048576,expected=None,size=None):
        name = str(path)
        if name in mapping:
            visited.append(name)
            return original_read(mapping[name],maximum,expected,size)
        assert name == str(entry.OLD_STEP/'command-006.result.json')
        assert expected == 'f160d196ff7ef58329299a5ffae22aca550cd1095e14cbeecd4f8145461e1ec2'
        raise RawStateNotLocal(name)
    worker = json.loads((ACTUAL/'worker.json').read_bytes())
    prior = types.SimpleNamespace(APK_SHA=worker['build']['APK']['sha256'],
        APK_BYTES=worker['build']['APK']['bytes'],SIGNER_SHA=worker['build']['signer_certificate_sha256'])
    entry.read = actual_read
    try:
        entry.actual_install(prior,None,worker['build'])
    except RawStateNotLocal:
        assert len(visited) == 4 and len(set(visited)) == 4
    else:
        raise AssertionError('Missing raw state input was bypassed')
    finally:
        entry.read = original_read
    result = {'schema':1,'source_manifest_sha256':expected,
        'actual_four_install02_receipt_pins_and_internal_chain_before_raw_state':'PASS',
        'source_AST_and_no_action_module_load':'PASS',
        'fixed_unique_nonces_and_inspect_only_plan':'PASS',
        'exact_request_packet_source_and_resource_binding':'PASS',
        'actual_original_state_command_reparse':'NOT_RUN_LOCAL_INPUT_UNAVAILABLE_REQUIRED_ON_DEVICE',
        'remote_actions':0,'Android_commands':0,'namespace_entry':False,
        'actual_UI_or_cleanup_qualification':False,'whole_app_production_ready':False}
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__ == '__main__':
    main()
