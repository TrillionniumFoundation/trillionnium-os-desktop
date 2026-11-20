"""Finite actual Calendar reminder UI decisions. No external command queue or input replay."""
DELIVERY_DEADLINES={'NATURAL_REMINDER_DELIVERY_DEADLINE','REMINDER_READ_BUDGET_EXHAUSTED'}
def run(flow,model):
    sequence=0
    def command(op,**values):
        nonlocal sequence
        sequence+=1
        if sequence>24:raise RuntimeError('REMINDER_COMMAND_BUDGET')
        request={'id':'reminder-'+str(sequence).zfill(2)+'-'+op,'op':op,**values}
        flow.record('local-driver-decision',{'request':request,'automatic_retry':False})
        flow.diag_chain.checkpoint('before-'+request['id'])
        result=flow.step(request)
        flow.diag_chain.checkpoint('after-'+request['id'])
        return result
    def node(role,target,kind='tap',value=None):
        matches=[i for i,n in enumerate(flow.obs['nodes']) if n is target]
        if len(matches)!=1:raise RuntimeError('ONE_CURRENT_REMINDER_NODE:'+role)
        values={'view':flow.view_id,'node':matches[0],'role':role,'kind':kind}
        if value is not None:values['value']=value
        if command('input',**values) is not True:raise RuntimeError('INPUT_STEP_TERMINATED')
    def exact(role,fields,kind='tap',value=None):
        if flow.obs is None:raise RuntimeError('CURRENT_OBSERVATION_REQUIRED')
        matches=[n for n in flow.obs['nodes'] if n.get('enabled') is True and n.get('clickable') is True and
                 all(n.get(k)==v for k,v in fields.items())]
        if len(matches)!=1:raise RuntimeError('ONE_CURRENT_REMINDER_ROLE:'+role)
        node(role,matches[0],kind,value)
    def button(role,text,positive=False):
        fields={'class':'android.widget.Button','text':text}
        if positive:fields['resource-id']='android:id/button1'
        exact(role,fields)
    def local_name(role,kind='tap',value=None):
        fields={'class':'android.widget.EditText','hint':'Calendar name','text':'On this device',
                'editable':True,'password':False}
        if kind=='set-text':fields['focused']=True
        exact(role,fields,kind,value)

    exact('open-new',{'class':'android.widget.Button','content-desc':'New event'})
    button('local-open','Create local calendar')
    local_name('focus-local-name')
    local_name('local-name','set-text',model.CALENDAR_LABEL)
    button('local-confirm','Create',True)
    command('verify-calendar')
    for role in ('reminder-open','reminder-at-start'):
        target,_=flow.policy.target(role,flow.obs);node(role,target)
    command('runtime-start')
    button('save-create','Save');command('verify-created')
    delivery_failure=None
    try:command('await-delivery')
    except RuntimeError as exc:
        # These two read-only deadline outcomes occur only after exact Save and
        # one normal close. Other failures, all input/close unknowns, and
        # LeaseExpired (BaseException) propagate without any next action.
        if str(exc) not in DELIVERY_DEADLINES:raise
        if flow.ui.pending or flow.business_pending is not None or flow.ui.owned or flow.ui.removals!=1:raise
        delivery_failure=type(exc).__name__+':'+str(exc)
        flow.result['delivery_error']=delivery_failure
        flow.record('delivery-deadline-with-owned-row-retained',{'error':delivery_failure,
            'next_action':'fresh exact owned event proof followed by its real Calendar UI Delete',
            'broadcasts_or_input_replayed':False})
    command('reopen-delete')
    button('delete-open','Delete');button('delete-confirm','Delete',True)
    command('verify-deleted');command('verify-notification-removed')
    if delivery_failure is None:
        if command('finish') is not False:raise RuntimeError('EXACT_REMINDER_FINISH_REQUIRED')
    flow.result['local_driver']={'commands':sequence,'automatic_retry':False,
        'transport_roundtrips_per_decision':0,'maximum_commands':24,
        'selected_from_current_observations':True,'diagnostics_contiguous_segments':True,
        'event_saves':1,'replayed_saves':0,'event_ui_delete_confirmations':1}
