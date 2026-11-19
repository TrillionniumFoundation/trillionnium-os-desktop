"""Original IHG phase and operation limits, bound by a new final plan."""
import json,math,re
from pathlib import Path
PACKAGE="com.ihg.apps.android"
UID=10137
SELF="org.droidloom.qa.ihg.finalmain.r1"


LIST=['/system/bin/cmd','package','list','packages','-U','--show-versioncode','--user','0',PACKAGE]

PATHS=['/system/bin/cmd','package','path','--user','0',PACKAGE]

OWN_UID=['/system/bin/cmd','package','list','packages','-U','--user','0',SELF]

OWN_PATH=['/system/bin/cmd','package','path','--user','0',SELF]

STACKS=['/system/bin/cmd','activity','stack','list']

FOREGROUND=['/system/bin/dumpsys','window','displays']

def need(value,reason):
    if not value:
        raise RuntimeError(reason)

class Policy:
    """Per-phase explicit command authority, separate from transport success."""
    def __init__(self,phase,qa,resolve,inspect_plan,step,read,selected_task):
        need(phase in ('launch','inspect','cleanup'),'EXACT_AMAZON_PHASE_REQUIRED')
        need(qa.PACKAGE==PACKAGE and qa.UID==UID and qa.SELF==SELF,'EXACT_AMAZON_CONTRACT_REQUIRED')
        need(set(inspect_plan)=={'search','destination','input','post','readiness'} and
             all(inspect_plan[role]['operation']=='click' and
                 set(inspect_plan[role]['nonces'])=={'before','inspect','action','after'}
                 for role in ('search','destination')) and
             set(inspect_plan['input'])=={'schema','operation','value','nonces'} and
             inspect_plan['input']['schema']==1 and inspect_plan['input']['operation']=='set_text' and
             inspect_plan['input']['value']=='London' and
             set(inspect_plan['input']['nonces'])=={'before','inspect','action','after'} and
             inspect_plan['post']['operation']=='inspect' and set(inspect_plan['post']['nonces'])=={'before','inspect','after'} and
             isinstance(inspect_plan['readiness'],list) and len(inspect_plan['readiness'])==8 and
             all(plan['operation']=='inspect' and set(plan['nonces'])=={'before','inspect','after'}
                 for plan in inspect_plan['readiness']),
             'EXPLICIT_SEARCH_DESTINATION_LONDON_POST_AND_EIGHT_NO_ACTION_READINESS_PLANS')
        flat={role:inspect_plan[role] for role in ('search','destination','input','post')}
        flat.update({'readiness_'+str(index+1):plan for index,plan in enumerate(inspect_plan['readiness'])})
        values=[n for plan in flat.values() for n in plan['nonces'].values()]
        need(len(values)==len(set(values))==39,'THIRTY_NINE_DISTINCT_CURRENT_HELPER_NONCES')
        self.phase,self.qa,self.resolve,self.plan=phase,qa,list(resolve),flat
        self.step,self.read,self.selected_task=step,read,selected_task
        self.counts={};self.used_nonces=set();self.remove_attempted=False

    def claim(self,name,limit):
        count=self.counts.get(name,0)
        need(count<limit,'AMAZON_PHASE_COMMAND_LIMIT:'+name)
        self.counts[name]=count+1

    def admit(self,argv,timeout,mutation,private):
        need(isinstance(argv,list) and all(isinstance(x,str) for x in argv) and type(mutation) is bool and
             type(private) is bool and isinstance(timeout,(int,float)) and not isinstance(timeout,bool) and
             math.isfinite(timeout) and 0<timeout<=70,'EXACT_COMMAND_SHAPE_REQUIRED')
        if argv in (LIST,PATHS):
            need(timeout==15 and not mutation and not private,'TARGET_METADATA_READ_ONLY')
            self.claim('target_uid' if argv==LIST else 'target_path',2)
            return
        if argv in (OWN_UID,OWN_PATH):
            need(timeout==8 and not mutation and not private,'HELPER_METADATA_READ_ONLY')
            # Up to eight read-only sequences plus four explicit sequences and outer pair.
            self.claim('helper_uid' if argv==OWN_UID else 'helper_path',26 if self.phase=='inspect' else 2)
            return
        if argv==self.resolve:
            need(self.phase=='launch' and timeout==15 and not mutation and not private,
                 'CURRENT_COMPONENT_READ_ONLY_BEFORE_LAUNCH')
            self.claim('resolve',1);return
        if argv==STACKS:
            need(not mutation and not private and timeout<=20,'TASK_SNAPSHOT_READ_ONLY')
            self.claim('stacks',33 if self.phase=='cleanup' else 24 if self.phase=='inspect' else 2);return
        if argv==FOREGROUND:
            need(self.phase=='inspect' and timeout==15 and not mutation and private,
                 'ONLY_PRIVATE_CURRENT_FOREGROUND_READ')
            self.claim('foreground',36);return
        if self.phase=='cleanup' and argv[:4]==['/system/bin/cmd','activity','stack','remove']:
            # Full equality below, not a prefix-based permission grant.
            selected=self.selected_task()
            need(len(argv)==5 and argv==['/system/bin/cmd','activity','stack','remove',str(selected['task'])] and
                 selected['package']==PACKAGE and selected['prelaunch_absent'] is True and
                 selected['cleanup_allowed'] is True and timeout==20 and mutation and not private,
                 'ONLY_EXACT_NEW_OWNED_LEAF_REMOVAL')
            need(not self.remove_attempted,'REMOVAL_CANNOT_BE_REPLAYED')
            self.remove_attempted=True;return
        need(self.phase=='inspect' and timeout==20 and not private,
             'NO_OTHER_IHG_COMMAND_ADMITTED')
        matches=[]
        for plan in self.plan.values():
            for phase,nonce in plan['nonces'].items():
                if nonce in self.used_nonces:continue
                path=self.step/(nonce+'.request.json')
                try:raw=self.read(path,65536)
                except FileNotFoundError:continue
                request=json.loads(raw)
                operation=plan['operation'] if phase=='action' else 'inspect' if phase=='inspect' else 'state'
                need(request.get('nonce')==nonce and request.get('op')==operation,
                     'FIXED_CURRENT_PHASE_REQUEST_REQUIRED')
                self.qa.validate_request(request)
                if self.qa.instrumentation_argv(request)==argv:
                    need(mutation is (operation in ('click','set_text')),'EXACT_CURRENT_OPERATION_MUTATION_FLAG')
                    matches.append((nonce,operation))
        need(len(matches)==1,'ONLY_ONE_CURRENT_SOURCE_BOUND_HELPER_REQUEST')
        nonce,operation=matches[0]
        self.used_nonces.add(nonce);self.claim('instrument',39)
        if operation=='click':self.claim('click',2)
        elif operation=='set_text':
            need(self.counts.get('click')==2,'TWO_PRIOR_CLICK_ADMISSIONS_REQUIRED_FOR_LONDON')
            self.claim('set_text',1)
