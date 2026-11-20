"""Private reminder-only extension of the successful Core21 fences; no inherited business credit."""
import re,time
INSTALL_SHA='ad31776194c0fb66dd4bed6a77bbbec3409782317912812ee965705d2d4053c2'
def need(v,reason):
    if not v:raise RuntimeError(reason)

REQUIRED={'reminder_set_in_calendar_ui','ordinary_provider_reminder_fired_while_task_closed',
          'exact_android_notification_delivered','deleted_in_calendar_ui',
          'owned_notification_removed_after_ui_delete'}

def extend(parent,core,m,model,base,policy,mouse,nms,runtime,audit,evidence_root,prerequisites):
    class ReminderFlow(parent):
        def __init__(self,*args):
            super().__init__(*args)
            self.plan=None;self.sampler=None;self.fired_alert=None;self.cleanup_deadline=None
            self.nms=nms.Evidence(self.s,self.tx,evidence_root,model.TITLE)
            self.result.update(schema='calendar-owned-natural-reminder22/v1',gates={},
                lease_seconds=480,cleanup_seconds=90,control_input_budget=20,total_UI_budget=24,
                original_core21_business_retested=False,host_notification_actions=0,
                spoofed_broadcasts=0,reminder_provider_insert_commands=0,
                provider_delivery_scope='natural ordinary reminder while normal-owned task is closed',
                desktop_delivery_or_sound_qualified=False,snooze_qualified=False)
        def setup(self):
            self.result['guard_before']=self.s.guard()
            self.result['calendar_uid_census_before']=audit.uid_census(self.s,self.record,'runtime-uid-before')
            self.result['fresh_prerequisites']=prerequisites.verify(self.s,self.result['guard_before'])
            self.result['calendar_before']=self.calendar_identity()
            need(m.permission_granted(self.result['calendar_before']['permissions'],'android.permission.POST_NOTIFICATIONS'),
                 'EXISTING_NOTIFICATION_PERMISSION_REQUIRED_NO_GRANT')
            self.result['provider_before']=self.doc.identity(self.s,'com.android.providers.calendar',core.PROVIDER_SHA,10017,37)
            self.result['existing_shell_calendar_permissions']=self.shell_grants()
            roots,tasks=self.ui.stacks('reminder-baseline')
            need(not any(c['component'].split('/')[0] in (m.CALENDAR,m.PACKAGE)
                         for r in roots.values() for c in r['children']),'PREEXISTING_CALENDAR_TASK')
            self.ui.baseline=set(tasks);self.result['baseline_task_ids']=sorted(tasks)
            self.baseline_counts=self.counts('reminder-baseline')
            need(not any(self.baseline_counts.values()),'FRESH_ZERO_CALENDAR_BASELINE')
            self.model.require_empty(self.model.read('baseline'))
            self.result['system_timezone_before']=self.s.android(['/system/bin/getprop','persist.sys.timezone'],8).decode().strip()
            need(self.result['system_timezone_before'] in ('GMT','UTC'),'UNCHANGED_UTC_DEVICE_ZONE_REQUIRED_NO_SET')
            self.before_diag=self.diagnostics.diagnostics('before',10061)
            need(abs(time.time()-self.before_diag['guest_seconds'])<=3,'REMINDER_GUEST_CLOCK_NOT_BOUND')
            self.plan=model.reminder_plan(self.before_diag['guest_seconds'])
            self.lease={**{k:self.plan[k] for k in ('dtstart','dtend')},'calendar_id':-1,'event_id':-1}
            self.result['intended_event']={'title':model.TITLE,**self.plan,'attendees':0}
            self.result['notifications_before']=self.nms.read('baseline')
            need(self.result['notifications_before']['active_calendar_count']==0,'PRESERVE_PREEXISTING_CALENDAR_NOTIFICATION')
            self.phase='FIRST_USE';self.ui.launch();self.observe('first-use-calendar')
        def role_node(self,role,kind,node,value):
            activity=self.obs['focus']['activity']
            need(activity in (m.MAIN,m.EDITOR,m.EDITOR_ALIAS,m.INFO),'EXACT_CALENDAR_ROUTE')
            if role in policy.ROLES:
                need(self.phase=='CREATING' and kind=='tap' and value is None,'REMINDER_PICKER_PHASE')
                if role=='reminder-at-start':need(self.roles.get('reminder-open')==1,'REMINDER_OPEN_ONCE_FIRST')
                target,_=policy.target(role,self.obs);need(node==target,'EXACT_CURRENT_REMINDER_TARGET');return
            if role in ('focus-local-name','local-name'):
                need(self.phase=='FIRST_USE' and node.get('class')=='android.widget.EditText' and
                     node.get('editable') is True and node.get('password') is False and
                     (node.get('hint')=='Calendar name' or node.get('text')=='On this device'),'LOCAL_NAME_FIELD')
                need((role=='focus-local-name' and kind=='tap' and value is None) or
                     (role=='local-name' and kind=='set-text' and value==model.CALENDAR_LABEL),'EXACT_OWNED_LOCAL_NAME')
                return
            need(kind=='tap' and value is None and node.get('clickable') is True,'SINGLE_OBSERVED_TAP')
            labels={'open-new':'New event','local-open':'Create local calendar','local-confirm':'Create',
                    'save-create':'Save','delete-open':'Delete','delete-confirm':'Delete'}
            need(role in labels and (node.get('text')==labels[role] or node.get('content-desc')==labels[role]),
                 'ROLE_LABEL_CHANGED')
            if role=='open-new':need(activity==m.MAIN,'NEW_EVENT_MAIN_REQUIRED')
            elif role in ('delete-open','delete-confirm'):need(activity==m.INFO,'OWNED_DETAIL_REQUIRED')
            else:need(activity in (m.EDITOR,m.EDITOR_ALIAS),'EDITOR_REQUIRED')
            if role=='local-confirm':
                need(self.roles.get('local-name')==1 and node.get('resource-id')=='android:id/button1','LOCAL_CREATE_CONFIRM')
            if role=='save-create':
                need(self.roles.get('reminder-at-start')==1,'UI_REMINDER_SELECTION_REQUIRED')
                self.result['reminder_form_before_save']=policy.selected_form(self.obs,model.TITLE)
                need(time.time()*1000+60000<self.plan['dtstart'],'NATURAL_REMINDER_TOO_CLOSE_NO_SAVE')
                self.model.require_no_event(self.model.read('before-single-save'))
            if role=='delete-confirm':
                need(node.get('resource-id')=='android:id/button1' and
                     any(n.get('resource-id')=='android:id/alertTitle' and n.get('text')=='Delete this event?'
                         for n in self.obs['nodes']),'EXACT_SINGLE_EVENT_DELETE_DIALOG')
        def input_step(self,c):
            need(not self.ui.pending and self.business_pending is None,'UNKNOWN_INPUT_NO_REPLAY')
            need(c.get('view')==self.view_id and self.obs is not None,'LATEST_OBSERVATION_REQUIRED')
            index=c.get('node');need(type(index) is int and 0<=index<len(self.obs['nodes']),'ACTUAL_NODE_INDEX')
            role=c.get('role');kind=c.get('kind','tap');value=c.get('value');node=self.obs['nodes'][index]
            allowed={'FIRST_USE':{'open-new','local-open','focus-local-name','local-name','local-confirm'},
                     'CREATING':{'reminder-open','reminder-at-start','save-create'},
                     'DELETING':{'delete-open','delete-confirm'}}
            need(role in allowed.get(self.phase,set()) and self.roles.get(role,0)==0,'ONE_ROLE_NO_REPLAY')
            self.role_node(role,kind,node,value)
            token='reminder-'+c['id'];business=role in ('local-confirm','save-create','delete-confirm')
            if business:self.business_pending={'role':role,'token':token}
            self.record('role-intent',{'role':role,'phase':self.phase,'token':token,'node':node,'kind':kind,
                                     'value':value,'business_write_expected':business,'automatic_retry':False})
            try:
                if role in policy.ROLES:
                    target,context=policy.target(role,self.obs)
                    if role=='reminder-open':base.FILES=self.obs['focus']['activity']
                    mouse.input(self.ui,self.obs,token,target,role,context,popup=role=='reminder-open')
                else:self.ui.input(self.obs,token,node,kind=kind,value=value)
            except BaseException:
                if token not in self.ui.pending:
                    if business:self.business_pending=None
                else:self.roles[role]=1;self.role_tokens[role]=token
                raise
            self.roles[role]=1;self.role_tokens[role]=token
            self.result['ui_roles'].append({'role':role,'token':token,'kind':kind,'phase':self.phase})
            self.observe('after-'+c['id'])
            if self.sampler is not None:self.sampler.checkpoint('after-owned-input')
        def wait_state(self,kind):
            end=time.monotonic()+35
            for attempt in range(6):
                value=self.model.read('verify-'+kind+'-'+str(attempt+1))
                try:
                    if kind in ('calendar','deleted'):self.model.require_no_event(value)
                    else:self.model.require_event(value,model.TITLE,self.lease['dtstart'],self.lease['dtend'])
                    return value
                except RuntimeError:
                    if attempt==5 or time.monotonic()+15>end:raise
                    time.sleep(.4)
            raise RuntimeError('OWNED_PROVIDER_STATE_NOT_OBSERVED')
        def verify(self,kind):
            if kind=='calendar':
                need(self.phase=='FIRST_USE' and self.roles.get('local-confirm')==1,'EXPLICIT_UI_CALENDAR_CREATE_REQUIRED')
                value=self.wait_state(kind);self.finish_business('local-confirm',value)
                self.lease['calendar_id']=self.model.calendar['_id']
                self.result['fixture_calendar_created_in_ui']=value
                self.phase='CREATING';self.route('insert');return
            if kind=='created':
                need(self.phase=='CREATING' and self.roles.get('save-create')==1,'ONE_UI_SAVE_REQUIRED')
                value=self.wait_state(kind);self.finish_business('save-create',value)
                self.event_id=self.model.event_id;self.lease['event_id']=self.event_id
                self.result['gates']['reminder_set_in_calendar_ui']=value;self.phase='CREATED';return
            if kind=='deleted':
                need(self.phase=='DELETING' and self.roles.get('delete-confirm')==1,'UI_DELETE_REQUIRED')
                value=self.wait_state(kind);self.finish_business('delete-confirm',value)
                self.result['gates']['deleted_in_calendar_ui']=value;self.phase='DELETED';return
            raise RuntimeError('UNREVIEWED_REMINDER_VERIFY')
        def start_runtime(self):
            need(self.sampler is None and not self.ui.pending and self.business_pending is None,'ONE_RUNTIME_OBSERVER')
            self.sampler=runtime.RuntimeEvidence(self.s,self.tx,evidence_root/'runtime','Pocket4_CalendarReminder_'+model.RUN)
            self.sampler.start();self.sampler.phase_changed('before-reminder-save')
        def await_delivery(self):
            need(self.phase=='CREATED' and self.sampler is not None and not self.ui.pending and self.business_pending is None,'CONFIRMED_SAVE_BEFORE_CLOSE')
            self.ui.close_all();need(self.ui.removals==len(self.ui.closed)==1 and not self.ui.owned,'ONE_NORMAL_CLOSE')
            self.ui.check_tasks('closed-wait-baseline');self.sampler.phase_changed('closed-await-natural-delivery')
            value=self.wait_state('created');self.result['closed_event_persistence']=value
            observations=[];finish=self.plan['latest_due_readback_ms']
            for attempt in range(72):
                need(time.time()*1000<=finish,'NATURAL_REMINDER_DELIVERY_DEADLINE')
                self.ui.check_tasks('closed-reminder-wait-'+str(attempt))
                self.diag_chain.checkpoint('reminder-wait-'+str(attempt))
                self.sampler.checkpoint('natural-wait-readback')
                value=self.model.read('await-'+str(attempt));self.model.require_event(value,model.TITLE,self.lease['dtstart'],self.lease['dtend'])
                rows=value['owned_alerts'];entry={'attempt':attempt,'observed_ms':int(time.time()*1000),'provider':value}
                if rows and rows[0]['state']==1:
                    row=self.model.require_fired(value,self.lease['dtstart'],self.lease['dtend'])
                    notification=self.nms.read('fired-'+str(attempt),row['_id']);entry['notification']=notification
                    if notification['present'] and notification.get('source_bound_uid_channel_title'):
                        self.fired_alert=dict(row);observations.append(entry)
                        self.result['gates']['ordinary_provider_reminder_fired_while_task_closed']=value
                        self.result['gates']['exact_android_notification_delivered']=notification
                        self.result['delivery_observations']=observations
                        self.phase='DELIVERED';self.sampler.phase_changed('delivered-while-task-closed');return
                observations.append(entry);self.result['delivery_observations']=observations
                # Only read-only waiting. No broadcast, launch, set-time or input retry.
                for _ in range(5):
                    if time.time()*1000>finish:break
                    self.s.guard()
                    remaining=self.s.deadline-time.monotonic()
                    need(remaining>0,'ORIGINAL_REMINDER_WORK_DEADLINE_EXPIRED')
                    time.sleep(min(1,remaining))
            raise RuntimeError('REMINDER_READ_BUDGET_EXHAUSTED')
        def delete_owned(self):
            need(self.phase in ('CREATED','DELIVERED') and not self.ui.pending and self.business_pending is None,
                 'NO_UNKNOWN_BEFORE_OWNED_UI_DELETE')
            need(not self.ui.owned and self.ui.removals==1,'FIRST_TASK_ALREADY_NORMALLY_CLOSED')
            value=self.wait_state('created')
            self.sampler.phase_changed('reopen-for-owned-reminder-delete')
            self.ui.launch();self.route('view')
            need(self.obs['focus']['activity']==m.INFO and
                 any(n.get('text')==model.TITLE for n in self.obs['nodes']) and
                 any(n.get('text')=='Reminders: 1' for n in self.obs['nodes']),
                 'EXACT_SAME_EVENT_WITH_REMINDER_DETAIL')
            self.phase='DELETING';return value
        def step(self,c):
            need(isinstance(c,dict) and not set(c)-{'id','op','view','node','kind','value','role'},'REMINDER_COMMAND_SCHEMA')
            ident=c.get('id');need(isinstance(ident,str) and re.fullmatch('[a-z][a-z0-9-]{0,39}',ident)
                 and ident not in self.seen and len(self.seen)<24,'UNIQUE_REMINDER_COMMAND_ID')
            self.seen.add(ident);self.record('command-'+ident,c);op=c.get('op')
            if op=='input':self.input_step(c);return True
            if op in ('verify-calendar','verify-created','verify-deleted'):self.verify(op[7:]);return True
            if op=='runtime-start':self.start_runtime();return True
            if op=='await-delivery':self.await_delivery();return True
            if op=='reopen-delete':self.delete_owned();return True
            if op=='verify-notification-removed':self.verify_notification_removed();return True
            need(op=='finish' and self.phase=='DELETED' and set(self.result['gates'])==REQUIRED and
                 not self.business_pending and not self.ui.pending,'ALL_REMINDER_GATES_REQUIRED')
            self.result['business_scope_completed']=True;return False
        def verify_notification_removed(self):
            need(self.phase=='DELETED' and not self.ui.pending and self.business_pending is None,'UI_DELETE_READBACK_FIRST')
            removed=None
            for attempt in range(6):
                self.model.require_no_event(self.model.read('deleted-notification-'+str(attempt)))
                removed=self.nms.read('deleted-'+str(attempt),self.fired_alert['_id'] if self.fired_alert else None)
                if removed['active_calendar_count']==0:
                    self.result['gates']['owned_notification_removed_after_ui_delete']=removed;return
                if attempt<5:time.sleep(.5)
            raise RuntimeError('CALENDAR_NOTIFICATION_REMAINS_AFTER_OWNED_DELETE')
        def arm_cleanup_remaining(self):
            need(self.s.phase_name=='final_cleanup' and self.cleanup_deadline==self.s.deadline,
                 'ONE_ACTUAL_ABSOLUTE_CLEANUP_PHASE_REQUIRED')
            need(self.cleanup_deadline-time.monotonic()>0,'REMINDER_CLEANUP_DEADLINE_EXPIRED')
            self.s.guard()
        def cleanup(self):
            result={'errors':[],'calendar_removed':False,'provider_baseline_restored':False}
            try:
                self.arm_cleanup_remaining()
                need(not self.business_pending,'UNKNOWN_BUSINESS_RETAIN_OWNED_TASK')
                self.ui.close_all()
            except BaseException as exc:result['errors'].append('owned-task:'+type(exc).__name__+':'+str(exc))
            try:
                self.arm_cleanup_remaining()
                need(not self.ui.owned and not self.ui.pending and not self.business_pending and not self.cleanup_pending,
                    'UNKNOWN_EFFECT_RETAIN_OWNED_FIXTURE')
                value=self.model.read('before-empty-calendar-cleanup')
                if self.model.calendar is None:
                    self.model.require_empty(value);result['calendar_removed']=True
                else:
                    self.model.require_no_event(value)
                    need('deleted_in_calendar_ui' in self.result['gates'] or self.roles.get('save-create',0)==0,
                        'EVENT_UI_DELETE_NOT_VERIFIED_RETAIN_FIXTURE')
                    uri,where=self.model.deletion_request()
                    need(self.shell_grants()==self.result['existing_shell_calendar_permissions'],
                         'SHELL_CALENDAR_GRANTS_CHANGED')
                    argv=['/system/bin/content','query','--user','0','--uri',uri,'--projection','_id','--where',where]
                    raw=self.s.android(argv,15).decode()
                    need(raw=='Row: 0 _id='+str(self.model.calendar['_id'])+'\n','FRESH_GUARDED_CALENDAR_NOT_UNIQUE')
                    # Same actual provider collection DELETE path already proved
                    # to re-evaluate this complete empty predicate transactionally.
                    self.ui.check_tasks('before-empty-calendar-cleanup')
                    request=['/system/bin/content','delete','--user','0','--uri',uri,'--where',where]
                    self.record('empty-calendar-cleanup-intent',{'argv':request,'calendar':self.model.calendar,
                        'expected_events':0,'automatic_retry':False,
                        'provider_internal_side_effect':'May schedule unsubscribe for this same unregistered LOCAL account; no external account or sync API is used.'})
                    self.arm_cleanup_remaining()
                    self.cleanup_pending=True;self.cleanup_calls+=1
                    output=self.s.android(request,20).decode();self.record('empty-calendar-cleanup-ack',{'stdout':output})
                    value=self.model.read('after-empty-calendar-cleanup');self.model.require_empty(value)
                    self.cleanup_pending=False;result['calendar_removed']=True
                result['provider_baseline_restored']=True
            except BaseException as exc:result['errors'].append('fixture:'+type(exc).__name__+':'+str(exc))
            return result
    return ReminderFlow
