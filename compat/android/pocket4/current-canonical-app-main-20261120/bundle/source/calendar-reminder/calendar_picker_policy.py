"""Private reminder spinner decisions; preserve the existing native mouse transaction fences."""
PACKAGE='com.android.calendar'
EDITORS={PACKAGE+'.event.EditEventActivity',PACKAGE+'.EditEventActivity'}
ROLES={'reminder-open','reminder-at-start'}
def need(v,reason):
    if not v:raise RuntimeError(reason)
def inside(outer,inner):
    return (isinstance(outer,list) and isinstance(inner,list) and len(outer)==len(inner)==4 and
            all(type(v) is int for v in outer+inner) and
            outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3])
def one(nodes,check,reason):
    hits=[n for n in nodes if n.get('package')==PACKAGE and n.get('visible') is True and check(n)]
    need(len(hits)==1,reason);return hits[0]
def selected(nodes,label):
    child=one(nodes,lambda n:n.get('class')=='android.widget.CheckedTextView' and
        n.get('resource-id')=='android:id/text1' and n.get('text')==label and n.get('enabled') is True,
        'EXACT_REMINDER_SELECTED_TEXT')
    spinner=one(nodes,lambda n:n.get('class')=='android.widget.Spinner' and
        n.get('enabled') is True and n.get('clickable') is True and inside(n.get('bounds_array'),child.get('bounds_array')),
        'EXACT_REMINDER_SPINNER')
    caption=one(nodes,lambda n:n.get('class')=='android.widget.TextView' and n.get('text')=='Reminder',
        'REMINDER_CAPTION_REQUIRED')
    need(child['window_id']==spinner['window_id']==caption['window_id'],'REMINDER_CROSS_WINDOW')
    return child,[spinner,caption]
def target(role,obs):
    need(role in ROLES and obs['focus']['package']==PACKAGE and obs['focus']['activity'] in EDITORS,
         'OWNED_REMINDER_EDITOR_REQUIRED')
    nodes=obs['nodes']
    if role=='reminder-open':
        need(obs['focus'].get('popup') is False,'REMINDER_POPUP_PREEXISTED')
        return selected(nodes,'No reminder')
    need(obs['focus'].get('popup') is True,'ACKNOWLEDGED_REMINDER_POPUP_REQUIRED')
    leaf=one(nodes,lambda n:n.get('class')=='android.widget.CheckedTextView' and
        n.get('resource-id')=='android:id/text1' and n.get('text')=='At start time' and
        n.get('enabled') is True and n.get('checked') is False and type(n.get('clickable')) is bool,
        'ONE_OBSERVED_AT_START_OPTION_REQUIRED')
    listing=one(nodes,lambda n:n.get('class')=='android.widget.ListView' and
        inside(n.get('bounds_array'),leaf.get('bounds_array')),'EXACT_REMINDER_OPTIONS_LIST')
    need(leaf['window_id']==listing['window_id'],'REMINDER_OPTION_CROSS_WINDOW')
    # This is a physical mouse transaction; clickable is recorded as actually
    # observed and compared in both complete native node identities, not assumed.
    return leaf,[listing]
def selected_form(obs,title):
    need(obs['focus']['package']==PACKAGE and obs['focus']['activity'] in EDITORS and not obs['focus'].get('popup'),
         'OWNED_REMINDER_FORM_REQUIRED')
    one(obs['nodes'],lambda n:n.get('class')=='android.widget.EditText' and n.get('hint')=='Title'
        and n.get('text')==title,'EXACT_OWNED_REMINDER_TITLE')
    leaf,context=selected(obs['nodes'],'At start time')
    return {'title':title,'reminder_label':leaf['text'],'source_bound_minutes':0,
            'selected_native_node':leaf,'context_nodes':context}
