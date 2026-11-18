"""Pure synthetic controls for source metadata, with no APK or execution IO."""

import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dual_dynamic_elf import parse_dual_dynamic_shared_library as parse


def sample(elf_class=2, overlap=True):
    """Construct an explicit synthetic dual-view ELF; no third-party bytes."""
    hs, ps, ss, ds, word = (64, 56, 64, 16, 8) if elf_class == 2 else (52, 32, 40, 8, 4)
    body = bytearray(4096)
    shoff, mapped, strings = 4096 - 4 * ss, 2304, 1024
    declared = shoff - 5 * ds if overlap else 3200
    body[:16] = b'\x7fELF' + bytes([elf_class, 1, 1]) + bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH' if elf_class == 2 else '<HHIIIIIHHHHHH', body, 16,
                     3, 62 if elf_class == 2 else 3, 1, 0, hs, shoff, 0, hs, ps, 3, ss, 4, 1)
    programs = [(1, 5, 0, 0, 0, 2048, 2048, 4096),
                (1, 6, 2048, 6144, 6144, 1024, 1024, 4096),
                (2, 6, declared, 6400, 6400, 10 * ds, 10 * ds, word)]
    for i, row in enumerate(programs):
        if elf_class == 1:
            pt, pf, off, va, pa, fs, ms, align = row
            row = pt, off, va, pa, fs, ms, pf, align
        struct.pack_into('<IIQQQQQQ' if elf_class == 2 else '<IIIIIIII', body, hs + i * ps, *row)
    body[strings:strings + 64] = b'\0libc.so\0libm.so\0libfocus.so\0'.ljust(64, b'\0')
    dformat = '<qQ' if elf_class == 2 else '<iI'
    for start, rows in [(declared, [(1, 1), (1, 9), (14, 17), (0, 0)]),
                        (mapped, [(5, strings), (10, 64), (1, 1), (1, 9),
                                  (14, 17), (0x6ffffffb, 1), (0, 0)])]:
        for i, row in enumerate(rows):
            struct.pack_into(dformat, body, start + i * ds, *row)
    sections = [(0,) * 10, (0, 8, 0, 0, 0, 4096, 0, 0, 0, 0),
                (0, 3, 2, strings, strings, 64, 0, 0, 1, 0),
                (0, 6, 3, declared, declared, 10 * ds, 2, 0, word, ds)]
    for i, row in enumerate(sections):
        struct.pack_into('<IIQQQQIIQQ' if elf_class == 2 else '<IIIIIIIIII',
                         body, shoff + i * ss, *row)
    return bytes(body), {'class': elf_class, 'hs': hs, 'ps': ps, 'ss': ss, 'ds': ds,
                         'word': word, 'shoff': shoff, 'declared': declared,
                         'mapped': mapped, 'strings': strings, 'dformat': dformat}


def edit(body, offset, fmt, *values):
    result = bytearray(body)
    struct.pack_into(fmt, result, offset, *values)
    return bytes(result)


def dynamic(body, meta, view, index, tag, value):
    return edit(body, meta[view] + index * meta['ds'], meta['dformat'], tag, value)


class DualDynamicElfControls(unittest.TestCase):
    def test_dual_views_bind_identity_and_noncanonical_layout(self):
        for elf_class in (1, 2):
            with self.subTest(elf_class=elf_class):
                body, _ = sample(elf_class)
                result = parse(body)
                self.assertEqual(result['elf_class'], elf_class)
                self.assertEqual(result['soname'], 'libfocus.so')
                self.assertEqual(result['dynamic_needed'], ['libc.so', 'libm.so'])
                self.assertFalse(result['has_interpreter'])
                layout = result['layout']
                self.assertEqual(layout['section_name_index_type'], 8)
                self.assertTrue(layout['range_overlaps']['declared_full_section_headers'])
                self.assertFalse(layout['range_overlaps']['declared_consumed_section_headers'])
                self.assertTrue(all(p['page_4096'] for p in layout['load_congruence']))
                self.assertFalse(all(p['page_16384'] for p in layout['load_congruence']))
                self.assertIn({'tag': 0x6ffffffb, 'declared': None, 'mapped': [1]}, layout['tag_differences'])
                self.assertFalse({'production_ready', 'runtime_qualified', 'installed'} & set(result))
        body, m = sample()
        replacement = 'libé.so'.encode('utf-8') + b'\0'
        body = body[:m['strings'] + 17] + replacement + body[m['strings'] + 17 + len(replacement):]
        result = parse(body)
        raw = json.dumps(result['layout'], sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.assertEqual(result['soname'], 'libé.so')
        self.assertEqual(result['layout_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(raw, json.dumps(result['layout'], sort_keys=True,
                                          separators=(',', ':'), ensure_ascii=True).encode('utf-8'))

    def test_full_unconsumed_bytes_are_bound_by_layout_hash(self):
        body, m = sample()
        before = parse(body)
        after = parse(edit(body, m['declared'] + 4 * m['ds'], '<B', 0xab))
        self.assertEqual(before['dynamic_needed'], after['dynamic_needed'])
        self.assertEqual(before['layout']['declared_dynamic']['consumed'],
                         after['layout']['declared_dynamic']['consumed'])
        self.assertNotEqual(before['layout']['declared_dynamic']['full'],
                            after['layout']['declared_dynamic']['full'])
        self.assertNotEqual(before['layout_sha256'], after['layout_sha256'])

    def test_ordered_needed_and_soname_mismatch_rejected(self):
        body, m = sample()
        cases = {
            'soname': dynamic(body, m, 'mapped', 4, 14, 1),
            'needed': dynamic(body, m, 'mapped', 2, 1, 17),
            'order': dynamic(dynamic(body, m, 'mapped', 2, 1, 9), m, 'mapped', 3, 1, 1),
            'out_of_bounds_string': dynamic(body, m, 'declared', 2, 14, 64),
            'empty_string': dynamic(body, m, 'declared', 2, 14, 0),
        }
        for name, bad in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse(bad)

    def test_strtab_link_size_pointer_and_uniqueness_rejected(self):
        body, m = sample()
        strrow, dynrow = m['shoff'] + 2 * m['ss'], m['shoff'] + 3 * m['ss']
        cases = {
            'link_to_nobits': edit(body, dynrow + 40, '<I', 1),
            'link_out_of_bounds': edit(body, dynrow + 40, '<I', 4),
            'wrong_section_type': edit(body, strrow + 4, '<I', 1),
            'different_offset': edit(body, strrow + 24, '<Q', m['strings'] + 1),
            'different_size': edit(body, strrow + 32, '<Q', 63),
            'different_pointer': dynamic(body, m, 'mapped', 0, 5, m['strings'] + 1),
            'unmapped_pointer': dynamic(body, m, 'mapped', 0, 5, 9000),
            'ambiguous_load': body[:m['hs'] + m['ps']] + body[m['hs']:m['hs'] + m['ps']] + body[m['hs'] + 2 * m['ps']:],
        }
        for name, bad in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse(bad)

    def test_dynamic_termination_duplicates_and_declared_model_rejected(self):
        body, m = sample(overlap=False)
        cases = {
            'duplicate_strtab': dynamic(body, m, 'mapped', 2, 5, 1024),
            'declared_unreviewed_tag': dynamic(body, m, 'declared', 2, 5, 1024),
            'nonzero_null': dynamic(body, m, 'declared', 3, 0, 1),
        }
        for view in ('declared', 'mapped'):
            bad = body
            for i in range(10):
                bad = dynamic(bad, m, view, i, 1, 1)
            cases[view + '_unterminated'] = bad
        for name, bad in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse(bad)

    def test_distinct_views_exact_section_range_and_consumed_separation_required(self):
        body, m = sample()
        dp, ds = m['hs'] + 2 * m['ps'], m['shoff'] + 3 * m['ss']
        same = edit(edit(body, dp + 8, '<Q', m['mapped']), ds + 24, '<Q', m['mapped'])
        extra = edit(body, 56, '<H', 4)
        extra = extra[:m['hs'] + 3 * m['ps']] + body[dp:dp + m['ps']] + extra[m['hs'] + 4 * m['ps']:]
        cases = {
            'same_view': same,
            'section_size': edit(body, ds + 32, '<Q', 9 * m['ds']),
            'section_offset': edit(body, ds + 24, '<Q', m['declared'] - 16),
            'multiple_dynamic_segments': extra,
            'multiple_dynamic_sections': edit(body, m['shoff'] + m['ss'] + 4, '<I', 6),
        }
        for name, bad in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse(bad)
        # A full tail may overlap SHT, but consuming valid tags from SHT must fail.
        bad = dynamic(body, m, 'declared', 3, 1, 1)
        bad = dynamic(bad, m, 'declared', 4, 1, 1)
        bad = dynamic(bad, m, 'mapped', 5, 1, 1)
        bad = dynamic(bad, m, 'mapped', 6, 1, 1)
        bad = dynamic(bad, m, 'mapped', 7, 0, 0)
        with self.assertRaisesRegex(ValueError, 'Consumed.*overlap'):
            parse(bad)

    def test_header_table_and_layout_output_bounds_rejected(self):
        body, m = sample(overlap=False)
        cases = {
            'mutable_input': bytearray(body), 'truncated': body[:60],
            'wrong_class': edit(body, 4, '<B', 3), 'wrong_endian': edit(body, 5, '<B', 2),
            'not_shared': edit(body, 16, '<H', 2), 'wrong_header_size': edit(body, 52, '<H', 63),
            'too_many_programs': edit(body, 56, '<H', 129),
            'too_many_sections': edit(body, 60, '<H', 4097),
            'invalid_shstrndx': edit(body, 62, '<H', 4),
            'program_bounds': edit(body, 32, '<Q', 4088),
            'section_bounds': edit(body, 40, '<Q', 8),
            'address_overflow': edit(body, m['hs'] + 16, '<Q', (1 << 64) - 1),
        }
        for name, bad in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse(bad)
        many = edit(body, 60, '<H', 512).ljust(m['shoff'] + 512 * m['ss'], b'\0')
        with self.assertRaisesRegex(ValueError, 'output bound'):
            parse(many)

    def test_interpreter_pie_and_invalid_code_pointer_rejected(self):
        body, m = sample()
        cases = {
            'interpreter': edit(body, m['hs'] + 2 * m['ps'], '<I', 3),
            'pie': dynamic(body, m, 'mapped', 5, 0x6ffffffb, 0x08000000),
            'unmapped_entry': edit(body, 24, '<Q', 9000),
            'non_executable_entry': edit(body, 24, '<Q', 6144),
            'non_executable_init': dynamic(body, m, 'mapped', 5, 12, 6144),
        }
        for name, bad in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse(bad)

    def test_unknown_and_unbounded_dynamic_pointers_rejected(self):
        body, m = sample()
        cases = {
            'unknown_tag': dynamic(body, m, 'mapped', 5, 0x12345, 1),
            'unmapped_init': dynamic(body, m, 'mapped', 5, 12, 9000),
            'symbol_without_size': dynamic(body, m, 'mapped', 5, 6, 1024),
            'empty_string_extent': dynamic(body, m, 'mapped', 1, 10, 0),
            'oversized_string_extent': dynamic(body, m, 'mapped', 1, 10, 1024 * 1024 + 1),
        }
        for name, bad in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse(bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
