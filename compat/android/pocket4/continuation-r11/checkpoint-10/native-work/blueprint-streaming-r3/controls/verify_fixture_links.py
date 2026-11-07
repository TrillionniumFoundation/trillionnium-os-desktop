#!/usr/bin/env python3
"""Local actual-copy controls. Does not run Go or access any remote system."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import os
import tempfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def fixture(base, links):
    source = base/'aosp/build/blueprint'
    source.mkdir(parents=True)
    (source/'context.go').write_text('package blueprint\n')
    for category in ['dangling','symlinks']:
        (source/'pathtools/testdata'/category/'a/a/a').mkdir(parents=True)
        (source/'pathtools/testdata'/category/'f').write_text('owned fixture only\n')
    for relative,target in links.items():
        path = source/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.symlink_to(target)
    return source

def main():
    old = module(BASE/'blueprint-streaming-r2/controls/run_control.py', 'original_gate')
    new = module(HERE/'run_control.py', 'candidate_gate')
    reports = []
    with tempfile.TemporaryDirectory(prefix='fixture-links-',dir=HERE) as temporary:
        root = Path(temporary)
        def case(name, change=None, old_gate=False, should_pass=False, expected_path=None):
            work = root/name
            source = fixture(work, new.SOURCE_TEST_LINKS)
            gate = old if old_gate else new
            gate.SOURCE = work/'aosp'
            if change:
                change(source)
            try:
                rows = gate.copy_source_tree(source,work/'copy')
                assert should_pass, name+' unexpectedly accepted'
                links = [r for r in rows if r.get('kind')=='symlink']
                assert len(links)==10
                for r in links:
                    path = work/'copy'/r['relative']
                    assert path.is_symlink() and os.readlink(path)==r['target']
                    assert new.copied_link(path,r)['sha256']==r['sha256']
                regular = [r for r in rows if r.get('kind')!='symlink']
                assert {r['relative'] for r in regular}=={'context.go','pathtools/testdata/dangling/f','pathtools/testdata/symlinks/f'}
                for r in regular:
                    assert hashlib.sha256((work/'copy'/r['relative']).read_bytes()).hexdigest()==r['sha256']
                reports.append({'name':name,'pass':True,'copied_links':len(links),'regular_files':len(regular),'followed_link_contents':False})
            except RuntimeError as error:
                assert not should_pass, str(error)
                if expected_path:
                    assert str(source/expected_path) in str(error), str(error)
                reports.append({'name':name,'pass':True,'rejected':True,'error':str(error)})
        case('original_rejects_actual_fixture_shape',old_gate=True)
        case('all_ten_known_links_preserved',should_pass=True)
        def change_target(source):
            p=source/'pathtools/testdata/symlinks/b';p.unlink();p.symlink_to('/etc')
        case('known_target_changed_external',change_target,expected_path='pathtools/testdata/symlinks/b')
        case('unknown_directory_symlink',lambda s:(s/'unknown-dir').symlink_to('/tmp'),expected_path='unknown-dir')
        case('unknown_go_file_symlink',lambda s:(s/'unknown.go').symlink_to('context.go'),expected_path='unknown.go')
        case('unknown_dangling_symlink',lambda s:(s/'unknown').symlink_to('not-present'),expected_path='unknown')
        case('known_link_missing',lambda s:(s/'pathtools/testdata/symlinks/b').unlink())
        def regular_replacement(source):
            p=source/'pathtools/testdata/symlinks/b';p.unlink();p.write_text('changed\n')
        case('known_link_became_regular',regular_replacement,expected_path='pathtools/testdata/symlinks/b')
        path=root/'pin-link';path.symlink_to('before')
        pinned=new.held_link(path,'before');path.unlink();path.symlink_to('after')
        try:
            new.copied_link(path,pinned)
            raise AssertionError('changed link accepted after copy')
        except RuntimeError as error:
            reports.append({'name':'link_after_copy_mutation_rejected','pass':True,'error':str(error)})
        outside=root/'outside';outside.mkdir();(outside/'secret.go').write_text('never copied\n')
        work=root/'outside-target';source=fixture(work,new.SOURCE_TEST_LINKS);new.SOURCE=work/'aosp'
        (source/'escape').symlink_to(outside)
        try:
            new.copy_source_tree(source,work/'copy')
            raise AssertionError('unlisted external subtree accepted')
        except RuntimeError as error:
            assert 'escape' in str(error) and not list((work/'copy').rglob('secret.go'))
            reports.append({'name':'external_subtree_not_followed','pass':True,'error':str(error)})
    oldtree=ast.parse((BASE/'blueprint-streaming-r2/controls/run_control.py').read_text())
    newtree=ast.parse((HERE/'run_control.py').read_text())
    before={n.name:ast.dump(n,include_attributes=False) for n in oldtree.body if isinstance(n,ast.FunctionDef)}
    after={n.name:ast.dump(n,include_attributes=False) for n in newtree.body if isinstance(n,ast.FunctionDef)}
    names=['resource_text','resource_snapshot','begin_resources','finish_resources','command','dependency_files','cleanup_children']
    for name in names:
        assert before[name]==after[name], name
    for relative in ['controls/owned_streaming_test.go','0009-blueprint-stream-uncached-module-actions.patch','candidate/context.go','preimage/context.go']:
        assert (BASE/'blueprint-streaming-r2'/relative).read_bytes()==(HERE.parent/relative).read_bytes()
    report={'scope':'actual Python source-copy functions only; no Go compilation or remote operation',
            'controls':reports,'passed':len(reports),'failed':0,
            'unchanged_actual_function_AST':names,
            'Go_test_and_production_patch_exactly_unchanged':True}
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
