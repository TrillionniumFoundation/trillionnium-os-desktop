#!/usr/bin/env python3
"""Offline, create-only binding of one separately reviewed resource readmission."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266/native-recovery-20261105-02')
OLD = BASE / 'full-engine-candidate06-go5-build-request-01'
NEW = BASE / 'full-engine-candidate06-go5-readmission02'
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence')
OLD_OUTER_SHA = '25487a42ed042f8e16abdcc38740697824c3f1d881d5f92c8f00837845cad56a'
OLD_REQUEST_SHA = 'ffe8292ce1b183ab851dbb220185cc227cae481b15057ace196a8b7ca59068d1'
OLD_PACKET_SHA = '385de8faf0cd91e36982cb1dc0356db5c29cb9a5f1a11d88b228c985f8e48299'
FAILED_SHA = '8b74d6b0351db5823c4e183c222783b94ada34369f1eede78289ac3b6d20146a'
MEMORY_SHA = '650a723bc5ea3a71446f3f33430e4c71bf961a1d1454ca4798e80690360ce526'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(path, wanted):
    raw = path.read_bytes()
    if sha(raw) != wanted:
        raise RuntimeError('input SHA changed: ' + str(path))
    return raw


def encode(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def main():
    old = exact(OLD / 'fenced_build_streaming.py', OLD_OUTER_SHA).decode()
    request = json.loads(exact(OLD / 'exact-request.json', OLD_REQUEST_SHA))
    packet_raw = exact(OLD / 'verified-source-packet.json', OLD_PACKET_SHA)
    assert request['stdin'].encode() == packet_raw
    packet = json.loads(packet_raw)
    failed = exact(EVIDENCE / 'candidate06-go5-build01/terminal.json', FAILED_SHA)
    sample = exact(EVIDENCE / 'memory-post06-read01/result.json', MEMORY_SHA)
    assert len(failed) == 1172 and len(sample) == 3812
    insert = '''
PRIOR_FAILURE_SHA = '8b74d6b0351db5823c4e183c222783b94ada34369f1eede78289ac3b6d20146a'
POSTFAILURE_MEMORY_SHA = '650a723bc5ea3a71446f3f33430e4c71bf961a1d1454ca4798e80690360ce526'


def require_original_attempt_absent(scope):
    attempt = scope['ATTEMPT']
    require(attempt == ROOT / 'attempt-01', 'original inner attempt path changed')
    scope['no_alias'](attempt)
    require(not attempt.exists() and not attempt.is_symlink(),
            'original attempt-01 exists; this readmission is not authorized')


def readmission_contract(packet, scope):
    # Bind the actual original rejection through a held descriptor. Nothing in
    # build-fences-01 is modified, and this is not evidence of a compiler run.
    path = ROOT / 'build-fences-01' / 'terminal.json'
    scope['no_alias'](path.parent)
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == 1172,
                'original failed fence is not the exact regular receipt')
        raw = stream.read(1173)
        after = os.fstat(stream.fileno())
        named = path.lstat()
        require(identity(before) == identity(after) == identity(named),
                'original failed fence changed while held')
    require(sha(raw) == PRIOR_FAILURE_SHA and
            raw == packet['prior_failed_fence_terminal'].encode(),
            'original failed fence bytes changed')
    failed = json.loads(raw)
    require(failed['state'] == 'FAILED' and failed['inner_returncode'] is None and
            failed['error'] == "RuntimeError('less than 13 GiB MemAvailable for fresh Go5 streaming profile; no automatic retry')" and
            failed['main_fence_assessment']['main_fence_pass'] is True,
            'prior result is not the authorized resource-admission failure')
    # This historical sample explains the new one-shot request. Only the
    # unchanged inner controller's fresh kernel read can admit this build.
    sample_raw = packet['postfailure_memory_sample'].encode()
    require(sha(sample_raw) == POSTFAILURE_MEMORY_SHA,
            'postfailure memory evidence changed')
    sample = json.loads(sample_raw)
    require(sample['fixed_collection_completed'] is True and
            sample['Main_actions'] == sample['files_written'] ==
            sample['resource_or_policy_changes'] == sample['stop_or_kill_actions'] == 0,
            'postfailure evidence is not the fixed read-only collection')
    require_original_attempt_absent(scope)
    return {'schema': 1, 'prior_failed_fence_terminal_sha256': PRIOR_FAILURE_SHA,
            'postfailure_memory_sample_sha256': POSTFAILURE_MEMORY_SHA,
            'sample_observed_utc': sample['finished_utc'],
            'historical_sample_is_not_build_admission': True,
            'original_attempt_must_remain_absent_before_inner_call': True,
            'original_controller_and_resource_gates_unchanged': True,
            'separately_reviewed_one_shot_readmission': True,
            'automatic_retry': False}

'''
    new = old.replace("FENCE_ROOT = ROOT / 'build-fences-01'", "FENCE_ROOT = ROOT / 'build-fences-02'")
    assert new != old
    anchor = '\n\ndef run(packet):\n'
    assert new.count(anchor) == 1
    new = new.replace(anchor, '\n' + insert + '\ndef run(packet):\n')
    anchor = "    require(not FENCE_ROOT.exists() and not FENCE_ROOT.is_symlink(), 'fence root already exists; reconcile exact job')\n"
    assert new.count(anchor) == 1
    new = new.replace(anchor, "    readmission = readmission_contract(packet, scope)\n" + anchor)
    anchor = "    FENCE_ROOT.mkdir(mode=0o700)\n"
    assert new.count(anchor) == 1
    new = new.replace(anchor, anchor + "    save('prior-failed-fence-terminal.json', packet['prior_failed_fence_terminal'].encode())\n    save('postfailure-memory-sample.json', packet['postfailure_memory_sample'].encode())\n    save('readmission.json', readmission)\n")
    anchor = "        attempted = True\n        inner_code = scope['main'](['--build', '--preparation-sha256', PREPARATION_SHA])\n"
    assert new.count(anchor) == 1
    new = new.replace(anchor, "        require_original_attempt_absent(scope)\n" + anchor)
    ast.parse(new)
    prior_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(old).body if isinstance(n, ast.FunctionDef)}
    next_functions = {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(new).body if isinstance(n, ast.FunctionDef)}
    unchanged = sorted(name for name in prior_functions if name != 'run')
    assert all(prior_functions[name] == next_functions[name] for name in unchanged)
    packet['outer_source'] = new
    packet['outer_sha256'] = sha(new.encode())
    packet['prior_failed_fence_terminal'] = failed.decode()
    packet['postfailure_memory_sample'] = sample.decode()
    assert packet['controller_source'] == json.loads(packet_raw)['controller_source']
    assert packet['snapshot_source'] == json.loads(packet_raw)['snapshot_source']
    new_packet = encode(packet)
    outer_sha = sha(new.encode())
    wrapper = ("import sys,hashlib,json;raw=sys.stdin.buffer.read();assert hashlib.sha256(raw).hexdigest()==" + repr(sha(new_packet)) + ";packet=json.loads(raw);source=packet['outer_source'];assert hashlib.sha256(source.encode()).hexdigest()==" + repr(outer_sha) + ";scope={'__name__':'__main__','__file__':'<verified-combined06-go5-streaming-readmission02>','PACKET':packet};exec(compile(source,'fenced_build_streaming.py','exec'),scope,scope)")
    request['args'] = ['-I', '-c', wrapper, '--execute-once']
    request['stdin'] = new_packet.decode()
    request['idempotency_key'] = 'pocket4-native-combined06-go5-streaming-fenced-cold-engine-flag0-build-02-20261105'
    old_request = json.loads((OLD / 'exact-request.json').read_bytes())
    unchanged_request = sorted(set(request) - {'args', 'stdin', 'idempotency_key'})
    assert all(request[name] == old_request[name] for name in unchanged_request)
    patch = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='build-request-01/fenced_build_streaming.py', tofile='readmission02/fenced_build_streaming.py'))
    files = {
        'fenced_build_streaming.py': new.encode(),
        'verified-source-packet.json': new_packet,
        'exact-request.json': encode(request),
        'outer01-to-readmission02.patch': patch.encode(),
        'references/prior-failed-fence-terminal.json': failed,
        'references/postfailure-memory-sample.json': sample,
    }
    pins = json.loads((OLD / 'REQUEST_PINS.json').read_bytes())
    pins['state'] = 'SEPARATELY_REVIEWED_READMISSION_REQUEST_NOT_SUBMITTED'
    pins['original_failed_fence_preserved'] = True
    pins['new_fence_directory'] = 'build-fences-02'
    pins['original_inner_attempt_directory'] = 'attempt-01'
    pins['original_attempt_must_remain_absent'] = True
    pins['prior_failure_sha256'] = FAILED_SHA
    pins['postfailure_memory_evidence_sha256'] = MEMORY_SHA
    pins['historical_sample_used_for_admission'] = False
    pins['unchanged_outer_functions_by_AST'] = unchanged
    pins['unchanged_request_fields'] = unchanged_request
    pins['inner_controller_byte_identical'] = True
    pins['Main_snapshot_byte_identical'] = True
    pins['idempotency_key'] = request['idempotency_key']
    pins['files'] = {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in files.items()}
    files['REQUEST_PINS.json'] = encode(pins)
    NEW.mkdir(mode=0o700)
    for name, raw in files.items():
        path = NEW / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
    print(json.dumps({'directory': str(NEW), 'files': pins['files'], 'REQUEST_PINS': {'bytes': len(files['REQUEST_PINS.json']), 'sha256': sha(files['REQUEST_PINS.json'])}}, indent=2))


if __name__ == '__main__':
    main()
