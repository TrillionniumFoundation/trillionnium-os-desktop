import unittest
from source_transfer_batches import partition_filelist


class BatchControls(unittest.TestCase):
    def test_large_list_is_disjoint_complete_and_bounded(self):
        names = [f'project/{n:06d}'.encode() for n in range(20003)]
        raw = b'\0'.join(names) + b'\0'
        batches = partition_filelist(raw)
        self.assertEqual([len(b.split(b'\0')) - 1 for b in batches], [8192, 8192, 3619])
        self.assertEqual(b''.join(batches), raw)

    def test_one_file_keeps_exact_bytes(self):
        self.assertEqual(partition_filelist(b'a/file with space\0'), [b'a/file with space\0'])

    def test_unicode_and_newlines_are_not_shell_expanded(self):
        raw = 'a/name\n$(literal)`file`\0b/文件\0'.encode()
        self.assertEqual(b''.join(partition_filelist(raw, 1)), raw)

    def test_unsorted_or_duplicate_is_rejected(self):
        for raw in (b'b\0a\0', b'a\0a\0'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                partition_filelist(raw)

    def test_incomplete_or_empty_is_rejected(self):
        for raw in (b'', b'a', b'\0', b'a\0\0', 'a\0'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                partition_filelist(raw)

    def test_escape_absolute_or_directory_is_rejected(self):
        for raw in (b'/a\0', b'../a\0', b'a/../b\0', b'a/\0', b'a//b\0', b'./a\0'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                partition_filelist(raw)

    def test_boolean_float_or_unbounded_batch_size_is_rejected(self):
        for count in (True, 1.0, 0, -1, 8193):
            with self.subTest(count=count), self.assertRaises(ValueError):
                partition_filelist(b'a\0', count)

    def test_file_names_are_not_replaced_by_parent_directories(self):
        raw = b'one/.git/objects/a\0one/source.c\0two/required.h\0'
        batches = partition_filelist(raw, 1)
        self.assertEqual([b[:-1] for b in batches], raw[:-1].split(b'\0'))


if __name__ == '__main__':
    unittest.main()
