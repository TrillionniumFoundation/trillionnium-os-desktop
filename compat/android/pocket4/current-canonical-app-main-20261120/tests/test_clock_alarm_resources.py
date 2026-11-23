"""Exercise the selected Clock alarm reader with compiled Android resource tables."""
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import unittest
from unittest import mock
import zipfile


SOURCE = Path(__file__).resolve().parents[1] / 'bundle/source/clock/clock_alarm_reader.py'
SPEC = importlib.util.spec_from_file_location('selected_clock_alarm_reader', SOURCE)
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)
APKS = ('433ff501b92a21bb9265c896add220b52bc16fc4124662eaf45310da99243a0d',
        '9f24ea5fa57bca4a453556ab7cb44fbad1813cb3d15292a8e572cfb40fff7a77')
# These are the pre-existing alarm contract and the CP3A method/layout references.
VIEWS = [
    ('clock', 'digital_clock', 0xc4, 0xc4), ('onoff', 'onoff', 0x1a0, 0x1a4),
    ('arrow', 'arrow', 0x64, 0x64), ('label', 'edit_label', 0xde, 0xdf),
    ('delete', 'delete', 0xba, 0xba), ('dismiss', 'dismiss', 0xcd, 0xce),
    ('alarm_button', 'alarm', 0x4b, 0x4b), ('alert_title', 'alert_title', 0x53, 0x53),
    ('repeat', 'repeat_onoff', 0x1d9, 0x1de),
]
STRINGS = [('add', 'button_alarms', 'Add alarm', 0x1ba, 0x1ba),
           ('label_message', 'label', 'Label', 0x1fc, 0x1fc),
           ('label_description', 'no_label_specified', 'No label specified', 0x28d, 0x298)]


def string_pool(values):
    strings = bytearray()
    indexes = bytearray()
    for value in values:
        encoded = value.encode('ascii')
        indexes.extend(struct.pack('<I', len(strings)))
        strings.extend(bytes([len(encoded), len(encoded)]) + encoded + b'\0')
    while len(strings) % 4:
        strings.append(0)
    start = 28 + len(indexes)
    return struct.pack('<HH6I', 1, 28, start + len(strings), len(values), 0,
                       0x100, start, 0) + indexes + strings


def type_chunk(type_id, entries):
    # Compact entries, sparse indexes and a default, unlocalized configuration.
    indexes = bytearray()
    body = bytearray()
    for index, key, value in sorted(entries):
        indexes.extend(struct.pack('<HH', index, len(body) // 4))
        body.extend(struct.pack('<HHI', key, 0x0308 if type_id == 18 else 0x1008, value))
    header_size = 84
    start = header_size + len(indexes)
    header = struct.pack('<HHIBBHIII', 0x201, header_size, start + len(body),
                         type_id, 1, 0, len(entries), start, 64)
    return header.ljust(header_size, b'\0') + indexes + body


def fixture(generation, wrong_view=None, wrong_text=None):
    keys = []
    view_entries = []
    text_entries = []
    for role, name, old, current in VIEWS:
        view_entries.append(((old, current)[generation], len(keys), 0))
        keys.append(wrong_view if role == 'label' and wrong_view else name)
    messages = []
    for role, name, value, old, current in STRINGS:
        text_entries.append(((old, current)[generation], len(keys), len(messages)))
        keys.append(wrong_text if role == 'label_description' and wrong_text else name)
        messages.append(value)
    types = ['type%d' % i for i in range(1, 19)]
    types[9], types[17] = 'id', 'string'
    type_names = string_pool(types)
    contents = type_names + string_pool(keys) + type_chunk(10, view_entries) + type_chunk(18, text_entries)
    pkg = bytearray(288)
    struct.pack_into('<HHII', pkg, 0, 0x200, 288, 288 + len(contents), 0x7f)
    struct.pack_into('<IIIII', pkg, 268, 288, 18, 288 + len(type_names), len(keys), 0)
    body = string_pool(messages) + pkg + contents
    arsc = struct.pack('<HHII', 2, 12, 12 + len(body), 1) + body
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('resources.arsc', arsc)
    return stream.getvalue()


class AlarmResources(unittest.TestCase):
    def setUp(self):
        self.reader = READER.make_reader('Pocket4 QA alarm ' + 'a' * 32)

    def resolve_fixture(self, generation, **changes):
        raw = fixture(generation, **changes)
        digest = hashlib.sha256(raw).hexdigest()
        with mock.patch.dict(READER.ALARM_RESOURCE_PROFILES, {digest: generation}):
            return self.reader.resource_contract(raw)

    def test_all_roles_and_empty_label_from_both_compiled_layouts(self):
        self.assertEqual(READER.ALARM_RESOURCE_PROFILES, {name: i for i, name in enumerate(APKS)})
        for i in range(2):
            with self.subTest(generation=i):
                result = self.resolve_fixture(i)
                self.assertEqual(result['ids'], {r: 'com.android.deskclock:id/' + n for r, n, _, _ in VIEWS})
                self.assertEqual(result['texts'], {r: text for r, _, text, _, _ in STRINGS})
                ids = {r: hex(0x7f0a0000 + (old, new)[i]) for r, _, old, new in VIEWS}
                ids.update({r: hex(0x7f120000 + (old, new)[i]) for r, _, _, old, new in STRINGS})
                self.assertEqual(result['numeric_ids_from_actual_installed_methods'], ids)

    def test_same_type_collapsed_label_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'ALARM_VIEW_RESOURCE_ROLE_MISMATCH'):
            self.resolve_fixture(1, wrong_view='label')

    def test_nonempty_label_string_is_rejected_for_new_alarm(self):
        with self.assertRaisesRegex(RuntimeError, 'ALARM_STRING_RESOURCE_ROLE_MISMATCH'):
            self.resolve_fixture(1, wrong_text='label_description')

    def test_unknown_apk_is_rejected_before_decoding(self):
        with self.assertRaisesRegex(RuntimeError, 'UNREVIEWED_DESKCLOCK_ALARM_APK'):
            self.reader.resource_contract(fixture(1))

    def test_legacy_addresses_do_not_identify_the_current_table(self):
        body = fixture(1)
        with mock.patch.dict(READER.ALARM_RESOURCE_PROFILES, {hashlib.sha256(body).hexdigest(): 0}):
            with self.assertRaisesRegex(RuntimeError, 'REQUIRED_COMPILED_RESOURCE_NOT_FOUND'):
                self.reader.resource_contract(body)


if __name__ == '__main__':
    unittest.main()
