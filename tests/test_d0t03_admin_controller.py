from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/d0t03_admin_controller.py"
spec = importlib.util.spec_from_file_location('d0t03_admin_controller', MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def closed_protection() -> tuple[dict, dict]:
    payload = module.branch_protection_payload()
    protection = {
        **payload,
        'enforce_admins': {'enabled': True},
        'required_conversation_resolution': {'enabled': True},
        'allow_force_pushes': {'enabled': False},
        'allow_deletions': {'enabled': False},
        'required_signatures': {'enabled': True},
    }
    return {'name': 'main', 'protected': True}, protection


def closed_accounts() -> dict:
    return {
        login: {'login': login, 'id': reviewer_id, 'type': 'User'}
        for login, reviewer_id in module.REVIEWER_ACCOUNTS.items()
    }


def closed_environment(name: str) -> dict:
    return {
        'name': name,
        'deployment_branch_policy': {
            'protected_branches': True,
            'custom_branch_policies': False,
        },
        'protection_rules': [
            {
                'type': 'required_reviewers',
                'prevent_self_review': True,
                'reviewers': [
                    {
                        'type': 'User',
                        'reviewer': {
                            'id': reviewer_id,
                            'login': login,
                            'type': 'User',
                        },
                    }
                    for login, reviewer_id in module.REVIEWER_ACCOUNTS.items()
                ],
            }
        ],
    }


def closed_probe_packet(main_sha: str) -> dict:
    roles = {
        role: [{'id': 1000 + index, 'login': f'{role}-identity'}]
        for index, role in enumerate(module.SEPARATED_ROLES)
    }
    lookup = {role: values[0] for role, values in roles.items()}
    probes = []
    for index, (probe_id, (result, operation, role)) in enumerate(
        module.PROBE_EXPECTATIONS.items()
    ):
        actor = lookup[role]
        probes.append(
            {
                'id': probe_id,
                'result': result,
                'operation': operation,
                'actor_id': actor['id'],
                'actor_login': actor['login'],
                'actor_role': role,
                'observed_at': '2026-09-10T11:30:00Z',
                'subject_sha': main_sha,
                'observation_id': f'd0t03:{probe_id}:{index:04d}',
            }
        )
    return {
        'schema_version': module.PROBE_SCHEMA_VERSION,
        'repository': module.REPOSITORY,
        'main_sha': main_sha,
        'issued_at': '2026-09-10T12:00:00Z',
        'evidence_authority': module.PROBE_EVIDENCE_AUTHORITY,
        'attestor': {
            'id': 999999,
            'login': 'independent-attestor',
            'role': 'independent_governance_attestor',
        },
        'probes': probes,
        'role_identities': roles,
    }


def closed_ruleset() -> dict:
    payload = module.ruleset_payload()
    payload['id'] = 77
    payload['source_type'] = 'Repository'
    return payload


def closed_repository() -> dict:
    return {**module.repository_merge_payload(), 'name': 'trillionnium-os-desktop'}


class FakeReadbackApi:
    def __init__(self, first_sha: str, final_sha: str | None = None):
        self.first_sha = first_sha
        self.final_sha = final_sha or first_sha
        self.branch_reads = 0

    def __call__(self, arguments, body):
        path = arguments[-1]
        if path == f'repos/{module.REPOSITORY}':
            return module.ApiResult(0, closed_repository(), '')
        if path == f'repos/{module.REPOSITORY}/branches/{module.DEFAULT_BRANCH}':
            self.branch_reads += 1
            sha = self.first_sha if self.branch_reads == 1 else self.final_sha
            return module.ApiResult(
                0,
                {'name': 'main', 'protected': True, 'commit': {'sha': sha}},
                '',
            )
        if path.endswith('/protection/required_signatures'):
            return module.ApiResult(0, {'enabled': True}, '')
        if path.endswith('/protection'):
            _branch, protection = closed_protection()
            protection.pop('required_signatures')
            return module.ApiResult(0, protection, '')
        if path.endswith('/rulesets?includes_parents=true'):
            return module.ApiResult(0, [{'id': 77, 'name': module.RULESET_NAME}], '')
        if path.endswith('/rulesets/77'):
            return module.ApiResult(0, closed_ruleset(), '')
        if path.startswith('users/'):
            login = path.split('/', 1)[1]
            return module.ApiResult(0, closed_accounts()[login], '')
        marker = f'repos/{module.REPOSITORY}/environments/'
        if path.startswith(marker):
            return module.ApiResult(0, closed_environment(path[len(marker):]), '')
        return module.ApiResult(1, None, f'unexpected path: {path}')


class D0T03ControllerTests(unittest.TestCase):
    def test_static_configuration_is_closed(self) -> None:
        self.assertEqual(module.static_configuration_errors(), [])

    def test_required_checks_are_exactly_bound_to_github_actions(self) -> None:
        rules = {entry['type']: entry for entry in module.ruleset_payload()['rules']}
        checks = rules['required_status_checks']['parameters']['required_status_checks']
        self.assertEqual({entry['integration_id'] for entry in checks}, {15368})
        classic = module.branch_protection_payload()['required_status_checks']['checks']
        self.assertEqual({entry['app_id'] for entry in classic}, {15368})

    def test_ruleset_rejects_missing_duplicate_foreign_and_unexpected_bindings(self) -> None:
        for mutation in ('missing', 'duplicate', 'foreign', 'unexpected'):
            with self.subTest(mutation=mutation):
                payload = module.ruleset_payload()
                rules = {entry['type']: entry for entry in payload['rules']}
                checks = rules['required_status_checks']['parameters']['required_status_checks']
                if mutation == 'missing':
                    checks.pop()
                elif mutation == 'duplicate':
                    checks.append(dict(checks[0]))
                elif mutation == 'foreign':
                    checks[0]['integration_id'] = 7
                else:
                    checks.append({'context': 'attacker/check', 'integration_id': 15368})
                self.assertTrue(module.verify_ruleset(payload))

    def test_protection_requires_complete_exact_critical_controls(self) -> None:
        branch, protection = closed_protection()
        self.assertEqual(module.verify_protection(branch, protection), [])
        for key, expected in (
            ('required_signatures', True),
            ('allow_force_pushes', False),
            ('allow_deletions', False),
        ):
            for value in ('absent', None, 'false', {}, {'other': expected}):
                with self.subTest(key=key, value=value):
                    branch, protection = closed_protection()
                    if value == 'absent':
                        protection.pop(key)
                    else:
                        protection[key] = value
                    self.assertTrue(module.verify_protection(branch, protection))

    def test_environment_requires_exact_resolved_users_no_extras_or_teams(self) -> None:
        accounts = closed_accounts()
        for name in module.ENVIRONMENTS:
            self.assertEqual(module.verify_environment(name, closed_environment(name), accounts), [])
        extra = closed_environment('qualification')
        extra['protection_rules'][0]['reviewers'].append(
            {'type': 'User', 'reviewer': {'id': 7, 'login': 'attacker', 'type': 'User'}}
        )
        self.assertTrue(module.verify_environment('qualification', extra, accounts))
        team = closed_environment('qualification')
        team['protection_rules'][0]['reviewers'][0] = {
            'type': 'Team',
            'reviewer': {'id': module.REVIEWERS[0], 'login': 'team', 'type': 'Team'},
        }
        self.assertTrue(module.verify_environment('qualification', team, accounts))

    def test_probe_schema_uses_external_attestor_authority_not_unverified_github_claims(self) -> None:
        self.assertNotIn('evidence_api_url', module.PROBE_FIELDS)
        self.assertNotIn('evidence_sha256', module.PROBE_FIELDS)
        packet = closed_probe_packet('a' * 40)
        errors = module.validate_probe_evidence(
            packet,
            'a' * 40,
            signature_verified=True,
            public_key_sha256='b' * 64,
            expected_attestor_id=999999,
            expected_attestor_login='independent-attestor',
            now=datetime(2026, 9, 10, 12, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(errors, [])

    def test_probe_requires_signature_external_key_and_external_attestor_binding(self) -> None:
        packet = closed_probe_packet('a' * 40)
        errors = module.validate_probe_evidence(
            packet,
            'a' * 40,
            now=datetime(2026, 9, 10, 12, 5, tzinfo=timezone.utc),
        )
        joined = '\n'.join(errors)
        self.assertIn('signature', joined)
        self.assertIn('public-key digest', joined)
        self.assertIn('expected attestor id', joined)
        self.assertIn('expected attestor login', joined)
        errors = module.validate_probe_evidence(
            packet,
            'a' * 40,
            signature_verified=True,
            public_key_sha256='b' * 64,
            expected_attestor_id=123,
            expected_attestor_login='wrong',
            now=datetime(2026, 9, 10, 12, 5, tzinfo=timezone.utc),
        )
        self.assertTrue(any('externally bound identity' in error for error in errors))

    def test_probe_rejects_unrelated_subject_actor_role_stale_time_duplicate_observation(self) -> None:
        for mutation in ('subject', 'actor', 'role', 'stale', 'duplicate_observation'):
            with self.subTest(mutation=mutation):
                packet = closed_probe_packet('a' * 40)
                probe = packet['probes'][0]
                if mutation == 'subject':
                    probe['subject_sha'] = 'c' * 40
                elif mutation == 'actor':
                    probe['actor_id'] = 42
                elif mutation == 'role':
                    probe['actor_role'] = 'reviewer'
                elif mutation == 'stale':
                    packet['issued_at'] = '2026-09-01T00:00:00Z'
                else:
                    packet['probes'][1]['observation_id'] = probe['observation_id']
                errors = module.validate_probe_evidence(
                    packet,
                    'a' * 40,
                    signature_verified=True,
                    public_key_sha256='b' * 64,
                    expected_attestor_id=999999,
                    expected_attestor_login='independent-attestor',
                    now=datetime(2026, 9, 10, 12, 5, tzinfo=timezone.utc),
                )
                self.assertTrue(errors)

    def test_probe_rejects_attestor_role_overlap_and_extra_fields(self) -> None:
        packet = closed_probe_packet('a' * 40)
        packet['attestor']['id'] = packet['role_identities']['author'][0]['id']
        packet['forged'] = True
        errors = module.validate_probe_evidence(
            packet,
            'a' * 40,
            signature_verified=True,
            public_key_sha256='b' * 64,
            expected_attestor_id=999999,
            expected_attestor_login='independent-attestor',
            now=datetime(2026, 9, 10, 12, 5, tzinfo=timezone.utc),
        )
        self.assertTrue(any('top-level' in error for error in errors))
        self.assertTrue(any('not independent' in error for error in errors))

    def test_readback_rechecks_main_and_fails_on_movement(self) -> None:
        stable = module.readback(FakeReadbackApi('a' * 40))
        self.assertEqual(stable['verification_errors'], [])
        moved = module.readback(FakeReadbackApi('a' * 40, 'b' * 40))
        self.assertTrue(any('advanced during governance readback' in error for error in moved['verification_errors']))

    def test_complete_transaction_rejects_post_probe_main_movement(self) -> None:
        self.assertEqual(module.verify_transaction_final_main('a' * 40, 'a' * 40), [])
        self.assertTrue(module.verify_transaction_final_main('a' * 40, 'b' * 40))

    def test_main_never_closes_when_main_moves_after_probe_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = root / 'packet.json'
            signature = root / 'packet.sig'
            public_key = root / 'probe.pub'
            output = root / 'evidence.json'
            packet.write_text('{}\n', encoding='utf-8')
            signature.write_bytes(b'signature')
            public_key.write_bytes(b'public-key')
            args = SimpleNamespace(
                apply=False,
                output=output,
                probe_evidence=packet,
                probe_signature=signature,
                probe_public_key=public_key,
                expected_probe_public_key_sha256='b' * 64,
                expected_probe_attestor_id=999999,
                expected_probe_attestor_login='independent-attestor',
                check_config=False,
            )
            with (
                mock.patch.object(module, 'parse_args', return_value=args),
                mock.patch.object(
                    module,
                    'readback',
                    return_value={'main_sha': 'a' * 40, 'verification_errors': []},
                ),
                mock.patch.object(
                    module, 'verify_detached_signature', return_value='b' * 64
                ),
                mock.patch.object(module, 'strict_json', return_value={}),
                mock.patch.object(module, 'validate_probe_evidence', return_value=[]),
                mock.patch.object(module, 'read_current_main_sha', return_value='c' * 40),
            ):
                self.assertEqual(module.main(), 1)
            evidence = module.strict_json(output.read_text(encoding='utf-8'))
            self.assertFalse(evidence['all_gaps_closed'])
            self.assertTrue(
                any(
                    'advanced during signed-probe' in error
                    for error in evidence['probe_verification_errors']
                )
            )

    def test_detached_signature_verifier_binds_external_key_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = root / 'packet.json'
            signature = root / 'packet.sig'
            public_key = root / 'probe.pub'
            packet.write_text('{}\n', encoding='utf-8')
            signature.write_bytes(b'signature')
            public_key.write_bytes(b'public-key')
            expected = hashlib.sha256(public_key.read_bytes()).hexdigest()
            calls = []

            def runner(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, 'Verified OK', '')

            self.assertEqual(
                module.verify_detached_signature(packet, signature, public_key, expected, runner=runner),
                expected,
            )
            self.assertEqual(calls[0][0:3], ['openssl', 'dgst', '-sha256'])
            with self.assertRaises(module.GovernanceError):
                module.verify_detached_signature(packet, signature, public_key, '0' * 64, runner=runner)

    def test_strict_json_rejects_duplicates_and_non_json_constants(self) -> None:
        with self.assertRaises(module.GovernanceError):
            module.strict_json('{"a":1,"a":2}')
        for value in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(value=value), self.assertRaises(module.GovernanceError):
                module.strict_json('{"value":' + value + '}')


if __name__ == '__main__':
    unittest.main()
