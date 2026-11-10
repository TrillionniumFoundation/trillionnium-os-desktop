#!/usr/bin/python3
"""Retain prior controls and reject ownership/path confusion for a new image."""
from pathlib import Path
import importlib.util
import unittest


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


candidate = load('camera_accept03', 'accept_camera_ready03.py')
previous = load('camera_readiness_tests', 'test_preview_ready02.py')
previous.candidate = candidate
previous.original.accept = candidate


def row(path, owner=candidate.PACKAGE):
    values = dict(zip(candidate.MEDIA_FIELDS, (
        '42', path, Path(path).name, 'image/jpeg', '32000', '640', '480', '0',
        '1000', '0', owner)))
    return ('Row: 0 ' + ', '.join(key + '=' + values[key] for key in candidate.MEDIA_FIELDS)).encode()


class ImagePathTests(unittest.TestCase):
    def test_provider_default_pictures_is_accepted_alongside_camera_folder(self):
        for directory in ('Pictures', 'DCIM/Camera'):
            value = candidate.image_record(row('/storage/emulated/0/' + directory + '/owned.jpg'), 42, 1000)
            self.assertEqual(value['_id'], 42)

    def test_foreign_owner_old_time_and_other_id_still_refused(self):
        path = '/storage/emulated/0/Pictures/owned.jpg'
        for raw, image_id, shutter_time in (
            (row(path, 'com.foreign.app'), 42, 1000),
            (row(path), 43, 1000),
            (row(path), 42, 1004),
        ):
            with self.subTest(image_id=image_id, shutter_time=shutter_time), self.assertRaises(candidate.Stop):
                candidate.image_record(raw, image_id, shutter_time)

    def test_no_arbitrary_path_or_subdirectory_expansion(self):
        for path in (
            '/storage/emulated/0/Pictures/../private.jpg',
            '/storage/emulated/0/Download/owned.jpg',
            '/storage/emulated/10/Pictures/owned.jpg',
            '/data/media/0/Pictures/owned.jpg',
            '/storage/emulated/0/Pictures/nested/owned.jpg',
        ):
            with self.subTest(path=path), self.assertRaises(candidate.Stop):
                candidate.image_record(row(path), 42, 1000)


if __name__ == '__main__':
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromModule(previous.original),
        unittest.defaultTestLoader.loadTestsFromTestCase(previous.ReadinessTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(ImagePathTests),
    ])
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
