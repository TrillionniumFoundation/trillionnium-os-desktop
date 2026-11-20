"""Focused offline controls; these fixtures grant no actual Main admission."""
import ast
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


class CalendarResourceBridge(unittest.TestCase):
    def test_complete_business_cleanup_and_original_resource_predicates_preserved(self):
        changed={'calendar_resources.py','system_entry.py'}
        originals=list((ROOT/'originals').glob('*.py'));self.assertEqual(len(originals),33)
        for path in originals:
            if path.name not in changed:self.assertEqual(path.read_bytes(),(ROOT/'source'/path.name).read_bytes())
        before={n.name:n for n in ast.parse((ROOT/'originals/calendar_resources.py').read_text()).body
                if isinstance(n,ast.FunctionDef)}
        after={n.name:n for n in ast.parse((ROOT/'source/calendar_resources.py').read_text()).body
               if isinstance(n,ast.FunctionDef)}
        for name in ('resource_limits','memory_events'):
            self.assertEqual(ast.dump(before[name]),ast.dump(after[name]))
        before['own_resources'].name='_local_own_resources'
        self.assertEqual(ast.dump(before['own_resources']),ast.dump(after['_local_own_resources']))

    def test_live_report_preserves_actual_ancestor_metrics_and_rejects_bad_limits(self):
        resource=load(ROOT/'source/calendar_resources.py','calendar_resource_report_controls')
        fields={'cpu.max':'50000 100000','cpu.stat':'usage_usec 10\nuser_usec 6\nsystem_usec 4',
                'memory.max':'536870912','memory.current':'16384','memory.peak':'32768',
                'memory.events':'low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0',
                'memory.swap.max':'0','memory.swap.current':'0','pids.current':'3'}
        report={'schema':'pocket4-held-effective-calendar-resources-v1',
                'cgroup':'0::/job/droidloom-app-calendar-reminder-leaf-42-7','limiting_ancestor':'0::/job',
                'native_parent_pid':42,'native_parent_start_ticks':123,
                'ancestor_files':fields,
                'limits':{'cpu.max':'50000 100000','memory.max':'536870912','memory.swap.max':'0','pids.max':'64'}}
        with self.assertRaisesRegex(RuntimeError,'ONE_LIVE_CALENDAR_RESOURCE_SCOPE_REQUIRED'):
            resource.bind_resource_scope(report)
        class OwnedLeafResources:
            def __init__(self):self.value=copy.deepcopy(report);self.calls=0
            def report(self):self.calls+=1;return copy.deepcopy(self.value)
        scope=OwnedLeafResources();resource.bind_resource_scope(scope)
        with mock.patch.object(resource.Path,'read_text',return_value=report['cgroup']+'\n'), \
             mock.patch.object(resource.os,'getppid',return_value=42):
            actual=resource.own_resources();self.assertEqual(actual['files'],fields)
            self.assertEqual(actual['directory'],'/sys/fs/cgroup/job')
            self.assertEqual(actual['cgroup'],report['cgroup']+'\n')
            resource.own_resources();self.assertEqual(scope.calls,2)
            for key,bad in (('cpu.max','50001 100000'),('cpu.max','max 100000'),('memory.max','2147483648'),
                            ('memory.swap.max','1'),('memory.swap.current','1'),('memory.current','NaN'),
                            ('cpu.stat','x'*8193),('memory.events','oom 0\noom 0\noom_kill 0\noom_group_kill 0')):
                scope.value=copy.deepcopy(report);scope.value['ancestor_files'][key]=bad
                if key in scope.value['limits']:scope.value['limits'][key]=bad
                with self.subTest(key=key,bad=bad[:30]),self.assertRaises(RuntimeError):resource.own_resources()

    def test_original_cpu_boundary_is_never_replaced_by_gallery_budget(self):
        resource=load(ROOT/'source/calendar_resources.py','calendar_original_budget_controls')
        for cpu in ('1 100000','50000 100000','100000 200000'):
            resource.resource_limits({'files':{'cpu.max':cpu,'memory.max':'536870912'}})
        for cpu,memory in (('50001 100000','536870912'),('200000 100000','536870912'),
                           ('50000 100000','2147483648'),('max 100000','536870912')):
            with self.assertRaises(RuntimeError):resource.resource_limits({'files':{'cpu.max':cpu,'memory.max':memory}})

    def test_entry_keeps_lease_through_original_execute_and_terminal_output(self):
        entry=load(ROOT/'source/system_entry.py','calendar_entry_lifetime_controls')
        prep={'path':'/source/preparation.json','bytes':1,'sha256':'a'*64}
        request={'base_plan':{'path':'/base.json','bytes':1,'sha256':'b'*64}}
        request_ref={'path':'/request.json','bytes':1,'sha256':'c'*64}
        for fail in (False,True):
            events=[]
            class OwnedLeafResources:pass
            scope=OwnedLeafResources()
            class Lease:
                def __enter__(self):events.append('lease_enter');return self
                def admit_owned_leaf_resources(self):events.append('admit_actual_scope');return scope
                def guard(self):events.append('lease_guard')
                def __exit__(self,*unused):events.append('lease_close')
            def execute(*unused):
                events.extend(['original_execute','original_cleanup','original_result_publication'])
                if fail:raise RuntimeError('ORIGINAL_FAILURE')
                return {'path':'/actual-result.json','bytes':1,'sha256':'d'*64},{'state':'ORIGINAL_SUCCESS','case_business_success_verified':True}
            modules={'native_calendar_release':types.SimpleNamespace(bind_current=lambda p:Lease(),OwnedLeafResources=OwnedLeafResources),
                     'calendar_resources':types.SimpleNamespace(bind_resource_scope=lambda s:events.append('bind_live_scope')),
                     'system_case':types.SimpleNamespace(execute=execute)}
            def need(ok,why):
                if not ok:raise RuntimeError(why)
            def read_ref(pin):
                if pin==request['base_plan']:return json.dumps({'source_preparation':prep}).encode()
                events.append('request_bookend');return b'{}'
            common=types.SimpleNamespace(need=need,regular=lambda *unused:(json.dumps(request).encode(),request_ref),
                parse=json.loads,read_ref=read_ref,module=lambda pin,name:modules[Path(pin['path']).stem])
            task={'files':[{'path':'/'+name+'.py'}for name in modules]}
            planner=types.SimpleNamespace(source_packet=lambda *unused:task)
            with mock.patch.object(entry,'bootstrap',return_value=(common,{},prep,planner)), \
                 mock.patch.object(entry.os,'getuid',return_value=0),mock.patch.object(entry.os,'geteuid',return_value=0), \
                 mock.patch.object(sys,'argv',['entry','--preparation','/source/preparation.json',
                     '--expect-preparation-sha256','a'*64,'execute','--request','/request.json',
                     '--expect-request-sha256','c'*64]),contextlib.redirect_stdout(io.StringIO())as output:
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'ORIGINAL_FAILURE'):entry.main()
                    self.assertEqual(output.getvalue(),'')
                else:
                    self.assertEqual(entry.main(),0);self.assertTrue(json.loads(output.getvalue())['case_business_success_verified'])
            self.assertEqual(events[0],'lease_enter');self.assertEqual(events[-1],'lease_close')
            self.assertLess(events.index('admit_actual_scope'),events.index('original_execute'))
            self.assertLess(events.index('original_result_publication'),events.index('lease_close'))
            if not fail:self.assertEqual(events[-3:],['request_bookend','lease_guard','lease_close'])


if __name__=='__main__':unittest.main()
