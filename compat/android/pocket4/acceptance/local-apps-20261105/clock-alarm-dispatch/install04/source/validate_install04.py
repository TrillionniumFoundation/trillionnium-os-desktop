#!/usr/bin/env python3
"""Actual receipt/precondition checks and installer-control doubles; zero device calls."""
from pathlib import Path
from contextlib import nullcontext
from copy import deepcopy
import hashlib, importlib.util, json, os, tempfile, types

ROOT = Path(__file__).resolve().parent
CERT = 'a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
EPOCH = '48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f'


def fresh():
    spec = importlib.util.spec_from_file_location('clock_install04_test', ROOT/'clock_install04.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def main():
    module = fresh(); rows = []
    build_raw = (ROOT/'build04-result-original.json').read_bytes()
    art_raw = (ROOT/'art04/result04-original.json').read_bytes()
    assert module.sha(build_raw) == module.BUILD_SHA and module.sha(art_raw) == module.ART_SHA
    build, art = json.loads(build_raw), json.loads(art_raw)
    tx = types.SimpleNamespace(CERT_SHA=CERT, EPOCH_SHA=EPOCH)
    actual = module.artifact_preconditions(build, art, tx)
    assert actual['actual_art_target_classes_verified'] == 4
    rows.append({'case':'actual_signed_build_and_four_ART_targets_accepted','passed':True})
    for label, mutate, expected in (
        ('foreign_APK_rejected', lambda b,a:b['candidate_apk'].update(sha256='0'*64),
         'OFFLINE_CANDIDATE_NOT_VERIFIED'),
        ('missing_ART_target_rejected', lambda b,a:a['target_status_proof']['target_statuses'].pop(module.ART_TARGETS[0]),
         'ACTUAL_ART_TARGET_SET_NOT_VERIFIED'),
        ('ART_shared_closure_change_rejected', lambda b,a:a.update(installed_clock_and_shared_libraries_unchanged=False),
         'ACTUAL_ART_OR_RUNTIME_BINDING_NOT_VERIFIED'),
        ('ART_final_OOM_rejected', lambda b,a:a['resource_usage']['memory_events'].update(oom=1),
         'ART_RESOURCE_BOUNDARY_NOT_PRESERVED'),
    ):
        b,a = deepcopy(build),deepcopy(art);mutate(b,a)
        try: module.artifact_preconditions(b,a,tx)
        except RuntimeError as error: assert str(error) == expected, (label,str(error))
        else: raise AssertionError(label)
        rows.append({'case':label,'passed':True})

    # Exercise the actual update() try/with/except and final state selection.
    # Android, signature, ZIP, snapshot, and install transport are explicit
    # boundary doubles. This does not install an APK or prove device behavior.
    for scenario, expected in (
        ('completed', 'INSTALLED_VERIFIED'),
        ('unknown_ack', 'INSTALL_OUTCOME_UNKNOWN'),
        ('dispatch_exception', 'INSTALL_OUTCOME_UNKNOWN'),
        ('session_exit_exception', 'FINAL_GUARD_FAILED'),
    ):
        m=fresh(); calls=[]
        with tempfile.TemporaryDirectory(prefix='clock-install04-local-') as folder:
            # Local workspace cannot map target host gid 1000. This boundary
            # double does not claim to test target-host ownership admission.
            class OwnedTestPath(type(Path())):
                def lstat(self):
                    actual=super().lstat()
                    return types.SimpleNamespace(st_mode=actual.st_mode,st_uid=0,st_gid=1000)
            root=OwnedTestPath(folder);os.chmod(root,0o750)
            m.os=types.SimpleNamespace(chown=lambda *args:None,chmod=os.chmod)
            (root/'build').mkdir();(root/'build/result.json').write_bytes(build_raw)
            old_bytes,new_bytes=b'local-boundary-old-APK',b'local-boundary-new-APK'
            m.ROOT=root;m.RUN=root/'install-04';m.CANDIDATE=root/'build/candidate.apk'
            m.CANDIDATE.write_bytes(new_bytes);m.OLD_SHA=m.sha(old_bytes);m.NEW_SHA=m.sha(new_bytes)
            m.OLD_BYTES=len(old_bytes);m.NEW_BYTES=len(new_bytes);m.ART_RESULT=root/'art.json'
            m.ART_RESULT.write_bytes(art_raw)
            def write_new(path,value,mode=0o600,alex_readable=False):
                raw=value if isinstance(value,bytes) else (json.dumps(value,sort_keys=True)+'\n').encode()
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
                with os.fdopen(fd,'wb') as stream:stream.write(raw)
            def read_regular(path,expected=None):
                raw=Path(path).read_bytes();assert expected is None or m.sha(raw)==expected;return raw
            class Session:
                def __init__(self,journal):self.journal_dir=journal;self.epoch_sha256=EPOCH;self.target=self
                def __enter__(self):self.journal_dir.mkdir();return self
                def __exit__(self,*args):
                    if scenario=='session_exit_exception':raise RuntimeError('INJECTED_SESSION_EXIT_FAILURE')
                def read_file(self,*args):return old_bytes,{}
                def caller_status(self,*args):return None
                def guard(self):return {'epoch_sha256':EPOCH}
            def snapshot(session, tx, model, timers,label):
                data=new_bytes if label=='after' else old_bytes
                value={'package':m.PACKAGE,'epoch_sha256':EPOCH,'identity':{'uid':10063,
                    'version':37,'min_sdk':37,'target_sdk':30},'directories':{},'alarm_state':{},
                    'alarm_content_sha256':m.ALARM_SHA,'timer_and_stopwatch_empty':True,
                    'notification_appop_allow':True,'sound_state':{},'tasks_sha256':'1'*64,
                    'preferences_sha256':'2'*64,'preferences_metadata':{},
                    'observed_utc':'2026-11-05T00:00:00+00:00',
                    'apk':{'guest_path':'/data/app/local/base.apk','bytes':len(data),'sha256':m.sha(data)}}
                write_new(session.journal_dir/(label+'.json'),value);return value
            def install_once(session,path,expected_sha,label):
                calls.append(label)
                write_new(session.journal_dir/(label+'-dispatch.json'),{'sha256':expected_sha})
                if scenario=='dispatch_exception':raise RuntimeError('INJECTED_UNKNOWN_TRANSPORT')
                return {'ack':scenario!='unknown_ack'}
            tx=types.SimpleNamespace(CERT_SHA=CERT,EPOCH_SHA=EPOCH,ui_lock=nullcontext,
                CameraSession=Session,read_regular=read_regular,write_new=write_new,
                install_once=install_once,verified_response=lambda r:r['ack'])
            m.modules=lambda:(None,tx,None);m.artifact_preconditions=lambda *args:actual
            m.snapshot=snapshot;m.verify_payload=lambda *args:None;m.verify_signature=lambda *args:None
            result=m.update();assert result['state']==expected,(scenario,result)
            assert calls==['clock-install'] and not (m.RUN/'rollback-01').exists()
            if scenario=='session_exit_exception':
                assert result['state_before_final_guard_failure']=='INSTALLED_VERIFIED'
                assert result['error']=='RuntimeError:INJECTED_SESSION_EXIT_FAILURE'
            if scenario=='dispatch_exception':
                assert result.get('installed_identity_observation') is None
            else:
                observation=json.loads((m.RUN/'latest-installed-identity.json').read_bytes())
                assert observation['installed_apk_sha256']==m.NEW_SHA
                assert observation['snapshot_evidence_sha256']==m.sha((m.RUN/'commands/after.json').read_bytes())
                assert observation['business_review_from_prior_APK_inherited'] is False
            rows.append({'case':scenario+'_actual_update_control_one_dispatch_no_retry','passed':True})
    result={'schema':'clock-install04-local-boundaries-v1','passed':len(rows),'failed':0,'cases':rows,
        'source_sha256':module.sha((ROOT/'clock_install04.py').read_bytes()),
        'actual_build_sha256':module.sha(build_raw),'actual_ART_result_sha256':module.sha(art_raw),
        'scope':'Actual precondition method on captured receipts; actual update control with explicit Android, snapshot, signature, ZIP, host ownership and install transport doubles. No device/App/installation execution.',
        'Android_commands_executed':0,'install_commands_executed':0}
    raw=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
    (ROOT/'INSTALL04_LOCAL_VALIDATION.json').write_bytes(raw)
    print(json.dumps({'passed':len(rows),'failed':0,'result_sha256':hashlib.sha256(raw).hexdigest()}))


if __name__=='__main__':main()
