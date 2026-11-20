#!/usr/bin/python3
"""Create only K0b source postimages against exact reviewed K0a inputs."""
from pathlib import Path
import difflib
import hashlib
import json

HERE = Path(__file__).resolve().parent
K0A = HERE.parent / 'p4_private_loop_k0a'
FILES = {
    'include/linux/fs_struct.h': (K0A/'base/linux-6.18.64/include/linux/fs_struct.h',
        1066, 'ec9afb74c3321719d044af007b900f8e72a09f496246cfd74d92476deada1aaf'),
    'fs/fs_struct.c': (K0A/'base/linux-6.18.64/fs/fs_struct.c',
        3238, 'dfb27ae16982f252124f708339b5989b9e9bdc5a62bccef1aefe68538ff22133'),
    'block/p4_private_loop_actor.c': (K0A/'candidate/block/p4_private_loop_actor.c',
        6103, '910c7ef5480e2b0cdf8ba3cd0676698dfa0da1445537167275455df4de353641'),
    'include/linux/p4_private_loop_actor.h': (K0A/'candidate/include/linux/p4_private_loop_actor.h',
        2217, '4728b7357734021980ce29253b1f1a677fade7594e5ef5e068a4ca28c73c696c'),
}


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def create(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as output:
        output.write(raw)


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    original = {}
    for name, (source, size, sha) in FILES.items():
        raw = source.read_bytes()
        assert pin(raw) == {'bytes': size, 'sha256': sha}
        original[name] = raw.decode()
    result = dict(original)
    name = 'include/linux/fs_struct.h'
    result[name] = replace_once(result[name], '#include <linux/path.h>\n',
        '#include <linux/path.h>\n#include <linux/refcount.h>\n')
    result[name] = replace_once(result[name], 'struct fs_struct {\n\tint users;\n',
        '''struct fs_struct {
	int users;
	/* One aggregate owner reference while the original users discipline
	 * owns this fs (also the initial unpublished-copy reference), plus
	 * independent observers. Never use refs for shared-fs access checks.
	 */
	refcount_t refs;
''')
    result[name] = replace_once(result[name], 'extern void free_fs_struct(struct fs_struct *);\n',
        '''/* Drop the original aggregate ownership, after its last users slot
 * or when discarding an unpublished copy. This may leave observers alive.
 */
extern void free_fs_struct(struct fs_struct *);

/* Lifetime only: neither function reads or changes users or in_exec.
 * get requires a reference the caller already owns, or task_lock followed
 * by fs->seq with an attached, positively counted task fs. No resurrection.
 * Final put releases paths and may sleep; never call it under a spinlock.
 */
extern void get_fs_struct_ref(struct fs_struct *);
extern void put_fs_struct_ref(struct fs_struct *);
''')
    name = 'fs/fs_struct.c'
    result[name] = replace_once(result[name], '''void free_fs_struct(struct fs_struct *fs)
{
	path_put(&fs->root);
	path_put(&fs->pwd);
	kmem_cache_free(fs_cachep, fs);
}
''', '''void get_fs_struct_ref(struct fs_struct *fs)
{
	/* The caller already owns a lifetime reference or holds the attached
	 * task/fs locks. Do not acquire a reference from an unowned pointer.
	 */
	refcount_inc(&fs->refs);
}

void put_fs_struct_ref(struct fs_struct *fs)
{
	if (!refcount_dec_and_test(&fs->refs))
		return;
	path_put(&fs->root);
	path_put(&fs->pwd);
	kmem_cache_free(fs_cachep, fs);
}

void free_fs_struct(struct fs_struct *fs)
{
	/* All original callers retire the users aggregate exactly once, or
	 * discard a copy that was never published to another owner.
	 */
	put_fs_struct_ref(fs);
}
''')
    result[name] = replace_once(result[name], '\t\tfs->users = 1;\n',
        '\t\tfs->users = 1;\n\t\trefcount_set(&fs->refs, 1);\n')
    result[name] = replace_once(result[name], '\t.users\t\t= 1,\n',
        '\t.users\t\t= 1,\n\t.refs\t\t= REFCOUNT_INIT(1),\n')
    name = 'block/p4_private_loop_actor.c'
    result[name] = replace_once(result[name],
        ' * graph stayed unchanged.  K0b/K1 must supply that independent graph binding\n',
        ' * graph stayed unchanged. Later stages must supply independent graph binding\n')
    result[name] = replace_once(result[name], '''/*
 * One counted fs users reference prevents pointer ABA after unshare/exit.
 * The existing 6.18.64 fs_struct users discipline is task_lock -> fs->seq.
 * Releasing the final fs and path references happens outside those locks.
 * This reference is visible to shared-fs/exec/unshare decisions; retaining it
 * is not behaviorally transparent and cannot be treated as a live lease.
 */
static void p4_private_loop_fs_put(struct fs_struct *fs)
{
	bool destroy;

	read_seqlock_excl(&fs->seq);
	destroy = !--fs->users;
	read_sequnlock_excl(&fs->seq);
	if (destroy)
		free_fs_struct(fs);
}

''', '''/*
 * An independent fs lifetime reference prevents pointer ABA after unshare or
 * exit without adding a users slot or changing shared-fs/exec decisions.
 * Capture takes it under task_lock -> fs->seq while a counted task owns fs.
 * Final release happens outside those locks and may release path custody.
 * This is still only retained identity, never an execution or access lease.
 */
''')
    result[name] = replace_once(result[name], '\t\tp4_private_loop_fs_put(actor->fs);\n',
        '\t\tput_fs_struct_ref(actor->fs);\n')
    result[name] = replace_once(result[name], '\tfs->users++;\n',
        '\tget_fs_struct_ref(fs);\n')
    result[name] = replace_once(result[name], '\tif (fs->users >= 2 && !fs->in_exec &&\n',
        '\tif (fs->users >= 1 && !fs->in_exec &&\n')
    name = 'include/linux/p4_private_loop_actor.h'
    result[name] = replace_once(result[name],
        ''' * Its counted fs reference affects shared-fs/exec/unshare decisions. This is
 * deliberate lifetime custody, not an observationally transparent monitor.
''', ''' * Its independent fs lifetime reference does not add a users slot or change
 * shared-fs/exec/unshare predicates. It still retains the fs allocation and
 * its paths, and must not be mistaken for a live execution or access lease.
''')
    patch = []; records = []
    for name in FILES:
        before = original[name].encode(); after = result[name].encode()
        create(HERE/'base'/name, before)
        create(HERE/'candidate'/name, after)
        patch.extend(difflib.unified_diff(original[name].splitlines(keepends=True),
                     result[name].splitlines(keepends=True), 'a/'+name, 'b/'+name))
        records.append({'path': name, 'before': pin(before), 'after': pin(after)})
    patch = ''.join(patch).encode(); create(HERE/'K0b.patch', patch)
    audit = HERE/'FIXED-FS-LIFETIME-AUDIT.json'
    assert pin(audit.read_bytes()) == {'bytes': 89735,
        'sha256': '3e50402974edc061da06e8eff21dc0f8a12b648d8b5b384c06ed0da182586f82'}
    manifest = {'schema': 'p4-k0b-independent-fs-lifetime-source-v1',
        'base_K0a_commit': '0bf19546e570a80247a5982d292de463cf0f4496',
        'exact_linux_version': '6.18.64', 'files': records, 'patch': pin(patch),
        'fixed_complete_tree_audit': pin(audit.read_bytes()),
        'existing_grant_source_unchanged': {'path': 'kernel/p4_guest_mntns.c', 'bytes': 11777,
            'sha256': '9807e3b53684b59796e73c33bcac78bdb9e81a3f5ea886d2b6c39866e6f4efcc'},
        'new_userspace_API': False, 'device_operations': 0, 'configuration_changed': False,
        'K0a_original_tree_modified': False, 'kernel_compiled': False, 'kernel_installed': False,
        'kernel_loaded': False, 'VM_started': False, 'Android_started': False,
        'live_actor_or_private_loop_issued': False, 'runtime_qualified': False, 'production_ready': False}
    create(HERE/'MANIFEST.json', (json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode())
    print(json.dumps({'patch':pin(patch),'files':records,'compiler_executed':False}))


if __name__ == '__main__':
    main()
