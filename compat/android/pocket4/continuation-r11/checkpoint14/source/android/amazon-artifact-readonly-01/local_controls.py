#!/usr/bin/env python3
"""Eight bounded local parser/first-error controls; no namespace or Android."""
import hashlib
import json
from pathlib import Path
import subprocess
import types

HERE=Path(__file__).resolve().parent


def main():
    raw=(HERE/'read_amazon.py').read_bytes()
    m=types.ModuleType('amazon_metadata_controls');m.__file__=str(HERE/'read_amazon.py')
    exec(compile(raw,m.__file__,'exec'),m.__dict__)
    rows=[]
    def record(name,run):
        run();rows.append({'name':name,'passed':True})
    def rejected(call,reason):
        try:call()
        except RuntimeError as e:assert str(e)==reason
        else:raise AssertionError('unexpected acceptance')
    def parse_good():
        result=m.metadata(('package:'+m.PACKAGE+' versionCode:1243240206 uid:14000\n').encode())
        assert result=={'package':m.PACKAGE,'user':0,'uid':14000,'version_code':1243240206}
    record('one_exact_synthetic_package_UID_version',parse_good)
    record('another_package_or_multiple_rows_rejected',lambda:rejected(
        lambda:m.metadata(b'package:unrelated.app versionCode:1 uid:14000\n'),
        'ONE_EXACT_AMAZON_USER0_METADATA_ROW_REQUIRED'))
    base='/data/app/~~owned-token/'+m.PACKAGE+'-owned-token/base.apk'
    def paths_good():assert m.apk_paths(('package:'+base+'\n').encode())==[base]
    record('one_synthetic_Amazon_base_path',paths_good)
    record('path_outside_Amazon_install_directory_rejected',lambda:rejected(
        lambda:m.apk_paths(b'package:/data/app/~~token/other.app-token/base.apk\n'),
        'ONLY_EXACT_AMAZON_INSTALL_DIRECTORY_APKS_MAY_BE_READ'))
    record('duplicate_APK_path_rejected',lambda:rejected(
        lambda:m.apk_paths((('package:'+base+'\n')*2).encode()),'DUPLICATE_APK_PATH'))

    def lifetime(kind):
        calls={'command':0,'release':0,'guard':0,'verify':0}
        authority=tuple(range(30,37))  # Protocol-only seam; no real FD or exec.
        class Entry:
            def __enter__(self):
                prefix=['/qualified/held-entry','--parent-pid='+str(m.os.getpid()),'--root-fd=30']
                prefix += ['--'+name+'-fd='+str(fd) for name,fd in
                    zip(('mnt','pid','uts','ipc','net','cgroup'),authority[1:])]
                if kind=='bad_prefix':prefix[1]='--target=1'
                return prefix+['--',*self.command],authority
            def __exit__(self,*unused):
                calls['release']+=1
                if kind in ('timeout_release','success_release'):raise OSError(9,'owned lease release seam')
        class Target:
            helper_path='/qualified/held-entry'
            def verify(self):calls['verify']+=1
            def entry(self,command):e=Entry();e.command=command;return e
        class Flow:
            @staticmethod
            def command(context,*args,**kwargs):
                calls['command']+=1;context.command_index+=1
                if kind=='timeout_release':raise subprocess.TimeoutExpired('owned command seam',15)
                r=subprocess.CompletedProcess([],0,b'owned-metadata',b'')
                r.recorder_spawned=True;r.recorder_joined=True;r.host_timed_out=False;r.recorder_errors=[]
                return r
        def guard():calls['guard']+=1
        c=m.Context(types.SimpleNamespace(Flow=Flow),object(),Target(),guard,{})
        try:c.command(list(m.LIST),{'PATH':'/system/bin'})
        except BaseException as e:
            if kind=='timeout_release':
                assert isinstance(e,subprocess.TimeoutExpired)
                assert any('entry_release' in n and 'OSError' in n for n in e.__notes__)
            elif kind=='success_release':assert isinstance(e,OSError) and e.errno==9
            else:assert str(e)=='EXACT_R4_HELD_PREFIX_AND_COMMAND_REQUIRED'
        else:raise AssertionError('expected closure rejection')
        assert calls['guard']==2 and calls['release']==1 and len(c.observations)==1
        assert calls['command']==(0 if kind=='bad_prefix' else 1)
        assert c.observations[0]['Android_UI_action'] is False
        if kind=='success_release':
            assert c.observations[0]['returncode']==0 and c.observations[0]['stdout_bytes']==14
        if kind=='timeout_release':assert len(c.observations[0]['secondary_errors'])==1
    for kind in ('bad_prefix','timeout_release','success_release'):
        record(kind+'_actual_Context_first_error_and_postguard',lambda k=kind:lifetime(k))
    report={'schema':1,'scope':'actual metadata parser/Context with explicit command/lease seam',
            'production_source_sha256':hashlib.sha256(raw).hexdigest(),'controls':rows,
            'passed':len(rows)==8,'Android_calls':0,'real_namespace_entry':False,
            'real_metadata_or_APK_read':False,'remote_execution':False,'whole_App_qualified':False}
    print(json.dumps(report,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
