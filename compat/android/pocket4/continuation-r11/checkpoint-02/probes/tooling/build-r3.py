#!/usr/bin/env python3
"""Build a headless owned APK using existing pinned Pocket4 tools; never install."""
from pathlib import Path, PurePosixPath
import ast
import datetime
import hashlib
import json
import os
import re
import resource
import struct
import subprocess
import sys
import zipfile

WORK = Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work')
DEFINITIONS = WORK / 'native-jni-oracle-v6/build.py'
DEFINITIONS_SHA = '0e77ac152e7fd91cb6e5171e189394fbdd4c30f6e62af919c7ca31dcab5ceb59'
NDK_ARCHIVE = Path('/home/alex/.local/state/pocket4-app-production-20261028-session/ndk-toolchain/android-ndk-r27d-linux.zip')
NDK_PREFIX = 'android-ndk-r27d/toolchains/llvm/prebuilt/linux-x86_64/sysroot/'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    root = Path(sys.argv[1]).resolve()
    kind = sys.argv[2]
    attempt = int(sys.argv[3])
    assert kind in ('owner', 'signal', 'signal-r3') and 1 <= attempt <= 9
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    allowed = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {6 if 6 in allowed else min(allowed)})
    build = root / ('build-attempt-' + str(attempt))
    build.mkdir(mode=0o700)
    report = {'state': 'BUILDING', 'kind': kind, 'commands': [],
              'actual_android_executed': False,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}

    def save():
        (build / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n')

    try:
        assert sha(DEFINITIONS) == DEFINITIONS_SHA
        scope = {'__name__': 'pinned_v6_definitions', '__file__': str(DEFINITIONS)}
        exec(compile(DEFINITIONS.read_bytes(), str(DEFINITIONS), 'exec'), scope)
        pins = scope['TOOL_PINS']
        assert all(sha(path) == expected for path, expected in pins.items())
        assert sha(scope['TEST_KEY']) == scope['TEST_KEY_SHA']
        # Reuse only the existing, hash-pinned owned-test signing configuration.
        # Do not put signing arguments or credentials in the build receipt.
        definitions_ast = ast.parse(DEFINITIONS.read_text())
        signing_literals = {n.value for n in ast.walk(definitions_ast)
                            if isinstance(n, ast.Constant) and isinstance(n.value, str)
                            and n.value.startswith('pass:')}
        assert len(signing_literals) == 1, 'ambiguous pinned test signing argument'
        signing_argument = next(iter(signing_literals))
        signing_aliases = set()
        for node in ast.walk(definitions_ast):
            if isinstance(node, ast.List):
                for index, item in enumerate(node.elts[:-1]):
                    if isinstance(item, ast.Constant) and item.value == '--ks-key-alias':
                        alias = node.elts[index + 1]
                        assert isinstance(alias, ast.Constant) and isinstance(alias.value, str)
                        signing_aliases.add(alias.value)
        assert len(signing_aliases) <= 1, 'ambiguous pinned test signing alias'
        signing_alias_arguments = ['--ks-key-alias', next(iter(signing_aliases))] if signing_aliases else []
        archive_sha = sha(NDK_ARCHIVE)
        report['ndk_archive'] = {'sha256': archive_sha, 'bytes': NDK_ARCHIVE.stat().st_size,
                                 'provenance': 'existing retained NDK archive; hash observed before extraction'}
        sysroot = build / 'sysroot'
        sysroot.mkdir()
        extracted = {}
        with zipfile.ZipFile(NDK_ARCHIVE) as archive:
            for member in archive.infolist():
                if not member.filename.startswith(NDK_PREFIX) or member.is_dir():
                    continue
                relative = member.filename[len(NDK_PREFIX):]
                selected = relative.startswith('usr/include/') or relative in (
                    'usr/lib/x86_64-linux-android/24/libc.so',
                    'usr/lib/aarch64-linux-android/24/libc.so')
                if not selected:
                    continue
                part = PurePosixPath(relative)
                assert not part.is_absolute() and '..' not in part.parts
                assert (member.external_attr >> 16) & 0o170000 != 0o120000
                target = sysroot / relative
                target.parent.mkdir(exist_ok=True, parents=True)
                data = archive.read(member)
                target.write_bytes(data)
                extracted[relative] = hashlib.sha256(data).hexdigest()
        (build / 'ndk-extracted-sha256.json').write_text(json.dumps(extracted, indent=2) + '\n')
        source_files = sorted(p for p in root.rglob('*') if p.is_file()
                              and not any(x.startswith('build-attempt-') for x in p.relative_to(root).parts))
        source_pins = {str(p.relative_to(root)): sha(p) for p in source_files}
        clang, jdk, sdk, r8, aapt, align, signer = [scope[k] for k in (
            'CLANG_DIR', 'JDK', 'SDK', 'R8', 'AAPT', 'ALIGN', 'SIGNER')]
        abi, triple, library = ('x86_64', 'x86_64-linux-android', 'fdownerprobe') if kind == 'owner' else (
            'arm64-v8a', 'aarch64-linux-android', 'owned_signal_probe')
        package = 'local.pocket4.fdownerprobe.r11' if kind == 'owner' else ('org.droidloom.signalprobe.r3' if kind == 'signal-r3' else 'org.droidloom.signalprobe')
        for directory in ('classes', 'dex', 'res', 'lib/' + abi):
            (build / directory).mkdir(parents=True, mode=0o700)
        env = {'PATH': str(jdk) + ':/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(build)}

        def run(name, args, timeout=100, secret=False):
            argv = list(map(str, args))
            proc = subprocess.run(argv, cwd=build, env=env, capture_output=True, timeout=timeout)
            stdout = proc.stdout.replace(signing_argument.encode(), b'[test-signing]')
            stderr = proc.stderr.replace(signing_argument.encode(), b'[test-signing]')
            (build / (name + '.stdout')).write_bytes(stdout)
            (build / (name + '.stderr')).write_bytes(stderr)
            report['commands'].append({'name': name, 'argv': ['[existing owned-test signing configuration]'] if secret else argv,
                'returncode': proc.returncode, 'stdout_sha256': sha(build / (name + '.stdout')),
                'stderr_sha256': sha(build / (name + '.stderr'))})
            save()
            assert proc.returncode == 0, (name, proc.returncode, stderr.decode(errors='replace')[-5000:])
            return stdout.decode(errors='replace')

        lib = build / 'lib' / abi / ('lib' + library + '.so')
        sources = [root / 'owner_probe.cpp'] if kind == 'owner' else sorted((root / 'native').glob('*.c')) + sorted((root / 'native').glob('*.S'))
        assert sources and all(p.is_file() for p in sources)
        common = [clang / ('clang++' if kind == 'owner' else 'clang'), '-target', triple + '24',
            '--sysroot=' + str(sysroot), '-shared', '-nostdlib', '-fPIC', '-fuse-ld=lld',
            '-Wl,--build-id=sha1,--no-undefined,--allow-shlib-undefined,--no-as-needed,--soname,lib' + library + '.so,-z,noexecstack,-z,relro,-z,now',
            '-fno-stack-protector', '-fvisibility=hidden', '-Wall', '-Wextra', '-Werror', '-O1',
            '-I', jdk.parent / 'include', '-I', jdk.parent / 'include/linux',
            '-I', sysroot / 'usr/include' / triple]
        if kind == 'owner':
            common += ['-std=c++17', '-fno-exceptions', '-fno-rtti', '-nostdinc++', '-isystem', sysroot / 'usr/include/c++/v1']
        else:
            common += ['-std=c11', '-D_GNU_SOURCE', '-march=armv8-a', '-mno-outline-atomics', '-mbranch-protection=none', '-fno-omit-frame-pointer']
        run('compile-native', common + sources + [sysroot / ('usr/lib/' + triple + '/24/libc.so'), '-o', lib])
        java = sorted((root / ('src' if kind == 'owner' else 'java')).rglob('*.java'))
        run('javac', [jdk / 'javac', '-J-XX:ActiveProcessorCount=1', '-J-XX:+UseSerialGC', '-J-Xmx256m',
            '-source', '8', '-target', '8', '-bootclasspath', sdk, '-d', build / 'classes'] + java)
        run('d8', [jdk / 'java', '-XX:ActiveProcessorCount=1', '-XX:+UseSerialGC', '-Xmx256m', '-cp', r8,
            'com.android.tools.r8.D8', '--lib', sdk, '--min-api', '24', '--output', build / 'dex'] + sorted((build / 'classes').rglob('*.class')))
        run('aapt-package', [aapt, 'package', '-f', '-M', root / 'AndroidManifest.xml', '-S', build / 'res', '-I', sdk, '-F', build / 'unsigned.apk'])
        with zipfile.ZipFile(build / 'unsigned.apk', 'a', compression=zipfile.ZIP_STORED) as archive:
            archive.write(build / 'dex/classes.dex', 'classes.dex')
            archive.write(lib, 'lib/' + abi + '/' + lib.name)
        run('align', [align, '-f', '4', build / 'unsigned.apk', build / 'aligned.apk'])
        apk = build / (library + '.apk')
        run('sign', [signer, 'sign', '--ks', scope['TEST_KEY']] + signing_alias_arguments + [
            '--ks-pass', signing_argument, '--key-pass', signing_argument, '--out', apk, build / 'aligned.apk'], secret=True)
        signature = run('signature', [signer, 'verify', '--verbose', '--print-certs', apk])
        run('alignment', [align, '-c', '4', apk])
        badging = run('badging', [aapt, 'dump', 'badging', apk])
        permissions = run('permissions', [aapt, 'dump', 'permissions', apk])
        manifest = run('manifest', [aapt, 'dump', 'xmltree', apk, 'AndroidManifest.xml'])
        elf = run('ELF', ['/usr/bin/readelf', '-h', '-d', '--dyn-syms', '-l', '-r', '-V', '--wide', lib])
        run('disassembly', [clang / 'llvm-objdump', '-d', lib])
        assert 'uses-permission:' not in permissions and 'launchable-activity:' not in badging
        assert "package: name='" + package + "'" in badging
        assert "native-code: '" + abi + "'" in badging
        assert 'Signer #1 certificate SHA-256 digest: ' + scope['SIGNER_CERT_SHA'] in signature
        assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in signature
        assert 'Verified using v3 scheme (APK Signature Scheme v3): true' in signature
        data = lib.read_bytes()
        assert data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', data, 16)[0] == 3
        assert struct.unpack_from('<H', data, 18)[0] == (62 if kind == 'owner' else 183)
        needed = re.findall(r'\(NEEDED\).*Shared library: \[(.*?)\]', elf)
        assert needed == ['libc.so'] and 'BIND_NOW' in elf
        po = struct.unpack_from('<Q', data, 32)[0]
        ps, pc = struct.unpack_from('<HH', data, 54)
        ph = [struct.unpack_from('<IIQQQQQQ', data, po + i * ps) for i in range(pc)]
        assert not any(p[0] == 1 and p[1] & 3 == 3 for p in ph)
        assert any(p[0] == 0x6474e551 and p[1] == 6 for p in ph) and any(p[0] == 0x6474e552 for p in ph)
        with zipfile.ZipFile(apk) as archive:
            assert [n for n in archive.namelist() if n.startswith('lib/')] == ['lib/' + abi + '/' + lib.name]
            assert archive.read('lib/' + abi + '/' + lib.name) == data
        assert all(sha(root / name) == expected for name, expected in source_pins.items())
        assert all(sha(path) == expected for path, expected in pins.items())
        assert sha(NDK_ARCHIVE) == archive_sha
        report.update(state='BUILT_STATIC_VERIFIED_ANDROID_UNRUN', package=package, ABI=abi,
            APK={'path': str(apk), 'sha256': sha(apk), 'bytes': apk.stat().st_size},
            ELF={'sha256': sha(lib), 'needed': needed, 'NX_RELRO_NOW_no_WX': True},
            source_sha256=source_pins, builder_sha256=sha(__file__),
            tools_sha256={str(p): h for p, h in pins.items()}, no_permissions=True, no_activity=True)
    except Exception as error:
        report.update(state='FAILED', error=repr(error))
    report['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save()
    print(json.dumps({'state': report['state'], 'error': report.get('error'), 'APK': report.get('APK')}), flush=True)
    return 0 if report['state'] == 'BUILT_STATIC_VERIFIED_ANDROID_UNRUN' else 1


if __name__ == '__main__':
    raise SystemExit(main())
