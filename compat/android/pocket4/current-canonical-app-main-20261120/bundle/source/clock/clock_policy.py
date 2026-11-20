"""Finite original Clock commands and native requests on one fresh Main.

Android task ownership is separately proved from real new launch or alert
evidence. Retiring a host command never proves Android task/data cleanup.
"""
import base64
import json
import re

PACKAGE='com.android.deskclock'
NATIVE='local.pocket4.actions.v2'
READERS=('clock_protection.py','clock_timer_core.py','clock_expiry_flow.py',
    'clock_alarm_flow.py','clock_alarm_reader.py','clock_delivery_trial.py',
    'clock_audio_observe.py','clock_delivery.py')


class Policy:
    def __init__(self,session):
        self.s=session;self.c=session.c;self.remove_sent=set()

    def command(self,argv,timeout):
        s,c=self.s,self.c
        c.need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv)
            and type(timeout) in (int,float) and 5<timeout<=70,'EXACT_ORIGINAL_CLOCK_COMMAND')
        caller=s.original_caller(READERS,skip=('android','sql','read_sql','root_query','run_host'))
        src,method=caller['source'],caller['function']
        if argv==['/system/bin/cmd','activity','stack','list']:
            c.need((src=='clock_delivery_trial.py' and method=='stacks' and timeout==15)
                or (src=='clock_protection.py' and method=='snapshot' and timeout==20),'ORIGINAL_CLOCK_TASK_READ')
            return False
        if argv==['/system/bin/dumpsys','window','displays']:
            c.need(src=='clock_delivery_trial.py' and method=='focus' and timeout==6,'ORIGINAL_CLOCK_FOCUS_READ')
            return False
        if argv in (['/system/bin/pm','path',PACKAGE],['/system/bin/dumpsys','package',PACKAGE]):
            c.need(src=='clock_protection.py' and method=='identity' and timeout==20,'ORIGINAL_CLOCK_IDENTITY_READ')
            return False
        p=s.components['clock_preservation.py']
        sound=[['/system/bin/dumpsys','audio'],['/system/bin/cmd','appops','get','--user','0',PACKAGE,'POST_NOTIFICATION']]
        sound += [['/system/bin/settings','--user','0','get','system',key] for key in p.SOUND_KEYS]
        if argv in sound:
            c.need(src=='clock_protection.py' and method=='snapshot' and timeout==20,'ORIGINAL_READONLY_SOUND_AND_PERMISSION')
            return False
        if argv==['/system/bin/cat','/proc/uptime']:
            c.need(src=='clock_timer_core.py' and method=='uptime' and timeout==20,'ORIGINAL_TIMER_UPTIME')
            return False
        if argv==['/system/bin/dumpsys','alarm']:
            c.need((src=='clock_timer_core.py' and method=='observe_scheduler' and timeout==15)
                or (src=='clock_alarm_flow.py' and method=='evidence' and timeout==12),'ORIGINAL_CLOCK_SCHEDULER_OBSERVATION')
            return False
        if argv in (['/system/bin/getprop','persist.sys.timezone'],['/system/bin/date','+%s|%Y-%m-%dT%H:%M:%S%z']):
            c.need(s.kind=='alarm04' and src=='clock_alarm_reader.py' and method=='clock' and timeout==20,
                'ORIGINAL_ALARM_READONLY_DEVICE_TIME')
            return False
        if argv==['/system/bin/dumpsys','media.audio_flinger']:
            c.need(s.kind=='expiry06' and src=='clock_audio_observe.py' and method=='sample' and timeout==15,
                'ORIGINAL_CLOCK_UID_AUDIO_OBSERVATION_ONLY')
            return False
        if argv==['/system/bin/dumpsys','notification','--package',PACKAGE]:
            c.need(s.kind=='expiry06' and src=='clock_expiry_flow.py' and method=='notifications' and timeout==12,
                'ORIGINAL_FILTERED_TIMER_NOTIFICATION')
            return False
        if argv==['/system/bin/dumpsys','notification','--noredact','--package',PACKAGE]:
            c.need(timeout==12 and ((s.kind=='alarm04' and src=='clock_alarm_flow.py' and method=='evidence')
                or (s.kind=='expiry06' and src=='clock_delivery.py' and method in ('running','expired'))),
                'ONLY_ORIGINAL_CLOCK_NOTIFICATION_TEXT_SCOPE')
            return False
        if argv==['/system/bin/dumpsys','activity','services',PACKAGE]:
            c.need(timeout==12 and ((s.kind=='alarm04' and src=='clock_alarm_flow.py' and method=='evidence')
                or (s.kind=='expiry06' and src=='clock_expiry_flow.py' and method=='service')),
                'ORIGINAL_CLOCK_SERVICE_OBSERVATION')
            return False
        if argv==['/system/bin/dumpsys','activity','activities',PACKAGE]:
            c.need(s.kind=='alarm04' and src=='clock_alarm_flow.py' and method=='claim_alert' and timeout==12,
                'ONLY_SOURCE_BOUND_ORIGINAL_ALARM_INTENT_READ')
            return False
        c.need(argv[:4]==['/system/bin/cmd','activity','stack','remove'] and len(argv)==5
            and re.fullmatch('[1-9][0-9]*',argv[4]) and timeout==15
            and caller=={'source':'clock_delivery_trial.py','function':'close'}
            and s.active_api is None and s.trial is not None and s.flow is not None,'ONLY_ORIGINAL_NORMAL_CLOCK_REMOVE')
        task=int(argv[4]);claim=s.claimed_tasks.get(task);flow=s.flow
        c.need(claim is not None and task not in self.remove_sent and s.trial.owned is None
            and s.pending_input() is None and flow.effect_pending is None and s.last_stacks is not None,
            'UNOWNED_OR_UNKNOWN_CLOCK_TASK_CANNOT_BE_REMOVED')
        close=flow.close_pending
        c.need(close==task if s.kind=='alarm04' else type(close) is dict and close.get('task')==task,
            'ORIGINAL_FLOW_CLOSE_AUTHORITY_REQUIRED')
        roots,tasks=s.last_stacks
        c.need(tasks==set(claim['prelaunch_tasks'])|{task} and s.trial.base.exact_leaf(roots,task),
            'EXACT_CURRENT_CLOCK_OWNED_TASK_TOPOLOGY')
        item=s.consume_intent('task-remove',argv)
        c.need(item['value'].get('prelaunch_absent') is True,'ORIGINAL_PRELAUNCH_ABSENCE_INTENT')
        self.remove_sent.add(task)
        return True

    def observe(self,argv,raw):
        s=self.s
        if argv==['/system/bin/cmd','activity','stack','list']:
            s.last_stacks=s.components['clock_delivery_trial.py'].parse_stacks(raw.decode('utf-8','strict'))
        if argv==['/system/bin/dumpsys','activity','activities',PACKAGE]:
            s.last_alarm_activities=bytes(raw)

    def sql(self,label,sql):
        s,c=self.s,self.c;p=s.components['clock_preservation.py']
        caller=s.original_caller(('clock_protection.py','clock_alarm_reader.py'),skip=('sql','read_sql','root_query'))
        if caller['source']=='clock_protection.py':
            c.need(label=='original-protection' and sql in list(p.QUERIES.values())+['SELECT * FROM alarm_templates ORDER BY _id;'],
                'ORIGINAL_FIXED_CLOCK_PROTECTION_SELECTS')
            return
        c.need(s.kind=='alarm04' and s.alarm_reader is not None,'ORIGINAL_ALARM_READER_SCOPE')
        r=s.alarm_reader;method=caller['function']
        summary=('SELECT (SELECT COUNT(*) FROM alarm_templates) AS template_count,'
            '(SELECT COUNT(*) FROM alarm_instances) AS instance_count,'
            '(SELECT COUNT(*) FROM alarm_templates WHERE enabled<>0) AS enabled_count,'
            '(SELECT COUNT(*) FROM alarm_templates WHERE _id IN(1,2) AND enabled<>0) AS original_enabled,'
            "(SELECT COUNT(*) FROM alarm_templates WHERE label='"+r.MARKER+"') AS marker_count;")
        fixed={'alarm-summary':summary,'alarm-ids':'SELECT _id FROM alarm_templates ORDER BY _id;',
            'instance-ids':'SELECT _id,alarm_id,alarm_state FROM alarm_instances ORDER BY _id;'}
        if label in fixed:
            c.need(method=='summary' and sql==fixed[label],'ORIGINAL_ALARM_SUMMARY_QUERY')
            return
        c.need(method=='read' and label in ('owned-template','owned-instances') and s.flow is not None,
            'ONLY_ORIGINAL_OWNED_ALARM_SELECT')
        reader=s.flow.reader;candidate=reader.alarm_id
        if candidate is None:
            c.need(s.pending_input() is None and s.flow.effect_pending is not None
                and s.flow.effect_pending['operation']=='create' and s.flow.create_ack
                and reader.target is not None and s.last_alarm_summary is not None,
                'NEW_ALARM_QUERY_REQUIRES_ACTUAL_CREATE_ACK_AND_SINGLE_EXTRA')
            ids=s.last_alarm_summary
            extra=set(ids)-{1,2}
            c.need(len(extra)==1 and {1,2}<set(ids),'ONE_NEW_ACTUAL_ALARM_ID')
            candidate=next(iter(extra))
        c.need(type(candidate) is int and candidate>2,'ONLY_THIS_NEW_ALARM_ID')
        wanted=('SELECT '+r.TEMPLATE_FIELDS+' FROM alarm_templates WHERE _id='+str(candidate)+';' if label=='owned-template'
            else 'SELECT '+r.INSTANCE_FIELDS+' FROM alarm_instances WHERE alarm_id='+str(candidate)+' ORDER BY _id;')
        c.need(sql==wanted,'EXACT_THIS_OWNED_ALARM_FIELDS_AND_ID')

    def observe_sql(self,label,raw):
        if label=='alarm-ids':
            rows=self.c.parse(raw)
            self.c.need(type(rows) is list and all(type(v) is dict and set(v)=={'_id'} and type(v['_id']) is int
                and v['_id']>0 for v in rows),'ACTUAL_ALARM_ID_ROWS')
            ids=[v['_id'] for v in rows]
            self.c.need(ids==sorted(set(ids)),'UNIQUE_ACTUAL_ALARM_IDS')
            self.s.last_alarm_summary=ids


def native_request(c,outer,request,action_used):
    c.need(type(request) is dict and request.get('expected_package')==PACKAGE
        and request.get('display')==0 and request.get('accessibility_mode')=='none','EXACT_CLOCK_NATIVE_SCOPE')
    if request.get('op') in ('meta','dump'):
        c.need(set(request)=={'op','expected_package','display','accessibility_mode'},'EXACT_CLOCK_NATIVE_READ_FIELDS')
        return False
    c.need(not action_used and outer.get('op') in ('click','set-text'),'ONE_ORIGINAL_CLOCK_NATIVE_EFFECT')
    if 'expected_package' in outer:expected=outer
    else:
        expected={k:v for k,v in outer.items() if k in {'op','selector','method','value','display','accessibility_mode'}}
        expected['expected_package']=outer['package']
    c.need(request==expected,'UNCHANGED_CLOCK_NATIVE_REQUEST_PROJECTION')
    return True


def backend_android(c,outer,argv,timeout,action_used):
    if argv==['/system/bin/screencap','-p']:
        c.need(timeout==20,'ORIGINAL_CLOCK_SCREENSHOT_TIMEOUT');return False,True
    c.need(len(argv)==8 and argv[:6]==['/system/bin/am','instrument','-w','-r','-e','request']
        and argv[-1]==NATIVE+'/.ActionRunner' and timeout==70,'ONLY_ORIGINAL_CLOCK_NATIVE_RUNNER')
    raw=base64.b64decode(argv[6],validate=True);c.need(len(raw)<=65536,'BOUNDED_CLOCK_NATIVE_REQUEST')
    request=c.parse(raw)
    c.need(base64.b64encode(json.dumps(request,ensure_ascii=True,separators=(',',':')).encode()).decode()==argv[6],
        'ORIGINAL_CLOCK_NATIVE_WIRE_ENCODING')
    return native_request(c,outer,request,action_used),False
