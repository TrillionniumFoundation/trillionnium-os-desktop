#!/usr/bin/env python3
"""Check exact K0c inheritance and original normal loop semantics; no kernel run."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
K0C = ROOT.parent/'p4_private_loop_k0c'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    manifest = json.loads((ROOT/'MANIFEST.json').read_bytes())
    rows = manifest['files']
    for row in rows:
        assert pin((ROOT/'candidate'/row['path']).read_bytes()) == row['after']
        if row['before']:
            before = (ROOT/'base'/row['path']).read_bytes()
            assert before == (K0C/'candidate'/row['path']).read_bytes()
            assert pin(before) == row['before']
    for row in manifest['unchanged_inherited_files']:
        raw = (ROOT/'candidate'/row['path']).read_bytes()
        assert raw == (K0C/'candidate'/row['path']).read_bytes()
        assert pin(raw) == {'bytes': row['bytes'], 'sha256': row['sha256']}
    patch = (ROOT/'K1a.patch').read_bytes()
    assert pin(patch) == manifest['patch']
    commands = []
    with tempfile.TemporaryDirectory(prefix='p4-k1a-source-') as directory:
        temp = Path(directory)
        for row in rows:
            if row['before']:
                path = temp/row['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT/'base'/row['path']).read_bytes())
        for options in (['--check'], [], ['--reverse', '--check'], ['--reverse']):
            argv = ['/usr/bin/git', 'apply', *options, str(ROOT/'K1a.patch')]
            result = subprocess.run(argv, cwd=temp, capture_output=True, check=False)
            commands.append({'argv': argv, 'exit_code': result.returncode,
                             'stdout': result.stdout.decode(), 'stderr': result.stderr.decode()})
            assert result.returncode == 0, commands[-1]
            if not options:
                for row in rows:
                    assert (temp/row['path']).read_bytes() == (ROOT/'candidate'/row['path']).read_bytes()
        for row in rows:
            if row['before']:
                assert (temp/row['path']).read_bytes() == (ROOT/'base'/row['path']).read_bytes()
            else:
                assert not (temp/row['path']).exists()

    # Exact inverse, rather than a selected-function smoke check: every byte
    # outside the new allocator and the same-body cleanup extraction is old.
    body = (ROOT/'candidate/drivers/block/loop.c').read_text()
    addition = (ROOT/'additions/drivers/block/private_loop_allocation.inc').read_text()
    replacements = [
        (addition, ''),
        ('#include <linux/p4_private_loop_realm.h>\n#include <linux/backing-dev.h>\n', ''),
        ('static void lo_free_disk(struct gendisk *disk)\n{\n\tloop_free_device(disk->private_data);\n}\n\n', ''),
        ('static void loop_free_device(struct loop_device *lo)\n{\n',
         'static void lo_free_disk(struct gendisk *disk)\n{\n\tstruct loop_device *lo = disk->private_data;\n\n'),
    ]
    for new, old in replacements:
        assert body.count(new) == 1
        body = body.replace(new, old)
    assert body.encode() == (ROOT/'base/drivers/block/loop.c').read_bytes()

    out = {
        'schema': 'p4-k1a-closed-allocation-source-preservation-v1',
        'state': 'PASSED_FINITE_SOURCE_PRESERVATION',
        'new_or_changed_postimages': len(rows),
        'unchanged_K0c_K0b_postimages': len(manifest['unchanged_inherited_files']),
        'whole_patch_forward_and_reverse_exact': True,
        'patch_apply_commands': commands,
        'whole_loop_body_inverse_exact_K0c': True,
        'normal_loop_add_remove_configure_probe_work_and_release_bodies_unchanged': True,
        'original_native_free_disk_cleanup_statements_preserved': True,
        'block_file_private_data_holder_assignments_changed': False,
        'K0c_closed_entry_gates_changed': False,
        'kernel_runtime_tests_executed': False,
        'real_control_or_block_OFD_created': False,
        'private_device_published': False,
        'K1_complete': False,
        'runtime_qualified': False,
        'production_ready': False,
    }
    raw = (json.dumps(out, sort_keys=True, indent=2)+'\n').encode()
    (ROOT/'SOURCE-CONTROLS.json').write_bytes(raw)
    print(json.dumps({'state': out['state'], **pin(raw)}))


if __name__ == '__main__':
    main()
