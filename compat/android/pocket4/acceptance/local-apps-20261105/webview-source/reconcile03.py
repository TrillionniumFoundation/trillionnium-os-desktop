#!/usr/bin/python3 -I
"""Reconcile the one unresolved WebView02 key at its original origin.

Default is inert. Execution reuses the frozen WebView02 identity, focus, task,
URL and lifecycle checks. It never replays Save or qualifies the business flow.
"""
from pathlib import Path
import argparse,base64,hashlib,json,os,signal,stat,time,types

BASE_SOURCE=Path('/home/alex/work/pocket4-webview-flow-20261105-r12-tools-02/ui_flow.py')
BASE_SHA='00a184996488f2433e05a6fcd3cc5b579801f6a9eeb6b5970b899db160e5bfd2'
FIXTURE_SOURCE=Path('/home/alex/work/pocket4-webview-flow-20261105-r12-reconcile-tools-03/fixture_reconcile03.py')
FIXTURE_SHA='3edfe85e2d5afe962ce44f726900ebef058b88232051156c9f815fed71127ba0'
ORIGINAL_RESULT=Path('/home/alex/work/pocket4-webview-flow-20261105-r12-02/result.json')
ORIGINAL_CANONICAL_SHA='4975b2545f9b6f1abda2efc873c86b0b0cd236d5df956ec0d274475b003be865'
ROOT=Path('/home/alex/work/pocket4-webview-flow-20261105-r12-reconcile-03')
RUN='9ef6872a170db189c5ce94cd02d2f1ac'
PORT=41565
ORIGIN='http://127.0.0.1:41565'
KEY='pocket4.webview.r12.'+RUN
MAX_ACTIONS,MAX_SECONDS,CLEANUP_RESERVE=8,360,60


def require(value,reason):
    if not value:raise RuntimeError(reason)


def source_bytes(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid==0 and
                before.st_size<=262144 and not before.st_mode&0o022,'SOURCE_IDENTITY_UNVERIFIED')
        raw=os.read(fd,262145);after=os.fstat(fd)
        fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        require(len(raw)==before.st_size and fields(before)==fields(after),'SOURCE_CHANGED_DURING_READ')
        return raw
    finally:os.close(fd)


def load(path,digest,name):
    raw=source_bytes(path)
    require(hashlib.sha256(raw).hexdigest()==digest,'FROZEN_SOURCE_CHANGED')
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def original_receipt():
    value=json.loads(source_bytes(ORIGINAL_RESULT))
    canonical=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    require(hashlib.sha256(canonical).hexdigest()==ORIGINAL_CANONICAL_SHA,'ORIGINAL_RESULT_CHANGED')
    require(value['run']==RUN and value['origin']==ORIGIN and value['fixture_port']==PORT and
            value['owned_storage_key']==KEY and value['owned_storage_state']=='WRITE_OUTCOME_NOT_YET_VERIFIED' and
            value['owned_storage_key_removal_verified'] is False and value['pending_effects']==[] and
            value['outcome_unknown'] is False and value['launch_calls']==value['owned_remove_calls']==1 and
            value['fixture_cleanup']['own_child_reaped'] is True and value['fixture_cleanup']['exit_code']==0 and
            value['fixture_cleanup']['terminal']['socket_closed'] is True,'ORIGINAL_SCOPE_OR_CLEANUP_UNVERIFIED')
    return value


def trial_type(base):
    class ReconcileTrial(base.Trial):
        def __init__(self,session,tx,fixture):
            super().__init__(session,tx,fixture)
            self.cleanup_inputs=0
            self.result.update(state='RECONCILIATION_NOT_STARTED',reconciliation_completed=False,
                owned_storage_key_absence_verified=False,cleanup_input_calls=0,
                navigation_scope='original-origin exact-key reconciliation only',
                original_result_canonical_sha256=ORIGINAL_CANONICAL_SHA,
                foreign_keys_accessed=False,save_replayed=False)

        def observe(self,label):
            # Same frozen observation contract, with its frame retained for a
            # possible cleanup tap. No saved frame from the old run is reused.
            self.budget();focus=self.ready_focus();self.s.guard()
            value=self.s.helper.dispatch({'op':'observe','package':base.PACKAGE,
                'window_token':focus['window_token'],'display':0,'accessibility_mode':'none','with_png':True})
            self.s.guard();png=value.pop('screenshot_png_base64',None)
            if png is not None:
                self.tx.write_new(ROOT/('%03d-'%(self.sequence+1)+label+'.png'),base64.b64decode(png,validate=True))
            self.record(label,value);native=value.get('native',{})
            require(value.get('ok') is True and value.get('outcome_unknown') is not True and
                    native.get('ok') is True and native.get('accessibility_mode_restoration_verified') is True,
                    'OBSERVATION_UNVERIFIED')
            require(value['screenshot']['scope']['package']==base.PACKAGE and
                    value['screenshot']['scope']['window_token']==focus['window_token'],'OBSERVATION_SCOPE_CHANGED')
            self.owned_check('observed-owned')
            return {'focus':focus,'screenshot':value['screenshot'],
                'nodes':[n for n in native.get('nodes',[]) if n.get('package')==base.PACKAGE and n.get('visible') is True]}

        def cleanup_tap(self,obs):
            require(self.cleanup_inputs==0,'CLEANUP_INPUT_ALREADY_ATTEMPTED')
            node=self.one(obs,lambda n:n.get('resource-id')=='cleanup' and
                n.get('class')=='android.widget.Button' and n.get('text')=='Remove this exact run key' and
                n.get('enabled') is True and n.get('clickable') is True,'ONE_OBSERVED_CLEANUP_BUTTON_REQUIRED')
            bounds=node.get('bounds_array');shot=obs['screenshot'];scope=shot['scope_bounds']
            require(isinstance(bounds,list) and len(bounds)==4 and all(type(x) is int for x in bounds) and
                scope[0]<=bounds[0]<bounds[2]<=scope[2] and scope[1]<=bounds[1]<bounds[3]<=scope[3],
                'CLEANUP_BUTTON_NOT_FULLY_IN_OBSERVED_SCOPE')
            self.budget();self.owned_check('before-cleanup')
            require(self.focus()==obs['focus'],'CLEANUP_FOCUS_CHANGED')
            request={'op':'snapshot-tap','package':base.PACKAGE,'display':0,'accessibility_mode':'none',
                'input_source':'touch','window_token':obs['focus']['window_token'],
                'frame_sha256':shot['frame_sha256'],'scope_sha256':shot['scope_sha256'],
                'context_token':shot['context_token'],
                'coords':[(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2]}
            self.record('cleanup-intent',{'request':request,'observed_node':node,'origin':ORIGIN,
                'exact_owned_key':KEY,'automatic_retry':False,'save_replayed':False})
            self.cleanup_inputs+=1;self.actions+=1;self.pending.add('cleanup-owned-key');self.s.guard()
            reply=self.s.helper.dispatch(request);self.s.guard();self.record('cleanup-response',reply)
            require(reply.get('ok') is True and reply.get('performed')=='snapshot-tap' and
                    reply.get('input_command_completed') is True and reply.get('outcome_unknown') is not True,
                    'CLEANUP_INPUT_UNVERIFIED_NO_REPLAY')
            self.pending.remove('cleanup-owned-key')

        def run(self):
            old=signal.signal(signal.SIGALRM,base.expired)
            signal.setitimer(signal.ITIMER_REAL,MAX_SECONDS-CLEANUP_RESERVE)
            try:
                self.identity();self.launch()
                obs=self.url('reconcile.html','OWNED_RECONCILE_READY')
                record=self.one(obs,lambda n:n.get('resource-id')=='record','ONE_OWNED_RECORD_STATUS_REQUIRED')
                value=record.get('text');self.result['original_key_observed_status']=value
                if value=='OWNED_KEY_ABSENT':
                    self.result['owned_storage_state']='ABSENT_VERIFIED_BY_SAME_ORIGIN_RECONCILIATION'
                    self.result['owned_storage_key_absence_verified']=True
                else:
                    require(value in ['OWNED_KEY_PRESENT counter=%d value='%i+base.VALUE for i in (1,2)],
                            'OWNED_CONTENT_NOT_EXACT_NO_REMOVAL')
                    self.result['owned_storage_state']='REMOVAL_OUTCOME_NOT_YET_VERIFIED'
                    self.cleanup_tap(obs)
                    obs=self.expect('key-removed','OWNED_KEY_REMOVED_AND_ABSENCE_VERIFIED')
                    self.one(obs,lambda n:n.get('resource-id')=='record' and n.get('text')=='OWNED_KEY_ABSENT',
                             'OWNED_KEY_ABSENCE_READBACK_MISSING')
                    self.result.update(owned_storage_state='ABSENT_VERIFIED_AFTER_EXACT_OWNED_REMOVAL',
                        owned_storage_key_absence_verified=True,owned_storage_key_removal_verified=True)
                self.close_task();self.identity()
                require(self.launches==self.removals==1 and not self.pending,'RECONCILE_LIFECYCLE_INCOMPLETE')
                self.result.update(state='OWNED_KEY_RECONCILED',reconciliation_completed=True)
            except BaseException as exc:
                self.result.update(state='RECONCILIATION_STOPPED',reconciliation_completed=False,
                    error=type(exc).__name__+': '+str(exc))
            finally:
                signal.setitimer(signal.ITIMER_REAL,max(.001,min(CLEANUP_RESERVE,MAX_SECONDS-(time.monotonic()-self.start))))
                try:self.close_task()
                except BaseException as exc:
                    self.result.update(state='OWNED_CLEANUP_UNVERIFIED',reconciliation_completed=False,
                        cleanup_error=type(exc).__name__+': '+str(exc))
                finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
                self.result.update(action_calls=self.actions,launch_calls=self.launches,
                    owned_remove_calls=self.removals,cleanup_input_calls=self.cleanup_inputs,
                    pending_effects=sorted(self.pending),outcome_unknown=bool(self.pending),
                    elapsed_seconds=time.monotonic()-self.start,framework_epoch_sha256=self.s.epoch_sha256)
            return self.result
    return ReconcileTrial


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'state':'PLAN_ONLY','server_starts':0,'ui_actions':0,'original_origin':ORIGIN,
            'run':RUN,'exact_owned_key':KEY,'save_replayed':False,'fixed_port_no_takeover':True,
            'max_actions':MAX_ACTIONS,'max_seconds':MAX_SECONDS,'whole_app_production_ready':False},indent=2));return 0
    base=load(BASE_SOURCE,BASE_SHA,'webview02_frozen_base')
    base.ROOT=ROOT;base.MAX_ACTIONS=MAX_ACTIONS;base.MAX_SECONDS=MAX_SECONDS;base.CLEANUP_RESERVE=CLEANUP_RESERVE
    tx=load(base.SESSION_SOURCE,base.SESSION_SHA,'webview_reconcile_session')
    fixture_module=load(FIXTURE_SOURCE,FIXTURE_SHA,'webview_reconcile_fixture')
    original=original_receipt()
    result={'state':'NOT_STARTED','reconciliation_completed':False,'business_flow_completed':False,
        'whole_app_production_ready':False,'origin':ORIGIN,'run':RUN,'owned_storage_key':KEY,
        'owned_storage_key_absence_verified':False,'owned_storage_key_removal_verified':False}
    with tx.ui_lock():
        ROOT.mkdir(mode=0o700)
        try:
            with tx.CameraSession(ROOT/'commands') as session:
                require(session.guard()==original['final_guard'],'ORIGINAL_ANDROID_GENERATION_CHANGED')
                with fixture_module.FixtureOwner(session,FIXTURE_SOURCE,FIXTURE_SHA,RUN,ROOT/'fixture',600) as fixture:
                    result=trial_type(base)(session,tx,fixture).run()
                require(fixture.result['own_child_reaped'] and fixture.result['exit_code']==0,'OWN_SERVER_CLEANUP_UNVERIFIED')
                terminal=[json.loads(line) for line in fixture.result['child_stdout'].splitlines()]
                require(len(terminal)==1 and terminal[0].get('state')=='FIXTURE_CLOSED' and
                        terminal[0].get('socket_closed') is True,'OWN_SERVER_CLOSE_RECEIPT_UNVERIFIED')
                fixture.result['terminal']=terminal[0];result['fixture_cleanup']=fixture.result
                result['final_guard']=session.guard();session.caller_status('webview-reconcile-final-caller')
        except BaseException as exc:
            result.update(state='RECONCILIATION_OUTER_FAILURE',reconciliation_completed=False,
                error=type(exc).__name__+': '+str(exc))
        tx.write_new(ROOT/'result.json',result)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result['reconciliation_completed'] else 1


if __name__=='__main__':raise SystemExit(main())
