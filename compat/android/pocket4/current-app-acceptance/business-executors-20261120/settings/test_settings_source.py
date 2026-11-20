"""Focused pure source controls. All UI packets are explicit model fixtures."""
import copy
import hashlib
import importlib.util
import io
from pathlib import Path
import types
import unittest
from PIL import Image

ROOT=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location('settings_control_'+name,ROOT/'source'/name)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
P=load('settings_profiles.py');PAGES=load('settings_pages.py');POLICY=load('settings_policy.py');IDENTITY=load('settings_identity.py')
def need(ok,code):
    if not ok:raise RuntimeError(code)


class SourceControls(unittest.TestCase):
    def packet(self,page=None,flat=False):
        im=Image.new('RGB',(32,32))
        im.putdata([(0,0,0) if flat or x%2 else (200,220,255) for x in range(1024)])
        digest=hashlib.sha256((32).to_bytes(4,'big')*2+im.tobytes()).hexdigest()
        stream=io.BytesIO();im.save(stream,format='PNG');im.close()
        title=P.HOME_TITLES[0] if page is None else page['titles'][0]
        node={'package':P.PACKAGE,'visible':True,'enabled':True,'password':False,'editable':False}
        value={'ok':True,'native':{'ok':True,'accessibility_mode_restoration_verified':True,
            'nodes':[{**node,'text':title},{**node,'text':'fixture control 1','clickable':True},
                     {**node,'text':'fixture control 2','scrollable':True}]},
            'screenshot':{'scope_width':32,'scope_height':32,'scope_sha256':digest,
                'scope':{'package':P.PACKAGE,'activity':P.HOME_ACTIVITY if page is None else page['activity'],
                    'android_init_host_pid':123456,'display_id':0,'accessibility_mode':'none','window_token':'a12b'}}}
        return value,stream.getvalue()

    def test_five_exact_pages_and_reopened_home_have_scoped_content_checks(self):
        for page in (None,*P.PAGES):
            value,png=self.packet(page)
            result=PAGES.observation(value,png,profile=P,page=page,init_pid=123456)
            self.assertTrue(result['expected_title_observed']);self.assertFalse(result['whole_app_business_accepted'])
            if page:
                route=P.route_argv(17,page)
                self.assertIn(page['component'],route)
                raw=('Status: ok\nActivity: '+page['component']+'\nComplete\n').encode()
                self.assertEqual(PAGES.route_result(raw,page)['component'],page['component'])

    def test_wrong_window_unknown_empty_and_flat_pages_refuse(self):
        changes=[lambda v:v.update(outcome_unknown=True),
            lambda v:v['native'].update(accessibility_mode_restoration_verified=False),
            lambda v:v['screenshot']['scope'].update(package='com.android.deskclock'),
            lambda v:v['screenshot']['scope'].update(activity=P.HOME_ACTIVITY+'Other'),
            lambda v:v['screenshot']['scope'].update(android_init_host_pid=123457),
            lambda v:v['screenshot'].update(scope_sha256='0'*64),
            lambda v:v['native'].update(nodes=[]),
            lambda v:v['native']['nodes'][0].update(text='Unrelated page')]
        for change in changes:
            value,png=self.packet();change(value)
            with self.assertRaises(RuntimeError):PAGES.observation(value,png,profile=P,page=None,init_pid=123456)
        value,png=self.packet(flat=True)
        with self.assertRaisesRegex(RuntimeError,'FLAT_IMAGE'):PAGES.observation(value,png,profile=P,page=None,init_pid=123456)

    def test_exact_once_policy_rejects_setting_writes_and_unowned_cleanup(self):
        c=types.SimpleNamespace(need=need,read_ref=lambda r:b'{}',STACKS=['/system/bin/cmd','activity','stack','list'])
        page=P.PAGES[0];s=types.SimpleNamespace(profile=P,pending_route={'sent':False,'page':page,'scope':'scope','intent':'ref'},
            page_route_count=1,cleanup_admission=None)
        r=types.SimpleNamespace(c=c,session=s,phase='inspect',scope_ref='scope',selected_task=lambda:{'task':17})
        policy=POLICY.Policy(r);argv=P.route_argv(17,page)
        policy.admit(argv,35,True,False)
        with self.assertRaises(RuntimeError):policy.admit(argv,35,True,False)
        for args in [(['/system/bin/settings','put','system','screen_brightness','0'],20,True,False),
                     (['/system/bin/pm','grant',P.PACKAGE,'android.permission.CAMERA'],20,True,False),
                     (['/system/bin/cmd','activity','stack','remove','17'],20,True,False)]:
            with self.assertRaises(RuntimeError):policy.admit(*args)
        for task in (True,0,-1,'17'):
            with self.assertRaises(RuntimeError):P.route_argv(task,page)

    def test_full_permission_and_data_metadata_are_preserved(self):
        c=types.SimpleNamespace(need=need)
        raw=('Packages:\n  Package [com.android.settings] (fixture):\n    appId=1000\n'
            '    versionCode=37 minSdk=37 targetSdk=37\n    User 0: installed=true hidden=false suspended=false enabled=0 stopped=true notLaunched=true ceDataInode=4 deDataInode=5\n'
            '      android.permission.INTERNET: granted=true\n').encode()
        a=IDENTITY.parse(c,raw,P);b=IDENTITY.parse(c,raw.replace(b'stopped=true',b'stopped=false').replace(b'notLaunched=true',b'notLaunched=false'),P)
        self.assertTrue(IDENTITY.same(c,a,b))
        b['all_permission_rows']=['android.permission.INTERNET: granted=false']
        with self.assertRaisesRegex(RuntimeError,'GRANTS'):IDENTITY.same(c,a,b)
        with self.assertRaisesRegex(RuntimeError,'SYSTEM_UID'):
            IDENTITY.parse(c,raw.replace(b'appId=1000',b'appId=10125'),P)


if __name__=='__main__':unittest.main()
