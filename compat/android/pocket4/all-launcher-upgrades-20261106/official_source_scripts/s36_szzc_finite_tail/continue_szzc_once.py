#!/usr/bin/env python3
"""One bounded continuation of an actually settled normal HTTPS download."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import stat
import sys
import time
import urllib.error
import urllib.request
URL = 'https://s.shouji.qihucdn.com/261102/4f0fd9484ffbe93318ce97df4d87ea90/com.szzc_327.apk?en=curpage%3Dopenbox_wap_detail%26exp%3D1794572091%26from%3Dopenbox_mintf_getAppInfoByIds%26m2%3D%26ts%3D1793967291%26tok%3Dfe3786e673aeec024bad9eff8a609b6a%26v%3D%26f%3Dz.apk'
NAME = 'com.szzc_327.apk'
EXPECTED_BYTES = 220579134
BOUND_INSTALLED_SHA256 = '997067da78cb0d8d0fde2adb58e26c90815de1daec4c1ee02beae39ce2ceda24'
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_nlink', 'st_mtime_ns', 'st_ctime_ns')
ROOT = Path('/home/alex/work/pocket4-szzc-finite-tail-20261106-s36')
PREFIX = {'path': '/home/alex/work/pocket4-szzc-published-candidate-20261106-s35/com.szzc_327.apk.partial', 'bytes': 187695104, 'sha256': '10e55e4bf2c8cb94efeb51be603aa18c7f458c65ae1c1a4208f8d7f7d5dccf2a', 'version': '66306:38800785:187695104:1793991746138897795:1793991746138897795', 'mode': 256}
PRIOR_RESULT = {'path': '/home/alex/work/pocket4-szzc-published-candidate-20261106-s35/download-result.json', 'bytes': 1948, 'sha256': 'd445c933451f033658e14fbdaff005aecb0f69eb2faf24f9a3f04931f66cf0a2', 'version': '66306:38802536:1948:1793991746141216599:1793991746141216599', 'mode': 384}
PRIOR_TERMINAL_RAW = '{\n  "at_unix_ms": 1793991746161,\n  "audit_recorded": true,\n  "automatic_retry": false,\n  "cancelled": false,\n  "exit_code": 1,\n  "job_id": "1a1b2395cf0-fc05-7d06",\n  "launch_nonce": "7b956834a20b0a728c421b37da8e7dbb",\n  "log_bytes": {\n    "stderr": {\n      "seen": 0,\n      "stored": 0\n    },\n    "stdout": {\n      "seen": 1948,\n      "stored": 1948\n    }\n  },\n  "log_errors": {\n    "stderr": null,\n    "stdout": null\n  },\n  "log_synced": {\n    "stderr": true,\n    "stdout": true\n  },\n  "log_truncated": {\n    "stderr": false,\n    "stdout": false\n  },\n  "output_complete": true,\n  "output_durable": true,\n  "state": "failed",\n  "terminal_publication_confirmed": true,\n  "terminal_publication_protocol": 1,\n  "timed_out": false\n}'
PRIOR_TERMINAL_SHA256 = '1a568ab10355ca1b982b121b4413be80a6c92a721b4d82dc7983bb1568a90e46'
LAST_MODIFIED = 'Mon, 02 Nov 2026 02:41:02 GMT'

def need(value, code):
    if not value:
        raise RuntimeError(code)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fp.close()
        raise RuntimeError('REDIRECT_REFUSED_NO_FOLLOW')

def census():
    rows = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name)
            s = os.fstat(fd)
            rows[name] = [os.readlink('/proc/self/fd/' + name), s.st_dev, s.st_ino,
                          s.st_mode, s.st_uid, s.st_gid, s.st_rdev,
                          fcntl.fcntl(fd, fcntl.F_GETFD), fcntl.fcntl(fd, fcntl.F_GETFL)]
        except FileNotFoundError:
            continue
        except OSError as error:
            if error.errno != 9:
                raise
    return rows

def write_all(fd, body):
    done = 0
    while done < len(body):
        n = os.write(fd, body[done:])
        need(n > 0, 'FILE_WRITE_PROGRESS')
        done += n

def verify_file(root_fd, name, expected_hash, deadline):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_uid == 1000 and
             stat.S_IMODE(first.st_mode) == 0o400 and first.st_nlink == 1 and
             first.st_size == EXPECTED_BYTES, 'EXACT_NEW_CANDIDATE_METADATA')
        count, digest = 0, hashlib.sha256()
        while True:
            need(time.monotonic() < deadline, 'COMPLETE_READBACK_DEADLINE')
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            count += len(block)
            digest.update(block)
        last = os.fstat(fd)
        named = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        need(count == EXPECTED_BYTES and digest.hexdigest() == expected_hash and
             all(getattr(first, k) == getattr(last, k) == getattr(named, k) for k in FIELDS),
             'COMPLETE_CANDIDATE_READBACK_CHANGED')
        return {k: str(getattr(first, k)) for k in FIELDS}
    finally:
        os.close(fd)

def identity(s):
    return tuple(str(getattr(s, k)) for k in FIELDS)


def hold_original(pin, owned, bindings):
    path = Path(pin['path'])
    need(path.is_absolute() and '..' not in path.parts, 'FIXED_ORIGINAL_PATH')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    owned.append(parent)
    current = Path('/')
    dirs = [(parent, current)]
    for part in path.parts[1:-1]:
        parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        owned.append(parent)
        current = current / part
        dirs.append((parent, current))
    fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    owned.append(fd)
    first = os.fstat(fd)
    need(stat.S_ISREG(first.st_mode) and first.st_uid == first.st_gid == 1000 and first.st_nlink == 1 and
         stat.S_IMODE(first.st_mode) == pin['mode'] and first.st_size == pin['bytes'], 'EXACT_ORIGINAL_METADATA')
    version = ':'.join(str(getattr(first, k)) for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
    need(version == pin['version'], 'ACTUAL_FILE_INFO_VERSION_CHANGED')
    bindings.append((fd, parent, path.name, identity(first), dirs, pin))
    return fd


def check_originals(bindings, deadline):
    for fd, parent, name, first, dirs, pin in bindings:
        need(identity(os.fstat(fd)) == first and identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == first,
             'ORIGINAL_FILE_OR_ENTRY_CHANGED')
        for directory_fd, path in dirs:
            a, b = os.fstat(directory_fd), os.stat(path, follow_symlinks=False)
            need(all(getattr(a, k) == getattr(b, k) for k in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid')),
                 'ORIGINAL_PARENT_PATH_REPLACED')
        offset, digest = 0, hashlib.sha256()
        while offset < pin['bytes']:
            need(time.monotonic() < deadline, 'ORIGINAL_RECHECK_DEADLINE')
            block = os.pread(fd, min(1024 * 1024, pin['bytes'] - offset), offset)
            need(bool(block), 'ORIGINAL_RECHECK_PROGRESS')
            offset += len(block)
            digest.update(block)
        need(digest.hexdigest() == pin['sha256'] and identity(os.fstat(fd)) == first, 'ORIGINAL_FULL_HASH_CHANGED')


def prior_gate(raw):
    need(len(raw) == PRIOR_RESULT['bytes'] and hashlib.sha256(raw).hexdigest() == PRIOR_RESULT['sha256'], 'PRIOR_RECEIPT_PIN')
    d = json.loads(raw)
    t = json.loads(PRIOR_TERMINAL_RAW)
    need(hashlib.sha256(PRIOR_TERMINAL_RAW.encode()).hexdigest() == PRIOR_TERMINAL_SHA256 and
         t['job_id'] == '1a1b2395cf0-fc05-7d06' and t['state'] == 'failed' and t['exit_code'] == 1 and
         all(t[k] is True for k in ('output_complete', 'output_durable', 'terminal_publication_confirmed')) and
         all(t[k] is False for k in ('automatic_retry', 'timed_out', 'cancelled')) and
         t['log_bytes'] == {'stdout': {'seen': len(raw), 'stored': len(raw)}, 'stderr': {'seen': 0, 'stored': 0}} and
         t['log_errors'] == {'stdout': None, 'stderr': None} and t['log_truncated'] == {'stdout': False, 'stderr': False},
         'PRIOR_DURABLE_SETTLED_FAILURE_REQUIRED')
    need(d['schema'] == 'pocket4-szzc-published-candidate-download-v1' and d['ok'] is False and
         d['state'] == 'DOWNLOAD_FAILED_NO_RETRY' and d['error'] == 'BOUNDED_DOWNLOAD_DEADLINE' and
         d['original_descriptor_identities_restored'] is True and d['automatic_retries'] == 0 and
         d['network_requests_attempted'] == 1 and d['subprocesses_started'] == 0 and
         d['url'] == URL and d['expected_bytes'] == EXPECTED_BYTES and
         d['completed_stream_chunk_bytes'] == PREFIX['bytes'] == d['partial_size_snapshot'] and
         d['completed_stream_chunk_sha256'] == PREFIX['sha256'] and d['partial_preserved'] is True,
         'EXACT_PRIOR_PARTIAL_AND_FAILURE_SCOPE')
    h = d['http']
    need(h['status'] == 200 and h['url'] == URL and h['content_length'] == EXPECTED_BYTES and
         h['redirect_followed'] is False and h['TLS_certificate_verification'] == 'default required HTTPS' and
         h['ETag'] is None and h['Last-Modified'] == LAST_MODIFIED, 'EXACT_PRIOR_HTTPS_ENTITY_OBSERVATION')


def main():
    need(os.getuid() == os.geteuid() == 1000 and sys.argv[1:] == ['--continue-one-range'], 'EXACT_UNPRIVILEGED_OPERATION')
    need(ROOT.parent.resolve() == ROOT.parent and shutil.disk_usage(ROOT.parent).free >= 4 * 1024**3, 'STAGING_PARENT_AND_SPACE')
    need(PREFIX['bytes'] == 187695104 and EXPECTED_BYTES - PREFIX['bytes'] == 32884030, 'EXACT_FINITE_REMAINDER')
    os.umask(0o077)
    before = census()
    owned, bindings = [], []
    result = {'schema': 'pocket4-szzc-one-finite-tail-v1', 'ok': False, 'url': URL,
        'previous_job': '1a1b2395cf0-fc05-7d06', 'previous_failure_preserved': True,
        'prefix': PREFIX, 'range_start': PREFIX['bytes'], 'range_end': EXPECTED_BYTES - 1,
        'range_bytes': EXPECTED_BYTES - PREFIX['bytes'], 'network_requests_attempted': 0, 'automatic_retries': 0,
        'Android_commands': 0, 'Main_actions': 0, 'App_installs': 0, 'permission_changes': 0,
        'subprocesses_started': 0, 'old_files_modified_or_deleted': False,
        'signature_or_manifest_verified': False, 'newer_version_claimed': False, 'production_ready': False}
    started = time.monotonic()
    deadline = started + 210
    created, root_fd, out_fd = False, None, None
    written, network_bytes = 0, 0
    digest, md5 = hashlib.sha256(), hashlib.md5()
    try:
        prefix_fd = hold_original(PREFIX, owned, bindings)
        receipt_fd = hold_original(PRIOR_RESULT, owned, bindings)
        prior_gate(os.pread(receipt_fd, PRIOR_RESULT['bytes'], 0))
        check_originals(bindings, deadline)
        ROOT.mkdir(mode=0o700)
        created = True
        root_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        need(os.fstat(root_fd).st_uid == 1000 and stat.S_IMODE(os.fstat(root_fd).st_mode) == 0o700, 'NEW_PRIVATE_ROOT')
        out_fd = os.open(NAME + '.partial', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=root_fd)
        while written < PREFIX['bytes']:
            need(time.monotonic() < deadline, 'PREFIX_COPY_DEADLINE')
            block = os.pread(prefix_fd, min(1024 * 1024, PREFIX['bytes'] - written), written)
            need(bool(block), 'PREFIX_COPY_PROGRESS')
            write_all(out_fd, block)
            digest.update(block); md5.update(block); written += len(block)
        need(digest.hexdigest() == PREFIX['sha256'], 'EXACT_COPIED_PREFIX_HASH')
        os.fsync(out_fd)
        context = ssl.create_default_context()
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity',
                   'Range': 'bytes=%d-%d' % (PREFIX['bytes'], EXPECTED_BYTES - 1), 'If-Range': LAST_MODIFIED}
        request = urllib.request.Request(URL, headers=headers)
        result['network_requests_attempted'] = 1
        with opener.open(request, timeout=30) as response:
            need(response.status == 206 and response.geturl() == URL, 'EXACT_NORMAL_HTTPS_RANGE_RESPONSE')
            need(response.headers.get('Retry-After') is None, 'SERVER_RETRY_AFTER_RESPECTED')
            need(response.headers.get_all('Content-Range') == ['bytes %d-%d/%d' % (PREFIX['bytes'], EXPECTED_BYTES-1, EXPECTED_BYTES)] and
                 response.headers.get_all('Content-Length') == [str(result['range_bytes'])], 'EXACT_RANGE_LENGTH_AND_ENTITY_TOTAL')
            need(response.headers.get('Content-Encoding', 'identity').lower() == 'identity' and
                 response.headers.get('Last-Modified') == LAST_MODIFIED and response.headers.get('ETag') is None,
                 'SAME_OBSERVED_ENTITY_HEADERS_NO_TRANSFORM')
            result['http'] = {'status': 206, 'url': URL, 'content_range': response.headers['Content-Range'],
                              'content_length': result['range_bytes'], 'Last-Modified': LAST_MODIFIED, 'ETag': None,
                              'TLS_certificate_verification': 'default required HTTPS', 'redirect_followed': False}
            while True:
                need(time.monotonic() < deadline, 'FINITE_TAIL_DEADLINE')
                block = response.read(min(65536, result['range_bytes'] + 1 - network_bytes))
                if not block:
                    break
                need(network_bytes + len(block) <= result['range_bytes'], 'FINITE_RANGE_SIZE_BOUND')
                write_all(out_fd, block)
                digest.update(block); md5.update(block); network_bytes += len(block); written += len(block)
        need(network_bytes == result['range_bytes'] and written == EXPECTED_BYTES and os.fstat(out_fd).st_size == written,
             'COMPLETE_RANGE_AND_FULL_ASSEMBLED_BODY_REQUIRED')
        os.fsync(out_fd); os.close(out_fd); out_fd = None
        partial_identity = verify_file(root_fd, NAME + '.partial', digest.hexdigest(), deadline)
        check_originals(bindings, deadline)
        os.link(NAME + '.partial', NAME, src_dir_fd=root_fd, dst_dir_fd=root_fd, follow_symlinks=False)
        os.unlink(NAME + '.partial', dir_fd=root_fd); os.fsync(root_fd)
        final = verify_file(root_fd, NAME, digest.hexdigest(), deadline)
        need(partial_identity['st_dev'] == final['st_dev'] and partial_identity['st_ino'] == final['st_ino'], 'OWN_NEW_FILE_PUBLICATION')
        result.update(ok=True, state='COMPLETE_PUBLISHED_CANDIDATE_PENDING_APP_VALIDATION', path=str(ROOT/NAME),
            bytes=written, sha256=digest.hexdigest(), md5=md5.hexdigest(), final_identity=final,
            original_files_full_hash_and_identity_unchanged=True, complete_body_rehashed=True,
            matches_bound_installed_full_APK_bytes=digest.hexdigest() == BOUND_INSTALLED_SHA256)
    except BaseException as error:
        result.update(state='FINITE_CONTINUATION_FAILED_NO_RETRY', error_type=type(error).__name__, error=str(error)[:1024],
                      complete_stream_chunk_bytes=written, network_complete_chunk_bytes=network_bytes,
                      partial_full_hash_verified=False, partial_preserved=created and (ROOT/(NAME+'.partial')).exists())
        if isinstance(error, urllib.error.HTTPError):
            result['http_failure'] = {'status': error.code, 'refusal_respected': error.code in (403,429),
                                      'retry_after': error.headers.get('Retry-After')}
            error.close()
    finally:
        if out_fd is not None:
            os.close(out_fd)
        if root_fd is not None:
            os.close(root_fd)
        for fd in reversed(owned):
            os.close(fd)
    result['elapsed_seconds'] = time.monotonic() - started
    result['original_descriptor_identities_restored'] = census() == before
    result['ok'] = result['ok'] and result['original_descriptor_identities_restored']
    raw = (json.dumps(result, sort_keys=True) + '\n').encode()
    if created:
        with (ROOT/'download-result.json').open('xb') as output:
            output.write(raw); output.flush(); os.fsync(output.fileno())
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
