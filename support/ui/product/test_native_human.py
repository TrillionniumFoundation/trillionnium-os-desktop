"""Local provider trust-boundary tests, not production Root qualification."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import native_human as human


class HumanProviderTests(unittest.TestCase):
    def setUp(self):
        self.session = dict(Id='19', User='1000', Active='yes', State='active',
                            Remote='no', Class='user', Type='wayland', Leader='234', Seat='seat0')
        self.template = dict(schema_version=1, program='/opt/trill/trill-ui',
                             program_sha256='a' * 64, arguments=[], working_directory='/opt/trill',
                             environment={}, socket_path='/run/trill/text.sock', route={},
                             human_lifetime_ms=300000, can_interrupt=True,
                             can_resolve_approvals=False)
        self.config = dict(peer_uid=1000, writer=dict(authority_lease=dict(
            revision=7, expires_at_unix_ms=800000)))

    def profile(self, template=None, config=None):
        return human.profile_from_verified_session(
            self.template if template is None else template,
            self.config if config is None else config, self.session,
            'a' * 32, '11111111-2222-3333-4444-555555555555', 456, 600000)

    def test_session_requires_active_physical_original_owner(self):
        human.validate_session(self.session, 1000)
        for key, value in [('User', '1001'), ('Active', 'no'), ('State', 'closing'),
                           ('Remote', 'yes'), ('Class', 'greeter'), ('Type', 'tty'),
                           ('Seat', ''), ('Leader', '0')]:
            with self.subTest(key=key), self.assertRaises(human.Refused):
                human.validate_session(dict(self.session, **{key: value}), 1000)

    def test_no_template_can_supply_human_identity_or_revision(self):
        for field in ['principal_id', 'session_id', 'permission_revision', 'expires_at_ms']:
            with self.subTest(field=field), self.assertRaises(human.Refused):
                self.profile(dict(self.template, **{field: 'caller-input'}))

    def test_profile_is_bounded_by_original_lease_and_live_session(self):
        original = self.profile()
        self.assertEqual(original['expires_at_ms'], 800000)
        self.assertEqual(original['permission_revision'], 7)
        self.assertNotIn('human_lifetime_ms', original)
        self.config['writer']['authority_lease']['expires_at_unix_ms'] = 1000000
        self.assertEqual(self.profile()['expires_at_ms'], 900000)
        self.session['Id'] = '20'
        self.assertNotEqual(self.profile()['session_id'], original['session_id'])
        self.assertEqual(self.profile()['principal_id'], original['principal_id'])

    def test_bool_and_unbounded_or_expired_fields_are_rejected(self):
        for key, value in [('schema_version', True), ('human_lifetime_ms', True),
                           ('human_lifetime_ms', 300001), ('human_lifetime_ms', 0),
                           ('can_interrupt', 1), ('can_resolve_approvals', 'yes')]:
            with self.subTest(key=key, value=value), self.assertRaises(human.Refused):
                self.profile(dict(self.template, **{key: value}))
        for key, value in [('revision', True), ('revision', 0),
                           ('expires_at_unix_ms', True), ('expires_at_unix_ms', 600000)]:
            config = copy.deepcopy(self.config)
            config['writer']['authority_lease'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(human.Refused):
                self.profile(config=config)
        for writer in [None, [], {'authority_lease': None}]:
            with self.subTest(writer=writer), self.assertRaises(human.Refused):
                self.profile(config=dict(self.config, writer=writer))

    def test_duplicate_input_and_ambiguous_local_session_are_rejected(self):
        with self.assertRaises(human.Refused):
            json.loads('{"peer_uid":1000,"peer_uid":1001}', object_pairs_hook=human.no_duplicates)
        def logind(arguments):
            if arguments[0] == 'list-sessions':
                return '19 1000 user seat0\n20 1000 user seat1\n'
            return '\n'.join(f'{key}={value}' for key, value in
                             dict(self.session, Id=arguments[1]).items())
        with patch.object(human, 'loginctl', side_effect=logind):
            with self.assertRaises(human.Refused):
                human.local_session(1000)
            self.assertEqual(human.local_session(1000, '19'), self.session)

    @unittest.skipUnless(hasattr(os, 'pidfd_open'), 'Linux pidfd API required')
    def test_actual_inherited_pidfd_is_checked_and_exit_is_terminal(self):
        child = subprocess.Popen(['/usr/bin/cat'], stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        descriptor = os.pidfd_open(child.pid)
        try:
            human.inherited_owner(descriptor, {'peer_pid': child.pid})
            with self.assertRaises(human.Refused):
                human.inherited_owner(descriptor, {'peer_pid': child.pid + 1})
            with open('/dev/null', 'rb') as ordinary:
                with self.assertRaises(human.Refused):
                    human.inherited_owner(ordinary.fileno(), {'peer_pid': child.pid})
            child.stdin.close()
            child.wait(timeout=3)
            with self.assertRaises(human.Refused):
                human.alive(descriptor)
        finally:
            child.stdin.close()
            child.wait(timeout=3)
            os.close(descriptor)

    @unittest.skipIf(os.geteuid() == 0, 'This case checks actual non-Root refusal')
    def test_actual_user_cannot_invoke_root_provider(self):
        with self.assertRaisesRegex(human.Refused, 'Root administrator'):
            human.prepare(None)


@unittest.skipUnless(os.geteuid() == 0, 'These file cases require explicit real Root test execution')
class ProtectedFileTests(unittest.TestCase):
    def test_actual_protected_read_refuses_symlink_hardlink_and_shared_mode(self):
        with tempfile.TemporaryDirectory(dir='/run') as directory:
            root = Path(directory)
            root.chmod(0o700)
            path = root / 'config.json'
            path.write_text('{"peer_uid":1000}')
            path.chmod(0o600)
            self.assertEqual(human.read_root_json(path), {'peer_uid': 1000})
            link = root / 'link.json'
            link.symlink_to(path)
            with self.assertRaises(OSError):
                human.read_root_json(link)
            hardlink = root / 'hard.json'
            os.link(path, hardlink)
            with self.assertRaises(human.Refused):
                human.read_root_json(path)
            hardlink.unlink()
            path.chmod(0o644)
            with self.assertRaises(human.Refused):
                human.read_root_json(path)

    def test_actual_read_rejects_duplicates_and_parent_fsync_works(self):
        with tempfile.TemporaryDirectory(dir='/run') as directory:
            path = Path(directory) / 'duplicate.json'
            path.write_text('{"x":1,"x":2}')
            path.chmod(0o600)
            with self.assertRaises(human.Refused):
                human.read_root_json(path)
            human.sync_parent(path)

    def test_root_files_below_shared_ancestry_are_refused(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as directory:
            path = Path(directory) / 'config.json'
            path.write_text('{"peer_uid":1000}')
            path.chmod(0o600)
            with self.assertRaisesRegex(human.Refused, 'Root custody'):
                human.read_root_json(path)


if __name__ == '__main__':
    unittest.main()
