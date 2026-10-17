#!/usr/bin/env python3
"""Prepare an owned Xvfb/IBus namespace from verified Ubuntu package bytes.

This environment preflight starts real distribution programs. It does not
claim that a Rust UI received an IME event; the later UI probe owns that gate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
FLOOR = 100 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merge_usr(host, packages, output, relative=Path()):
    output.mkdir()
    names = set(item.name for item in host.iterdir()) if host.is_dir() else set()
    names |= set(item.name for item in packages.iterdir()) if packages.is_dir() else set()
    count = 0
    for name in sorted(names):
        old, new = host / name, packages / name
        rel = relative / name
        if new.is_dir() and not new.is_symlink() and old.is_dir() and not old.is_symlink():
            count += merge_usr(old, new, output / name, rel)
        elif new.exists() or new.is_symlink():
            (output / name).symlink_to(Path('/a10-packages/usr') / rel)
            count += 1
        else:
            (output / name).symlink_to(Path('/host/usr') / rel)
            count += 1
    return count


def load_guard(path):
    spec = importlib.util.spec_from_file_location('a10_ime_child_guard', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.child_anchor_available(), 'waitable child identity required')
    return module


def inside():
    output = Path('/run/a10-ime')
    has_ui = Path('/ui-bin/trill-shell').is_file()
    guard_path = '/test-source/tests/integration/hepta/run_original_agentd.py'
    guard = load_guard(guard_path)
    for name in ['runtime', 'cache', 'config', 'state', 'data', 'schemas']:
        (output / name).mkdir(mode=0o700)
    env = os.environ.copy()
    env.update({
        'DISPLAY': ':91', 'XAUTHORITY': str(output / 'Xauthority'),
        'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/a10-ime/session-bus',
        'XMODIFIERS': '@im=ibus', 'GDK_BACKEND': 'x11',
        'GTK_IM_MODULE': 'ibus', 'QT_IM_MODULE': 'ibus',
        'IBUS_USE_PORTAL': '0', 'GSETTINGS_SCHEMA_DIR': str(output / 'schemas'),
        'XDG_CURRENT_DESKTOP': 'A10_PRIVATE_IME_TEST',
    })
    if has_ui:
        (output / 'fonts.conf').write_text('<?xml version="1.0"?>\n'
            '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n<fontconfig>\n'
            '<dir>/test-fonts</dir><cachedir>/run/a10-ime/cache/fontconfig</cachedir>\n'
            '</fontconfig>\n')
        env['FONTCONFIG_FILE'] = str(output / 'fonts.conf')
    report = {
        'evidence_class': 'private_xvfb_ibus_xim_environment_preflight',
        'started_unix_ms': time.time_ns() // 1_000_000,
        'passed': False, 'system_install_performed': False,
        'rust_ui_started': False, 'rust_ui_ime_verified': False,
        'xim_text_committed': False, 'physical_input_verified': False,
        'wayland_text_input_v3_verified': False,
        'probe_sha256': digest(Path('/probe.py')),
        'child_guard_sha256': digest(Path(guard_path)),
        'commands': [], 'children': [],
    }
    groups, logs = [], []

    def save():
        (output / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')

    def command(label, argv, environment=None, required=True):
        try:
            completed = subprocess.run(argv, env=environment or env,
                stdin=subprocess.DEVNULL, capture_output=True, timeout=8)
        except subprocess.TimeoutExpired as error:
            (output / (label + '.stdout.log')).write_bytes(error.stdout or b'')
            (output / (label + '.stderr.log')).write_bytes(error.stderr or b'')
            report['commands'].append({'label': label, 'argv': argv,
                'returncode': None, 'timeout_seconds': 8})
            raise
        (output / (label + '.stdout.log')).write_bytes(completed.stdout)
        (output / (label + '.stderr.log')).write_bytes(completed.stderr)
        report['commands'].append({'label': label, 'argv': argv,
            'returncode': completed.returncode})
        if required:
            require(completed.returncode == 0, label + ' command failed')
        return completed

    def spawn(label, argv):
        stdout = (output / (label + '.stdout.log')).open('xb')
        stderr = (output / (label + '.stderr.log')).open('xb')
        logs.extend([stdout, stderr])
        process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(process)
        groups.append((label, group))
        report['children'].append({'label': label, 'namespace_pid': process.pid,
            'argv': argv})
        return group

    def alive(group):
        return group.observe_exit() is None

    try:
        # dpkg extraction does not run host package triggers. Build only a new
        # private schema cache, preserving every packaged/original schema.
        for schema in Path('/usr/share/glib-2.0/schemas').iterdir():
            if schema.name.endswith(('.xml', '.gschema.override')):
                shutil.copyfile(schema, output / 'schemas' / schema.name)
        # Exact IBus 1.5.29 CLI returns failure for the libpinyin "default"
        # layout after successfully selecting its engine unless this setting
        # is enabled. Keep a test-owned US keymap and private schema override.
        (output / 'schemas' / '99-a10-private.gschema.override').write_text(
            '[org.freedesktop.ibus.general]\n'
            'use-system-keyboard-layout=true\nuse-xmodmap=false\n')
        compiler = Path('/usr/lib/x86_64-linux-gnu/glib-2.0/glib-compile-schemas')
        require(compiler.is_file(), 'packaged GLib schema compiler missing')
        command('schemas', [str(compiler), '--strict', str(output / 'schemas')])
        auth = output / 'Xauthority'
        auth.touch(mode=0o600)
        # The cookie is new and meaningful only in this isolated test display.
        cookie = secrets.token_hex(16)
        p = subprocess.run(['xauth', '-f', str(auth), 'add', ':91', '.', cookie],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
        (output / 'xauth.stdout.log').write_bytes(p.stdout)
        (output / 'xauth.stderr.log').write_bytes(p.stderr)
        require(p.returncode == 0, 'private X authority initialization failed')
        xserver = spawn('xvfb', ['Xvfb', ':91', '-nolisten', 'tcp',
            '-screen', '0', '1440x1000x24' if has_ui else '1280x800x24', '-auth', str(auth)])
        for attempt in range(60):
            require(alive(xserver), 'Xvfb exited before readiness')
            result = command(f'display-ready-{attempt:02}', ['xdpyinfo'], required=False)
            if result.returncode == 0:
                break
            require(attempt < 59, 'private Xvfb display timed out')
            time.sleep(0.05)
        no_cookie = dict(env, XAUTHORITY=str(output / 'absent-cookie'))
        denied = command('unauthenticated-display', ['xdpyinfo'],
            environment=no_cookie, required=False)
        require(denied.returncode != 0, 'Xvfb accepted a client without the owned cookie')
        command('private-us-keymap', ['setxkbmap', '-layout', 'us'])
        command('private-keymap-observed', ['setxkbmap', '-query'])
        bus = spawn('dbus', ['dbus-daemon', '--session', '--nofork',
            '--address=' + env['DBUS_SESSION_BUS_ADDRESS'], '--print-address=1'])
        for attempt in range(60):
            require(alive(bus), 'private session bus exited')
            if (output / 'session-bus').is_socket():
                break
            require(attempt < 59, 'private session bus timed out')
            time.sleep(0.05)
        ibus = spawn('ibus-daemon', ['ibus-daemon', '--xim', '--verbose',
            '--panel=/usr/libexec/ibus-ui-gtk3',
            '--config=/usr/libexec/ibus-memconf', '--cache=none'])
        for attempt in range(80):
            require(all(alive(g) for g in [xserver, bus, ibus]),
                'private display/input service exited')
            result = command(f'engines-ready-{attempt:02}',
                ['ibus', 'list-engine'], required=False)
            if result.returncode == 0 and b'libpinyin' in result.stdout:
                break
            require(attempt < 79, 'IBus did not register the real libpinyin engine')
            time.sleep(0.05)
        command('engine-select', ['ibus', 'engine', 'libpinyin'])
        selected = command('engine-observed', ['ibus', 'engine'])
        require(selected.stdout.strip() == b'libpinyin', 'selected engine was not observed')
        command('ibus-version', ['ibus', 'version'])
        address = command('ibus-address', ['ibus', 'address'])
        advertised = command('xim-selection', ['xprop', '-root', 'XIM_SERVERS'])
        require(b'@server=ibus' in advertised.stdout, 'IBus XIM selection was not advertised')
        require(all(alive(g) for g in [xserver, bus, ibus]), 'input services exited')
        report['passed'] = True
        report['engine'] = selected.stdout.decode().strip()
        report['xim_selection_advertised'] = True
        report['private_display_rejects_no_cookie'] = True
        if has_ui:
            report['passed'] = False
            report['environment_preflight_passed'] = True
            report['evidence_class'] = 'private_X11_IBus_XIM_real_Rust_input_probe'
            trace = spawn('ibus-private-signal-trace', ['dbus-monitor', '--address',
                address.stdout.decode().strip(),
                "type='signal',interface='org.freedesktop.IBus.InputContext'"])
            report['ibus_signal_trace_started'] = True
            spec = importlib.util.spec_from_file_location('a10_real_ime_ui', '/ui-probe.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.run_ui(output, report, env, command, spawn, alive)
            report['passed'] = bool(report['rust_ui_ime_verified'])
            report['ibus_signal_trace_alive_at_end'] = alive(trace)
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        cleanup_errors = []
        for label, group in reversed(groups):
            try:
                code = guard.terminate_group(group)
                report.setdefault('cleanup', []).append({'label': label,
                    'namespace_pid': group.process.pid, 'observed_returncode': code})
            except BaseException as error:
                cleanup_errors.append(label + ': ' + str(error))
        for log in logs:
            log.close()
        if cleanup_errors:
            report['passed'] = False
            report['cleanup_errors'] = cleanup_errors
        report['finished_unix_ms'] = time.time_ns() // 1_000_000
        save()
        print(json.dumps(report, indent=2), flush=True)
        require(not cleanup_errors, 'private child cleanup failed')


def outer(args):
    base = args.base.resolve(strict=True)
    metadata = base.stat()
    require(args.base.is_absolute() and metadata.st_uid == os.geteuid()
        and stat.S_IMODE(metadata.st_mode) == 0o700, 'owned private 0700 package root required')
    source_root = (args.source_root or Path(__file__).resolve().parents[2]).resolve(strict=True)
    stage = json.loads((base / 'package-stage.json').read_text())
    require(stage['passed'] and len(stage['items']) == 44, 'verified package stage incomplete')
    free = os.statvfs(base).f_bavail * os.statvfs(base).f_frsize
    require(free >= FLOOR, 'private RAM is below the 100 MiB floor')
    merged = base / 'merged'
    if not merged.exists():
        merged.mkdir()
        count = merge_usr(Path('/usr'), base / 'packages/usr', merged / 'usr')
        (base / 'merge-layout.json').write_text(json.dumps({
            'symlinks': count, 'system_files_copied': False,
            'package_bytes_changed': False}, indent=2) + '\n')
    output = Path(args.output)
    require(output.is_absolute() and not output.exists() and not output.is_symlink(),
        'new absolute output directory required')
    require(output.parent.is_dir(), 'output parent must already exist')
    output.mkdir(mode=0o700)
    require(stat.S_IMODE(output.stat().st_mode) == 0o700, 'output must be private 0700')
    shutil.copyfile(__file__, output / 'probe-source.py')
    extra_mounts = []
    provenance = {'environment_source_sha256': digest(Path(__file__))}
    if args.ui:
        build = json.loads(args.build_receipt.read_text())
        require(build['status'] == 'passed' and build['exit_code'] == 0,
            'passing Rust build provenance required')
        require(set(build['binaries']) == {'trill-shell', 'trill-session',
            'trill-ctl', 'trill-app-window'}, 'four exact A10 binaries required')
        def git(*arguments):
            return subprocess.check_output(['git', '-C', str(source_root), *arguments],
                stderr=subprocess.PIPE, timeout=10).decode().strip()
        require(not git('status', '--porcelain=v1', '--untracked-files=all'),
            'commit the probe and preserve a clean source checkout before execution')
        ui_tree = git('rev-parse', build['source_commit'] + ':ui')
        require(git('rev-parse', 'HEAD:ui') == ui_tree,
            'current Rust UI source differs from the recorded ELF source')
        provenance.update({'harness_commit': git('rev-parse', 'HEAD'),
            'harness_tree': git('rev-parse', 'HEAD^{tree}'),
            'production_ui_commit': build['source_commit'],
            'production_ui_tree': build['source_tree'], 'unchanged_ui_subtree': ui_tree})
        for name, recorded in build['binaries'].items():
            candidate = args.bin_dir / name
            require(candidate.is_file() and candidate.stat().st_size == recorded['bytes']
                and digest(candidate) == recorded['sha256'],
                'Rust ELF does not match recorded source: ' + name)
        require(digest(args.font) == '27251f8f257e831f4b876408a7d0ef88ae2c18fe0cbb6780bd18fe6bad8ddb10',
            'unexpected test font bytes')
        shutil.copyfile(args.build_receipt, output / 'rust-build-receipt.json')
        client_source = Path(__file__).with_name('x11-ime-client.py')
        shutil.copyfile(client_source, output / 'ui-probe-source.py')
        scenario = json.loads(args.scenario.read_text())
        require(isinstance(scenario, list) and len(scenario) == 23,
            'fixed 23-action ASCII input scenario required')
        shutil.copyfile(args.scenario, output / 'replay-scenario.json')
        provenance.update({'client_source_sha256': digest(client_source),
            'input_fixture_sha256': digest(args.scenario),
            'font_sha256': digest(args.font), 'binaries': build['binaries']})
        (output / 'probe-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
        extra_mounts = ['--ro-bind', str(args.bin_dir), '/ui-bin',
            '--ro-bind', str(args.font), '/test-fonts/CJK.ttf',
            '--ro-bind', str(output / 'ui-probe-source.py'), '/ui-probe.py']
    guard_source = source_root / 'tests/integration/hepta/run_original_agentd.py'
    command = ['/usr/bin/bwrap', '--unshare-all', '--die-with-parent', '--new-session',
        '--hostname', 'a10-private-ime', '--ro-bind', '/usr', '/host/usr',
        '--ro-bind', str(base / 'packages'), '/a10-packages',
        '--ro-bind', str(merged / 'usr'), '/usr',
        '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/sbin', '/sbin',
        '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
        '--ro-bind', '/etc', '/etc', '--ro-bind', '/proc', '/proc', '--dev', '/dev',
        '--tmpfs', '/tmp', '--dir', '/root', '--dir', '/run',
        '--bind', str(output), '/run/a10-ime',
        '--ro-bind', str(output / 'probe-source.py'), '/probe.py',
        '--ro-bind', str(guard_source),
        '/test-source/tests/integration/hepta/run_original_agentd.py', *extra_mounts, '--clearenv',
        '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'LANG', 'C.UTF-8',
        '--setenv', 'LC_ALL', 'C.UTF-8', '--setenv', 'PYTHONDONTWRITEBYTECODE', '1',
        '--setenv', 'TZ', 'UTC',
        '--setenv', 'XDG_RUNTIME_DIR', '/run/a10-ime/runtime',
        '--setenv', 'XDG_CACHE_HOME', '/run/a10-ime/cache',
        '--setenv', 'XDG_CONFIG_HOME', '/run/a10-ime/config',
        '--setenv', 'XDG_STATE_HOME', '/run/a10-ime/state',
        '--setenv', 'XDG_DATA_HOME', '/run/a10-ime/data',
        '--chdir', '/run/a10-ime', '/usr/bin/python3', '-B', '/probe.py', '--inside']
    record = {'argv': command, 'started_unix_ms': time.time_ns() // 1_000_000,
        'free_bytes_before': free, 'minimum_free_bytes': free,
        'source_sha256': digest(Path(__file__)), 'system_mutated': False,
        'provenance': provenance}
    guard = load_guard(guard_source)
    with (output / 'namespace.stdout.log').open('xb') as stdout, (output / 'namespace.stderr.log').open('xb') as stderr:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout,
            stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(child)
        deadline = time.monotonic() + (420 if args.ui else 90)
        try:
            while group.observe_exit() is None:
                current = os.statvfs(base).f_bavail * os.statvfs(base).f_frsize
                record['minimum_free_bytes'] = min(record['minimum_free_bytes'], current)
                require(current >= FLOOR, 'RAM stop threshold crossed')
                require(time.monotonic() < deadline, 'namespace preflight deadline')
                time.sleep(0.05)
            record['returncode'] = group.reap()
        except BaseException:
            record['returncode'] = guard.terminate_group(group)
            raise
        finally:
            record['finished_unix_ms'] = time.time_ns() // 1_000_000
            (output / 'namespace.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    require(record['returncode'] == 0, 'private namespace preflight failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside', action='store_true')
    parser.add_argument('--base', type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--ui', action='store_true')
    parser.add_argument('--bin-dir', type=Path)
    parser.add_argument('--build-receipt', type=Path)
    parser.add_argument('--font', type=Path)
    parser.add_argument('--scenario', type=Path,
        default=Path(__file__).with_name('x11-ime-actions.json'))
    parser.add_argument('--output')
    arguments = parser.parse_args()
    inside() if arguments.inside else outer(arguments)
