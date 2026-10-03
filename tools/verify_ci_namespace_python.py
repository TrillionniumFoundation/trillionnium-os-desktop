#!/usr/bin/env python3
"""Finite CI setup correspondence only; no privileged setup or host probe."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
try:
    from . import verify_approved_native_startup as reader
    from . import verify_ci_required_contexts as contexts
except ImportError:
    import verify_approved_native_startup as reader
    import verify_ci_required_contexts as contexts
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/ci-namespace-python.v1.json"
EXPECTED = {'schema': 'hepta.ci-namespace-python.v1',
 'status': 'CI_CONFIGURATION_CANDIDATE_NOT_HOSTED_QUALIFIED',
 'platform': 'Linux-Ubuntu24.04',
 'jobs': [{'workflow': '.github/workflows/ci.yml', 'job_id': 'repository-contracts'},
          {'workflow': '.github/workflows/ci.yml',
           'job_id': 'repository-contracts-prospective-merge'},
          {'workflow': '.github/workflows/g2-approved-native-startup.yml',
           'job_id': 'source-prospective'},
          {'workflow': '.github/workflows/g2-native-product-owner.yml',
           'job_id': 'source-prospective'}],
 'scope': 'temporary named debug profile attaches only the unique root-owned real interpreter copy '
          'for this CI job',
 'worker_and_original_tests_changed': False,
 'corpus_as_host_root': False,
 'global_AppArmor_or_sysctl_changes': False,
 'interpreter_filecap_or_setid': False,
 'namespace_or_security_fallback': False,
 'production_activation': False,
 'hosted_qualified': False,
 'G1_closed': False,
 'production_ready': False,
 'entrypoints': {'setup': 'python3 tools/ci_namespace_python.py setup',
                 'cleanup': '/usr/bin/python3.12 tools/ci_namespace_python.py cleanup'},
 'identity': {'normal_runner_uid_gid': 'captured from actual normal process and checked against '
                                       'actual sudo caller',
              'interpreter': '/usr/bin/python3.12 whole byte copy; fixed provider correspondence '
                             'and stdlib prefix readback',
              'allocation': '/var/lib/hepta-ci-g1-<bounded-run>-<bounded-attempt>-<fixed-workflow>-<literal-job>; '
                            'root0:0 mode0755 create-new; no other global interpreter attachment',
              'workflow_ref': 'actual runner GITHUB_WORKFLOW_REF under fixed repository and three '
                              'literal filenames; whole suffix bounded to original main/codex push '
                              'or positive numbered pull merge ref',
              'retirement_ledger': 'unique derived /var/lib/.<profile>.ledger; root0:0 mode0700 '
                                   'with mode0600 create-new same-inode lock/state; no secrets, '
                                   'interpreter bytes or active profile retained',
              'root_operation_launcher': 'fixed /usr/bin/sudo --non-interactive /usr/bin/setsid '
                                         '--fork --wait -- /usr/bin/python3.12 and reviewed '
                                         'helper; both provider whole bytes/devino/non-setid/no '
                                         'filecaps checked before and after; root actual parent '
                                         'UID0/exe/argv and PID/start handoff checked'},
 'profile': {'mode': 'temporary CI-only unconfined debugging profile with explicit userns '
                     'permission',
             'template': '.github/apparmor/hepta-ci-namespace-python.v1.profile',
             'initial_host_privilege_gained': False,
             'production_confinement_profile': False,
             'entire_host_Python_exempted': False},
 'acceptance': {'same_host_uid_gid': True,
                'before_after_global_AA_sysctl_label_readback': True,
                'real_sealed_memfd_original_body_preserved': True,
                'readonly_distinct_inode_EROFS_original_body_preserved': True,
                'after_exec_five_caps_zero_NNP_original_body_preserved': True,
                'unavailable_readback_is_success': False,
                'full_original_corpus_required': True,
                'cleanup_error_is_success': False,
                'live_owned_interpreter_or_profile_process_refuses_cleanup': True},
 'bounds': {'maximum_interpreter_bytes': 67108864,
            'maximum_state_bytes': 2097152,
            'maximum_proc_visible_entries': 65536,
            'each_setup_cleanup_subcommand_timeout_seconds': 30,
            'old_job_timeout_minutes': 20,
            'maximum_ledger_bytes': 16384,
            'maximum_proc_cmdline_bytes': 65536,
            'maximum_proc_maps_bytes': 4194304},
 'source_sha256': {'tools/ci_namespace_python.py': '0f269ea663505db04a57ed02484c8392cf8830cae05d4a78b2b3be497889bbce',
                   '.github/apparmor/hepta-ci-namespace-python.v1.profile': '9d6bf7dc994cc4b7e19444c1d1b633327ccc22bb202c4c7685a3125ae0b157be',
                   '.github/workflows/ci.yml': 'be49b338e5bc425b66c0eb27e785dd39a35d3120b9a8749bdfa33b2313768826',
                   '.github/workflows/g2-approved-native-startup.yml': 'a484cdf5a3c9699031467e3e11d8b28adb3129148024edc4457166c22bd6401a',
                   '.github/workflows/g2-native-product-owner.yml': '7b2d84837afc9b3e07f24d07d3f6860fb4392006b0b4631b4c55cb4b6b62c40f'},
 'non_claims': ['original99c hosted failure remains',
                'localRoot success is not hosted qualification',
                'no new crypto or Cargo consumption proof',
                'no NativeHealth installed human hardware or production qualification'],
 'workflows_inverse': {'.github/workflows/ci.yml': {'original_sha256': 'a2392184e4099c5488be1c90ed886d9eefd9a1f88e183a0d94b83670a02638fe',
                                                    'setup': '      - name: Provision job-private '
                                                             'CI namespace Python\n'
                                                             '        id: namespace_python_setup\n'
                                                             '        run: |\n'
                                                             '          set -euo pipefail\n'
                                                             '          python3 '
                                                             'tools/verify_ci_namespace_python.py\n'
                                                             '          python3 '
                                                             'tools/ci_namespace_python.py setup\n'
                                                             '\n',
                                                    'cleanup': '      - name: Remove only owned CI '
                                                               'namespace Python and profile\n'
                                                               '        if: always()\n'
                                                               '        run: /usr/bin/python3.12 '
                                                               'tools/ci_namespace_python.py '
                                                               'cleanup\n'
                                                               '\n',
                                                    'count_each': 2,
                                                    'positive_paths': []},
                       '.github/workflows/g2-approved-native-startup.yml': {'original_sha256': '5ad5c3ecc646082f8c66c4d09d4963e03c1aba34ad9fa2b0507bf21a2b785228',
                                                                            'setup': '      - '
                                                                                     'name: '
                                                                                     'Provision '
                                                                                     'job-private '
                                                                                     'CI namespace '
                                                                                     'Python\n'
                                                                                     '        id: '
                                                                                     'namespace_python_setup\n'
                                                                                     '        run: '
                                                                                     '|\n'
                                                                                     '          '
                                                                                     'set -euo '
                                                                                     'pipefail\n'
                                                                                     '          '
                                                                                     'python3 '
                                                                                     'tools/verify_ci_namespace_python.py\n'
                                                                                     '          '
                                                                                     'python3 '
                                                                                     'tools/ci_namespace_python.py '
                                                                                     'setup\n'
                                                                                     '\n',
                                                                            'cleanup': '      - '
                                                                                       'name: '
                                                                                       'Remove '
                                                                                       'only owned '
                                                                                       'CI '
                                                                                       'namespace '
                                                                                       'Python and '
                                                                                       'profile\n'
                                                                                       '        '
                                                                                       'if: '
                                                                                       'always()\n'
                                                                                       '        '
                                                                                       'run: '
                                                                                       '/usr/bin/python3.12 '
                                                                                       'tools/ci_namespace_python.py '
                                                                                       'cleanup\n'
                                                                                       '\n',
                                                                            'count_each': 1,
                                                                            'positive_paths': ['.github/apparmor/hepta-ci-namespace-python.v1.profile',
                                                                                               'tools/ci_namespace_python.py',
                                                                                               'contracts/ci-namespace-python.v1.json',
                                                                                               'tools/verify_ci_namespace_python.py',
                                                                                               'tests/test_ci_namespace_python.py',
                                                                                               'tools/verify_ci_required_contexts.py']},
                       '.github/workflows/g2-native-product-owner.yml': {'original_sha256': 'afbc7eab3d053fbdd935c3a40c33e0bd140f08440b4a83bce163d9e5736ac9d3',
                                                                         'setup': '      - name: '
                                                                                  'Provision '
                                                                                  'job-private CI '
                                                                                  'namespace '
                                                                                  'Python\n'
                                                                                  '        id: '
                                                                                  'namespace_python_setup\n'
                                                                                  '        run: |\n'
                                                                                  '          set '
                                                                                  '-euo pipefail\n'
                                                                                  '          '
                                                                                  'python3 '
                                                                                  'tools/verify_ci_namespace_python.py\n'
                                                                                  '          '
                                                                                  'python3 '
                                                                                  'tools/ci_namespace_python.py '
                                                                                  'setup\n'
                                                                                  '\n',
                                                                         'cleanup': '      - name: '
                                                                                    'Remove only '
                                                                                    'owned CI '
                                                                                    'namespace '
                                                                                    'Python and '
                                                                                    'profile\n'
                                                                                    '        if: '
                                                                                    'always()\n'
                                                                                    '        run: '
                                                                                    '/usr/bin/python3.12 '
                                                                                    'tools/ci_namespace_python.py '
                                                                                    'cleanup\n'
                                                                                    '\n',
                                                                         'count_each': 1,
                                                                         'positive_paths': ['.github/apparmor/hepta-ci-namespace-python.v1.profile',
                                                                                            'tools/ci_namespace_python.py',
                                                                                            'contracts/ci-namespace-python.v1.json',
                                                                                            'tools/verify_ci_namespace_python.py',
                                                                                            'tests/test_ci_namespace_python.py',
                                                                                            'tools/verify_ci_required_contexts.py']}},
 'lifecycle': {'serialization': 'create-new root-owned ledger then nonblocking same-inode flock '
                                'before profile/parser; phase state pins actual lock identity',
               'phases': ['STARTED', 'READY', 'RETIRED'],
               'actual_setup_worker': 'actual Root writer PID=PGID=SID and independently read '
                                      'start ticks, UID0 and selfPython devino, plus real fixed '
                                      'setsid supervisor PID/start/PGID/SID/UID0/exe/argv, all '
                                      'registered before parser',
               'direct_child_timeout_proves_root_descendants_dead': False,
               'cleanup_requirements': 'bounded actual worker PID/start/session/group and private '
                                       'executable inode/label/mappings absent, before unload and '
                                       'after unload/retirement; unreadable or unknown state '
                                       'refuses',
               'late_setup': 'early cleanup leaves RETIRED deny tombstone; existing ledger forbids '
                             'every setup; phase revival forbidden',
               'retired_ledger_retained': True,
               'all_root_state_deleted': False,
               'broad_or_arbitrary_process_kill': False,
               'retirement_ledger_is_runtime_or_release_authority': False,
               'actual_cleanup_worker': 'single finite cleanup_worker registered under same inode '
                                        'lock before any unload; prior writer and supervisor '
                                        'groups must be empty; no same-writer handoff or phase '
                                        'revival',
               'parser_inherits_recorded_root_writer_session': True,
               'root_marker_is_final_cleanup_success': False,
               'in_worker_exclusion': 'only exact currently verifying writer '
                                      'PID/start/PGID/SID/UID/exe, never its child or entire '
                                      'group; current waiting supervisor is a separate recorded '
                                      'session whose exit is checked after wait',
               'normal_runner_success': 'only after actual sudo/setsid direct child terminal and '
                                        'bounded kernel inventory of both returned actual '
                                        'writer/supervisor sessions/groups empty; no exclusions; '
                                        'unavailable related readback refuses',
               'retired_ledger_proves_root_descendants_dead': False},
 'command_capture': {'fixed_commands_only': True,
                     'each_stdout_stderr_post_completion_refusal_bytes': 2097152,
                     'strict_inflight_output_or_memory_bound': False,
                     'timeout_seconds': 30,
                     'timeout_waits_direct_child_only': True,
                     'root_descendant_absence_proven_by_timeout': False,
                     'ledger_and_process_readback_required_before_cleanup': True,
                     'root_parser_starts_new_session': False,
                     'normal_runner_sudo_starts_new_session': True,
                     'method': 'owned anonymous temporary files; completed child output read at '
                               'most LIMIT+1 per stream; no descendant PIPE EOF wait',
                     'strict_inflight_output_or_disk_bound': False}}


def inputs(root=ROOT):
    paths = list(EXPECTED["source_sha256"]) + ["contracts/ci-required-contexts.v1.json"]
    return {path: reader.source(root, path) for path in paths}


def check(value, texts):
    reader.typed_equal(value, EXPECTED)
    if type(texts) is not dict or set(texts) != set(EXPECTED["source_sha256"]) | {"contracts/ci-required-contexts.v1.json"}:
        raise ValueError("closed CI setup inputs differ")
    for path, wanted in EXPECTED["source_sha256"].items():
        if type(texts[path]) is not str or hashlib.sha256(texts[path].encode()).hexdigest() != wanted:
            raise ValueError("reviewed complete CI setup source differs")
    catalog = contexts.load_json_strict(texts["contracts/ci-required-contexts.v1.json"].encode())
    for path, inverse in EXPECTED["workflows_inverse"].items():
        text = texts[path]
        for block in [inverse["setup"], inverse["cleanup"]]:
            if text.count(block) != inverse["count_each"]:
                raise ValueError("CI setup/always-cleanup detached")
            text = text.replace(block, "")
        for value in inverse["positive_paths"]:
            literal = '      - ' + json.dumps(value) + '\n'
            if text.count(literal) != 2: raise ValueError("CI input registration differs")
            text = text.replace(literal, "")
        if hashlib.sha256(text.encode()).hexdigest() != inverse["original_sha256"]:
            raise ValueError("original complete CI workflow differs")
        digest, jobs, events, filtered, conditional = contexts.inventory(path, texts[path])
        contexts.exact(catalog["workflows"][path],
                       {"body_without_job_display_names_sha256": digest, "jobs": jobs,
                        "trigger_events": events, "path_filtered": filtered,
                        "conditional_jobs": conditional}, "CI setup exact contexts")
        if set(events) != {"push", "pull_request"} or (path == ".github/workflows/ci.yml" and filtered):
            raise ValueError("CI input original event domain differs")



def validate(root=ROOT):
    check(reader.load(root / CONTRACT), inputs(root))


def main():
    try: validate()
    except (OSError, ValueError, KeyError, UnicodeError):
        print("CI_NAMESPACE_PYTHON_SOURCE_INVALID", file=sys.stderr); return 1
    print(json.dumps({"scope": "CI_CONFIGURATION_SOURCE_ONLY", "hosted_qualified": False,
                      "global_security_changed": False, "production_ready": False})); return 0


if __name__ == "__main__":
    raise SystemExit(main())
