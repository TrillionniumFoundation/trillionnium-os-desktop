#!/usr/bin/env python3
"""Package the completed frozen restore only; no downloads or installers."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile

HERE = Path(__file__).resolve().parent
SOURCE = Path('/workspace/scratch/ae1a8cf05419/round-next/restore-frozen')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('source is not a regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read()
        after = os.fstat(fd)
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if tuple(getattr(before, k) for k in keys) != tuple(getattr(after, k) for k in keys):
            raise ValueError('source changed during packaging')
        return data
    finally:
        os.close(fd)


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def save(name, value):
    write(HERE / name, (json.dumps(value, indent=2) + '\n').encode())


def archive(files):
    result = io.BytesIO()
    with gzip.GzipFile(fileobj=result, mode='wb', filename='', mtime=0, compresslevel=9) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.USTAR_FORMAT) as output:
            for name, raw in files:
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(raw), 0o644
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                output.addfile(info, io.BytesIO(raw))
    return result.getvalue()


def main():
    original = read(SOURCE / 'SHA256SUMS')
    if sha(original) != 'a3cd39678aa15bb850f538d6bc7b1a661a9a3ed1559a080231c75c42611fe00a':
        raise ValueError('frozen original identity differs')
    files = [(p.relative_to(SOURCE).as_posix(), read(p)) for p in sorted(SOURCE.rglob('*')) if p.is_file()]
    if len(files) != 225:
        raise ValueError('frozen member count differs')
    payload = dict(files)
    declared = dict(line.split('  ', 1)[::-1] for line in original.decode().splitlines())
    if set(declared) != set(payload) - {'SHA256SUMS'} or any(sha(payload[n]) != h for n, h in declared.items()):
        raise ValueError('frozen checksum coverage differs')
    raw = archive(files)
    second = archive(files)
    if raw != second:
        raise ValueError('deterministic packing differs')
    parts = []
    for number, offset in enumerate(range(0, len(raw), 2097152)):
        block = raw[offset:offset + 2097152]
        name = f'archive/restore-frozen.tar.gz.part{number:03}'
        write(HERE / name, block)
        parts.append({'path': name, 'size': len(block), 'sha256': sha(block)})
    save('archive.json', {'logical_filename': 'restore-frozen.tar.gz', 'regular_member_count': len(files), 'compressed_size': len(raw), 'sha256': sha(raw), 'inner_sha256sums_sha256': sha(original), 'parts': parts, 'deterministic_independent_packings': 2, 'bytewise_equal': True, 'archive_scope': 'All 225 original frozen files, including original absolute-path receipts as data; no installer/tool/deb payloads.'})
    save('member-manifest.json', {'members': [{'path': name, 'size': len(data), 'sha256': sha(data)} for name, data in files]})
    save('source-bindings.json', {'prior_phase_commit': 'cdf308e751e561328c556ca2ece86056d15809a0', 'prior_phase': 'support/build/evidence/2026-10-17-private-toolchain', 'prior_phase_SHA256SUMS_sha256': '638b3c5e0a1534a4c9c0656af5390374ace6f97ffd92a985cb01f2db4949da00', 'prior_native_restore_git_blob': '54bbfcc65d14c781e401d11785d544c676cdbf68', 'prior_package_lock_git_blob': '8bf22b2b33cb1dfcdb4edb5c063e98119dcfca50', 'prior_rust_restore_git_blob': '926306c8c7e59a113b920abda27599b923bc3596', 'frozen_manifest_sha256': sha(payload['manifest.json']), 'frozen_SHA256SUMS_sha256': sha(original), 'executed_native_controller': 'native-original/restore.py', 'executed_native_controller_sha256': sha(payload['native-original/restore.py']), 'executed_new_rust_controller': 'controllers/restore-rust-controller.py', 'executed_new_rust_controller_sha256': sha(payload['controllers/restore-rust-controller.py']), 'controller_adaptation': 'New Rust controller preserves the original eight installer/version/binutils/vDSO operations, uses allowed round-next outputs, requires fresh exact installer/manifest bytes and validated private native prefix, and records current inherited PATH plus explicit private entries. Four additional identity/components checks follow.'})
    omitted = json.loads(payload['manifest.json'])['omitted_payloads']
    save('omitted-artifacts.json', {'omitted': omitted, 'fresh_nightly_manifest': {'member': 'restore-rust-inputs/channel-rust-nightly.toml', 'direct_copy': 'fresh-nightly-manifest.toml.gz', 'uncompressed_size': 929653, 'sha256': 'c0b09f4e128768b2d6eab27050625a1ce974f8b39c07871370368cd82fbf8617', 'raw_body_retained': True}, 'scope': 'Omitted payloads were present and used locally during the recorded restoration. This archive verifies authenticated input metadata and original receipts; it cannot reinstall tools without fetching omitted payloads.'})
    write(HERE / 'fresh-nightly-manifest.toml.gz', gzip.compress(payload['restore-rust-inputs/channel-rust-nightly.toml'], compresslevel=9, mtime=0))
    save('report.json', {'state': 'completed actual private dependency restoration on distinct execution instance; no kernel acceptance', 'actual_host': '24f0ea2620fe', 'boot_id': '952006db-88a3-4a56-8049-0adbbe2acfb2', 'kernel': 'Linux 6.18.55', 'cpu_model': 'AMD EPYC 9V74 80-Core Processor', 'old_host_reference': '343e40cfefc1 / Linux 6.18.44 / Intel exposed CPU', 'same_public_dpkg_status_sha256': '315debd2c0d91242550234b1fc27842103bccdf4274aa75c59b6d1f51d07966e', 'native': {'signed_InRelease': 3, 'signed_Packages_indexes': 6, 'exact_locked_packages': 57, 'download_bytes': 132706754, 'package_extractions_exit_zero': 57, 'native_runtime_commands_exit_zero': 19, 'executable_and_guest_firmware_identities_equal': 10, 'paused_QEMU_owned_child_passed': True, 'paused_QEMU_is_kernel_boot': False}, 'rust': {'fresh_installer_size': 21113232, 'fresh_installer_sha256': 'dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71', 'fresh_manifest_size': 929653, 'fresh_manifest_sha256': 'c0b09f4e128768b2d6eab27050625a1ce974f8b39c07871370368cd82fbf8617', 'toolchain': 'nightly-2026-07-21', 'rustc_commit': '87e5904f5eb6398af6b22eac2802c78934260c48', 'target': 'x86_64-unknown-none', 'components': ['rust-src', 'rustc-dev', 'llvm-tools-preview', 'rustfmt', 'clippy'], 'cargo_binutils': '0.4.0 --locked', 'original_eight_operations_exit_zero': True, 'additional_identity_checks_exit_zero': 4, 'global_cargo_osdk_installed': False}, 'vdso': {'commit': '8af571775a3d3a1df3e84fc9709b9d6b160c771a', 'tree': '8e0a300d78c2a020ccc79f1253bc27a8301416e6', 'artifact_sha256': '27cd7bf576a92fa48a891c05988f52fac35b7374d5b9650d6b035e477c5d93a3'}, 'failed_current_dependency_commands': [], 'historical_failure_scope': 'The prior 2026-10-17-private-toolchain phase retains original prepare-host.sh --apt exit100 and missing-QEMU-resource warning. Neither was rerun or silently converted to a pass in this restoration.', 'restrictions': {'dev_kvm_present': False, 'default_AF_UNIX_socket_errno': 1, 'AF_UNIX_socketpair_passed': True, 'IPv4_loopback_passed': True, 'system_packages_installed': False, 'maintainer_scripts_executed': False, 'sandbox_or_namespace_or_capabilities_modified': False, 'Docker_or_Nix_installed': False}, 'frozen_regular_members': len(files), 'frozen_bytes': sum(len(x) for _, x in files), 'archive_sha256': sha(raw), 'limits': ['A different exposed host/kernel/CPU model is observed, not independently attested physical hardware.', 'The private prefix reuses unchanged system libc; this is not an immutable environment.', 'Only restoration is accepted here. Cross-instance kernel compilation, ELF equality and real guest acceptance are separate.', 'Offline verification checks preserved cryptographic inputs and original receipts, not a new dependency install or VM.']})
    if read(SOURCE / 'SHA256SUMS') != original:
        raise ValueError('frozen original changed while packaging')
    print(json.dumps({'members': len(files), 'compressed_size': len(raw), 'parts': len(parts), 'archive_sha256': sha(raw)}, sort_keys=True))


if __name__ == '__main__':
    main()
