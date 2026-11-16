#!/usr/bin/env bash
# Run only in the disposable Ubuntu CI job. No producer or Android build here.
set -euo pipefail
umask 077
if [[ $# != 2 || $1 != --work ]]; then
  printf 'usage: %s --work NEW_ABSOLUTE_DIRECTORY\n' "$0" >&2
  exit 2
fi
capsule_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 -I -B - "$capsule_dir" "$2" <<'PY'
import ctypes
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import sys
import tarfile
import time
import traceback

HERE = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location('current_setup_runner', HERE / 'run_ci.py')
CI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CI)
V = CI.VERIFY
URL = 'https://deb.debian.org/debian/pool/main/e/erofs-utils/erofs-utils_1.9.4.orig.tar.gz'
SOURCE = {'bytes': 273489, 'sha256': '7d135aa2550326a5acf20f53c518aea5a8900015ce50700044e40f818c31dd80'}
PACKAGES = ['build-essential', 'gcc-13', 'pkgconf', 'libgbm-dev', 'libdrm-dev', 'libegl-dev',
    'libgles-dev', 'libwayland-dev', 'libxkbcommon-dev', 'libsystemd-dev', 'git', 'rsync',
    'python3', 'zip', 'unzip', 'xz-utils', 'coreutils', 'util-linux', 'gawk', 'dash',
    'dbus-daemon', 'e2fsprogs', 'attr', 'fakeroot', 'libarchive-tools', 'autoconf', 'automake',
    'libtool', 'liblz4-dev', 'liblzma-dev', 'libzstd-dev', 'libselinux1-dev', 'libattr1-dev',
    'uuid-dev', 'zlib1g-dev', 'curl', 'ca-certificates']

V.need(os.geteuid() != 0 and os.uname().machine == 'x86_64' and sys.platform == 'linux',
       'run setup as the ordinary Ubuntu amd64 CI user')
cpus = sorted(os.sched_getaffinity(0))
V.need(len(cpus) >= 4, 'two build CPUs and two reserved CPUs required')
os.sched_setaffinity(0, set(cpus[:2]))
V.need(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, 'setup subreaper required')
V.need(not CI.owned_children(), 'setup starts without owned descendants')
signal.signal(signal.SIGTERM, CI.interrupted)
signal.signal(signal.SIGINT, CI.interrupted)
work = V.fresh_destination(Path(sys.argv[2]), [HERE])
V.need(work.is_absolute() and not any(c.isspace() for c in str(work)), 'new absolute path without whitespace required')
work.mkdir(mode=0o700)
logs = work / 'logs'; logs.mkdir(mode=0o700)
prefix = work / 'erofs'; source = work / 'source'
archive = work / 'erofs-utils_1.9.4.orig.tar.gz'
deadline = time.monotonic() + 1800
result = {'schema': 'p4-current-ci-dependencies-v1', 'state': 'RUNNING', 'commands': [], 'errors': [],
    'started_ns': time.time_ns(), 'source_url': URL, 'expected_source': SOURCE,
    'source_checksum_publication': 'https://tracker.debian.org/news/1788045/accepted-erofs-utils-194-1-source-into-unstable/',
    'private_erofs_prefix': str(prefix), 'requested_packages': PACKAGES,
    'affinity': cpus[:2], 'reserved_cpus': cpus[2:], 'jobs': 1, 'whole_limit_seconds': 1800,
    'producer_builds': 0, 'Android_builds': 0, 'Android_starts': 0, 'production_ready': False}
rustup = shutil.which('rustup')
V.need(rustup is not None, 'official Ubuntu runner must already provide rustup')
env = {key: value for key, value in os.environ.items() if key in
       {'HOME', 'USER', 'LOGNAME', 'RUSTUP_HOME', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
        'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}}
env.update(PATH=str(Path(rustup).absolute().parent) + ':/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
           LANG='C.UTF-8', LC_ALL='C.UTF-8', PYTHONDONTWRITEBYTECODE='1',
           CC='/usr/bin/x86_64-linux-gnu-gcc-13', PKG_CONFIG='/usr/bin/pkgconf',
           MAKEFLAGS='-j1', RUSTUP_TOOLCHAIN='1.93.0', RUSTUP_AUTO_INSTALL='0')

def before(seconds=0):
    V.need(time.monotonic() + seconds < deadline, 'dependency preparation deadline')

def run(name, argv, seconds, cwd=work):
    before(seconds + 15)
    V.need(not CI.owned_children(), 'prior setup command still has children')
    start = time.time_ns()
    outpath, errpath = logs / (name + '.stdout'), logs / (name + '.stderr')
    with outpath.open('xb') as out, errpath.open('xb') as err:
        actual = CI.execute_child(argv, cwd, env, out, err, seconds)
    stdout, stderr = V.regular(outpath, 32 * 1024**2), V.regular(errpath, 32 * 1024**2)
    result['commands'].append({'name': name, 'argv': argv, 'cwd': str(cwd), 'started_ns': start,
        'finished_ns': time.time_ns(), **actual,
        'stdout': {'path': str(outpath), **V.digest(stdout)},
        'stderr': {'path': str(errpath), **V.digest(stderr)}})
    V.need(actual['error'] is None and not actual['cleanup_errors'] and actual['exit_code'] == 0
           and actual['actual_child_reaped'] and actual['original_pidfd_held_until_reaped']
           and not CI.owned_children() and not any(x.get('forced') for x in actual['retired_descendants']),
           'dependency command or retirement failed: ' + name)
    before()
    return stdout, stderr

def tool_identity(requested):
    path = Path(requested).resolve(strict=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        V.need(stat.S_ISREG(first.st_mode) and 0 < first.st_size <= 128 * 1024**2, 'bounded dependency file')
        h = hashlib.sha256(); total = 0
        while True:
            before()
            block = os.read(fd, 1024**2)
            if not block: break
            total += len(block); h.update(block)
        V.need(total == first.st_size and V.f9(first) == V.f9(os.fstat(fd)) == V.f9(path.lstat()),
               'dependency changed during hash')
        return {'requested_path': str(requested), 'resolved_path': str(path),
                'identity': V.f9(first), 'bytes': total, 'sha256': h.hexdigest()}
    finally:
        os.close(fd)

def extract_source(raw):
    before()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as bundle:
        members = bundle.getmembers()
        V.need(0 < len(members) <= 4096 and sum(m.size for m in members) <= 16 * 1024**2,
               'bounded official source archive')
        paths = set(); roots = set()
        for member in members:
            path = PurePosixPath(member.name)
            V.need(not path.is_absolute() and member.name.rstrip('/') == path.as_posix()
                   and all(p not in ('', '.', '..') for p in path.parts)
                   and all(ord(c) >= 32 and ord(c) != 127 for c in member.name)
                   and '\\' not in member.name and not member.linkname
                   and (member.isfile() or member.isdir()) and 0 <= member.size <= 2 * 1024**2,
                   'ordinary source members only')
            V.need(path.as_posix() not in paths, 'duplicate official source path')
            paths.add(path.as_posix()); roots.add(path.parts[0])
        V.need(len(roots) == 1, 'single official source root')
        source.mkdir(mode=0o700)
        for member in members:
            before()
            parts = PurePosixPath(member.name).parts[1:]
            if not parts:
                V.need(member.isdir(), 'archive root must be a directory'); continue
            path = source.joinpath(*parts)
            if member.isdir():
                path.mkdir(mode=0o700, parents=True, exist_ok=True); continue
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            V.need(path.parent.resolve() == path.parent, 'no extraction parent alias')
            body = bundle.extractfile(member).read(member.size + 1)
            V.need(len(body) == member.size, 'whole official source member')
            with path.open('xb') as output:
                output.write(body); output.flush(); os.fsync(output.fileno())
            path.chmod(0o700 if member.mode & 0o111 else 0o600)
        result['source_archive_members'] = len(members)
        result['source_archive_root'] = next(iter(roots))
    before()

try:
    result['fresh_disk_free_bytes'] = shutil.disk_usage(work).free
    V.need(result['fresh_disk_free_bytes'] >= 8 * 1024**3, 'dependency preparation needs 8 GiB free')
    apt = ['/usr/bin/sudo', '-n', '/usr/bin/env', 'DEBIAN_FRONTEND=noninteractive',
           '/usr/bin/apt-get', '-o', 'Acquire::Retries=0', '-o', 'Acquire::http::Timeout=30',
           '-o', 'Acquire::https::Timeout=30', '-o', 'DPkg::Lock::Timeout=60']
    run('apt-update', [*apt, 'update'], 180)
    run('apt-install', [*apt, 'install', '-y', '--no-install-recommends', *PACKAGES], 600)
    run('resolved-packages', ['/usr/bin/dpkg-query', '-W',
         '-f=${binary:Package}\t${Version}\t${Architecture}\n', *PACKAGES], 30)
    run('rust-toolchain', [rustup, 'toolchain', 'install', '1.93.0', '--profile', 'minimal'], 300)
    stdout, _ = run('rust-version', [rustup, 'run', '1.93.0', 'rustc', '--version'], 30)
    V.need(stdout.decode().startswith('rustc 1.93.0 '), 'exact Rust toolchain')
    run('cargo-version', [rustup, 'run', '1.93.0', 'cargo', '--version'], 30)
    run('native-library-versions', ['/usr/bin/pkgconf', '--modversion', 'gbm', 'libdrm', 'egl',
         'glesv2', 'wayland-client', 'xkbcommon', 'libsystemd', 'liblz4', 'liblzma', 'libzstd'], 30)
    run('fetch-erofs-source', ['/usr/bin/curl', '--fail', '--show-error', '--silent', '--location',
         '--proto', '=https', '--proto-redir', '=https', '--connect-timeout', '15', '--max-time', '75',
         '--max-filesize', '1048576', '--output', str(archive), URL], 90)
    raw = V.regular(archive, 1048576)
    V.need(V.digest(raw) == SOURCE, 'official EROFS 1.9.4 source size and SHA256 must both match')
    result['actual_source'] = {'path': str(archive), **V.digest(raw)}
    extract_source(raw)
    V.need((source / 'autogen.sh').is_file() and (source / 'configure.ac').is_file(), 'upstream autotools source')
    run('erofs-autogen', ['/bin/sh', './autogen.sh'], 60, source)
    run('erofs-configure', ['./configure', '--prefix=' + str(prefix), '--bindir=' + str(prefix / 'bin'),
         '--enable-lz4', '--enable-lzma', '--with-libzstd', '--with-selinux', '--disable-fuse'], 120, source)
    config = V.regular(source / 'config.h', 1048576).decode()
    required_macros = ['LZ4_ENABLED', 'LZ4HC_ENABLED', 'HAVE_SYS_XATTR_H', 'HAVE_LGETXATTR',
                       'HAVE_LLISTXATTR', 'HAVE_LSETXATTR', 'HAVE_LIBSELINUX']
    for name in required_macros:
        V.need(re.search(r'^#define\s+' + name + r'\s+1\s*$', config, re.MULTILINE),
               'EROFS required configure feature missing: ' + name)
    result['configured_features'] = required_macros
    result['configure_header'] = {'path': str(source / 'config.h'), **V.digest(config.encode())}
    run('erofs-build', ['/usr/bin/make', '-j1'], 300, source)
    run('erofs-private-install', ['/usr/bin/make', '-j1', 'install'], 60, source)
    identities = []
    for name in ('mkfs.erofs', 'fsck.erofs', 'dump.erofs'):
        path = prefix / 'bin' / name
        V.need(path.resolve() == path and os.access(path, os.X_OK), 'actual private EROFS executable')
        stdout, stderr = run('version-' + name, [str(path), '-V'], 30)
        V.need(re.search(rb'(?<![0-9.])1\.9\.4(?![0-9.])', stdout + stderr), 'actual EROFS version')
        identities.append(tool_identity(path))
    run('fakeroot-version', ['/usr/bin/fakeroot-sysv', '--version'], 30)
    run('bsdtar-version', ['/usr/bin/bsdtar', '--version'], 30)
    for requested in ['/usr/bin/fakeroot-sysv', '/usr/bin/faked-sysv',
                      '/usr/lib/x86_64-linux-gnu/libfakeroot/libfakeroot-sysv.so', '/bin/sh',
                      '/usr/sbin/mke2fs', '/usr/sbin/debugfs', '/usr/sbin/e2fsck',
                      '/usr/bin/bsdtar', '/usr/bin/getfattr', '/usr/bin/setfattr',
                      '/usr/bin/awk', '/usr/bin/x86_64-linux-gnu-gcc-13', '/usr/bin/pkgconf', rustup]:
        identities.append(tool_identity(requested))
    result['tool_identities'] = identities
    result['package_versions'] = (logs / 'resolved-packages.stdout').read_text().splitlines()
    result['preservation_tests_required'] = True
    result['image_preservation_qualified_by_setup'] = False
    before()
    result['state'] = 'DEPENDENCIES_PREPARED'
except BaseException as error:
    result['state'] = 'FAILED'
    result['errors'].append({'type': type(error).__name__, 'message': str(error),
                             'traceback': traceback.format_exc()})
finally:
    try:
        retired = CI.reap_descendants()
        result['final_retirement'] = retired
        V.need(not CI.owned_children() and not any(row.get('forced') for row in retired),
               'setup finalizer found unexpected descendants')
    except BaseException as error:
        result['state'] = 'FAILED'; result['errors'].append({'cleanup': repr(error)})
    if time.monotonic() >= deadline:
        result['state'] = 'FAILED'; result['errors'].append({'whole_deadline_expired': True})
result['finished_ns'] = time.time_ns()
V.write_report(work / 'DEPENDENCIES.json', result, [HERE])
print(json.dumps({'state': result['state'], 'manifest': str(work / 'DEPENDENCIES.json'),
                  'private_erofs_prefix': str(prefix), 'producer_builds': 0}, sort_keys=True))
raise SystemExit(0 if result['state'] == 'DEPENDENCIES_PREPARED' else 1)
PY
