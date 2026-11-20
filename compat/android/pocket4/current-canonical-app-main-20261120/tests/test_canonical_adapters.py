"""Finite source contracts and actual host-file caller controls.

Main, Android replies and mapping admission are explicit fixtures here. The
root-only controls use real private temporary FDs/shifted ownership; they
never operate on an Android process, image, application, or user directory.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'bundle/source'

def module(path,name):
    m=types.ModuleType(name);m.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__)
    return m

def method(path,name):
    m=module(path,'actual_method_source_'+path.stem)
    tree=ast.parse(path.read_bytes())
    nodes=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name]
    assert len(nodes)==1
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),m.__dict__)
    return m,m.__dict__[name]

class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.scope=module(ROOT/'source/deployment_scope.py','tested_finite_scope')
        self.transaction={'schema':self.scope.SCHEMA,**self.scope.retention_fields()}

    def test_original_receipt_sets_are_independent_and_complete(self):
        self.assertTrue(self.scope.validate_transaction(self.transaction))
        app=self.transaction['qualified_required39'];data=self.transaction['preserved_original45']
        self.assertEqual((len(app['required_packages']),app['required_count'],app['selected_count']),(39,39,42))
        self.assertEqual((len(data['packages']),sum(len(x['directories']) for x in data['packages'])),(45,90))
        self.assertNotEqual(set(app['required_packages']),{x['package'] for x in data['packages']})
        self.assertEqual({x['package'] for x in app['unavailable_APK_exemptions']},
            {'com.enflick.android.TextNow','com.pinger.textfree','com.ubercab'})
        # The producer returns independent data and cannot mutate its frozen source.
        self.transaction['preserved_original45']['packages'].clear()
        self.assertEqual(len(self.scope.retention_fields()['preserved_original45']['packages']),45)

    def test_v1_or_reduced_app_or_original_data_cannot_satisfy_v2(self):
        cases=[]
        old=copy.deepcopy(self.transaction);old['schema']='pocket4-final-deployment-result-v1';cases.append(old)
        for key in ('qualified_required39','preserved_original45'):
            old=copy.deepcopy(self.transaction);del old[key];cases.append(old)
        old=copy.deepcopy(self.transaction);old['qualified_required39']['required_packages'].pop();cases.append(old)
        old=copy.deepcopy(self.transaction);old['preserved_original45']['packages'].pop();cases.append(old)
        old=copy.deepcopy(self.transaction);old['preserved_original45']['packages'][0]['directories'].pop();cases.append(old)
        old=copy.deepcopy(self.transaction);old['retention_release_requires']['unresolved_supported_migrations']=False;cases.append(old)
        old=copy.deepcopy(self.transaction);old['preserved_original45']['preimage']['sha256']='0'*64;cases.append(old)
        for candidate in cases:
            with self.subTest(candidate=candidate.get('schema')),self.assertRaises(RuntimeError):
                self.scope.validate_transaction(candidate)

    def test_owned_command_lifecycle_functions_and_bounds_are_preserved(self):
        def functions(path):
            return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_bytes()).body
                    if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        original=ROOT/'inputs/original-support'
        for name in ('business_commands.py','business_image_capture.py'):
            self.assertEqual(functions(original/name),functions(ROOT/'source'/name))
        self.assertEqual(functions(ROOT/'inputs/main/bounded_host_capture.py'),
                         functions(ROOT/'source/bounded_host_capture.py'))
        source=(ROOT/'inputs/camera/6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877-capture_lifecycle.py').read_bytes()
        self.assertEqual((ROOT/'source/capture_lifecycle.py').read_bytes(),source)

@unittest.skipUnless(os.getuid()==os.geteuid()==0,'Requires actual root-owned temporary file controls on Pocket4')
class ActualFileCallerTests(unittest.TestCase):
    def test_reminder_identity_keeps_guest_uid_and_closes_actual_shifted_fds(self):
        identity=module(BUNDLE/'calendar-reminder/calendar_identity.py','actual_reminder_identity')
        for guest in (10061,10017,10125):
            with self.subTest(guest=guest),tempfile.TemporaryDirectory(prefix='calendar-id-control-') as root:
                dirs=[]
                for name in ('ce','de'):
                    p=Path(root)/name;p.mkdir();os.chown(p,100000+guest,100000+guest);dirs.append(p)
                package='explicit.fixture.package';apk=b'CALLSITE_CONTROL_NOT_AN_APK';view=object();calls=[]
                def mapped(actual,fd,uid):
                    self.assertIs(actual,view);self.assertEqual(uid,guest);calls.append(uid)
                    return os.fstat(fd),(100000+uid,100000+uid)
                def opened(path,flags):
                    self.assertIn(path,('/data/user/0/'+package,'/data/user_de/0/'+package))
                    return os.open(dirs[int('/user_de/' in path)],flags|os.O_CLOEXEC)
                dump=('Packages:\n  Package ['+package+'] (fixture):\n    appId='+str(guest)+
                    '\n    versionCode=37 minSdk=37 targetSdk=28\n    User 0: installed=true hidden=false suspended=false enabled=0 ceDataInode='+
                    str(dirs[0].stat().st_ino)+' deDataInode='+str(dirs[1].stat().st_ino)+'\n')
                def android(argv):
                    if argv==['/system/bin/dumpsys','package',package]:return dump.encode()
                    self.assertEqual(argv,['/system/bin/pm','path','--user','0',package]);return b'package:/system/fixture.apk\n'
                session=types.SimpleNamespace(c=types.SimpleNamespace(mapped_file_info=mapped),flow=types.SimpleNamespace(view=view),
                    android=android,guard=lambda:None,target=types.SimpleNamespace(open_root=opened,read_file=lambda *a,**k:(apk,{})))
                count=len(os.listdir('/proc/self/fd'))
                result=identity.identity(session,package,hashlib.sha256(apk).hexdigest(),guest,37)
                self.assertEqual(result['uid'],guest);self.assertEqual(calls,[guest,guest])
                self.assertEqual(result['directories']['ce']['st_uid'],100000+guest)
                self.assertEqual(len(os.listdir('/proc/self/fd')),count)
                os.chown(dirs[0],guest,100000+guest)
                with self.assertRaisesRegex(RuntimeError,'PACKAGE_DATA_IDENTITY_CHANGED'):
                    identity.identity(session,package,hashlib.sha256(apk).hexdigest(),guest,37)
                self.assertEqual(len(os.listdir('/proc/self/fd')),count)

    def test_both_reminder_database_callers_keep_original_sql_and_gid_fingerprint(self):
        for name,method_name in (('calendar_base.py','counts'),('calendar_model.py','read')):
            with self.subTest(source=name),tempfile.TemporaryFile() as file:
                source=BUNDLE/'calendar-reminder'/name
                mod=module(source,'actual_'+name.replace('.','_'))
                if method_name=='counts':
                    _,call=method(source,'counts');tables=mod.TABLES
                else:
                    bound=mod.bind('1234567890abcdef'*2);call=bound.Model.read;tables=bound.TABLES
                os.fchown(file.fileno(),110017,110020);view=object();calls=[]
                def mapped(actual,fd,uid):
                    self.assertIs(actual,view);self.assertEqual(uid,10017)
                    return os.fstat(fd),(110017,110017)
                def opened(path,flags):
                    self.assertEqual(path,'/data/user/0/com.android.providers.calendar/databases/calendar.db')
                    self.assertEqual(flags,os.O_RDONLY|os.O_NOFOLLOW);return os.dup(file.fileno())
                def query(label,argv,timeout):
                    self.assertEqual(timeout,14);self.assertIn('-readonly',argv)
                    self.assertTrue(argv[-1].startswith('PRAGMA query_only=ON;BEGIN;'))
                    self.assertTrue(argv[-1].endswith(';ROLLBACK;'));calls.append(argv)
                    if method_name=='counts':out=[{'name':n,'count':0} for n in tables]
                    else:
                        value={'counts':dict.fromkeys(tables,0),'calendars':[],'events':[],
                            'owned_instances':[],'owned_reminders':[],'owned_alerts':[],
                            'foreign_children':dict.fromkeys(bound.CHILDREN,0)}
                        out=[{'payload':json.dumps(value)}]
                    return {'rc':0,'joined':True,'timed_out':False,'stdout':json.dumps(out)}
                session=types.SimpleNamespace(c=types.SimpleNamespace(mapped_file_info=mapped),flow=types.SimpleNamespace(view=view),
                    guard=lambda:None,target=types.SimpleNamespace(open_root=opened),environment={},root_query=query)
                obj=types.SimpleNamespace(s=session,db_birth=None,birth=None,sequence=0,record=lambda *a:None)
                count=len(os.listdir('/proc/self/fd'));call(obj,'fixture')
                identity=obj.db_birth if method_name=='counts' else obj.birth
                self.assertEqual(identity['st_gid'],110020);self.assertEqual(len(calls),1)
                self.assertEqual(len(os.listdir('/proc/self/fd')),count)
                os.fchown(file.fileno(),10017,110020)
                with self.assertRaisesRegex(RuntimeError,'CALENDAR_DB_IDENTITY'):call(obj,'fixture')
                self.assertEqual(len(calls),1);self.assertEqual(len(os.listdir('/proc/self/fd')),count)

if __name__=='__main__':unittest.main()
