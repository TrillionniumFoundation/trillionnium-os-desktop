"""Focused callsite controls, using real temporary file FDs and fixture Main.

These controls do not launch Android, read user data, or establish Main
qualification. The unchanged actual-map helper has separate PR324 controls.
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest

ROOT=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location('calendar_mapped_'+name,ROOT/'source'/name)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
IDENTITY=load('calendar_identity.py');BASE=load('calendar_base.py')


class Calls(unittest.TestCase):
    def test_identity_maps_all_three_guest_owners_and_closes_fds(self):
        for guest in (10061,10017,10125):
            with self.subTest(guest=guest), tempfile.TemporaryDirectory() as root:
                dirs=[]
                for name in ('ce','de'):
                    p=Path(root)/name;p.mkdir();os.chown(p,100000+guest,100000+guest);dirs.append(p)
                package={10061:'com.android.calendar',10017:'com.android.providers.calendar',10125:'local.pocket4.actions.v2'}[guest]
                apk=b'CALLSITE_FIXTURE_NOT_AN_APK';path='/system/fixture.apk';view=object();called=[]
                def mapped(actual,fd,uid):
                    self.assertIs(actual,view);self.assertEqual(uid,guest);called.append(uid)
                    return os.fstat(fd),(100000+uid,100000+uid)
                def opened(path,flags):
                    self.assertIn(path,('/data/user/0/'+package,'/data/user_de/0/'+package))
                    return os.open(dirs[int('/user_de/' in path)],flags|os.O_CLOEXEC)
                dump=('Packages:\n  Package ['+package+'] (fixture):\n    appId='+str(guest)+
                    '\n    versionCode=37 minSdk=37 targetSdk=28\n    User 0: installed=true hidden=false suspended=false enabled=0 ceDataInode='+
                    str(dirs[0].stat().st_ino)+' deDataInode='+str(dirs[1].stat().st_ino)+'\n')
                def android(argv):
                    if argv==['/system/bin/dumpsys','package',package]:return dump.encode()
                    self.assertEqual(argv,['/system/bin/pm','path','--user','0',package]);return ('package:'+path+'\n').encode()
                s=types.SimpleNamespace(c=types.SimpleNamespace(mapped_file_info=mapped),flow=types.SimpleNamespace(view=view),
                    android=android,guard=lambda:None,target=types.SimpleNamespace(open_root=opened,read_file=lambda *a,**k:(apk,{})))
                count=len(os.listdir('/proc/self/fd'))
                result=IDENTITY.identity(s,package,hashlib.sha256(apk).hexdigest(),guest,37)
                self.assertEqual(result['uid'],guest);self.assertEqual(called,[guest,guest])
                self.assertEqual(result['directories']['ce']['st_uid'],100000+guest)
                self.assertEqual(len(os.listdir('/proc/self/fd')),count)
                os.chown(dirs[0],guest,100000+guest)
                with self.assertRaisesRegex(RuntimeError,'PACKAGE_DATA_IDENTITY_CHANGED'):
                    IDENTITY.identity(s,package,hashlib.sha256(apk).hexdigest(),guest,37)
                self.assertEqual(len(os.listdir('/proc/self/fd')),count)

    def test_database_mapping_preserves_original_gid_fingerprint_and_query(self):
        tree=ast.parse((ROOT/'source/calendar_base.py').read_bytes())
        fn=next(x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef) and x.name=='counts')
        env=dict(BASE.__dict__);exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual-counts-method','exec'),env)
        with tempfile.TemporaryFile() as file:
            # Original counts checked UID; a different, stable GID is valid.
            os.fchown(file.fileno(),110017,110020);path='/proc/self/fd/'+str(file.fileno());view=object();calls=[]
            def mapped(actual,fd,uid):
                self.assertIs(actual,view);self.assertEqual(uid,10017)
                return os.fstat(fd),(110017,110017)
            def opened(guest,flags):
                self.assertEqual(guest,BASE.DB);self.assertEqual(flags,os.O_RDONLY|os.O_NOFOLLOW)
                return os.dup(file.fileno())
            def query(label,argv,timeout):
                self.assertEqual(label,'calendar-counts-fixture');self.assertEqual(timeout,14)
                self.assertIn('-readonly',argv);self.assertEqual(argv[-2],BASE.DB)
                self.assertTrue(argv[-1].startswith('PRAGMA query_only=ON;BEGIN;'))
                self.assertTrue(argv[-1].endswith(';ROLLBACK;'));calls.append(argv)
                return {'rc':0,'joined':True,'timed_out':False,
                        'stdout':json.dumps([{'name':n,'count':0} for n in BASE.TABLES])}
            session=types.SimpleNamespace(c=types.SimpleNamespace(mapped_file_info=mapped),flow=types.SimpleNamespace(view=view),
                guard=lambda:None,target=types.SimpleNamespace(open_root=opened),environment={},root_query=query)
            obj=types.SimpleNamespace(s=session,db_birth=None,record=lambda *a:None)
            count=len(os.listdir('/proc/self/fd'))
            result=env['counts'](obj,'fixture');self.assertEqual(set(result),set(BASE.TABLES));self.assertEqual(len(calls),1)
            self.assertEqual(obj.db_birth['st_gid'],110020);self.assertEqual(len(os.listdir('/proc/self/fd')),count)
            os.fchown(file.fileno(),10017,110020)
            with self.assertRaisesRegex(RuntimeError,'CALENDAR_DB_IDENTITY'):env['counts'](obj,'fixture')
            self.assertEqual(len(calls),1);self.assertEqual(len(os.listdir('/proc/self/fd')),count)

    def test_exact_preserved_sources_and_shared_helper(self):
        prep=json.loads((ROOT/'inputs/preparation.json').read_bytes())
        changed={'app_common.py','calendar_identity.py','calendar_base.py'}
        for ref in prep['files']:
            name=Path(ref['path']).name;raw=(ROOT/'source'/name).read_bytes()
            if name not in changed:self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(ref['bytes'],ref['sha256']))
            else:
                old=(ROOT/'inputs/originals'/name).read_bytes()
                self.assertEqual(hashlib.sha256(old).hexdigest(),ref['sha256'])
                if name=='app_common.py':self.assertEqual(raw,old+(ROOT/'mapped_owner_addition.py').read_bytes())
            compile(raw,name,'exec')
        self.assertEqual(len(prep['files'])-len(changed),32)


if __name__=='__main__':unittest.main()
