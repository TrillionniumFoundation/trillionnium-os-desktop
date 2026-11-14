"""Filesystem controls for the cross-host receipt boundary, not APEX tests."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'audio-continuation-r1'))
import canonical_audio_import as subject
import audio_continuation_control as guard


def encoded(value):
    return (json.dumps(value, sort_keys=True) + '\n').encode()


def identity(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


class Files:
    """A real local-file witness; there is no original-host path resolver."""
    def __init__(self):
        self.read_paths = []

    def pinned(self, expected, *, contents=False, single=False):
        path = Path(expected['path'])
        self.read_paths.append(str(path))
        if path.resolve() != path:
            raise ValueError('local alias refused')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError('single regular fixture file required')
            raw = stream.read()
            if identity(before) != identity(os.fstat(stream.fileno())) or identity(before) != identity(path.lstat()):
                raise ValueError('held fixture changed')
        actual = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                  'identity': identity(before)}
        for key in ('path', 'bytes', 'sha256', 'identity'):
            if key in expected and actual[key] != expected[key]:
                raise ValueError('canonical fixture pin changed')
        return actual, raw if contents else None

    def read(self, expected, json=False):
        actual, raw = self.pinned(expected, contents=json)
        return (__import__('json').loads(raw) if json else actual), actual


class Fixture:
    def __init__(self, root, *, source_content=None, origin_host='builder', destination_host='device'):
        self.allowed = root / 'qualification'
        self.local = self.allowed / 'import-r1'
        self.local.mkdir(parents=True)
        self.io = Files()
        self.mapping = {}
        self.docs = {}
        self.paths = {
            'whole_apex': '/origin/audio/out/audio.apex',
            'qualification': '/origin/audio/qualification/result.json',
            'contents': '/origin/audio/qualification/payload-file-contents.json',
            'compiled': '/origin/audio/compiled/result.json',
            'source_manifest': '/origin/audio/qualifier/source-manifest.json',
            'source_qualifier': '/origin/audio/qualifier/qualify_audio_whole_apex.py',
            'source_join': '/origin/audio/qualifier/apex_evidence_join.py',
            'specification': '/origin/audio/qualification-spec.json',
            **{'H_' + key: '/origin/runtime/jobs/fixture-job/' + key + '.json'
               for key in ('request', 'started', 'exit', 'stdout', 'stderr')},
        }
        self.put('whole_apex', b'synthetic validator artifact; this is not an APEX\n')
        source_content = source_content or {}
        self.put('source_qualifier', source_content.get('source_qualifier', b'# Synthetic source identity fixture, never executed.\n'))
        self.put('source_join', source_content.get('source_join', b'# Synthetic dependency identity fixture, never executed.\n'))
        self.reviewed = {'qualify_audio_whole_apex.py': self.mapping['source_qualifier']['origin']['sha256'],
                         'apex_evidence_join.py': self.mapping['source_join']['origin']['sha256']}
        core = {'bytes': 7, 'sha256': hashlib.sha256(b'fixture').hexdigest()}
        self.put('contents', {'schema':'droidloom-audio-apex-file-contents-v1',
                             'payload_file_contents_match':True, 'files':{guard.CORE_PAYLOAD:core}})
        compiled = {'schema':'pocket4-audio-compiled-bridge-binding-v1', 'state':'PASS',
                    'whole_apex':self.origin('whole_apex'), 'core_payload_relative':guard.CORE_PAYLOAD,
                    'core_payload_file':core,
                    'translation_units':[{'source':x} for x in sorted(guard.REQUIRED_BRIDGE_UNITS)],
                    'actual_successful_ninja_commands_verified':True,
                    'actual_header_dependencies_verified':True, 'effective_source_input_window_verified':True}
        self.put('compiled', compiled)
        self.put('source_manifest', {'schema':'audio-whole-apex-qualification-sources-v1', 'files':{
            'qualify_audio_whole_apex.py':self.origin('source_qualifier'),
            'apex_evidence_join.py':self.origin('source_join')}})
        full_h = {'request':{'path':'/origin/full/request.json','bytes':1,'sha256':'a'*64}}
        compiled_h = {'request':{'path':'/origin/compiled/request.json','bytes':1,'sha256':'b'*64}}
        self.put('specification', {'full_generation':{'H':full_h},
            'compiled_qualification':{'result':self.origin('compiled'),'H':compiled_h}, 'verifier_controls':{}})
        qualified = {'schema':'pocket4-audio-whole-apex-qualification-v1',
            'state':'COMPLETE_APEX_QUALIFIED_RUNTIME_PENDING', 'errors':[], 'signals':[],
            'all_command_children_retired':True,'resource_gate_passed':True,
            'original_build_host':origin_host, 'host_generation_inherited':False,
            'runtime_qualified':False,'production_deployment_performed':False,
            'actual_apex':self.origin('whole_apex'),'copy':{'source':self.origin('whole_apex')},
            'payload_contents':{'actual_file_contents_result':self.origin('contents'),
                'compiled_bridge_binding_result':self.origin('compiled'),'compiled_bridge_binding':compiled,
                'payload_membership_verified':True,'payload_file_contents_verified':True,
                'compiled_qualification_H':compiled_h},
            'qualifier_source_manifest':self.origin('source_manifest'),
            'specification':self.origin('specification'),'full_raw_H':full_h,
            'started_ns':1100000000,'finished_ns':1900500000,
            **{name:True for name in subject.FLAGS}}
        self.put('qualification', qualified)
        self.put('H_request', {'job_id':'fixture-job','launch_nonce':'fixture-nonce',
            'executable':'/usr/bin/python3','args':['-I','-B',self.paths['source_qualifier'],
                '--spec',self.paths['specification'],'--sources',self.paths['source_manifest'],
                '--output',str(Path(self.paths['qualification']).parent)]})
        self.put('H_started', {'job_id':'fixture-job','launch_nonce':'fixture-nonce','at_unix_ms':1000})
        self.put('H_stdout', encoded({'state':qualified['state'],'result':self.origin('qualification'),
            'complete_apex_qualified':True,'runtime_qualified':False,'errors':[]}))
        self.put('H_stderr', b'')
        self.put('H_exit', {'job_id':'fixture-job','launch_nonce':'fixture-nonce','exit_code':0,
            'at_unix_ms':1900,'timed_out':False,'cancelled':False,'output_complete':True,
            'output_durable':True,'terminal_publication_protocol':1,
            'log_bytes':{name:{'seen':self.mapping['H_'+name]['origin']['bytes'],
                               'stored':self.mapping['H_'+name]['origin']['bytes']}
                         for name in ('stdout','stderr')},
            'log_synced':{'stdout':True,'stderr':True},'log_truncated':{'stdout':False,'stderr':False},
            'log_errors':{'stdout':None,'stderr':None}})
        self.receipt = {'schema':'pocket4-audio-canonical-whole-apex-qualification-v1',
            'state':'CANONICAL_BYTES_BOUND_RUNTIME_PENDING','origin_build_host':origin_host,
            'destination_host':destination_host,'origin_host_authority_inherited':False,
            'runtime_qualified':False,'production_deployment_performed':False,
            'all_canonical_copies_read_back':True,'canonical_root':str(self.local),
            'files':self.mapping, **{name:True for name in subject.FLAGS}}

    def origin(self, role):
        return copy.deepcopy(self.mapping[role]['origin'])

    def put(self, role, value):
        raw = value if isinstance(value, bytes) else encoded(value)
        if not isinstance(value, bytes):
            self.docs[role] = copy.deepcopy(value)
        path = self.local / role
        if path.exists():
            path.chmod(0o600)
        path.write_bytes(raw); path.chmod(0o400)
        short = {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        actual, _ = self.io.pinned(short)
        self.mapping[role] = {'origin':dict(short,path=self.paths[role]), 'canonical':actual}

    def run(self, **kwargs):
        options = dict(allowed_root=self.allowed,origin_host='builder',destination_host='device',
                       canonical_owner_uid=os.getuid(),reviewed_source_hashes=self.reviewed,guard=guard)
        options.update(kwargs)
        return subject.qualify(self.io,self.io,self.receipt,self.mapping['whole_apex']['canonical'],**options)


class CanonicalCustodyControls(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.directory.name).resolve())

    def tearDown(self):
        self.directory.cleanup()

    def test_real_destination_copies_work_without_origin_path_access(self):
        f = self.fixture; result = f.run()
        self.assertEqual(set(result), subject.JSON_ROLES)
        self.assertTrue(all(Path(x['path']).is_relative_to(f.local) for x in result.values()))
        self.assertTrue(all(Path(path).is_relative_to(f.local) for path in f.io.read_paths))
        self.assertFalse(f.receipt['origin_host_authority_inherited'])

    def test_previous_same_host_reader_cannot_consume_remote_original_paths(self):
        f = self.fixture
        with self.assertRaises(FileNotFoundError):
            guard.validate_stage_apex(f.io,f.docs['qualification'],f.mapping['whole_apex']['canonical'])
        f.run()

    def test_corrupted_destination_bytes_are_rejected(self):
        f = self.fixture; path = f.local/'contents'; path.chmod(0o600); path.write_bytes(b'altered')
        with self.assertRaises(ValueError): f.run()

    def test_destination_alias_is_rejected(self):
        f = self.fixture; path=f.local/'contents'; path.unlink(); path.symlink_to(f.local/'compiled')
        with self.assertRaises(ValueError): f.run()

    def test_destination_hardlink_is_rejected(self):
        f = self.fixture; os.link(f.local/'contents',f.local/'second-link')
        with self.assertRaises(ValueError): f.run()

    def test_original_identity_cannot_be_claimed_as_local_identity(self):
        f=self.fixture;f.mapping['contents']['origin']['identity']=[1]*9
        with self.assertRaisesRegex(ValueError,'historical identity'):f.run()

    def test_host_generation_credit_is_rejected(self):
        self.fixture.receipt['origin_host_authority_inherited']=True
        with self.assertRaisesRegex(ValueError,'local process'):self.fixture.run()

    def test_host_swap_is_rejected(self):
        self.fixture.receipt['origin_build_host']='device'
        with self.assertRaisesRegex(ValueError,'distinct build'):self.fixture.run()

    def test_canonical_root_outside_allowed_tree_is_rejected(self):
        self.fixture.receipt['canonical_root']=str(self.fixture.local.parent.parent)
        with self.assertRaisesRegex(ValueError,'canonical child'):self.fixture.run()

    def test_missing_receipt_role_is_rejected(self):
        del self.fixture.mapping['H_started']
        with self.assertRaisesRegex(ValueError,'role set'):self.fixture.run()

    def test_destination_owner_is_observed_not_inherited(self):
        with self.assertRaisesRegex(ValueError,'ownership'):self.fixture.run(canonical_owner_uid=os.getuid()+1)

    def test_boolean_file_length_is_rejected(self):
        self.fixture.mapping['whole_apex']['origin']['bytes']=True
        with self.assertRaisesRegex(ValueError,'strict file length'):self.fixture.run()

    def test_independently_reviewed_source_must_match(self):
        f=self.fixture;wrong=dict(f.reviewed);wrong['apex_evidence_join.py']='f'*64
        with self.assertRaisesRegex(ValueError,'reviewed bytes'):f.run(reviewed_source_hashes=wrong)

    def test_raw_terminal_boolean_protocol_is_rejected(self):
        f=self.fixture;d=copy.deepcopy(f.docs['H_exit']);d['terminal_publication_protocol']=True;f.put('H_exit',d)
        with self.assertRaises(guard.ContractError):f.run()

    def test_raw_terminal_other_generation_is_rejected(self):
        f=self.fixture;d=copy.deepcopy(f.docs['H_exit']);d['launch_nonce']='another-nonce';f.put('H_exit',d)
        with self.assertRaises(guard.ContractError):f.run()

    def test_actual_qualifier_argv_must_match(self):
        f=self.fixture;d=copy.deepcopy(f.docs['H_request']);d['args'][2]='/origin/another.py';f.put('H_request',d)
        with self.assertRaisesRegex(ValueError,'exact qualifier'):f.run()

    def test_stdout_result_pin_must_match_original_bytes(self):
        f=self.fixture;raw=(f.local/'H_stdout').read_bytes();d=json.loads(raw);d['result']['sha256']='e'*64
        f.put('H_stdout',encoded(d))
        with self.assertRaisesRegex(ValueError,'stdout did not bind'):f.run()

    def test_failed_original_qualification_cannot_be_upgraded(self):
        f=self.fixture;d=copy.deepcopy(f.docs['qualification']);d['state']='FAIL';f.put('qualification',d)
        with self.assertRaisesRegex(ValueError,'source-host qualification'):f.run()

    def test_result_time_outside_process_is_rejected(self):
        f=self.fixture;d=copy.deepcopy(f.docs['qualification']);d['finished_ns']=1901000000;f.put('qualification',d)
        with self.assertRaisesRegex(ValueError,'outside the actual'):f.run()


if __name__=='__main__':
    unittest.main(verbosity=2)
