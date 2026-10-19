#!/usr/bin/env python3
"""Record the source review and independently check the author's source identities."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import subprocess

ROOT = Path('/workspace/scratch/499c7902de8e/r12-g1c')
OUT = Path(__file__).resolve().parent
BASE = '7c675e1d3efe46587edeebe14bd90ac1a842ffbf'
AUTHOR = OUT.parent / 'g1c-lifecycle/source-manifest.json'
EXPECTED_AUTHOR_SHA = 'b763fd851286823f0c1cc2c59ce32763cc4b4270c5179904f62c9bdd1254125c'

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

def digest(path, data):
    return {'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'git_blob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}

author_bytes = AUTHOR.read_bytes()
assert hashlib.sha256(author_bytes).hexdigest() == EXPECTED_AUTHOR_SHA
author = json.loads(author_bytes)
sources = []
for item in author['files']:
    raw = (ROOT / item['path']).read_bytes()
    actual = digest(item['path'], raw)
    actual['ktests'] = re.findall(r'#\[ktest\]\s*fn\s+(\w+)', raw.decode())
    actual['matches_author_manifest'] = all(actual[k] == item[k] for k in ('bytes', 'sha256', 'git_blob', 'ktests'))
    assert actual['matches_author_manifest'], item['path']
    sources.append(actual)

additional = []
for name in (
    'tests/kernel/control/queryabi_candidate_guest.c',
    'tests/kernel/control/run_queryabi_candidate_guest.py',
    'tests/kernel/control/test_queryabi_candidate_runner.py',
    'tests/spec/test_a05_capspace_nonce.py',
    'tests/kernel/control/README.md',
):
    additional.append(digest(name, (ROOT / name).read_bytes()))

preserved = []
for name in (
    'kernel/asterinas/kernel/core/src/process/clone.rs',
    'kernel/asterinas/kernel/core/src/process/task_set.rs',
    'kernel/asterinas/kernel/core/src/process/posix_thread/mod.rs',
    'kernel/asterinas/kernel/core/src/process/posix_thread/builder.rs',
    'kernel/asterinas/kernel/core/src/process/process_vm/mod.rs',
    'kernel/asterinas/kernel/core/src/process/program_loader/mod.rs',
    'kernel/asterinas/kernel/core/src/process/program_loader/elf/load_elf.rs',
    'kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native.rs',
    'kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs',
    'kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/pid/task/mem.rs',
    'kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/pid/task/maps.rs',
    'kernel/asterinas/kernel/core/src/thread/mod.rs',
    'kernel/asterinas/kernel/core/src/syscall/execve.rs',
    'kernel/asterinas/kernel/core/src/prelude.rs',
    'kernel/asterinas/ostd/src/task/mod.rs',
    'tests/kernel/control/queryabi_guest.c',
    'tests/kernel/control/run_queryabi_guest.py',
):
    raw = (ROOT / name).read_bytes()
    item = digest(name, raw)
    item['matches_base'] = raw == git('show', BASE + ':' + name)
    assert item['matches_base'], name
    preserved.append(item)

diff_check = subprocess.run(['git', '-C', str(ROOT), 'diff', '--check'], capture_output=True)
ktests = [{'path': item['path'], 'name': name} for item in sources for name in item['ktests']]
assert len(ktests) == 18

review = {
    'schema_version': 1,
    'kind': 'independent_g1c_lifecycle_source_review',
    'reviewer': '/root/g1c_review',
    'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'base_commit': BASE,
    'base_tree': git('rev-parse', BASE + '^{tree}').decode().strip(),
    'candidate_identity': 'Working candidate bytes listed below; not yet a new committed or executed product qualification.',
    'author_manifest': {'path': 'g1c-lifecycle/source-manifest.json', 'bytes': len(author_bytes),
                        'sha256': EXPECTED_AUTHOR_SHA},
    'decision': 'No blocking source defect found in the reviewed lifecycle slice. Suitable for fixed-source complete build/runtime acceptance; this receipt does not approve an unexecuted product or enable new HOS2 operations.',
    'blocking_findings': [],
    'resolved_design_findings': [
        {'id': 'R1', 'status': 'implemented', 'evidence': 'with_initial_image takes Process VMAR -> TaskSet -> image. Process::run and accepted exec/exit use TaskSet -> image. Image methods acquire no outer lock. Existing procfs VMAR -> main_thread/TaskSet remains unchanged.'},
        {'id': 'R2', 'status': 'implemented_with_bounded_origin_proof', 'evidence': 'PreparedInitialProcess is private and non-Clone, constructed only after create_init_task succeeds. The same VmarHandle is moved into PosixThreadBuilder; token retains the matching Arc<Vmar>, Arc<Task> and Arc<Process>. with_initial_image checks Process VMAR, exact sole main Task, Task weak Process backlink and live TaskSet. FirstRun is canonical under the image lock; both prepared and ordinary Process start claim it before enqueue.'},
        {'id': 'R3', 'status': 'implemented', 'evidence': 'session and check_session reject Closing/Closed. begin_close cannot reopen Closed; close is idempotent. commit_exec accepts only Closing, closes before checked epoch increment, clears nonce only for a new successful epoch and preserves first_run. Nonce allocator and epoch overflow are checked and terminal.'},
        {'id': 'R4', 'status': 'preserved', 'evidence': 'Device still advertises QueryAbi only, max response payload 48 and no features. All four recognized resource operations remain EOPNOTSUPP; no resource grant, handle table, delivery table or budget ledger was introduced.'}
    ],
    'reviewed_call_paths': [
        {'id': 'C1', 'property': 'Failed exec before acceptance preserves the image',
         'reasoning': 'sys_execve first resolves/opens the supplied path. do_execve then reads argv/envp, resolves program/credentials and fully loads a new VMAR before TaskSet.start_execve. Every ? before that point leaves the old image state untouched. Existing EAGAIN when another exec/exit already owns TaskSet does not close a separate live image.'},
        {'id': 'C2', 'property': 'Irreversible exec closes before sibling signalling',
         'reasoning': 'Immediately after start_execve, begin_hepta_image_close runs under TaskSet before sigkill_other_threads. Success through do_execve_no_return is required for commit_hepta_exec_image; any failure or overflow closes before enqueuing SIGKILL. No failed path runs commit-new-image after close.'},
        {'id': 'C3', 'property': 'Exit closure precedes resource teardown',
         'reasoning': 'Accepted exit_group sets the group flag and closes image admission before sibling signalling. A non-last ordinary exit does not close. remove_exited=true closes under TaskSet before dropping files/thread VMAR; exit_process completes Closed before Process VMAR removal. Actual syscall body was reviewed; current unit fixtures do not execute a last-thread exit syscall.'},
        {'id': 'C4', 'property': 'Ordinary fork first-run expect is an internal invariant',
         'reasoning': 'Current only production Process::run call is clone_child after a fresh Process::new, sole Task insertion, cgroup assignment and membership-lock release. The new Task has not run. Merely publishing the PID and allowing signals does not execute that Task or mutate its Process first_run/exec/exit lifecycle. Prepared init uses a separate consuming path. Running, prepared or closed Process cannot silently enqueue through Process::run.'},
        {'id': 'C5', 'property': 'Prepared validation and failure do not publish an orphan',
         'reasoning': 'resume consumes/validates before bootstrap PID/session registration. No fallible preparation remains after registration. Failure consumes self and Drop cancels only the matching still-prepared key. Success sets consumed=true and Started before enqueue. All process locks are released before registration or Task.run.'},
        {'id': 'C6', 'property': 'Preparation binds exact original objects',
         'reasoning': 'Exact Process allocation is checked through the Task Weak backlink; Task is the sole main member, not exited; Process retains the exact VMAR Arc. Private create_init passed that same VmarHandle into create_init_task and builder. The unstarted Task ThreadLocal is not arbitrarily inspected: same-VMAR Task origin is proved by this restricted factory call path. An Arc<Vmar> pin is used, not an extra VmarHandle.'},
        {'id': 'C7', 'property': 'Accounting survives image closure',
         'reasoning': 'No new image method acquires CPU membership/runqueue/bandwidth locks, drops a CpuCgroupLease, resets cumulative/debt/revision or substitutes a new owner. Original CpuCgroupLease, clone membership handling, native CPU state and scheduler source bytes are unchanged. test_util extends actual unstarted Task construction; its temporary VmarHandle is dropped on return, leaving one handle per created Task.'},
        {'id': 'C8', 'property': 'Device retains exact Process and complete image key',
         'reasoning': 'Per-open file stores Weak<Process> and ProcessImageKey. check_session retains Arc equality before phase/epoch/nonce validation on the canonical image lock. Passing an fd or sharing credentials is not authority. The check still precedes user copies; admitted QueryAbi-only requests can finish without resource effects. Future resource operations require post-copy canonical owner admission.'}
    ],
    'guest_source_review': {
        'status': 'source reviewed; no guest executed by this reviewer',
        'cases': ['SYS_execve valid probe pathname with argv pointer 1 strictly requires EFAULT; original and fresh fds keep complete boot/space identity.',
                  'SYS_execve nonexistent pathname strictly requires ENOENT; original and fresh fds retain identity.',
                  'pthread worker checks same PID and distinct TID; shared old fd and fresh open match full 16-byte boot and CapSpace.',
                  'pthread_join provides completion synchronization; surviving main fd and fresh open remain valid after non-last exit.',
                  'Original successful exec child and original source remain unchanged, with candidate early-return preventing repeated added markers.',
                  'Runner requires all old markers plus four lifecycle and four disabled-operation markers exactly once and in the applicable order; final process and QEMU checks remain.'],
        'limits': ['EFAULT and ENOENT cover pre-boundary failures, not fatal post-boundary exec.',
                   'New guest cases also pass the old QueryAbi implementation and are compatibility/non-regression checks; actual new lifecycle state logic must be exercised by the new kernel cases and new product build.',
                   'Guest non-last-thread survival is observable; no successful ioctl after final Process exit is claimed.']
    },
    'kernel_test_source_inventory': ktests,
    'kernel_test_scope': '18 newly declared ktests, nine image-state and nine prepared-init. They allocate actual Process/Task/VMAR objects, invoke production lifecycle methods and mutate boundary setup in tests. No fixture Task is scheduled and no fixture executable is loaded. The prepared_old_epoch test deliberately simulates a lifecycle replacement on an unstarted fixture; it is not real exec evidence.',
    'source_files': sources,
    'additional_reviewed_files': additional,
    'preserved_call_path_inputs': preserved,
    'diff_whitespace_check': {'exit_code': diff_check.returncode,
                              'stdout': diff_check.stdout.decode(), 'stderr': diff_check.stderr.decode()},
    'next_positive_slice': 'Use design-review-base7c675e1d.json for bounded immutable static-image and alien-write requirements. Those are future ReadUsage prerequisites and do not block this explicitly QueryAbi-only source slice.',
    'activities': {'product_source_edits': 0, 'rust_compilations': 0, 'product_tests': 0,
                   'runtime_executions': 0, 'toolchain_installs': 0, 'remote_writes': 0},
    'not_qualified_here': ['authenticated final executable identity', 'native ReadUsage/InstallBudget/QueryDelivery/RetireThrough',
                           'canonical resource revocation or cross-CPU admission', 'new product runtime result',
                           'Hepta persistent K/D effects', 'complete SMP or physical-device behavior']
}
assert diff_check.returncode == 0
output = OUT / 'implementation-review-v1.json'
output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'path': str(output), 'bytes': output.stat().st_size,
                  'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                  'source_files': len(sources), 'additional_files': len(additional),
                  'preserved_files': len(preserved), 'ktests': len(ktests),
                  'blocking_findings': len(review['blocking_findings'])}))
