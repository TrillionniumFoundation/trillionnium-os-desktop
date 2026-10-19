#!/usr/bin/env python3
"""Derive the authorized two-page capture from the existing R7 owned harness."""
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = BASE.parent / 'repo'
PATHS = ['tests/ui/probe-chat-workspace.py', 'tests/ui/x11-ime-client.py',
         'tests/ui/probe-original-hepta-shell.py', 'tests/integration/hepta/run_original_agentd.py']

OUTSIDE = r'''def outside(args):
    source = args.source.resolve(strict=True)
    native = args.native_root.resolve(strict=True)
    binary_dir = args.binaries.resolve(strict=True)
    output = args.output.resolve()
    source_before = sources(source)
    require(source_before['head'] == args.expected_head and not source_before['status'], 'clean expected product source required')
    harness_before = {str(p.relative_to(ROOT)): digest(p) for p in ROOT.rglob('*.py')}
    restoration = json.loads((native / 'receipts/environment-restoration.json').read_text())
    require(restoration['status'] == 'passed', 'fixed private dependency restoration required')
    build = json.loads(args.build_receipt.read_text())
    require(build['source_equal'] is True and build['source_before'] == build['source_after'], 'successful unchanged build source required')
    compiled = build['source_before']
    for name, entry in compiled['files'].items():
        require(digest(source / name) == entry['sha256'] and (source / name).stat().st_size == entry['bytes'], 'compiled source mismatch: ' + name)
    actual_binaries = binaries(binary_dir)
    for name, record in actual_binaries.items():
        require(all(build['binaries'][name][key] == value for key, value in record.items()), 'build ELF mismatch: ' + name)
    output.mkdir(mode=0o700)
    (output / 'inside').mkdir(mode=0o700)
    font = native / 'sysroot/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    require(digest(font) == restoration['font']['sha256'], 'restored font identity changed')
    binding = {'schema': 'r9-native-two-page-input-v1', 'source': source_before,
        'compiled_source': compiled, 'compiled_source_closure_equal': True,
        'harness_files': harness_before, 'binaries': actual_binaries,
        'build_receipt': build, 'build_receipt_sha256': digest(args.build_receipt),
        'harness_derivation_sha256': digest(native / 'harness-derivation.json'),
        'environment_restoration_sha256': digest(native / 'receipts/environment-restoration.json'),
        'font_sha256': digest(font),
        'namespace': ['owned_mount', 'user', 'ipc', 'network', 'uts', 'pid'],
        'proc_view': 'read_only_host_proc_for_Linux_host_resource_metrics',
        'host_desktop_bound': False, 'scope': 'default Workspace/Chat and embedded Console pixels only; fresh empty owned Session'}
    write(output / 'inside/input-binding.json', binding)
    script = Path('/test-harness/tests/ui/probe-chat-workspace.py')
    cmd = ['/usr/bin/bwrap', '--unshare-user', '--unshare-ipc', '--unshare-net', '--unshare-uts', '--unshare-pid',
        '--die-with-parent', '--new-session', '--hostname', 'r9-native-workspace',
        '--ro-bind', '/usr', '/host/usr', '--ro-bind', str(native / 'sysroot'), '/r9-sysroot',
        '--ro-bind', str(native / 'view02/usr'), '/usr', '--symlink', 'usr/bin', '/bin',
        '--symlink', 'usr/sbin', '/sbin', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
        '--ro-bind', '/etc', '/etc', '--ro-bind', '/proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/root', '--dir', '/run',
        '--ro-bind', str(ROOT), '/test-harness', '--ro-bind', str(source), '/test-source',
        '--ro-bind', str(binary_dir), '/ui-bin', '--bind', str(output / 'inside'), '/capture', '--chdir', '/capture',
        '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'LANG', 'C.UTF-8',
        '--setenv', 'LC_ALL', 'C.UTF-8', '--setenv', 'TZ', 'UTC',
        '/usr/bin/python3', '-B', str(script), '--inside', '/capture']
    write(output / 'namespace-command.json', cmd)
    guard = module('chat_outer_guard', ROOT / 'tests/integration/hepta/run_original_agentd.py')
    require(guard.child_anchor_available(), 'outer owned-child anchor required')
    wrapped = [sys.executable, '-B', str(Path(__file__)), '--exec-parent', str(os.getpid()), '--', *cmd]
    record = {'started_unix_ms': now(), 'status': 'running', 'namespace_command_sha256': digest(output / 'namespace-command.json')}
    failure = None
    group = None
    try:
        with (output / 'namespace.stdout.log').open('xb') as stdout, (output / 'namespace.stderr.log').open('xb') as stderr:
            child = subprocess.Popen(wrapped, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(child)
        record['owned_namespace_leader_pid'] = child.pid
        write(output / 'launch.json', record)
        print(json.dumps({'output': str(output), 'status': 'running', 'namespace_leader_pid': child.pid}), flush=True)
        group.wait_exit(300)
    except BaseException as error:
        failure = repr(error)
    finally:
        if group is not None and group.armed:
            group.signal_group(signal.SIGKILL)
            group.wait_exit(5)
            record['exit_code'] = group.reap()
        record.update(completed_unix_ms=now(), failure=failure,
            product_source_unchanged=sources(source) == source_before,
            harness_source_unchanged={str(p.relative_to(ROOT)): digest(p) for p in ROOT.rglob('*.py')} == harness_before,
            executable_bytes_unchanged=binaries(binary_dir) == actual_binaries,
            namespace_guard_armed_after=group.armed if group else None)
        try:
            inner_path = output / 'inside/capture-receipt.json'
            inner_receipt = json.loads(inner_path.read_text())
            record['inner_receipt_status'] = inner_receipt['status']
            record['inner_receipt_sha256'] = digest(inner_path)
        except (OSError, ValueError, KeyError) as error:
            record['inner_receipt_error'] = repr(error)
        inner_complete = record.get('inner_receipt_status') == 'completed_native_capture_requires_independent_visual_review'
        record['status'] = 'completed' if inner_complete and record.get('exit_code') == 0 and failure is None and all(record[k]
            for k in ('product_source_unchanged', 'harness_source_unchanged', 'executable_bytes_unchanged')) else 'failed'
        write(output / 'receipt.json', record)
    require(record['status'] == 'completed', 'native capture failed; raw evidence retained')


'''

FINISH = '''            elif action == 'finish':
                require(len(report['screenshots']) == 2 and not report['exports'], 'exact two-page scope required')
                value = snapshot(label + '-empty-session')
                require(value['session_instance'] == report['session_a']['instance'], 'same Session required')
                require(all(not x['snapshot']['tasks'] for x in report['snapshot_observations']), 'no host apps may be launched in this scope')
                require(all(x['snapshot']['session_instance'] == report['session_a']['instance'] for x in report['snapshot_observations']), 'all snapshots must belong to the same Session')
                require(value['hepta']['connection'] == 'not_configured' and value['hepta']['last_observation'] is None, 'no original or fixture Hepta source permitted')
                require(window(label + '-same-shell', shell.process.pid, 'trill-shell') == report['shell'], 'same actual Shell/window required')
                report['status'] = 'completed_native_capture_requires_independent_visual_review'
'''


def main():
    entries = []
    for name in PATHS:
        raw = (REPO / name).read_bytes()
        for directory in ['harness-origin', 'harness']:
            target = BASE / directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(raw)
        entries.append({'path': name, 'original_sha256': hashlib.sha256(raw).hexdigest(), 'original_bytes': len(raw)})
    target = BASE / 'harness' / PATHS[0]
    old = target.read_text()
    new = old.replace('Source-bound manual input capture for the native Rust chat workspace.',
                      'R9 two-page actual native Workspace/Chat and Console capture.')
    new = new.replace('The bounded input queue drives XTEST, actual Session IPC and explicit lifecycle\nchanges.',
                      'The bounded input queue permits only a pointer click, a screenshot and finish.\nActual Session IPC must remain empty and bound to one Session instance.')
    new = new.replace("'schema': 'r7-native-chat-capture-v1'", "'schema': 'r9-native-two-page-capture-v1', 'host_task_lifecycle_exercised': False, 'scope': 'two_pages_fresh_empty_session'")
    new = new.replace('deadline = time.monotonic() + 900', 'deadline = time.monotonic() + 240')
    new = new.replace("            action = request['action']", "            action = request['action']\n            require(action in ('click', 'screenshot', 'finish'), 'two-page capture input only')")
    start = new.index("            elif action == 'finish':\n")
    end = new.index("            else:\n                raise RuntimeError('unsupported bounded action')", start)
    new = new[:start] + FINISH + new[end:]
    start = new.index('def outside(args):\n')
    end = new.index("if __name__ == '__main__':", start)
    new = new[:start] + OUTSIDE + new[end:]
    target.write_text(new)
    patch = ''.join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                       fromfile='tracked/tests/ui/probe-chat-workspace.py',
                                       tofile='r9-private/tests/ui/probe-chat-workspace.py'))
    (BASE / 'harness.patch').write_text(patch)
    compile(new, str(target), 'exec')
    manifest = {'schema': 'r9-two-page-harness-derivation-v1', 'original_files': entries,
                'derivation_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'patch_sha256': hashlib.sha256(patch.encode()).hexdigest(),
                'derived_files': {name: {'sha256': hashlib.sha256((BASE / 'harness' / name).read_bytes()).hexdigest(),
                                         'bytes': (BASE / 'harness' / name).stat().st_size} for name in PATHS},
                'scope': 'Only the external capture consumer/receipt binding and finish condition differ. Product source and original harness remain unchanged.'}
    (BASE / 'harness-derivation.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(json.dumps(manifest, sort_keys=True))


if __name__ == '__main__':
    main()
