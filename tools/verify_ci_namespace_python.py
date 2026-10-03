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
 'jobs': ['repository-contracts', 'repository-contracts-prospective-merge'],
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
              'allocation': '/var/lib/hepta-ci-g1-<bounded-run>-<bounded-attempt>-<literal-job>; '
                            'root0:0 mode0755 create-new; no other global interpreter attachment'},
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
            'old_job_timeout_minutes': 20},
 'source_sha256': {'tools/ci_namespace_python.py': 'a7fef49ff154ba7e0ad6151fdaf6700112337f02acfba7ccfa175c6946e5e1d6',
                   '.github/apparmor/hepta-ci-namespace-python.v1.profile': '9d6bf7dc994cc4b7e19444c1d1b633327ccc22bb202c4c7685a3125ae0b157be',
                   '.github/workflows/ci.yml': 'be49b338e5bc425b66c0eb27e785dd39a35d3120b9a8749bdfa33b2313768826'},
 'workflow_inverse': {'path': '.github/workflows/ci.yml',
                      'original_sha256': 'a2392184e4099c5488be1c90ed886d9eefd9a1f88e183a0d94b83670a02638fe',
                      'setup': '      - name: Provision job-private CI namespace Python\n'
                               '        id: namespace_python_setup\n'
                               '        run: |\n'
                               '          set -euo pipefail\n'
                               '          python3 tools/verify_ci_namespace_python.py\n'
                               '          python3 tools/ci_namespace_python.py setup\n'
                               '\n',
                      'cleanup': '      - name: Remove only owned CI namespace Python and profile\n'
                                 '        if: always()\n'
                                 '        run: /usr/bin/python3.12 tools/ci_namespace_python.py '
                                 'cleanup\n'
                                 '\n',
                      'count_each': 2},
 'non_claims': ['original99c hosted failure remains',
                'localRoot success is not hosted qualification',
                'no new crypto or Cargo consumption proof',
                'no NativeHealth installed human hardware or production qualification']}


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
    inverse = EXPECTED["workflow_inverse"]
    text = texts[inverse["path"]]
    for block in [inverse["setup"], inverse["cleanup"]]:
        if text.count(block) != inverse["count_each"]: raise ValueError("CI setup/always-cleanup detached")
        text = text.replace(block, "")
    if hashlib.sha256(text.encode()).hexdigest() != inverse["original_sha256"]:
        raise ValueError("original complete CI workflow differs")
    catalog = contexts.load_json_strict(texts["contracts/ci-required-contexts.v1.json"].encode())
    digest, jobs, events, filtered, conditional = contexts.inventory(inverse["path"], texts[inverse["path"]])
    contexts.exact(catalog["workflows"][inverse["path"]],
                   {"body_without_job_display_names_sha256": digest, "jobs": jobs,
                    "trigger_events": events, "path_filtered": filtered,
                    "conditional_jobs": conditional}, "CI setup exact contexts")
    if events != ["push", "pull_request"] or filtered:
        raise ValueError("new CI inputs require both unfiltered original events")


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
