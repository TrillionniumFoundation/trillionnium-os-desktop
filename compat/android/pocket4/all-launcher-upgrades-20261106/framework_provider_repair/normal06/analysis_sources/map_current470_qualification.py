"""Write the finite capability/contract mapping and an additive Git08 delta index."""
import ast
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DEST = BASE / 'builder470-current-qualification-r1/source-r1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path, function=None):
    raw = (BASE / path).read_bytes()
    value = {'path': path, 'bytes': len(raw), 'sha256': sha(raw)}
    if function:
        node = next(item for item in ast.parse(raw).body if isinstance(item, ast.FunctionDef) and item.name == function)
        value.update(function=function, first_line=node.lineno, last_line=node.end_lineno)
    return value


def write(name, document):
    (DEST / name).write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def main():
    plan = json.loads((DEST / 'execution-plan.json').read_bytes())
    tests = plan['updater_tests']
    resume = plan['source_resume_tests']
    source_file = 'builder470-current-qualification-r1/source-r1/qualify_current470.py'
    old_contracts = [ref('source-r4/' + name, 'builder_contract') for name in
                     ['parent-normal03-framework_build.py', 'parent-normal05-framework_build.py', 'framework_build.py']]
    rows = []
    for index, name in enumerate(tests):
        origin = '468 original updater 15' if index < 15 else ('469 additional native provider' if index == 15 else '470 SystemUI/provider3')
        rows.append({'id': 'updater-' + str(index), 'historical_origin': origin, 'exact_test': name,
            'new_action': 'Re-run the existing exact actual470 updater test ELF with --exact and independent --logfile.',
            'current_source': '498-file source manifest; original actual470 compile, test ELF and all raw command outputs identity-bound.',
            'expected_registered_count': 209, 'expected_filtered_count': 208,
            'new_label': 'projection-test-' + str(index), 'new_status': 'NOT_EXECUTED',
            'required_evidence': ['new command exit 0, no timeout, exactly one selected test',
                'one held O_EXCL private libtest file containing exactly ok + exact test name',
                'independent record agrees with stdout counts and all post-input/resource/lifetime checks']})
    for index, name in enumerate(resume):
        rows.append({'id': 'resume-' + str(index), 'historical_origin': '468 source-resume 9; inherited, not rerun by old469/current470 compile',
            'exact_test': name, 'new_action': 'Compile only the source library test from current498 into a fresh owned target, then run this exact test.',
            'source_proof': 'All four tools/droidloom-source files plus Cargo.toml/Cargo.lock/rust-toolchain.toml match original491,493,498 manifests.',
            'expected_registered_count': 20, 'expected_filtered_count': 19,
            'new_label': 'projection-test-' + str(100 + index), 'new_status': 'NOT_EXECUTED',
            'required_evidence': ['actual Cargo compiler-artifact list equals the original source-resume 46-package subset, remapped only to current source',
                'source test artifact path/kind/name/manifest derived from that successful Cargo output',
                'independent held libtest record and exact stdout counts',
                'local temporary fixtures; cfg(test) disables HTTPS; source/dependencies/tools unchanged afterward']})
    controls = [
        ('legacy-live-elf', 'Old468 and old469 live ELF identities in the inherited builder_contract chain',
         'Old468 ELF is actually missing. This qualification never opens it as an executable, writes its path, reconstructs its inode, or changes historical metadata.',
         'Qualify current470 ELF against its own actual compile receipt, full original inode/mode/mtime/ctime, bytes/SHA, executable mode and explicit owner. A future distinct authorization contract must be separately reviewed.',
         'current_artifact', 'BLOCKED_OLD_CONTRACT_UNCHANGED'),
        ('historical-authorities', '468 result, 469 compile02 + qualify02, and 470 compile02 result provenance',
         'Preserve immutable historical bytes and every real failure; old PASS remains historical, never relabeled as fresh.',
         'Bind all exact receipt hashes, current470 predecessor receipt full identities, original dependency authority, manifest ancestry and historical test-name relationships.',
         'authority', 'NOT_EXECUTED'),
        ('actual470-compile', 'Current470 actual 23-command compile and 19 independent gates',
         'No need to rebuild the unchanged current updater; its actual qualification already exists.',
         'Use the unchanged pure receipt validator; re-read all 46 stdout/stderr files and 19 independent logs with exact original identities; preserve memory peak 1GiB and max events 657, OOM/swap zero.',
         'current_receipt_outputs', 'NOT_EXECUTED'),
        ('current-source-completeness', '491 → 493 → 498 source and manifest closure',
         'No hidden source substitution or stale manifest.',
         'Verify every one of 498 current file contents/modes, source owners and directory types; exact two changed files and 2 then 5 additions; no deletions. Capture every full identity before/after.',
         'source_observation', 'NOT_EXECUTED'),
        ('source-lock-provenance', 'Original typed/provider/provider2/provider3 source locks and retained Go resource patch',
         'No fake defaults, unpinned provider, rewritten old lock, or unrestricted repo sync.',
         'Exact complete498 manifest binds all old locks, patch and new242-project/eight-link official superproject lock. Existing 19 tests cover exact lock acceptance, rejection and source projection. This candidate neither syncs nor runs Soong.',
         'verify_source_ancestry', 'NOT_EXECUTED'),
        ('registry-package-closure', 'Original 49 selected packages, 45 registry packages and 2706 source/archive files',
         'No new dependencies or substituted same-name files.',
         'Exact original registry file full identities and hashes before/after; original dependency document full identity retained; current updater original actual49 package lists bound; newly compiled source library must match exact46 subset.',
         'qualify_compiler_inputs', 'NOT_EXECUTED'),
        ('rust-tools-and-identities', 'Original explicit Rust1.93, compiler/linker/runtime closure and current tool continuity',
         'Do not run rustup proxy or silently accept moved/replaced tool bytes.',
         'All70 actual tools must equal the actual470 pre-compile full pins. Also verify original allowed bytes/resolved paths/modes, owner root for /usr or operator1000 for pinned .rustup, and unchanged full identities afterward.',
         'checked_tools', 'NOT_EXECUTED'),
        ('cargo-and-environment', 'Offline locked j1, no Cargo config or inherited HOME/wrappers',
         'No arbitrary shell, toolchain proxy or network dependency fetch.',
         'Explicit environment, fixed Cargo path, --offline --locked -j1, owned new target/tmp, absent config set before/after. Fresh source compile only; existing updater binary remains untouched.',
         'no_cargo_config', 'NOT_EXECUTED'),
        ('typed-cli', 'Fixed native-role-ingress CLI only; no arbitrary targets',
         'Source help actual flag is --resume-source-staging, not the rejected draft spelling.',
         'Only invoke current470 --help and native-role-ingress-build --help, then existing exact CLI tests. Do not invoke the actual build subcommand.',
         'registered_tests', 'NOT_EXECUTED'),
        ('private-resume-fixtures', 'Resume preserves interrupted/dirty files, rejects wrong origin/symlinks/stale manifest',
         'Do not test against actual source staging or live AOSP worktree.',
         'Exact current cfg(test) source disables HTTPS. Nine test fixtures use tempfile::tempdir under new TMPDIR, with local file:// fixture origins only.',
         'run_current_qualification', 'NOT_EXECUTED'),
        ('fresh-rust-resources', 'Owned1GiB RAM,1CPU,j1,zero swap,at least2 logical CPUs free;fresh3GiB admission',
         'No retry or lowering full-framework 15GiB admission.',
         'Reuse unchanged admission helpers; record the fresh bounded /proc/meminfo sample before deciding. One /usr/bin/systemctl --user command sets only the already-owned unit MemorySwapMax=0; no Main service changes.',
         'record_resource_admission', 'NOT_EXECUTED'),
        ('child-lifetime', 'No owned residual children, timeout, forced cleanup or reap hidden as PASS',
         'Actual subprocess failures are retained.',
         'Unchanged command/subreaper/pidfd-cleanup helpers. PASS requires exact cleanup complete=true,children=[],errors=[]; any kill/reap cleanup record fails. Root must reconcile durable exit and full logs.',
         'cleanup_children', 'NOT_EXECUTED'),
        ('library-fd-lifetime', 'Diagnostic failed its FD census when _ctypes introduced libffi FD3',
         'That real failure remains unchanged; do not close libffi manually or adopt late unknown FDs.',
         'Start with only0/1/2, explicitly import ctypes at an early phase, qualify only observedFD3 by full original stat/hash/owner/flags. Before/after descriptor set identical; process exit retires library. This is a new explicit contract, not a reinterpretation of the failed diagnostic.',
         'explicit_library_baseline', 'NOT_EXECUTED'),
        ('source-and-owner-final', 'All bound source, receipts, registry inputs, tools, existing artifacts and owners unchanged',
         'Incomplete observation cannot count as final continuity.',
         'Final gate requires all11 fixed authorities and each mandatory input group reached, then re-reads full pins/owners, source inventory, zero OOM/swap and exact descriptor set.',
         'run_current_qualification', 'NOT_EXECUTED'),
        ('finite-command-test-closure', 'Fresh28 tests are jointly required; nine alone never equivalent to old contract',
         'Do not treat arbitrary result flags as valid execution.',
         'Exact34 recorded CLI/list/test/compile command labels, every returncode0/no timeout, exact19+9 independent names, all15 gates, no errors and strict child cleanup; final stdout + authoritative durable exit0 required.',
         'qualification_complete', 'NOT_EXECUTED'),
    ]
    control_rows = [{'id': key, 'inherited_condition': inherited, 'preserved_boundary': boundary,
        'new_qualification_evidence_required': new, 'implementation': ref(source_file, function), 'status': status}
        for key, inherited, boundary, new, function, status in controls]
    retained = [
        {'condition': 'Old468/469 live ELF contract', 'state': 'NOT_REPAIRED_OR_BYPASSED',
         'reason': 'New qualification is a prerequisite for a later explicitly reviewed current-builder authorization contract.'},
        {'condition': 'Full Android framework two-target compilation, source-resume on actual staging and transitive Soong graph',
         'state': 'NOT_EXECUTED', 'reason': 'No Soong, Java/JNI build, source fetch, deployment or live worktree mutation here.'},
        {'condition': 'Main typedguard, runtime epoch, explicit47/current launcher scope, lifecycle/source flow locks and before/after fence',
         'state': 'UNCHANGED_AND_NOT_USED', 'reason': 'A future full-framework request must bind then-current actual scope and retain all existing lock/fence contracts.'},
        {'condition': 'Full-framework fresh15GiB admission,10GiB RAM,0swap,2CPU,j1,Strict/ALLOW_MISSING_DEPENDENCIES=false',
         'state': 'UNCHANGED', 'reason': 'One-GiB Rust qualification is a distinct previously evidenced workload profile, never a lowered Soong gate.'},
        {'condition': 'APK vendor signatures, installation permission, Meituan location denial, Bili isolated-cell Accept and business integrity checks',
         'state': 'UNTOUCHED', 'reason': 'No APK, Android, permission, UI, location, login or guest Accept action exists in this candidate.'},
        {'condition': 'Old468 image-tool ldd observations and packaging/image functionality',
         'state': 'HISTORICAL_ONLY_NOT_REQUALIFIED', 'reason': 'No image/packaging command is authorized by this current-builder qualifier or the fixed framework two-target route. Future use needs its own applicable tool/artifact qualification.'},
        {'condition': 'Production readiness and old-version cleanup', 'state': 'FALSE',
         'reason': 'Neither host qualification nor eventual successful compilation proves deployment or app regression readiness.'},
    ]
    write('capability-contract-map.json', {
        'schema': 'pocket4-builder470-current-qualification-capability-map-v1',
        'state': 'NEW_CANDIDATE_NOT_EXECUTED', 'old_contracts': old_contracts,
        'qualification_source': ref(source_file), 'test_mapping': rows, 'contract_mapping': control_rows,
        'conditions_not_replaced_or_granted': retained, 'production_ready': False,
        'cleanup_eligible': False, 'new_authorization_contract_connected': False,
        'logical_scope': '28 finite tests + current498 provenance/identity/input/resource/lifetime qualification; no assertion of all old operational contracts being interchangeable.',
        'historical_status': {'old468_compiler03': 'historical24PASS; live ELF now missing',
            'old469_compile02_qualify02': 'historical16PASS; nine source-resume inherited',
            'current470_compile02': 'actual19PASS; 498source/242projects; nine source-resume not rerun there',
            'build06': 'failed before inner due exact snapshot pin mismatch, preserved',
            'build07': 'failed inside verify_prepared before builder Popen; old468 ELF ENOENT',
            'preparation_diagnostic': 'FAILED1; ENOENT plus libffi descriptor census difference, preserved'},
        'reference_inputs': [ref('builder470-current-qualification-r1/reference/' + name) for name in
            ['legacy468-tool-inputs.original.json', 'current470-tool-inputs.original.json',
             'legacy468-source-cli-help.original.txt', 'legacy468-source-test-compile.original.txt',
             'current470-resume.original.rs', 'current470-source-lib.original.rs', 'current470-AGENTS.original.md']],
    })
    write('review-notes.json', {
        'state': 'READY_FOR_ROOT_SOURCE_REVIEW_ONLY', 'remote_processes_submitted': 0,
        'required_separate_future_review': 'Connecting any newly successful qualification to a current-builder framework authorization contract.',
        'new_owned_files_only': [plan['new_root'] + '/qualify_current470.py', plan['new_root'] + '/stage-receipt.json', plan['output']],
        'never_written': ['any old468/469 path', plan['source_read_only'], plan['existing_builder']['path'],
                          plan['existing_test_executable']['path'], 'existing Android/Main source, namespace, APK or data'],
        'own_resource_configuration_command': ['/usr/bin/systemctl', '--user', 'set-property', '--runtime',
                                               '<current owned hepta job service only>', 'MemorySwapMax=0'],
        'recorded_qualification_command_count_excludes_that_one_own_resource_configuration': 34,
        'all_commands_including_owned_resource_configuration': 35,
        'descriptor_policy': 'Only original stdio, then one explicitly initialized/pinned process-lifetime libffi descriptor. No manual close; authoritative normal process exit required.',
        'predecessor_failure': ref('preparation-diagnostic-r1/actual/stdout.original.jsonl'),
        'build07_failure': ref('actual-build07/fence-terminal.original.json'),
        'new_candidates_are_not_historical_results': True,
        'old_diagnostic_census_failure_not_reclassified': True,
        'no_extra_helper_install_or_Main_reader_needed': True,
    })
    existing = sorted(path for path in DEST.iterdir() if path.is_file() and path.name != 'SOURCE_PINS.json')
    write('SOURCE_PINS.json', {'schema': 1, 'state': 'FROZEN_LOCAL_CANDIDATE_NOT_SUBMITTED',
        'files': [{'path': path.name, 'bytes': len(path.read_bytes()), 'sha256': sha(path.read_bytes())} for path in existing]})
    scope = [BASE / 'old468-recovery-investigation-r1', BASE / 'builder470-current-qualification-r1']
    files = [path for root in scope for path in root.rglob('*') if path.is_file()]
    files += [BASE / 'analysis_sources' / name for name in ['current470_qualification_extra.py.inc',
        'current470_qualification_stage.py.inc', 'generate_current470_qualification.py',
        'check_current470_qualification.py', 'map_current470_qualification.py']]
    index = {'schema': 'pocket4-official-versions-post-git08-delta-v1',
        'base_commit': '6d67481d0c580bdf74e80358bbadb87ff6293905', 'file_count': len(files),
        'files': [ref(str(path.relative_to(BASE))) for path in sorted(files)],
        'total_bytes': sum(path.stat().st_size for path in files), 'deletions': [],
        'APKs_included': False, 'private_UI_included': False, 'ELF_binaries_included': False,
        'original_bin_and_fragment_files_are_JSON_transport_fragments': True,
        'old_failures_kept_in_prior_checkpoint': True, 'current_candidate_submitted': False}
    target = BASE / 'post-checkpoint08-current470-qualification-delta.json'
    target.write_text(json.dumps(index, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'mapping': ref(str((DEST / 'capability-contract-map.json').relative_to(BASE))),
                      'source_pins': ref(str((DEST / 'SOURCE_PINS.json').relative_to(BASE))),
                      'delta': ref(str(target.relative_to(BASE))), 'delta_files': len(files)}, indent=2))


if __name__ == '__main__':
    main()
