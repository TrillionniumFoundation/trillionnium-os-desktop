#!/usr/bin/env python3
"""Read-only publication integrity gate; no native or host tests are launched."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
from urllib.parse import unquote, urlsplit

sys.dont_write_bytecode = True
R = Path('/workspace/scratch/d7da9e7650f0/a01-mainf9')
O = R / 'support/build/out/2026-10-19-mainf9'
E = R / 'support/build/evidence/2026-10-19-mainf9'
P = '7758ffe294bb0e1eab46e20cba60e8af9d8bcd61'
M = 'f9e306f76154590e096a42f70ce9de0a7c859e60'


def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(path): return json.loads(path.read_text())
def git(*args):
    return subprocess.check_output(['git', '-C', str(R), *args], env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})


def main():
    review = {'kind': 'independent_read_only_publication_review', 'started_at': now(),
              'native_producer': P, 'evidence_root': str(E), 'checks': [], 'observations': {},
              'new_native_or_host_test_executions': 0, 'repository_writes_by_reviewer': False,
              'ordered_followup_before_publication': [
                  'Root copies this review and its script into the final payload.',
                  'Root generates SHA256SUMS and runs actual sha256sum -c, retaining stdout, exit code and manifest SHA256.',
                  'Root verifies final payload coverage with the documented self-reference exclusions before committing/pushing.',
              ]}

    def check(name, passed, observed=None):
        c = {'name': name, 'passed': bool(passed)}
        if observed is not None: c['observed'] = observed
        review['checks'].append(c)

    try:
        index = read(E / 'archive-index.json')
        report = read(E / 'report.json')
        bridge = read(E / 'publication-source-bridge.json')
        bindings = read(E / 'artifact-bindings.json')
        summary = read(E / 'source-summary.json')
        proof = read(E / 'review/native-review.json')
        baseline = read(O / 'source/kernel-before.json')
        root_lock = read(R / 'support/upstream-lock.json')
        previous_lock = json.loads(git('show', P + ':support/upstream-lock.json'))
        check('all_publication_source_identities_bind_native_producer',
              report['producer_commit'] == index['producer'] == bindings['producer'] == bridge['native_producer'] == summary['head'] == proof['execution_head'] == P
              and report['integrated_main'] == M and report['project_tree'] == bridge['native_project_tree'] == baseline['project_tree']
              and report['kernel_tree'] == bridge['native_kernel_tree'] == baseline['kernel_tree'])

        manifests = {}
        archive_observations = []
        dependency_origins = {
            'dependencies/installation-2026-10-18.tar.gz': Path('/workspace/scratch/d7da9e7650f0/a01-current-runtime/runtime-current.tar.gz'),
            'dependencies/revalidation-2026-10-18.tar.gz': Path('/tmp/a01-round2-runtime.tar.gz'),
            'dependencies/revalidation-2026-10-19.tar.gz': Path('/tmp/a01-round2-runtime-resume/runtime-resume-check.tar.gz'),
        }
        archive_payloads = {}
        for entry in index['archives']:
            path = E / entry['path']
            raw = path.read_bytes()
            check(entry['path'] + '_outer_hash_size_mode', len(raw) == entry['size'] and sha(raw) == entry['sha256']
                  and stat.S_IMODE(path.stat().st_mode) == int(entry['mode'], 8))
            with tarfile.open(path, 'r:*') as tf:
                members = tf.getmembers()
                names = [m.name for m in members]
                valid = len(names) == len(set(names)) and all(m.isfile() and not PurePosixPath(m.name).is_absolute()
                         and '..' not in PurePosixPath(m.name).parts for m in members)
                check(entry['path'] + '_safe_unique_regular_members', valid)
                contents = {m.name: tf.extractfile(m).read() for m in members if m.isfile()}
                archive_payloads[entry['path']] = contents
                if entry['path'].endswith('.tar.xz'):
                    manifest = json.loads(contents['ARCHIVE-MANIFEST.json'])
                    manifests[entry['path']] = manifest
                    payload = manifest['members']
                    failures = []
                    ti = {m.name: m for m in members}
                    for item in payload:
                        actual = contents[item['member']]
                        source = Path(item['source'])
                        if (len(actual) != item['size'] or sha(actual) != item['sha256']
                                or ti[item['member']].mode != int(item['mode'], 8)
                                or ti[item['member']].mtime != 0 or source.read_bytes() != actual
                                or stat.S_IMODE(source.stat().st_mode) != int(item['mode'], 8)):
                            failures.append(item['member'])
                    check(entry['path'] + '_every_payload_matches_manifest_and_original_source', not failures
                          and manifest['source_commit'] == P
                          and set(names) == {'ARCHIVE-MANIFEST.json', *[item['member'] for item in payload]}
                          and len(names) == entry['member_count'] and len(payload) == entry['payload_file_count'],
                          {'members': len(names), 'payload_files': len(payload), 'mismatches': failures})
                else:
                    check(entry['path'] + '_original_archive_bytes_preserved', raw == dependency_origins[entry['path']].read_bytes())
                    checksum_names = [name for name in names if name.endswith('/SHA256SUMS')]
                    if len(checksum_names) != 1: raise ValueError(entry['path'] + ': no unique inner checksum manifest')
                    checksum = checksum_names[0]
                    prefix = str(PurePosixPath(checksum).parent)
                    covered = []
                    failures = []
                    for line in contents[checksum].decode().splitlines():
                        expected, rel = line.split('  ', 1)
                        key = prefix + '/' + rel
                        covered.append(key)
                        if key not in contents or sha(contents[key]) != expected: failures.append(key)
                    check(entry['path'] + '_inner_checksums_cover_every_payload', not failures
                          and set(covered) == set(names) - {checksum},
                          {'members': len(names), 'checksummed_payloads': len(covered), 'mismatches': failures})
                archive_observations.append({'archive': entry['path'], 'sha256': sha(raw), 'size': len(raw), 'members': len(names)})
        review['observations']['archives'] = archive_observations

        direct_pairs = []
        for phase, label in (('kernel', 'kernel'), ('boot-retry', 'boot')):
            for name in ('command.sh', 'environment.log', 'source-inputs.json', 'manifest-cleanup.json', 'make-exit-code.txt', 'run-exit-code.txt', 'initramfs-manifest.json'):
                direct_pairs.append((O / phase / name, E / label / name))
        for source, dest in (('boot-retry/qemu.json', 'boot/qemu.json'), ('boot-retry/serial.log', 'boot/serial.log'), ('kernel/kernel.log', 'kernel/kernel.log'),
                             ('executions/boot.stdout-stderr.log', 'failures/boot-preflight/driver.log')):
            direct_pairs.append((O / source, E / dest))
        for name in ('result.json', 'environment.json', 'commands.json'):
            direct_pairs.append((O / 'ktest' / name, E / 'ktest' / name))
        for crate in ('ostd', 'aster-core'):
            for name in ('qemu.json', 'serial.log'):
                rel = f'ktest/{crate}/guests/guest-001/{name}'
                direct_pairs.append((O / rel, E / rel))
        for stage in ('kernel', 'boot', 'boot-retry', 'ktest'):
            direct_pairs.append((O / f'executions/{stage}.json', E / f'executions/{stage}.json'))
        for source in sorted((O / 'failures').rglob('*')):
            if source.is_file(): direct_pairs.append((source, E / 'failures' / source.relative_to(O / 'failures')))
        direct_failures = [str(dest.relative_to(E)) for source, dest in direct_pairs if source.read_bytes() != dest.read_bytes()]
        check('all_direct_native_logs_receipts_and_failures_equal_originals', not direct_failures,
              {'files': len(direct_pairs), 'mismatches': direct_failures})
        check('independent_native_review_and_script_preserved',
              (E / 'review/native-review.json').read_bytes() == Path('/tmp/a01-round2-native-review/native-review.json').read_bytes()
              and (E / 'review/native-review.py').read_bytes() == Path('/tmp/a01-round2-native-review/review.py').read_bytes()
              and proof['all_checked_native_evidence_consistent'] and proof['passed_checks'] == 53 and proof['failed_checks'] == 0)

        boot = read(E / 'boot/qemu.json')
        guest_payload = archive_payloads['guest-artifacts.tar.xz']
        check('archived_boot_bytes_are_the_actually_loaded_artifacts',
              all(sha(guest_payload[name]) == boot['artifacts'][flag]['sha256']
                  and len(guest_payload[name]) == boot['artifacts'][flag]['size']
                  for flag, name in (('-kernel', 'boot/kernel.elf'), ('-initrd', 'boot/initramfs.cpio.gz'), ('-bios', 'firmware/bios.bin'))))
        check('first_build_and_report_boot_hash_size_argv_bindings',
              guest_payload['boot/kernel.elf'] == Path(bindings['first_kernel']['frozen']['path']).read_bytes()
              and report['native_build']['first_elf']['sha256'] == report['boot']['artifact_sha256'] == sha(guest_payload['boot/kernel.elf'])
              and report['boot']['actual_argv'] == boot['argv']
              and (E / 'boot/qemu.command.sh').read_text() == boot['shell_command'] + '\n'
              and report['boot']['serial_sha256'] == sha((E / 'boot/serial.log').read_bytes())
              and report['boot']['serial_bytes'] == len((E / 'boot/serial.log').read_bytes()))
        check('ktest_archives_match_prelaunch_hash_and_preserve_snapshot_limitation',
              all(sha(guest_payload[f'ktest/{crate}.elf']) == bindings['ktest'][crate]['prelaunch_recorded']['sha256']
                  == bindings['ktest'][crate]['post_execution_frozen']['frozen']['sha256']
                  and bindings['ktest'][crate]['prelaunch_private_snapshot'] is False for crate in ('ostd', 'aster-core'))
              and 'not private prelaunch copies' in report['kernel_tests']['ktest_snapshot_scope'])
        original_counts = read(O / 'ktest/result.json')
        counts = [c['guests'][0] for c in original_counts['crates']]
        k = report['kernel_tests']
        check('reported_counts_are_original_full_crate_guest_counts', k['crates'] == counts
              and k['reported_passed'] == sum(c['passed'] for c in counts) == 390
              and k['soft_skipped'] == sum(c['soft_skipped'] for c in counts) == 3
              and k['exercised_passed_lower_bound'] == sum(c['exercised_passed_lower_bound'] for c in counts) == 387
              and k['failed'] == k['filtered'] == 0 and k['new_cpu_config_tests_executed_and_passed'] == 9)
        check('report_current_failures_and_scope_match_original_receipts',
              report['failures']['first_boot_driver_exit'] == read(O / 'executions/boot.json')['exit_code'] == 1
              and report['failures']['first_boot_launched_make_or_qemu'] is False
              and report['failures']['current_public_manifest_present'] is True
              and report['failures']['whole_worktree_current_clean'] is False
              and report['failures']['writer_identified'] is False
              and report['boot']['boot_stage_reused_fresh_target'] is True
              and report['boot']['separate_second_cold_build_claimed'] is False)
        dependency = read(E / 'dependencies/current-summary.json')
        check('dependency_date_reuse_and_current_counts_are_accurate',
              report['dependencies']['new_installation_for_this_run'] is False and dependency['no_installation_performed'] is True
              and dependency['commands']['passed'] == report['dependencies']['current_commands_passed'] == 13
              and dependency['effective_binaries_and_libraries']['passed'] == report['dependencies']['binaries_and_libraries_matched'] == 70
              and dependency['qemu_current_libraries']['passed'] == report['dependencies']['qemu_dynamic_libraries_matched'] == 48
              and dependency['artifacts']['passed'] == report['dependencies']['firmware_busybox_vdso_initramfs_matched'] == 4)

        changed = []
        for item in baseline['files']:
            path = R / item['path']
            s = path.lstat()
            raw = os.fsencode(os.readlink(path)) if stat.S_ISLNK(s.st_mode) else path.read_bytes()
            mode = '120000' if stat.S_ISLNK(s.st_mode) else '100755' if s.st_mode & 0o111 else '100644'
            if sha(raw) != item['sha256'] or mode != item['worktree_mode']: changed.append(item['path'])
        check('publication_bridge_has_exactly_two_metadata_exceptions',
              set(changed) == {'support/build/README.md', 'support/upstream-lock.json'}
              and set(changed) == {x['path'] for x in bridge['metadata_exceptions']}
              and bridge['selected_inputs'] == len(baseline['files']) == 3014
              and bridge['unchanged_selected_inputs'] == len(baseline['files']) - len(changed) == 3012
              and bridge['new_native_executions_for_reporting_commit'] == 0, changed)
        check('bridge_exception_after_hashes_and_modes_bind_current_files',
              all(sha((R / c['path']).read_bytes()) == c['after']['sha256']
                  and hashlib.sha1(f"blob {(R / c['path']).stat().st_size}\0".encode() + (R / c['path']).read_bytes()).hexdigest() == c['after']['git_blob']
                  and (R / c['path']).stat().st_size == c['after']['size'] for c in bridge['metadata_exceptions']))
        reporting_fields = {'native_boot_history', 'latest_native_boot', 'native_validation_history', 'latest_native_validation',
                            'latest_main_source_integration', 'kernel_mode_regression_history', 'kernel_mode_regression'}
        def without_reporting(value):
            value = copy.deepcopy(value)
            value.pop('native_build_environment', None)
            for field in reporting_fields: value['kernel'].pop(field, None)
            return value
        check('upstream_lock_all_nonreporting_fields_preserved', without_reporting(root_lock) == without_reporting(previous_lock))
        for history, current in (('native_boot_history', 'latest_native_boot'), ('native_validation_history', 'latest_native_validation'), ('kernel_mode_regression_history', 'kernel_mode_regression')):
            check(history + '_appends_previous_current_without_rewriting_history',
                  root_lock['kernel'][history] == previous_lock['kernel'].get(history, []) + [previous_lock['kernel'][current]])
        lk = root_lock['kernel']
        check('lock_latest_source_and_kernel_counts_match_current_report',
              lk['latest_native_boot']['code_commit'] == lk['latest_native_validation']['source_commit'] == lk['kernel_mode_regression']['code_commit'] == P
              and lk['latest_native_boot']['boot_sha256'] == report['boot']['artifact_sha256']
              and lk['latest_native_validation']['base_main'] == M
              and lk['latest_native_validation']['kernel_mode_reported_passed'] == lk['kernel_mode_regression']['reported_passed'] == 390
              and lk['latest_native_validation']['kernel_mode_exercised_passed_lower_bound'] == lk['kernel_mode_regression']['exercised_passed_lower_bound'] == 387
              and lk['latest_native_validation']['whole_worktree_current_clean'] is False
              and lk['latest_native_validation']['fresh_dependency_installation'] is False
              and lk['latest_native_boot']['first_attempt_failed_before_qemu'] is True)

        tracked_changes = git('diff', '--name-only', P).decode().splitlines()
        staged_changes = git('diff', '--cached', '--name-only').decode().splitlines()
        check('tracked_and_staged_changes_stay_in_A01_scope',
              all(p == 'support/upstream-lock.json' or p.startswith('support/build/') for p in tracked_changes + staged_changes),
              {'tracked_changes': tracked_changes, 'staged_changes_at_review': staged_changes})
        untracked = git('ls-files', '--others', '--exclude-standard').decode().splitlines()
        foreign = 'kernel/asterinas/kernel/OSDK.toml'
        check('only_foreign_untracked_manifest_is_outside_proposed_A01_payload',
              all(p.startswith('support/build/evidence/2026-10-19-mainf9/') or p == foreign for p in untracked)
              and foreign not in staged_changes,
              {'untracked_count': len(untracked), 'foreign_manifest_untracked': foreign in untracked})
        check('root_README_zero_and_no_kernel_ABI_diff', (R / 'README.md').stat().st_size == 0
              and not git('diff', P, '--name-only', '--', 'kernel/asterinas', 'libs').strip())

        links = []
        for doc in (E / 'REPORT.md', E / 'HANDOFF.md', R / 'support/build/README.md'):
            body = re.sub(r'^```.*?^```\s*$', '', doc.read_text(), flags=re.MULTILINE | re.DOTALL)
            for raw_target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', body):
                target = raw_target.strip().split(' "', 1)[0].strip('<>')
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path: continue
                path = (doc.parent / unquote(parsed.path)).resolve()
                exists = path.exists()
                resolution = 'actual_local_path' if exists else 'missing'
                try: relative = path.relative_to(R).as_posix()
                except ValueError: relative = None
                is_new_delivery = relative is not None and relative.startswith('support/build/evidence/2026-10-19-mainf9/')
                if not exists and relative and not is_new_delivery:
                    probe = subprocess.run(['git', '-C', str(R), 'cat-file', '-e', P + ':' + relative], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
                    if probe.returncode == 0: exists, resolution = True, 'historical_object_in_Git_sparse_checkout'
                links.append({'document': str(doc.relative_to(R)), 'target': target, 'resolved': exists, 'resolution': resolution})
        check('all_key_local_Markdown_links_resolve_with_sparse_history_handling', all(x['resolved'] for x in links),
              {'links': len(links), 'missing': [x for x in links if not x['resolved']],
               'historical_Git_only_links': sum(x['resolution'].startswith('historical') for x in links)})
        review['observations']['local_links'] = links
        prose = (E / 'REPORT.md').read_text()
        handoff = (E / 'HANDOFF.md').read_text()
        check('read_report_explicitly_preserves_native_acceptance_limits',
              'No whole-worktree-clean or continuously clean workspace claim' in prose
              and 'not described as prelaunch private snapshots' in prose
              and 'not relabeled as a new October 19 installation' in prose
              and 'No new full OSDK host/debug/coverage matrix' in prose
              and '没有重跑' in handoff and '3,014' in handoff and '387' in handoff)
        review['observations']['reviewed_prose_sha256'] = {
            str(path.relative_to(R)): sha(path.read_bytes()) for path in (E / 'REPORT.md', E / 'HANDOFF.md', R / 'support/build/README.md')}
        review['observations']['final_checksum_files_at_review'] = {
            name: (E / name).exists() for name in ('SHA256SUMS', 'review/checksum-verification.json')}
        review['observations']['checksum_ordering'] = 'Intentionally pending until this review joins the payload; root must execute the declared final seal before publication. Not a failed native test or a completed seal.'
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.SubprocessError) as error:
        check('review_completed_without_invalid_or_missing_required_inputs', False, f'{type(error).__name__}: {error}')
    review['finished_at'] = now()
    review['script_sha256'] = sha(Path(__file__).read_bytes())
    review['passed_checks'] = sum(c['passed'] for c in review['checks'])
    review['failed_checks'] = len(review['checks']) - review['passed_checks']
    review['ready_for_final_sealing'] = review['failed_checks'] == 0
    review['final_seal_executed_by_reviewer'] = False
    print(json.dumps(review, indent=2))
    return 0 if review['ready_for_final_sealing'] else 1


if __name__ == '__main__': raise SystemExit(main())
