"""Independently retire only the original storage generation, preserving every failure."""
import hashlib, json, pathlib, sys, types
C = pathlib.Path(__file__).parent
assert len(sys.argv) in (4, 5)
role, accepted, admission_sha = sys.argv[1:4]
assert role in ('server', 'controller', 'finalize')
raw = (C / 'SOURCE-MANIFEST.json').read_bytes(); assert hashlib.sha256(raw).hexdigest() == accepted
manifest = json.loads(raw)
for name in ('common.py', 'storage_support.py', 'rotation_support.py'):
    body = (C / name).read_bytes(); assert hashlib.sha256(body).hexdigest() == manifest['files'][name]['sha256']
    exec(compile(body, str(C / name), 'exec'))
contract = json.loads((C / 'contract.json').read_bytes())
admission_ref, admission = storage_admission(C, accepted, admission_sha, contract)
need(os.getresuid() == os.getresgid() == (0, 0, 0), 'root independent storage retirement')
host = 'desktop' if role == 'controller' else 'pocket4'
need(str(C) == contract['desktop_source' if host == 'desktop' else 'p4_source'], 'exact retirement source')
boot_is(contract['hosts'][host]['boot']); check_tools(contract, host); _, sources = sealed_sources(C, accepted)
Q = P(contract['desktop_root'] if host == 'desktop' else contract['p4_root'])
directory = C / (role + '-retirement')
if not directory.exists(): directory.mkdir(mode=0o700)
need(directory.resolve() == directory and directory.lstat().st_uid == 0, 'original independent journal')
attempt = directory / ('observation-' + str(time.time_ns())); attempt.mkdir(mode=0o700); commands = Commands(attempt)
destination = C / (role + '-INDEPENDENT-RETIREMENT.json')
unit = contract[role + '_unit']; dispatch = C / (role + '-dispatch')
if destination.exists():
    ref, previous = root_record(destination)
    need(previous['nonce'] == contract['nonce'] and previous['retirement_passed'] is True and
         previous['source_manifest_sha256'] == accepted and previous['admission_sha256'] == admission_sha,
         'only the original finished independent retirement')
    state = show(commands, unit)
    need(state['MainPID'] == '0' and state['ActiveState'] == 'inactive' and
         not (P('/sys/fs/cgroup/system.slice') / unit).exists(), 'same original unit remains retired')
    print(json.dumps({'reused_original_retirement': ref, 'new_starts': 0}, sort_keys=True)); raise SystemExit(0)
if not (dispatch / (unit + '.actual.json')).exists():
    recovered = OwnedUnit.recover(commands, dispatch, unit)
    if recovered.held is not None: recovered.held.close()
original_ref, body = pin(dispatch / (unit + '.actual.json')); original = json.loads(body)
need(original['unit'] == unit and original['argv'][0:3] == ['/usr/bin/python3', '-I', '-B'] and
     original['argv'][4:6] == [accepted, admission_sha], 'original fixed executable and accepted source cohort')
if role == 'server' and (Q / 'SERVER-READY.json').exists():
    need(len(sys.argv) == 5, 'exact desktop retirement hash before stopping an advertised server')
    peer_ref, body = pin(Q / 'DESKTOP-INDEPENDENT-RETIREMENT.json'); peer = json.loads(body)
    need(peer_ref['sha256'] == sys.argv[4] and peer['role'] == 'controller' and peer['nonce'] == contract['nonce'] and
         peer['source_manifest_sha256'] == accepted and peer['admission_sha256'] == admission_sha and
         peer['retirement_passed'] is True and peer['original_module_device_mount_state_restored'] is True,
         'actual independently detached original desktop before stopping server')
else: need(len(sys.argv) == 4, 'no extra retirement arguments; an unadvertised server cannot have admitted this controller')
terminal_path = directory / 'ORIGINAL-TERMINAL.json'
state = show(commands, unit)
if state.get('LoadState') == 'not-found':
    _, terminal_document = root_record(terminal_path)
    need(terminal_document['original'] == original_ref and terminal_document['nonce'] == contract['nonce'],
         'durable original terminal before an uncertain release acknowledgement')
    terminal = terminal_document['state']
else:
    need(state['Description'] == contract[role + '_description'] and state['InvocationID'] == original['InvocationID'],
         'only the original native storage invocation may retire')
    if state['MainPID'] != '0':
        need(role in ('server', 'controller') and state['MainPID'] == str(original['pid']),
             'only original live owner/server supports requested shutdown')
        held = HeldProcess(original['pid'])
        try:
            need(held.start == original['start_ticks'] and
                 proc_ref(held.pid)['cmdline'] == [x.encode() for x in original['argv']], 'held original requested-stop generation')
            save(attempt / 'REQUESTED-STOP.json', {'original': original_ref, 'state': state, 'start_ticks': held.start})
            held.signal(signal.SIGTERM); held.retired(1100)
        finally: held.close()
        state = show(commands, unit)
    need(state['InvocationID'] == original['InvocationID'] and state['MainPID'] == '0' and
         state['ExecMainCode'] in ('1', '2', '3'), 'actual original terminal wait status')
    terminal = state
    if not terminal_path.exists():
        save(terminal_path, {'original': original_ref, 'nonce': contract['nonce'], 'state': terminal}, 0o444)
    else:
        _, previous = root_record(terminal_path)
        need(previous['original'] == original_ref and previous['state']['InvocationID'] == terminal['InvocationID'],
             'same original preserved terminal')
again = show(commands, unit); stop_error = None
if again.get('LoadState') != 'not-found':
    need(again['InvocationID'] == original['InvocationID'] and again['MainPID'] == '0', 'same terminal immediately before release')
    try: commands.run('release-original-storage-unit', ['/usr/bin/systemctl', 'stop', unit], 45)
    except BaseException as error: stop_error = str(error)
after = show(commands, unit)
if after.get('ActiveState') == 'failed':
    need(after['InvocationID'] == original['InvocationID'], 'only original failed storage unit reset')
    commands.run('release-original-storage-failure', ['/usr/bin/systemctl', 'reset-failed', unit], 15)
    after = show(commands, unit)
need(after['MainPID'] == '0' and after['ActiveState'] == 'inactive' and not P(original['cgroup']).exists(),
     'original storage native unit and all cgroup processes gone')
filename = {'controller': 'DESKTOP-RESULT.json', 'server': 'SERVER-RESULT.json', 'finalize': 'FILESYSTEM-RESULT.json'}[role]
result_ref = result = None
if (Q / filename).exists():
    result_ref, body = pin(Q / filename); result = json.loads(body)
    need(result['nonce'] == contract['nonce'] and result['source_manifest_sha256'] == accepted and
         result['admission_sha256'] == admission_sha, 'original storage result identity')
recovery = None; socket_retirement = None; module_restored = None; offline_image = None
if role == 'controller':
    if not result or result.get('original_module_device_mount_state_restored') is not True:
        role_retirements = retire_registered_roles(commands, Q, contract, accepted, admission_sha)
        early_failure = result is None and not (Q / 'HOST-MOUNTS-BEFORE.json').exists()
        if early_failure:
            need(not (Q / 'MODULE-INTENT.json').exists() and not (Q / 'OWNER-READY.json').exists() and
                 not P('/sys/module/nbd').exists() and not list(P('/sys/class/block').glob('nbd*')) and
                 not list(P('/dev').glob('nbd[0-9]*')), 'actual pre-mutation failure retained original zero-device state')
            for key in ('client_unit', 'ssh_unit'):
                value = show(commands, contract[key])
                need(value['MainPID'] == '0' and value['ActiveState'] == 'inactive' and
                     not (P('/sys/fs/cgroup/system.slice') / contract[key]).exists(), 'no subordinate actor before mutation witness')
            recovery = {'failed_before_any_mount_or_module_command': True,
                        'original_module_device_mount_state_restored': True,
                        'original_result_missing': True, 'mounted_role_retirements': role_retirements}
        elif result is None:
            _, before_mounts = root_record(Q / 'HOST-MOUNTS-BEFORE.json')
            need(before_mounts['nonce'] == contract['nonce'] and before_mounts['native']['InvocationID'] == original['InvocationID'],
                 'actual pre-mutation host mount witness')
            recovery_context = {'nonce': contract['nonce'], 'source_manifest_sha256': accepted,
                'admission_sha256': admission_sha, 'native': before_mounts['native'],
                'host_global_mounts_sha256': before_mounts['sha256'],
                'commands': [json.loads(pin(p)[1]) for p in sorted((Q / 'commands').glob('command-*.json'))]}
            if (Q / 'DEVICE-BEFORE-ATTACH.json').exists():
                _, device = root_record(Q / 'DEVICE-BEFORE-ATTACH.json')
                need(device['nonce'] == contract['nonce'], 'actual original device witness')
                recovery_context['new_device_identity'] = device['identity']
            if (Q / 'OWNER-READY.json').exists():
                _, ready = root_record(Q / 'OWNER-READY.json')
                need(ready['nonce'] == contract['nonce'], 'actual original ready witness')
                for key in ('tunnel_socket_f9', 'relay_socket_f9'): recovery_context[key] = ready[key]
        else: recovery_context = result
        if not early_failure:
            module = types.ModuleType('_p4_storage_detached_recovery')
            module.__file__ = str(C / 'desktop_owner.py'); module._accepted = accepted; module._admission_sha = admission_sha
            body = pin(C / 'desktop_owner.py', manifest['files']['desktop_owner.py'])[1]
            exec(compile(body, module.__file__, 'exec'), module.__dict__)
            recovery = module.recover_detached_resources(commands, recovery_context)
            recovery['original_result_missing'] = result is None
            recovery['mounted_role_retirements'] = role_retirements
    need(not P('/sys/module/nbd').exists() and not list(P('/sys/class/block').glob('nbd*')) and
         not list(P('/dev').glob('nbd[0-9]*')), 'independent original zero-device state restored')
    module_restored = True
elif role == 'server' and (Q / 'SERVER-READY.json').exists():
    ready_ref, body = pin(Q / 'SERVER-READY.json'); ready = json.loads(body)
    need(ready['nonce'] == contract['nonce'], 'original server socket witness')
    socket_retirement = remove_retired_socket(Q / 'ipc/export.sock', ready['socket_f9'])
if role == 'server': offline_image = offline_image_observation(contract, admission)
sources_unchanged(sources); check_tools(contract, host); pin(admission_ref['path'], admission_ref)
host_before = json.loads(pin(dispatch / 'DISPATCH-HOST.json')[1])
need(host_mac_state() == host_before, 'host boot, kernel and MAC unchanged')
logs = []
for pattern in ('*.stdout', '*.stderr'):
    for path in sorted(dispatch.glob(pattern)):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC); os.fsync(fd); os.close(fd); logs.append(pin(path)[0])
functional = bool(result and result.get('passed', result.get('server_lifecycle_clean', False)) and
                  result.get('native', {}).get('InvocationID') == original['InvocationID'] and
                  terminal['ExecMainCode'] == '1' and terminal['ExecMainStatus'] == '0' and terminal['Result'] == 'success')
proof = {'schema': 'p4-production651-nbd-independent-retirement-v1', 'role': role, 'nonce': contract['nonce'],
    'source_manifest_sha256': accepted, 'admission_sha256': admission_sha, 'H_job_id': None,
    'retirement_passed': True, 'functional_result_passed': functional, 'actual_terminal': terminal,
    'actual_after': after, 'original': original_ref, 'result': result_ref, 'stop_ack_error': stop_error,
    'cgroup_absent': True, 'original_module_device_mount_state_restored': module_restored,
    'detached_recovery': recovery, 'socket_retirement': socket_retirement,
    'offline_original_image': offline_image,
    'source_and_tools_unchanged': True, 'host_kernel_and_MAC_unchanged': True,
    'whole_fsynced_native_logs': logs, 'commands': commands.records,
    'CURRENT_renewal_is_not_a_cleanup_blocker': True, 'Android_starts': 0, 'production_ready': False}
print(json.dumps(save(destination, proof, 0o444), sort_keys=True))
