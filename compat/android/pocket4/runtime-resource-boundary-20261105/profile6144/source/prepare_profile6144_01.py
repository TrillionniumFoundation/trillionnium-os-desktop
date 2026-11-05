#!/usr/bin/python3 -I
"""Prepare a new strict host-only verification profile for observed TasksMax6144.

The original activation/transaction remain byte-identical. This creates only a
new private evidence/controller directory; it never enters Android, writes a
cgroup/configuration file, reloads a service, or selects replacement processes.
"""
from pathlib import Path
import argparse
import ast
import copy
import datetime
import difflib
import hashlib
import json
import os
import stat
import subprocess
import types

OUT = Path('/home/alex/work/pocket4-runtime-profile-20261105-r12-6144-01')
OLD_TX = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
OLD_TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
OLD_ACT = Path('/home/alex/work/pocket4-app-production-20261104-r10/deployment-preparation/activation-after-01.json')
OLD_ACT_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
CONFIG_PROOF = Path('/home/alex/work/pocket4-main-runtime-boundary-20261105-r12-04/result.json')
CONFIG_PROOF_SHA = 'da54529e07d1434082773c387ef2b0333345f3d1f4fca81c75043705b8ddaa7c'
EPOCH_SHA = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'
EXPECTED_LIMITS = {'cpu.max': '200000 100000', 'memory.high': '5368709120',
                   'memory.max': '6442450944', 'memory.swap.max': 'max', 'pids.max': '6144'}
NEW_ACT = OUT / 'activation-after-01.json'
NEW_TX = OUT / 'camera_transaction.py'
PROPERTIES = ('TasksMax', 'EffectiveTasksMax', 'TasksAccounting', 'ControlGroup', 'FragmentPath',
              'DropInPaths', 'NeedDaemonReload', 'InvocationID', 'ExecMainPID',
              'ActiveEnterTimestampMonotonic', 'CPUQuotaPerSecUSec', 'MemoryHigh', 'MemoryMax', 'MemorySwapMax')

def require(value, message):
    if not value:
        raise RuntimeError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def first_read(path, expected):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= 1048576, 'BOOTSTRAP_INPUT_SCOPE')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(1048577)
        after = os.fstat(fd)
        require(len(raw) == before.st_size and sha(raw) == expected and all(getattr(before, k) == getattr(after, k) for k in ('st_dev', 'st_ino', 'st_mtime_ns', 'st_ctime_ns', 'st_size')), 'BOOTSTRAP_INPUT_CHANGED')
        return raw
    finally:
        os.close(fd)

def module(raw, path, name):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value

def normalized_tree(raw):
    tree = ast.parse(raw)
    replaced = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('ACTIVATION', 'ACTIVATION_SHA'):
            replaced.append(node.targets[0].id)
            node.value = ast.Constant('NORMALIZED_ACTIVATION_BINDING_ONLY')
    require(sorted(replaced) == ['ACTIVATION', 'ACTIVATION_SHA'], 'EXACT_TWO_BINDINGS_REQUIRED')
    return ast.dump(tree, include_attributes=False)

def main():
    require(os.geteuid() == 0 and not os.path.lexists(OUT), 'NEW_HOST_ONLY_PROFILE_REQUIRED')
    old_source = first_read(OLD_TX, OLD_TX_SHA)
    tx = module(old_source, OLD_TX, 'original_transaction_for_profile_preparation')
    old_activation_raw = tx.read_regular(OLD_ACT, OLD_ACT_SHA)
    original = json.loads(old_activation_raw)
    proof_raw = tx.read_regular(CONFIG_PROOF, CONFIG_PROOF_SHA)
    proof = json.loads(proof_raw)
    require(proof['before']['limits'] == proof['after']['limits'] == EXPECTED_LIMITS and proof['limit_consistency'], 'CONFIGURED_LIMIT_PROOF_DIFFERS')
    require(proof['fixed_framework_and_host_identity_verified_twice'] and proof['after']['epoch_sha256'] == EPOCH_SHA, 'CONFIGURATION_EPOCH_PROOF_DIFFERS')
    require(proof['systemd_properties']['TasksMax'] == proof['systemd_properties']['EffectiveTasksMax'] == '6144' and proof['systemd_properties']['NeedDaemonReload'] == 'no', 'EFFECTIVE_SYSTEMD_LIMIT_NOT_PROVEN')
    expected_old = dict(EXPECTED_LIMITS, **{'pids.max': '12288'})
    require(original['limits'] == expected_old and original['framework_epoch']['sha256'] == EPOCH_SHA, 'ORIGINAL_RESOURCE_PROFILE_DIFFERS')
    epoch = tx.load_module(tx.EPOCH_SOURCE, tx.EPOCH_SOURCE_SHA, 'original_epoch_for_profile_preparation')
    held_raw = tx.read_regular(OLD_TX.parent / 'references/held_runtime_r5.py', tx.HELD_SHA)
    before_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def boundary_old_rejection():
        old = tx.CameraSession(OUT / 'never-entered-old-session')
        old.activation, old.epoch = original, epoch
        try:
            old.guard()
        except RuntimeError as error:
            require(str(error) == 'MAIN_LIMITS_CHANGED', 'ORIGINAL_GUARD_FAILED_FOR_ANOTHER_REASON')
        else:
            raise RuntimeError('ORIGINAL_GUARD_NO_LONGER_REPORTS_THE_OBSERVED_CHANGE')
        actual = {key: (Path('/sys/fs/cgroup/system.slice/droidloomd.service') / key).read_text().strip() for key in EXPECTED_LIMITS}
        require(actual == EXPECTED_LIMITS, 'CURRENT_LIMITS_CHANGED_AGAIN')
        return actual

    before_limits = boundary_old_rejection()
    configured_sources = []
    for source in proof['resource_configuration_files']:
        path = Path(source['canonical'])
        require(path.resolve(strict=True) == path, 'CONFIGURATION_CANONICAL_PATH_CHANGED')
        data = tx.read_regular(path, source['sha256'], maximum=65536)
        require(len(data) == source['bytes'], 'CONFIGURATION_SIZE_CHANGED')
        configured_sources.append({'path': str(path), 'bytes': len(data), 'sha256': sha(data)})
    tool = proof['systemd_query']
    executable = Path(tool['executable'])
    require(executable == Path('/usr/bin/systemctl') and executable.resolve(strict=True) == executable, 'EXACT_SYSTEMCTL_REQUIRED')
    tool_bytes = tx.read_regular(executable, tool['tool']['sha256'])
    tool_stat = executable.stat()
    require(tool_stat.st_uid == 0 and not tool_stat.st_mode & 0o022 and len(tool_bytes) == tool['tool']['bytes'], 'SYSTEMCTL_IDENTITY_CHANGED')
    argv = ['/usr/bin/systemctl', '--system', 'show', 'droidloomd.service', '--no-pager', '--property=' + ','.join(PROPERTIES)]
    require(argv == tool['argv'], 'QUERY_ARGV_DIFFERS')
    query = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=10, start_new_session=True,
                           env={'PATH': '/usr/bin:/usr/sbin', 'LANG': 'C.UTF-8', 'SYSTEMD_PAGER': ''})
    require(query.returncode == 0 and len(query.stdout) <= 16384 and not query.stderr, 'READ_ONLY_SYSTEMD_QUERY_FAILED')
    properties = dict(line.split('=', 1) for line in query.stdout.decode('utf-8', 'strict').splitlines())
    require(properties == proof['systemd_properties'], 'OBSERVED_SYSTEMD_CONFIGURATION_CHANGED')
    require(tx.read_regular(executable, tool['tool']['sha256']) == tool_bytes, 'SYSTEMCTL_CHANGED_AFTER_QUERY')

    activation = copy.deepcopy(original)
    activation['limits']['pids.max'] = '6144'
    check = copy.deepcopy(activation)
    check['limits']['pids.max'] = '12288'
    require(check == original, 'ACTIVATION_SEMANTIC_CHANGE_NOT_SCOPED')
    activation_raw = (json.dumps(activation, indent=2, sort_keys=True) + '\n').encode()
    activation_sha = sha(activation_raw)
    source_text = old_source.decode('utf-8')
    old_binding = 'ACTIVATION = Path(' + repr(str(OLD_ACT)) + ')'
    new_binding = 'ACTIVATION = Path(' + repr(str(NEW_ACT)) + ')'
    old_pin = 'ACTIVATION_SHA = ' + repr(OLD_ACT_SHA)
    new_pin = 'ACTIVATION_SHA = ' + repr(activation_sha)
    require(source_text.count(old_binding) == source_text.count(old_pin) == 1, 'TRANSACTION_BINDING_SCOPE')
    new_source = source_text.replace(old_binding, new_binding).replace(old_pin, new_pin).encode()
    require(normalized_tree(old_source) == normalized_tree(new_source), 'TRANSACTION_LOGIC_CHANGED')
    require(boundary_old_rejection() == before_limits, 'LIMITS_CHANGED_BEFORE_HOST_STAGE')

    os.umask(0o077)
    OUT.mkdir(mode=0o750)
    os.chown(OUT, 0, 1000)
    os.chmod(OUT, 0o750)
    references = OUT / 'references'
    references.mkdir(mode=0o750)
    os.chown(references, 0, 1000)
    os.chmod(references, 0o750)
    exports = [tx.write_new(OUT / 'activation-before-original.json', old_activation_raw, alex_readable=True),
               tx.write_new(NEW_ACT, activation_raw, alex_readable=True),
               tx.write_new(NEW_TX, new_source, alex_readable=True),
               tx.write_new(references / 'held_runtime_r5.py', held_raw, alex_readable=True),
               tx.write_new(OUT / 'configuration-proof-original.json', proof_raw, alex_readable=True)]
    patch = ''.join(difflib.unified_diff(source_text.splitlines(True), new_source.decode().splitlines(True),
                                       fromfile='original-b227/camera_transaction.py', tofile='configured-6144/camera_transaction.py'))
    exports.append(tx.write_new(OUT / 'transaction-change.patch', patch.encode(), alex_readable=True))
    current_tx = tx.load_module(NEW_TX, sha(new_source), 'configured_6144_transaction_read_only_check')
    current = current_tx.CameraSession(OUT / 'never-entered-new-session')
    current.activation = json.loads(current_tx.read_regular(NEW_ACT, activation_sha))
    current.epoch = epoch
    new_guard = current.guard()
    require(new_guard['epoch_sha256'] == EPOCH_SHA and current.target is None, 'READ_ONLY_GUARD_SCOPE')
    require(boundary_old_rejection() == before_limits, 'OLD_GUARD_OR_LIMITS_CHANGED_AFTER_STAGE')
    require(tx.read_regular(OLD_TX, OLD_TX_SHA) == old_source and tx.read_regular(OLD_ACT, OLD_ACT_SHA) == old_activation_raw, 'ORIGINAL_PROFILE_MODIFIED')
    for source in configured_sources:
        tx.read_regular(source['path'], source['sha256'], maximum=65536)
    current.guard()
    result = {'schema': 'pocket4-strict-configured-resource-profile/v1',
              'state': 'HOST_PROFILE_PREPARED_AND_READ_ONLY_GUARDS_VERIFIED',
              'started_utc': before_utc, 'finished_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'original_activation_sha256': OLD_ACT_SHA, 'original_transaction_sha256': OLD_TX_SHA,
              'original_files_unchanged': True, 'original_guard_still_rejects_changed_limit': True,
              'new_activation': {'path': str(NEW_ACT), 'sha256': activation_sha, 'bytes': len(activation_raw)},
              'new_transaction': {'path': str(NEW_TX), 'sha256': sha(new_source), 'bytes': len(new_source)},
              'only_activation_semantic_change': {'path': 'limits.pids.max', 'from': '12288', 'to': '6144'},
              'only_transaction_AST_changes': ['ACTIVATION', 'ACTIVATION_SHA'], 'all_guard_and_other_logic_AST_unchanged': True,
              'guard_before_after_limits': before_limits, 'new_guard': new_guard,
              'configuration_evidence_sha256': CONFIG_PROOF_SHA, 'configured_source_pins': configured_sources,
              'read_only_systemd_properties': properties, 'exports': exports,
              'scope': {'android_commands': 0, 'namespace_entries': 0, 'ui_actions': 0, 'package_actions': 0,
                        'cgroup_writes': 0, 'system_configuration_writes': 0, 'service_reloads_or_restarts': 0,
                        'signals_to_existing_processes': 0, 'fresh_main_selection': False},
              'limitations': ['The conflicting 50/90 TasksMax configuration is retained, not repaired.',
                              'This binds the observed effective6144 budget; it does not restore12288.',
                              'No App gate, complete runtime release, or stability qualification is granted.'],
              'app_actions_allowed_by_this_preparation': False}
    record = tx.write_new(OUT / 'profile-creation-result.json', result, alex_readable=True)
    print(json.dumps({'state': result['state'], 'result': record, 'new_activation': result['new_activation'], 'new_transaction': result['new_transaction']}), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        main()
    else:
        print('INERT: new host-only resource profile; no Android or Main configuration operation.')
