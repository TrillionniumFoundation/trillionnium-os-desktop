#!/usr/bin/env python3
"""Capture only a newly created private Weston, using pre-existing A10 ELF files."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path('/workspace/scratch/98f315e377b2/next-ui')
GUARD_SOURCE = ROOT / 'tests/integration/hepta/run_original_agentd.py'
spec = importlib.util.spec_from_file_location('a10_private_group_guard', GUARD_SOURCE)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renderer', choices=['pixman', 'gl'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    runtime = Path(tempfile.mkdtemp(prefix='a10-pixel-preflight-'))
    require(guard.child_anchor_available(), 'waitable child process identity required')
    env = os.environ.copy()
    for name in list(env):
        if name.startswith('TRILL_') or name in ('DISPLAY', 'WAYLAND_SOCKET', 'EFRAME_SCREENSHOT_TO'):
            env.pop(name)
    env.update({
        'XDG_RUNTIME_DIR': str(runtime), 'WAYLAND_DISPLAY': 'a10-pixel-private',
        'XDG_STATE_HOME': str(runtime / 'state'),
        'XDG_CONFIG_HOME': str(runtime / 'config'),
        'XDG_CACHE_HOME': str(runtime / 'cache'),
        'LIBGL_ALWAYS_SOFTWARE': '1', 'EGL_PLATFORM': 'wayland',
    })
    if args.font:
        env['TRILL_UI_CJK_FONT'] = str(args.font.resolve())
    binaries = Path('/workspace/scratch/98f315e377b2/r2-host-target/debug')
    executables = [binaries / name for name in ['trill-shell', 'trill-session']]
    for path in executables:
        require(path.is_file() and os.access(path, os.X_OK), 'existing executable missing')
    report = {
        'source_of_existing_elf': '865ecf381dc8ddb70470ee173add9bd3b4a6a29a',
        'evidence_class': 'private_software_compositor_pixel_preflight',
        'not_proven': ['CJK input method', 'physical monitor or GPU', 'original Agentd', 'device effect'],
        'renderer_requested': args.renderer, 'started_unix_ms': time.time_ns() // 1_000_000,
        'binary_sha256': {p.name: digest(p) for p in executables},
        'guard_source_sha256': digest(GUARD_SOURCE),
        'font': {'path': str(args.font), 'sha256': digest(args.font)} if args.font else None,
        'passed': False,
    }
    groups, logs = [], []

    def spawn(label, command):
        stdout = (output / (label + '.stdout.log')).open('xb')
        stderr = (output / (label + '.stderr.log')).open('xb')
        logs.extend([stdout, stderr])
        child = subprocess.Popen(command, env=env, cwd=output,
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(child)
        groups.append((label, group))
        return group

    def alive(group):
        return group.observe_exit() is None

    def capture(label):
        destination = output / label
        destination.mkdir(mode=0o700)
        with (destination / 'capture.stdout.log').open('xb') as out, (destination / 'capture.stderr.log').open('xb') as err:
            completed = subprocess.run(['weston-screenshooter'], env=env, cwd=destination,
                stdin=subprocess.DEVNULL, stdout=out, stderr=err, timeout=5)
        require(completed.returncode == 0, 'screenshooter returned failure')
        pngs = list(destination.glob('*.png'))
        require(len(pngs) == 1, 'screenshooter did not produce exactly one PNG')
        from PIL import Image
        with Image.open(pngs[0]) as image:
            image.load()
            colors = image.convert('RGB').getcolors(maxcolors=2_000_000)
            require(image.size == (1440, 900), 'unexpected compositor image dimensions')
            require(colors is not None and len(colors) > 20, 'capture lacks real rendered color detail')
            details = {'path': str(pngs[0].relative_to(output)), 'sha256': digest(pngs[0]),
                'size': list(image.size), 'distinct_colors': len(colors), 'bytes': pngs[0].stat().st_size}
        return details

    try:
        weston = spawn('weston', ['weston', '--backend=headless-backend.so',
            '--renderer=' + args.renderer, '--no-config', '--debug', '--width=1440', '--height=900',
            '--idle-time=0', '--socket=' + env['WAYLAND_DISPLAY'], '--log=' + str(output / 'weston.log')])
        ready = False
        for _ in range(80):
            require(alive(weston), 'private compositor exited before registry readiness')
            if (runtime / env['WAYLAND_DISPLAY']).is_socket():
                result = subprocess.run(['wayland-info'], env=env, capture_output=True, timeout=2)
                if result.returncode == 0:
                    (output / 'wayland-registry.stdout.log').write_bytes(result.stdout)
                    (output / 'wayland-registry.stderr.log').write_bytes(result.stderr)
                    report['text_input_v3_advertised'] = b"interface: 'zwp_text_input_manager_v3'" in result.stdout
                    report['text_input_v1_advertised'] = b"interface: 'zwp_text_input_manager_v1'" in result.stdout
                    ready = True
                    break
            time.sleep(.05)
        require(ready, 'private compositor registry round-trip timed out')
        time.sleep(.35)
        report['baseline'] = capture('baseline')
        session = spawn('session', [str(binaries / 'trill-session')])
        shell = spawn('shell', [str(binaries / 'trill-shell')])
        ready = False
        for _ in range(120):
            require(all(alive(g) for g in (weston, session, shell)), 'owned UI process exited before layout')
            if b'TRILL_SHELL_FIRST_FRAME_V1\n' in (output / 'shell.stdout.log').read_bytes():
                ready = True
                break
            time.sleep(.05)
        require(ready, 'existing Shell layout timed out')
        time.sleep(.5)
        report['shell'] = capture('shell')
        require(report['baseline']['sha256'] != report['shell']['sha256'], 'Shell capture unchanged from background')
        report['owned_pids'] = {label: group.process.pid for label, group in groups}
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['cleanup'] = []
        for label, group in reversed(groups):
            try:
                code = guard.terminate_group(group)
                report['cleanup'].append({'label': label, 'reaped': True, 'exit_code': code})
            except Exception as error:
                report['cleanup'].append({'label': label, 'reaped': False, 'error': str(error)})
                report['passed'] = False
        for stream in logs:
            stream.close()
        shutil.rmtree(runtime)
        report['finished_unix_ms'] = time.time_ns() // 1_000_000
        (output / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    require(report['passed'], 'private process cleanup did not complete')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
