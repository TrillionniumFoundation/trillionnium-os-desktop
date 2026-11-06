#!/usr/bin/env python3
"""Fetch one official, independently checksum-bound host tool; never execute it."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import ssl
import stat
import sys
import time
import urllib.request
import zipfile

URL = 'https://dl.google.com/dl/android/maven2/com/android/tools/build/aapt2/9.5.1-16666295/aapt2-9.5.1-16666295-linux.jar'
EXPECTED_SHA256 = 'fa1014cb1431622d292ef55ba870e75882ea19987bec541698b912f446a2d08f'
ROOT = Path('/home/alex/work/pocket4-official-aapt2-9.5.1-16666295-20261106-r1')
NAME = 'aapt2-9.5.1-16666295-linux.jar'
MAX_BYTES = 16 * 1024 * 1024


def need(value, message):
    if not value:
        raise RuntimeError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('UNEXPECTED_REDIRECT_NO_FOLLOW')


def census():
    rows = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name)
            s = os.fstat(fd)
            rows[name] = [os.readlink('/proc/self/fd/' + name), s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid]
        except FileNotFoundError:
            continue
        except OSError as error:
            if error.errno != 9:
                raise
    return rows


def main():
    need(os.getuid() == os.geteuid() == 1000, 'OPERATOR_UID1000_REQUIRED')
    need(sys.argv[1:] == ['--fetch-once'], 'EXACT_OPERATION_REQUIRED')
    need(ROOT.parent.resolve() == ROOT.parent, 'HOST_WORK_PARENT_ALIAS')
    os.umask(0o077)
    before = census()
    ROOT.mkdir(mode=0o700)
    root_fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    result = {'schema': 'pocket4-official-aapt2-download-v1', 'ok': False, 'url': URL,
              'expected_sha256': EXPECTED_SHA256, 'automatic_retry': False,
              'tool_executed': False, 'Android_commands': 0, 'Main_actions': 0,
              'App_installs': 0, 'permission_changes': 0, 'production_ready': False}
    try:
        info = os.fstat(root_fd)
        need(info.st_uid == 1000 and stat.S_IMODE(info.st_mode) == 0o700, 'NEW_PRIVATE_HOST_ROOT')
        context = ssl.create_default_context()
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
        request = urllib.request.Request(URL, headers={'User-Agent': 'Pocket4-official-tool-audit/1'})
        deadline = time.monotonic() + 90
        count, digest = 0, hashlib.sha256()
        with opener.open(request, timeout=15) as response:
            need(response.status == 200 and response.geturl() == URL, 'EXACT_OFFICIAL_HTTPS_RESPONSE')
            length_text = response.headers.get('Content-Length')
            need(length_text is not None and length_text.isdecimal() and 0 < int(length_text) <= MAX_BYTES,
                 'BOUNDED_DECLARED_ARTIFACT_LENGTH_REQUIRED')
            expected_length = int(length_text)
            result['http'] = {'status': response.status, 'final_url': response.geturl(),
                              'content_length': expected_length, 'certificate_verification': 'default required HTTPS',
                              'redirect_followed': False, 'last_modified': response.headers.get('Last-Modified')}
            fd = os.open(NAME + '.partial', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o400, dir_fd=root_fd)
            with os.fdopen(fd, 'wb') as stream:
                while True:
                    need(time.monotonic() < deadline, 'ARTIFACT_TOTAL_DEADLINE')
                    chunk = response.read(min(65536, MAX_BYTES + 1 - count))
                    if not chunk:
                        break
                    count += len(chunk)
                    need(count <= MAX_BYTES, 'ARTIFACT_SIZE_BOUND')
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
                need(count == expected_length and os.fstat(stream.fileno()).st_size == count,
                     'ARTIFACT_LENGTH_CHANGED')
        need(digest.hexdigest() == EXPECTED_SHA256, 'OFFICIAL_PUBLISHED_SHA256_MISMATCH')
        path = ROOT / (NAME + '.partial')
        members = []
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            need(0 < len(infos) <= 64 and len({v.filename for v in infos}) == len(infos), 'BOUNDED_UNIQUE_JAR_MEMBERS')
            total = 0
            for member in infos:
                name = PurePosixPath(member.filename)
                need(not name.is_absolute() and '..' not in name.parts and not member.flag_bits & 1 and
                     stat.S_IFMT(member.external_attr >> 16) != stat.S_IFLNK and
                     0 <= member.file_size <= 32 * 1024 * 1024, 'UNSAFE_JAR_MEMBER')
                total += member.file_size
                need(total <= 64 * 1024 * 1024 and time.monotonic() < deadline, 'JAR_EXPANSION_OR_TIME_BOUND')
                members.append({'name': member.filename, 'bytes': member.file_size, 'compressed_bytes': member.compress_size})
            need(sum(v.filename == 'aapt2' and not v.is_dir() for v in infos) == 1, 'ONE_ROOT_AAPT2_MEMBER_REQUIRED')
            need(archive.testzip() is None, 'JAR_CRC_FAILURE')
        os.link(NAME + '.partial', NAME, src_dir_fd=root_fd, dst_dir_fd=root_fd, follow_symlinks=False)
        os.unlink(NAME + '.partial', dir_fd=root_fd)
        os.fsync(root_fd)
        result.update(ok=True, path=str(ROOT / NAME), bytes=count, sha256=digest.hexdigest(),
                      published_sha256_match=True, jar_members=members, jar_extracted=False,
                      legacy_tools_or_APKs_modified=False, namespace_entries=0, subprocesses_started=0)
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error)[:1024])
    finally:
        os.close(root_fd)
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
