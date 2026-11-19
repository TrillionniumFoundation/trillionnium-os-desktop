#!/usr/bin/env python3
"""Qualify one new publisher SZZC source candidate using pinned SDK37 tools."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import sys
import time
import traceback
import types
import zipfile

ROOT = Path('/home/qq/work/p4-szzc-current-source-5cd1-20261119-r1')
OUT = ROOT / 'qualification'
HELPER = Path('/home/qq/work/p4-cp3a-provider-source-5cd1-20261119-r2/verify_providers.py')
HELPER_PIN = (31257, 'b75a440ab7707032a22c28a621d9df254e416b8170f9b1a9d96429ecf30e462d')
REGISTRY_PIN = (116810, '62df07622afa60960863dd9721cfd8b46a67b74076355c150534052f1f58abb1')
HISTORY_PIN = (283411, '3fd428793499f4811ff5a73c912c95ed23dfd2c82987f3a737a84624e79f5669')
HEAD_PIN = (1502, '73fc14312fe687859899e9a1f9fa2d2ed3d3a52d90dcdd29ee1642a7845c64fd')
FAILURE_PIN = (2031, '25c53c96e6cccbd90479d023e9d0e60e955fd0d7485c750bb32171fe5bdf2b07')
FREEZE_PIN = (1662, '01536a3d7139e58e176a739414a29500700df4cece2895df9c7a5277a0f030c2')
PREFIX_SHA = 'f6132a3989b706664209dda867c0c5d0816bc76b2fef3488abc144cd80a28c0d'
SECOND_PREFIX_SHA = '64300f2c18df066c0b9d667eba858c85fe30f759de62aea6d9776d4e914e7242'
RANGE_FAILURE_PIN = (4818, 'b8ee3b641bdfdce72a1e0cdab1f9f2af057af0a415e5a82397876676dc4c5ce8')
SECOND_FREEZE_PIN = (3108, 'ed046d71ca079dded74e0a074980ca17340c322a1dfcc6c7b9020bd56fc9527d')
EXPECTED_SIGNER = ['d85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44']
PACKAGE = 'com.szzc'
NEW_BYTES = 220498418
OLD_BYTES = 220522994
OLD_SHA = '7af438808904dbd4457f8d5ea7e267e5779e8ad6ab4d6a9c156c1e8ea0285d96'
W = None
R = {'schema': 'pocket4-szzc-current-publisher-source-qualification-v1',
     'success': False, 'source_identity_verified': False, 'source_candidate_only': True,
     'current_input_selected': False, 'existing_selected_APK_changed': False,
     'existing_registry_changed': False, 'historical_signer_reference_only': True,
     'installed': False, 'actual_UID': None, 'framework_epoch': None,
     'runtime_qualified': False, 'native_compatibility_qualified': False,
     'business_qualified': False, 'production_ready': False,
     'Android_calls': 0, 'new_downloads_in_this_stage': 0, 'user_data_reads': 0,
     'privileged_actions': 0, 'C_or_Rust_compilations': 0}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def f9(s):
    return [str(x) for x in (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
                            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)]


def bootstrap_helper():
    global W
    fd = os.open(HELPER, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    st = os.fstat(fd)
    try:
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 1000 or st.st_nlink != 1
                or f9(HELPER.lstat()) != f9(st)):
            raise ValueError('reviewed helper ordinary input identity')
        data = os.pread(fd, HELPER_PIN[0] + 1, 0)
        if (len(data), sha(data)) != HELPER_PIN:
            raise ValueError('reviewed helper full pin mismatch')
        if f9(os.fstat(fd)) != f9(st) or f9(HELPER.lstat()) != f9(st):
            raise ValueError('reviewed helper changed during bootstrap')
        W = types.ModuleType('p4_reviewed_source_primitives')
        W.__file__ = str(HELPER)
        exec(compile(data, str(HELPER), 'exec'), W.__dict__)
        # Reuse only reviewed file, budget, bounded-process, manifest identity,
        # and ELF-header primitives. The provider/GSI main is never invoked.
        W.ROOT = ROOT
        W.OUT = OUT
        W.LIMIT = 44 * 1024 * 1024
        W.DEADLINE = time.monotonic() + 180
        pin = {'path': str(HELPER), 'bytes': len(data), 'sha256': sha(data), 'identity': f9(st)}
        W.BOOKENDS.append((HELPER, fd, pin))
        R['reviewed_helper_source'] = pin
        return data
    except BaseException:
        os.close(fd)
        raise


def held_json(path, pin):
    fd, proof = W.held(path, pin, max(pin[0], 1024 * 1024))
    raw = os.pread(fd, proof['bytes'], 0)
    return json.loads(raw), proof, raw


def main():
    if os.getuid() != 1000 or os.sched_getaffinity(0) != {31}:
        raise ValueError('ordinary qq and actual CPU31 required')
    if ROOT.resolve() != ROOT or ROOT.lstat().st_uid != 1000:
        raise ValueError('canonical owned scope root required')
    if len(sys.argv) != 3 or not re.fullmatch('[0-9a-f]{64}', sys.argv[1]):
        raise ValueError('exact actual transport SHA and bytes arguments required')
    receipt_size = int(sys.argv[2])
    if not 1 <= receipt_size <= 65536:
        raise ValueError('transport receipt size bound')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (180, 180))
    os.umask(0o077)
    helper_bytes = bootstrap_helper()
    R['SDK_commands'] = W.COMMANDS
    W.verify_process_observation_preconditions()
    OUT.mkdir(mode=0o700, exist_ok=False)
    for name in ('source', 'evidence', 'logs', 'receipts', 'tmp', 'home'):
        (OUT / name).mkdir(mode=0o700)
    R['started_utc'] = now()
    cgroups = [x.split(':', 2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::')]
    W.need(len(cgroups) == 1, 'one unified cgroup')
    cgp = Path('/sys/fs/cgroup') / cgroups[0].lstrip('/')
    limits = {x: (cgp / x).read_text().strip() for x in
              ('memory.max', 'memory.high', 'memory.swap.max', 'cpu.max', 'pids.max')}
    W.need(limits == {'memory.max': '268435456', 'memory.high': '234881024',
                      'memory.swap.max': '0', 'cpu.max': '100000 100000', 'pids.max': '32'},
           'actual source verifier resource limits differ')
    before_events = (cgp / 'memory.events').read_text()
    R['resource_limits'] = {'observed': limits, 'affinity': [31], 'cgroup': str(cgp),
                            'SDK_output_max_allocated_bytes': W.LIMIT, 'deadline_seconds': 180}
    R['memory_events_before'] = before_events
    self_fd, R['worker_source'] = W.held(Path(__file__), limit=65536)
    W.save(OUT / 'source/qualify_current_szzc.py', os.pread(self_fd, R['worker_source']['bytes'], 0))
    W.save(OUT / 'source/reviewed_provider_source_primitives.py', helper_bytes)
    transport, tp, traw = held_json(ROOT / 'download/RESUME2-TRANSPORT-RESULT.json', (receipt_size, sys.argv[1]))
    W.need(transport['complete'] is True and transport['source_identity_verified'] is False
           and transport['signature_verified'] is False,
           'complete resumed transport required without borrowed SDK credit')
    artifact = transport['artifact']
    apk_path = ROOT / 'download/com.szzc.publisher-current.apk'
    W.need(artifact['path'] == str(apk_path) and artifact['bytes'] == NEW_BYTES
           and re.fullmatch('[0-9a-f]{64}', artifact['sha256']), 'exact new candidate custody')
    W.need(transport['http']['status'] == 206 and transport['http']['content_length'] == '52137116'
           and transport['http']['content_range'] == 'bytes 168361302-220498417/220498418'
           and transport['http']['request_range'] == 'bytes=168361302-220498417'
           and transport['http']['conditional_if_match'] == '"108948280DD69A433DD2AEFD4585FD2B"'
           and transport['http']['etag'] == '"108948280DD69A433DD2AEFD4585FD2B"'
           and transport['http']['last_modified'] == 'Wed, 18 Nov 2026 13:23:40 GMT'
           and transport['http']['url'] == 'https://edfs.zuchecdn.com/android-package/SZZC.apk'
           and transport['http']['content_encoding'] == 'identity'
           and transport['http']['content_type'] == 'application/vnd.android.package-archive'
           and transport['all_five_input_bookends_unchanged'] is True
           and transport['full_SHA_readback_verified'] is True
           and transport['prefix_SHA_readback_unchanged'] is True
           and transport['same_inode_append_only'] is True
           and transport['prefix_bytes_redownloaded'] == 0
           and transport['tail_bytes_downloaded'] == 52137116
           and transport['prefix_before']['sha256'] == SECOND_PREFIX_SHA
           and transport['prefix_after']['sha256'] == SECOND_PREFIX_SHA,
           'original publisher HEAD/frozen prefix/exact conditional Range binding')
    failed, fp, fraw = held_json(ROOT / 'download/TRANSPORT-RESULT.json', FAILURE_PIN)
    freeze, pp, praw = held_json(ROOT / 'inputs/PARTIAL-PREFIX-FREEZE.json', FREEZE_PIN)
    W.need(failed['complete'] is False and failed['total_bytes_received_before_terminal'] == 58720256
           and freeze['prefix']['bytes'] == 58720256 and freeze['prefix']['sha256'] == PREFIX_SHA
           and freeze['original_failed_transport']['sha256'] == FAILURE_PIN[1]
           and freeze['original_unit']['retired'] is True,
           'original failed transport and retired prefix freeze remain immutable')
    failed_range, frp, frraw = held_json(ROOT / 'download/RESUME-TRANSPORT-RESULT.json', RANGE_FAILURE_PIN)
    second_freeze, sfp, sfraw = held_json(ROOT / 'inputs/SECOND-PREFIX-FREEZE.json', SECOND_FREEZE_PIN)
    W.need(failed_range['complete'] is False and failed_range['actual_inode_size_at_terminal'] == 168361302
           and failed_range['all_three_input_bookends_unchanged'] is True
           and second_freeze['prefix']['bytes'] == 168361302
           and second_freeze['prefix']['sha256'] == SECOND_PREFIX_SHA
           and second_freeze['failed_first_resume']['sha256'] == RANGE_FAILURE_PIN[1]
           and second_freeze['first_prefix_freeze']['sha256'] == FREEZE_PIN[1]
           and second_freeze['both_original_units_retired'] is True
           and second_freeze['original_58720256_prefix'] == {'bytes': 58720256,
               'sha256': PREFIX_SHA, 'full_readback_unchanged': True},
           'second actual retired prefix and both immutable prior failures')
    expected_chain = {'HEAD': HEAD_PIN, 'original_failed_transport': FAILURE_PIN,
                      'first_prefix_freeze': FREEZE_PIN, 'failed_first_resume': RANGE_FAILURE_PIN,
                      'second_prefix_freeze': SECOND_FREEZE_PIN}
    W.need(len(transport['source_inputs']) == 5 and len(transport['input_bookends']) == 5,
           'all five resumed source links present')
    for row in transport['source_inputs']:
        W.need(row['label'] in expected_chain and (row['bytes'], row['sha256']) == expected_chain[row['label']],
               'resumed source link full pin')
    W.need({x['label'] for x in transport['source_inputs']} == set(expected_chain), 'unique resumed source links')
    W.need(all(x['unchanged'] is True for x in transport['input_bookends']), 'all resumed source bookends passed')
    R.update(original_failed_transport=fp, retired_prefix_freeze=pp,
             first_failed_range=frp, retired_second_prefix_freeze=sfp)
    head, hp, hraw = held_json(ROOT / 'inputs/PUBLISHER-REDIRECT-HEAD.json', HEAD_PIN)
    W.need(head['content_length'] == str(NEW_BYTES) and head['selected_APK_bytes'] == OLD_BYTES,
           'original observed source drift')
    registry, rp, rraw = held_json(ROOT / 'inputs/CURRENT-SOURCE-INPUTS.json', REGISTRY_PIN)
    current = [x for x in registry['applications'] if x['package'] == PACKAGE]
    W.need(len(current) == 1, 'one current selected source row')
    old = current[0]
    W.need(old['version_name'] == '9.6.3' and old['version_code'] == 329
           and old['input']['bytes'] == OLD_BYTES and old['input']['sha256'] == OLD_SHA,
           'actual current329 source metadata pin')
    history, histp, histraw = held_json(ROOT / 'inputs/CANDIDATE42.json', HISTORY_PIN)
    history_rows = [x for x in history['selected_candidates'] if x['package'] == PACKAGE]
    W.need(len(history_rows) == 1, 'one historical signer reference')
    proposed = history_rows[0]['proposed_official_input']
    W.need(proposed['signer_certificate_sha256'] == EXPECTED_SIGNER
           and proposed['signature_verified_in_retained_source'] is True
           and proposed['version_code'] == 328 and proposed['version_name'] == '9.6.2',
           'historical signer continuity reference only')
    R.update(transport=tp, original_HEAD=hp, previous_current_registry=rp,
             historical_signer_reference=histp,
             prior_selected={'package': PACKAGE, 'version_name': '9.6.3', 'version_code': 329,
                             'APK_bytes': OLD_BYTES, 'APK_sha256': OLD_SHA,
                             'old_APK_body_read': False},
             signer_reference_scope='SHA-pinned public canonical history 6fd7efdc; signer continuity only, no old runtime credit')
    for name, data in [('transport.json', traw), ('original-failed-transport.json', fraw),
                       ('retired-prefix-freeze.json', praw), ('first-failed-range.json', frraw),
                       ('retired-second-prefix-freeze.json', sfraw), ('original-HEAD.json', hraw),
                       ('current-source-registry.json', rraw), ('historical-candidate42.json', histraw)]:
        W.save(OUT / 'evidence' / name, data)
    parser_pins = {}
    for name, expected in W.SOURCE_PINS.items():
        fd, pin = W.held(W.ORIGINAL / name, expected, 65536)
        W.save(OUT / 'source' / name, os.pread(fd, expected[0], 0))
        parser_pins[name] = pin
    sys.path.insert(0, str(OUT / 'source'))
    import verify_apk as single
    from verify_apk_set import safe_members, manifest_observation
    from axml_metadata import signing_block_certificates, verified_scheme_certificates
    W.single = single
    R['original_parser_source_pins'] = parser_pins
    sdk, sdkp, sdkraw = held_json(W.APP / 'metadata/sdk37-preparation-receipt.json',
                                 (7636, 'c9b2003dfeec0d0dc72263ff63723f9b4fe5f77ca4ad0b6ac77224ca80a78bb5'))
    W.need(sdk['ready'] and sdk['archive']['official_sha1_matched'], 'original SDK37 preparation')
    W.save(OUT / 'evidence/sdk37-preparation-receipt.json', sdkraw)
    R['SDK_preparation'] = sdkp
    R['SDK_full_tool_bookends'] = []
    for pin in sdk['extracted'] + [sdk['java'], sdk['jdk_release']]:
        R['SDK_full_tool_bookends'].append(W.held(pin['path'], (pin['bytes'], pin['sha256']), 8 * 1024 * 1024)[1])
    R['tool_pins'] = {name: W.held(W.TOOLS[name][0], (W.TOOLS[name][1], W.TOOLS[name][2]),
                                 8 * 1024 * 1024)[1] for name in ('aapt2', 'apksigner', 'java')}
    apk_fd, apk_pin = W.held(apk_path, (NEW_BYTES, artifact['sha256']), 256 * 1024 * 1024)
    W.need(apk_pin['identity'] == artifact['identity'], 'transport/qualification candidate F9 changed')
    R['candidate_full_disk_SHA_readback_verified'] = True
    members = []
    native = []
    manifest_bytes = None
    with os.fdopen(os.dup(apk_fd), 'rb') as stream, zipfile.ZipFile(stream) as archive:
        entries = safe_members(archive, count_limit=100000, expansion_limit=512 * 1024 * 1024)
        W.need('AndroidManifest.xml' in entries, 'manifest member required')
        for item in archive.infolist():
            W.budget()
            digest = hashlib.sha256()
            size = 0
            header = b''
            parts = [] if item.filename == 'AndroidManifest.xml' else None
            with archive.open(item) as source:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
                    size += len(block)
                    if len(header) < 64:
                        header = (header + block)[:64]
                    if parts is not None:
                        W.need(size <= 1024 * 1024, 'bounded manifest')
                        parts.append(block)
            W.need(size == item.file_size, 'complete member EOF')
            rec = {'name': item.filename, 'bytes': size, 'sha256': digest.hexdigest(),
                   'crc32': f'{item.CRC:08x}', 'compressed_bytes': item.compress_size,
                   'compression': item.compress_type, 'directory': item.is_dir(),
                   'complete_eof_crc_verified': True}
            members.append(rec)
            if parts is not None:
                manifest_bytes = b''.join(parts)
            if not item.is_dir() and item.filename.startswith('lib/'):
                native.append({**rec, **W.native_header(item.filename, header), 'execution_qualified': False})
    raw = manifest_observation(manifest_bytes)
    arg = f'/proc/self/fd/{apk_fd}'
    block = signing_block_certificates(arg)
    badging, be, bc = W.run('szzc-badging', [W.TOOLS['aapt2'][0], 'dump', 'badging', arg], (apk_fd,), 40)
    manifest, me, mc = W.run('szzc-manifest', [W.TOOLS['aapt2'][0], 'dump', 'xmltree', arg,
                                             '--file', 'AndroidManifest.xml'], (apk_fd,), 40)
    java = [W.TOOLS['java'][0], '-XX:ActiveProcessorCount=1', '-Xms16m', '-Xmx64m', '-XX:+UseSerialGC',
            '-XX:CompressedClassSpaceSize=16m', '-XX:ReservedCodeCacheSize=16m',
            '-XX:MaxMetaspaceSize=48m', '-Xss256k', '-Duser.home=' + str(OUT / 'home'),
            '-Djava.io.tmpdir=' + str(OUT / 'tmp'), '-jar', W.TOOLS['apksigner'][0],
            'verify', '--min-sdk-version', '37', '--max-sdk-version', '37',
            '--verbose', '--print-certs', arg]
    signature, se, sc = W.run('szzc-signature', java, (apk_fd,), 100)
    selected = verified_scheme_certificates(signature + se, block)
    attrs, certs = W.verify_identity(PACKAGE, raw, badging, manifest, signature + se, block, selected)
    W.need(certs == EXPECTED_SIGNER, 'new publisher candidate signer differs from historical reference')
    min_sdk = raw.get('min_sdk_version')
    W.need(min_sdk is None or (str(min_sdk).isdigit() and int(min_sdk) <= 37), 'minimum SDK exceeds current API37')
    W.need(attrs.get('versionName') is not None and attrs['versionName'] == raw['version_name'],
           'SDK/AXML version name required and identical')
    new_code = raw['version_code'] + (raw['version_code_major'] << 32)
    if new_code > 329:
        comparison = 'NEWER_VERSION_CODE_THAN_SELECTED329'
    elif new_code < 329:
        comparison = 'LOWER_VERSION_CODE_THAN_SELECTED329_DO_NOT_DOWNGRADE'
    elif attrs['versionName'] == '9.6.3':
        comparison = 'SAME_VERSION329_DIFFERENT_PUBLISHER_ARTIFACT'
    else:
        comparison = 'SAME_VERSION329_DIFFERENT_VERSION_NAME_REVIEW_REQUIRED'
    receipt = {'schema': 'pocket4-szzc-publisher-APK-source-receipt-v1', 'observed_utc': now(),
               'package': PACKAGE, 'version_name': attrs['versionName'], 'version_name_axml': raw['version_name'],
               'version_code': raw['version_code'], 'version_code_major': raw['version_code_major'],
               'long_version_code': new_code, 'version_comparison_to_actual_current329': comparison,
               'APK': apk_pin, 'original_transport': tp, 'original_HEAD': hp,
               'original_failed_transport': fp, 'retired_prefix_freeze': pp,
               'first_failed_range': frp, 'retired_second_prefix_freeze': sfp,
               'previous_current_registry': rp, 'historical_signer_reference': histp,
               'historical_signer_reference_is_not_current_version_pin': True,
               'signer_certificate_sha256': certs, 'selected_signing_scheme': selected,
               'signature_verified_for_API': 37, 'public_signing_block': block,
               'manifest': raw, 'native_ABIs': sorted({n['abi'] for n in native}),
               'native_members': native, 'complete_zip_members': members,
               'all_ZIP_members_CRC_and_SHA_verified': True, 'commands': [bc, mc, sc],
               'SDK_preparation': sdkp, 'tool_pins': R['tool_pins'],
               'original_parser_source_pins': parser_pins, 'source_identity_verified': True,
               'source_qualification_is_conditional_on_successful_terminal_RESULT_and_all_bookends': True,
               'required_terminal_RESULT_path': str(OUT / 'RESULT.json'),
               'existing_current_package_retained': True, 'current_input_selected': False,
               'actual_UID': None, 'installed': False, 'native_compatibility_qualified': False,
               'runtime_qualified': False, 'business_qualified': False, 'production_ready': False}
    proof = W.save(OUT / 'receipts/com.szzc.json', receipt)
    R.update(candidate=apk_pin, package=PACKAGE, version_name=attrs['versionName'],
             version_code=raw['version_code'], long_version_code=new_code,
             version_comparison_to_actual_current329=comparison,
             signer_certificate_sha256=certs, source_receipt=proof,
             native_ABIs=receipt['native_ABIs'], native_member_count=len(native),
             complete_ZIP_member_count=len(members), selected_signing_scheme=selected,
             SDK_commands=W.COMMANDS, source_bytes_differ_from_selected=(apk_pin['sha256'] != OLD_SHA))
    R['bookends'] = []
    for path, fd, pin in W.BOOKENDS:
        W.need(W.f9(os.fstat(fd)) == pin['identity'] and W.f9(path.lstat()) == pin['identity'],
               'source path/FD identity changed: ' + str(path))
        W.need(W.fdsha(fd) == pin['sha256'], 'source full SHA changed: ' + str(path))
        R['bookends'].append({'path': str(path), 'bytes': pin['bytes'], 'sha256': pin['sha256'],
                              'F9_and_full_SHA_equal': True})
    W.need(len(W.COMMANDS) == 3 and all(c.get('exit') == 0 and c['actual_child_reaped']
               and c.get('after_reap_echild') and c['original_pidfd_held_until_reaped'] for c in W.COMMANDS),
           'exact three original SDK children retired')
    remaining = Path('/proc/self/task/' + str(os.getpid()) + '/children').read_text().strip()
    W.need(remaining == '', 'remaining child process')
    R['remaining_children'] = remaining
    after_events = (cgp / 'memory.events').read_text()
    R['memory_events_after'] = after_events
    before = dict(x.split() for x in before_events.splitlines())
    after = dict(x.split() for x in after_events.splitlines())
    W.need(all(int(before[x]) == int(after[x]) for x in ('oom', 'oom_kill', 'oom_group_kill')), 'OOM counters changed')
    R['output_allocated_bytes_before_RESULT'] = W.budget()
    R['source_identity_verified'] = True
    R['success'] = True


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        R.update(success=False, source_identity_verified=False, error=repr(exc), traceback=traceback.format_exc())
    finally:
        R['completed_utc'] = now()
        if W is not None and OUT.exists():
            try:
                pin = W.save(OUT / 'RESULT.json', R)
                print(json.dumps({'success': R['success'], 'package': PACKAGE,
                                  'version_name': R.get('version_name'), 'version_code': R.get('version_code'),
                                  'version_comparison': R.get('version_comparison_to_actual_current329'),
                                  'result': pin, 'error': R.get('error'), 'production_ready': False}, sort_keys=True), flush=True)
            except BaseException:
                R.update(success=False, source_identity_verified=False, terminal_RESULT_or_stdout_failed=True)
                traceback.print_exc()
        else:
            R.update(success=False, source_identity_verified=False, terminal_RESULT_missing=True)
        if W is not None:
            for path, fd, pin in W.BOOKENDS:
                try:
                    os.close(fd)
                except OSError:
                    pass
    raise SystemExit(0 if R['success'] else 1)
