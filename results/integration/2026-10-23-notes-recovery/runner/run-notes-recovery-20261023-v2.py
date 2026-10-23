#!/usr/bin/env python3
"""Build and qualify this isolated Notes source pair without committing it.

The GUI uses the original writer with an explicit test issuer. The separate
Python bootstrap and broker probes are transport fixtures, never production.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time


ROOT = Path('/home/qian-qi/work/trillionnium-os-20261021-b2da20752f15')
OS_REPO = ROOT / 'os-notes-recovery-20261023'
HEPTA_REPO = ROOT / 'hepta-notes-recovery-20261023'
OS_TARGET = ROOT / 'target-notes-ui-20261023'
HEPTA_TARGET = ROOT / 'target-hepta-compact'
OS_BASE = '1f4a252c22adf3bc4e1de1ce655e42387070f503'
HEPTA_BASE = '6d6097da843f5831dfaf9cee3530da512d072a15'
STEPS = []


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def save(name, value):
    path = OUT / name
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    temporary.replace(path)


def git(repo, *args, env=None):
    return subprocess.check_output(
        ['git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
         '-C', str(repo), *args], env=env or ENV)


def snapshot(repo, name, expected_head):
    require(repo.resolve() == repo and repo.is_dir(), 'unexpected source repository location')
    require(Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()) == repo,
            'source path must be its repository root')
    head = git(repo, 'rev-parse', 'HEAD').decode().strip()
    require(head == expected_head, name + ' HEAD changed from its explicitly selected base')
    flags = git(repo, 'ls-files', '-v', '-z').split(b'\0')
    require(not any(item and (item[:1].islower() or item[:1] == b'S') for item in flags),
            name + ' has index flags that can conceal worktree changes')
    # The temporary index is owned by this output directory. No real index,
    # branch, commit, live runtime, credential or grant is changed.
    selected = dict(ENV, GIT_INDEX_FILE=str(OUT / (name + '.index')))
    git(repo, 'read-tree', 'HEAD', env=selected)
    git(repo, 'add', '--all', '--', '.', env=selected)
    worktree = git(repo, 'write-tree', env=selected).decode().strip()
    return {'path': str(repo), 'head': head,
            'head_tree': git(repo, 'rev-parse', 'HEAD^{tree}').decode().strip(),
            'worktree_tree': worktree,
            'status': git(repo, 'status', '--porcelain=v1', '--untracked-files=all').decode()}


def sources():
    return {'os': snapshot(OS_REPO, 'os', ARGS.os_head),
            'hepta': snapshot(HEPTA_REPO, 'hepta', ARGS.hepta_head)}


def run(name, argv, cwd, env):
    row = {'name': name, 'argv': argv, 'cwd': str(cwd), 'status': 'running',
           'started_unix': time.time()}
    STEPS.append(row)
    save('steps.json', STEPS)
    print('STEP_START', name, flush=True)
    with (OUT / (name + '.log')).open('wb') as stream:
        code = subprocess.run(argv, cwd=cwd, env=env, stdout=stream,
                              stderr=subprocess.STDOUT).returncode
    row.update(status='passed' if code == 0 else 'failed', exit_code=code,
               finished_unix=time.time())
    save('steps.json', STEPS)
    print('STEP_END', name, code, flush=True)
    require(code == 0, name + ' failed with exit ' + str(code))


def json_log(name):
    values = []
    for line in (OUT / (name + '.log')).read_text().splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and 'profile' in value:
            values.append(value)
    require(len(values) == 1, name + ' did not produce exactly one qualification object')
    return values[0]


def freeze_binaries():
    directory = OUT / 'bin'
    directory.mkdir(mode=0o700)
    records = {}
    for role, built in (
            ('session', OS_TARGET / 'debug/trill-session'),
            ('app', OS_TARGET / 'debug/trill-app-window'),
            ('broker_probe', OS_TARGET / 'debug/examples/notes_host_probe')):
        require(built.is_file() and os.access(built, os.X_OK), 'missing newly built ' + role)
        frozen = directory / built.name
        shutil.copy2(built, frozen)
        digest = sha(built)
        require(sha(frozen) == digest, 'binary changed while freezing ' + role)
        records[role] = {'build_path': str(built), 'path': str(frozen),
                         'bytes': frozen.stat().st_size, 'sha256': digest}
    save('companion-binaries.json', records)
    return records


def actual_gui(companion):
    gui = OUT / 'gui'
    gui.mkdir(mode=0o700)
    runtime = gui / 'runtime'
    runtime.mkdir(mode=0o700)
    auth = gui / 'xauthority'
    auth.touch(mode=0o600)
    display = next((':' + str(number) for number in range(195, 226)
                    if not Path('/tmp/.X11-unix/X' + str(number)).exists()
                    and not Path('/tmp/.X' + str(number) + '-lock').exists()), None)
    require(display is not None, 'no unused owned Xvfb display')
    xenv = dict(HEPTA_ENV, DISPLAY=display, XAUTHORITY=str(auth),
                XDG_RUNTIME_DIR=str(runtime), WINIT_UNIX_BACKEND='x11',
                LIBGL_ALWAYS_SOFTWARE='1', TRILL_NOTES_PROBE_ISOLATED='1',
                HEPTA_NOTES_SESSION_BIN=companion['session']['path'],
                HEPTA_NOTES_QUALIFICATION_OUTPUT=str(gui / 'original-owner-receipt.json'))
    subprocess.run(['xauth', '-f', str(auth), 'add', display, '.', secrets.token_hex(16)],
                   env=xenv, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    with (gui / 'xvfb.log').open('wb') as stream:
        server = subprocess.Popen(
            ['Xvfb', display, '-nolisten', 'tcp', '-screen', '0', '1280x800x24',
             '-auth', str(auth)], env=xenv, stdout=stream, stderr=subprocess.STDOUT)
        try:
            until = time.monotonic() + 10
            while True:
                require(server.poll() is None, 'owned Xvfb exited before readiness')
                result = subprocess.run(['xdpyinfo', '-display', display], env=xenv,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        timeout=2)
                if result.returncode == 0:
                    break
                require(time.monotonic() < until, 'owned Xvfb readiness timed out')
                time.sleep(0.05)
            denied = dict(xenv, XAUTHORITY=str(gui / 'missing-cookie'))
            require(subprocess.run(['xdpyinfo', '-display', display], env=denied,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=2).returncode != 0,
                    'owned Xvfb accepted a missing-cookie client')

            run('python-bootstrap-v2', [sys.executable,
                str(OS_REPO / 'tests/ui/test-notes-bootstrap-ipc.py'), str(OUT / 'bin')],
                cwd=OS_REPO, env=xenv)
            bootstrap = json_log('python-bootstrap-v2')
            require(bootstrap.get('bootstrap_schema_version') == 2
                    and bootstrap.get('ordered_private_endpoints') == ['effect_stream', 'recovery_datagram']
                    and bootstrap.get('actual_app_read_only_query') is True
                    and bootstrap.get('recovery_lane_rejects_replace') is True
                    and bootstrap.get('document_revision') == 0
                    and bootstrap.get('hepta_production_owner_run') is False
                    and bootstrap.get('final_use_authority_run') is False,
                    'bootstrap probe did not establish the expected transport-only boundary')
            save('bootstrap-receipt.json', bootstrap)

            run('broker-target-probe', [companion['broker_probe']['path'], companion['app']['path']],
                cwd=OS_REPO, env=xenv)
            target = json_log('broker-target-probe')
            require(target.get('independent_application_receipt_query') is True
                    and target.get('hepta_production_owner_run') is False
                    and target.get('final_use_authority_run') is False
                    and target.get('compositor_pixels_verified') is False,
                    'broker probe did not retain its target-only qualification boundary')
            save('broker-target-receipt.json', target)

            run('actual-gui-original-owner', ['nice', '-n', '10', 'just', 'test', '--locked',
                '-p', 'codex-hepta-agentd', 'notes_actual_ui_original_owner_roundtrip',
                '--run-ignored', 'only'], cwd=HEPTA_REPO / 'codex-rs', env=xenv)
            receipt = json.loads((gui / 'original-owner-receipt.json').read_text())
            require(all(receipt.get(name) is False for name in
                        ('production_authority', 'native_kernel_qualified', 'pixels_qualified')),
                    'test issuer qualification was mislabeled as production/native/pixels')
            require(receipt.get('bootstrap_schema_version') == 2
                    and receipt.get('recovery_transport') == 'private_unix_datagram'
                    and receipt.get('receipt_capacity_reused_after_durable_ack') is True
                    and receipt.get('issuer_requests') == 4,
                    'GUI did not establish three original-owner edits after one refused grant request')
            for role in ('session', 'app'):
                require(receipt[role + '_sha256'] == companion[role]['sha256'],
                        'original-owner test consumed a different ' + role + ' binary')
            first = receipt['application_receipt']
            second = receipt['second_application_receipt']
            require(first['target'] == second['target']
                    and first['operation_id'] != second['operation_id'],
                    'two effects must target one incarnation with distinct original operations')
            third = receipt['recovered_application_receipt']
            require(first['target'] == third['target']
                    and third['operation_id'] not in (first['operation_id'], second['operation_id']),
                    'recovery must refer to the third operation on the same application incarnation')
            for application, previous in ((first, 0), (second, 1), (third, 2)):
                result = application['result']
                require(result['status'] == 'applied'
                        and result['previous_revision'] == previous
                        and result['revision'] == previous + 1,
                        'actual Notes revision chain differs from 0 -> 1 -> 2 -> 3')
            require(receipt.get('lost_reply_initial_source_state') == 'indeterminate'
                    and receipt.get('lost_reply_recovered_source_state') == 'committed'
                    and receipt.get('complete_frame_written_then_effect_stream_closed') is True
                    and receipt.get('effect_reply_read_by_fault_fixture') is False
                    and receipt.get('effect_dispatch_attempts') == 3
                    and receipt.get('injected_complete_frame_writes') == 1
                    and receipt.get('recovery_effect_replay') is False
                    and receipt.get('recovery_requested_new_grant') is False,
                    'real effect-stream loss did not recover through the original writer without replay')
            recovered_raw = receipt['recovered_application_receipt_utf8'].encode()
            recovered_digest = hashlib.sha256(recovered_raw).hexdigest()
            require(json.loads(recovered_raw) == third
                    and recovered_digest == receipt['recovered_receipt_sha256'],
                    'recovered complete application receipt bytes differ from their digest')
            retired = receipt['recovered_retirement_response']
            require(retired['target'] == third['target']
                    and retired['operation_id'] == third['operation_id']
                    and retired['payload_sha256'] == third['payload_sha256']
                    and retired['receipt_sha256'] == recovered_digest
                    and retired['status'] in ('released', 'already_released'),
                    'actual retirement ACK did not match the recovered complete receipt')
            return receipt
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
            else:
                server.wait()


def main():
    before = sources()
    save('source-before.json', before)
    for name, expected in (('os', ARGS.os_worktree), ('hepta', ARGS.hepta_worktree)):
        if expected is not None:
            require(before[name]['worktree_tree'] == expected, name + ' expected worktree tree differs')
    for tool in ('cargo', 'rustc', 'just', 'Xvfb', 'xauth', 'xdpyinfo'):
        require(shutil.which(tool, path=ENV['PATH']) is not None, 'required tool unavailable: ' + tool)
    for role, paths in json.loads((OS_REPO / 'support/release/organ_source_map.json').read_text())['goldens'].items():
        left, right = OS_REPO / paths['os'], HEPTA_REPO / paths['hepta']
        require(left.read_bytes() == right.read_bytes(), 'cross-repository golden mismatch: ' + role)
    run('toolchain', ['rustc', '--version', '--verbose'], cwd=ROOT, env=ENV)
    run('build-desktop-binaries', ['nice', '-n', '10', 'cargo', 'build', '--locked',
        '-p', 'trill-session', '-p', 'trill-app-window', '--bins'], cwd=OS_REPO / 'ui', env=UI_ENV)
    run('build-broker-probe', ['nice', '-n', '10', 'cargo', 'build', '--locked',
        '-p', 'trill-ui-broker', '--example', 'notes_host_probe'], cwd=OS_REPO / 'ui', env=UI_ENV)
    require(sources() == before, 'source HEAD/worktree changed during companion build')
    companion = freeze_binaries()
    receipt = actual_gui(companion)
    after = sources()
    save('source-after.json', after)
    require(after == before, 'source HEAD/worktree changed during qualification')
    for role, record in companion.items():
        require(sha(record['path']) == record['sha256'], 'frozen companion binary changed: ' + role)
    save('qualification.json', {
        'schema_version': 1, 'status': 'passed', 'source': before,
        'working_tree_hash_algorithm': 'Git tree from HEAD plus all nonignored worktree files using an isolated index',
        'source_was_committed_by_runner': False,
        'production_authority': False, 'native_asterinas': False, 'pixels_qualified': False,
        'app_process_restart_recovery_qualified': False,
        'agentd_process_restart_descriptor_recovery_qualified': False,
        'same_live_app_effect_stream_loss_recovery_qualified': True,
        'original_owner_gui_receipt': receipt,
        'bootstrap_fixture_receipt': json.loads((OUT / 'bootstrap-receipt.json').read_text()),
        'broker_target_fixture_receipt': json.loads((OUT / 'broker-target-receipt.json').read_text()),
        'companion_binaries': companion,
    })
    print('QUALIFICATION_PASSED', str(OUT / 'qualification.json'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory outside both source repositories')
    parser.add_argument('--toolchain', default='1.95.0')
    parser.add_argument('--os-head', default=OS_BASE)
    parser.add_argument('--hepta-head', default=HEPTA_BASE)
    parser.add_argument('--os-worktree', help='optional explicitly expected full Git worktree tree')
    parser.add_argument('--hepta-worktree', help='optional explicitly expected full Git worktree tree')
    ARGS = parser.parse_args()
    OUT = ARGS.output.resolve()
    require(OUT.is_relative_to(ROOT) and OUT != ROOT
            and not any(OUT.is_relative_to(repo) for repo in (OS_REPO, HEPTA_REPO)),
            'output must be a new task-owned directory outside source repositories')
    OUT.mkdir(mode=0o700, exist_ok=False)
    ENV = dict(os.environ)
    for name in list(ENV):
        if name.startswith('TRILL_HEPTA_') or name.startswith('HEPTA_NOTES_'):
            ENV.pop(name)
    ENV.update(PATH='/home/qian-qi/.cargo/bin:' + ENV.get('PATH', ''),
               RUSTUP_TOOLCHAIN=ARGS.toolchain, CARGO_PROFILE_DEV_DEBUG='0',
               CARGO_PROFILE_TEST_DEBUG='0', CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='4',
               GIT_TERMINAL_PROMPT='0', GIT_NO_REPLACE_OBJECTS='1', PYTHONDONTWRITEBYTECODE='1')
    for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY'):
        ENV.pop(name, None)
    UI_ENV = dict(ENV, CARGO_TARGET_DIR=str(OS_TARGET))
    HEPTA_ENV = dict(ENV, CARGO_TARGET_DIR=str(HEPTA_TARGET))
    try:
        main()
    except BaseException as error:
        save('failure.json', {'type': type(error).__name__, 'message': str(error)})
        print('QUALIFICATION_FAILED', type(error).__name__, str(error), flush=True)
        raise
    finally:
        records = {}
        for path in sorted(OUT.rglob('*')):
            if path.is_file() and path.name != 'xauthority' and path.suffix != '.index':
                records[str(path.relative_to(OUT))] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
        save('artifact-sha256.json', records)
