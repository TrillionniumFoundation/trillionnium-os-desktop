"""Regression controls for the existing CI verifier interface."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

P = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('current_verify_tests', P / 'verify.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


# Complete observed fragments from updater-bulk400.stdout, SHA256
# cbfb961bba917c7995f2cb8b4ba8af32cbd1a13dfd42e77ea8a4137a52babdd5.
ACTUAL_IMAGE_CHILD = """test image_policy::tests::repack_preserves_android_metadata_and_adbd ... 
running 1 test
mkfs.erofs 1.9.4
Processing / ...
Processing apex ...
Processing apex/com.android.adbd.apex ...
Processing apex/com.android.vndk.v31.apex ...
Processing apex/com.android.vndk.v32.apex ...
Processing apex/com.android.vndk.v33.apex ...
Processing apex/com.android.vndk.v34.apex ...
Processing apex/retained-link ...
Build completed.

------
Filesystem UUID: 3d99bf0b-96ee-4605-ad5e-c8870f6c6871
Filesystem total blocks: 6 (of 4096-byte blocks)
Filesystem total inodes: 8
Filesystem total metadata blocks: 1
Filesystem total deduplicated bytes (of source files): 0
mkfs.erofs 1.9.4
Processing / ...
Processing apex ...
Processing apex/com.android.adbd.apex ...
Processing apex/retained-link ...
Build completed.

------
Filesystem UUID: 7b895cb0-54d5-4a4d-950d-50cda078053f
Filesystem total blocks: 2 (of 4096-byte blocks)
Filesystem total inodes: 4
Filesystem total metadata blocks: 1
Filesystem total deduplicated bytes (of source files): 0
test image_policy::tests::repack_preserves_android_metadata_and_adbd ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 464 filtered out; finished in 0.03s

ok
"""

ACTUAL_TOOL_OUTPUT = """test native_generation::tests::real_erofs_bundle_verifies_its_embedded_pair ... mkfs.erofs 1.9.4
Processing / ...
Processing system ...
Processing system/apex ...
Processing system/etc ...
Processing system/lib64 ...
Processing system/apex/com.android.art.apex ...
Processing system/etc/droidloom-native-generation-pair.json ...
Processing system/lib64/libberberis_arm64.so ...
Build completed.

------
Filesystem UUID: 737e853f-6d9e-4257-8d18-5862359da501
Filesystem total blocks: 5 (of 4096-byte blocks)
Filesystem total inodes: 8
Filesystem total metadata blocks: 1
Filesystem total deduplicated bytes (of source files): 0
mkfs.erofs 1.9.4
Processing / ...
Processing system ...
Processing system/apex ...
Processing system/etc ...
Processing system/lib64 ...
Processing system/apex/com.android.art.apex ...
Processing system/etc/droidloom-native-generation-pair.json ...
Processing system/lib64/libberberis_arm64.so ...
Build completed.

------
Filesystem UUID: 44e2162e-f70b-4a0d-a751-3f5fa2845697
Filesystem total blocks: 5 (of 4096-byte blocks)
Filesystem total inodes: 8
Filesystem total metadata blocks: 1
Filesystem total deduplicated bytes (of source files): 0
ok
"""

ACTUAL_STAGING_CHILD = """test native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata ... 
running 1 test
test native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 464 filtered out; finished in 0.68s

ok
"""


def updater_catalogs():
    rows = v.decode(v.regular(P / 'EXPECTED-CATALOG.json'))
    current = next(row for row in rows if (row['package'], row['target']) == ('droidloom-update', 'droidloom-update'))
    added = {
        'coherent_images::tests::release_mapping_cannot_relabel_the_actual_selected_cp2a_lock',
        'coherent_images::tests::selected_lock_identity_requires_exact_typed_and_unique_identity_fields',
    }
    v.need(len(current['all']) == 467 and added <= set(current['all']), 'exact current updater catalog required')
    historical = [name for name in current['all'] if name not in added]
    historical_body = (json.dumps(historical, sort_keys=True, separators=(',', ':')) + '\n').encode()
    v.need(len(historical) == 465 and v.digest(historical_body)['sha256'] ==
           'feeb8f74d780b51eb215d34d3c924bca127443b759dca6b7325b89e91d534680',
           'the unchanged actual historical fragments require their original complete name set')
    return current, historical


class Controls(unittest.TestCase):
    def test_terminal_rejects_contradictions_and_duplicate_identity(self):
            good='running 2 tests\ntest one ... ok\ntest privileged ... ignored, requires namespaces\ntest result: ok. 1 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.01s\n'
            self.assertEqual(v.test_terminal(good,{'one'},{'privileged'},0)['filtered'],0)
            bad=[good+'test extra ... FAILED\n',good+'test extra ... ignored\n',good+'running 2 tests\n',
                 good+good.splitlines()[-1]+'\n',good.replace('1 ignored;','0 ignored;'),good.replace('0 measured;','1 measured;'),
                 good.replace('0 filtered out;','1 filtered out;'),good.replace('test one ... ok\n',''),
                 good.replace('test one ... ok\n','test one ... ok\ntest one ... ok\n'),
                 good.replace('test privileged ... ignored, requires namespaces','test privileged ... ok'),
                 good.replace('test one ... ok','test one ... FAILED'),good.rsplit('test result:',1)[0]]
            for text in bad:
                with self.subTest(text=text),self.assertRaises(RuntimeError):v.test_terminal(text,{'one'},{'privileged'},0)

    def test_cargo_exact_terminal(self):
            terminal={'reason':'build-finished','success':True};good=(json.dumps(terminal)+'\n').encode()
            self.assertEqual(v.successful_cargo_stream(good),[terminal])
            for bad in [json.dumps({'reason':'build-finished','success':False}).encode()+b'\n'+good,good+good,
                        json.dumps({'reason':'compiler-message','message':{'level':'error'}}).encode()+b'\n'+good,
                        good+b'{"reason":"compiler-artifact"}\n']:
                with self.subTest(raw=bad),self.assertRaises(RuntimeError):v.successful_cargo_stream(bad)

    def test_duplicate_json_and_relative_names(self):
            with self.assertRaises(RuntimeError):v.decode(b'{"same":1,"same":2}')
            for name in ['/absolute','../escape','a/../escape','a/.git/object','a//b','a\\b','a\x00b']:
                with self.subTest(name=name),self.assertRaises(RuntimeError):v.safe(name)

    def test_whole_source_rejects_extra_alias_link_and_mode(self):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);path=root/'data';path.write_bytes(b'original');path.chmod(0o644)
                rows=[{'path':'data','mode':'100644','git_blob':v.object_id('blob',b'original'),**v.digest(b'original')}]
                tree=v.tree_id(rows);v.source_snapshot(root,rows,tree)
                (root/'extra').mkdir()
                with self.assertRaises(RuntimeError):v.source_snapshot(root,rows,tree)
                (root/'extra').rmdir();path.chmod(0o755)
                with self.assertRaises(RuntimeError):v.source_snapshot(root,rows,tree)
                path.chmod(0o644);(root/'alias').symlink_to(path)
                with self.assertRaises(RuntimeError):v.source_snapshot(root,rows,tree)
                (root/'alias').unlink();(root/'link').hardlink_to(path)
                with self.assertRaises(RuntimeError):v.regular(path)

    def test_fresh_destinations_reject_source_or_parent_alias(self):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'input';source.mkdir();alias=root/'alias';alias.symlink_to(source,target_is_directory=True)
                for output in [source/'nested',alias/'nested',source]:
                    with self.subTest(output=output),self.assertRaises(RuntimeError):v.fresh_destination(output,[source])
                self.assertEqual(v.fresh_destination(root/'new',[source]),root/'new')


    def test_actual_nested_and_tool_fragments_credit_only_outer_records(self):
        _, historical = updater_catalogs()
        names = {'image_policy::tests::repack_preserves_android_metadata_and_adbd',
                 'native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata',
                 'native_generation::tests::real_erofs_bundle_verifies_its_embedded_pair'}
        text = ('running 3 tests\n' + ACTUAL_IMAGE_CHILD + ACTUAL_TOOL_OUTPUT + ACTUAL_STAGING_CHILD
                + '\ntest result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 462 filtered out; finished in 1.00s\n')
        self.assertEqual(v.test_terminal(text, names, [], 462, catalog=historical),
                         {'passed': sorted(names), 'ignored': [], 'filtered': 462})

    def test_known_nested_child_rejects_failure_unknown_extra_and_unclosed_frames(self):
        _, historical = updater_catalogs()
        name = 'native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata'
        child_record = f'test {name} ... ok\n'
        child_summary = 'test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 464 filtered out; finished in 0.68s\n'
        parent_summary = 'test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 464 filtered out; finished in 1.00s\n'
        wrap = lambda body: 'running 1 test\n' + body + '\n' + parent_summary
        self.assertEqual(v.test_terminal(wrap(ACTUAL_STAGING_CHILD), [name], [], 464, catalog=historical)['passed'], [name])
        bad = {
            'unknown-child': ACTUAL_STAGING_CHILD.replace(child_record, 'test foreign ... ok\n'),
            'failed-child': ACTUAL_STAGING_CHILD.replace(child_record, f'test {name} ... FAILED\n'),
            'ignored-child': ACTUAL_STAGING_CHILD.replace(child_record, f'test {name} ... ignored\n'),
            'duplicate-child-record': ACTUAL_STAGING_CHILD.replace(child_record, child_record * 2),
            'wrong-child-count': ACTUAL_STAGING_CHILD.replace('running 1 test\n', 'running 2 tests\n'),
            'missing-child-header': ACTUAL_STAGING_CHILD.replace('running 1 test\n', ''),
            'duplicate-child-header': ACTUAL_STAGING_CHILD.replace('running 1 test\n', 'running 1 test\n' * 2),
            'missing-child-record': ACTUAL_STAGING_CHILD.replace(child_record, ''),
            'missing-child-summary': ACTUAL_STAGING_CHILD.replace(child_summary, ''),
            'duplicate-child-summary': ACTUAL_STAGING_CHILD.replace(child_summary, child_summary * 2),
            'failed-child-summary': ACTUAL_STAGING_CHILD.replace('1 passed; 0 failed;', '0 passed; 1 failed;'),
            'wrong-child-passed': ACTUAL_STAGING_CHILD.replace('1 passed;', '2 passed;'),
            'wrong-child-ignored': ACTUAL_STAGING_CHILD.replace('0 ignored;', '1 ignored;'),
            'wrong-child-measured': ACTUAL_STAGING_CHILD.replace('0 measured;', '1 measured;'),
            'wrong-child-filtered': ACTUAL_STAGING_CHILD.replace('464 filtered out;', '463 filtered out;'),
            'missing-parent-status': ACTUAL_STAGING_CHILD[:-3],
            'failed-parent-status': ACTUAL_STAGING_CHILD[:-3] + 'FAILED\n',
            'premature-parent-status': ACTUAL_STAGING_CHILD.replace('running 1 test\n', 'ok\n'),
            'recursive-grandchild': ACTUAL_STAGING_CHILD.replace(child_record, f'test {name} ... \nrunning 1 test\n' + child_record),
            'extra-child-frame': ACTUAL_STAGING_CHILD.replace('\nok\n', '\nrunning 1 test\n' + child_record + child_summary + '\nok\n'),
        }
        for label, body in bad.items():
            with self.subTest(label=label), self.assertRaises(RuntimeError):
                v.test_terminal(wrap(body), [name], [], 464, catalog=historical)
        unknown = wrap(ACTUAL_STAGING_CHILD.replace(name, 'unknown::test'))
        with self.assertRaises(RuntimeError): v.test_terminal(unknown, ['unknown::test'], [], 464, catalog=historical)
        for invalid in [wrap(ACTUAL_STAGING_CHILD) + parent_summary,
                        wrap(ACTUAL_STAGING_CHILD + child_record),
                        parent_summary + wrap(ACTUAL_STAGING_CHILD),
                        wrap(ACTUAL_STAGING_CHILD).replace(parent_summary, parent_summary.replace('1 passed;', '2 passed;'))]:
            with self.subTest(text=invalid), self.assertRaises(RuntimeError):
                v.test_terminal(invalid, [name], [], 464, catalog=historical)
        with self.assertRaises(RuntimeError): v.test_terminal(wrap(ACTUAL_STAGING_CHILD), [name], [], None, catalog=historical)

    def test_current_nested_catalog_binds_all_names_and_credits_only_parent_records(self):
        current, historical = updater_catalogs()
        exact = set(v.decode(v.regular(P / 'UPDATER-EXACT64.json')))
        ignored = set(current['ignored'])
        passed = set(current['all']) - exact - ignored
        self.assertEqual((len(passed), len(ignored), len(exact)), (402, 1, 64))
        # Synthetic current-catalog transcript. The three ACTUAL_* constants
        # above remain byte-for-byte historical evidence, not new CI output.
        fragments = {
            'image_policy::tests::repack_preserves_android_metadata_and_adbd':
                ACTUAL_IMAGE_CHILD.replace('464 filtered out;', '466 filtered out;'),
            'native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata':
                ACTUAL_STAGING_CHILD.replace('464 filtered out;', '466 filtered out;'),
            'native_generation::tests::real_erofs_bundle_verifies_its_embedded_pair': ACTUAL_TOOL_OUTPUT,
        }
        self.assertTrue(set(fragments) <= passed)
        text = 'running 403 tests\n'
        for name in sorted(passed | ignored):
            text += fragments.get(name, f'test {name} ... ' + ('ignored' if name in ignored else 'ok') + '\n')
        text += '\ntest result: ok. 402 passed; 0 failed; 1 ignored; 0 measured; 64 filtered out; finished in 1.00s\n'
        self.assertEqual(v.test_terminal(text, passed, ignored, 64, catalog=current['all']),
                         {'passed': sorted(passed), 'ignored': sorted(ignored), 'filtered': 64})
        wrong_names = list(current['all'])
        wrong_names[wrong_names.index(sorted(passed)[0])] = 'foreign::same_size_catalog'
        for catalog in (None, historical, wrong_names, current['all'] + ['extra::case'],
                        current['all'][:-1] + [current['all'][0]]):
            with self.subTest(catalog=catalog), self.assertRaises(RuntimeError):
                v.test_terminal(text, passed, ignored, 64, catalog=catalog)
        for bad in (text.replace('466 filtered out;', '464 filtered out;', 1),
                    text.replace('466 filtered out;', '465 filtered out;', 1),
                    text.replace('1 ignored;', '0 ignored;', 1),
                    text.replace('64 filtered out;', '62 filtered out;', 1)):
            with self.subTest(text=bad), self.assertRaises(RuntimeError):
                v.test_terminal(bad, passed, ignored, 64, catalog=current['all'])

    def test_split_tool_output_requires_known_parent_and_exact_terminal(self):
        name = 'native_generation::tests::real_erofs_bundle_verifies_its_embedded_pair'
        summary = 'test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 464 filtered out; finished in 1.00s\n'
        wrap = lambda body: 'running 1 test\n' + body + '\n' + summary
        self.assertEqual(v.test_terminal(wrap(ACTUAL_TOOL_OUTPUT), [name], [], 464)['passed'], [name])
        for body in [ACTUAL_TOOL_OUTPUT[:-3], ACTUAL_TOOL_OUTPUT[:-3] + 'FAILED\n',
                     ACTUAL_TOOL_OUTPUT.replace('mkfs.erofs 1.9.4', 'unexpected tool'),
                     ACTUAL_TOOL_OUTPUT.replace('Build completed.', 'Build failed.', 1),
                     ACTUAL_TOOL_OUTPUT.replace('Processing / ...', 'running 1 test', 1),
                     ACTUAL_TOOL_OUTPUT.replace('Processing / ...', 'test foreign ... FAILED', 1),
                     ACTUAL_TOOL_OUTPUT.replace('Processing / ...', summary.rstrip(), 1),
                     ACTUAL_TOOL_OUTPUT + 'ok\n']:
            with self.subTest(body=body), self.assertRaises(RuntimeError):
                v.test_terminal(wrap(body), [name], [], 464)
        with self.assertRaises(RuntimeError):
            v.test_terminal(wrap(ACTUAL_TOOL_OUTPUT.replace(name, 'unknown::test')), ['unknown::test'], [], 464)


class OverlayControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = v.archive_entries(v.check(v.HERE / 'SOURCE-CAPSULE.tar.xz', v.CAPSULE))
        cls.parent = v.decode(cls.entries['SOURCE-MANIFEST.json'][1])
        cls.rows = [{'path': name, 'bytes': row['bytes'], 'sha256': row['sha256'],
                     'git_blob': row['git_blob'], 'mode': row['git_mode']}
                    for name, row in sorted(cls.parent['files'].items())]
        cls.compressed = v.check(v.HERE / 'SOURCE-OVERLAY.json.xz', v.OVERLAY)
        cls.packet = v.overlay_packet(cls.compressed)

    def clone(self):
        return v.decode(json.dumps(self.packet))

    def apply(self, packet):
        return v.apply_overlay(self.parent, self.rows, self.entries, packet)

    def test_overlay_complete_parent_and_successor_have_distinct_identities(self):
        inventory_sha = v.digest(v.regular(v.HERE / 'FILES.sha256'))['sha256']
        capsule = v.verify_capsule(inventory_sha)
        self.assertIsNone(v.HEAD_COMMIT)
        self.assertEqual(capsule['parent_manifest']['head'], v.PARENT_COMMIT)
        self.assertEqual(len(capsule['rows']), 2233)
        self.assertEqual(sum(row['bytes'] for row in capsule['rows']), 40728234)
        self.assertEqual(v.tree_id(capsule['rows']), '2eebf00f0b3e446168c1d6baeacbf1b4adc84db5')
        self.assertEqual(len(capsule['overlay_manifest']['paths']), 32)
        self.assertNotEqual(v.HEAD_TREE, v.PARENT_TREE)

    def test_overlay_rejects_wrong_base_omitted_extra_or_unsafe_member(self):
        name = 'Cargo.lock'
        mutations = []
        packet = self.clone(); packet['manifest']['paths'][name]['before']['sha256'] = '0' * 64
        mutations.append(packet)
        packet = self.clone(); del packet['files_base64'][name]; mutations.append(packet)
        packet = self.clone(); packet['files_base64']['extra'] = ''; mutations.append(packet)
        packet = self.clone()
        packet['manifest']['paths']['../escape'] = packet['manifest']['paths'].pop(name)
        packet['files_base64']['../escape'] = packet['files_base64'].pop(name)
        mutations.append(packet)
        packet = self.clone(); packet['manifest']['parent_head'] = '0' * 40; mutations.append(packet)
        packet = self.clone(); packet['manifest']['parent_tree'] = '0' * 40; mutations.append(packet)
        packet = self.clone(); packet['manifest']['source_commit'] = '0' * 40; mutations.append(packet)
        packet = self.clone(); packet['manifest']['runtime_qualified'] = True; mutations.append(packet)
        for packet in mutations:
            with self.subTest(packet=packet['manifest'].get('parent_head')), self.assertRaises(RuntimeError):
                self.apply(packet)

    def test_overlay_rejects_wrong_body_mode_size_blob_tree_and_count(self):
        name = 'Cargo.lock'
        changes = [('bytes', 1), ('sha256', '0' * 64),
                   ('git_blob', '0' * 40), ('git_mode', '100755')]
        for key, value in changes:
            packet = self.clone(); packet['manifest']['paths'][name]['after'][key] = value
            with self.subTest(field=key), self.assertRaises(RuntimeError):
                self.apply(packet)
        packet = self.clone(); packet['files_base64'][name] = v.base64.b64encode(b'wrong body').decode()
        with self.assertRaises(RuntimeError): self.apply(packet)
        # The combined overlay must include both actual MAC successor bodies.
        # A self-consistent old body/row must still fail the complete new tree gate.
        for name in ('runtime/droidloom-supervisor/src/production_mac.rs',
                     'runtime/droidloom-supervisor/src/production_mac_systemd.rs'):
            packet = self.clone()
            packet['manifest']['paths'][name]['after'] = dict(self.parent['files'][name])
            packet['files_base64'][name] = v.base64.b64encode(self.entries['source/' + name][1]).decode()
            with self.subTest(stale_mac_body=name), self.assertRaises(RuntimeError):
                self.apply(packet)
            packet = self.clone()
            del packet['manifest']['paths'][name]
            del packet['files_base64'][name]
            with self.subTest(omitted_mac_body=name), self.assertRaises(RuntimeError):
                self.apply(packet)
        # Both new M3 sources are absent in the baseline: complete removal
        # and a self-consistent wrong body/row must fail the exact final tree.
        for name in ('runtime/droidloom-supervisor/src/production_namespace_task_control_mac.rs',
                     'runtime/droidloom-supervisor/src/production_namespace_task_control_mac_tests.rs'):
            packet = self.clone()
            del packet['manifest']['paths'][name]
            del packet['files_base64'][name]
            with self.subTest(omitted_m3_body=name), self.assertRaises(RuntimeError):
                self.apply(packet)
            packet = self.clone(); body = b'changed M3 source\n'
            packet['manifest']['paths'][name]['after'] = {
                **v.digest(body), 'git_blob': v.object_id('blob', body), 'git_mode': '100644'}
            packet['files_base64'][name] = v.base64.b64encode(body).decode()
            with self.subTest(changed_m3_body=name), self.assertRaises(RuntimeError):
                self.apply(packet)
        # Neither selected-lock repair body can be omitted or replaced with
        # its self-consistent prior source without changing the full new tree.
        for name in ('tools/droidloom-update/src/coherent_images.rs',
                     'tools/droidloom-update/src/coherent_images_tests.rs'):
            packet = self.clone()
            packet['manifest']['paths'][name]['after'] = dict(self.parent['files'][name])
            packet['files_base64'][name] = v.base64.b64encode(self.entries['source/' + name][1]).decode()
            with self.subTest(stale_selected_lock_body=name), self.assertRaises(RuntimeError):
                self.apply(packet)
            packet = self.clone()
            del packet['manifest']['paths'][name]
            del packet['files_base64'][name]
            with self.subTest(omitted_selected_lock_body=name), self.assertRaises(RuntimeError):
                self.apply(packet)
        # Either current AppBridge repair body must remain in the exact successor.
        for name in ('runtime/droidloom-supervisor/src/application_probe.rs',
                     'runtime/droidloom-supervisor/src/production_control.rs'):
            packet = self.clone()
            packet['manifest']['paths'][name]['after'] = dict(self.parent['files'][name])
            packet['files_base64'][name] = v.base64.b64encode(self.entries['source/' + name][1]).decode()
            with self.subTest(stale_appbridge_body=name), self.assertRaises(RuntimeError):
                self.apply(packet)
            packet = self.clone()
            del packet['manifest']['paths'][name]
            del packet['files_base64'][name]
            with self.subTest(omitted_appbridge_body=name), self.assertRaises(RuntimeError):
                self.apply(packet)
        for key, value in [('candidate_tree_from_manifest', '0' * 40),
                           ('candidate_file_count', 2232), ('candidate_bytes', 40728233)]:
            packet = self.clone(); packet['manifest'][key] = value
            with self.subTest(field=key), self.assertRaises(RuntimeError):
                self.apply(packet)

    def test_overlay_decoder_rejects_truncation_trailing_frames_and_expansion(self):
        tiny = v.lzma.compress(b'{}')
        too_large = v.lzma.compress(b'a' * (v.OVERLAY_EXPANSION_MAX + 1))
        for raw in [self.compressed[:-1], tiny + tiny, tiny + b'trailing', too_large]:
            with self.subTest(size=len(raw)), self.assertRaises(RuntimeError):
                v.overlay_packet(raw)



if __name__ == '__main__':
    unittest.main()
