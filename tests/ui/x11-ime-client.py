"""Operate only the Rust windows on an owned, isolated X11 test display.

XTEST emits ASCII physical-key equivalents into the real XIM/IBus path.
No egui events, Unicode paste, UI memory or agentd messages are injected.
"""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import struct
import time
import zlib


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class XImage(C.Structure):
    _fields_ = [(name, C.c_int) for name in ('width', 'height', 'xoffset', 'format')] + [
        ('data', C.c_void_p)] + [(name, C.c_int) for name in (
        'byte_order', 'bitmap_unit', 'bitmap_bit_order', 'bitmap_pad', 'depth',
        'bytes_per_line', 'bits_per_pixel')] + [
        (name, C.c_ulong) for name in ('red_mask', 'green_mask', 'blue_mask')]


class Display:
    def __init__(self):
        self.lib = C.CDLL('libX11.so.6')
        functions = {
            'XOpenDisplay': ([C.c_char_p], C.c_void_p),
            'XDefaultRootWindow': ([C.c_void_p], C.c_ulong),
            'XCloseDisplay': ([C.c_void_p], C.c_int),
            'XGetImage': ([C.c_void_p, C.c_ulong, C.c_int, C.c_int,
                C.c_uint, C.c_uint, C.c_ulong, C.c_int], C.POINTER(XImage)),
            'XDestroyImage': ([C.POINTER(XImage)], C.c_int),
            'XCreateSimpleWindow': ([C.c_void_p, C.c_ulong, C.c_int, C.c_int,
                C.c_uint, C.c_uint, C.c_uint, C.c_ulong, C.c_ulong], C.c_ulong),
            'XInternAtom': ([C.c_void_p, C.c_char_p, C.c_int], C.c_ulong),
            'XConvertSelection': ([C.c_void_p, C.c_ulong, C.c_ulong,
                C.c_ulong, C.c_ulong, C.c_ulong], C.c_int),
            'XFlush': ([C.c_void_p], C.c_int),
            'XPending': ([C.c_void_p], C.c_int),
            'XNextEvent': ([C.c_void_p, C.c_void_p], C.c_int),
            'XGetWindowProperty': ([C.c_void_p, C.c_ulong, C.c_ulong,
                C.c_long, C.c_long, C.c_int, C.c_ulong,
                C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
                C.POINTER(C.c_ulong), C.POINTER(C.c_void_p)], C.c_int),
            'XFree': ([C.c_void_p], C.c_int),
            'XDestroyWindow': ([C.c_void_p, C.c_ulong], C.c_int),
        }
        for name, (arguments, result) in functions.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.lib.XOpenDisplay(os.environ['DISPLAY'].encode())
        require(self.handle, 'private X display could not be opened')
        self.root = self.lib.XDefaultRootWindow(self.handle)

    def close(self):
        if self.handle:
            self.lib.XCloseDisplay(self.handle)
            self.handle = None

    def screenshot(self, destination):
        image = self.lib.XGetImage(self.handle, self.root, 0, 0,
            1440, 1000, C.c_ulong(-1).value, 2)
        require(image, 'XGetImage did not return a framebuffer')
        try:
            value = image.contents
            require((value.width, value.height, value.bits_per_pixel,
                value.byte_order, value.red_mask, value.green_mask,
                value.blue_mask) == (1440, 1000, 32, 0, 0xff0000, 0xff00, 0xff),
                'unexpected private Xvfb framebuffer format')
            raw = C.string_at(value.data, value.bytes_per_line * value.height)
            rows = []
            for y in range(value.height):
                row = raw[y * value.bytes_per_line:y * value.bytes_per_line + value.width * 4]
                rgb = bytearray(value.width * 3)
                rgb[0::3], rgb[1::3], rgb[2::3] = row[2::4], row[1::4], row[0::4]
                rows.append(b'\x00' + rgb)
            pixels = b''.join(rows)
        finally:
            self.lib.XDestroyImage(image)
        def chunk(kind, content):
            return (struct.pack('!I', len(content)) + kind + content
                + struct.pack('!I', zlib.crc32(kind + content) & 0xffffffff))
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B',
            1440, 1000, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
        destination.write_bytes(png)
        return {'file': destination.name, 'width': 1440, 'height': 1000,
            'bytes': len(png), 'sha256': hashlib.sha256(png).hexdigest(),
            'capture_api': 'XGetImage_actual_private_root_framebuffer',
            'visual_review_required': True}

    def clipboard(self):
        # Read only the disposable display's CLIPBOARD after an explicit copy
        # in an owned Rust editor. This is an output oracle, never text input.
        window = self.lib.XCreateSimpleWindow(self.handle, self.root, 0, 0, 1, 1, 0, 0, 0)
        clipboard = self.lib.XInternAtom(self.handle, b'CLIPBOARD', 0)
        utf8 = self.lib.XInternAtom(self.handle, b'UTF8_STRING', 0)
        property_atom = self.lib.XInternAtom(self.handle, b'A10_PRIVATE_IME_RESULT', 0)
        self.lib.XConvertSelection(self.handle, clipboard, utf8, property_atom, window, 0)
        self.lib.XFlush(self.handle)
        event = (C.c_long * 24)()
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if not self.lib.XPending(self.handle):
                    time.sleep(0.01)
                    continue
                self.lib.XNextEvent(self.handle, C.byref(event))
                if C.cast(C.byref(event), C.POINTER(C.c_int)).contents.value != 31:
                    continue
                actual_type, actual_format = C.c_ulong(), C.c_int()
                count, remaining, data = C.c_ulong(), C.c_ulong(), C.c_void_p()
                result = self.lib.XGetWindowProperty(self.handle, window, property_atom,
                    0, 4096, 1, utf8, C.byref(actual_type), C.byref(actual_format),
                    C.byref(count), C.byref(remaining), C.byref(data))
                try:
                    require(result == 0 and actual_type.value == utf8
                        and actual_format.value == 8 and remaining.value == 0
                        and count.value <= 16384 and data.value,
                        'owned editor did not provide bounded UTF-8 clipboard text')
                    return C.string_at(data, count.value).decode('utf-8')
                finally:
                    if data.value:
                        self.lib.XFree(data)
            raise RuntimeError('owned editor clipboard request timed out')
        finally:
            self.lib.XDestroyWindow(self.handle, window)


def run_ui(output, report, env, command, spawn, alive):
    env.update({'WINIT_UNIX_BACKEND': 'x11', 'LIBGL_ALWAYS_SOFTWARE': '1',
        'LP_NUM_THREADS': '2', 'MESA_SHADER_CACHE_DISABLE': 'true',
        'TRILL_UI_CJK_FONT': '/test-fonts/CJK.ttf', 'TRILL_UI_CJK_FONT_INDEX': '0'})
    os.environ.update(env)
    provenance = json.loads((output / 'probe-provenance.json').read_text())
    ui = {'status': 'running', 'source_commit': provenance['production_ui_commit'],
        'source_tree': provenance['production_ui_tree'], 'harness_provenance': provenance,
        'input_path': 'XTEST_ASCII_keys_to_Xvfb_to_IBus_libpinyin_XIM_to_winit_egui',
        'physical_keyboard_verified': False, 'wayland_v3_verified': False,
        'synthetic_egui_events_used': False, 'unicode_injection_used': False,
        'actions': [], 'screenshots': [], 'owned_windows': {}, 'clipboard_samples': []}
    report['ui'] = ui
    def save():
        (output / 'ui-progress.json').write_text(json.dumps(ui, indent=2, ensure_ascii=False) + '\n')
    def current_snapshot(label):
        result = command(label, ['/ui-bin/trill-ctl', 'snapshot'])
        return json.loads(result.stdout)
    session = spawn('rust-session', ['/ui-bin/trill-session'])
    report['rust_ui_started'] = True
    for attempt in range(100):
        require(alive(session), 'new Rust Session exited before IPC readiness')
        result = command(f'rust-ipc-ready-{attempt:03}', ['/ui-bin/trill-ctl', 'snapshot'], required=False)
        if result.returncode == 0:
            initial = json.loads(result.stdout)
            require(initial['type'] == 'snapshot' and not initial['tasks'], 'private Session was not empty')
            ui['session_instance'] = initial['session_instance']
            break
        require(attempt < 99, 'private Rust Session IPC timeout')
        time.sleep(0.05)
    shell = spawn('rust-shell', ['/ui-bin/trill-shell'])
    for attempt in range(150):
        require(alive(shell), 'new Rust Shell exited before layout')
        if b'TRILL_SHELL_FIRST_FRAME_V1\n' in (output / 'rust-shell.stdout.log').read_bytes():
            break
        require(attempt < 149, 'Rust Shell did not complete layout')
        time.sleep(0.05)
    def window_for(label, pid, klass):
        command(label + '-window-tree-before', ['xwininfo', '-root', '-tree'])
        for attempt in range(100):
            result = command(f'{label}-xid-{attempt:03}', ['xdotool', 'search', '--all',
                '--onlyvisible', '--pid', str(pid), '--class', '^' + klass + '$'], required=False)
            if result.returncode == 0 and result.stdout.strip():
                break
            require(attempt < 99, 'owned Rust window was not mapped')
            time.sleep(0.05)
        ids = result.stdout.decode().split()
        require(len(ids) == 1 and ids[0].isdigit(), 'exactly one owned Rust window required')
        xid = ids[0]
        properties = command(label + '-properties', ['xprop', '-id', xid, 'WM_CLASS', '_NET_WM_PID'])
        require(klass.encode() in properties.stdout and str(pid).encode() in properties.stdout,
            'Rust window identity mismatch')
        ui['owned_windows'][label] = {'xid': xid, 'namespace_pid': pid, 'class': klass}
        return xid
    window_for('shell', shell.process.pid, 'trill-shell')
    display = Display()
    try:
        time.sleep(0.3)
        ui['screenshots'].append(display.screenshot(output / 'ui-initial.png'))
        (output / 'ui-ready.json').write_text(json.dumps(ui, indent=2) + '\n')
        save()
        queue = output / 'commands'
        queue.mkdir(mode=0o700)
        scenario = output / 'replay-scenario.json'
        if scenario.is_file():
            recorded = json.loads(scenario.read_text())
            require(isinstance(recorded, list) and 1 <= len(recorded) <= 80,
                'bounded recorded input scenario required')
            for index, action in enumerate(recorded, 1):
                (queue / f'{index:03}.json').write_text(json.dumps(action) + '\n')
        sequence = 1
        while sequence <= 80:
            require(alive(shell) and alive(session), 'owned Rust process exited during input probe')
            path = queue / f'{sequence:03}.json'
            if not path.is_file():
                time.sleep(0.05)
                continue
            require(path.stat().st_size <= 4096, 'input action is too large')
            request = json.loads(path.read_bytes())
            action = request['action']
            label = f'input-{sequence:03}-{action}'
            item = {'sequence': sequence, 'request': request,
                'started_unix_ms': time.time_ns() // 1_000_000}
            ui['actions'].append(item)
            if action in {'focus', 'click', 'ascii', 'key', 'copy'}:
                target = ui['owned_windows'][request['target']]
                xid = target['xid']
                command(label + '-focus', ['xdotool', 'windowfocus', '--sync', xid])
                focused = command(label + '-focus-observed', ['xdotool', 'getwindowfocus'])
                require(focused.stdout.strip() == xid.encode(), 'owned input focus was not observed')
                if action == 'click':
                    x, y = int(request['x']), int(request['y'])
                    require(0 <= x < 1360 and 0 <= y < 840, 'pointer coordinates outside test bounds')
                    command(label, ['xdotool', 'mousemove', '--window', xid,
                        str(x), str(y), 'click', '1'])
                elif action == 'ascii':
                    text = request['text']
                    require(0 < len(text) <= 128 and all(32 <= ord(c) < 127 for c in text),
                        'only bounded ASCII key input is allowed')
                    command(label, ['xdotool', 'type', '--clearmodifiers', '--delay', '130', '--', text])
                elif action == 'key':
                    key = request['key']
                    require(key in {'space', 'Return', 'Escape', 'BackSpace', 'Tab',
                        'Left', 'Right', 'ctrl+a', 'ctrl+c', 'ctrl+space'}, 'unsupported private key action')
                    command(label, ['xdotool', 'key', '--clearmodifiers', key])
                elif action == 'copy':
                    command(label, ['xdotool', 'key', '--clearmodifiers', 'ctrl+a', 'ctrl+c'])
                    time.sleep(0.15)
                    text = display.clipboard()
                    item['copied_utf8'] = text
                    ui['clipboard_samples'].append({'target': request['target'], 'text': text,
                        'sequence': sequence, 'oracle': 'owned_X11_CLIPBOARD_after_explicit_copy'})
            elif action == 'screenshot':
                ui['screenshots'].append(display.screenshot(output / (label + '.png')))
            elif action == 'snapshot':
                item['snapshot'] = current_snapshot(label)
            elif action == 'notes':
                require('notes' not in ui['owned_windows'], 'only one owned Notes process allowed')
                launched = json.loads(command(label, ['/ui-bin/trill-ctl', 'launch', 'personal', 'notes']).stdout)
                task = launched['task']
                require(task['state'] == 'running' and task['pid'], 'Notes was not running')
                for attempt in range(150):
                    snapshot = current_snapshot(f'{label}-layout-{attempt:03}')
                    observed = next(t for t in snapshot['tasks'] if t['id'] == task['id'])
                    require(observed['state'] == 'running', 'Notes left running before layout')
                    if observed['ui_first_frame_unix_ms']:
                        break
                    require(attempt < 149, 'Notes layout timeout')
                    time.sleep(0.05)
                window_for('notes', task['pid'], 'trill-app-window')
                ui['notes_task'] = task['id']
            elif action == 'finish':
                draft = output / 'state/trillionnium-ui/local-context-drafts-v2.json'
                require(draft.is_file(), 'actual Shell export missing')
                exported = json.loads(draft.read_bytes())
                require(exported == {'version': 2, 'drafts': [
                    {'workspace': 'personal', 'text': '你好', 'contexts': []}
                ]}, 'actual Shell text/context export did not match IME sample')
                require(any(s['target'] == 'shell' and s['text'] == '你好' for s in ui['clipboard_samples']),
                    'actual Shell clipboard text did not match IME sample')
                # A different expected value excludes a stale Shell clipboard
                # being mistaken for Notes' current contents.
                require(any(s['target'] == 'notes' and s['text'] == '中文' for s in ui['clipboard_samples']),
                    'actual Notes text did not match IME sample')
                ui['shell_export'] = {'file': str(draft.relative_to(output)),
                    'sha256': hashlib.sha256(draft.read_bytes()).hexdigest(),
                    'content': exported, 'mode': oct(draft.stat().st_mode & 0o777)}
                require(ui['shell_export']['mode'] == '0o600', 'local export is not private')
                require(all(a['request']['action'] != 'ascii' or a['request']['text'].isascii()
                    for a in ui['actions']), 'non-ASCII input was used')
                command(label + '-cancel', ['/ui-bin/trill-ctl', 'cancel', str(ui['notes_task']),
                    ui['session_instance']])
                for attempt in range(100):
                    snap = current_snapshot(f'{label}-cancel-observed-{attempt:03}')
                    if next(t for t in snap['tasks'] if t['id'] == ui['notes_task'])['state'] == 'cancelled':
                        ui['final_snapshot'] = snap
                        break
                    require(attempt < 99, 'Notes cancellation not observed')
                    time.sleep(0.05)
                ui['status'] = 'passed_private_XIM_ASCII_to_Chinese_in_two_Rust_editors'
                report['rust_ui_ime_verified'] = True
                report['xim_text_committed'] = True
                item['completed_unix_ms'] = time.time_ns() // 1_000_000
                save()
                break
            else:
                raise RuntimeError('unsupported bounded input action')
            time.sleep(0.15)
            item['completed_unix_ms'] = time.time_ns() // 1_000_000
            save()
            (queue / f'{sequence:03}.done.json').write_text(json.dumps(item, ensure_ascii=False, indent=2) + '\n')
            sequence += 1
        require(ui['status'].startswith('passed_'), 'input probe did not reach both real editor oracles')
    finally:
        display.close()
        save()
