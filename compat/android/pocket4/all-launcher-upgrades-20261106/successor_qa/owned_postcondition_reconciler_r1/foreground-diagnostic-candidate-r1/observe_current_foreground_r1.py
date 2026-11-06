#!/usr/bin/env python3
"""One independent readonly current foreground observation, never admission.

Uses the exact existing Flow/R5/private backend and installed helper checks.
It does not call or modify Session.foreground, replay a publisher, resume an
activity, run instrumentation, or create a reconciliation envelope.
"""
import argparse
import datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

STAGED = Path('/home/alex/work/pocket4-beike-owned-postcondition-20261106-baaf68ac0d617dbe3894f714b18f099b')
PUBLISHER = {'path': str(STAGED / 'publish_owned_reconciliation.py'), 'bytes': 41838,
    'sha256': '1c20f6ffb7c8fc260e161a1ac5a95df0852d0daa23bc833c71533ef6964b55a2'}
CORE = {'path': str(STAGED / 'owned_postcondition_core.py'), 'bytes': 28714,
    'sha256': '6f780bdd021942617a6817dbc449eeacc60eeda9972d619fdb192ec4ae313e41'}
FLOW = '/home/alex/work/pocket4-successor-qa-flow-86d1a0aa167743a1842dc30487245feb'
OPERATION = 'owned-qa-readonly-current-foreground'
STEP = 'foreground-after-proof-rejection-01'
FAILURE = {'job_id': '1a1b1f2e015-fc05-7ba9',
    'stdout_sha256': '6018ef68e5fc95822137d56b2bfe9f8ec7cfe805988e9a4df434f2903cade3ab',
    'terminal_sha256': 'b1211031571b1aab3d0d65a8afe9fb0ebf059cd41769f8d25856556454ce660f'}
PRIOR_READER = {'job_id': '1a1b1fcedab-fc05-7be7', 'private_bundle_bytes': 145132,
    'private_bundle_sha256': '387df122065231e47b3e3fe2843166f293ae068b35eda716a260c059833fc781'}
STAT = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
DEADLINE_SECONDS = 180


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def pinned(pin, maximum=131072):
    need(set(pin) == {'path', 'bytes', 'sha256'} and type(pin['bytes']) is int and
         0 < pin['bytes'] <= maximum and re.fullmatch('[0-9a-f]{64}', pin['sha256']), 'EXACT_BOUNDED_PIN')
    path = Path(pin['path'])
    need(path.is_absolute() and all(part not in ('', '.', '..') for part in path.parts[1:]), 'CANONICAL_PIN_PATH')
    owned = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC); owned.append(parent)
        for part in path.parts[1:-1]:
            parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            owned.append(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
        owned.append(fd); first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == 0 and first.st_nlink == 1 and
             not first.st_mode & 0o022 and first.st_size == pin['bytes'], 'ROOT_OWNED_PINNED_SOURCE')
        data = bytearray(); end = time.monotonic() + 10
        while len(data) <= first.st_size:
            need(time.monotonic() < end, 'PIN_READ_DEADLINE')
            part = os.read(fd, min(65536, first.st_size + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        last = os.fstat(fd); current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        need(len(data) == pin['bytes'] and sha(data) == pin['sha256'] and
             all(getattr(first, key) == getattr(last, key) == getattr(current, key) for key in STAT),
             'PIN_BYTES_OR_PATH_CHANGED')
        return bytes(data)
    finally:
        for fd in reversed(owned):
            os.close(fd)


def load(pin, name):
    raw = pinned(pin)
    module = types.ModuleType(name); module.__file__ = pin['path']
    exec(compile(raw, pin['path'], 'exec'), module.__dict__)
    return module


def run(args):
    need(os.getuid() == os.geteuid() == 0, 'ACTUAL_ROOT_REQUIRED')
    os.umask(0o077)
    here = Path(__file__).resolve().parent
    need(here.name.startswith('pocket4-beike-foreground-diagnostic-20261106-') and
         here.parent == Path('/home/alex/work') and here.resolve() == here, 'NEW_FIXED_DIAGNOSTIC_SOURCE_ROOT')
    own_pin = {'path': str(Path(__file__).resolve()), 'bytes': args.source_bytes, 'sha256': args.source_sha256}
    own_raw = pinned(own_pin)
    request_pin = {'path': str(here / 'request.json'), 'bytes': args.request_bytes, 'sha256': args.request_sha256}
    request_raw = pinned(request_pin); request = json.loads(request_raw)
    expected_request = {'schema': 'pocket4-current-beike-foreground-observation-request-v1', 'operation': OPERATION,
        'flow_dir': FLOW, 'step': STEP, 'failure_reference': FAILURE, 'settled_host_reader_reference': PRIOR_READER,
        'diagnostic_only': True, 'mutation_authority': False, 'full_window_text_retained': False}
    need(request == expected_request, 'EXACT_READONLY_DIAGNOSTIC_REQUEST')
    publisher = load(PUBLISHER, 'frozen_publisher_helpers_only_no_entrypoint')
    core = load(CORE, 'fixed_offline_scope_contract')
    boot = publisher.load(publisher.FFI_BOOTSTRAP['path'], publisher.FFI_BOOTSTRAP['sha256'],
        'frozen_exact_library_bootstrap', 131072, publisher.FFI_BOOTSTRAP['bytes'])
    probe = boot.load_module(boot.PROBE_SOURCE, 'frozen_library_and_descriptor_observation')
    before = probe.census()
    need(set(before) == {'0', '1', '2'}, 'INITIAL_STDIO_ONLY_NO_LATE_FD_ADOPTION')
    context = publisher.frozen_context(core)
    need(probe.same_descriptors(before, probe.census()), 'PURE_CONTEXT_OPENED_UNKNOWN_DESCRIPTOR')
    observed_runtime = boot.probe_proof()
    initial, frozen, library_fd, library = boot.initialize_library(probe, observed_runtime)
    flow = action_lock = None
    authority_closed = False
    result = {'schema': 'pocket4-current-beike-foreground-observation-v1', 'ok': False, 'errors': [],
        'started_utc': now(), 'operation': OPERATION, 'step': STEP, 'diagnostic_only': True,
        'mutation_authority': False, 'reconciliation_published': False, 'publisher_retried': False,
        'Session_foreground_predicate_changed': False, 'full_window_text_retained': False,
        'UI_actions': 0, 'instrumentation_calls': 0, 'App_installs': 0, 'permission_grants': 0,
        'activity_resume_or_activation': 0, 'Bili_actions': 0, 'original_unknown_changed': False,
        'business_success_verified': False, 'production_ready': False, 'automatic_retry': False,
        'source_sha256': sha(own_raw), 'request_sha256': sha(request_raw),
        'historical_failure_reference': FAILURE, 'historical_reader_reference': PRIOR_READER,
        'historical_foreground_package_reconstructed': False,
        'acceptance_requires_original_final_stdout_and_authoritative_durable_terminal': True}
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        own, qa, build, recorder_manifest, unused_transport = context
        recorder = own.load(publisher.RECORDER_ROOT / 'recorder.py', recorder_manifest['files']['recorder.py']['sha256'],
                            'unchanged_current_readonly_flow')
        fargs = types.SimpleNamespace(operation=OPERATION, adapter_manifest_sha256=core.RECORDER_MANIFEST,
            flow_dir=Path(FLOW), epoch_module=publisher.RECORDER_ROOT / 'references/framework_epoch.py',
            task_source=publisher.RECORDER_ROOT / 'references/task_scope_baseline.py', step=STEP,
            request={'diagnostic_source_sha256': sha(own_raw), 'diagnostic_request_sha256': sha(request_raw),
                     'failure_reference': FAILURE, 'mutation_authority': False},
            unknown_step=None, observation_step=None, postcondition=None)
        flow = recorder.Flow(fargs)
        flow.begin(fargs, mutation=False)
        action_lock = recorder.lock_file(recorder.ACTION_LOCK)
        core.fixed_scope(flow.scope)
        need(flow.scope['package'] == 'com.lianjia.beike' and flow.scope['uid'] == 10143, 'ONLY_EXISTING_BEIKE_SCOPE')
        launch = flow.selected_task(); core.fixed_launch(launch)
        binding = flow.bind()
        session = own.Session(flow, recorder, qa, build, core.HELPER_UID)
        installed = session.installed()
        need(time.monotonic() < deadline, 'DIAGNOSTIC_DEADLINE_BEFORE_TASK')
        unused_raw, roots, tasks = flow.stacks()
        target_root = roots.get(core.TASK)
        exact_task = flow.tasks.exact_leaf(roots, core.TASK, core.PACKAGE)
        task_observed_utc = now()
        # The unchanged parser discards its full raw window text. Calling it
        # here only observes another current package; it grants no authority.
        # Session.foreground and all helper mutation predicates remain intact.
        backend = flow.contract.load('references/android_backend.py', 'readonly_current_foreground_parser')
        need(not flow._private_backend_transport, 'NO_NESTED_PRIVATE_BACKEND')
        flow._private_backend_transport = True
        try:
            backend.arun = lambda argv, timeout=30: flow.android(argv, timeout, mutation=False)
            foreground = backend.foreground()
        finally:
            flow._private_backend_transport = False
        foreground_observed_utc = now()
        need(type(foreground) is dict and set(foreground) == {'package', 'activity', 'window_token'} and
             all(type(value) is str and 0 < len(value) <= 512 for value in foreground.values()), 'COMPACT_FROZEN_FOREGROUND_RESULT')
        need(flow.command_index == 3 and flow.transport._sequence == 4 and flow.action_attempted is False,
             'EXACT_THREE_RECORDED_COMMANDS_AND_ONE_PRIVATE_READ')
        need(time.monotonic() < deadline, 'DIAGNOSTIC_DEADLINE_AFTER_READ')
        flow.guard(attempted=False); binding.verify(); flow.contract.verify()
        own.own_source(core.HELPER_MANIFEST)
        need(pinned(PUBLISHER) and pinned(CORE) and pinned(own_pin) == own_raw and pinned(request_pin) == request_raw,
             'ORIGINAL_SOURCE_AND_REQUEST_PINS_UNCHANGED')
        flow.close(); authority_closed = True
        flow.source.runtime_and_app_guard(flow.current_guard)
        flow.epoch.require_unchanged(flow.activation['framework_epoch'], action_attempted=False)
        current = probe.census()
        lock_fds = (flow.lock, action_lock)
        need(len(set(lock_fds)) == 2 and all(type(fd) is int and str(fd) not in frozen for fd in lock_fds),
             'TWO_KNOWN_OWNED_FINAL_LOCK_DESCRIPTORS')
        expected = {**frozen, **{str(fd): current[str(fd)] for fd in lock_fds}}
        publisher._fd_subset(probe, current, expected)
        need(boot.stable_library(probe.library_binding(library_fd, current[str(library_fd)])) == boot.stable_library(library),
             'ORIGINAL_LIBRARY_RESOURCE_UNCHANGED')
        result.update(ok=True, foreground=foreground, foreground_observed_utc=foreground_observed_utc,
            foreground_package_matches_target=foreground['package'] == core.PACKAGE,
            foreground_window_type='NOT_QUERIED', target_task_observed_utc=task_observed_utc,
            task_and_foreground_are_sequential_observations=True,
            target_task={'id': core.TASK, 'present': core.TASK in tasks, 'exact_leaf': exact_task, 'root': target_root},
            installed_helper={key: installed[key] for key in ('package', 'uid', 'bytes', 'apk_sha256', 'signer_bound_by_exact_signed_apk_bytes')},
            framework_epoch_sha256=core.MAIN_EPOCH, runtime_epoch_sha256=core.RUNTIME_EPOCH,
            app_scope_sha256=core.APP_SCOPE, held_namespace_authority_released=True,
            recorded_readonly_commands=3, private_foreground_reads=1, unknown_descriptors=[],
            explicit_library_resource={'path': library['path'], 'bytes': library['bytes'], 'sha256': library['sha256'],
                                       'manual_close': False, 'retirement': 'normal process exit'},
            flow_and_action_locks_held_until_process_exit=True,
            final_fd_set_exactly_explicit_library_plus_original_streams_and_two_owned_locks=True)
        recorder.write_new(flow.step / 'diagnostic-source.py', own_raw)
        recorder.write_new(flow.step / 'diagnostic-request.json', request_raw)
        result['ended_utc'] = now()
        recorder.write_new(flow.step / 'result.json', result)
        publisher._fd_subset(probe, probe.census(), expected)
        flow.source.runtime_and_app_guard(flow.current_guard)
        flow.epoch.require_unchanged(flow.activation['framework_epoch'], action_attempted=False)
        publisher._fd_subset(probe, probe.census(), expected)
    except BaseException as error:
        result['ok'] = False
        result['errors'].append({'type': type(error).__name__, 'code': str(error)[:512]})
    finally:
        if flow is not None and not authority_closed:
            try:
                flow.close()
            except BaseException as error:
                result['ok'] = False
                result['errors'].append({'phase': 'held_authority_release', 'type': type(error).__name__, 'code': str(error)[:256]})
    result['ended_utc'] = now()
    raw = json.dumps(result, ensure_ascii=True, sort_keys=True)
    need(len(raw.encode()) <= 16384, 'BOUNDED_COMPACT_DIAGNOSTIC_RESULT')
    print(raw, flush=True)
    return 0 if result['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observe-once', action='store_true')
    parser.add_argument('--source-sha256')
    parser.add_argument('--source-bytes', type=int)
    parser.add_argument('--request-sha256')
    parser.add_argument('--request-bytes', type=int)
    args = parser.parse_args()
    if not args.observe_once:
        print(json.dumps({'status': 'PLAN_ONLY', 'Main_commands': 0, 'mutation_authority': False}))
        return 0
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
