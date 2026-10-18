#!/usr/bin/env python3
"""Source-bound manual input capture for the native Rust chat workspace.

Runs only freshly built project binaries in an owned Xvfb/PID/net namespace.
The bounded input queue drives XTEST, actual Session IPC and explicit lifecycle
changes. Screenshots always need independent visual review; queue ACKs, first
layout markers and exported JSON do not prove visible pixels on their own.
No original Agentd, signer, objective ingress, model or device is started.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
NAMES = ('trill-session', 'trill-shell', 'trill-app-window', 'trill-ctl')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.new')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    os.replace(temporary, path)


def now():
    return time.time_ns() // 1_000_000


def sources(source):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], text=True, timeout=30).strip()
    return {'head': git('rev-parse', 'HEAD'), 'tree': git('rev-parse', 'HEAD^{tree}'),
        'status': git('status', '--porcelain=v1', '--untracked-files=all'),
        'files': {p: digest(source / p) for p in git('ls-files', '--', 'ui', 'services/hepta-os').splitlines()
                  if (source / p).is_file()}}


def binaries(directory):
    result = {}
    for name in NAMES:
        path = directory / name
        require(path.is_file() and os.access(path, os.X_OK), 'real executable missing: ' + name)
        with path.open('rb') as stream:
            require(stream.read(4) == b'\x7fELF', 'ELF required: ' + name)
        result[name] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    return result


def inside(output):
    guard = module('chat_owned_guard', ROOT / 'tests/integration/hepta/run_original_agentd.py')
    capture = module('chat_framebuffer', ROOT / 'tests/ui/x11-ime-client.py')
    require(guard.child_anchor_available(), 'waitable owned child identities required')
    config = json.loads((output / 'input-binding.json').read_text())
    require(binaries(Path('/ui-bin')) == config['binaries'], 'bound executable bytes changed')
    env = dict(os.environ, WINIT_UNIX_BACKEND='x11', XMODIFIERS='@im=none',
        LIBGL_ALWAYS_SOFTWARE='1', LP_NUM_THREADS='2', MESA_SHADER_CACHE_DISABLE='true',
        TRILL_UI_CJK_FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        TRILL_UI_CJK_FONT_INDEX='0')
    for name in ('cache', 'config', 'state', 'data', 'runtime'):
        directory = output / name
        directory.mkdir(mode=0o700)
        key = 'XDG_RUNTIME_DIR' if name == 'runtime' else 'XDG_' + name.upper() + '_HOME'
        env[key] = str(directory)
    require(not any(k.startswith('TRILL_HEPTA_') for k in env), 'no Hepta endpoint permitted')
    queue = output / 'commands'
    queue.mkdir(mode=0o700)
    groups = []
    report = {'schema': 'r7-native-chat-capture-v1', 'status': 'running', 'started_unix_ms': now(),
        'input_path': 'XTEST_ASCII_and_primary_pointer_to_actual_X11_Rust_windows',
        'original_agentd_started': False, 'objective_submitted': False, 'model_called': False,
        'physical_input_qualified': False, 'IME_qualified': False, 'mobile_qualified': False,
        'synthetic_egui_events_used': False, 'screenshots': [], 'actions': [], 'processes': [],
        'snapshot_observations': [], 'exports': [], 'cleanup': []}
    display = None
    session = None
    shell = None
    deadline = time.monotonic() + 900

    def save():
        write(output / 'capture-progress.json', report)

    def spawn(label, argv):
        wrapped = [sys.executable, '-B', str(Path(__file__)), '--exec-parent', str(os.getpid()), '--', *argv]
        with (output / (label + '.stdout.log')).open('xb') as stdout, (output / (label + '.stderr.log')).open('xb') as stderr:
            process = subprocess.Popen(wrapped, env=env, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(process)
        groups.append((label, group))
        report['processes'].append({'label': label, 'namespace_pid': process.pid, 'command': argv})
        return group

    def alive(group):
        return group is not None and group.armed and group.observe_exit() is None

    def stop(label, group):
        require(group is not None and group.armed, 'owned group was already disarmed')
        code = guard.terminate_group(group)
        report['cleanup'].append({'label': label, 'namespace_pid': group.process.pid,
            'exit_code': code, 'guard_armed_after': group.armed, 'completed_unix_ms': now()})

    def command(label, argv, required=True):
        child = spawn(label, argv)
        failure = None
        try:
            child.wait_exit(12)
        except BaseException as error:
            failure = error
        # Kill any remaining group members while its unreaped leader anchors
        # the PGID; never signal a numeric ID after reap.
        child.signal_group(signal.SIGKILL)
        child.wait_exit(3)
        code = child.reap()
        data = (output / (label + '.stdout.log')).read_bytes()
        require(len(data) <= 1024 * 1024, 'bounded command output required')
        if failure:
            raise failure
        if required:
            require(code == 0, 'owned command failed: ' + label + ', exit ' + str(code))
        return code, data

    def snapshot(label, required=True):
        code, data = command(label, ['/ui-bin/trill-ctl', 'snapshot'], required)
        if code != 0:
            return None
        value = json.loads(data)
        require(value['type'] == 'snapshot', 'real Snapshot required')
        report['snapshot_observations'].append({'label': label, 'recorded_unix_ms': now(), 'snapshot': value})
        return value

    def session_ready(label):
        for attempt in range(100):
            require(alive(session), 'owned Session exited before readiness')
            value = snapshot(f'{label}-ready-{attempt:03}', required=False)
            if value:
                require(not value['tasks'], 'fresh private Session must begin empty')
                return value
            time.sleep(0.05)
        raise RuntimeError('bounded Session readiness timeout')

    def window(label, pid, klass):
        for attempt in range(80):
            code, data = command(f'{label}-window-{attempt:03}', ['xdotool', 'search', '--all',
                '--onlyvisible', '--pid', str(pid), '--class', '^' + klass + '$'], required=False)
            if code == 0 and data.strip():
                break
            time.sleep(0.05)
        values = data.decode().split()
        require(code == 0 and len(values) == 1 and values[0].isdigit(), 'one exact owned window required')
        xid = values[0]
        _, properties = command(label + '-properties', ['xprop', '-id', xid, 'WM_CLASS', '_NET_WM_PID'])
        require(klass.encode() in properties and ('= ' + str(pid)).encode() in properties, 'window PID/class mismatch')
        return {'xid': xid, 'namespace_pid': pid, 'class': klass}

    def screenshot(label):
        require(alive(shell), 'same Shell must remain alive for capture')
        command(label + '-raise', ['xdotool', 'windowraise', report['shell']['xid']])
        before = snapshot(label + '-before', required=alive(session))
        time.sleep(0.2)
        item = display.screenshot(output / (label + '.png'))
        item.update(captured_unix_ms=now(), shell=report['shell'], before_snapshot=label + '-before')
        after = snapshot(label + '-after', required=alive(session))
        if before and after:
            require(before['session_instance'] == after['session_instance'], 'Session changed during capture')
        item['after_snapshot'] = label + '-after'
        report['screenshots'].append(item)

    try:
        xvfb = spawn('Xvfb', ['/usr/bin/Xvfb', ':77', '-screen', '0', '1440x1000x24',
            '-nolisten', 'tcp', '-noreset', '-ac'])
        env['DISPLAY'] = ':77'
        for attempt in range(100):
            require(alive(xvfb), 'private Xvfb exited')
            code, _ = command(f'display-ready-{attempt:03}', ['xdpyinfo'], required=False)
            if code == 0:
                break
            time.sleep(0.05)
        require(code == 0, 'bounded display readiness timeout')
        os.environ.update(env)
        display = capture.Display()
        session = spawn('Session-A', ['/ui-bin/trill-session'])
        initial = session_ready('session-a')
        report['session_a'] = {'namespace_pid': session.process.pid, 'instance': initial['session_instance']}
        shell = spawn('Shell', ['/ui-bin/trill-shell'])
        for _ in range(160):
            require(alive(shell), 'Rust Shell exited before first layout')
            if b'TRILL_SHELL_FIRST_FRAME_V1\n' in (output / 'Shell.stdout.log').read_bytes():
                break
            time.sleep(0.05)
        else:
            raise RuntimeError('bounded Rust Shell first-layout timeout')
        report['shell'] = window('shell', shell.process.pid, 'trill-shell')
        screenshot('initial')
        save()
        write(output / 'ready.json', report['shell'])
        for sequence in range(1, 81):
            path = queue / f'{sequence:03}.json'
            while not path.exists():
                require(time.monotonic() < deadline, 'bounded input queue deadline exceeded')
                require(alive(shell) and alive(xvfb), 'owned UI process exited during input capture')
                time.sleep(0.05)
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), 'rb') as stream:
                meta = os.fstat(stream.fileno())
                require(stat.S_ISREG(meta.st_mode) and meta.st_uid == os.geteuid() and meta.st_size <= 4096,
                    'owned bounded regular action file required')
                request = json.loads(stream.read(4097))
            action = request['action']
            label = f'action-{sequence:03}-{action}'
            item = {'sequence': sequence, 'request': request, 'started_unix_ms': now()}
            report['actions'].append(item)
            if action in ('click', 'ascii', 'key'):
                xid = report['shell']['xid']
                command(label + '-focus', ['xdotool', 'windowfocus', '--sync', xid])
                _, focused = command(label + '-focus-readback', ['xdotool', 'getwindowfocus'])
                require(focused.strip() == xid.encode(), 'owned Shell input focus mismatch')
                if action == 'click':
                    x, y = request['x'], request['y']
                    require(type(x) is int and type(y) is int and 0 <= x < 1360 and 0 <= y < 840,
                        'bounded Shell coordinates required')
                    command(label, ['xdotool', 'mousemove', '--window', xid, str(x), str(y), 'click', '1'])
                elif action == 'ascii':
                    text = request['text']
                    require(0 < len(text) <= 200 and all(32 <= ord(c) < 127 for c in text), 'bounded ASCII required')
                    command(label, ['xdotool', 'type', '--clearmodifiers', '--delay', '25', '--', text])
                else:
                    key = request['key']
                    require(key in ('Tab', 'Escape', 'Return', 'BackSpace', 'ctrl+a'), 'bounded key required')
                    command(label, ['xdotool', 'key', '--clearmodifiers', key])
                time.sleep(0.25)
            elif action == 'screenshot':
                screenshot(label)
            elif action == 'await-task':
                target_session = request['session']
                require(target_session in ('a', 'b'), 'explicit owned Session required')
                expected = report['session_' + target_session]['instance']
                state = request['state']
                require(state in ('running', 'cancelled'), 'bounded actual lifecycle condition required')
                for attempt in range(80):
                    value = snapshot(f'{label}-{attempt:03}')
                    require(value['session_instance'] == expected, 'unexpected Session identity')
                    rows = [t for t in value['tasks'] if t['app'] == 'notes' and t['workspace'] == 'personal']
                    if len(rows) == 1 and rows[0]['state'] == state and (state != 'running' or rows[0]['ui_first_frame_unix_ms']):
                        item['observed_task'] = rows[0]
                        report[f'task_{target_session}_{state}'] = rows[0]
                        if state == 'running':
                            item['window'] = window(label + '-notes', rows[0]['pid'], 'trill-app-window')
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError('actual task lifecycle condition not observed')
            elif action == 'verify-export':
                target = output / 'state/trillionnium-ui/local-context-drafts-v2.json'
                meta = target.lstat()
                require(stat.S_ISREG(meta.st_mode) and stat.S_IMODE(meta.st_mode) == 0o600
                    and meta.st_uid == os.geteuid() and meta.st_size <= 4 * 1024 * 1024, 'private real Shell export required')
                value = json.loads(target.read_bytes())
                require(value['version'] == 2 and len(value['drafts']) == 1, 'one v2 native draft expected')
                draft = value['drafts'][0]
                require(draft['workspace'] == 'personal' and draft['text'] == request['text']
                    and len(draft['contexts']) == 1, 'native text/context export differs')
                reference = draft['contexts'][0]
                require(reference['kind'] == 'host_task', 'typed host reference required')
                # ContextRef is serde internally tagged: the host fields sit
                # beside `kind`, with no invented `context` wrapper.
                quoted = reference
                require(quoted['key']['session_instance'] == report['session_a']['instance']
                    and quoted['key']['task_id'] == report['task_a_running']['id']
                    and quoted['app'] == 'notes' and quoted['quoted_state'] == 'running'
                    and quoted['quoted_pid'] == report['task_a_running']['pid'], 'original task identity was rebound')
                item['export'] = {'sha256': digest(target), 'bytes': meta.st_size, 'value': value}
                report['exports'].append(item['export'])
                if len(report['exports']) > 1:
                    require(report['exports'][0] == item['export'], 'original exported quote was silently rewritten')
            elif action == 'stop-session-a':
                require('task_a_cancelled' in report and 'session_b' not in report, 'cancel old Notes before Session stop')
                stop('Session-A-explicit-stop', session)
                session = None
                time.sleep(2.5)
            elif action == 'start-session-b':
                require(session is None and 'session_b' not in report, 'only one explicit Session replacement allowed')
                session = spawn('Session-B', ['/ui-bin/trill-session'])
                value = session_ready('session-b')
                require(value['session_instance'] != report['session_a']['instance'], 'new random Session identity required')
                report['session_b'] = {'namespace_pid': session.process.pid, 'instance': value['session_instance']}
                require(window(label + '-same-shell', shell.process.pid, 'trill-shell') == report['shell'], 'Shell window changed')
                time.sleep(1.5)
            elif action == 'finish':
                require(len(report['exports']) == 2 and 'task_b_running' in report, 'two real exports and replacement task required')
                require(report['task_a_running']['id'] == report['task_b_running']['id'], 'same-numbered replacement task required')
                require(len(report['screenshots']) >= 5, 'visible sequence incomplete')
                code, data = command(label + '-cleanup-new-notes', ['/ui-bin/trill-ctl', 'cancel',
                    str(report['task_b_running']['id']), report['session_b']['instance']])
                item['cleanup_cancel_response'] = json.loads(data)
                report['status'] = 'completed_native_capture_requires_independent_visual_review'
            else:
                raise RuntimeError('unsupported bounded action')
            item['completed_unix_ms'] = now()
            save()
            write(queue / f'{sequence:03}.done.json', item)
            if action == 'finish':
                break
        require(report['status'].startswith('completed_'), 'capture did not finish')
    except BaseException as error:
        report['status'] = 'failed'
        report['failure'] = repr(error)
        raise
    finally:
        if display:
            display.close()
        for label, group in reversed(groups):
            if group.armed:
                try:
                    stop(label, group)
                except BaseException as error:
                    report['status'] = 'failed'
                    report['cleanup'].append({'label': label, 'error': repr(error)})
        report['completed_unix_ms'] = now()
        save()
        write(output / 'capture-receipt.json', report)
    # Cleanup errors recorded by finally must also fail the namespace process.
    # A successful action sequence alone cannot qualify leaked/lost children.
    require(report['status'] == 'completed_native_capture_requires_independent_visual_review',
        'native capture or owned cleanup failed; inner raw receipt retained')


def outside(args):
    source = args.source.resolve(strict=True)
    native = args.native_root.resolve(strict=True)
    binary_dir = args.binaries.resolve(strict=True)
    output = args.output.resolve()
    source_before = sources(source)
    harness_before = sources(ROOT)
    require(source_before['head'] == args.expected_head and not source_before['status'], 'clean expected product source required')
    require(not harness_before['status'], 'commit harness before actual execution')
    build = json.loads(args.build_receipt.read_text())
    require(build['status'] == 'passed' and build['mode'] == 'build'
        and build['expected_head'] == args.expected_head and build['source_before_equals_after'], 'exact successful build receipt required')
    build_source = json.loads(args.build_receipt.with_name('source-before.json').read_text())
    require(build_source['files'] == source_before['files'], 'build/source closure mismatch')
    actual_binaries = binaries(binary_dir)
    for name, record in actual_binaries.items():
        require(all(build['production_binaries'][name][key] == value for key, value in record.items()), 'build ELF mismatch: ' + name)
    output.mkdir(mode=0o700)
    (output / 'inside').mkdir(mode=0o700)
    native_receipts = ['native-build-packages.json', 'runtime-packages.json', 'extra-libxkbfile1.json', 'usr-view02.json']
    binding = {'schema': 'r7-native-chat-input-v1', 'source': source_before, 'harness': harness_before,
        'binaries': actual_binaries, 'build_receipt': build, 'build_receipt_sha256': digest(args.build_receipt),
        'harness_sha256': digest(Path(__file__)), 'native_receipts': {name: digest(native / 'receipts' / name) for name in native_receipts},
        'font_sha256': digest(native / 'sysroot/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        'namespace': ['owned_mount', 'user', 'ipc', 'network', 'uts', 'pid'], 'host_desktop_bound': False}
    write(output / 'inside/input-binding.json', binding)
    script = Path('/test-harness/tests/ui/probe-chat-workspace.py')
    cmd = ['/usr/bin/bwrap', '--unshare-user', '--unshare-ipc', '--unshare-net', '--unshare-uts', '--unshare-pid',
        '--die-with-parent', '--new-session', '--hostname', 'r7-native-chat',
        '--ro-bind', '/usr', '/host/usr', '--ro-bind', str(native / 'sysroot'), '/r7-sysroot',
        '--ro-bind', str(native / 'view02/usr'), '/usr', '--symlink', 'usr/bin', '/bin',
        '--symlink', 'usr/sbin', '/sbin', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
        '--ro-bind', '/etc', '/etc', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/root', '--dir', '/run',
        '--ro-bind', str(ROOT), '/test-harness', '--ro-bind', str(source), '/test-source',
        '--ro-bind', str(binary_dir), '/ui-bin', '--bind', str(output / 'inside'), '/capture',
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
        group.wait_exit(960)
    except BaseException as error:
        failure = repr(error)
    finally:
        if group is not None and group.armed:
            group.signal_group(signal.SIGKILL)
            group.wait_exit(5)
            record['exit_code'] = group.reap()
        record.update(completed_unix_ms=now(), failure=failure,
            product_source_unchanged=sources(source) == source_before,
            harness_source_unchanged=sources(ROOT) == harness_before,
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


if __name__ == '__main__':
    if len(sys.argv) >= 5 and sys.argv[1] == '--exec-parent' and sys.argv[3] == '--':
        helper = module('chat_death_exec', ROOT / 'tests/ui/probe-original-hepta-shell.py')
        helper.bound_exec(int(sys.argv[2]), sys.argv[4:])
    elif len(sys.argv) == 3 and sys.argv[1] == '--inside':
        inside(Path(sys.argv[2]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--source', type=Path, required=True)
        parser.add_argument('--expected-head', required=True)
        parser.add_argument('--binaries', type=Path, required=True)
        parser.add_argument('--build-receipt', type=Path, required=True)
        parser.add_argument('--native-root', type=Path, required=True)
        parser.add_argument('--output', type=Path, required=True)
        outside(parser.parse_args())
