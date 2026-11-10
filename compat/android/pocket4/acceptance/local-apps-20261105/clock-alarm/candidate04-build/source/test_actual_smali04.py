#!/usr/bin/env python3
"""Execute reviewed smali control flow against explicit Android boundary doubles.

This is not an Android runtime test. The VM consumes the candidate's actual
instruction stream and exception ranges; unsupported instructions fail closed.
Provider/clock/PI/Service boundaries are named doubles. ART verification remains
an independent required artifact gate.
"""
from pathlib import Path
import ast, copy, hashlib, importlib.util, json, re

ROOT = Path(__file__).resolve().parent
BASE = 'Lcom/android/deskclock/alarms/'
COMP = BASE + 'AlarmStateManager$Companion;'
SERVICE = BASE + 'AlarmService;'
SCHED = BASE + 'AlarmStateManager$AlarmManagerStateChangeScheduler;'
RECEIVER = BASE + 'AlarmStateManager;'
PREFIX = 'com.android.deskclock.extra.SCHEDULED_ALARM_'
STATE = 'intent.extra.alarm.state'
GLOBAL = 'intent.extra.alarm.global.id'
spec = importlib.util.spec_from_file_location('clock_ir_test', ROOT.parent / 'expired-text/smali_equivalence.py')
ir = importlib.util.module_from_spec(spec); spec.loader.exec_module(ir)


class Thrown(Exception):
    def __init__(self, kind, message=''):
        self.kind = kind; super().__init__(message or kind)


def instance(state=3, ident=3, parent=7, when=100000, timeout=160000):
    return {'kind': 'instance', 'mId': ident, 'mAlarmId': parent, 'mAlarmState': state,
            'when': when, 'timeout': timeout}


def intent(row=None, state=5, source=None, generation=121):
    row = instance() if row is None else row
    return {'kind': 'intent', 'component': SERVICE, 'data': 'content://com.android.deskclock/instances/' + str(row['mId']),
        'action': 'change_state', 'categories': {'ALARM_MANAGER'}, 'flags': 0,
        'extras': {PREFIX + 'VERSION': 1, PREFIX + 'TIME': row['when'],
            PREFIX + 'PARENT': -1 if row['mAlarmId'] is None else row['mAlarmId'],
            PREFIX + 'FROM_STATE': row['mAlarmState'] if source is None else source,
            STATE: state, GLOBAL: generation}}


class Machine:
    def __init__(self, original=False):
        self.methods = {}
        for path in (ROOT / ('original' if original else 'candidate')).rglob('*.smali'):
            text = path.read_text(); cls = re.search(r'^\.class .* (L[^;]+;)$', text, re.M)[1]
            for signature, body in ir.class_ir(text)['methods'].items():
                self.methods[(cls, signature.split()[-1])] = (signature, body)
        self.original = original; self.now = 100010; self.generation = 121
        self.rows = {3: instance()}; self.current = None
        self.pis = {}; self.scheduled = {}; self.factory_calls = []; self.calls = []
        self.handler_mode = 'normal'; self.finish_throws = False; self.is_m = True
        self.service = {'kind': 'service'}; self.context = {'kind': 'context'}
        self.companion = {'kind': 'companion'}; self.scheduler = {'kind': 'scheduler'}

    def call(self, cls, method, args):
        signature, body = self.methods[(cls, method)]
        args = list(args); registers = {}; word = 0
        parameters = re.findall(r'\[*L[^;]+;|\[*[ZBSCIFJD]', method[method.index('(')+1:method.index(')')])
        if ' static ' not in ' ' + signature + ' ': parameters.insert(0, 'Lself;')
        for typ, value in zip(parameters, args, strict=True):
            registers['p' + str(word)] = value
            if typ in ('J', 'D'): registers['p' + str(word + 1)] = value; word += 1
            word += 1
        instructions = body['instructions']; pc = 0; last = None; exception = None
        def read(name):
            if name not in registers: raise AssertionError('UNINITIALIZED_REGISTER:' + name)
            return registers[name]
        def put(name, value, wide=False):
            registers[name] = value
            if wide: registers[name[0]+str(int(name[1:])+1)] = value
        def target(text): return int(re.fullmatch(r'@instruction\[(\d+)\]', text)[1])
        for step in range(5000):
            if pc >= len(instructions): raise AssertionError('MISSING_RETURN')
            instruction = instructions[pc]; oldpc = pc; pc += 1
            op, _, operands = instruction.partition(' ')
            try:
                if op.startswith('const-string'):
                    name, value = operands.split(', ', 1); put(name, ast.literal_eval(value))
                elif op == 'const-class':
                    name, value = operands.split(', ', 1); put(name, value)
                elif op.startswith('const'):
                    name, value = operands.split(', ', 1); put(name, int(value.rstrip('L'), 0), 'wide' in op)
                elif op.startswith('move-result'):
                    put(operands, last, 'wide' in op)
                elif op == 'move-exception': put(operands, exception)
                elif op.startswith('move'):
                    a, b = operands.split(', '); put(a, read(b), 'wide' in op)
                elif op.startswith('iget'):
                    dest, obj, field = operands.split(', '); name = field.split('->')[1].split(':')[0]
                    value = self.current if name == 'mCurrentAlarm' else read(obj)[name]
                    put(dest, value, 'wide' in op)
                elif op.startswith('sget'):
                    dest, field = operands.split(', ')
                    put(dest, {'kind': field})
                elif op.startswith('invoke'):
                    match = re.fullmatch(r'\{(.*?)\}, (L[^;]+;)->(.+)', operands)
                    if not match: raise AssertionError('UNSUPPORTED_INVOKE:' + instruction)
                    words = [] if not match[1] else [read(x) for x in match[1].split(', ')]
                    desc = match[3]; types = re.findall(r'\[*L[^;]+;|\[*[ZBSCIFJD]', desc[desc.index('(')+1:desc.index(')')])
                    if not op.startswith('invoke-static'): types.insert(0, 'Lself;')
                    values=[]; cursor=0
                    for typ in types:
                        values.append(words[cursor]); cursor += 2 if typ in ('J','D') else 1
                    if cursor != len(words): raise AssertionError('INVOKE_WORD_COUNT:' + instruction)
                    last = self.invoke(match[2], desc, values)
                elif op.startswith('if-'):
                    fields=operands.split(', '); names=fields[:-1]
                    a=read(names[0]); b=0 if len(names)==1 else read(names[1])
                    if a is None: a=0
                    if b is None: b=0
                    cmp=op[3:].removesuffix('z')
                    test={'eq':lambda:a==b,'ne':lambda:a!=b,'lt':lambda:a<b,'le':lambda:a<=b,
                          'gt':lambda:a>b,'ge':lambda:a>=b}[cmp]()
                    if test: pc=target(fields[-1])
                elif op.startswith('goto'): pc=target(operands)
                elif op == 'cmp-long':
                    dest,a,b=operands.split(', '); put(dest,(read(a)>read(b))-(read(a)<read(b)))
                elif op == 'return-void': return None
                elif op.startswith('return'): return read(operands)
                elif op == 'check-cast': pass
                elif op == 'new-instance':
                    dest,typ=operands.split(', ');put(dest,{'kind':typ})
                elif op == 'new-array':
                    dest,size,typ=operands.split(', ');put(dest,[None]*read(size))
                elif op == 'filled-new-array':
                    regs=operands.split('}',1)[0][1:]; last=[read(x) for x in regs.split(', ')] if regs else []
                elif op == 'throw':
                    item=read(operands)
                    if isinstance(item,BaseException): raise item
                    raise Thrown(item['kind'],item.get('message',''))
                else: raise AssertionError('UNSUPPORTED_INSTRUCTION:' + instruction)
            except Thrown as error:
                handlers=body['exception_coverage'][oldpc]
                handler=next((h for h in handlers if h[0]=='all' or h[0]==error.kind),None)
                if handler is None: raise
                exception=error;pc=handler[1]
        raise AssertionError('INSTRUCTION_BUDGET_EXCEEDED')

    def invoke(self, cls, method, args):
        name=method.split('(')[0]
        if cls==COMP and name=='createStateChangeIntent':
            _,ctx,category,row,state=args
            item=intent(row,state);item['categories']={category};item['extras']={GLOBAL:self.generation}
            if state is not None and state != 0: item['extras'][STATE]=state
            # Integer.valueOf(0) is represented as an int; keep that valid state.
            if state == 0 and category=='ALARM_MANAGER': item['extras'][STATE]=0
            return item
        if cls==COMP and name=='handleIntent':
            self.calls.append(('handle',copy.deepcopy(args[2])))
            if self.handler_mode=='throw': raise Thrown('Ljava/lang/IllegalStateException;','provider failure')
            item=args[2];ident=int(item['data'].rsplit('/',1)[1]);row=self.rows.get(ident)
            if not row or item['extras'].get(GLOBAL,-1)!=self.generation: return None
            if not self.original and not self.call(COMP,'isScheduledIntentCurrent(Landroid/content/Context;Landroid/content/Intent;Lcom/android/deskclock/provider/AlarmInstance;)Z',[self.companion,self.context,item,row]): return None
            if self.handler_mode=='no-write':return None
            if self.handler_mode=='delete':self.rows.pop(ident);return None
            if self.handler_mode=='reuse':self.rows[ident]=instance(state=5,when=row['when']+60000);return None
            row['mAlarmState']=item['extras'][STATE]
            if self.handler_mode=='new-generation':self.generation+=1
            return None
        if cls==COMP and name=='registerInstance':
            self.calls.append(('register',copy.deepcopy(args[2])))
            self.rows[args[2]['mId']]['mAlarmState']=6
            return None
        if cls==SERVICE and name=='startAlarm':
            self.calls.append(('start',copy.deepcopy(args[1])));self.current=copy.deepcopy(args[1]);return None
        if (cls,method) in self.methods: return self.call(cls,method,args)
        if 'LogUtils' in cls: return None
        if cls=='Ljava/lang/Object;' and name=='getClass':
            if args[0] is None:raise Thrown('Ljava/lang/NullPointerException;')
            return type(args[0]).__name__
        if cls in ('Ljava/lang/Integer;','Ljava/lang/Long;') and name=='valueOf':return args[0]
        if cls=='Ljava/lang/Long;' and name=='longValue':return args[0]
        if cls=='Ljava/lang/String;' and name=='equals':return args[0]==args[1]
        if cls=='Ljava/lang/String;' and name=='hashCode':
            value=0
            for c in args[0]:value=(31*value+ord(c))&0xffffffff
            return value if value<2**31 else value-2**32
        if cls=='Ljava/util/Objects;' and name=='equals':return args[0]==args[1]
        if cls=='Ljava/util/Calendar;':
            if name=='getInstance':return {'calendar':self.now}
            if name=='getTimeInMillis':return args[0]['calendar']
            if name=='before':return args[0]['calendar']<args[1]['calendar']
            if name=='after':return args[0]['calendar']>args[1]['calendar']
        if cls.endswith('/AlarmInstance;'):
            if name=='getAlarmTime':return {'calendar':args[0]['when']}
            if name=='getTimeout':return None if args[0]['timeout'] is None else {'calendar':args[0]['timeout']}
            if name=='hashCode':return args[0]['mId']
        if cls.endswith('/AlarmInstance$Companion;'):
            if name=='getId':
                try:return int(args[1].rsplit('/',1)[1])
                except (ValueError,AttributeError):raise Thrown('Ljava/lang/IllegalArgumentException;')
            if name=='getInstance':return copy.deepcopy(self.rows.get(args[2]))
        if cls.endswith('/DataModel$Companion;') and name=='getDataModel':return {'kind':'data-model'}
        if cls.endswith('/DataModel;') and name=='getGlobalIntentId':return self.generation
        if cls.endswith('/Utils;') and name=='isMOrLater':return self.is_m
        if cls=='Landroid/content/Intent;':
            item=args[0]
            if name=='hasExtra':return args[1] in item['extras']
            if name in ('getIntExtra','getLongExtra'):return item['extras'].get(args[1],args[2])
            if name=='putExtra':item['extras'][args[1]]=args[2];return item
            if name=='getAction':return item['action']
            if name=='getData':return item['data']
            if name=='hasCategory':return args[1] in item['categories']
            if name=='setClass':item['component']=args[2];return item
            if name=='addFlags':item['flags']|=args[1];return item
        if cls in ('Landroid/content/Context;','Landroid/app/Service;'):
            if name=='getContentResolver':return {'kind':'resolver'}
            if name=='getSystemService':assert args[1]=='alarm';return {'kind':'alarm-manager'}
            if name=='stopSelf':self.calls.append(('stop',args[1]));return None
        if cls=='Landroid/app/PendingIntent;':
            if name.startswith('get'):
                ctx,request,item,flags=args;kind={'getService':'service','getForegroundService':'fgs','getBroadcast':'receiver'}[name]
                key=(kind,request,item['component'],item['data'],item['action'],tuple(sorted(item['categories'])))
                self.factory_calls.append((kind,flags,key))
                if flags&0x20000000:return self.pis.get(key)
                pi={'key':key,'intent':copy.deepcopy(item)};self.pis[key]=pi;return pi
            if name=='cancel':self.pis.pop(args[0]['key'],None);return None
        if cls=='Landroid/app/AlarmManager;':
            if name=='cancel':self.scheduled.pop(args[1]['key'],None);return None
            if name in ('setExact','setExactAndAllowWhileIdle'):
                assert args[1]==0;self.scheduled[args[3]['key']]={'at':args[2],'pi':args[3],'api':name};return None
        if cls=='Landroid/content/BroadcastReceiver$PendingResult;' and name=='finish':
            self.calls.append(('finish',None))
            if self.finish_throws:raise Thrown('Ljava/lang/IllegalStateException;','finish failure')
            return None
        if cls=='Landroid/os/PowerManager$WakeLock;' and name=='release':self.calls.append(('release',None));return None
        if name=='<init>' and cls.endswith('Exception;'):args[0]['message']=args[1];return None
        raise AssertionError('UNIMPLEMENTED_BOUNDARY:'+cls+'->'+method)


VALID='isScheduledIntentCurrent(Landroid/content/Context;Landroid/content/Intent;Lcom/android/deskclock/provider/AlarmInstance;)Z'
START='onScheduledStart(Landroid/content/Intent;I)Z'
SCHEDULE='scheduleInstanceStateChange(Landroid/content/Context;Ljava/util/Calendar;Lcom/android/deskclock/provider/AlarmInstance;I)V'
CANCEL='cancelScheduledInstanceStateChange(Landroid/content/Context;Lcom/android/deskclock/provider/AlarmInstance;)V'
LAMBDA='$r8$lambda$_knPXn4cJMDcun_XoalMIdqZCj0(Landroid/content/Context;Landroid/content/Intent;Landroid/content/BroadcastReceiver$PendingResult;Landroid/os/PowerManager$WakeLock;)Lkotlin/Unit;'


def run_tests():
    checks=[]
    def check(name,fn):
        fn();checks.append({'name':name,'passed':True})
    def counts(m):return {k:sum(x[0]==k for x in m.calls) for k in ('handle','start','stop','register','finish','release')}
    def schedule_case(state):
        m=Machine();row=m.rows[3]
        m.call(SCHED,SCHEDULE,[m.scheduler,m.context,{'calendar':120000},row,state])
        assert len(m.scheduled)==1
        key,entry=next(iter(m.scheduled.items()))
        assert key[0]==('fgs' if state==5 else 'receiver') and key[2]==(SERVICE if state==5 else RECEIVER)
        assert entry['at']==120000 and entry['api']=='setExactAndAllowWhileIdle'
        assert entry['pi']['intent']['extras'][STATE]==state
        assert entry['pi']['intent']['extras'][PREFIX+'FROM_STATE']==3
        assert [x[0] for x in m.factory_calls[:3]]==['service','fgs','receiver']
        assert all(x[1]==0x20000000 for x in m.factory_calls[:3])
        m.call(SCHED,CANCEL,[m.scheduler,m.context,row]);assert not m.pis and not m.scheduled
    for state in range(9):check('route-and-cancel-state-'+str(state),lambda state=state:schedule_case(state))
    def migration():
        m=Machine();row=m.rows[3];old=intent(row)
        for kind,comp in [('getService',SERVICE),('getForegroundService',SERVICE),('getBroadcast',RECEIVER)]:
            old['component']=comp;pi=m.invoke('Landroid/app/PendingIntent;',kind,[m.context,3,old,0x8000000]);m.scheduled[pi['key']]={}
        foreign=intent(instance(ident=99));pi=m.invoke('Landroid/app/PendingIntent;','getService',[m.context,99,foreign,0x8000000]);m.scheduled[pi['key']]={}
        m.call(SCHED,SCHEDULE,[m.scheduler,m.context,{'calendar':100000},row,5])
        assert sorted(x[0] for x in m.scheduled)==['fgs','service']
        row['mAlarmState']=5;m.call(SCHED,SCHEDULE,[m.scheduler,m.context,{'calendar':160000},row,6])
        assert sorted(x[0] for x in m.scheduled)==['receiver','service'] and all(x[1] in (3,99) for x in m.scheduled)
    check('legacy-plus-two-new-types-cancelled-on-reschedule-foreign-PI-preserved',migration)
    def bad_schedule(state):
        m=Machine()
        try:m.call(SCHED,SCHEDULE,[m.scheduler,m.context,{'calendar':120000},m.rows[3],state])
        except Thrown:pass
        else:raise AssertionError('unsupported state accepted')
        assert not m.factory_calls and not m.scheduled
    for state in (-1,9):check('unsupported-scheduler-state-'+str(state),lambda state=state:bad_schedule(state))
    def validate(change,expected=0):
        m=Machine();row=copy.deepcopy(m.rows[3]);item=intent(row);change(m,row,item)
        assert m.call(COMP,VALID,[m.companion,m.context,item,row])==expected
    for name,change in [
        ('old-generation',lambda m,r,i:i['extras'].__setitem__(GLOBAL,120)),
        ('other-occurrence',lambda m,r,i:i['extras'].__setitem__(PREFIX+'TIME',160000)),
        ('reused-id-other-parent',lambda m,r,i:i['extras'].__setitem__(PREFIX+'PARENT',8)),
        ('source-state-changed',lambda m,r,i:r.__setitem__('mAlarmState',4)),
        ('wrong-category',lambda m,r,i:i.__setitem__('categories',{'DISMISS_TAG'})),
        ('wrong-action',lambda m,r,i:i.__setitem__('action','STOP_ALARM')),
        ('missing-occurrence',lambda m,r,i:i['extras'].pop(PREFIX+'TIME')),
        ('unsupported-version',lambda m,r,i:i['extras'].__setitem__(PREFIX+'VERSION',2)),
        ('negative-request',lambda m,r,i:i['extras'].__setitem__(STATE,-1)),
        ('unknown-request',lambda m,r,i:i['extras'].__setitem__(STATE,9))]:
        check(name,lambda change=change:validate(change))
    for state in (6,7,8):check('terminal-state-'+str(state)+'-cannot-fire',lambda state=state:validate(lambda m,r,i:r.__setitem__('mAlarmState',state)))
    check('DB-FIRED-recovery-accepted',lambda:validate(lambda m,r,i:r.__setitem__('mAlarmState',5),1))
    check('unmarked-existing-handler-contract-bypasses-new-envelope',lambda:validate(lambda m,r,i:i['extras'].pop(PREFIX+'VERSION'),1))
    def service_case(mode='fresh',current=False):
        m=Machine();row=m.rows[3];item=intent(row)
        if current:m.current=copy.deepcopy(row);m.current['mAlarmState']=5
        if mode in ('recovery','duplicate'):row['mAlarmState']=5
        if mode=='duplicate':m.current=copy.deepcopy(row)
        if mode=='old-generation':item['extras'][GLOBAL]=120
        if mode=='missing':m.rows.clear()
        if mode=='wrong-parent':item['extras'][PREFIX+'PARENT']=8
        if mode=='expired':row['mAlarmState']=5;m.now=170000
        if mode=='early':m.now=99999
        if mode=='terminal':row['mAlarmState']=8;item['extras'][PREFIX+'FROM_STATE']=8
        if mode=='malformed':item['data']='content://com.android.deskclock/instances/no-id'
        if mode=='non-fired':item['extras'][STATE]=3
        if mode in ('no-write','delete','reuse','new-generation','throw'):m.handler_mode=mode
        thrown=False
        try:assert m.call(SERVICE,START,[m.service,item,41])==1
        except Thrown:thrown=True
        c=counts(m)
        if mode in ('fresh','recovery'):assert c['start']==1 and c['handle']==1 and c['stop']==0
        elif mode=='duplicate':assert c['start']==c['handle']==c['stop']==0
        elif mode=='expired':assert c['register']==1 and c['start']==c['handle']==0 and c['stop']==(not current)
        else:assert c['start']==0 and c['stop']==(not current)
        assert thrown==(mode=='throw')
        assert all(value==41 for kind,value in m.calls if kind=='stop')
        assert c['release']==0
    for mode in ('fresh','recovery','duplicate','old-generation','missing','wrong-parent','expired','early','terminal','malformed','non-fired','no-write','delete','reuse','new-generation','throw'):
        check('service-'+mode,lambda mode=mode:service_case(mode))
    for mode in ('old-generation','missing','wrong-parent','terminal','throw'):
        check('service-'+mode+'-preserves-existing-alarm',lambda mode=mode:service_case(mode,True))
    def receiver(mode):
        m=Machine();item=intent(state=6);m.rows[3]['mAlarmState']=5;item['extras'][PREFIX+'FROM_STATE']=5
        if mode=='FIRED':item['extras'][STATE]=5
        if mode=='handler-throws':m.handler_mode='throw'
        if mode=='finish-throws':m.finish_throws=True
        thrown=False
        try:m.call(RECEIVER,LAMBDA,[m.context,item,{'kind':'pending-result'},{'kind':'wake-lock'}])
        except Thrown:thrown=True
        c=counts(m);assert c['finish']==c['release']==1
        assert c['handle']==(mode!='FIRED') and thrown==(mode in ('handler-throws','finish-throws'))
        assert c['start']==0
    for mode in ('non-FIRED','FIRED','handler-throws','finish-throws'):check('receiver-'+mode,lambda mode=mode:receiver(mode))
    def negative_control():
        m=Machine(original=True);item=intent(generation=120)
        m.call(SERVICE,'onStartCommand(Landroid/content/Intent;II)I',[m.service,item,0,41])
        assert counts(m)['start']==1 and m.rows[3]['mAlarmState']==3
    check('actual-preimage-negative-old-generation-handler-reject-still-starts',negative_control)
    return checks


if __name__=='__main__':
    checks=run_tests()
    sources={str(p.relative_to(ROOT)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for sub in ('original','candidate') for p in (ROOT/sub).rglob('*.smali')}
    result={'schema':'actual-smali-host-control-flow-tests-v1','passed':len(checks),'checks':checks,'sources':sources,
        'Android_runtime_executed':False,'business_success':False,
        'scope':'Actual reviewed smali instructions and catch ranges; Android services/provider/PI/clock are explicit doubles. ART and actual owned-alarm acceptance remain separate.'}
    (ROOT/'HOST_CONTROL_FLOW_VALIDATION.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'passed':len(checks),'Android_runtime_executed':False}))
