#!/usr/bin/env python3
"""Freeze read-only G1-c design findings; this does not run product tests."""
from pathlib import Path
import datetime
import hashlib
import json
import subprocess

ROOT = Path('/workspace/scratch/499c7902de8e/r12-g1c')
OUT = Path(__file__).resolve().parent
BASE = '7c675e1d3efe46587edeebe14bd90ac1a842ffbf'
PATHS = '''kernel/asterinas/AGENTS.md
kernel/asterinas/book/src/to-contribute/coding-guidelines/for-development/README.md
kernel/asterinas/book/src/to-contribute/coding-guidelines/for-development/concurrency.md
kernel/asterinas/book/src/to-contribute/coding-guidelines/for-development/correctness.md
kernel/asterinas/book/src/to-contribute/coding-guidelines/for-development/resource-management.md
kernel/asterinas/book/src/to-contribute/coding-guidelines/for-development/testing.md
kernel/asterinas/book/src/to-contribute/coding-guidelines/for-security/README.md
kernel/asterinas/book/src/to-contribute/coding-guidelines/for-security/security-properties.md
kernel/asterinas/book/src/to-contribute/coding-guidelines/for-security/memory-safety.md
kernel/asterinas/kernel/core/src/process/process/mod.rs
kernel/asterinas/kernel/core/src/process/process/init_proc.rs
kernel/asterinas/kernel/core/src/process/clone.rs
kernel/asterinas/kernel/core/src/process/execve.rs
kernel/asterinas/kernel/core/src/process/exit.rs
kernel/asterinas/kernel/core/src/process/task_set.rs
kernel/asterinas/kernel/core/src/process/posix_thread/exit.rs
kernel/asterinas/kernel/core/src/process/posix_thread/alien_access.rs
kernel/asterinas/kernel/core/src/process/posix_thread/builder.rs
kernel/asterinas/kernel/core/src/process/posix_thread/ptrace/mod.rs
kernel/asterinas/kernel/core/src/process/process_vm/mod.rs
kernel/asterinas/kernel/core/src/process/program_loader/mod.rs
kernel/asterinas/kernel/core/src/process/program_loader/elf/load_elf.rs
kernel/asterinas/kernel/core/src/thread/mod.rs
kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs
kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/pid/task/mem.rs
kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/pid/task/maps.rs
kernel/asterinas/kernel/core/src/security/lsm/modules/capability.rs
kernel/asterinas/kernel/core/src/security/lsm/hooks/alien_access.rs
kernel/asterinas/kernel/core/src/syscall/ptrace.rs
kernel/asterinas/kernel/core/src/vm/vmar/handle.rs
kernel/asterinas/kernel/core/src/vm/vmar/vmar_impls/access_alien.rs
kernel/asterinas/kernel/core/src/vm/vmar/vmar_impls/protect.rs
kernel/asterinas/kernel/core/src/vm/vmar/vmar_impls/map.rs
kernel/asterinas/kernel/core/src/vm/vmar/vm_mapping.rs
kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native.rs
kernel/asterinas/ostd/src/task/mod.rs
tests/kernel/control/queryabi_guest.c
tests/kernel/control/queryabi_candidate_guest.c
tests/kernel/control/README.md
docs/SECURITY_AND_RECOVERY.md
results/integration/2026-10-19-g1b-usage/g1c-design/process-exec-owner-design-4d3011cf.json'''.splitlines()

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

inputs = []
for name in PATHS:
    data = git('show', BASE + ':' + name)
    local = (ROOT / name).read_bytes()
    mode_blob_path = git('ls-tree', BASE, '--', name).decode().strip()
    inputs.append({'path': name, 'base_git_entry': mode_blob_path,
                   'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                   'local_at_freeze_matches_base': local == data})

review = {
    'schema_version': 1,
    'kind': 'read_only_g1c_design_review',
    'reviewer': '/root/g1c_review',
    'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source': {'commit': BASE, 'tree': git('rev-parse', BASE + '^{tree}').decode().strip(),
               'repository': 'TrillionniumFoundation/trillionnium-os-desktop'},
    'scope': 'Independent design and selected actual call-path review. No candidate implementation is approved by this receipt. No product tests, builds, toolchain installation or remote writes.',
    'minimum_implementation_scope': [
        'Replace anonymous Process image tuple and independent epoch with one canonical mutex-protected lifecycle; no copied authority on new/fork Process.',
        'Use private uncloneable prepared-init construction on the existing load-complete, never-scheduled path. Bind exact Process, VMAR, main Task and image key. Consume once before scheduling.',
        'Close old image at irreversible exec admission, before signalling sibling threads; commit only a distinct empty image after success. Pre-boundary failures leave old session unchanged; fatal failure stays closed.',
        'Close on accepted exit_group and final ordinary-thread exit. Non-last ordinary-thread exit retains the shared Process image.',
        'Keep QueryAbi-only, all four resource operations disabled, no grant/handle placeholder table, no owner revoke framework or resource ledger duplication.'
    ],
    'necessary_design_refinements': [
        {'id': 'R1', 'severity': 'implementation_constraint',
         'finding': 'Existing procfs mem/maps open holds Process VMAR, then main_thread obtains TaskSet. New preparation cannot nest TaskSet -> VMAR.',
         'evidence': ['kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/pid/task/mem.rs:45-48',
                      'kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/pid/task/maps.rs:48-51',
                      'kernel/asterinas/kernel/core/src/process/process/mod.rs:377'],
         'required_order': 'VMAR -> TaskSet -> image where all are required. TaskSet -> image alone is allowed. Never image -> TaskSet or VMAR; no Process/image lock in IRQ/runqueue accounting sections.',
         'communication': 'Sent to /root and /root/g1c_lifecycle before candidate edits.'},
        {'id': 'R2', 'severity': 'implementation_constraint',
         'finding': 'Thread has is_exited but no public Init state. OSTD Task::run delegates to run_new_task and does not provide a public never-started proof.',
         'evidence': ['kernel/asterinas/kernel/core/src/thread/mod.rs:85-139',
                      'kernel/asterinas/ostd/src/task/mod.rs:111-115'],
         'required_fix': 'Prove never-run by private constructor reachability and a canonical first-run claim shared with the ordinary Process startup path, not is_exited=false or a freely constructible token. Token consume rechecks exact live objects and closes/consumes on terminal failures. No OSTD change is necessary for the scoped lifecycle.'},
        {'id': 'R3', 'severity': 'implementation_constraint',
         'finding': 'Existing lazy open can allocate nonce whenever epoch pair is reset; new Closing/Closed phase must gate lazy allocation, not merely old-fd equality.',
         'required_fix': 'Closed and exhausted states never revive by open or a stale prepared token. Epoch and nonce use checked arithmetic; exhaustion must not allow alias or partial publication.'},
        {'id': 'R4', 'severity': 'scope_constraint',
         'finding': 'A prepared object proves allocation/lifecycle, not executable authentication or authorization.',
         'required_fix': 'Keep four effects closed. Do not claim trusted boot principal, canonical resource observe rights, revoke completion or durable Hepta delivery from this lifecycle patch.'}
    ],
    'guest_test_recommendations': [
        {'case': 'pre-boundary-user-copy-failure',
         'action': 'Open QueryAbi in the current Process; record full boot and CapSpace bytes. Direct SYS_execve of valid probe path with invalid argv pointer must return EFAULT. The same fd and a new open must remain valid with identical boot/space.',
         'scope': 'Actual syscall user-copy failure before irreversible boundary; not a loader-stage or fatal exec test.'},
        {'case': 'pre-boundary-lookup-or-format-failure',
         'action': 'Direct execve of nonexistent path expects ENOENT, or fixed malformed executable expects ENOEXEC. Requery original fd and fresh open, requiring unchanged full identity.',
         'scope': 'Record selected failure stage; nonexistent path alone does not cover new_vmar or segment-loading failures.'},
        {'case': 'successful-real-exec',
         'action': 'Preserve original guest child that opens its own non-CLOEXEC fd, proves it valid before exec, executes the same probe, obtains ESTALE on old fd and a different namespace on reopen.',
         'scope': 'Do not substitute a parent fd already invalid due to fork, or an fd closed by CLOEXEC. Retain original seven lifecycle markers and four disabled-operation markers.'},
        {'case': 'same-process-threads',
         'action': 'Optional pthread guest with full identity equality on same Process and dup; a non-last thread exits and surviving thread remains usable.',
         'scope': 'No need to infer close-on-final-exit from a foreign process, whose fd access was already denied.'},
        {'case': 'kernel-object-only-boundaries',
         'action': 'Use actual unstarted Process/Task/VMAR objects for mismatched preparation, duplicate consumption, close idempotence, epoch/nonce exhaustion and detached old-key refusal.',
         'scope': 'Explicitly label as kernel-object regressions; no user-visible route currently exists to force nonce exhaustion or issue ioctl after final Process exit.'}
    ],
    'next_static_readusage_requirements': [
        {'id': 'S1', 'call_paths': ['process/program_loader/mod.rs::UndetectedExecutable::detect_format',
                                   'process/program_loader/mod.rs::ProgramToLoad::from_executable',
                                   'process/program_loader/elf/load_elf.rs::lookup_and_parse_ldso',
                                   'process/program_loader/elf/load_elf.rs::map_segment_vmo'],
         'finding': 'The loader may replace a script with an interpreter and map file-backed private segments from Arc<FileLike>. ElfLoadInfo has only entry/stack.',
         'needed': 'First grant only for a directly loaded static ELF with no shebang or PT_INTERP, from an immutable measured byte source actually used to build mappings. Binding pathname or Arc allocation alone is insufficient. Preserve ordinary execution without grant for unsupported shapes.'},
        {'id': 'S2', 'call_paths': ['fs/fs_impls/procfs/pid/task/mem.rs::MemFileOps::open',
                                   'fs/fs_impls/procfs/pid/task/mem.rs::MemFileHandle::write_at',
                                   'process/posix_thread/ptrace/mod.rs::TraceeStatus::poke_data',
                                   'syscall/ptrace.rs::sys_ptrace'],
         'finding': 'procfs mem checks access at open, then retained handles only check VMAR identity before read/write. Ptrace can alter data and register state. The present capability LSM permits same credentials or SYS_PTRACE subject to active other LSMs; no native-image exclusion appears at these paths.',
         'needed': 'Activation and later accesses must exclude or canonically fence both existing and future untrusted alien writers, including old mem handles, tracing register writes and clone/shared-VM aliases. Blocking new opens alone does not close retained-handle races. Whole-VMAR writable data/stack matters as well as text.'},
        {'id': 'S3', 'call_paths': ['vm/vmar/vmar_impls/map.rs::VmarMapOptions::new',
                                   'vm/vmar/vmar_impls/access_alien.rs::query_page_with_required_flags',
                                   'vm/vmar/vm_mapping.rs::check_perms_for_page_fault',
                                   'vm/vmar/vmar_impls/protect.rs::Vmar::protect'],
         'finding': 'Default mapping may-permissions include write; alien access uses forced faults and COW can permit writing private read-only text. RX page flags alone do not prove immutable executable identity.',
         'needed': 'Use validated immutable source/mappings with constrained may-permissions or equivalent enforced exclusion, and cover shared backing changes/remapping. Do not announce a grant solely after hashing mutable file contents.'},
        {'id': 'S4', 'call_paths': ['device/misc/hepta_control.rs::HeptaControlFile::ioctl',
                                   'fs/fs_impls/cgroupfs/controller/cpu/native.rs::Controller::read_native_cpu_usage_for_owner'],
         'finding': 'Current session check precedes user copies; internal G1-b observation supplies identity/revision/usage but explicitly no authorization.',
         'needed': 'After complete bounded request copy, resolve exact image/handle then release sleeping locks. At the original CPU owner mutation lock recheck canonical live observer grant/lease, owner instance and revision. Revoke must use the same admission synchronization. Keep N0 one CPU/100ms first and response capacity real.'},
        {'id': 'S5', 'call_paths': ['process/clone.rs::clone_vmar', 'process/clone.rs::clone_child',
                                   'process/clone.rs::create_child_process'],
         'finding': 'A fresh Process can share VMAR through CLONE_VM without CLONE_THREAD. Empty child authority alone does not exclude the child from modifying a granted parent address space.',
         'needed': 'First positive profile must reject/close grant on unsupported shared-VM process creation or establish whole-VMAR writer ownership; future process_vm support must enter the same policy, not bypass it.'}
    ],
    'accounting_boundary': 'Native image close must not clear CpuMax cumulative, debt, quota, revision or final CpuCgroupLease. Existing migration order is CgroupMembership -> TaskSet. Preserve original retained accounting until the final old run segment is settled.',
    'inputs': inputs,
    'activities': {'product_source_edits': 0, 'product_tests': 0, 'builds': 0,
                   'runtime_executions': 0, 'toolchain_installs': 0, 'remote_writes': 0},
    'pending': ['Read and independently review actual implementation diff after author declares a coherent candidate.',
                'Record final candidate source identity and check source closure without substituting for root runtime acceptance.']
}
path = OUT / 'design-review-base7c675e1d.json'
path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'path': str(path), 'bytes': path.stat().st_size,
                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'inputs': len(inputs), 'all_local_inputs_equal_base': all(v['local_at_freeze_matches_base'] for v in inputs)}))
