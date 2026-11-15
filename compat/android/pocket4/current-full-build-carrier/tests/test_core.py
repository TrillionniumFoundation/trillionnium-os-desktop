"""Self-contained public core regressions; no field qualification records."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'src'
SESSION = tempfile.TemporaryDirectory(prefix='pocket4-full-carrier-core-')
TEMP = Path(SESSION.name)
OBSERVATIONS = []

def load(name):
    spec = importlib.util.spec_from_file_location('test_' + name, CANDIDATE / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def record(path):
    ref = checks.read_file(path)
    identity = ref.pop('identity')
    ref.update(device=identity[0], inode=identity[1], mode=identity[2], uid=identity[3], gid=identity[4], nlink=identity[5],
               mtime_seconds=identity[7] // 10**9, mtime_nanoseconds=identity[7] % 10**9,
               ctime_seconds=identity[8] // 10**9, ctime_nanoseconds=identity[8] % 10**9)
    return ref

def valid_input(lane, phase):
    item = producer.spec()['lanes'][lane]
    recipe = Path('/fixture/recipe'); source = Path('/fixture/source')
    value = {'schema': receipts.NAMES[lane] + '-inputs-v1', 'requested_targets': producer.targets(phase),
             'source_profile': 'exact-production651-source-user-vendor-image' if phase == 'vendor' else 'exact-production651-source-framework-asb-and-wm-targets',
             'projection_scope_targets': producer.targets(phase), 'product': producer.PRODUCT,
             'source_release': 'cp2a', 'build_variant': 'user', 'QPR1_source_identity_claim': False,
             'source_lock': {'path': str(recipe / 'android/manifest/production-full-source-lock.json'), 'sha256': producer.LOCK_SHA},
             'strict_allow_missing_dependencies': 'false', 'selinux_ignore_neverallows': 'false',
             'artifact_identity_qualified': False, 'vendor_artifact_identity_qualified': False,
             'official_device_tests_executed': False, 'binary_semantic_fix_qualified': False,
             'production_signing_qualified': False, 'whole_security_bulletin_qualified': False,
             'runtime_qualified': False, 'production_ready': False, 'regression_executed': False,
             'effective_projection': {'files': {item['project'] + '/' + name: sha for name, _, sha in item['fixed']}}}
    effective = [{'path': str(source / item['project'] / name), 'bytes': size, 'sha256': sha} for name, size, sha in item['fixed'] + (item['providers'] if lane in ('framework', 'wm') else [])]
    if lane in ('framework', 'wm'):
        value.update(original_frameworks_base_pin=item['project_pin'], CVE_rows=item['cves'],
                     effective_upstream_files_and_providers=effective,
                     official_complete_patches=[{'path': str(recipe / name), 'bytes': size, 'sha256': sha, 'commit': commit,
                                                 'url': 'https://android.googlesource.com/platform/frameworks/base/+/' + commit} for name, size, sha, commit in item['patches']])
        if lane == 'framework':
            value.update(same_fix_aliases_not_replayed=item['aliases'], official_test_modules=['FrameworksServicesTests', 'UsbTests', 'AudioServiceTests', 'WmTests'])
    else:
        value.update(original_project_pin=item['project_pin'], effective_upstream_files=effective,
                     original_Android_bp_sha256=item['providers'][0][2],
                     official_patches_in_order=[{'path': str(recipe / name), 'bytes': size, 'sha256': sha, 'official_commit': item['commits'][i]} for i, (name, size, sha) in enumerate(item['patches'])])
        if lane == 'avb':
            value.update(CVE='CVE-2026-58956', upstream_bug='A-461507723', alternate_commit_not_replayed='119d66ea37241def63e715658ac02c414bd3d0e5', original_file_equals_official_patch_preimage=True)
        else:
            value.update(CVE='CVE-2026-58936', first_official_fix_parent='7d98050ef8d9d17d495eb178b8217548437cedf1', original_project_pin_is_first_fix_parent=False, all_five_original_files_equal_official_patch_preimages=True)
    return value

checks = load('carrier_checks')
producer = load('producer_contract')
receipts = load('build_receipts')
importer = load('cohort_import')
projection = load('production651_projection')
elf = load('elf_closure')


class InputReceipts(unittest.TestCase):
    def check(self, value, lane='framework', phase='wm'):
        return receipts.lane_input(value, lane, phase, Path('/fixture/recipe'), Path('/fixture/source'))

    def test_all_actual_lane_specs_accept_complete_input(self):
        for lane, phase in [('framework', 'wm'), ('wm', 'wm'), ('avb', 'wm'), ('avb', 'vendor'), ('libpng', 'vendor')]:
            with self.subTest(lane=lane, phase=phase): self.check(valid_input(lane, phase), lane, phase)

    def test_missing_fourteenth_patch_rejected(self):
        value = valid_input('framework', 'wm'); value['official_complete_patches'].pop()
        with self.assertRaisesRegex(RuntimeError, 'patch'): self.check(value)

    def test_changed_patch_hash_rejected(self):
        value = valid_input('framework', 'wm'); value['official_complete_patches'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'patch'): self.check(value)

    def test_effective_provider_omission_rejected(self):
        value = valid_input('framework', 'wm'); value['effective_upstream_files_and_providers'].pop()
        with self.assertRaisesRegex(RuntimeError, 'providers'): self.check(value)

    def test_old_wm_only_targets_rejected(self):
        value = valid_input('framework', 'wm'); value['requested_targets'] = ['services', 'WmTests']
        with self.assertRaisesRegex(RuntimeError, 'targets'): self.check(value)

    def test_neverallow_relaxation_rejected(self):
        value = valid_input('framework', 'wm'); value['selinux_ignore_neverallows'] = 'true'
        with self.assertRaisesRegex(RuntimeError, 'neverallow'): self.check(value)

    def test_missing_dependency_relaxation_rejected(self):
        value = valid_input('framework', 'wm'); value['strict_allow_missing_dependencies'] = 'true'
        with self.assertRaisesRegex(RuntimeError, 'dependency'): self.check(value)

    def test_cp3a_relabel_rejected(self):
        value = valid_input('framework', 'wm'); value['source_release'] = 'cp3a'
        with self.assertRaisesRegex(RuntimeError, 'cp2a'): self.check(value)

    def test_runtime_and_signature_credit_rejected(self):
        for flag in ['runtime_qualified', 'QPR1_source_identity_claim', 'production_ready', 'production_signing_qualified', 'official_device_tests_executed']:
            value = valid_input('framework', 'wm'); value[flag] = True
            with self.subTest(flag=flag), self.assertRaisesRegex(RuntimeError, 'cannot grant'): self.check(value)

    def test_missing_actual_fixed_projection_rejected(self):
        value = valid_input('framework', 'wm'); value['effective_projection']['files'].pop(next(iter(value['effective_projection']['files'])))
        with self.assertRaisesRegex(RuntimeError, 'projection'): self.check(value)

    def test_avb_alternate_commit_not_substituted(self):
        value = valid_input('avb', 'vendor'); value['official_patches_in_order'][0]['official_commit'] = value['alternate_commit_not_replayed']
        with self.assertRaisesRegex(RuntimeError, 'patches'): self.check(value, 'avb', 'vendor')

    def test_missing_live_pidfd_input_observation_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'observation missing'): receipts.security_completion('/missing', '/missing', '/missing', 'wm', None)

class ArtifactReceipts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEMP); self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'out'; self.product = self.out / 'target/product/droidloom_x86_64'
        services = self.product / 'system/framework/services.jar'; services.parent.mkdir(parents=True)
        with zipfile.ZipFile(services, 'w') as archive: archive.writestr('classes.dex', b'offline fixture, not Android output')
        self.info = {}; apk_paths = []
        for module, provider in producer.TEST_PROVIDERS.items():
            apk = self.product / 'data/app' / module / (module + '.apk'); apk.parent.mkdir(parents=True)
            with zipfile.ZipFile(apk, 'w') as archive: archive.writestr('AndroidManifest.xml', b'offline fixture')
            self.info[module] = {'path': [provider], 'installed': [str(apk)]}
            apk_paths.append((module, provider, apk))
        self.info_path = self.product / 'module-info.json'; self.info_path.write_text(json.dumps(self.info))
        self.value = {'actual_output_files': [record(services)] + [{'module': module, 'provider': provider, 'artifact': record(apk)} for module, provider, apk in apk_paths] + [{'module_info': record(self.info_path)}]}

    def check(self): return receipts.framework_artifacts(self.out, self.value)

    def update_info_ref(self):
        self.info_path.write_text(json.dumps(self.info)); self.value['actual_output_files'][-1]['module_info'] = record(self.info_path)

    def test_complete_services_metadata_and_four_apks_pass(self):
        self.assertEqual(len(self.check()), 6)

    def test_missing_test_output_record_rejected(self):
        self.value['actual_output_files'].pop(2)
        with self.assertRaises(RuntimeError): self.check()

    def test_empty_test_apk_rejected(self):
        row = self.value['actual_output_files'][1]['artifact']; Path(row['path']).write_bytes(b'')
        row.update(record(row['path']))
        with self.assertRaisesRegex(RuntimeError, 'empty'): self.check()

    def test_wrong_provider_metadata_rejected(self):
        self.info['WmTests']['path'] = ['frameworks/base/foreign/tests']; self.update_info_ref()
        with self.assertRaisesRegex(RuntimeError, 'provider'): self.check()

    def test_relative_installed_apk_rejected(self):
        self.info['WmTests']['installed'] = ['data/app/WmTests/WmTests.apk']; self.update_info_ref()
        with self.assertRaisesRegex(RuntimeError, 'absolute product'): self.check()

    def test_escaping_installed_apk_rejected(self):
        self.info['WmTests']['installed'] = [str(self.product / '..' / 'other.apk')]; self.update_info_ref()
        with self.assertRaisesRegex(RuntimeError, 'absolute product'): self.check()

    def test_same_bytes_new_inode_rejected(self):
        path = Path(self.value['actual_output_files'][1]['artifact']['path']); raw = path.read_bytes()
        other = path.with_suffix('.replacement'); other.write_bytes(raw); other.replace(path)
        with self.assertRaisesRegex(RuntimeError, 'identity'): self.check()

    def test_same_bytes_changed_mode_rejected(self):
        path = Path(self.value['actual_output_files'][1]['artifact']['path']); path.chmod(0o400)
        with self.assertRaisesRegex(RuntimeError, 'identity'): self.check()

    def test_hardlinked_output_rejected(self):
        path = Path(self.value['actual_output_files'][1]['artifact']['path']); os.link(path, path.with_suffix('.extra'))
        with self.assertRaisesRegex(RuntimeError, 'single-link'): self.check()

    def test_symlink_ancestor_rejected(self):
        path = self.product / 'data'; moved = self.product / 'moved-data'; path.rename(moved); path.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'ancestor'): self.check()

    def test_duplicate_module_metadata_key_rejected(self):
        self.info_path.write_text('{"WmTests":{},"WmTests":{}}'); self.value['actual_output_files'][-1]['module_info'] = record(self.info_path)
        with self.assertRaisesRegex(RuntimeError, 'duplicate JSON'): self.check()

    def test_duplicate_or_shared_apk_metadata_rejected(self):
        self.info['WmTests']['installed'] *= 2; self.update_info_ref()
        with self.assertRaisesRegex(RuntimeError, 'duplicate'): self.check()

class FilesystemBounds(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEMP); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)

    def test_regular_hash_and_full_identity_pass(self):
        p = self.root / 'input'; p.write_bytes(b'original')
        ref = checks.read_file(p)
        self.assertEqual(ref['sha256'], hashlib.sha256(b'original').hexdigest())
        self.assertEqual(checks.exact_file(ref, p, identity=True), ref)

    def test_real_fifo_rejected_without_blocking_all_readers(self):
        p = self.root / 'fifo'; os.mkfifo(p)
        for module, function in [('carrier_checks', 'read_file'), ('cohort_import', 'reference'), ('ai395_build_support', 'file_ref')]:
            code = "import importlib.util,sys,time\ns=importlib.util.spec_from_file_location('bound_reader',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\nt=time.monotonic()\ntry:getattr(m,sys.argv[2])(sys.argv[3])\nexcept RuntimeError:print(time.monotonic()-t);raise SystemExit(0)\nraise SystemExit(2)\n"
            with self.subTest(module=module):
                run = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(CANDIDATE / (module + '.py')), function, str(p)], capture_output=True, text=True, timeout=2)
                self.assertEqual(run.returncode, 0, run.stderr); self.assertLess(float(run.stdout), 0.5)
                OBSERVATIONS.append({'kind': 'real_fifo_nonblocking_rejection', 'reader': module + '.' + function,
                                     'elapsed_seconds': float(run.stdout), 'outer_timeout_seconds': 2,
                                     'returncode': run.returncode, 'stderr': run.stderr})

    def test_empty_directories_included(self):
        (self.root / '.git/refs/empty').mkdir(parents=True)
        dirs = checks.directory_refs(self.root)
        self.assertIn('.git/refs/empty', dirs); checks.verify_directories(self.root, dirs)

    def test_unexpected_empty_directory_rejected(self):
        (self.root / 'known').mkdir(); dirs = checks.directory_refs(self.root)
        (self.root / 'unknown').mkdir()
        with self.assertRaisesRegex(RuntimeError, 'membership'): checks.verify_directories(self.root, dirs)

    def test_deleted_empty_directory_rejected(self):
        (self.root / 'empty').mkdir(); dirs = checks.directory_refs(self.root); (self.root / 'empty').rmdir()
        with self.assertRaisesRegex(RuntimeError, 'membership'): checks.verify_directories(self.root, dirs)

class ElfDependencies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(dir=TEMP); cls.root = Path(cls.build.name)
        compiler = shutil.which('cc')
        if compiler is None: raise RuntimeError('actual local C compiler required for meaningful ELF fixtures')
        out = cls.root / 'out'; lib = out / 'host/linux-x86/lib64'; binary = out / 'host/linux-x86/bin'; lib.mkdir(parents=True); binary.mkdir()
        for name, body in [('leaf', 'int leaf(void){return 7;}'), ('middle', 'extern int leaf(void);int middle(void){return leaf();}'), ('entry', 'extern int middle(void);void _start(void){volatile int x=middle();(void)x;for(;;){}}')]:
            (cls.root / (name + '.c')).write_text(body)
        commands = [
            [compiler, '-fPIC', '-shared', '-nostdlib', '-Wl,-soname,libleaf.so', str(cls.root / 'leaf.c'), '-o', str(lib / 'libleaf.so')],
            [compiler, '-fPIC', '-shared', '-nostdlib', '-Wl,-soname,libmiddle.so', '-Wl,-rpath,$ORIGIN', str(cls.root / 'middle.c'), '-L' + str(lib), '-Wl,--no-as-needed', '-lleaf', '-o', str(lib / 'libmiddle.so')],
            [compiler, '-fPIE', '-pie', '-nostdlib', '-Wl,-e,_start', '-Wl,-rpath,$ORIGIN/../lib64', str(cls.root / 'entry.c'), '-L' + str(lib), '-Wl,--no-as-needed', '-lmiddle', '-o', str(binary / 'secilc')],
        ]
        for args in commands:
            subprocess.run(args, check=True, capture_output=True, timeout=15)
        cls.fixture = out
        OBSERVATIONS.append({'kind': 'real_local_linker_fixture', 'commands': commands,
                             'compiler': checks.read_file(Path(compiler).resolve()),
                             'files': [checks.read_file(path) for path in [lib / 'libleaf.so', lib / 'libmiddle.so', binary / 'secilc']],
                             'Android_builds': 0, 'output_ELFs_executed': False})

    @classmethod
    def tearDownClass(cls): cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TEMP); self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'out'; shutil.copytree(self.fixture, self.out)
        self.exe = self.out / 'host/linux-x86/bin/secilc'; self.ref = checks.read_file(self.exe)
        self.meta = elf.parse_elf(self.exe.read_bytes())
        loader = Path(self.meta['interpreter']).resolve(strict=True)
        self.binding = {'loader_path': self.meta['interpreter'], 'reference': checks.read_file(loader)}

    def capture(self): return elf.capture(self.ref, self.out, interpreter_reference=self.binding)

    def test_real_linked_two_level_dependency_graph_passes(self):
        result = self.capture()
        self.assertTrue(result['static_dependency_closure_complete'])
        self.assertEqual({edge['DT_NEEDED'] for edge in result['dependencies']}, {'libmiddle.so', 'libleaf.so'})
        self.assertFalse(result['loader_resolution_qualified']); self.assertFalse(result['tool_execution_qualified'])
        OBSERVATIONS.append({'kind': 'actual_transitive_ELF_fixture_closure', 'result': result})

    def test_missing_transitive_library_is_failure(self):
        (self.out / 'host/linux-x86/lib64/libleaf.so').unlink()
        with self.assertRaisesRegex(RuntimeError, 'unresolved actual DT_NEEDED'): self.capture()

    def reject_unmodeled_loader_directive(self, option, tag_name):
        # An actual linker emits a load directive in a transitive leaf with no
        # DT_NEEDED entries. The absent object is invisible to NEEDED traversal.
        # Do not execute this fixture or use ldd: parser/capture rejection is the
        # boundary under test, independently of this host's loader behavior.
        leaf = self.out / 'host/linux-x86/lib64/libleaf.so'
        missing = leaf.parent / 'libunretained.so'
        self.assertFalse(missing.exists())
        args = [shutil.which('cc'), '-fPIC', '-shared', '-nostdlib',
                '-Wl,-soname,libleaf.so', '-Wl,--' + option + ',libunretained.so',
                str(self.root / 'leaf.c'), '-o', str(leaf)]
        subprocess.run(args, check=True, capture_output=True, timeout=15)
        message = 'unsupported ELF load directive ' + tag_name
        with self.assertRaisesRegex(RuntimeError, message):
            elf.parse_elf(leaf.read_bytes())
        with self.assertRaisesRegex(RuntimeError, message):
            self.capture()
        OBSERVATIONS.append({'kind': 'real_linker_unmodeled_load_directive',
                             'option': option, 'dynamic_tag': tag_name,
                             'argv': args, 'library_missing': not missing.exists(),
                             'output_ELFs_executed': False})

    def test_transitive_filter_directive_is_rejected(self):
        self.reject_unmodeled_loader_directive('filter', 'DT_FILTER')

    def test_transitive_auxiliary_directive_is_rejected(self):
        self.reject_unmodeled_loader_directive('auxiliary', 'DT_AUXILIARY')

    def test_transitive_audit_directive_is_rejected(self):
        self.reject_unmodeled_loader_directive('audit', 'DT_AUDIT')

    def test_transitive_depaudit_directive_is_rejected(self):
        self.reject_unmodeled_loader_directive('depaudit', 'DT_DEPAUDIT')

    def test_missing_interpreter_binding_is_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'interpreter'): elf.capture(self.ref, self.out)

    def test_escaping_library_symlink_is_failure(self):
        path = self.out / 'host/linux-x86/lib64/libleaf.so'; external = Path(self.temp.name) / 'outside.so'; path.rename(external); path.symlink_to(external)
        with self.assertRaisesRegex(RuntimeError, 'alias escaped'): self.capture()

    def test_valid_owned_library_alias_is_retained(self):
        path = self.out / 'host/linux-x86/lib64/libleaf.so'; path.rename(path.with_name('libleaf.so.real')); path.symlink_to('libleaf.so.real')
        result = self.capture(); self.assertIn(str(path), result['aliases'])

    def test_same_name_wrong_soname_is_failure(self):
        path = self.out / 'host/linux-x86/lib64/libleaf.so'; path.write_bytes((self.out / 'host/linux-x86/lib64/libmiddle.so').read_bytes())
        with self.assertRaisesRegex(RuntimeError, 'SONAME'): self.capture()

    def test_dependency_replaced_after_selection_is_failure(self):
        path = self.out / 'host/linux-x86/lib64/libleaf.so'
        original = path.read_bytes()
        self.assertEqual(original.count(b'libleaf.so\0'), 1)
        replacement = original.replace(b'libleaf.so\0', b'libevil.so\0')
        self.assertEqual(elf.parse_elf(replacement)['soname'], 'libevil.so')
        self.assertEqual(elf.parse_elf(replacement)['needed'], [])
        original_read = elf._read; selected_reads = []
        def replace_after_real_read(selected):
            value = original_read(selected)
            if Path(selected) == path:
                selected_reads.append(value[0])
                if len(selected_reads) == 1:
                    temporary = path.with_name('replacement.so')
                    temporary.write_bytes(replacement); os.replace(temporary, path)
            return value
        elf._read = replace_after_real_read
        try:
            with self.assertRaisesRegex(RuntimeError, 'whole file (bytes|F9) differ|dependency snapshot'):
                self.capture()
        finally:
            elf._read = original_read
        self.assertEqual(len(selected_reads), 1)
        self.assertNotEqual(checks.read_file(path)['identity'], selected_reads[0]['identity'])
        OBSERVATIONS.append({'kind': 'actual_library_replacement_after_selection_rejected',
                             'selected_reads': len(selected_reads), 'first': selected_reads[0],
                             'replacement': checks.read_file(path), 'ELF_execution': False})

    def test_dynamic_segment_mapping_disagreement_is_failure(self):
        # Fixed independent ELF byte layout: LOAD maps vaddr 4096 to file 0;
        # its actual dynamic table is at 256, and its string table is at 512.
        def fixture(needed=(), soname=None, runpath=None):
            strings = bytearray(b'\0'); dynamic = []
            for tag, text in [(1, name) for name in needed] + ([(14, soname)] if soname else []) + ([(29, runpath)] if runpath else []):
                dynamic.append((tag, len(strings))); strings.extend(text.encode() + b'\0')
            dynamic.extend(((5, 4096 + 512), (10, len(strings)), (0, 0)))
            raw = bytearray(1024); raw[:16] = b'\x7fELF\x02\x01\x01' + b'\0' * 9
            struct.pack_into('<HHIQQQIHHHHHH', raw, 16, 3, 62, 1, 4096, 64, 0, 0, 64, 56, 2, 0, 0, 0)
            struct.pack_into('<IIQQQQQQ', raw, 64, 1, 5, 0, 4096, 4096, len(raw), len(raw), 4096)
            struct.pack_into('<IIQQQQQQ', raw, 120, 2, 4, 256, 4096 + 256, 4096 + 256, len(dynamic) * 16, len(dynamic) * 16, 8)
            for index, item in enumerate(dynamic): struct.pack_into('<qQ', raw, 256 + index * 16, *item)
            raw[512:512 + len(strings)] = strings
            return raw
        original = fixture(['libhidden.so'], runpath='$ORIGIN/../lib64')
        self.exe.write_bytes(original)
        (self.out / 'host/linux-x86/lib64/libhidden.so').write_bytes(fixture(soname='libhidden.so'))
        positive = elf.capture(checks.read_file(self.exe), self.out)
        self.assertEqual([edge['DT_NEEDED'] for edge in positive['dependencies']], ['libhidden.so'])
        cases = {}
        shadow = bytearray(original); struct.pack_into('<Q', shadow, 120 + 8, 768)
        string_size = original.index(0, 512 + 1 + len('libhidden.so') + 1) - 512 + 1
        for index, item in enumerate(((5, 4096 + 512), (10, string_size), (0, 0))):
            struct.pack_into('<qQ', shadow, 768 + index * 16, *item)
        self.assertEqual(struct.unpack_from('<qQ', shadow, 256)[0], 1)
        cases['shadow_offset_hides_real_needed'] = shadow
        unmapped = bytearray(original); struct.pack_into('<Q', unmapped, 120 + 16, 8192 + 256)
        cases['unmapped_dynamic_address'] = unmapped
        partial = bytearray(original); struct.pack_into('<Q', partial, 64 + 32, 272)
        cases['dynamic_range_extends_past_file_backing'] = partial
        ambiguous = bytearray(original); struct.pack_into('<H', ambiguous, 56, 3); ambiguous[176:232] = original[64:120]
        cases['two_full_load_mappings'] = ambiguous
        overlap = bytearray(original); struct.pack_into('<H', overlap, 56, 3)
        struct.pack_into('<IIQQQQQQ', overlap, 176, 1, 4, 272, 4096 + 272, 4096 + 272, 16, 16, 8)
        cases['partial_load_overlap_inside_dynamic_range'] = overlap
        overflow = bytearray(original); struct.pack_into('<Q', overflow, 64 + 16, 2**64 - 512)
        cases['load_virtual_range_overflow'] = overflow
        for name, raw in cases.items():
            with self.subTest(case=name, stage='parser'), self.assertRaisesRegex(RuntimeError, 'ELF (dynamic|virtual)'):
                elf.parse_elf(raw)
            self.exe.write_bytes(raw)
            with self.subTest(case=name, stage='capture'), self.assertRaisesRegex(RuntimeError, 'ELF (dynamic|virtual)'):
                elf.capture(checks.read_file(self.exe), self.out)
        OBSERVATIONS.append({'kind': 'independent_dynamic_load_mapping_negatives_rejected',
                             'cases': sorted(cases), 'positive_needed': ['libhidden.so'],
                             'ELF_execution': False})

    def test_truncated_elf_is_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'program headers'): elf.parse_elf(self.exe.read_bytes()[:64])

    def test_origin_tokens_have_exact_boundaries(self):
        origin = self.out / 'host/linux-x86/bin'
        for value in ['$ORIGIN/../lib64', '${ORIGIN}/../lib64', '$ORIGIN', '${ORIGIN}']:
            with self.subTest(value=value): self.assertTrue(elf._runpath_paths(value, origin, self.out))
        for value in ['$ORIGINfoo', '${ORIGIN}foo', '$ORIGIN_suffix/lib', '$ORIGIN:relative', '$LIB', '$PLATFORM', '']:
            with self.subTest(value=value), self.assertRaises(RuntimeError): elf._runpath_paths(value, origin, self.out)

class IntegrationSource(unittest.TestCase):

    def test_actual_controller_stops_before_historical_path_access(self):
        code = "import runpy,sys,types\nsys.modules['p4_storage_entry']=types.SimpleNamespace(proof={'role':'wm_inner'})\ntry:runpy.run_path(sys.argv[1],run_name='__main__')\nexcept RuntimeError as e:\n assert str(e).startswith('SOURCE_ONLY_CANDIDATE:'),str(e)\n print(str(e));raise SystemExit(0)\nraise SystemExit(2)\n"
        run = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(CANDIDATE / 'full_controller.py')], capture_output=True, text=True, timeout=2)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('fresh finite storage owner', run.stdout)

    def test_no_undefined_wm_completion_or_old_target(self):
        text = (CANDIDATE / 'full_controller.py').read_text()
        tree = ast.parse(text)
        self.assertNotIn('wm_completion()', text)
        self.assertIn('framework_completion', {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)})
        self.assertIn("else 'framework-security-build'", text)
        self.assertIn('TARGETS=producer.targets(PHASE)', text)
        self.assertIn('receipts.live_inputs(OUT,RECIPE,SOURCE,PHASE)', text)

    def test_observer_requests_same_six_actual_soong_targets(self):
        observer = load('production651_wm_observation')
        self.assertEqual(observer.current_expected_ui_argv(observer.OUT)[3:], producer.FRAMEWORK_TARGETS)
        self.assertIn('framework-security-build', observer.NORMAL_ARGV)
        self.assertEqual((observer.UPDATE_REF['bytes'], observer.UPDATE_REF['sha256']), producer.TOOL_PINS['droidloom-update'])

    def test_controller_retains_original_critical_runtime_gates(self):
        text = (CANDIDATE / 'full_controller.py').read_text()
        for token in ['s.serial_lock()', 's.work_lock_probe(WORK', "row['lifecycle']['pidfd_closed'] is False", 'held.verify_running', "'ALLOW_MISSING_DEPENDENCIES':'false'", "'SELINUX_IGNORE_NEVERALLOWS':'false'", 'ARGV,21600', 's.admission(ROOT)', "source_qualification(commands,'after',True)", 's.validate_inner_resource_retirement', 'projection.verify_restored', "all(r['owned_retirement_complete']", 'producer.require_new_execution_binding()']:
            with self.subTest(token=token):
                self.assertIn(token, text)

class ExecutionGate(unittest.TestCase):

    def test_no_execution_override(self):
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_ONLY_CANDIDATE'):
            producer.require_new_execution_binding()
        with self.assertRaisesRegex(RuntimeError, 'SOURCE_ONLY_CANDIDATE'):
            importer.import_coherent_tools()

def tearDownModule():
    SESSION.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)
