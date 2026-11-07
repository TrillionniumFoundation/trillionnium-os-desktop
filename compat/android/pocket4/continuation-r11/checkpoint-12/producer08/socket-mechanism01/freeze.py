#!/usr/bin/env python3
"""Freeze a reviewed-source candidate; never submit or execute a namespace."""
import ast
import base64
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266/lmkd-recovery-20261105-01')
WORK = BASE / 'socket-projection-mechanism-work-01'
OUT = BASE / 'socket-projection-mechanism-freeze-01'
EVIDENCE = Path('/workspace/scratch/94990735b266/root-recovery-20261104-02/evidence')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    profile = json.loads((WORK / 'profile.json').read_bytes())
    probe = (WORK / 'probe.c').read_bytes()
    assert sha(probe) == profile['probe_sha256']
    assert ('#define FIXTURE_NONCE "' + profile['nonce'] + '"').encode() in probe
    source_root = BASE / 'owner07-normal03-diagnostic-freeze-01'
    plan_raw = (source_root / 'plan.json').read_bytes()
    assert sha(plan_raw) == '650ab0428bd88d9b5ba2217cbafd9c718e780eaf696c90fb567296c850ba2baa'
    plan = json.loads(plan_raw)
    support = (source_root / 'source/pinned_support.py').read_bytes()
    support_manifest = json.loads((source_root / 'manifest.json').read_bytes())
    expected_support = next(x for x in support_manifest['files'] if x['path'] == 'source/pinned_support.py')
    assert sha(support) == expected_support['sha256'] and len(support) == expected_support['bytes']
    guard = (BASE / 'init-project-diagnostic-build-freeze-03/resource_guard.py').read_bytes()
    assert sha(guard) == '4192389de077c41dc395d9f5b083d10372272c45aacb053697d3c24e94a25961'
    build_raw = (EVIDENCE / 'init-project-diagnostic-build03/build-result.json').read_bytes()
    assert sha(build_raw) == '15c122a42f1c0d81ff4d473925184a8f7aedb6babc84d9fa4036ae6378b44d02'
    build = json.loads(build_raw); assert build['success'] is True
    runtime_raw = (EVIDENCE / 'owner07-normal03-runtime01/runtime-result.json').read_bytes()
    assert sha(runtime_raw) == 'b836404cc5011662239706418921758a4380b9c21d41534783f7fa64c8dfda7e'
    runtime = json.loads(runtime_raw)
    audit = runtime['actor_result']['latest_status']['relay_lifecycle']
    init = next(x['detail']['init'] for x in audit['records'] if x['detail']['event'] == 'init_hello')
    producer_user = audit['producer']['namespaces'][4]
    assert producer_user == init['namespaces'][4] == {'device': 5, 'inode': 4026531837}
    assert audit['producer']['namespaces'][2] != init['namespaces'][2]
    compat = next(x for x in plan['base']['records'] if x['sha256'] ==
                  'b4da6c85703e5f0dac88c039438d8836a4123c97655d14130e68828295d3fb50')
    cfg = {
        'root': profile['root'], 'nonce': profile['nonce'], 'main': plan['main'],
        'normal03_runtime_sha256': sha(runtime_raw),
        'actual_normal03_user_namespace': [producer_user['device'], producer_user['inode']],
        'tools_sha256': {name: plan['tools_sha256'][name] for name in ('/usr/bin/python3', '/usr/bin/systemctl')},
        'host_tools': {'cc': build['host_tools_before']['/usr/bin/cc'],
                       'readelf': build['host_tools_before']['/usr/bin/readelf']},
        'compat': {'path': compat['frozen'], 'sha256': compat['sha256'], 'bytes': compat['bytes']},
        'sources': {},
    }
    members = {'source/probe.c': probe, 'source/pinned_support.py': support,
               'source/resource_guard.py': guard}
    for name, raw in list(members.items()):
        cfg['sources'][Path(name).name] = {'bytes': len(raw), 'sha256': sha(raw),
                                          'base64': base64.b64encode(raw).decode()}
    template = (WORK / 'controller-template.py').read_bytes()
    assert template.count(b'CFG = None') == 1
    stdin = template.replace(b'CFG = None', ('CFG = ' + repr(cfg)).encode())
    parsed = ast.parse(stdin); compile(stdin, '<frozen owned mount mechanism controller>', 'exec')
    assignments = [n for n in parsed.body if isinstance(n, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == 'CFG' for t in n.targets)]
    assert len(assignments) == 1 and ast.literal_eval(assignments[0].value) == cfg
    original = ast.parse(template)
    assignments[0].value = ast.Constant(value=None)
    assert ast.dump(parsed) == ast.dump(original)
    request = {'host': 'pocket4', 'executable': '/usr/bin/sudo',
        'args': ['-n', '/usr/bin/python3', '-I', '-B', '-'], 'stdin': stdin.decode(), 'cwd': '/',
        'timeout_seconds': 120, 'memory_max_bytes': 536870912, 'cpu_quota_percent': 100, 'nice': 10,
        'idempotency_key': 'p4-owned-socket-projection-mechanism01-' + sha(stdin)[:16]}
    request_raw = pretty(request)
    binding = {'schema': 1, 'source_packet_count': 3, 'source_packet_pins_exact': True,
        'stdin_AST_equals_template_with_single_literal_CFG': True, 'request_stdin_exact': True,
        'actual_normal03_user_namespace_shared_by_producer_and_init': True,
        'actual_normal03_mount_namespaces_differ': True, 'actual_compile_tool_pins_used': True,
        'MainFence_and_resource_guard_copied_unchanged': True, 'namespace_probe_executed': False,
        'Android_constructor_qualified': False, 'production_qualified': False,
        'request_sha256': sha(request_raw), 'stdin_sha256': sha(stdin), 'key': request['idempotency_key']}
    topology = {'schema': 1, 'actual_runtime_sha256': sha(runtime_raw), 'user_namespace_index': 4,
        'mount_namespace_index': 2, 'namespace_order': ['pid', 'pid_for_children', 'mnt', 'cgroup', 'user',
            'net', 'ipc', 'uts', 'time', 'time_for_children'],
        'producer_namespaces': audit['producer']['namespaces'], 'actual_init_namespaces': init['namespaces'],
        'scope': 'Actual namespace identities only; host control PASS cannot qualify the Bionic constructor.'}
    readme = '''# Owned socket projection kernel mechanism control

NORMAL03 reached the authenticated init HELLO, broker READY and PROJECT send,
then its diagnostic constructor failed at `project-bind-mount` with errno 22.
Its original result remains failed. This new request creates one fresh private
host fixture, with a second private mount namespace in its owned child.
The producer and actual NORMAL03 init share user namespace dev 5 / inode
4026531837; their mount namespaces differ. This control records and requires
that same user namespace, with two distinct owned mount namespaces.

The source socket is a new, owned 1069:1069 mode-0600 inode on a private 1 MiB
tmpfs. The child closes inherited source handles and receives exactly two
SCM_RIGHTS descriptors. Three observations must hold: a raw foreign attached
O_PATH source fails ordinary bind with EINVAL; reopening the identical source
through the child's own mount namespace binds successfully; a detached mount
cloned by its host owner moves onto the child's exact new held target. The
post-operation inode, ownership, mode and statx mount IDs are checked.

All mounts happen after unshare and recursive private propagation. There is no
Android, network namespace creation, production endpoint, pressure allocation,
or installed-file mutation. The owned C parent/child have parent-death signals,
pidfd/precise-child wait cleanup, and explicit private tmpfs unmount. The Python
controller remains outside those namespaces, retains the original MainFence,
and uses the unchanged held own-cgroup resource guard at CPU 1 / 512 MiB.
It binds actual compiler/readelf pins from successful build03, compares complete
preflight/actual MD sets and source inputs, and requires exact waits. A bounded
readelf check reports whether the already-pinned compat artifact exports mount
or syscall-related entry points; it is not source provenance for that artifact.

Upstream kernel source supports the mechanism hypothesis; it does not bind the
Pocket4 kernel binary. In Linux v6.17, ordinary bind and child-side open_tree
cloning use may_copy_tree, whereas move_mount accepts a detached anonymous root
and validates its target namespace. Source:
https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux.git/+/refs/tags/v6.17/fs/namespace.c

No namespace probe was run when freezing this source. The actual request must
be reviewed and scheduled by the root coordinator once. Even if it passes,
the paired Rust producer and Android constructor still require matching builds
and a fresh real init canary. This control never grants production readiness.
'''
    members.update({'controller-template.py': template, 'stdin.py': stdin, 'request.json': request_raw,
        'binding-result.json': pretty(binding), 'topology-reference.json': pretty(topology),
        'profile.json': (WORK / 'profile.json').read_bytes(), 'README.md': readme.encode(),
        'freeze.py': Path(__file__).read_bytes(), 'local-compile02.json': (WORK / 'local-compile02.json').read_bytes(),
        'local-compile02.stdout': (WORK / 'local-compile02.stdout').read_bytes(),
        'local-compile02.stderr': (WORK / 'local-compile02.stderr').read_bytes(),
        'probe-userns-delta.diff': (WORK / 'probe-userns-delta.diff').read_bytes(),
        'preimage/probe-source-01.c': (WORK / 'probe-source-01.c').read_bytes(),
        'preimage/local-compile.json': (WORK / 'local-compile.json').read_bytes()})
    OUT.mkdir(exist_ok=False)
    rows = []
    for name, raw in members.items():
        raw.decode('utf-8'); path = OUT / name; path.parent.mkdir(exist_ok=True, parents=True); path.write_bytes(raw)
        rows.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw)})
    manifest = pretty({'schema': 1, 'kind': 'owned-socket-projection-mechanism01-source-freeze',
                       'namespace_executed': False, 'files': rows})
    (OUT / 'manifest.json').write_bytes(manifest)
    print(json.dumps({'root': str(OUT), 'manifest_sha256': sha(manifest),
                      'request_bytes': len(request_raw), 'stdin_bytes': len(stdin), **binding}, indent=2))


if __name__ == '__main__':
    main()
