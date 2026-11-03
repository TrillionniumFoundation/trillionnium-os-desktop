#!/usr/bin/env python3
"""Focused GTK control for the real private IBus service; never a Makepad gate.

Uses the same private schema/Xvfb/bus settings as qualify.py. Only ASCII XTEST
keys enter a real Gtk.Entry. A successful GTK control does not qualify any SDK,
production authority, physical keyboard, candidate placement or Wayland path.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    pending = path.with_suffix(path.suffix + '.new')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)


def waitid_record(status):
    """Preserve WNOWAIT child identity; this does not reap or signal anything."""
    if status is None:
        return None
    if not isinstance(status, os.waitid_result):
        raise TypeError('ChildGroup.observe_exit must return os.waitid_result, not an exit integer')
    code = status.si_status if status.si_code == os.CLD_EXITED else -status.si_status
    return {'pid': status.si_pid, 'uid': status.si_uid, 'si_code': status.si_code,
            'si_status': status.si_status, 'exit_code': code,
            'exited_successfully': status.si_code == os.CLD_EXITED and status.si_status == 0}


def gtk_child(path):
    if os.environ.get('TRILL_PRIVATE_IBUS_FOCUS_CONTROL') != '1':
        raise RuntimeError('GTK child requires the newly created private surfaces')
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('GdkX11', '3.0')
    from gi.repository import Gtk, GdkX11, GLib
    window = Gtk.Window(title='Owned GTK IBus focus control')
    window.set_default_size(640, 140)
    entry = Gtk.Entry()
    entry.set_placeholder_text('Real private IBus input control')
    entry.get_accessible().set_name('Owned GTK IBus entry')
    window.add(entry)
    state = {'schema': 'trill.gtk-ibus-entry.v1', 'pid': os.getpid(), 'heartbeat': 0,
             'events': [], 'preedit': '', 'gtk_version': [Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()]}

    def event(kind, text):
        state['events'].append({'kind': kind, 'text': text[:4096], 'monotonic': time.monotonic()})
        if len(state['events']) > 256:
            state['error'] = 'GTK diagnostic event bound exceeded'
            Gtk.main_quit()

    def preedit(_entry, text):
        state['preedit'] = text
        event('preedit-changed', text)

    def snapshot():
        native = window.get_window()
        state.update(heartbeat=state['heartbeat'] + 1, monotonic=time.monotonic(),
                     xid=None if native is None else GdkX11.X11Window.get_xid(native),
                     mapped=window.get_mapped(), window_active=window.is_active(),
                     entry_has_focus=entry.has_focus(), entry_is_window_focus=window.get_focus() == entry,
                     text=entry.get_text())
        write_json(path, state)
        return True

    entry.connect('preedit-changed', preedit)
    entry.connect('changed', lambda current: event('changed', current.get_text()))
    entry.connect('focus-in-event', lambda *_: event('focus-in', '') or False)
    entry.connect('focus-out-event', lambda *_: event('focus-out', '') or False)
    window.connect('destroy', Gtk.main_quit)
    window.show_all()
    window.present()
    entry.grab_focus()
    GLib.timeout_add(80, snapshot)
    snapshot()
    Gtk.main()


def descendants():
    rows, seen, pending = [], set(), [os.getpid()]
    while pending and len(rows) < 128:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        proc = Path('/proc') / str(pid)
        try:
            pending.extend(int(value) for value in (proc / f'task/{pid}/children').read_text().split())
            rows.append({'pid': pid, 'comm': (proc / 'comm').read_text().strip(),
                         'wchan': (proc / 'wchan').read_text().strip(),
                         'stat': (proc / 'stat').read_text().strip()})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rows


def run(args):
    output = args.output.absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise RuntimeError('Output must be a new directory under an existing parent')
    output.mkdir(mode=0o700)
    desktop, hepta = args.desktop_source.resolve(strict=True), args.hepta_source.resolve(strict=True)
    guard_path = desktop / 'tests/integration/hepta/run_original_agentd.py'
    capture_path = desktop / 'tests/ui/native-makepad/capture.py'
    owner_path = hepta / 'apps/hepta-control-ui/test/x11_client_owner.py'
    guard = load('focused_ibus_child_guard', guard_path)
    if not guard.child_anchor_available():
        raise RuntimeError('Original sole-reaper child identity anchor is unavailable')
    report = {'schema': 'hepta.private-ibus-gtk-control.v2', 'passed': False,
              'sdk_running': False, 'makepad_preedit_qualified': False,
              'production_root_authority_qualified': False, 'physical_device_qualified': False,
              'wayland_qualified': False, 'original_production_oracle_changed': False,
              'unicode_injection_used': False, 'synthetic_ime_events_used': False,
              'gtk_im_module': args.gtk_im_module, 'engine': 'libpinyin', 'input': [],
              'commands': [], 'children': [], 'cleanup': [], 'captures': [],
              'source_sha256': {str(path): digest(path) for path in (Path(__file__), guard_path, capture_path, owner_path)}}
    groups, logs, display_pixels = [], [], None
    temporary = tempfile.TemporaryDirectory(prefix='trill-ibus-gtk-')
    private = Path(temporary.name)
    for name in ('runtime', 'config', 'cache', 'state', 'data', 'schemas'):
        (private / name).mkdir(mode=0o700)
    state_path = output / 'gtk-state.json'

    def save():
        write_json(output / 'result.json', report)

    def command(label, argv, *, required=True, timeout=8, environment=None):
        number = len(report['commands'])
        if number >= 256:
            raise RuntimeError('Diagnostic command bound reached')
        row = {'label': label, 'argv': list(map(str, argv))}
        report['commands'].append(row)
        try:
            result = subprocess.run(argv, env=environment or env, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=timeout)
            row['exit_code'] = result.returncode
            stdout, stderr = result.stdout, result.stderr
        except subprocess.TimeoutExpired as error:
            row['timeout_seconds'] = timeout
            stdout, stderr = error.stdout or b'', error.stderr or b''
            raise
        finally:
            if 'stdout' in locals():
                (output / f'{number:03}-{label}.stdout.log').write_bytes(stdout)
                (output / f'{number:03}-{label}.stderr.log').write_bytes(stderr)
        if required and result.returncode != 0:
            raise RuntimeError(f'{label} failed with exit {result.returncode}')
        return result

    def spawn(label, argv):
        stdout, stderr = (output / f'{label}.stdout.log').open('xb'), (output / f'{label}.stderr.log').open('xb')
        logs.extend((stdout, stderr))
        process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=stdout,
                                   stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(process)
        groups.append((label, group))
        report['children'].append({'label': label, 'argv': list(map(str, argv)), 'pid': process.pid})
        return group

    def alive(group):
        status = group.observe_exit()
        if status is not None:
            raise RuntimeError(f'Owned child exited before readiness: {waitid_record(status)}')
        return True

    def until(probe, description, timeout=15):
        end, last = time.monotonic() + timeout, None
        while time.monotonic() < end:
            try:
                value = probe()
                if value:
                    return value
            except (FileNotFoundError, json.JSONDecodeError) as error:
                last = str(error)
            time.sleep(0.08)
        raise RuntimeError(f'{description}; last={last}')

    def entry_state():
        alive(gtk)
        value = json.loads(state_path.read_bytes())
        if value['pid'] != gtk.process.pid or time.monotonic() - value['monotonic'] > 2:
            raise RuntimeError('The actual GTK child stopped serving its GLib loop')
        return value

    def entry_when(predicate):
        value = entry_state()
        return value if predicate(value) else None

    def capture(label):
        for suffix, window in (('window', xid), ('display', None)):
            report['captures'].append(display_pixels.screenshot(output / f'{label}-{suffix}.png', window))

    try:
        for _ in range(128):
            number = secrets.randbelow(1800) + 200
            if not Path(f'/tmp/.X{number}-lock').exists() and not Path(f'/tmp/.X11-unix/X{number}').exists():
                display = f':{number}'
                break
        else:
            raise RuntimeError('No unused private display')
        env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
               'DISPLAY': display, 'XAUTHORITY': str(private / 'Xauthority'),
               'DBUS_SESSION_BUS_ADDRESS': f'unix:path={private}/runtime/session-bus',
               'XDG_RUNTIME_DIR': str(private / 'runtime'), 'XDG_CONFIG_HOME': str(private / 'config'),
               'XDG_CACHE_HOME': str(private / 'cache'), 'XDG_STATE_HOME': str(private / 'state'),
               'XDG_DATA_HOME': str(private / 'data'), 'XDG_CURRENT_DESKTOP': 'TRILL_NATIVE_PRIVATE_TEST',
               'GSETTINGS_SCHEMA_DIR': str(private / 'schemas'), 'GSETTINGS_BACKEND': 'memory',
               'XMODIFIERS': '@im=ibus', 'GTK_IM_MODULE': args.gtk_im_module, 'QT_IM_MODULE': 'ibus',
               'GDK_BACKEND': 'x11', 'IBUS_USE_PORTAL': '0', 'WINIT_UNIX_BACKEND': 'x11',
               'LIBGL_ALWAYS_SOFTWARE': '1', 'LP_NUM_THREADS': '2', 'MESA_SHADER_CACHE_DISABLE': 'true',
               'PYTHONDONTWRITEBYTECODE': '1', 'TRILL_PRIVATE_IBUS_FOCUS_CONTROL': '1'}
        for schema in Path('/usr/share/glib-2.0/schemas').iterdir():
            if schema.name.endswith(('.xml', '.gschema.override')) and schema.is_file():
                shutil.copyfile(schema, private / 'schemas' / schema.name)
        (private / 'schemas/99-trill-native.gschema.override').write_text(
            '[org.freedesktop.ibus.general]\nuse-system-keyboard-layout=true\nuse-xmodmap=false\n')
        command('private-schemas', ['glib-compile-schemas', '--strict', str(private / 'schemas')])
        report['compiled_schemas_sha256'] = digest(private / 'schemas/gschemas.compiled')
        auth = private / 'Xauthority'
        auth.touch(mode=0o600)
        # The display cookie stays out of command receipts and archived logs.
        subprocess.run(['xauth', '-f', str(auth), 'add', display, '.', secrets.token_hex(16)],
                       env=env, capture_output=True, check=True, timeout=5)
        xvfb = spawn('xvfb', ['Xvfb', display, '-nolisten', 'tcp', '-screen', '0', '1440x1000x24', '-auth', str(auth)])
        until(lambda: alive(xvfb) and command('display-ready', ['xdpyinfo'], required=False, timeout=3).returncode == 0, 'Private display readiness')
        assert command('display-without-cookie', ['xdpyinfo'], required=False,
                       environment=dict(env, XAUTHORITY=str(private / 'missing-cookie'))).returncode != 0
        report['private_display_rejected_missing_cookie'] = True
        command('private-keymap', ['setxkbmap', '-layout', 'us'])
        bus = spawn('bus', ['dbus-daemon', '--session', '--nofork', '--address=' + env['DBUS_SESSION_BUS_ADDRESS']])
        until(lambda: alive(bus) and (private / 'runtime/session-bus').is_socket(), 'Private bus readiness')
        a11y = spawn('a11y', ['/usr/libexec/at-spi-bus-launcher', '--launch-immediately', '--a11y=1', '--screen-reader=1'])
        for key in ('IsEnabled', 'ScreenReaderEnabled'):
            until(lambda: alive(a11y) and command('a11y-' + key, ['gdbus', 'call', '--session', '--dest', 'org.a11y.Bus',
                '--object-path', '/org/a11y/bus', '--method', 'org.freedesktop.DBus.Properties.Set',
                'org.a11y.Status', key, '<true>'], required=False).returncode == 0, 'Private accessibility readiness')
        ibus = spawn('ibus', ['ibus-daemon', '--xim', '--verbose', '--panel=/usr/libexec/ibus-ui-gtk3',
                              '--config=/usr/libexec/ibus-memconf', '--cache=none'])
        until(lambda: alive(ibus) and b'libpinyin' in command('engine-list', ['ibus', 'list-engine', '--name-only'], required=False).stdout.splitlines(), 'Real engine registration')
        until(lambda: b'@server=ibus' in command('xim-ready', ['xprop', '-root', 'XIM_SERVERS'], required=False).stdout, 'Real private XIM selection')
        command('ibus-version', ['ibus', '--version'], required=False)
        gtk = spawn('gtk-entry', ['/usr/bin/python3', '-B', str(Path(__file__).resolve()), '--gtk-child', str(state_path)])
        snapshot = until(lambda: entry_when(lambda state: state['mapped'] and state['xid']), 'Real GTK window readiness')
        xid = int(snapshot['xid'])
        command('xres-owner', ['/usr/bin/python3', '-B', str(owner_path), '--pid', str(gtk.process.pid), '--window-id', str(xid)])
        command('focus-owned-gtk', ['xdotool', 'windowfocus', '--sync', str(xid)])
        until(lambda: entry_when(lambda state: state['entry_has_focus'] and state['entry_is_window_focus'] and state['window_active']), 'Real GTK entry focus')
        assert int(command('actual-focus', ['xdotool', 'getwindowfocus']).stdout) == xid
        report['focus_before_activation'] = entry_state()
        assert report['focus_before_activation']['text'] == ''
        # Capture accesses only this newly owned display, never an inherited one.
        os.environ.update(DISPLAY=display, XAUTHORITY=str(auth))
        display_pixels = load('focused_ibus_capture', capture_path).Display()
        command('initial-english-engine', ['ibus', 'engine', 'xkb:us::eng'])
        began = time.monotonic()
        switch = spawn('switch-libpinyin', ['ibus', 'engine', 'libpinyin'])
        status, at_eight = None, False
        while time.monotonic() - began < 30:
            status = switch.observe_exit()
            if status is not None:
                break
            if not at_eight and time.monotonic() - began >= 8:
                at_eight = True
                report['pending_at_original_eight_seconds'] = {'gtk': entry_state(), 'processes': descendants()}
                capture('activation-pending')
                save()
            time.sleep(0.05)
        report['activation_seconds'] = round(time.monotonic() - began, 6)
        report['activation_exit'] = waitid_record(status)
        report['activation_within_original_8s'] = status is not None and report['activation_seconds'] <= 8
        report['focus_after_activation'] = entry_state()
        queried = command('actual-engine', ['ibus', 'engine'], required=False, timeout=5)
        report['actual_engine'] = queried.stdout.decode().strip()
        if status is None or not report['activation_exit']['exited_successfully'] or report['actual_engine'] != 'libpinyin':
            raise RuntimeError('Real focused GTK engine activation did not complete successfully')
        assert entry_state()['entry_has_focus'] and int(command('input-focus', ['xdotool', 'getwindowfocus']).stdout) == xid
        command('real-ascii-input', ['xdotool', 'type', '--clearmodifiers', '--delay', '150', '--', 'nihao'])
        report['input'].append({'kind': 'XTEST_ASCII', 'text': 'nihao'})
        preedit = until(lambda: entry_when(lambda state: state['preedit']), 'GTK real IBus preedit')
        report['preedit_observed'] = preedit
        assert preedit['text'] == '', 'Preedit was prematurely committed to the GTK entry'
        capture('preedit')
        command('real-space-confirmation', ['xdotool', 'key', '--clearmodifiers', 'space'])
        report['input'].append({'kind': 'XTEST_key', 'key': 'space'})
        committed = until(lambda: entry_when(lambda state: state['text'] == '你好' and state['preedit'] == ''), 'Exact GTK Chinese commit')
        report['committed_observed'] = committed
        capture('committed')
        report['gtk_real_ibus_text_input_observed'] = True
        report['passed'] = report['activation_within_original_8s']
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        if state_path.exists():
            report['gtk_failure_observation'] = json.loads(state_path.read_bytes())
        if display_pixels is not None:
            try:
                capture('failure')
            except Exception as capture_error:
                report['capture_error'] = str(capture_error)
    finally:
        report['final_processes_before_cleanup'] = descendants()
        if display_pixels is not None:
            display_pixels.close()
        errors = []
        for label, group in reversed(groups):
            try:
                report['cleanup'].append({'label': label, 'exit_code': guard.terminate_group(group)})
            except BaseException as error:
                errors.append(label + ': ' + str(error))
        for log in logs:
            log.close()
        try:
            temporary.cleanup()
        except Exception as error:
            errors.append('private-state: ' + str(error))
        report['cleanup_errors'] = errors
        report['private_credentials_and_state_removed'] = not private.exists()
        if errors or private.exists():
            report['passed'] = False
        save()
        print(json.dumps({'passed': report['passed'], 'receipt': str(output / 'result.json'),
                          'error': report.get('error'), 'makepad_preedit_qualified': False}))
    return 0 if report['passed'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop-source', type=Path)
    parser.add_argument('--hepta-source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--gtk-im-module', choices=('ibus', 'xim'), default='ibus')
    parser.add_argument('--gtk-child', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    os.umask(0o077)
    if args.gtk_child is not None:
        gtk_child(args.gtk_child)
        return 0
    if args.desktop_source is None or args.hepta_source is None or args.output is None:
        parser.error('--desktop-source, --hepta-source and --output are required')
    def interrupted(_number, _frame):
        raise KeyboardInterrupt('Cleaning only this diagnostic\'s owned children')
    signal.signal(signal.SIGTERM, interrupted)
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
