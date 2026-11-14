import unittest

import ninja_audio_proof as p
import ninja_command_proof as log


class AudioCompileControls(unittest.TestCase):
    def command(self, source='audio/Stream.cpp', output='out/Stream.o', extra=''):
        return 'clang++ --target=x86_64-linux-android35 -c ' + source + ' -o ' + output + ' ' + extra

    def parse(self, command, response=b''):
        return p.compile_command(command, response, 'audio/Stream.cpp', 'out/Stream.o', None, '/source')

    def test_unconditional_bridge_needs_actual_object_compile_without_feature_macro(self):
        result = self.parse(self.command())
        self.assertEqual(result['target_triple'], 'x86_64-linux-android35')
        self.assertIsNone(result['macro'])

    def test_response_file_retains_exact_source_output_and_target(self):
        result = self.parse('clang++ @out/compile.rsp', self.command().removeprefix('clang++ ').encode())
        self.assertEqual(result['response_file'], 'out/compile.rsp')

    def test_multiple_sources_are_rejected(self):
        with self.assertRaises(RuntimeError):
            self.parse(self.command(extra='audio/Other.cpp'))

    def test_wrong_source_output_or_architecture_is_rejected(self):
        for command in (self.command(source='other.cpp'), self.command(output='out/other.o'),
                        self.command().replace('x86_64-', 'aarch64-')):
            with self.subTest(command=command), self.assertRaises(RuntimeError):
                self.parse(command)

    def test_masks_and_object_replacement_are_rejected(self):
        for tail in ('; true', '|| true', '&& cp foreign.o out/Stream.o', '&& touch out/other.o'):
            with self.subTest(tail=tail), self.assertRaises(RuntimeError):
                self.parse(self.command() + tail)

    def test_non_compiling_modes_are_rejected(self):
        for flag in ('-E', '-S', '-fsyntax-only'):
            with self.subTest(flag=flag), self.assertRaises(RuntimeError):
                self.parse(self.command(extra=flag))

    def test_compile_only_original_chain_and_matching_touch_are_accepted(self):
        self.parse(self.command() + '&& touch out/Stream.o')
        with self.assertRaises(RuntimeError):
            self.parse('echo fake && ' + self.command())

    def test_unsupported_nested_response_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.parse('clang++ @out/compile.rsp', b'@out/hidden.rsp')

    def test_actual_valid_headers_are_tied_to_same_object_mtime(self):
        raw = 'out/Stream.o: #deps 2, deps mtime 123 (VALID)\n    audio/Stream.cpp\n    audio/Bridge.h\n\n'
        self.assertEqual(p.header_dependencies('out/Stream.o', raw, 123), ['audio/Stream.cpp', 'audio/Bridge.h'])
        for bad in (raw.replace('(VALID)', '(STALE)'), raw.replace('#deps 2', '#deps 3'),
                    raw.replace('mtime 123', 'mtime 124'), raw.replace('audio/Bridge.h', 'audio/Stream.cpp')):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                p.header_dependencies('out/Stream.o', bad, 123)

    def test_order_only_edge_is_not_linkage(self):
        record = p.query_record('core', 'core:\n  input: link\n    || out/Stream.o\n  outputs:\n')
        with self.assertRaises(RuntimeError):
            p.dependency_edge(record, 'out/Stream.o')

    def test_source_requires_direct_compiled_object_parent(self):
        with self.assertRaises(RuntimeError):
            p.dependency_path('core', 'audio/Stream.cpp', 'core\nphony\naudio/Stream.cpp\n')

    def test_log_hash_binds_actual_response_bytes(self):
        command = b'clang++ @out/compile.rsp'; response = self.command().encode()
        digest = log.command_hash(command, response)
        raw = ('# ninja log v5\n1\t2\t123\tout/Stream.o\t%x\n' % digest).encode()
        self.assertEqual(log.bind_log_entry(raw, 'out/Stream.o', command, response)['mtime'], 123)
        with self.assertRaises(RuntimeError):
            log.bind_log_entry(raw, 'out/Stream.o', command, response + b' -DCHANGED=1')


if __name__ == '__main__':
    unittest.main()
