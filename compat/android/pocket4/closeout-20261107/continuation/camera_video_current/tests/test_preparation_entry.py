"""Real file/FD and production entry/planner controls; no runtime plan or device.

Only c.FINAL is relocated for source_packet's isolated filesystem fixture.
No baseline, identity, Main command, acoustic actor, or display lease is faked as
qualified; source_packet is the existing source-only validation boundary.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


BUILDER = load(ROOT / 'tools/prepare_camera_video.py', 'camera_preparation_builder')


def fd_table():
    result = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            result[int(name)] = os.readlink('/proc/self/fd/' + name)
        except FileNotFoundError:
            pass
    return result


class PreparationEntryControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='camera-source-entry-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.before = fd_table()
        self.addCleanup(lambda: self.assertEqual(self.before, fd_table()))

    def prepare(self, source=None):
        result = BUILDER.prepare(source or ROOT / 'source', ROOT / 'reviewed-source-inventory.json',
                                 BUILDER.INVENTORY_SHA256, self.root / 'prepared')
        self.prep_ref = result['preparation']
        self.entry_path = self.root / 'prepared/source/camera_entry.py'
        self.entry = load(self.entry_path, 'actual_prepared_camera_entry')
        self.common, self.packet, _, self.planner = self.entry.bootstrap(argparse.Namespace(
            preparation=self.prep_ref['path'], expect_preparation_sha256=self.prep_ref['sha256']))
        return result

    def tasks(self):
        c = self.common
        c.FINAL = self.root / 'fixture-final'
        self.case = c.FINAL / 'qualification' / ('business-camera-video-plan-' + '1' * 32)
        source = self.case / 'source'
        source.mkdir(parents=True)
        files = [c.write_new(source / Path(r['path']).name, c.read_ref(r), 0o400)
                 for r in self.packet['files']]
        names = {Path(r['path']).name: r for r in files}
        origins = [self.prep_ref] + self.packet['files'] + self.packet['origins']
        profiles = self.planner.named(c, self.packet, 'camera_profiles.py').profiles('camera_video')
        self.task_values = {}
        refs = {}
        for role, profile in zip(('camera', 'player'), profiles[:2]):
            task = {'schema': 'pocket4-final-business-task-source-v1', 'files': copy.deepcopy(files),
                'origins': copy.deepcopy(origins), 'guard_source': names['camera_guard.py'],
                'recorder_source': names['camera_flow.py'], 'target_package': profile['package'],
                'target_uid': profile['uid'], 'old_runtime_authority_transferred': False}
            self.task_values[role] = task
            refs[role] = c.write_new(self.case / ('task-' + role + '.json'), task)
        value = {name: None for name in self.planner.BASE_FIELDS}
        value.update(schema='pocket4-current-camera-video-plan-v1', kind='camera_video',
                     case_root=str(self.case), task_source_manifests=refs, source_preparation=self.prep_ref)
        return value

    def replace_task(self, value, role, task):
        path = self.case / ('task-' + role + '.json')
        path.write_bytes(self.common.canonical(task))
        value['task_source_manifests'][role] = self.common.regular(path, contents=False)

    def test_formal_entry_reads_exact_whole_graph_and_closes_all_fds(self):
        result = self.prepare()
        self.assertEqual(result['source_files'], 29)
        inspection = json.loads(Path(result['inspection']['path']).read_bytes())
        self.assertTrue(inspection['formal_entry_bootstrap_passed'])
        self.assertEqual(inspection['held_evidence_files'], 32)
        self.assertTrue(inspection['all_live_dependencies_under_preparation_root'])
        for row in self.packet['files']:
            self.assertEqual(Path(row['path']).read_bytes(), (ROOT / 'source' / Path(row['path']).name).read_bytes())
        self.assertFalse(self.packet['runtime_qualified'])
        self.assertFalse(self.packet['Android_execution_authorized_by_publication'])

    def test_two_actual_role_packets_consume_only_new_exact_source_copies(self):
        self.prepare()
        value = self.tasks()
        original = self.common.read_ref
        reads = []
        def recording_reader(ref, *args, **kwargs):
            reads.append(ref['path'])
            return original(ref, *args, **kwargs)
        self.common.read_ref = recording_reader
        result = self.planner.source_packet(self.common, value, self.packet)
        self.assertEqual(set(result), {'camera', 'player'})
        self.assertNotEqual(result['camera']['target_uid'], result['player']['target_uid'])
        self.assertEqual(len(result['camera']['files']), 29)
        self.assertTrue(all(Path(path).is_relative_to(self.root) for path in reads))
        for role in result:
            for row in result[role]['files']:
                self.assertEqual(Path(row['path']).parent, self.case / 'source')
        self.assertIn(str(self.case / 'source/camera_decode.py'), reads)
        self.assertIn(str(self.case / 'source/camera_video_state.py'), reads)

    def test_previous_r4_decoder_hash_in_task_is_rejected(self):
        self.prepare()
        value = self.tasks()
        task = copy.deepcopy(self.task_values['camera'])
        row = next(r for r in task['files'] if Path(r['path']).name == 'camera_decode.py')
        row.update(bytes=14138, sha256='22face5af8d95709111008f837ac8ba9e6e2520971c340e62da62939658f1e10')
        self.replace_task(value, 'camera', task)
        with self.assertRaisesRegex(RuntimeError, 'EXTERNAL_PREPARATION_MUST_MATCH_EVERY_TASK_BYTE_AND_ROLE:camera'):
            self.planner.source_packet(self.common, value, self.packet)

    def test_old_source_path_and_package_role_substitution_are_rejected(self):
        self.prepare()
        original_value = self.tasks()
        for changed in ('old-path', 'wrong-role'):
            with self.subTest(changed=changed):
                value = copy.deepcopy(original_value)
                task = copy.deepcopy(self.task_values['player'])
                if changed == 'old-path':
                    task['files'][0]['path'] = '/home/alex/work/pocket4-android-final/qualification/camera-video-recovery-current-draft-20261108-r3/source/app_common.py'
                else:
                    task['target_package'] = self.task_values['camera']['target_package']
                    task['target_uid'] = self.task_values['camera']['target_uid']
                self.replace_task(value, 'player', task)
                with self.assertRaisesRegex(RuntimeError, 'EXTERNAL_PREPARATION_MUST_MATCH_EVERY_TASK_BYTE_AND_ROLE:player'):
                    self.planner.source_packet(self.common, value, self.packet)

    def test_changed_source_is_refused_before_any_preparation_is_created(self):
        source = self.root / 'input'
        shutil.copytree(ROOT / 'source', source)
        path = source / 'camera_video_state.py'
        path.write_bytes(path.read_bytes() + b'\n# unreviewed source\n')
        with self.assertRaisesRegex(RuntimeError, 'REVIEWED_SOURCE_BYTES_CHANGED:camera_video_state.py'):
            self.prepare(source)
        self.assertFalse((self.root / 'prepared').exists())

    def test_preparation_external_pin_and_origin_bytes_cannot_be_rebound(self):
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, 'VIDEO_PREPARATION_PIN_CHANGED'):
            self.entry.bootstrap(argparse.Namespace(preparation=self.prep_ref['path'], expect_preparation_sha256='0' * 64))
        provenance = self.root / 'prepared/source-provenance.json'
        provenance.chmod(0o600)
        provenance.write_bytes(provenance.read_bytes() + b'\n')
        with self.assertRaisesRegex(RuntimeError, 'REFERENCE_CHANGED'):
            self.entry.bootstrap(argparse.Namespace(preparation=self.prep_ref['path'],
                                                    expect_preparation_sha256=self.prep_ref['sha256']))

    def test_preparation_recreation_refused_without_modifying_existing_packet(self):
        self.prepare()
        path = Path(self.prep_ref['path'])
        before = path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'CREATE_ONLY_PREPARATION_REQUIRED'):
            self.prepare()
        self.assertEqual(path.read_bytes(), before)

    def test_extra_or_symlink_source_member_is_rejected(self):
        source = self.root / 'input'
        shutil.copytree(ROOT / 'source', source)
        (source / 'unexpected.py').write_text('raise RuntimeError("must never execute")\n')
        with self.assertRaisesRegex(RuntimeError, 'EXACT_29_SOURCE_DIRECTORY_MEMBERS_REQUIRED'):
            self.prepare(source)
        (source / 'unexpected.py').unlink()
        path = source / 'camera_decode.py'
        path.unlink()
        path.symlink_to(ROOT / 'source/camera_decode.py')
        with self.assertRaisesRegex(RuntimeError, 'CANONICAL_INPUT_REQUIRED'):
            self.prepare(source)
        self.assertFalse((self.root / 'prepared').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
