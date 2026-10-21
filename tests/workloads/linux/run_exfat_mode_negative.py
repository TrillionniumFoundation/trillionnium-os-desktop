#!/usr/bin/env python3
"""Run the frozen, one-line ExFAT old-mode control in an owned cloud worktree.

The original positive source checkout remains clean. The temporary commit and
full snapshots identify the sole production mutation; all tests, probes, build
inputs and gate code stay byte-identical to the reviewed candidate.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('exfat_disk', Path(__file__).with_name('run_exfat_mode_guest.py'))
disk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disk)
ROOT, require, save = disk.ROOT, disk.require, disk.save
INODE = 'kernel/asterinas/kernel/core/src/fs/fs_impls/exfat/inode.rs'
PATCH = 'tests/organ_backend/exfat_synthesized_setid_negative.patch'
PATCH_SHA256 = '525e11369a5aefe9ae79358b83a293aa40e4b63de53b476b22cf220c55cd7024'
BEFORE = b'        let mut ret = mkmod!(a+rwx);\n'
AFTER = b'        let mut ret = InodeMode::all();\n'


def mutation(source):
    require(source.count(BEFORE) == 1, 'reviewed access-bit initializer is absent or ambiguous')
    return source.replace(BEFORE, AFTER)


def verify_delta(before, after, original, changed):
    require(before['files'].keys() == after['files'].keys(), 'mutation added or removed tracked files')
    paths = [path for path in before['files'] if before['files'][path] != after['files'][path]]
    require(paths == [INODE], 'mutation changed a test, gate, dependency or unrelated production path')
    require(changed == mutation(original), 'mutation is not the exact old access-mode behavior')
    for snapshot, content in ((before, original), (after, changed)):
        row = snapshot['files'][INODE]
        require(row['mode'] == '100644' and row['size'] == len(content)
                and row['sha256'] == disk.sha(content), 'inode postimage differs from the full source snapshot')


def run(args, out, report):
    before = disk.product.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(out / 'positive-source-before.json', before)
    kernel, product_sha = disk.common.product_input(args.product_evidence, args.expected_source_head, args.expected_source_tree)
    original_product = json.loads(disk.common.read_file(args.product_evidence / 'source-before.json', disk.LOG_LIMIT))
    require(before['files'] == original_product['files'], 'ordinary product was built from different source bytes')
    bundle, probe = disk.bundle_input(args.bundle, args.expected_input_sha256)
    require((bundle['source_head'], bundle['source_tree']) == (args.expected_source_head, args.expected_source_tree),
            'frozen probe/image belong to another source tree')
    reference_sha = disk.reference_input(args.linux_reference, bundle, args.expected_input_sha256)
    positive_raw = disk.common.read_file(args.positive_guest / 'result.json', disk.LOG_LIMIT)
    positive = json.loads(positive_raw)
    serial = disk.common.read_pinned(args.positive_guest / 'serial.log', positive['serial_sha256'])
    require(positive['passed'] is True and positive['inputs_unchanged'] is True
            and positive['bundle_sha256'] == args.expected_input_sha256
            and positive['product_receipt_sha256'] == product_sha
            and positive['kernel_sha256'] == disk.sha(kernel), 'corrected-kernel disk reference is incomplete')
    require(disk.oracle.evaluate(serial, guest=True, negative=False, process_exit=positive['qemu_exit'],
                                 timed_out=positive['timed_out'], probe_bytes=len(probe))['passed'],
            'corrected-kernel raw observations did not pass')
    patch = disk.common.read_pinned(ROOT / PATCH, PATCH_SHA256, 16384)
    original = (ROOT / INODE).read_bytes()
    changed = mutation(original)
    (out / 'mutation.patch').write_bytes(patch)
    (out / 'inode-before.rs').write_bytes(original)
    (out / 'inode-after.rs').write_bytes(changed)
    source = args.source_worktree.absolute()
    require(not source.exists() and not source.is_symlink()
            and not source.is_relative_to(ROOT) and not source.is_relative_to(out),
            'negative source must be a fresh sibling worktree outside source and evidence')
    disk.run_logged(['git', 'worktree', 'add', '--detach', str(source), args.expected_source_head], out, 'worktree-create', cwd=ROOT)
    try:
        staged_before = disk.product.source_snapshot(source, args.expected_source_head, args.expected_source_tree)
        require(staged_before['files'] == before['files'], 'fresh worktree differs from reviewed source')
        disk.run_logged(['git', 'apply', '--check', str(out / 'mutation.patch')], out, 'patch-check', cwd=source)
        disk.run_logged(['git', 'apply', str(out / 'mutation.patch')], out, 'patch-apply', cwd=source)
        require((source / INODE).read_bytes() == changed, 'frozen patch postimage differs')
        changed_paths = subprocess.check_output(['git', 'diff', '--name-only'], cwd=source).decode().splitlines()
        require(changed_paths == [INODE], 'patch touched any path other than the one production helper')
        subprocess.run(['git', 'add', '--', INODE], cwd=source, check=True)
        tree = subprocess.check_output(['git', 'write-tree'], cwd=source).decode().strip()
        head = subprocess.check_output(['git', '-c', 'user.name=ExFAT qualification', '-c',
                                        'user.email=exfat-qualification@invalid.example',
                                        'commit-tree', tree, '-p', args.expected_source_head], cwd=source,
                                       input=b'Local cloud negative control: restore only synthesized ExFAT set-ID bits\n').decode().strip()
        subprocess.run(['git', 'update-ref', 'HEAD', head, args.expected_source_head], cwd=source, check=True)
        after = disk.product.source_snapshot(source, head, tree)
        verify_delta(staged_before, after, original, changed)
        save(out / 'negative-source-before.json', after)
        report.update(positive_source_head=args.expected_source_head, positive_source_tree=args.expected_source_tree,
                      negative_source_head=head, negative_source_tree=tree, negative_parent=args.expected_source_head,
                      mutation_path=INODE, mutation_patch_sha256=PATCH_SHA256,
                      positive_kernel_sha256=disk.sha(kernel), positive_guest_receipt_sha256=disk.sha(positive_raw))
        env = dict(os.environ)
        env['VDSO_LIBRARY_DIR'] = str(ROOT / 'support/build/out/linux-vdso')
        negative_product = out / 'ordinary-product'
        disk.run_logged([sys.executable, '-I', '-B', str(source / 'tests/kernel/control/run_queryabi_candidate_guest.py'),
                         '--expected-source-head', head, '--expected-source-tree', tree,
                         '--target-dir', str(args.target_dir.absolute()), '--output', str(negative_product)],
                        out, 'ordinary-negative-build-and-boot', timeout=3600, cwd=source, env=env)
        mutated_kernel, receipt_sha = disk.common.product_input(negative_product, head, tree)
        require(mutated_kernel != kernel, 'negative ELF is identical to the positive kernel')
        finished = disk.product.source_snapshot(source, head, tree)
        require(finished == after, 'negative build changed its tracked source inputs')
        save(out / 'negative-source-after-build.json', finished)
        guest_out = out / 'disk-guest'
        guest_out.mkdir(mode=0o700)
        guest_report = {'schema': 'a06.exfat-negative-guest.v1', 'passed': False, 'source_inputs': disk.source_inputs(),
                        'source_head': head, 'source_tree': tree}
        try:
            disk.run_disk_guest(args, guest_out, guest_report, bundle, probe, mutated_kernel,
                                receipt_sha, reference_sha, negative=True)
        finally:
            save(guest_out / 'result.json', guest_report)
        require(guest_report['passed'] is True, 'old behavior did not produce the required actual mode and exec observations')
        require(disk.product.source_snapshot(source, head, tree) == after, 'negative source changed during disk guest')
        report.update(negative_kernel_sha256=disk.sha(mutated_kernel), negative_product_receipt_sha256=receipt_sha,
                      negative_guest_receipt_sha256=disk.sha((guest_out / 'result.json').read_bytes()),
                      passed=True, negative_source_inputs_unchanged=True)
    finally:
        # No --force: retain a changed worktree for diagnosis instead of deleting
        # unknown source edits. All needed pre/postimages are in the evidence.
        disk.run_logged(['git', 'worktree', 'remove', str(source)], out, 'worktree-remove', cwd=ROOT)
        report['owned_worktree_removed'] = True
    final = disk.product.source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
    save(out / 'positive-source-after.json', final)
    require(final == before, 'negative profile changed original positive checkout')
    report['positive_source_inputs_unchanged'] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'linux-reference', 'product-evidence', 'positive-guest', 'a01-initramfs',
                 'source-worktree', 'target-dir', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('expected-input-sha256', 'expected-source-head', 'expected-source-tree'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    parser.add_argument('--qemu', default='qemu-system-x86_64')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink() and not out.is_relative_to(ROOT), 'output must be new and outside source')
    require(1 <= args.timeout <= 180, 'timeout must be 1..180 seconds')
    out.mkdir(parents=True, mode=0o700)
    report = {'schema': 'a06.exfat-one-line-negative.v1', 'passed': False,
              'runner_sha256': disk.sha(Path(__file__).read_bytes())}
    try:
        run(args, out, report)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
    save(out / 'result.json', report)
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
