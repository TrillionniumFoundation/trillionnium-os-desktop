"""Freeze one production Rust delta and bounded local evidence; no device action."""
from pathlib import Path
import difflib
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(__file__).resolve().parent
OUT = ROOT / 'android-owner17-bootstrap-mode-source-freeze01'
REL = 'runtime/droidloom-supervisor/src/relay_lifecycle/entry.rs'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    assert not OUT.exists()
    old = (WORK / 'preimage' / REL).read_bytes()
    new = (WORK / 'candidate' / REL).read_bytes()
    assert len(old) == 31106 and sha(old) == 'c821e6c62906c9f4d4f27c22781f7521518f715588ca3be791055d32fbed174f'
    assert len(new) == 37570 and sha(new) == 'fa8a4d2c6ddc6508f3527a4711566402b7d0ad51339e42aca3c3d9395615d080'
    before, after = old.decode(), new.decode()
    patch = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                    fromfile='preimage/' + REL, tofile='candidate/' + REL)).encode()
    assert patch == (WORK / 'production.diff').read_bytes()
    # Remove only the declared import, two call sites, helper replacement and
    # three new tests. Every other byte must reconstruct the actual preimage.
    inverse = after.replace('use std::ffi::{CStr, CString, OsString};', 'use std::ffi::{CString, OsString};')
    a = inverse.index('        // These two directories belong to the fresh synthetic guest tmpfs.')
    z = inverse.index('        for (name, mode)', a)
    oa = before.index('        let droidloom = make_parent(')
    oz = before.index('        for (name, mode)', oa)
    inverse = inverse[:a] + before[oa:oz] + inverse[z:]
    a, z = inverse.index('fn bootstrap_directory('), inverse.index('fn bind_readonly(')
    oa, oz = before.index('fn make_parent('), before.index('fn bind_readonly(')
    inverse = inverse[:a] + before[oa:oz] + inverse[z:]
    a = inverse.index('    #[test]\n    fn guest_search_mode_changes_only_the_held_owned_directory()')
    z = inverse.index('    #[test]\n    fn final_init_exec_contract_rejects_wrappers_and_other_stage()', a)
    inverse = inverse[:a] + inverse[z:]
    assert inverse.encode() == old
    controls = (WORK / 'controls/kernel-result.json').read_bytes()
    cr = json.loads(controls)
    assert sha(controls) == 'dcd363476a28a66b2138730495d892a5a2ab3e7e784ca989ff3fd6f8d3c0fb4b'
    assert cr['ok'] and cr['checks_passed'] == 8 and cr['first_error'] is None
    assert cr['held_fds_closed'] and not cr['close_errors']
    assert not cr['actual_Rust_function_executed'] and not cr['Android_or_device_run']
    runtime_review = (ROOT / 'android-owner16-runtime-actual-review01/report.json').read_bytes()
    assert len(runtime_review) == 6777 and sha(runtime_review) == '490240e3c22e6dead7f17d5b242f8554792d7426e5d6f9dd1165bbd5ea67970e'
    actual_raw = (ROOT / 'root-recovery-20261104-02/evidence/owner16-host-log-compile02/compile-result.json').read_bytes()
    assert len(actual_raw) == 49729 and sha(actual_raw) == 'dad36fe9fd79aa782bcc255e74b8cc1b1ee241a341318e179ccaa9e7f1c785ea'
    actual = json.loads(actual_raw)
    assert actual['inputs_before'] == actual['inputs_after'] and len(actual['inputs_before']) == 33
    assert actual['inputs_before'][REL] == {'bytes': len(old), 'sha256': sha(old)}
    assert actual['success'] and actual['compile_only'] and actual['revision'] == 'producer16-bounded-init-log01'
    paths = json.loads((ROOT / 'android-owner16-runtime-analysis-work01/matched-source-paths.json').read_bytes())
    matched = {}
    for relative, path in paths.items():
        body = (ROOT / path).read_bytes()
        assert actual['inputs_before'][relative] == {'bytes': len(body), 'sha256': sha(body)}
        assert 'umask' not in body.decode()
        matched[relative] = {'path': path, 'bytes': len(body), 'sha256': sha(body)}
    assert len(matched) == 27
    files = {}
    def put(name, body):
        body = body.encode() if isinstance(body, str) else body
        body.decode('utf-8'); assert name not in files
        files[name] = body
    put('preimage/' + REL, old)
    put('candidate/' + REL, new)
    put('production.diff', patch)
    put('controls/kernel_mode_controls.py', (WORK / 'controls/kernel_mode_controls.py').read_bytes())
    put('controls/kernel-result.json', controls)
    put('evidence/owner16-runtime-review.json', runtime_review)
    put('evidence/actual-host16-source-pins.json', pretty({'actual_report_bytes': len(actual_raw),
        'actual_report_sha256': sha(actual_raw), 'candidate': actual['candidate'], 'revision': actual['revision'],
        'inputs': actual['inputs_before'], 'all_source_inventory_sha256': actual['all_source_inventory_before_sha256']}))
    put('evidence/matched27-Rust-source-umask-check.json', pretty({'sources': matched,
        'all_27_actual_Rust_inputs_found_by_exact_bytes_and_sha256': True,
        'umask_occurrences': 0, 'transitive_libraries_and_external_binaries_not_inspected': True}))
    put('validation.json', pretty({'schema': 1, 'scope': 'SOURCE_AND_OWNED_KERNEL_MECHANISM_ONLY',
        'source_files_changed': 1, 'production_delta_bytes': len(patch), 'production_delta_sha256': sha(patch),
        'exact_inverse_to_actual_preimage': True, 'original_remaining_source_bytes_identical': True,
        'original_cgroup_projection_ABI3_authority_logger_retirement_RC_and_readonly_bind_unchanged': True,
        'local_kernel_mechanism_checks': 8, 'local_kernel_result_sha256': sha(controls),
        'new_Rust_tests': ['guest_search_mode_changes_only_the_held_owned_directory',
            'guest_search_mode_rejects_replaced_or_symlink_name_before_chmod',
            'guest_search_mode_preserves_failed_fchmod_errno'],
        'new_Rust_test_execution': 'PENDING_MATCHED_HOST_COMPILE_AND_ORDINARY_RUN',
        'expected_ordinary_relay_count': 39, 'expected_ordinary_supervisor_count': 139,
        'previous_ordinary_supervisor_136_tests_retained': True,
        'LMKD_exec_EACCES_complete_cause_proven': False, 'HWS_abort_cause_proven': False,
        'remote_action': False, 'Main_or_service_config_modified': False, 'Android_runtime_qualified': False}))
    put('README.md', '''# Owner17 owned guest bootstrap search modes

This is one Rust production-file successor to the actual Host16 entry source.
The original Owner16 FAILED report, binaries and source are unchanged. Its
generation-private logger delivered both real KernelLogger markers and161943
bytes, including four LMKD exec EACCES messages and a distinct critical
hwservicemanager repeated-SIGABRT fatal reboot. The actual unit uses UMask0077.
All27 pinned Rust inputs have been inspected for umask calls; none contains
one. The prior mkdir0755/create_dir_all paths admit0700 guest directories.

Only /droidloom and the new create-only lmkd-bootstrap directory are adjusted
through held descriptors. Before chmod the exact synthetic root must be
tmpfs, inode1, UID/GID0 and0755; parents and target must be directories on the
same device, owned byUID/GID0, without group/other writes or special bits.
This prevents chmod of a host or partition bind. The existing parent is
accepted only within that already-created private guest tmpfs. Names are
one fixed component; O_NOFOLLOW/O_CLOEXEC remain. The held target and named
target must agree before and after fchmod0755. Host package/data parents,
unit umask, all payload hashes and read-only binds remain unchanged.

The actual mode operation is factored after root/private-tmpfs authorization.
Three added Rust tests exercise it with ordinary owned files: exact scope,
replacement/symlink rejection before chmod, and the original EBADF from an
O_PATH descriptor. They are not yet compiled or run. Eight local kernel
mechanism assertions reproduced the umask counterexample and verified the
held chmod/mode/inode behavior; they do not execute the Rust function or
prove private mount authorization, LMKD effective capabilities, or Android.
The existing39 relay and136 supervisor tests remain; the candidate adds3
supervisor tests, for an exact139 expectation on the next ordinary run.

The RC requests DAC_OVERRIDE. Therefore the directory defect alone does not
prove the complete cause of all four EACCES results. The HWS abort message
is still absent and is a separate investigation. No critical service flag,
Main setting, identity gate, broker grant or generation recovery is relaxed.
FD/named checks are not an atomic filesystem CAS; the production call occurs
in the existing single-threaded pre-init entry and owned private mount view.
''')
    put('freeze_source.py', Path(__file__).read_bytes())
    put('SOURCE_PINS.json', pretty({'schema': 1, 'kind': 'OWNER17_OWNED_GUEST_BOOTSTRAP_MODES_SOURCE_ONLY',
        'files': {name: {'bytes': len(body), 'sha256': sha(body)} for name, body in sorted(files.items())}}))
    OUT.mkdir()
    for name, body in files.items():
        destination = OUT / name; destination.parent.mkdir(parents=True, exist_ok=True)
        destination.open('xb').write(body)
    print(json.dumps({'root': str(OUT), 'files': len(files), 'manifest_sha256': sha(files['SOURCE_PINS.json']),
        'entry_bytes': len(new), 'entry_sha256': sha(new), 'diff_bytes': len(patch), 'diff_sha256': sha(patch)}))


if __name__ == '__main__':
    main()
