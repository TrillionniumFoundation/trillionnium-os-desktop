#!/usr/bin/python3 -I
"""Private, read-only proof of this one Calendar UI run; no account enumeration."""
from pathlib import Path
import hashlib, json, os, re, stat
from urllib.parse import urlencode,quote as url_quote

RUN='calendar-core12-4d958c110b6e7a2f'
CALENDAR_LABEL='Pocket4 Calendar QA '+RUN
TITLE='Pocket4 event '+RUN
EDITED=TITLE+' Edited'
UNSAVED=TITLE+' Not saved'
ACCOUNT='Droidloom local calendars'
DB='/data/user/0/com.android.providers.calendar/databases/calendar.db'
TABLES=('Calendars','Events','Reminders','Attendees','Instances','CalendarAlerts',
        'EventsRawTimes','ExtendedProperties')
CALENDAR_COLUMNS=('_id','account_name','account_type','name','calendar_displayName','ownerAccount',
                  'calendar_access_level','visible','sync_events','calendar_timezone')
EVENT_COLUMNS=('_id','calendar_id','title','dtstart','dtend','duration','eventTimezone','allDay',
               'rrule','rdate','exrule','exdate','hasAlarm','deleted','_sync_id')

def need(value,reason):
    if not value: raise RuntimeError(reason)

def quote(value): return "'"+str(value).replace("'","''")+"'"
def fp(info):return {k:getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_gid','st_mode')}

def owner_where():
    return ' AND '.join(k+'='+quote(v) for k,v in {
        'account_name':ACCOUNT,'account_type':'LOCAL','ownerAccount':ACCOUNT,
        'calendar_displayName':CALENDAR_LABEL}.items())

def json_rows(table,columns,where):
    values=','.join(quote(c)+','+c for c in columns)
    return ('(SELECT json_group_array(json_object('+values+')) FROM (SELECT '+','.join(columns)+
        ' FROM '+table+' WHERE '+where+' ORDER BY _id LIMIT 2))')

def observation_sql():
    where=owner_where();event_where='calendar_id IN (SELECT _id FROM Calendars WHERE '+where+')'
    counts="json_object("+','.join(quote(t)+',(SELECT COUNT(*) FROM '+t+')' for t in TABLES)+")"
    return ('PRAGMA query_only=ON;BEGIN;SELECT json_object(\'counts\','+counts+
        ',\'calendars\',json('+json_rows('Calendars',CALENDAR_COLUMNS,where)+')'+
        ',\'events\',json('+json_rows('Events',EVENT_COLUMNS,event_where)+')) AS payload;ROLLBACK;')

def validate_projection(value):
    need(set(value)=={'counts','calendars','events'} and set(value['counts'])==set(TABLES),'PROVIDER_RECORD_SHAPE')
    need(all(type(n) is int and n>=0 for n in value['counts'].values()),'PROVIDER_COUNTS_INVALID')
    need(isinstance(value['calendars'],list) and len(value['calendars'])<=1 and
         isinstance(value['events'],list) and len(value['events'])<=1,'ONE_OWNED_CALENDAR_EVENT_MAX')
    need(value['counts']['Calendars']==len(value['calendars']) and
         value['counts']['Events']==len(value['events']),'NON_OWNED_PROVIDER_ROWS_APPEARED')
    return value

class Model:
    def __init__(self,session,record):
        self.s,self.record=session,record
        self.birth=None;self.calendar=None;self.event_id=None;self.sequence=0

    def read(self,label):
        self.s.guard();fd=self.s.target.open_root(DB,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and info.st_uid==10017,'CALENDAR_DB_IDENTITY')
            birth=fp(info)
        finally:os.close(fd)
        if self.birth is None:self.birth=birth
        need(birth==self.birth,'CALENDAR_DATABASE_REPLACED')
        sql=observation_sql()
        args=['/system/bin/env','-i']+[k+'='+self.s.environment[k] for k in sorted(self.s.environment)]
        args+=['/system/bin/timeout','-k','2','10','/system/bin/sqlite3','-readonly','-json',DB,sql]
        self.sequence+=1
        with self.s.target.entry(args) as (command,fds):reply=self.s.run_host('calendar-owned-read',command,14,fds)
        need(reply['rc']==0 and reply['joined'] and not reply['timed_out'],'OWNED_PROVIDER_READ_FAILED')
        outer=json.loads(reply['stdout']);need(len(outer)==1 and set(outer[0])=={'payload'},'PROVIDER_READ_SHAPE')
        value=json.loads(outer[0]['payload'])
        # Only the exact unique marker is read. Unexpected non-owned rows are
        # counted and stop the run; their content is never selected or exported.
        validate_projection(value)
        fd=self.s.target.open_root(DB,os.O_RDONLY|os.O_NOFOLLOW)
        try:need(fp(os.fstat(fd))==self.birth,'DB_CHANGED_DURING_READ')
        finally:os.close(fd)
        self.s.guard();self.record('owned-read-'+label,{'db_identity':self.birth,'value':value})
        return value

    @staticmethod
    def require_empty(value):
        need(not value['calendars'] and not value['events'] and
             all(n==0 for n in value['counts'].values()),'ZERO_PROVIDER_BASELINE_REQUIRED')

    def bind_calendar(self,value):
        need(len(value['calendars'])==1,'ONE_UI_CREATED_LOCAL_CALENDAR_REQUIRED')
        row=value['calendars'][0]
        need(set(row)==set(CALENDAR_COLUMNS) and type(row['_id']) is int and row['_id']>0,'CALENDAR_ROW_SCHEMA')
        need(row['account_name']==row['ownerAccount']==ACCOUNT and row['account_type']=='LOCAL' and
             row['calendar_displayName']==CALENDAR_LABEL and
             re.fullmatch(r'droidloom-local-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',row['name']) and
             row['calendar_access_level']==700 and row['visible']==row['sync_events']==1,'LOCAL_CALENDAR_OWNER_DIFFERS')
        if self.calendar is None:self.calendar=dict(row)
        need(row==self.calendar,'OWNED_CALENDAR_IDENTITY_CHANGED')
        return row

    def require_no_event(self,value):
        self.bind_calendar(value)
        need(not value['events'] and value['counts']==dict.fromkeys(TABLES,0)|{'Calendars':1},
             'OWNED_EVENT_OR_CHILD_ROWS_REMAIN')

    def require_event(self,value,title,begin,end):
        self.bind_calendar(value)
        need(len(value['events'])==1,'ONE_COMMITTED_UI_EVENT_REQUIRED')
        event=value['events'][0]
        need(set(event)==set(EVENT_COLUMNS) and type(event['_id']) is int and event['_id']>0 and
             event['calendar_id']==self.calendar['_id'] and event['title']==title and
             event['dtstart']==begin and event['dtend']==end and event['allDay']==0 and
             event['deleted']==0 and event['_sync_id'] is None and event['hasAlarm']==0 and
             all(event[k] in (None,'') for k in ('duration','rrule','rdate','exrule','exdate')),
             'EXACT_OWNED_SINGLE_EVENT_DIFFERS')
        need(all(value['counts'][k]==0 for k in ('Reminders','Attendees','CalendarAlerts','ExtendedProperties')) and
             value['counts']['Instances']<=1 and value['counts']['EventsRawTimes']<=1,
             'UNEXPECTED_EVENT_CHILD_ROWS')
        if self.event_id is None:self.event_id=event['_id']
        need(event['_id']==self.event_id,'UI_EVENT_ID_CHANGED')
        return event

    def deletion_request(self):
        need(self.calendar is not None,'NO_BOUND_OWNED_CALENDAR')
        row=self.calendar;fields=('_id','account_name','account_type','name','calendar_displayName','ownerAccount')
        where=' AND '.join(k+'='+quote(row[k]) for k in fields)
        where+=' AND NOT EXISTS (SELECT 1 FROM Events WHERE calendar_id='+str(row['_id'])+')'
        uri='content://com.android.calendar/calendars?'+urlencode({
            'caller_is_syncadapter':'true','account_name':ACCOUNT,'account_type':'LOCAL'},quote_via=url_quote)
        return uri,where

if __name__=='__main__':
    print('INERT: a reader class only; no device call or provider mutation')
