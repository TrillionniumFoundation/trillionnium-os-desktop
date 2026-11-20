"""Assemble one isolated K0a kernel patch; no compiler or device operations."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'base/linux-6.18.64'
CANDIDATE = ROOT / 'candidate'

def sha(body):
    return hashlib.sha256(body).hexdigest()

def save_exact(path, body):
    if path.exists():
        assert path.read_bytes() == body, 'Existing candidate differs: ' + str(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

def main():
    inputs = json.loads((ROOT / 'INPUTS.json').read_bytes())
    kernel = inputs['kernel_root'] + '/'
    for item in inputs['files']:
        relative = item['path'].removeprefix(kernel)
        assert relative != item['path']
        body = (BASE / relative).read_bytes()
        assert len(body) == item['size'] and sha(body) == item['sha256'], relative
    old_kconfig = (BASE / 'block/Kconfig').read_bytes()
    anchor = b'source "block/Kconfig.iosched"\n'
    assert old_kconfig.count(anchor) == 1
    addition = b'''config P4_PRIVATE_LOOP_ACTOR
\tbool "Pocket4 private-loop actor reference foundation"
\tdepends on EXPERT && USER_NS && PID_NS
\tdefault n
\thelp
\t  Build an internal exact-thread context reference type for the
\t  future private-loop implementation. This adds no userspace API,
\t  device allocator, loop access permission or namespace mutation.
\t  It does not isolate ordinary host loop devices. All block access,
\t  mount-graph and IO lifetime gates remain separate prerequisites.

\t  Say N unless developing the separately reviewed private-loop
\t  implementation against this exact kernel source.

'''
    new_kconfig = old_kconfig.replace(anchor, addition + anchor)
    assert new_kconfig.replace(addition, b'') == old_kconfig
    old_makefile = (BASE / 'block/Makefile').read_bytes()
    rule = b'obj-$(CONFIG_P4_PRIVATE_LOOP_ACTOR) += p4_private_loop_actor.o\n'
    assert b'P4_PRIVATE_LOOP_ACTOR' not in old_makefile
    new_makefile = old_makefile + b'\n' + rule
    save_exact(CANDIDATE / 'block/Kconfig', new_kconfig)
    save_exact(CANDIDATE / 'block/Makefile', new_makefile)
    rows = []
    patch = []
    for relative, before in [('block/Kconfig', old_kconfig), ('block/Makefile', old_makefile),
                             ('block/p4_private_loop_actor.c', None),
                             ('include/linux/p4_private_loop_actor.h', None)]:
        after = (CANDIDATE / relative).read_bytes()
        rows.append({'path': relative, 'before': None if before is None else {'bytes': len(before), 'sha256': sha(before)},
                     'after': {'bytes': len(after), 'sha256': sha(after)}})
        patch.extend(difflib.unified_diff([] if before is None else before.decode().splitlines(True),
            after.decode().splitlines(True), fromfile='/dev/null' if before is None else 'a/' + relative,
            tofile='b/' + relative))
    raw_patch = ''.join(patch).encode()
    save_exact(ROOT / 'K0a.patch', raw_patch)
    manifest = {'schema': 'p4-private-loop-k0a-source-manifest-v1',
        'kernel_release': inputs['kernel_release'], 'files': rows,
        'patch': {'bytes': len(raw_patch), 'sha256': sha(raw_patch)},
        'inputs': {'bytes': len((ROOT / 'INPUTS.json').read_bytes()), 'sha256': sha((ROOT / 'INPUTS.json').read_bytes())},
        'build_default_enabled': False, 'userspace_interface_added': False,
        'ordinary_block_or_loop_entry_points_changed': False,
        'existing_namespace_grant_changed': False, 'device_allocator_added': False,
        'rust_original_target_issuer_constructible': False,
        'complete_private_loop_isolation_implemented': False,
        'target_kernel_compiled': False, 'kernel_loaded': False,
        'kernel_runtime_tests_executed': False, 'Android_started': False,
        'runtime_qualified': False, 'production_ready': False}
    save_exact(ROOT / 'MANIFEST.json', (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps(manifest, indent=2, sort_keys=True))

if __name__ == '__main__':
    main()
