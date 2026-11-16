import importlib.util
import copy
import json
from pathlib import Path
import tempfile
import unittest

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('d7_verify_tests',P/'verify.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
spec=importlib.util.spec_from_file_location('d7_ci_tests',P/'run_ci.py');ci=importlib.util.module_from_spec(spec);spec.loader.exec_module(ci)


class Controls(unittest.TestCase):
    def test_actual_289_and_all21_ignored(self):
        manifest=v.decode(v.regular(P/'manifest.json'));catalog=v.test_catalog(manifest)
        text=v.regular(P/'evidence/runtime/normal/all-ordinary-supervisor-tests.stdout').decode()
        result=v.test_terminal(text,catalog['runtime_ordinary'],catalog['runtime_privileged_ignored'],0)
        self.assertEqual((len(result['passed']),len(result['ignored'])),(289,21))

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

    def test_release_receipts_reject_extra_missing_duplicate_cached_and_non_bin(self):
        names=['droidloom-supervisor','droidloomd','droidloom-source','droidloom-update']
        rows=[{'reason':'compiler-artifact','executable':'/fresh/release/'+name,
               'profile':{'test':False},'fresh':False,'target':{'name':name,'kind':['bin']}} for name in names]
        self.assertEqual(ci.select_release_artifacts(rows),rows)
        extra=copy.deepcopy(rows[0]);extra['target']['name']='droidloomctl'
        cached=copy.deepcopy(rows);cached[0]['fresh']=True
        library=copy.deepcopy(rows);library[0]['target']['kind']=['lib']
        for bad in [rows+[extra],rows[:-1],rows[:-1]+[rows[0]],cached,library]:
            with self.subTest(rows=bad),self.assertRaises(RuntimeError):ci.select_release_artifacts(bad)

    def test_directory_F9_detects_removed_fixture_and_external_working_directory_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'source';source.mkdir()
            path=source/'input';path.write_bytes(b'original');path.chmod(0o644)
            rows=[{'path':'input','mode':'100644','git_blob':v.object_id('blob',b'original'),**v.digest(b'original')}]
            tree=v.tree_id(rows);before=v.source_snapshot(source,rows,tree)
            with tempfile.TemporaryDirectory(dir=source):pass
            after=v.source_snapshot(source,rows,tree)
            self.assertEqual(before['files'],after['files'])
            self.assertNotEqual(before['directories'],after['directories'])
            private=ci.destinations(source,base/'target',base/'report.json')[3]
            private.mkdir(mode=0o700)
            with tempfile.TemporaryDirectory(dir=private):pass
            self.assertEqual(v.source_snapshot(source,rows,tree),after)

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

    def test_ci_target_cannot_contain_logs_or_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir()
            with self.assertRaises(RuntimeError):ci.destinations(source,source/'target',root/'report.json')
            with self.assertRaises(RuntimeError):ci.destinations(source,root/'target',root/'target/report.json')
            recipe,target,report,logs=ci.destinations(source,root/'target',root/'report.json')
            self.assertEqual(recipe,source);self.assertFalse(logs.is_relative_to(target))

    def test_both_full_git_roots_and_all167_original_evidence(self):
        index=v.regular(P/'FILES.sha256');manifest=v.verify_capsule(v.hashlib.sha256(index).hexdigest())
        self.assertEqual([manifest[x]['files'] for x in ('audio','runtime','head')],[1557,430,1595])
        self.assertEqual(len(manifest['selected_runtime_paths']),66)


if __name__=='__main__':
    unittest.main()
