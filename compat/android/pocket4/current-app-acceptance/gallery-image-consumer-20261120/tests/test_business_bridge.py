"""Targeted controls for the two real legacy identity/admission regressions."""
import ast
import importlib.util
import hashlib
from pathlib import Path
import re
import stat
import tempfile
import types
import unittest
import os
import copy
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


class BusinessBridge(unittest.TestCase):
    def test_rotation_compares_all_29_permissions_and_keeps_27_android_diagnostics(self):
        original=load(ROOT/'dependencies/gallery_identity_qpr1.py','original_identity_fixture')
        diagnostics=load(ROOT/'generated/rotation/bounded_diagnostics.py','new_diagnostics')
        identity=load(ROOT/'generated/shared/gallery_image_identity.py','new_identity')
        rows=original.EXPECTED['all_permission_rows']
        self.assertEqual(len(rows),29)
        raw=('Packages:\n  Package [com.android.gallery3d] (offline-model):\n'+
             ''.join('      '+row+'\n' for row in rows)).encode()
        diagnostics.TARGETS={'com.android.gallery3d':10112}
        session=types.SimpleNamespace(android=lambda argv,timeout:raw)
        result=diagnostics.permissions(session,lambda *args:None,'offline-parser-control')['com.android.gallery3d']
        self.assertEqual(result['permission_rows'],sorted(rows))
        self.assertEqual(len(result['android_permission_rows']),27)
        self.assertEqual({row.split(':',1)[0] for row in result['permission_rows']},set(identity.PERMISSION_NAMES))
        for defective in (rows[:-1],rows[:-1]+[rows[0]]):
            bad=('Packages:\n  Package [com.android.gallery3d] (offline-model):\n'+
                 ''.join('      '+row+'\n' for row in defective)).encode()
            session.android=lambda argv,timeout,bad=bad:bad
            with self.assertRaisesRegex(RuntimeError,'ALL_29_ACTUAL_PERMISSION_ROWS_REQUIRED'):
                diagnostics.permissions(session,lambda *args:None,'offline-negative')

    def test_directory_identity_uses_current_owner_mapping_for_every_package_reader(self):
        paths=[ROOT/'generated/shared/gallery_image_identity.py',ROOT/'generated/rotation/rotation_package.py']
        paths += [ROOT/'generated'/role/name for role in ('video','seek','album')
                  for name in ('video_identity.py','video_fixture.py')]
        for path in paths:
            with self.subTest(path=path.name):
                tree=ast.parse(path.read_text())
                comparisons=[node for node in ast.walk(tree) if isinstance(node,ast.Compare)
                             and 'st_uid' in ast.unparse(node) and 'st_gid' in ast.unparse(node)]
                self.assertEqual(len(comparisons),1)
                expr=ast.Expression(comparisons[0]);ast.fix_missing_locations(expr)
                code=compile(expr,str(path),'eval')
                env={'info':types.SimpleNamespace(st_uid=110112,st_gid=210112),'uid':10112,'expected_uid':10112,
                     'session':types.SimpleNamespace(mapped_owner=lambda uid:(100000+uid,200000+uid))}
                self.assertTrue(eval(code,env))
                env['info'].st_gid=110112
                self.assertFalse(eval(code,env))
                env['info']=types.SimpleNamespace(st_uid=10112,st_gid=10112)
                self.assertFalse(eval(code,env))

    def test_native_capture_uses_existing_zero_fd_host_recorder_contract(self):
        # This is the verbatim original run_recorded interface copied by the
        # independent reviewer from its pinned 12813-byte support module. The
        # guard below ends execution before any child/process action.
        path=ROOT/'dependencies/business_commands.py'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         'cfe92077ebb75db4f7f0fd577fcd7e6d664afd9338128a05435512549ceeb1f3')
        tree=ast.parse(path.read_text())
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='run_recorded')
        module=ast.Module(body=[function],type_ignores=[]);ast.fix_missing_locations(module)
        class GuardReached(Exception):pass
        def need(value,why):
            if not value:raise RuntimeError(why)
        def guard(**kw):raise GuardReached()
        env={'need':need,'re':re,'os':os,'Path':Path,'stat':stat,'load_capture':lambda:None}
        exec(compile(module,str(path),'exec'),env)
        custody=load(ROOT/'src/gallery_image_custody.py','new_custody_contract')
        source=ast.parse((ROOT/'src/gallery_image_custody.py').read_text())
        call=next(node for node in ast.walk(source) if isinstance(node,ast.Call)
                  and isinstance(node.func,ast.Attribute) and node.func.attr=='run_recorded')
        descriptors=ast.literal_eval(next(keyword.value for keyword in call.keywords if keyword.arg=='pass_fds'))
        self.assertEqual(descriptors,())
        with tempfile.TemporaryDirectory() as directory:
            argv=['/usr/bin/droidloom-applications','--inspect-package',custody.PACKAGE,'--user','0','--socket','/run/droidloom/control.sock']
            args=dict(protected_pids=[2],mutation=False,pass_fds=descriptors,host_env={},check=False,
                      output_bound=custody.MAX_OUTPUT)
            with self.assertRaises(GuardReached):
                env['run_recorded']('native-image-custody',argv,custody.CAPTURE_SECONDS,directory,guard,**args)
            args['pass_fds']=(123,)
            with self.assertRaisesRegex(RuntimeError,'EXACT_HELD_DESCRIPTOR_SET_REQUIRED'):
                env['run_recorded']('native-image-custody',argv,custody.CAPTURE_SECONDS,directory,guard,**args)

    def test_entry_rejects_saved_installation_and_imported_custody_fields(self):
        entry=load(ROOT/'src/gallery_image_entry.py','new_image_entry')
        for extra in ('installation','image_custody','socket','pid'):
            request={'schema':'pocket4-gallery-image-request-v1','baseline':{},'qualification':{},'output':'/unreached','native_release':{},extra:{}}
            with self.assertRaisesRegex(RuntimeError,'NO_IMPORTED_IMAGE_RECEIPT_OR_INSTALL_REQUEST'):
                entry.validate_request(request,'rotation')

    def test_effective_resource_report_requires_live_binding_and_fresh_numbers(self):
        # Offline report-consumer controls only. This model has no pidfd,
        # native-parent custody or authority to execute a Gallery leaf.
        support=load(ROOT/'generated/shared/gallery_image_support.py','new_resource_report_controls')
        report={'schema':'pocket4-held-effective-leaf-resources-v1',
                'cgroup':'0::/bounded/droidloom-app-gallery-leaf-42-7',
                'limiting_ancestor':'0::/bounded',
                'limits':{'cpu.max':'200000 100000','memory.max':'2147483648','memory.swap.max':'0','pids.max':'64'},
                'child_local_limits':{'cpu.max':'max 100000','memory.max':'max'},
                'affinity':[20],'memory_events':{'oom':0,'oom_kill':0,'oom_group_kill':0},
                'memory_peak_bytes':4096,'swap_current_bytes':0,'native_parent_pid':42,
                'native_parent_start_ticks':12345,'hierarchy_is_within_original_native_retirement_scope':True}
        with self.assertRaisesRegex(RuntimeError,'ONE_LIVE_OWNED_NATIVE_RESOURCE_SCOPE_REQUIRED'):
            support.bind_resource_scope(report)
        class OwnedLeafResources:
            def __init__(self):self.calls=0;self.value=copy.deepcopy(report)
            def report(self):self.calls+=1;return copy.deepcopy(self.value)
        scope=OwnedLeafResources();support.bind_resource_scope(scope)
        with mock.patch.object(support.Path,'read_text',return_value=report['cgroup']), \
             mock.patch.object(support.os,'sched_getaffinity',return_value={20}), \
             mock.patch.object(support.os,'getppid',return_value=42), \
             mock.patch.object(support.resource,'getrlimit',return_value=(0,0)):
            self.assertEqual(support.resources(),report)
            self.assertEqual(support.resources(),report)
            self.assertEqual(scope.calls,2)
            for path,bad in ((('limits','cpu.max'),'max 100000'),(('limits','memory.max'),'4294967296'),
                             (('limits','pids.max'),'max'),(('limits','memory.swap.max'),'1024'),
                             (('memory_events','oom'),1),(('swap_current_bytes',),True),
                             (('native_parent_pid',),43),(('limiting_ancestor',),'0::/unrelated')):
                scope.value=copy.deepcopy(report);target=scope.value
                for key in path[:-1]:target=target[key]
                target[path[-1]]=bad
                with self.subTest(path=path),self.assertRaises(RuntimeError):support.resources()

    def test_unbound_resource_checks_retain_the_original_complete_body(self):
        original_path=ROOT/'originals/gallery-new-runtime-preparation-20261107-r7/gallery_runtime_support_current.py'
        if not original_path.exists():
            original_path=ROOT.parent/'system-cp3a-source-adapter-20261119/originals/gallery-new-runtime-preparation-20261107-r7/gallery_runtime_support_current.py'
        original=next(n for n in ast.parse(original_path.read_text()).body
                      if isinstance(n,ast.FunctionDef) and n.name=='resources')
        actual=next(n for n in ast.parse((ROOT/'generated/shared/gallery_image_support.py').read_text()).body
                    if isinstance(n,ast.FunctionDef) and n.name=='_local_resources')
        original.name='_local_resources'
        self.assertEqual(ast.dump(actual),ast.dump(original))


if __name__=='__main__':unittest.main()
