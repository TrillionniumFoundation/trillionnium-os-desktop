#!/usr/bin/env python3
"""Actual Shell clicks -> actual Session -> original Supervisor/Agentd.

Only a fresh qualification issuer and private authenticated Xvfb are used.
The original owner performs admission/history; no product issuer, model turn,
external effect, local signer or substitute owner is implied by this test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import tempfile
import time


def check(value, message):
    if not value:
        raise AssertionError(message)


def wait(predicate, message, seconds=10):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        found = predicate()
        if found:
            return found
        time.sleep(.025)
    raise AssertionError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ['probe', 'agentd', 'observer', 'submitter', 'session', 'shell']:
        parser.add_argument('--'+name+'-bin', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    bins = {name: getattr(args, name+'_bin').resolve() for name in ['probe', 'agentd', 'observer', 'submitter', 'session', 'shell']}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    owned, logs, steps = [], [], []
    result = {'schema_version': 1, 'binaries': {name: {'path': str(path), 'sha256': sha(path)} for name, path in bins.items()}, 'steps': steps,
              'scope': 'actual isolated Shell/Session and original Supervisor/Agentd with qualification issuer', 'production_issuer': False, 'device_effect': False, 'model_turn': False}
    stopped_pid = None

    def spawn(command, name, **kwargs):
        stream = (output/name).open('wb')
        logs.append(stream)
        child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True, **kwargs)
        owned.append(child)
        return child

    def kill(child):
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)

    try:
        storage = tempfile.TemporaryDirectory(prefix='ob-')
        temporary = storage.name
        root = Path(temporary)
        result['temporary_storage'] = {'path': temporary, 'device': root.stat().st_dev}
        fleet = root/'owner'
        fleet.mkdir(mode=0o700)
        fixture = spawn([str(bins['probe']), str(bins['agentd']), str(bins['observer']), str(bins['submitter']), str(fleet), '--export-ready'], 'original-owner.log')
        ready_path = fleet/'shell-inbox/ready.json'
        wait(lambda: ready_path.is_file(), 'original Supervisor/Agentd readiness', 65)
        ready = json.loads(ready_path.read_text())
        result['original_ready'] = ready
        config_path = Path(ready['config_path'])
        config = json.loads(config_path.read_text())
        owner_pid = config['owner']['peer_pid']
        journal = Path(ready['journal_path'])
        initial_hash = sha(journal)
        # Authentication is explicit even for this isolated display domain.
        cookie, auth = os.urandom(16), root/'Xauthority'
        def authority(number):
            fields = [b'', str(number).encode() if number is not None else b'', b'MIT-MAGIC-COOKIE-1', cookie]
            auth.write_bytes(struct.pack('!H', 65535)+b''.join(struct.pack('!H', len(v))+v for v in fields))
            auth.chmod(0o600)
        authority(None)
        readfd, writefd = os.pipe()
        server = spawn(['Xvfb', '-displayfd', str(writefd), '-screen', '0', '1600x1100x24', '-nolisten', 'tcp', '-auth', str(auth)], 'xvfb.log', pass_fds=(writefd,))
        os.close(writefd)
        display_start=time.monotonic()
        # Infrastructure startup only; no Session/original transport deadline changes.
        check(select.select([readfd], [], [], 20)[0], 'private Xvfb readiness')
        result['xvfb_startup_seconds']=time.monotonic()-display_start
        number = int(os.read(readfd, 64).strip())
        os.close(readfd)
        authority(number)
        env = dict(os.environ, DISPLAY=f':{number}', XAUTHORITY=str(auth), WINIT_UNIX_BACKEND='x11', WINIT_X11_SCALE_FACTOR='1')
        env.pop('WAYLAND_DISPLAY', None)
        for name in list(env):
            if name.startswith(('TRILL_HEPTA_', 'TRILL_NOTES_')):
                env.pop(name)
        os.environ['XAUTHORITY'] = str(auth)
        runtime = root/'runtime'
        runtime.mkdir(mode=0o700)
        env['XDG_RUNTIME_DIR'] = str(runtime)
        env['XDG_DATA_HOME'] = str(root/'ui-data')
        endpoint = runtime/'trillionnium-ui/session.sock'

        def ipc(value):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                stream.settimeout(2)
                stream.connect(str(endpoint))
                stream.sendall(json.dumps(value, separators=(',', ':')).encode()+b'\n')
                data = bytearray()
                while not data.endswith(b'\n'):
                    part = stream.recv(65536-len(data))
                    check(part, 'Session response EOF')
                    data.extend(part)
                    check(len(data) <= 65536, 'Session response bound')
                return json.loads(data)

        def instance():
            try:
                value = ipc({'type': 'snapshot'})
                return value.get('session_instance')
            except (OSError, AssertionError):
                return None

        def session(tag, configured):
            if configured:
                with config_path.open('rb') as inherited:
                    child = spawn([str(bins['session']), '--objective-config-fd', str(inherited.fileno())], tag+'.log', env=env, pass_fds=(inherited.fileno(),))
            else:
                child = spawn([str(bins['session'])], tag+'.log', env=env)
            identity = wait(instance, 'Session socket readiness')
            return child, identity

        shell_pids = {}

        def shell(tag):
            child = spawn([str(bins['shell']), '--page', 'objectives', '--objective-layout-probe'], tag+'.log', env=env)
            shell_pids[output/(tag+'.log')] = child.pid
            return child, output/(tag+'.log')

        def layout(log):
            for line in reversed(log.read_text(errors='replace').splitlines()):
                if line.startswith('TRILL_OBJECTIVE_LAYOUT_V1 '):
                    return json.loads(line.split(' ', 1)[1])
            return None

        def state(log, predicate, message):
            return wait(lambda: (value if (value := layout(log)) and predicate(value) else None), message)

        def click(log, name):
            value = state(log, lambda v: any(p['name'] == name for p in v['positions']), 'button '+name)
            position = next(p for p in value['positions'] if p['name'] == name)
            windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(shell_pids[log])], env=env, capture_output=True, check=True, timeout=3).stdout.splitlines()
            check(windows, 'owned Shell window present')
            geometry = subprocess.run(['xdotool', 'getwindowgeometry', '--shell', windows[0]], env=env, capture_output=True, check=True, timeout=3).stdout.decode()
            origin = dict(line.split('=', 1) for line in geometry.splitlines() if '=' in line)
            subprocess.run(['xdotool', 'mousemove', str(int(origin['X'])+round(position['x'])), str(int(origin['Y'])+round(position['y'])), 'click', '1'], env=env, check=True, timeout=3)

        def capture(name):
            # Layout probes precede the actual swap. Give the next real paint
            # an opportunity before recording screen pixels, not a new receipt.
            time.sleep(.3)
            from PIL import ImageGrab
            def presented():
                image=ImageGrab.grab(xdisplay=env['DISPLAY'])
                colors=image.getcolors(256)
                return image if colors is None or len(colors)>16 else None
            wait(presented,'actual Shell pixels presented').save(output/(name+'.png'))

        sess, identity = session('session-default', False)
        gui, gui_log = shell('shell-default')
        state(gui_log, lambda v: v['connected'] and not v['configured'], 'default UI submission unavailable')
        check(ipc({'type': 'objective_submit', 'id': 'valid', 'expected_instance': identity})['type'] == 'error', 'default Session cannot submit')
        check(sha(journal) == initial_hash, 'default UI changed original journal')
        capture('01-default-unavailable')
        steps.append('default_ui_and_session_have_no_submission_owner')
        kill(gui)
        kill(sess)

        sess, identity = session('session-configured', True)
        gui, gui_log = shell('shell-configured')
        state(gui_log, lambda v: v['connected'] and v['configured'], 'trusted inbox visible')
        check(sha(journal) == initial_hash, 'rendering inbox submitted without click')
        for command in [
            {'type': 'objective_submit', 'id': 'valid', 'expected_instance': '0'*32},
            {'type': 'objective_submit', 'id': 'valid', 'expected_instance': identity, 'source_envelope_json': 'local draft'},
            {'type': 'objective_submit', 'id': 'missing', 'expected_instance': identity},
        ]:
            check(ipc(command)['type'] == 'error', 'untrusted command was not rejected')
        steps.append('render_only_stale_generation_and_raw_draft_cannot_submit')

        click(gui_log, 'select:invalid')
        state(gui_log, lambda v: v['selected'] and v['selected']['id'] == 'invalid', 'invalid envelope selection')
        click(gui_log, 'review')
        click(gui_log, 'submit')
        bad = state(gui_log, lambda v: v['selected'] and v['selected']['id'] == 'invalid' and v['selected']['delivery'] == 'unknown', 'owner invalid signature remains unknown')
        check(sha(journal) == initial_hash, 'invalid signature published a run')
        check(ipc({'type': 'objective_submit', 'id': 'invalid', 'expected_instance': identity})['type'] == 'error', 'unknown signature attempt was resent')
        click(gui_log, 'query')
        state(gui_log, lambda v: v['selected']['history'] == 'unknown', 'invalid history remains unknown')
        capture('02-invalid-unknown')
        steps.append('real_owner_invalid_signature_no_publication_unknown_no_retry')
        result['invalid'] = bad['selected']

        click(gui_log, 'select:valid')
        state(gui_log, lambda v: v['selected'] and v['selected']['id'] == 'valid', 'valid envelope selection')
        click(gui_log, 'query')
        state(gui_log, lambda v: v['selected']['history'] == 'unknown', 'missing history is unknown')
        check(sha(journal) == initial_hash, 'read-only query published a run')
        click(gui_log, 'review')
        click(gui_log, 'submit')
        admitted = state(gui_log, lambda v: v['selected'] and v['selected']['delivery'] == 'admitted', 'actual original admission')
        changed_hash = sha(journal)
        check(changed_hash != initial_hash, 'original journal did not change')
        independent = subprocess.run([str(bins['observer']), config['owner']['socket_path'], config['owner']['agent_id'], str(config['owner']['spawn_generation']), str(config['owner']['peer_uid']), 'run.shell-valid'], capture_output=True, check=True, timeout=5)
        run = json.loads(independent.stdout)
        check(run['phase'] == 'admitted' and run['terminal_observed'] is False, 'independent original run does not match admission')
        result['independent_original_run'] = run
        result['admitted'] = admitted['selected']
        click(gui_log, 'query')
        historical = state(gui_log, lambda v: v['selected']['history'] == 'historical_publication', 'actual original history publication')
        check(historical['selected']['history_publication_digest'] == admitted['selected']['publication_digest'], 'admission/history mismatch')
        capture('03-admitted-and-history')
        steps.append('actual_shell_click_original_admission_and_independent_run_history_match')

        # A stalled original query must not block Session's public fairness.
        os.kill(owner_pid, signal.SIGSTOP)
        stopped_pid = owner_pid
        click(gui_log, 'query')
        begin = time.monotonic()
        check(ipc({'type': 'snapshot'})['session_instance'] == identity, 'owner stall blocked Session')
        result['stalled_owner_snapshot_seconds'] = time.monotonic()-begin
        check(result['stalled_owner_snapshot_seconds'] < 1, 'snapshot fairness deadline')
        state(gui_log, lambda v: v['selected']['history'] == 'unknown', 'stalled query expires conservatively')
        os.kill(owner_pid, signal.SIGCONT)
        stopped_pid = None
        steps.append('stalled_owner_query_is_bounded_and_session_remains_responsive')

        old_identity = identity
        kill(sess)
        sess, identity = session('session-restarted', True)
        check(identity != old_identity, 'Session generation changed after SIGKILL')
        state(gui_log, lambda v: v['connected'] and v['configured'] and v['selected'] is None, 'Shell discards old selection on Session replacement')
        click(gui_log, 'select:valid')
        recovered = state(gui_log, lambda v: v['selected'] and v['selected']['id'] == 'valid' and v['selected']['delivery'] == 'unknown', 'retained attempt is query-only after SIGKILL')
        check(ipc({'type': 'objective_submit', 'id': 'valid', 'expected_instance': identity})['type'] == 'error', 'restarted Session replayed attempt')
        click(gui_log, 'query')
        recovered = state(gui_log, lambda v: v['selected']['history'] == 'historical_publication', 'original recovery after Session kill')
        check(recovered['selected']['history_publication_digest'] == admitted['selected']['publication_digest'] and sha(journal) == changed_hash, 'recovery changed original publication')
        capture('04-restart-query-only')
        result['recovered'] = recovered['selected']
        steps.append('sigkill_session_reopen_original_query_only_without_duplicate_publication')
        kill(gui)
        kill(sess)
        Path(ready['stop_path']).write_bytes(b'stop')
        check(fixture.wait(timeout=15) == 0, 'original owner stopped and journal inspected')
        final = json.loads((fleet/'shell-inbox/final.json').read_text())
        check(final['active'] is False and len(final['publications']) == 1, 'unexpected original journal publication count')
        check(final['publications'][0]['run_id'] == 'run.shell-valid' and final['publications'][0]['publication_digest'] == admitted['selected']['publication_digest'], 'original durable record mismatch')
        result['original_final'] = final
        steps.append('controlled_stop_read_only_original_journal_matches_actual_ui_receipt')
        # Evidence retains public envelope examples and client markers, no
        # private signing key. The fixture key was never serialized.
        import shutil
        shutil.copytree(fleet/'shell-inbox', output/'inbox-evidence')
        result['status'] = 'passed'
    except BaseException as error:
        result['status'] = 'failed'
        result['error'] = repr(error)
        raise
    finally:
        if stopped_pid is not None:
            try:
                os.kill(stopped_pid, signal.SIGCONT)
            except ProcessLookupError:
                pass
        if 'fixture' in locals() and fixture.poll() is None and 'fleet' in locals():
            inbox = fleet/'shell-inbox'
            if inbox.is_dir():
                (inbox/'stop').write_bytes(b'stop')
            try:
                fixture.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        for child in reversed(owned):
            kill(child)
        if 'storage' in locals():
            storage.cleanup()
        for stream in logs:
            stream.close()
        (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        result['final_binary_sha256'] = {name: sha(path) for name, path in bins.items()}
        stable=all(result['binaries'][name]['sha256']==value for name,value in result['final_binary_sha256'].items())
        result['binaries_unchanged']=stable
        if not stable: result['status']='failed'; result['error']='input ELF changed during qualification'
        (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        check(stable,'input ELF changed during qualification')


if __name__ == '__main__':
    main()
