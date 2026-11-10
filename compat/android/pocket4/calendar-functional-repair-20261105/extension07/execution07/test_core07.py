#!/usr/bin/python3
"""Host-only tests of actual SQL, owner guards and actual adapter/controller methods.
These are not Android, ART, Calendar UI or provider integration qualification.
"""
import copy, importlib.util, json, sqlite3, types, unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m);return m

reader=load('reader','read_owned_calendar07.py')
core=load('core','calendar_accept_core07.py')
adapter=load('adapter','calendar_ui07.py')


def db_fixture(calendar=True,event=False):
    db=sqlite3.connect(':memory:')
    for table,columns in [('Calendars',reader.CALENDAR_COLUMNS),('Events',reader.EVENT_COLUMNS)]:
        ints={'_id','calendar_id','dtstart','dtend','allDay','hasAlarm','deleted','calendar_access_level','visible','sync_events'}
        db.execute('CREATE TABLE '+table+' ('+','.join(c+(' INTEGER' if c in ints else ' TEXT') for c in columns)+')')
    for table in reader.TABLES[2:]:db.execute('CREATE TABLE '+table+' (_id INTEGER,event_id INTEGER)')
    cal=dict(zip(reader.CALENDAR_COLUMNS,[11,reader.ACCOUNT,'LOCAL',
        'droidloom-local-12345678-1234-1234-1234-123456789012',reader.CALENDAR_LABEL,reader.ACCOUNT,700,1,1,'UTC']))
    row=dict(zip(reader.EVENT_COLUMNS,[22,11,reader.TITLE,2000000000000,2000002700000,None,'UTC',0,
        None,None,None,None,0,0,None]))
    if calendar:db.execute('INSERT INTO Calendars VALUES ('+','.join('?' for _ in cal)+')',tuple(cal.values()))
    if event:db.execute('INSERT INTO Events VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
    db.commit();return db,cal,row


def observe(db):
    result=None
    for sql in reader.observation_sql().split(';'):
        if sql.strip():
            cursor=db.execute(sql)
            if cursor.description:result=json.loads(cursor.fetchone()[0])
    db.execute('PRAGMA query_only=OFF')
    return result


class OwnedSqlTests(unittest.TestCase):
    def test_production_sql_empty_first_use(self):
        db,_,_=db_fixture(False);value=reader.validate_projection(observe(db))
        reader.Model.require_empty(value);db.close()

    def test_actual_projection_binds_single_event_and_identity(self):
        db,cal,event=db_fixture(event=True);value=reader.validate_projection(observe(db))
        model=reader.Model(None,None);model.require_event(value,reader.TITLE,event['dtstart'],event['dtend'])
        self.assertEqual(model.calendar,cal);self.assertEqual(model.event_id,22)
        bad=copy.deepcopy(value);bad['events'][0]['_id']=23
        with self.assertRaisesRegex(RuntimeError,'UI_EVENT_ID_CHANGED'):
            model.require_event(bad,reader.TITLE,event['dtstart'],event['dtend'])
        db.close()

    def test_foreign_row_counted_but_contents_not_selected(self):
        db,_,_=db_fixture(False)
        db.execute("INSERT INTO Calendars (_id,calendar_displayName,account_name) VALUES (1,'PRIVATE LABEL','PRIVATE ACCOUNT')");db.commit()
        value=observe(db);self.assertNotIn('PRIVATE',json.dumps(value));self.assertEqual(value['counts']['Calendars'],1)
        with self.assertRaisesRegex(RuntimeError,'NON_OWNED_PROVIDER_ROWS_APPEARED'):reader.validate_projection(value)
        db.close()

    def test_multiple_owned_rows_rejected(self):
        db,cal,_=db_fixture();cal['_id']=12
        db.execute('INSERT INTO Calendars VALUES ('+','.join('?' for _ in cal)+')',tuple(cal.values()));db.commit()
        with self.assertRaisesRegex(RuntimeError,'ONE_OWNED_CALENDAR_EVENT_MAX'):reader.validate_projection(observe(db))
        db.close()

    def test_same_calendar_id_owner_drift_rejected(self):
        db,_,_=db_fixture();model=reader.Model(None,None);value=observe(db);model.bind_calendar(value)
        value['calendars'][0]['calendar_timezone']='Asia/Tokyo'
        with self.assertRaisesRegex(RuntimeError,'OWNED_CALENDAR_IDENTITY_CHANGED'):model.bind_calendar(value)
        db.close()

    def test_final_delete_predicate_blocks_new_event_and_rechecks_owner(self):
        db,cal,event=db_fixture(event=True);model=reader.Model(None,None);model.bind_calendar(observe(db))
        uri,predicate=model.deletion_request();self.assertIn('caller_is_syncadapter=true',uri)
        self.assertEqual(db.execute('DELETE FROM Calendars WHERE '+predicate).rowcount,0)
        db.execute('DELETE FROM Events');db.execute("UPDATE Calendars SET ownerAccount='changed'")
        self.assertEqual(db.execute('DELETE FROM Calendars WHERE '+predicate).rowcount,0)
        db.execute('UPDATE Calendars SET ownerAccount=?',(cal['ownerAccount'],))
        self.assertEqual(db.execute('DELETE FROM Calendars WHERE '+predicate).rowcount,1)
        self.assertEqual(db.execute('DELETE FROM Calendars WHERE '+predicate).rowcount,0);db.close()

    def test_child_rows_prevent_empty_cleanup_and_event_qualification(self):
        db,_,event=db_fixture(event=True);db.execute('INSERT INTO Reminders VALUES (33,22)');db.commit()
        model=reader.Model(None,None);value=observe(db)
        with self.assertRaisesRegex(RuntimeError,'UNEXPECTED_EVENT_CHILD_ROWS'):
            model.require_event(value,reader.TITLE,event['dtstart'],event['dtend'])
        db.execute('DELETE FROM Events');db.commit();value=observe(db)
        with self.assertRaisesRegex(RuntimeError,'OWNED_EVENT_OR_CHILD_ROWS_REMAIN'):model.require_no_event(value)
        db.close()


class Helper:
    def __init__(self,nodes,outcome='success'):
        self.nodes=nodes;self.dispatched=[];self.frames=0;self.outcome=outcome
    def capture(self,request):self.frames+=1;return {}
    def validate_snapshot(self,request,frame):pass
    def ui(self,request):return {'ok':True,'accessibility_mode_restoration_verified':True,'nodes':copy.deepcopy(self.nodes)}
    def dispatch(self,request):
        self.dispatched.append(request)
        if self.outcome=='unknown':raise RuntimeError('transport-after-input')
        if request['op']=='set-text':return {'ok':True,'performed':'set-text','readback_verified':True,'password':False}
        return {'ok':True,'performed':request['op'],'target':{},'actual_target':{}}


def adapter_case(nodes,outcome='success'):
    a=adapter.Adapter.__new__(adapter.Adapter)
    a.actions=0;a.pending={};a.popup_grant=None;a.allow_new=None;a.recorded=[]
    a.check_tasks=lambda label:None;a.record=lambda label,v:a.recorded.append((label,v))
    f={'package':'com.android.calendar','activity':'com.android.calendar.event.EditEventActivity','window_token':'abc','task':1}
    a.focus=lambda:dict(f);helper=Helper(nodes,outcome)
    a.s=types.SimpleNamespace(helper=helper,guard=lambda:None)
    obs={'focus':f,'nodes':copy.deepcopy(nodes),'screenshot':{'scope':{'package':'com.android.calendar','window_token':'abc'},
        'scope_bounds':[0,0,500,500],'frame_sha256':'a'*64,'scope_sha256':'b'*64,'context_token':'c'}}
    return a,obs,helper


def field(focused=True,window=1):return {'package':'com.android.calendar','class':'android.widget.EditText',
    'resource-id':'','text':'','hint':'Title','enabled':True,'editable':True,'password':False,'focused':focused,
    'bounds_array':[10,10,300,70],'window_id':window}


class AdapterBoundaryTests(unittest.TestCase):
    def test_focused_field_disambiguates_blank_fields_and_preserves_full_node(self):
        a,obs,h=adapter_case([field(),dict(field(False),hint='Location',bounds_array=[10,80,300,140])])
        node=obs['nodes'][0];h.nodes[0]['window_id']=2;h.nodes[1]['window_id']=2
        a.input(obs,'once',node,'set-text',reader.UNSAVED)
        self.assertEqual(h.dispatched[0]['selector']['focused'],True);self.assertEqual(h.frames,2)
        self.assertTrue(a.pending['once']['input_acknowledged'])

    def test_full_node_change_stops_before_input(self):
        a,obs,h=adapter_case([field()]);h.nodes[0]['hint']='Location'
        with self.assertRaisesRegex(RuntimeError,'FULL_EDITOR_NODE_CHANGED_BEFORE_TEXT'):
            a.input(obs,'once',obs['nodes'][0],'set-text',reader.UNSAVED)
        self.assertEqual(h.dispatched,[]);self.assertEqual(a.pending,{})

    def test_two_focused_fields_fail_without_input(self):
        a,obs,h=adapter_case([field(),dict(field(),hint='Location')])
        with self.assertRaisesRegex(RuntimeError,'FULL_EDITOR_NODE_CHANGED_BEFORE_TEXT'):
            a.input(obs,'once',obs['nodes'][0],'set-text',reader.UNSAVED)
        self.assertEqual(h.dispatched,[])

    def test_scroll_requires_unique_full_observed_container(self):
        node=dict(field(),**{'class':'android.widget.ScrollView','editable':False,'scrollable':True,'bounds_array':[0,0,500,500]})
        a,obs,h=adapter_case([node]);a.input(obs,'scroll-once',obs['nodes'][0],'scroll-forward')
        self.assertEqual(h.dispatched[0]['selector'],{'package':'com.android.calendar','class':'android.widget.ScrollView','scrollable':True,'enabled':True})
        self.assertTrue(a.pending['scroll-once']['input_acknowledged'])

    def test_unknown_input_retains_pending_and_blocks_replay(self):
        a,obs,h=adapter_case([field()],'unknown')
        with self.assertRaisesRegex(RuntimeError,'transport-after-input'):
            a.input(obs,'once',obs['nodes'][0],'set-text',reader.UNSAVED)
        with self.assertRaisesRegex(RuntimeError,'PENDING_INPUT_NOT_REPLAYABLE'):
            a.input(obs,'different-token',obs['nodes'][0],'set-text',reader.UNSAVED)
        self.assertEqual(len(h.dispatched),1);self.assertIn('once',a.pending)


def controller_case():
    m=types.SimpleNamespace(Flow=object,CALENDAR='com.android.calendar',MAIN='main',INFO='info',EDITOR='editor',EDITOR_ALIAS='alias')
    cls=core.flow_class(m,reader,types.SimpleNamespace(),None);flow=cls.__new__(cls)
    flow.business_pending={'role':'save-create','token':'one'}
    flow.ui=types.SimpleNamespace(pending={'one':{'kind':'tap','input_acknowledged':False}})
    flow.logs=[];flow.record=lambda label,value:flow.logs.append((label,value));return flow


class ControllerBoundaryTests(unittest.TestCase):
    def test_business_reconciliation_requires_exact_role_and_keeps_original_receipt(self):
        flow=controller_case()
        with self.assertRaisesRegex(RuntimeError,'EXACT_PENDING_BUSINESS_ROLE_REQUIRED'):
            flow.finish_business('delete-confirm',{'event_absent':True})
        self.assertIn('one',flow.ui.pending)
        flow.finish_business('save-create',{'exact_owned_event_id':22})
        self.assertIsNone(flow.business_pending);self.assertEqual(flow.ui.pending,{})
        self.assertFalse(flow.logs[0][1]['action_replayed']);self.assertFalse(flow.logs[0][1]['original_ack_rewritten'])

    def test_business_readback_does_not_clear_another_unknown_input(self):
        flow=controller_case();flow.ui.pending['two']={'kind':'intent'}
        with self.assertRaisesRegex(RuntimeError,'ANOTHER_INPUT_STILL_PENDING'):
            flow.finish_business('save-create',{'exact_owned_event_id':22})
        self.assertIn('two',flow.ui.pending);self.assertIsNotNone(flow.business_pending)

if __name__=='__main__':unittest.main(verbosity=2)
