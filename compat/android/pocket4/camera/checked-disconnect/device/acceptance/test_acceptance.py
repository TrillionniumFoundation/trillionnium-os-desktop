#!/usr/bin/env python3
"""Local-only regression: synthetic inputs and fake transport, no device calls."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest

spec = importlib.util.spec_from_file_location('accept_camera', Path(__file__).with_name('accept_camera.py'))
accept = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accept)


def stack(task, package):
    return (f'RootTask id={task} displayId=0 userId=0\n mWindowingMode=freeform\n'
            f' taskId={task}: {package}/.Activity bounds=[0,0][100,100] userId=0\n')


OTHER = stack(851, 'local.pocket4.fixture')
CAMERA = stack(900, accept.PACKAGE)


def provider_events():
    values = [
        {'event': 'producer', 'message': 'Pocket4LiveCamera source_connected session=42 peer_uid=0'},
        {'event': 'physical_camera_open'},
        {'event': 'producer', 'message': 'Pocket4LiveCamera source_closed session=42 frames=196'},
        {'event': 'physical_camera_closed', 'frames': 197, 'exit': 0},
    ]
    return [{'MESSAGE': json.dumps(value)} for value in values]


class Tests(unittest.TestCase):
    def test_leaf_rejects_foreign_or_shared_root(self):
        roots, tasks = accept.parse_stacks(OTHER + CAMERA)
        self.assertTrue(accept.exact_leaf(roots, 900))
        self.assertFalse(accept.exact_leaf(roots, 851))
        roots[900]['children'].append(roots[851]['children'][0])
        self.assertFalse(accept.exact_leaf(roots, 900))
        self.assertEqual(tasks, {851, 900})

    def test_native_receipt_rejects_wrong_main_or_unknown_effect(self):
        receipt = {'ok': True, 'host_pid': 77, 'state': 'running',
                   'launch': 'object=5 composer_display=2 android_display=0 task=900'}
        self.assertEqual(accept.native_task(receipt, 77), 900)
        with self.assertRaises(accept.Stop):
            accept.native_task(receipt, 78)
        with self.assertRaises(accept.Stop):
            accept.native_task({**receipt, 'outcome_unknown': True}, 77)

    def test_media_delta_never_chooses_old_or_ambiguous_photo(self):
        self.assertEqual(accept.media_ids(b'Row: 0 _id=5\nRow: 1 _id=6\n'), {5, 6})
        self.assertIsNone(accept.new_image_id({5, 6}, {5, 6}))
        self.assertEqual(accept.new_image_id({5, 6}, {5, 6, 8}), 8)
        for after in ({6, 8}, {5, 6, 8, 9}):
            with self.subTest(after=after), self.assertRaises(accept.Stop):
                accept.new_image_id({5, 6}, after)

    def test_media_unknown_response_is_not_empty_gallery(self):
        for raw in (b'', b'Permission Denial', b'Row: 0 _id=1\nRow: 1 _id=1', b'Row: 0 _id=1, width=5'):
            with self.subTest(raw=raw), self.assertRaises(accept.Stop):
                accept.media_ids(raw)

    def test_real_jpeg_decode_and_corruption(self):
        from PIL import Image
        stream = io.BytesIO()
        Image.new('RGB', (64, 48), (30, 70, 110)).save(stream, 'JPEG')
        raw = stream.getvalue()
        row = {'_size': len(raw), 'width': 64, 'height': 48, 'orientation': 0}
        self.assertTrue(accept.decoded_photo(raw, row)['fully_decoded'])
        with self.assertRaises(accept.Stop):
            accept.decoded_photo(raw[:64], {**row, '_size': 64})

    def test_provider_actual_frame_counts_and_matching_session(self):
        result = accept.provider_proof(provider_events())
        self.assertEqual((result['physical_frames'], result['producer_frames']), (197, 196))
        rows = provider_events()
        rows[2]['MESSAGE'] = json.dumps({'event': 'producer',
                                        'message': 'Pocket4LiveCamera source_closed session=43 frames=196'})
        with self.assertRaises(accept.Stop):
            accept.provider_proof(rows)

    def test_provider_history_or_incomplete_window_cannot_pass(self):
        rows = provider_events()
        for bad in (rows[:-1], [rows[-1], *rows[:-1]], [*rows, rows[1]]):
            with self.subTest(bad=bad), self.assertRaises(accept.Stop):
                accept.provider_proof(bad)

    def test_unknown_exit_info_cannot_be_reported_as_no_crash(self):
        for text in ('', 'Permission Denial: uid', 'future output',
                     'ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)\nfuture format'):
            with self.subTest(text=text), self.assertRaises(accept.Stop):
                accept.exit_events(text)

    def test_fresh_uid_crash_and_new_exit_detected(self):
        header = 'ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)\n'
        before = {'exits': header + 'No records.\n', 'crash': '', 'events': ''}
        after = {'exits': header + ' ApplicationExitInfo #0:\n  timestamp=2026-11-05 10:00:00\n'
                 '  pid=42 realUid=10062 packageUid=10062\n  process=com.android.camera2\n  reason=4 (CRASH)\n',
                 'crash': '100.123 42 43 E AndroidRuntime: Fatal\n', 'events': ''}
        result = accept.fresh_crashes(before, after, 10062, 100)
        self.assertFalse(result['clear'])
        self.assertEqual(result['new_crash_or_anr_exits'], 1)
        self.assertEqual(result['new_uid_crash_lines'], 1)
        self.assertTrue(accept.fresh_crashes(before, before, 10062, 100)['clear'])

    def test_mode_is_exact_string_zero_without_preference_write(self):
        for raw, good in [(b'<map><string name="camera.startup_module">0</string></map>', True),
                          (b'<map><string name="camera.startup_module">1</string></map>', False),
                          (b'<map><int name="camera.startup_module" value="0"/></map>', False),
                          (b'<map/>', False)]:
            session = types.SimpleNamespace(guard=lambda: None,
                target=types.SimpleNamespace(read_file=lambda path, limit: (raw, {})))
            if good:
                self.assertEqual(accept.photo_mode_verified(session)['preference_writes'], 0)
            else:
                with self.assertRaises(accept.Stop):
                    accept.photo_mode_verified(session)

    def test_uncertain_remove_is_never_replayed(self):
        removed = []
        def android(command, timeout=20):
            if command[-2] == 'remove':
                removed.append(command)
                raise TimeoutError('transport lost after possible removal')
            return (OTHER + CAMERA).encode()
        session = types.SimpleNamespace(android=android)
        with tempfile.TemporaryDirectory() as directory:
            trial = accept.Trial(session, None, Path(directory))
            trial.owned = (900, {851}, 'open')
            with self.assertRaises(TimeoutError):
                trial.close()
            trial.close()
            self.assertEqual(len(removed), 1)
            self.assertEqual(trial.pending_effects, {'open-remove'})

    def test_cleanup_cannot_hide_uncertain_shutter(self):
        removed = []
        def android(command, timeout=20):
            if command[-2] == 'remove':
                removed.append(command)
                return b''
            return (OTHER if removed else OTHER + CAMERA).encode()
        def dispatch(request):
            raise TimeoutError('unknown after one shutter')
        session = types.SimpleNamespace(android=android, guard=lambda: None,
                                        helper=types.SimpleNamespace(dispatch=dispatch))
        with tempfile.TemporaryDirectory() as directory:
            trial = accept.Trial(session, None, Path(directory))
            trial.owned = (900, {851}, 'open')
            request = {'op': 'click', 'package': accept.PACKAGE, 'method': 'accessibility',
                       'selector': {'id': accept.PACKAGE + ':id/shutter_button'}}
            with self.assertRaises(TimeoutError):
                trial.ui('shutter', request)
            trial.close()
            self.assertEqual(trial.pending_effects, {'shutter'})
            self.assertEqual((trial.shutter_calls, trial.remove_calls), (1, 1))
            with self.assertRaises(accept.Stop):
                trial.ui('shutter-again', request)

    def test_self_exit_before_close_is_preserved_but_not_qualified(self):
        commands = []
        def android(command, timeout=20):
            commands.append(command)
            return OTHER.encode()
        with tempfile.TemporaryDirectory() as directory:
            trial = accept.Trial(types.SimpleNamespace(android=android), None, Path(directory))
            trial.owned = (900, {851}, 'reopen')
            trial.launch_calls, trial.remove_calls, trial.shutter_calls = 2, 1, 1
            trial.close()
            self.assertIsNone(trial.owned)
            self.assertTrue(all('remove' not in command for command in commands))
            with self.assertRaises(accept.Stop):
                accept.require_completed_lifecycle(trial)
            trial.remove_calls = 2
            accept.require_completed_lifecycle(trial)


if __name__ == '__main__':
    unittest.main(verbosity=2)
