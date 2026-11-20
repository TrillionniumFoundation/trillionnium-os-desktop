"""One fresh-Main, complete Gallery candidate ART verification; no install/UI."""
from pathlib import Path
import contextlib
import io
import json
import os
import signal
import struct
import time
import zipfile

NAMES_REF = {'bytes': 119880, 'path': '/home/alex/work/pocket4-android-final/qualification/gallery-qpr1-current-inputs-20261108-8b88-r1/inputs/expected-2144-descriptors.json', 'sha256': '48784ff0a225c9319f685c86b44772d2240809a857686965aab3cdbe8b0d265e'}
DEX_SHA = '6a994fabd3494dcbf071d727922351f72ff8fdbee0d3d3c1a46b6ed30ca034ee'
WORK_SECONDS = 350


def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def own_file(path, raw, stack, *, mode, uid):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    stack.callback(os.close, fd); os.fchown(fd, uid, 1000); os.fchmod(fd, mode)
    offset = 0
    while offset < len(raw):
        count = os.write(fd, raw[offset:]); need(count > 0, 'OWN_FILE_WRITE_PROGRESS'); offset += count
    os.fsync(fd)
    return fd


def own_candidate(root, raw, stack, support):
    directory = root / 'candidate'; directory.mkdir(mode=0o750); os.chown(directory, 0, 1000)
    own_file(directory / 'candidate.apk', raw, stack, mode=0o444, uid=0)
    source = os.open(directory / 'candidate.apk', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    stack.callback(os.close, source)
    marker_raw = ('pocket4-gallery-current-art:' + support.APK_SHA + '\n').encode()
    own_file(directory / 'marker', marker_raw, stack, mode=0o444, uid=0)
    marker = os.open(directory / 'marker', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    stack.callback(os.close, marker)
    oat = own_file(directory / 'candidate.odex', b'', stack, mode=0o440, uid=2000)
    vdex = own_file(directory / 'candidate.vdex', b'', stack, mode=0o440, uid=2000)
    os.chmod(directory, 0o555)
    dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    stack.callback(os.close, dirfd)
    need(support.pin_fd(source)['sha256'] == support.APK_SHA, 'OWN_CANDIDATE_APK_CHANGED')
    return {'source': source, 'marker': marker, 'oat': oat, 'vdex': vdex, 'directory': dirfd}


def verifier_plans(session, before, flattened, own, boot_fds, context_fds, support):
    extras = (*boot_fds, *context_fds, own['source'], own['oat'], own['vdex'], own['directory'], own['marker'])
    need(len(boot_fds) == 52 and len(context_fds) == len(flattened) == 4
         and len(set(extras)) == len(extras), 'ACTUAL_52_PLUS_4_DISTINCT_INPUT_FDS')
    writable = (own['oat'], own['vdex']); expected = b'2000\n'; rows = []
    for fd in extras:
        info = os.fstat(fd)
        expected += f'/proc/self/fd/{fd}:{info.st_dev}:{info.st_ino}:{info.st_size}\n'.encode()
        rows.append({'fd': fd, 'identity': support.metadata(info), 'writable': fd in writable})
    script = "set -eu\n/system/bin/id -u\n/system/bin/toybox stat -L -c '%n:%d:%i:%s' "
    script += ' '.join('/proc/self/fd/' + str(fd) for fd in extras)
    script += f'\n/system/bin/cat /proc/self/fd/{own["marker"]} /proc/self/fd/{own["directory"]}/marker\n'
    expected += os.pread(own['marker'], 512, 0) * 2
    session.register('verifier-fd-proof', ['/system/bin/sh', '-c', script],
                     extras=extras, writable=writable, timeout=15)
    context = before['gallery_context']['class_loader_context']
    compiler = [support.DEX2OAT, f'--zip-fd={own["source"]}', '--zip-location=' + '/product/app/Gallery2/Gallery2.apk',
        f'--oat-fd={own["oat"]}', f'--output-vdex-fd={own["vdex"]}',
        f'--oat-location=/proc/self/fd/{own["directory"]}/candidate.odex', '--instruction-set=x86_64',
        '--boot-image=' + before['compiler_boot_image_argument'],
        '--runtime-arg', '-Xbootclasspath:' + ':'.join(before['bootclasspath']),
        '--runtime-arg', '-Xbootclasspathfds:' + ':'.join(map(str, boot_fds)),
        '--class-loader-context=' + context,
        '--class-loader-context-fds=' + ':'.join(map(str, context_fds)),
        '--compiler-filter=verify', '--abort-on-hard-verifier-error', '--abort-on-soft-verifier-error',
        '--copy-dex-files=always', '--runtime-arg', '-Xms32m', '--runtime-arg', '-Xmx768m', '-j2']
    session.register('compiler', compiler, extras=extras, writable=writable, timeout=90)
    prefix = [support.OATDUMP, f'--oat-file=/proc/self/fd/{own["directory"]}/candidate.odex',
        f'--dex-file=/proc/self/fd/{own["directory"]}/candidate.apk', '--no-disassemble', '--no-dump:vmap']
    for kind, selector in [('all-class-status', '--list-classes'),
            ('method-exif', '--class-filter=com.android.gallery3d.exif.ExifInterface'),
            ('method-operation', '--class-filter=com.android.gallery3d.ui.MenuExecutor$MediaOperation')]:
        session.register(kind, [*prefix, selector], extras=extras, writable=writable, timeout=35)
    return expected, rows, compiler


class Deadline(BaseException):
    pass


def execute(request, preparation_ref, root, common, originals, held_reader, support, closure, parser):
    raise RuntimeError('CP3A_OFFICIAL_FULL_GSI_ONLY_OLD_MODIFIED_CANDIDATE_RUNTIME_ENTRY_RETIRED')
    result = {'schema': 'pocket4-gallery-qpr1-art-qualification-v2', 'state': 'FAILED',
        'baseline': request['baseline'], 'qualification': request['qualification'],
        'source_preparation': preparation_ref, 'candidate_sha256': support.APK_SHA,
        'candidate_dex_sha256': DEX_SHA, 'historical_runtime_authority_transferred': False,
        'same_historical_ART17_code_closure_claimed': False, 'installed': False,
        'UI_actions': 0, 'package_mutations': 0, 'Gallery_code_executions': 0,
        'whole_app_business_accepted': False, 'automatic_retry': False,
        'compiler_attempts': 0, 'analyzer_attempts': 0, 'oatdump_attempts': 0,
        'actual_completed_command_counts': None,
        'all_2144_stored_statuses_verified': False, 'both_modified_methods_verified': False,
        'session_closed': False, 'candidate_fd_closed': False, 'global_action_lock_exited': False,
        'started_unix_ns': time.time_ns()}
    start = time.monotonic(); deadline = start + WORK_SECONDS
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*unused):
        raise Deadline('GALLERY_CURRENT_ART_ABSOLUTE_WORK_DEADLINE')
    signal.signal(signal.SIGALRM, expired); signal.setitimer(signal.ITIMER_REAL, WORK_SECONDS)
    session = None
    try:
        result['resources_before'] = support.resources()
        result['host_inputs_before'] = originals['install'].host_evidence()
        names = common.parse(common.read_ref(NAMES_REF, 131072))
        need(type(names) is list and len(names) == len(set(names)) == 2144, 'ALL_CURRENT_QPR1_DEX_CLASSES_REQUIRED')
        with common.locked(support.ACTION_LOCK, wait_seconds=5):
            with originals['stdin'].HeldApk() as candidate:
                result['held_candidate_before'] = candidate.verify()
                result['payload_scope'] = originals['install'].payload_exact(candidate, originals['identity'])
                raw = os.pread(candidate.fd, support.APK_BYTES + 1, 0)
                need(len(raw) == support.APK_BYTES and common.sha(raw) == support.APK_SHA, 'EXACT_SIGNED_CANDIDATE')
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    dex = archive.read('classes.dex')
                need(len(dex) == 1886696 and common.sha(dex) == DEX_SHA
                     and originals['dex'].dex_classes(dex, names)[0] == names,
                     'ACTUAL_CANDIDATE_DEX_CLASS_SET')
                checksum = struct.unpack_from('<I', dex, 8)[0]
                result['dex_header_checksum'] = checksum
                session = support.Session(common, held_reader, request, root, deadline)
                try:
                    result['main_before'] = session.guard()
                    result['home_before'] = closure.fresh_home(session, originals['identity'])
                    before = closure.snapshot(session, originals['context'], originals['identity'])
                    result['closure_before'] = common.write_new(root / 'code-closure-before.json', before)
                    context = before['gallery_context']['class_loader_context']
                    session.register('flatten', [support.ANALYZER, '--flatten-class-loader-context',
                                                '--class-loader-context=' + context], timeout=20, expected_rc=50)
                    result['analyzer_attempts'] = 1
                    flattened_raw, stderr, flatten_ref = session.run('flatten')
                    need(not stderr and len(flattened_raw) <= 4096, 'BOUNDED_ACTUAL_CONTEXT_FLATTEN_OUTPUT')
                    text = flattened_raw.decode('ascii', 'strict').strip()
                    need(text and '\n' not in text and '\r' not in text, 'ONE_ACTUAL_FLATTENED_CONTEXT_LINE')
                    flattened = text.split(':')
                    need(len(flattened) == 4 and set(flattened) == set(originals['context'].FILES),
                         'ACTUAL_FOUR_GALLERY_CONTEXT_OCCURRENCES_REQUIRED')
                    result['actual_context_flatten'] = {'receipt': flatten_ref, 'order': flattened,
                        'duplicates_preserved': True, 'class_loader_context': context}
                    with contextlib.ExitStack() as stack:
                        boot_fds = []; context_fds = []; held_pins = {}
                        for paths, target in ((before['bootclasspath'], boot_fds), (flattened, context_fds)):
                            for path in paths:
                                fd = session.target.open_root(path, os.O_RDONLY)
                                stack.callback(os.close, fd)
                                pin = support.pin_fd(fd)
                                need(pin == before['code_files'][path], 'HELD_VERIFIER_INPUT_CHANGED')
                                target.append(fd); held_pins[fd] = (path, pin)
                        own = own_candidate(root, raw, stack, support)
                        expected, fd_rows, compiler_argv = verifier_plans(
                            session, before, flattened, own, boot_fds, context_fds, support)
                        result['verifier_input_fd_order'] = {'boot': list(zip(before['bootclasspath'], boot_fds)),
                                                           'context': list(zip(flattened, context_fds))}
                        actual, stderr, proof_ref = session.run('verifier-fd-proof')
                        need(actual == expected and not stderr, 'ACTUAL_INHERITED_UID_AND_DESCRIPTOR_PROOF')
                        result['inherited_FD_proof'] = {'receipt': proof_ref, 'descriptors': fd_rows,
                            'actual_android_uid': 2000, 'marker_direct_and_directory_equal': True}
                        result['compiler_attempts'] = 1; result['compiler_argv'] = compiler_argv
                        _, _, result['compiler_receipt'] = session.run('compiler')
                        need(os.pread(own['oat'], 4, 0) == b'\x7fELF'
                             and os.pread(own['vdex'], 4, 0) == b'vdex', 'ACTUAL_VERIFIER_OUTPUT_HEADERS')
                        compiled = {key: support.pin_fd(own[key]) for key in ('source', 'oat', 'vdex')}
                        result['compiled_outputs'] = compiled
                        result['oatdump_attempts'] += 1
                        class_output, class_stderr, class_ref = session.run('all-class-status')
                        need(not class_stderr, 'ALL_CLASS_STATUS_STDERR_MUST_BE_EMPTY')
                        method_outputs = {}; method_refs = {}
                        pairs = [('method-exif', 'Lcom/android/gallery3d/exif/ExifInterface;'),
                                 ('method-operation', 'Lcom/android/gallery3d/ui/MenuExecutor$MediaOperation;')]
                        for kind, descriptor in pairs:
                            result['oatdump_attempts'] += 1
                            stdout, stderr, ref = session.run(kind)
                            need(not stderr, 'METHOD_OATDUMP_STDERR_MUST_BE_EMPTY')
                            method_outputs[descriptor] = stdout; method_refs[descriptor] = ref
                        status, windows = parser.prove_parts(class_output, method_outputs, names, checksum=checksum)
                        result['class_status_proof'] = common.write_new(root / 'all-class-status-proof.json', status)
                        result['oatdump_receipts'] = {'all_classes': class_ref, 'methods': method_refs}
                        result['modified_method_windows'] = {descriptor: common.write_new(
                            root / ('modified-method-%d.txt' % index), window)
                            for index, (descriptor, window) in enumerate(windows.items())}
                        need({key: support.pin_fd(own[key]) for key in ('source', 'oat', 'vdex')} == compiled,
                             'OAT_VDEX_APK_CHANGED_BETWEEN_THREE_OBSERVATIONS')
                        for fd, (path, pin) in held_pins.items():
                            need(support.pin_fd(fd) == pin == before['code_files'][path],
                                 'HELD_BOOT_OR_CONTEXT_FD_CHANGED_AFTER_VERIFICATION')
                        result['all_2144_stored_statuses_verified'] = status['all_2144_stored_statuses_verified']
                        result['both_modified_methods_verified'] = status['both_modified_method_windows_verified']
                    result['verifier_input_and_output_FDs_closed'] = True
                    after = closure.snapshot(session, originals['context'], originals['identity'])
                    result['closure_after'] = common.write_new(root / 'code-closure-after.json', after)
                    need(after == before, 'CURRENT_FINAL_MAIN_CODE_OR_GALLERY_CLOSURE_CHANGED')
                    result['home_after'] = originals['identity'].home_snapshot(session, result['home_before']['roots'])
                    need(result['home_after']['roots'] == result['home_before']['roots'], 'HOME_TASK_BASELINE_CHANGED')
                    result['main_after'] = session.guard()
                    need(result['main_after'] == result['main_before'], 'FINAL_MAIN_CHANGED_DURING_GALLERY_ART')
                    result['commands'] = session.records
                    completed = [row for row in session.records if row.get('kind')]
                    need(len(completed) == 6 and all(row['complete'] for row in completed)
                         and {row['kind'] for row in completed} == {'flatten', 'verifier-fd-proof',
                            'compiler', 'all-class-status', 'method-exif', 'method-operation'},
                         'SIX_ACTUAL_COMPLETED_OWNED_COMMANDS_REQUIRED')
                    for row in completed:
                        command = common.parse(common.read_ref(row['receipt']))
                        need(command['complete'] is True and command['host_retirement_proved'] is True
                             and command['lifecycle']['child_started'] is True,
                             'ACTUAL_COMMAND_DISPATCH_AND_RETIREMENT_RECEIPT_REQUIRED')
                    result['actual_completed_command_counts'] = {'analyzer': 1, 'descriptor_proof': 1,
                                                                 'compiler': 1, 'oatdump': 3}
                finally:
                    session.close()
                    result['session_closed'] = session.closed
                need(candidate.verify() == result['held_candidate_before'], 'HOST_SIGNED_CANDIDATE_CHANGED')
            result['candidate_fd_closed'] = candidate.closed
            result['host_inputs_after'] = originals['install'].host_evidence()
            need(result['host_inputs_after'] == result['host_inputs_before'], 'SIGNED_BUILD_PROVENANCE_CHANGED')
        result['global_action_lock_exited'] = True
        result['resources_after'] = support.resources()
        need(result['resources_after']['limits'] == result['resources_before']['limits']
             and result['session_closed'] and result['candidate_fd_closed']
             and result['verifier_input_and_output_FDs_closed']
             and result['all_2144_stored_statuses_verified'] and result['both_modified_methods_verified'],
             'COMPLETE_FRESH_ART_QUALIFICATION_AND_NORMAL_EXIT_REQUIRED')
        result['state'] = 'CURRENT_QPR1_MAIN_ALL_2144_CLASSES_ART_VERIFIED_NOT_INSTALLED'
    except BaseException as error:
        result['error'] = type(error).__name__ + ':' + str(error)
        if session is not None:
            result['commands'] = session.records
            result['session_closed'] = session.closed
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous)
        result['finished_unix_ns'] = time.time_ns(); result['elapsed_seconds'] = time.monotonic() - start
    return result
