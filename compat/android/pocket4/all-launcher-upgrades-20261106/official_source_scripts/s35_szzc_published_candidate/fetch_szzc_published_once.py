#!/usr/bin/env python3
"""Fetch one published store candidate without installing or executing an APK."""
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
ROOT = Path('/home/alex/work/pocket4-szzc-published-candidate-20261106-s35')
NAME = 'com.szzc_327.apk'
EXPECTED_BYTES = 220579134
BOUND_INSTALLED_SHA256 = '997067da78cb0d8d0fde2adb58e26c90815de1daec4c1ee02beae39ce2ceda24'
TOTAL_SECONDS = 270
FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_nlink', 'st_mtime_ns', 'st_ctime_ns')


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


def main():
    need(os.getuid() == os.geteuid() == 1000, 'EXACT_OPERATOR_UID1000')
    need(sys.argv[1:] == ['--fetch-once'], 'EXACT_FETCH_OPERATION')
    need(ROOT.parent.resolve() == ROOT.parent, 'FIXED_HOST_WORK_PARENT')
    need(shutil.disk_usage(ROOT.parent).free >= 4 * 1024**3, 'HOST_STAGING_SPACE_REQUIRED')
    os.umask(0o077)
    before = census()
    ROOT.mkdir(mode=0o700)
    root_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    result = {
        'schema': 'pocket4-szzc-published-candidate-download-v1', 'ok': False,
        'url': URL, 'package_hint_not_manifest_proof': 'com.szzc',
        'version_code_hint_not_manifest_proof': 327, 'expected_bytes': EXPECTED_BYTES,
        'bound_installed_reference_sha256': BOUND_INSTALLED_SHA256,
        'source': 'Published HTTPS delivery in actual 360 metadata, 2026-11-06T12:14:49.120373Z',
        'newer_version_claimed': False, 'candidate_signature_verified': False,
        'manifest_or_ABI_verified': False, 'latest_usable_qualified': False,
        'network_requests_attempted': 0, 'automatic_retries': 0,
        'Android_commands': 0, 'Main_actions': 0, 'App_installs': 0,
        'permission_changes': 0, 'subprocesses_started': 0,
        'old_files_modified_or_deleted': False, 'production_ready': False,
    }
    count = 0
    digest, md5 = hashlib.sha256(), hashlib.md5()
    started = time.monotonic()
    deadline = started + TOTAL_SECONDS
    try:
        info = os.fstat(root_fd)
        need(info.st_uid == 1000 and stat.S_IMODE(info.st_mode) == 0o700, 'NEW_PRIVATE_HOST_ROOT')
        context = ssl.create_default_context()
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
        request = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity'})
        result['network_requests_attempted'] = 1
        with opener.open(request, timeout=30) as response:
            need(response.status == 200 and response.geturl() == URL, 'EXACT_HTTPS_RESPONSE_REQUIRED')
            need(response.headers.get('Retry-After') is None, 'SERVER_RETRY_AFTER_RESPECTED')
            lengths = response.headers.get_all('Content-Length')
            need(lengths == [str(EXPECTED_BYTES)], 'EXACT_PUBLISHED_CONTENT_LENGTH_REQUIRED')
            need(response.headers.get('Content-Encoding', 'identity').lower() == 'identity', 'NO_CONTENT_TRANSFORM')
            result['http'] = {'status': response.status, 'url': response.geturl(),
                'content_length': EXPECTED_BYTES, 'redirect_followed': False,
                'TLS_certificate_verification': 'default required HTTPS',
                'ETag': response.headers.get('ETag'), 'Last-Modified': response.headers.get('Last-Modified')}
            fd = os.open(NAME + '.partial', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o400, dir_fd=root_fd)
            try:
                while True:
                    need(time.monotonic() < deadline, 'BOUNDED_DOWNLOAD_DEADLINE')
                    block = response.read(min(65536, EXPECTED_BYTES + 1 - count))
                    if not block:
                        break
                    if count == 0:
                        need(block.startswith(b'PK\x03\x04'), 'EXPECTED_APK_ZIP_HEADER')
                    next_count = count + len(block)
                    need(next_count <= EXPECTED_BYTES, 'PUBLISHED_SIZE_BOUND_EXCEEDED')
                    write_all(fd, block)
                    digest.update(block)
                    md5.update(block)
                    count = next_count
                os.fsync(fd)
                need(count == EXPECTED_BYTES and os.fstat(fd).st_size == count, 'FULL_PUBLISHED_BODY_REQUIRED')
            finally:
                os.close(fd)
        original = verify_file(root_fd, NAME + '.partial', digest.hexdigest(), deadline)
        os.link(NAME + '.partial', NAME, src_dir_fd=root_fd, dst_dir_fd=root_fd, follow_symlinks=False)
        os.unlink(NAME + '.partial', dir_fd=root_fd)
        os.fsync(root_fd)
        final = verify_file(root_fd, NAME, digest.hexdigest(), deadline)
        need(original['st_dev'] == final['st_dev'] and original['st_ino'] == final['st_ino'], 'SAME_NEW_FILE_PUBLICATION')
        result.update(ok=True, path=str(ROOT / NAME), bytes=count, sha256=digest.hexdigest(), md5=md5.hexdigest(),
            final_identity=final, complete_body_rehashed=True,
            matches_bound_installed_full_APK_bytes=digest.hexdigest() == BOUND_INSTALLED_SHA256,
            state='COMPLETE_STORE_CANDIDATE_PENDING_CURRENT_SIGNATURE_MANIFEST_AND_BUSINESS_VALIDATION')
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error)[:1024], state='DOWNLOAD_FAILED_NO_RETRY')
        if isinstance(error, urllib.error.HTTPError):
            result['http_failure'] = {'status': error.code, 'refusal_respected': error.code in (403, 429),
                                      'retry_after': error.headers.get('Retry-After')}
            error.close()
        partial_exists = (ROOT / (NAME + '.partial')).exists()
        result.update(completed_stream_chunk_bytes=count, completed_stream_chunk_sha256=digest.hexdigest(),
                      partial_preserved=partial_exists, partial_full_hash_verified=False)
        if partial_exists:
            result['partial_size_snapshot'] = os.stat(NAME + '.partial', dir_fd=root_fd, follow_symlinks=False).st_size
    finally:
        os.close(root_fd)
    result['elapsed_seconds'] = time.monotonic() - started
    result['original_descriptor_identities_restored'] = census() == before
    result['ok'] = result['ok'] and result['original_descriptor_identities_restored']
    raw = (json.dumps(result, sort_keys=True) + '\n').encode()
    with (ROOT / 'download-result.json').open('xb') as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    print(raw.decode(), end='', flush=True)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
