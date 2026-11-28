"""Comparison-only view of the normal Rust owner's private leaf channel.

This module does not admit a peer, select a Main, or mint business authority.
The normal source-owned Rust invocation creates the sealed descriptor and the
unnamed check endpoint after borrowing its actual Main and PM observations.
A saved document or a standalone Python invocation cannot recreate those Rust
types. Only fixed host Python children inherit the two comparison descriptors;
the mapped namespace helper never receives them.
"""
from contextlib import contextmanager
import array
import base64
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import socket
import stat
import time

ROOT=Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261126-apps-r2')
FACTS_ENV='DROIDLOOM_NATIVE_LEAF_FACTS_FD'
GUARD_ENV='DROIDLOOM_NATIVE_LEAF_GUARD_FD'
MAX_FACTS=262144
SEALS=fcntl.F_SEAL_SEAL|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW|fcntl.F_SEAL_WRITE
# This is a fixed source set, not a prefix permission. It is updated only with
# the reviewed actual host callers; no descriptor is inherited by Android.
UI_CHILDREN=frozenset({
    str(ROOT/'source/support/business_ui_entry.py'),
    str(ROOT/'source/clock-support/business_ui_entry.py'),
})
CLOCK_CHILD=str(ROOT/'source/clock/clock_entry.py')
IHG_CHILD=str(ROOT/'source/ihg/app_entry.py')
CAMERA_CHILD=str(ROOT/'source/camera-photo/camera_entry.py')
HOST_CHILDREN=UI_CHILDREN|{CLOCK_CHILD,IHG_CHILD,CAMERA_CHILD}
NORMAL_PROGRAMS={
    'manager':'/usr/lib/droidloom/production/current/droidloomd',
    'presenter':'/usr/bin/droidloom-wayland',
}
META=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')

def need(value,code):
    if not value:raise RuntimeError(code)
def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def parse(raw):
    def pairs(items):
        out={}
        for key,value in items:
            need(key not in out,'DUPLICATE_NATIVE_LEAF_CHANNEL_FIELD');out[key]=value
        return out
    def bad(_):raise RuntimeError('NONFINITE_NATIVE_LEAF_CHANNEL_FIELD')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
def metadata(fd):return tuple(getattr(os.fstat(fd),key) for key in META)
def number(value,minimum=0,maximum=2**64-1):
    return type(value) is int and minimum<=value<=maximum

def validate_core(core):
    need(type(core) is dict and set(core)=={
        'schema','application','main','data','peer','comparison_only',
        'account_contents_read','business_acceptance_evaluated'} and
        core['schema']=='droidloom.native-leaf-baseline.v1' and
        core['comparison_only'] is True and core['account_contents_read'] is False and
        core['business_acceptance_evaluated'] is False,'EXACT_ACTUAL_NATIVE_LEAF_COMPARISON_REQUIRED')
    app,main,data,peer=(core[key] for key in ('application','main','data','peer'))
    need(type(app) is dict and type(main) is dict and type(data) is dict and type(peer) is dict and
        main.get('schema')=='droidloom.runtime-main-custody.v1' and
        data.get('schema')=='droidloom.native-leaf-data.v1','EXACT_NORMAL_MAIN_AND_DATA_SCHEMAS')
    need(app['epoch']==main['epoch'] and app['package']==data['package'] and
        app['user']==data['user']==0 and app['uid']==data['android_uid'] and
        number(app['uid'],1,99999) and number(app['version_code'],1) and
        isinstance(app['apks'],list) and 0<len(app['apks'])<=64,
        'SAME_ACTUAL_PACKAGE_MAIN_AND_WORKING_DATA_REQUIRED')
    need(peer['boot_id']==main['epoch']['boot_id'] and
        peer['pid']>1 and peer['systemd_invocation_checked'] is False and
        data['framework_root']==main['framework']['root'] and
        data['user_namespace']==main['persistent_data']['user_namespace'] and
        type(main['persistent_data'].get('original_copy_origin')) is dict,
        'NORMAL_OWNER_AND_ORIGINAL_WORKING_LINEAGE_REQUIRED')
    need(type(data['directories']) is list and len(data['directories'])==4 and
        [row['path'] for row in data['directories']]==[
            '/data/user/0','/data/user_de/0',
            '/data/user/0/'+app['package'],'/data/user_de/0/'+app['package']] and
        all(row['device']==data['data_root']['device'] for row in data['directories']) and
        all(row['host_uid']==data['mapped_host_uid'] for row in data['directories'][2:]) and
        data['directories'][2]['inode']!=data['directories'][3]['inode'],
        'EXACT_TARGET_ONLY_CE_DE_METADATA_REQUIRED')
    release=main.get('normal_host_release')
    need(type(release) is dict and set(release)=={'schema','manager','presenter'} and
         release['schema']=='droidloom.normal-host-release.v1',
         'ACTUAL_NORMAL_HOST_RELEASE_REQUIRED')
    for role,path in NORMAL_PROGRAMS.items():
        pin=release[role]
        need(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and pin['path']==path and
             number(pin['bytes'],64,128*1024*1024) and type(pin['sha256']) is str and
             re.fullmatch('[0-9a-f]{64}',pin['sha256']),
             'EXACT_SELECTED_NORMAL_HOST_PROGRAM_REQUIRED')
    need(release['manager']['sha256']!=release['presenter']['sha256'] and
         release['manager']['bytes']==peer['executable_bytes'] and
         release['manager']['sha256']==peer['executable_sha256'],
         'NORMAL_SELECTED_MANAGER_AND_ACTUAL_PEER_MUST_MATCH')
    return core


def inventory_table(value,core,*,fixture=False):
    """Validate comparison data only; the actual token stays in the Rust owner."""
    if value is None:
        need(core['application']['package']!='com.ihg.apps.android',
             'IHG_REQUIRES_COMPLETE_ACTUAL_USER0_INVENTORY')
        return None
    need((core['application']['package']=='com.ihg.apps.android' or (fixture and core['application']['package'] in ('com.android.documentsui','com.android.gallery3d'))) and
         type(value) is dict and set(value)=={'schema','epoch','records','records_sha256',
             'stdout_bytes','stdout_sha256','query_receipt','comparison_only'} and
         value['schema']=='droidloom.user-zero-package-inventory.v1' and
         value['epoch']==core['main']['epoch'] and value['comparison_only'] is True and
         type(value['records']) is list and 1<=len(value['records'])<=2048 and
         number(value['stdout_bytes'],1,65536) and
         all(type(value[k]) is str and re.fullmatch('[0-9a-f]{64}',value[k])
             for k in ('stdout_sha256','records_sha256')),
         'EXACT_COMPLETE_USER0_INVENTORY_COMPARISON_REQUIRED')
    rows=value['records'];names=[];records={};size=0
    for row in rows:
        need(type(row) is dict and set(row)=={'package','uid'} and
             type(row['package']) is str and 1<=len(row['package'])<=255 and
             (row['package']=='android' or ('.' in row['package'] and
                 all(re.fullmatch('[A-Za-z0-9_]+',p) for p in row['package'].split('.')))) and
             number(row['uid'],0,99999),
             'COMPLETE_USER0_INVENTORY_ROW_DIFFERS')
        name,uid=row['package'],row['uid'];need(name not in records,'DUPLICATE_USER0_PACKAGE')
        names.append(name);records[name]=uid
        size+=len(('package:'+name+' uid:'+str(uid)+'\n').encode())
    need(names==sorted(names) and size==value['stdout_bytes'] and
         sha(canonical(rows))==value['records_sha256'] and
         records.get(core['application']['package'])==core['application']['uid'],
         'COMPLETE_USER0_INVENTORY_BODY_OR_TARGET_DIFFERS')
    r=value['query_receipt'];life=r.get('lifecycle',{}) if type(r) is dict else {}
    io=life.get('stdio_creator',{}) if type(life) is dict else {}
    need(type(r) is dict and set(r)=={'schema','lifecycle','query_pid','query_waitid_code',
         'query_waitid_status','exec','output_bytes','output_sha256','elapsed_millis','cgroup_removed'} and
         r['schema']==2 and number(r['query_pid'],2,2**32-1) and
         r['query_waitid_code']==1 and r['query_waitid_status']==0 and
         r['cgroup_removed'] is True and type(r['exec']) is dict and
         r['output_bytes']==value['stdout_bytes'] and r['output_sha256']==value['stdout_sha256'] and
         type(life) is dict and set(life)=={'owner','factory_pid','factory_tid','factory_pidfd_device',
             'factory_pidfd_inode','query_pidfd_device','query_pidfd_inode','stdio_creator','release_acknowledged'} and
         life['owner']=='instance_factory' and number(life['factory_pid'],2,2**32-1) and
         life['factory_pid']==life['factory_tid'] and life['factory_pid']!=r['query_pid'] and
         all(number(life[k],1) for k in ('factory_pidfd_device','factory_pidfd_inode',
             'query_pidfd_device','query_pidfd_inode')) and life['release_acknowledged'] is True and
         type(io) is dict and set(io)=={'pid','waitid_code','waitid_status'} and
         number(io['pid'],2,2**32-1) and io['pid'] not in (life['factory_pid'],r['query_pid']) and
         io['waitid_code']==1 and io['waitid_status']==0,
         'ACTUAL_RETIRED_FIXED_QUERY_COMPARISON_REQUIRED')
    return records


CALENDAR_TABLES=('Calendars','Events','Reminders','Attendees','Instances',
                 'CalendarAlerts','EventsRawTimes','ExtendedProperties')
CALENDAR_PROVIDER='com.android.providers.calendar'
CALENDAR_DB='/data/user/0/'+CALENDAR_PROVIDER+'/databases/calendar.db'
CALENDAR_UID=10017
CALENDAR_DB_CONTEXT='u:object_r:privapp_data_file:s0:c512,c768'

def _calendar_file(value):
    need(type(value) is dict and set(value)=={
        'device','inode','uid','gid','mode','links','size','selinux','mtime','ctime'},
        'EXACT_CALENDAR_FILE_STATE_REQUIRED')
    need(number(value['device'],1) and number(value['inode'],1)
         and value['uid']==CALENDAR_UID and type(value['uid']) is int
         and number(value['gid'],0,2**32-1) and number(value['mode'],0,2**32-1)
         and stat.S_ISREG(value['mode']) and value['mode']&0o400!=0
         and value['mode']&0o002==0 and type(value['links']) is int and value['links']==1
         and number(value['size']) and value['selinux']==CALENDAR_DB_CONTEXT,
         'CALENDAR_FILE_IDENTITY_DIFFERS')
    for name in ('mtime','ctime'):
        moment=value[name]
        need(type(moment) is dict and set(moment)=={'seconds','nanos'}
             and number(moment['seconds']) and number(moment['nanos'],0,999999999),
             'EXACT_CALENDAR_NANOSECOND_TIME_REQUIRED')
    return {key:value[source] for key,source in (
        ('st_dev','device'),('st_ino','inode'),('st_uid','uid'),
        ('st_gid','gid'),('st_mode','mode'),('st_nlink','links'))}

def _calendar_provider(value,core):
    need(type(value) is dict and set(value)=={
        'package','user','uid','version_code','epoch','apks'}
         and value['package']==CALENDAR_PROVIDER
         and type(value['user']) is int and value['user']==0
         and type(value['uid']) is int and value['uid']==CALENDAR_UID
         and number(value['version_code'],1) and value['epoch']==core['main']['epoch']
         and type(value['apks']) is list and 1<=len(value['apks'])<=64,
         'ACTUAL_COMPLETE_CALENDAR_PROVIDER_REQUIRED')
    names=set();paths=set();base=0
    for apk in value['apks']:
        need(type(apk) is dict and set(apk)=={'name','path','bytes','sha256'}
             and type(apk['name']) is str and 1<=len(apk['name'])<=255
             and '/' not in apk['name'] and _absolute(apk['path'])
             and apk['path'].endswith('.apk') and number(apk['bytes'],1)
             and _hash(apk['sha256']) and apk['name'] not in names and apk['path'] not in paths,
             'COMPLETE_CALENDAR_PROVIDER_APK_SET_DIFFERS')
        names.add(apk['name']);paths.add(apk['path']);base+=apk['name']=='base.apk'
    need(base==1,'ONE_CALENDAR_PROVIDER_BASE_APK_REQUIRED')

def validate_calendar_counts_comparison(value,core,deadline_ns):
    """Validate comparison data only; the live owner remains in the Rust parent."""
    need(core['application']['package']=='com.android.calendar'
         and type(value) is dict and set(value)=={'schema','counts',
             'provider_before','provider_after','gateway','comparison_only','business_actions_admitted'}
         and value['schema']=='droidloom.native-leaf-calendar-counts.v1'
         and value['comparison_only'] is True and value['business_actions_admitted'] is False,
         'FIXED_CALENDAR_COMPARISON_REQUIRED')
    before_provider,after_provider=value['provider_before'],value['provider_after']
    _calendar_provider(before_provider,core);_calendar_provider(after_provider,core)
    need(before_provider==after_provider,'CALENDAR_PROVIDER_CHANGED_DURING_COUNTS')
    projection=value['counts']
    need(type(projection) is dict and set(projection)=={'counts','db_identity',
         'database_before','database_after','identity_namespace','database_body_read_by',
         'application_rows_disclosed','comparison_only'}
         and projection['identity_namespace']=='selected_android_user_zero'
         and projection['database_body_read_by']=='fixed_guest_readonly_sqlite_observer'
         and projection['application_rows_disclosed'] is False and projection['comparison_only'] is True,
         'EXACT_CALENDAR_COUNT_PROJECTION_REQUIRED')
    db_before=_calendar_file(projection['database_before'])
    db_after=_calendar_file(projection['database_after'])
    need(type(projection['db_identity']) is dict and
         set(projection['db_identity'])==set(db_before) and
         all(number(n) for n in projection['db_identity'].values()) and
         db_before==db_after==projection['db_identity'],'CALENDAR_DATABASE_REPLACED')
    counts=projection['counts']
    need(type(counts) is dict and set(counts)==set(CALENDAR_TABLES)
         and all(number(counts[name],0,2**63-1) for name in CALENDAR_TABLES),
         'ALL_EIGHT_EXACT_CALENDAR_COUNTS_REQUIRED')
    gateway=value['gateway']
    need(type(gateway) is dict and set(gateway)=={'schema','request','before_main','after_main',
         'stdout_base64','stderr_base64','stderr_bytes','stderr_sha256','receipt'}
         and gateway['schema']=='droidloom.native-ui-gateway-reply.v1'
         and gateway['before_main']==gateway['after_main']==core['main']
         and gateway['stderr_base64']=='' and type(gateway['stderr_bytes']) is int
         and gateway['stderr_bytes']==0 and gateway['stderr_sha256']==sha(b''),
         'ACTUAL_RETIRED_CALENDAR_GATEWAY_REQUIRED')
    request=gateway['request']
    need(type(request) is dict and set(request)=={'schema','main','application','command',
         'deadline_monotonic_ns'} and request['schema']=='droidloom.native-ui-gateway-request.v1'
         and request['main']==core['main'] and request['application']==core['application']
         and request['command']=={'kind':'calendar_counts'}
         and number(request['deadline_monotonic_ns'],1,deadline_ns),
         'CALENDAR_REQUEST_BELONGS_TO_ANOTHER_MAIN_APPLICATION_OR_END')
    encoded=gateway['stdout_base64']
    need(type(encoded) is str and len(encoded)<=4*((8192+2)//3),'BOUNDED_CALENDAR_STDOUT_REQUIRED')
    stdout=base64.b64decode(encoded,validate=True)
    need(base64.b64encode(stdout).decode('ascii')==encoded and 0<len(stdout)<=8192
         and stdout[:1]==b'{' and stdout[-1:]==b'\n'
         and not any(byte<32 or byte==127 for byte in stdout[:-1]),
         'CANONICAL_COMPLETE_CALENDAR_STDOUT_REQUIRED')
    android=parse(stdout)
    need(type(android) is dict and set(android)=={'schema','provider','user','observer_uid',
         'observer_gid','database','read_only','query','cursor_rows','window_rows','before','after','tables'}
         and android['schema']=='droidloom.native-calendar-counts.android.v1'
         and android['provider']==CALENDAR_PROVIDER and type(android['user']) is int
         and android['user']==0 and type(android['observer_uid']) is int
         and type(android['observer_gid']) is int
         and android['observer_uid']==android['observer_gid']==CALENDAR_UID
         and android['database']==CALENDAR_DB and android['read_only'] is True
         and android['query']=='eight-table-counts-one-sqlite-statement.v1'
         and type(android['cursor_rows']) is int and type(android['window_rows']) is int
         and android['cursor_rows']==android['window_rows']==8
         and android['before']==projection['database_before']
         and android['after']==projection['database_after']
         and type(android['tables']) is list and len(android['tables'])==8,
         'FIXED_CALENDAR_ANDROID_OUTPUT_DIFFERS')
    for row,name in zip(android['tables'],CALENDAR_TABLES):
        need(type(row) is dict and set(row)=={'name','count'} and row['name']==name
             and number(row['count'],0,2**63-1) and row['count']==counts[name],
             'CALENDAR_STDOUT_AND_COUNT_PROJECTION_DIFFER')
    receipt=gateway['receipt']
    need(type(receipt) is dict and set(receipt)=={'schema','lifecycle','query_pid','query_waitid_code',
         'query_waitid_status','exec','output_bytes','output_sha256','elapsed_millis','cgroup_removed'}
         and type(receipt['schema']) is int and receipt['schema']==2
         and number(receipt['query_pid'],2,2**31-1)
         and type(receipt['query_waitid_code']) is int and receipt['query_waitid_code']==1
         and type(receipt['query_waitid_status']) is int and receipt['query_waitid_status']==0
         and receipt['cgroup_removed'] is True and number(receipt['elapsed_millis'],0,14000)
         and type(receipt['output_bytes']) is int and receipt['output_bytes']==len(stdout)
         and receipt['output_sha256']==sha(stdout),
         'CALENDAR_ACTUAL_OUTPUT_OR_QUERY_RETIREMENT_DIFFERS')
    life=receipt['lifecycle']
    need(type(life) is dict and set(life)=={'owner','factory_pid','factory_tid','factory_pidfd_device',
         'factory_pidfd_inode','query_pidfd_device','query_pidfd_inode','stdio_creator','release_acknowledged'}
         and life['owner']=='instance_factory' and number(life['factory_pid'],2,2**31-1)
         and type(life['factory_tid']) is int and life['factory_tid']==life['factory_pid']
         and life['factory_pid']!=receipt['query_pid'] and life['release_acknowledged'] is True
         and all(number(life[k],1) for k in ('factory_pidfd_device','factory_pidfd_inode',
                                           'query_pidfd_device','query_pidfd_inode'))
         and (life['factory_pidfd_device'],life['factory_pidfd_inode'])!=
             (life['query_pidfd_device'],life['query_pidfd_inode']),
         'CALENDAR_ORIGINAL_FACTORY_RELEASE_DIFFERS')
    creator=life['stdio_creator']
    need(type(creator) is dict and set(creator)=={'pid','waitid_code','waitid_status'}
         and number(creator['pid'],2,2**31-1)
         and creator['pid'] not in (life['factory_pid'],receipt['query_pid'])
         and type(creator['waitid_code']) is int and creator['waitid_code']==1
         and type(creator['waitid_status']) is int and creator['waitid_status']==0,
         'CALENDAR_STDIO_CREATOR_RETIREMENT_DIFFERS')
    executed=receipt['exec']
    need(type(executed) is dict and set(executed)=={'query_start_ticks','original_parent_pid','tracer_tid',
         'waitid_code','waitid_status','event_previous_tid','executable','executable_mount_id',
         'executable_sha256','executable_selinux','process_selinux','process_apparmor','uid','gid',
         'no_new_privileges','seccomp_filter_mode'}
         and number(executed['query_start_ticks'],1)
         and executed['original_parent_pid']==executed['tracer_tid']==life['factory_pid']
         and type(executed['waitid_code']) is int and executed['waitid_code']==4
         and type(executed['waitid_status']) is int and executed['waitid_status']==(5|(4<<8))
         and executed['event_previous_tid']==receipt['query_pid']
         and number(executed['executable_mount_id'],1) and _hash(executed['executable_sha256'])
         and executed['executable_selinux']=='u:object_r:droidloom_provider_exec:s0'
         and executed['process_selinux']=='u:r:droidloom_calendar_counts:s0:c512,c768'
         and executed['process_apparmor']=='droidloom-production-android (enforce)'
         and executed['no_new_privileges'] is True
         and type(executed['seccomp_filter_mode']) is int and executed['seccomp_filter_mode']==2,
         'CALENDAR_ACTUAL_TRACEEXEC_ROLE_DIFFERS')
    node=executed['executable']
    need(type(node) is dict and set(node)=={'dev','ino','mode','uid','gid','nlink','bytes',
         'mtime','mtime_nsec','ctime','ctime_nsec'} and number(node['dev'],1) and number(node['ino'],1)
         and type(node['mode']) is int and node['mode']==stat.S_IFREG|0o555
         and type(node['nlink']) is int and node['nlink']==1 and number(node['bytes'],1)
         and number(node['uid'],0,2**32-1) and number(node['gid'],0,2**32-1)
         and number(node['mtime'],-2**63,2**63-1) and number(node['ctime'],-2**63,2**63-1)
         and number(node['mtime_nsec'],0,999999999) and number(node['ctime_nsec'],0,999999999)
         and number(executed['uid'],0,2**32-1) and number(executed['gid'],0,2**32-1)
         and executed['uid']==node['uid']+CALENDAR_UID and executed['gid']==node['gid']+CALENDAR_UID,
         'CALENDAR_ACTUAL_EXECUTABLE_OR_MAPPED_UID_DIFFERS')
    return projection


# The original-reader comparison is distinct from the received sealed copy.
# None of these Python records can start an owner, replace a role or retire it.
APK_BYTES_LIMIT=512*1024*1024
APK_GROUP_BYTES_LIMIT=(1024+17)*1024*1024
APK_FILE_FIELDS=frozenset(('dev','ino','mode','uid','gid','nlink','bytes',
                          'mtime','mtime_nsec','ctime','ctime_nsec'))
APK_APPLICATION_FIELDS=frozenset(('package','user','uid','version_code','epoch','apks'))
APK_MAIN_PACKAGES={
    'calendar_core':'com.android.calendar','calendar_reminder':'com.android.calendar',
    'camera_photo':'com.android.camera2','contacts_search':'com.android.contacts',
    'clock_pair':'com.android.deskclock','clock_alarm':'com.android.deskclock',
    'documents_saf':'com.android.documentsui','documents_search':'com.android.documentsui',
    'gallery_rotation':'com.android.gallery3d','gallery_video':'com.android.gallery3d',
    'gallery_seek':'com.android.gallery3d','gallery_album':'com.android.gallery3d',
    'settings_supported_pages':'com.android.settings','ihg_london':'com.ihg.apps.android',
}
APK_PROVIDERS={
    'calendar_core':'com.android.providers.calendar',
    'calendar_reminder':'com.android.providers.calendar',
    'contacts_search':'com.android.providers.contacts',
    'camera_photo':'com.android.providers.media.module',
    'gallery_rotation':'com.android.providers.media.module',
    'documents_saf':'com.android.externalstorage','documents_search':'com.android.externalstorage',
}
APK_NATIVE_HELPER='local.pocket4.actions.v2'
APK_IHG_HELPER='org.droidloom.qa.ihg.finalmain.r1'
APK_QUERY_EXEC_BYTES=52160
APK_QUERY_EXEC_SHA='237410b6f4bfb9586a9a1135feaa4e75c189288483575890447aa5d492c56984'

def _apk_roles(scope,core):
    need(type(scope) is dict and scope.get('kind') in ('business','preparation'),
         'FIXED_ORIGINAL_APK_SCOPE_REQUIRED')
    prep=scope['kind']=='preparation'
    need(set(scope)==({'kind','case','member'} if prep else {'kind','route'}),
         'EXACT_ORIGINAL_APK_SCOPE_FIELDS_REQUIRED')
    case=scope['case'] if prep else scope['route']
    need(case in APK_MAIN_PACKAGES and core['application']['package']==APK_MAIN_PACKAGES[case],
         'ORIGINAL_APK_SCOPE_MUST_MATCH_PRIMARY_BASELINE')
    helper=('ihg_helper',APK_IHG_HELPER,1,2*1024*1024) if case=='ihg_london' else (
        'native_helper',APK_NATIVE_HELPER,1,1024*1024)
    roles=[('application',APK_MAIN_PACKAGES[case],32,1024*1024*1024)]
    if case in APK_PROVIDERS:roles.append(('provider',APK_PROVIDERS[case],1,16*1024*1024))
    roles.append(helper)
    if prep:
        member=scope['member']
        need(member in ('application','provider','native_helper','ihg_helper')
             and not (member=='provider' and case in ('camera_photo','gallery_rotation')),
             'PREPARATION_ROLE_REQUIRES_ITS_ORIGINAL_IDENTITY_PRODUCER')
        roles=[r for r in roles if r[0]==member]
        need(len(roles)==1,'EXACT_SINGLE_PREPARATION_ROLE_REQUIRED')
    return roles

def _apk_file(value,size,copy=False):
    need(type(value) is dict and set(value)==APK_FILE_FIELDS
         and all(number(value[k],0,2**64-1) for k in
                 ('dev','ino','mode','uid','gid','nlink','bytes'))
         and value['ino']>0 and stat.S_ISREG(value['mode'])
         and 0<value['bytes']==size<=APK_BYTES_LIMIT
         and all(type(value[k]) is int and -(2**63)<=value[k]<2**63 for k in ('mtime','ctime'))
         and all(number(value[k],0,999999999) for k in ('mtime_nsec','ctime_nsec')),
         'COMPLETE_ORIGINAL_OR_COPY_APK_FILE_IDENTITY_REQUIRED')
    if copy:
        need(value['nlink']==0 and value['mode']&0o7777==0o400 and
             value['uid']==value['gid']==0,'SEALED_COPY_FILE_IDENTITY_REQUIRED')
    else:
        need(value['nlink']==1 and value['mode']&0o6022==0,
             'ORIGINAL_SINGLE_LINK_NONWRITABLE_APK_REQUIRED')
    return value

def _apk_application(value,package,epoch,maximum_count,maximum_bytes):
    need(type(value) is dict and set(value)==APK_APPLICATION_FIELDS and
         value['package']==package and value['user']==0 and number(value['uid'],0,99999)
         and number(value['version_code'],1) and value['epoch']==epoch,
         'SAME_COMPLETE_ACTUAL_ROLE_PM_REQUIRED')
    apks=value['apks']
    need(type(apks) is list and 1<=len(apks)<=maximum_count
         and all(type(a) is dict and set(a)=={'name','path','bytes','sha256'} for a in apks),
         'EXACT_COMPLETE_ROLE_APK_SET_REQUIRED')
    names=[];paths=[];total=0
    for apk in apks:
        name,path=apk['name'],apk['path']
        need(type(name) is str and 1<=len(name.encode())<=255 and name.endswith('.apk')
             and not re.search(r'[\x00-\x20\x7f/]',name)
             and type(path) is str and len(path.encode())<=512 and path.endswith('.apk')
             and path.startswith(('/data/app/','/system/','/system_ext/','/product/',
                                  '/vendor/','/odm/','/oem/','/apex/'))
             and not re.search(r'[\x00-\x20\x7f]',path)
             and all(p not in ('','.','..') for p in path.split('/')[1:])
             and number(apk['bytes'],1,APK_BYTES_LIMIT) and _hash(apk['sha256']),
             'FIXED_PUBLIC_APK_PATH_AND_COMPLETE_HASH_REQUIRED')
        names.append(name);paths.append(path);total+=apk['bytes']
    need(names==sorted(set(names)) and names.count('base.apk')==1
         and len(paths)==len(set(paths)) and total<=maximum_bytes,
         'COMPLETE_SORTED_ROLE_APK_BOUND_REQUIRED')
    return value

def _apk_query_receipt(receipt,stdout,kind,maximum_millis=15000):
    """Validate comparison of an actual normal factory, not a host subprocess."""
    need(kind in ('identity','paths','launcher','fixture_install','fixture_state') and
         ((stdout is None and kind=='fixture_install') or (type(stdout) is bytes and len(stdout)<=(262144 if kind=='fixture_state' else 65536))),
         'FIXED_APK_QUERY_KIND_AND_OUTPUT_BOUND_REQUIRED')
    need(type(receipt) is dict and set(receipt)=={'schema','lifecycle','query_pid','query_waitid_code',
         'query_waitid_status','exec','output_bytes','output_sha256','elapsed_millis','cgroup_removed'}
         and receipt['schema']==2 and receipt['cgroup_removed'] is True
         and number(receipt['query_pid'],2,2**31-1)
         and receipt['query_waitid_code']==1 and receipt['query_waitid_status']==0
         and ((stdout is None and number(receipt['output_bytes'],0,65536) and _hash(receipt['output_sha256']))
              or (stdout is not None and receipt['output_bytes']==len(stdout) and receipt['output_sha256']==sha(stdout)))
         and number(receipt['elapsed_millis'],0,maximum_millis),
         'ACTUAL_SUCCESSFUL_APK_QUERY_RETIREMENT_REQUIRED')
    life=receipt['lifecycle'];stdio=life.get('stdio_creator') if type(life) is dict else None
    need(type(life) is dict and set(life)=={'owner','factory_pid','factory_tid','factory_pidfd_device',
         'factory_pidfd_inode','query_pidfd_device','query_pidfd_inode','stdio_creator','release_acknowledged'}
         and life['owner']=='instance_factory' and life['release_acknowledged'] is True
         and number(life['factory_pid'],2,2**31-1) and life['factory_pid']==life['factory_tid']
         and life['factory_pid']!=receipt['query_pid']
         and all(number(life[k],1) for k in ('factory_pidfd_device','factory_pidfd_inode',
              'query_pidfd_device','query_pidfd_inode'))
         and (life['factory_pidfd_device'],life['factory_pidfd_inode'])!=
              (life['query_pidfd_device'],life['query_pidfd_inode'])
         and type(stdio) is dict and set(stdio)=={'pid','waitid_code','waitid_status'}
         and number(stdio['pid'],2,2**31-1) and stdio['pid'] not in (receipt['query_pid'],life['factory_pid'])
         and stdio['waitid_code']==1 and stdio['waitid_status']==0,
         'ACTUAL_APK_FACTORY_AND_STDIO_RETIREMENT_REQUIRED')
    e=receipt['exec'];n=e.get('executable') if type(e) is dict else None
    need(type(e) is dict and set(e)=={'query_start_ticks','original_parent_pid','tracer_tid',
         'waitid_code','waitid_status','event_previous_tid','executable','executable_mount_id',
         'executable_sha256','executable_selinux','process_selinux','process_apparmor','uid','gid',
         'no_new_privileges','seccomp_filter_mode'}
         and number(e['query_start_ticks'],1) and e['original_parent_pid']==life['factory_pid']
         and e['tracer_tid']==life['factory_tid'] and e['waitid_code']==4
         and e['waitid_status']==(5|(4<<8)) and e['event_previous_tid']==receipt['query_pid']
         and e['process_selinux']=={'launcher':'u:r:droidloom_launch_read:s0','fixture_install':'u:r:droidloom_install:s0','fixture_state':'u:r:droidloom_fixture_state:s0'}.get(kind,'u:r:droidloom_query:s0')
         and e['process_apparmor']=='droidloom-production-android (enforce)'
         and e['executable_selinux']==('u:object_r:droidloom_provider_exec:s0' if kind=='fixture_state' else 'u:object_r:droidloom_query_exec:s0')
         and number(e['executable_mount_id'],1) and e['executable_sha256']==('bcc150b9c7e2abcc9aef312ea04f5bbcba631dbb2e23cb1b240b7219df1229a2' if kind=='fixture_state' else APK_QUERY_EXEC_SHA)
         and e['no_new_privileges'] is True and e['seccomp_filter_mode']==2
         and type(n) is dict and set(n)==APK_FILE_FIELDS
         and all(number(n[k],0) for k in ('dev','ino','mode','uid','gid','nlink','bytes'))
         and n['dev']>0 and n['ino']>0 and n['mode']==(stat.S_IFREG|0o555)
         and n['nlink']==1 and n['bytes']==(51616 if kind=='fixture_state' else APK_QUERY_EXEC_BYTES)
         and all(type(n[k]) is int and -(2**63)<=n[k]<2**63 for k in ('mtime','ctime'))
         and all(number(n[k],0,999999999) for k in ('mtime_nsec','ctime_nsec'))
         and e['uid']==n['uid']+2000 and e['gid']==n['gid']+2000,
         'ACTUAL_APK_QUERY_TRACEEXEC_AND_MAPPED_SHELL_REQUIRED')

def _apk_raw_matches(kind,stdout,application):
    text=stdout.decode('utf-8','strict')
    if kind=='identity':
        match=re.fullmatch(r'package:([^\s]+) (?:versionCode:([0-9]+) uid:([0-9]+)|uid:([0-9]+) versionCode:([0-9]+))\n?',text)
        need(match is not None,'ONE_COMPLETE_ACTUAL_PACKAGE_ROW_REQUIRED')
        package=match[1];version=int(match[2] or match[5]);uid=int(match[3] or match[4])
        need(package==application['package'] and uid==application['uid']
             and version==application['version_code'],'ACTUAL_ROLE_UID_OR_VERSION_CHANGED')
    elif kind=='paths':
        rows=text.splitlines()
        need(rows and len(rows)==len(set(rows)) and all(r.startswith('package:/') for r in rows)
             and sorted(r[8:] for r in rows)==sorted(a['path'] for a in application['apks']),
             'ACTUAL_COMPLETE_ROLE_APK_PATHS_CHANGED')
    return stdout

def validate_apk_custody(value,core):
    need(type(value) is dict and set(value)=={'schema','main','application','scope','packages',
         'originals','before_bookends','copies_transferred','package_read_count','package_reads_sha256','reader_retired',
         'comparison_only','original_apk_descriptors_on_host','business_accepted'}
         and value['schema']=='droidloom.native-leaf-apk-custody.v2'
         and value['main']==core['main'] and value['reader_retired'] is False
         and value['comparison_only'] is True and value['business_accepted'] is False
         and value['original_apk_descriptors_on_host'] is False,
         'LIVE_NORMAL_ORIGINAL_APK_COMPARISON_REQUIRED')
    roles=_apk_roles(value['scope'],core);packages=value['packages'];originals=[]
    need(type(packages) is list and len(packages)==len(roles),'COMPLETE_FIXED_APK_ROLE_GROUP_REQUIRED')
    seen=set();total=0
    for package,(_,name,count,limit) in zip(packages,roles):
        need(type(package) is dict and set(package)=={'application','originals'},
             'EXACT_APK_ROLE_COMPARISON_FIELDS_REQUIRED')
        app=_apk_application(package['application'],name,core['main']['epoch'],count,limit)
        need(type(package['originals']) is list and len(package['originals'])==len(app['apks']),
             'ONE_ORIGINAL_DESCRIPTOR_COMPARISON_PER_APK_REQUIRED')
        for original,apk in zip(package['originals'],app['apks']):
            need(type(original) is dict and set(original)=={'package','apk','identity','selinux'}
                 and original['package']==name and original['apk']==apk
                 and type(original['selinux']) is str and len(original['selinux'])<=256
                 and re.fullmatch(r'u:object_r:[A-Za-z0-9_:,.-]+',original['selinux'])
                 and apk['path'] not in seen,'DISTINCT_ACTUAL_ORIGINAL_APK_PROVENANCE_REQUIRED')
            _apk_file(original['identity'],apk['bytes'])
            seen.add(apk['path']);total+=apk['bytes'];originals.append(original)
    need(value['application']==packages[0]['application']
         and value['originals']==originals and 1<=len(originals)<=34
         and total<=APK_GROUP_BYTES_LIMIT and number(value['copies_transferred'],0,len(originals)),
         'EXACT_COMPLETE_APK_GROUP_AND_COPY_POSITION_REQUIRED')
    if value['scope']['kind']=='business':
        need(value['application']==core['application'],'BUSINESS_APK_PRIMARY_MUST_BE_ACTUAL_BASELINE')
    before=value['before_bookends']
    need(type(before) is list and len(before)==len(packages),'EVERY_ROLE_REQUIRES_ACTUAL_PM_MAIN_BOOKEND')
    for package,book in zip(packages,before):
        app=package['application']
        metadata_expected={k:v for k,v in app.items() if k!='apks'}
        metadata_expected['apks']=[{'name':a['name'],'path':a['path']} for a in app['apks']]
        need(type(book) is dict and set(book)=={'main','metadata','reads'}
             and book['main']==core['main'] and book['metadata']==metadata_expected
             and type(book['reads']) is list and len(book['reads'])==2,
             'COMPLETE_ACTUAL_PM_BOOKEND_REQUIRED')
        for kind,read in zip(('identity','paths'),book['reads']):
            need(type(read) is dict and set(read)=={'stdout','receipt'} and type(read['stdout']) is str,
                 'COMPLETE_ORIGINAL_PM_OUTPUT_REQUIRED')
            raw=read['stdout'].encode('utf-8')
            _apk_query_receipt(read['receipt'],raw,kind,30000);_apk_raw_matches(kind,raw,app)
    need(number(value['package_read_count'],0,4096)
         and _hash(value['package_reads_sha256']),
         'BOUNDED_ACTUAL_APK_QUERY_HISTORY_DIGEST_REQUIRED')
    return value

def validate_apk_package_read(value,custody,kind,ordinal):
    need(type(value) is dict and set(value)=={'schema','kind','ordinal','main_before','main_after',
         'application','stdout_base64','stderr_base64','stderr_bytes','stderr_sha256','receipt'}
         and value['schema']=='droidloom.native-leaf-package-read.v2'
         and value['kind']==kind and value['ordinal']==ordinal
         and value['main_before']==value['main_after']==custody['main']
         and number(ordinal,0,len(custody['packages'])-1)
         and value['application']==custody['packages'][ordinal]['application'],
         'ACTUAL_APK_QUERY_MUST_MATCH_ITS_OWN_ROLE_AND_MAIN')
    buffers=[]
    for key in ('stdout_base64','stderr_base64'):
        encoded=value[key]
        need(type(encoded) is str and len(encoded)<=4*((65536+2)//3),
             'BOUNDED_COMPLETE_APK_QUERY_BASE64_REQUIRED')
        raw=base64.b64decode(encoded,validate=True)
        need(len(raw)<=65536 and base64.b64encode(raw).decode('ascii')==encoded,
             'CANONICAL_COMPLETE_APK_QUERY_BASE64_REQUIRED')
        buffers.append(raw)
    out,err=buffers
    need(value['stderr_bytes']==len(err) and value['stderr_sha256']==sha(err) and not err,
         'ACTUAL_COMPLETE_APK_QUERY_STDERR_MUST_BE_EMPTY')
    _apk_query_receipt(value['receipt'],out,kind)
    _apk_raw_matches(kind,out,value['application'])
    return out,err

def _apk_actual_identity(fd):
    st=os.fstat(fd)
    return {'dev':st.st_dev,'ino':st.st_ino,'mode':st.st_mode,'uid':st.st_uid,'gid':st.st_gid,
            'nlink':st.st_nlink,'bytes':st.st_size,'mtime':st.st_mtime_ns//10**9,
            'mtime_nsec':st.st_mtime_ns%10**9,'ctime':st.st_ctime_ns//10**9,
            'ctime_nsec':st.st_ctime_ns%10**9}

class OriginalApkCustody:
    """Comparison access to one already-captured source-owned Rust interval."""
    def __init__(self,channel):
        self.channel=channel;self.pid=os.getpid();self.failed=False;self.closed=False
        channel.guard()
        self.value=validate_apk_custody(channel._read_fixed_comparison(b'A'),channel.core)
        self.originals=self.value['originals']
        self.anchor={k:self.value[k] for k in ('main','application','scope','packages','originals','before_bookends')}
        self.copy_position=self.value['copies_transferred']
        self.minimum_query_count=self.value['package_read_count']
        channel.guard()
    def local(self):
        need(self.pid==os.getpid() and not self.closed and not self.failed,
             'ORIGINAL_APK_COMPARISON_CLOSED_FAILED_OR_FORKED')
        self.channel.remaining(7200)
    def role(self,package):
        self.local()
        rows=[i for i,r in enumerate(self.value['packages']) if r['application']['package']==package]
        need(len(rows)==1,'PACKAGE_NOT_IN_THIS_ACTUAL_FIXED_APK_SCOPE')
        return rows[0]
    def package_read(self,kind,package):
        self.local();ordinal=self.role(package)
        need(kind in ('identity','paths','launcher'),'FIXED_APK_QUERY_KIND_REQUIRED')
        token={'identity':b'I','paths':b'P','launcher':b'L'}[kind]
        value=None
        try:
            value=self.channel._read_fixed_comparison(token,ordinal)
            out,err=validate_apk_package_read(value,self.value,kind,ordinal)
            self.minimum_query_count+=1
            self.local()
            return out,err,value
        except BaseException as error:
            self.failed=True
            if value is not None:error.native_package_comparison=value
            raise
    def guard(self,full=False):
        self.local();need(type(full) is bool,'EXPLICIT_ORIGINAL_APK_HASH_PHASE_REQUIRED')
        try:
            value=self.channel._read_fixed_comparison(b'R' if full else b'V')
            need(type(value) is dict and set(value)=={'schema','custody','full_sha256_checked','comparison_only'}
                 and value['schema']=='droidloom.native-leaf-apk-guard.v1'
                 and value['full_sha256_checked'] is full and value['comparison_only'] is True,
                 'ACTUAL_ORIGINAL_APK_PHASE_REPLY_REQUIRED')
            observed=validate_apk_custody(value['custody'],self.channel.core)
            need(all(observed[k]==v for k,v in self.anchor.items())
                 and observed['copies_transferred']>=self.copy_position
                 and observed['package_read_count']>=self.minimum_query_count
                 and (observed['package_read_count']!=self.value['package_read_count']
                      or observed['package_reads_sha256']==self.value['package_reads_sha256']),
                 'ORIGINAL_APK_OWNER_OR_WHOLE_ROLE_SET_CHANGED')
            self.minimum_query_count=observed['package_read_count']
            self.copy_position=observed['copies_transferred'];self.value=observed
            self.local()
            return value
        except BaseException:
            self.failed=True
            raise
    def copy_all(self,package,paths,directory):
        self.local()
        need(self.value['scope']['kind']=='preparation' and len(self.value['packages'])==1
             and self.role(package)==0 and self.copy_position==0
             and type(paths) is list and len(paths)==len(set(paths))
             and set(paths)=={o['apk']['path'] for o in self.originals},
             'EXACT_SINGLE_ROLE_IDENTITY_COPY_PHASE_REQUIRED')
        directory=Path(directory)
        need(directory.is_absolute() and directory.resolve()==directory
             and directory.is_dir(),'REAL_PRIVATE_IDENTITY_OUTPUT_REQUIRED')
        copies={}
        try:
            for index,original in enumerate(self.originals):
                self.local()
                # Unknown/interrupted requests are not repeated.
                self.copy_position=index+1
                with self.channel._read_apk_copy() as (value,fd):
                    need(type(value) is dict and set(value)=={'schema','main','application','copy',
                         'comparison_only','original_apk_descriptors_on_host'}
                         and value['schema']=='droidloom.native-leaf-apk-copy.v1'
                         and value['main']==self.channel.core['main']
                         and value['application']==self.channel.core['application']
                         and value['comparison_only'] is True
                         and value['original_apk_descriptors_on_host'] is False,
                         'ACTUAL_APK_COPY_MUST_BELONG_TO_THE_PRIMARY_INVOCATION')
                    copy=value['copy']
                    need(type(copy) is dict and set(copy)=={'ordinal','original','sealed_copy',
                         'sealed_copy_sha256','seals'} and copy['ordinal']==index
                         and copy['original']==original
                         and copy['sealed_copy_sha256']==original['apk']['sha256']
                         and copy['seals']==SEALS,'ORDERED_SAME_ORIGINAL_APK_COPY_REQUIRED')
                    _apk_file(copy['sealed_copy'],original['apk']['bytes'],copy=True)
                    need((copy['sealed_copy']['dev'],copy['sealed_copy']['ino'])!=
                         (original['identity']['dev'],original['identity']['ino'])
                         and _apk_actual_identity(fd)==copy['sealed_copy']
                         and fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY
                         and fcntl.fcntl(fd,fcntl.F_GET_SEALS)==SEALS
                         and os.getxattr(fd,'security.selinux').removesuffix(b'\0')==
                             b'u:object_r:droidloom_native_leaf_apk_copy:s0',
                         'REAL_SEALED_COPY_MUST_BE_DISTINCT_FROM_THE_ORIGINAL_INODE')
                    path=directory/('apk-%02d.apk'%index)
                    output=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
                    try:
                        count=0;digest=hashlib.sha256();size=original['apk']['bytes']
                        while count<size:
                            self.local()
                            block=os.pread(fd,min(65536,size-count),count)
                            need(block,'SEALED_APK_COPY_PREMATURE_EOF')
                            digest.update(block);offset=0
                            while offset<len(block):
                                self.local();written=os.write(output,block[offset:])
                                need(written>0,'PRIVATE_APK_COPY_SHORT_WRITE');offset+=written
                            count+=len(block)
                        os.fsync(output)
                        need(count==size and digest.hexdigest()==original['apk']['sha256']
                             and _apk_actual_identity(fd)==copy['sealed_copy']
                             and fcntl.fcntl(fd,fcntl.F_GET_SEALS)==SEALS
                             and os.pread(fd,1,size)==b'',
                             'COMPLETE_ACTUAL_SEALED_APK_BYTES_OR_INODE_CHANGED')
                    finally:os.close(output)
                    parent=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
                    try:os.fsync(parent)
                    finally:os.close(parent)
                    i=original['identity']
                    held={'device':i['dev'],'inode':i['ino'],'mode':i['mode'],'uid':i['uid'],
                          'gid':i['gid'],'bytes':i['bytes'],'mtime_ns':i['mtime']*10**9+i['mtime_nsec'],
                          'nlink':i['nlink']}
                    copies[original['apk']['path']]={'guest_path':original['apk']['path'],
                        'bytes':size,'sha256':original['apk']['sha256'],'held_file':held,
                        'stat_file':{**held,'ctime_ns':i['ctime']*10**9+i['ctime_nsec']},
                        'private_copy':{'path':str(path),'bytes':size,'sha256':digest.hexdigest()},
                        'original_custody':original,'sealed_copy':copy,
                        'original_apk_descriptor_on_host':False}
            self.guard(full=True)
            return [copies[path] for path in paths]
        except BaseException:
            self.failed=True
            raise
    def match_identity(self,identity):
        self.local()
        need(type(identity) is dict and type(identity.get('metadata')) is dict,
             'ACTUAL_IDENTITY_COMPARISON_REQUIRED')
        ordinal=self.role(identity['metadata']['package'])
        app=self.value['packages'][ordinal]['application']
        need(identity['metadata']=={k:app[k] for k in ('package','uid','version_code','user')}
             and len(identity['artifacts'])==len(app['apks']),
             'SAVED_IDENTITY_MUST_MATCH_THIS_ACTUAL_ROLE')
        by_path={row['apk']['path']:row for row in self.value['packages'][ordinal]['originals']}
        need(len(identity['artifacts'])==len({a['guest_path'] for a in identity['artifacts']})
             and set(by_path)=={a['guest_path'] for a in identity['artifacts']},
             'COMPLETE_SAVED_APK_SET_MUST_MATCH_ACTUAL_OWNER')
        for artifact in identity['artifacts']:
            original=by_path[artifact['guest_path']];i=original['identity']
            held={'device':i['dev'],'inode':i['ino'],'mode':i['mode'],'uid':i['uid'],'gid':i['gid'],
                  'bytes':i['bytes'],'mtime_ns':i['mtime']*10**9+i['mtime_nsec'],'nlink':i['nlink']}
            need(artifact['bytes']==original['apk']['bytes'] and artifact['sha256']==original['apk']['sha256']
                 and artifact['held_file']==held
                 and artifact['stat_file']=={**held,'ctime_ns':i['ctime']*10**9+i['ctime_nsec']},
                 'SAVED_ORIGINAL_APK_F9_OR_FULL_HASH_DIFFERS')
        return app
    def require_identity(self,identity,full=False):
        app=self.match_identity(identity)
        self.guard(full=full)
        self.package_read('identity',app['package'])
    def close(self):
        self.closed=True
        # The Rust parent still owns the reader. Its final PM/Main, whole hash,
        # release and actual waitid occur after the child; this is no retirement.

# The four source-owned fixtures are independent from the commercial app
# roster. These literals compare observations; only the retained Rust owner
# can install, read state, or retire one of them.
FIXTURE_ROOT='/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1'
FIXTURE_ROUTES={'documents_saf':'saf','documents_search':'features','gallery_rotation':'rotation',
                'gallery_video':'video','gallery_seek':'video','gallery_album':'video'}
FIXTURE_PINS={'saf': {'kind': 'saf', 'package': 'org.droidloom.qa.saf.r12.na7f1de49e707c7a9', 'run_id': 'a7f1de49e707c7a9', 'apk': {'bytes': 24838, 'sha256': 'eb7bac9ede6b729829fbecb031db4ae7b7224634619154abe2f01b2b3be875d6'}, 'certificate_sha256': 'b5ed86bf8873ade11e2304965288d19f0ee0dc84da5a5f3e4411d4535b015ea7', 'preference': 'owned-saf-a7f1de49e707c7a9.xml', 'members': {'MANIFEST.json': {'bytes': 16781, 'sha256': '5b965fdab8fd49af9686854fb65f7ce0442e83f716752802ede2f646cc429dbb'}, 'SOURCE.json': {'bytes': 2281, 'sha256': 'a6ac2ec4a91930e573bca80b712738a7db647036a9ba86b3d2f169cd55b7123a'}, 'STATE-SOURCE.json': {'bytes': 15851, 'sha256': 'd11880a5c19c7783b5d7b130f081740887e559891aee0fc3ebda0cb3f339cb2b'}, 'helper.apk': {'bytes': 24838, 'sha256': 'eb7bac9ede6b729829fbecb031db4ae7b7224634619154abe2f01b2b3be875d6'}, 'signer.der': {'bytes': 1083, 'sha256': 'b5ed86bf8873ade11e2304965288d19f0ee0dc84da5a5f3e4411d4535b015ea7'}, 'source/AndroidManifest.xml': {'bytes': 1137, 'sha256': 'a3adcf3764edcda1fb89526ea93669637e3513342788d4d681581695b77451b9'}, 'source/SOURCE_PINS.json': {'bytes': 2281, 'sha256': 'a6ac2ec4a91930e573bca80b712738a7db647036a9ba86b3d2f169cd55b7123a'}, 'source/contract.json': {'bytes': 1105, 'sha256': '146bba638a8875dd7b3eedc0d1fbbcd28e636975afd4a65cb145927abc7ac6cf'}, 'source/res/values/ids.xml': {'bytes': 273, 'sha256': '96b43d2d226700a9d1b99a9575b6ab73f5ca245776165d1a05ef783579e9c1f7'}, 'source/src/org/droidloom/qa/saf/r12/na7f1de49e707c7a9/SafActivity.java': {'bytes': 16590, 'sha256': 'b0e977a68c02d1e2d9be5509d2e705f4068480ab85bd7409e3fe9a625f0dd7fd'}, 'state/FixedStateProvider.java': {'bytes': 11630, 'sha256': 'f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545'}}}, 'features': {'kind': 'features', 'package': 'org.droidloom.qa.documents.r12.n98116f3fbefcfc95', 'run_id': '98116f3fbefcfc95', 'apk': {'bytes': 24838, 'sha256': '368e9c52f391c0f11f78da4b1c3c9e72abe31f4d001fa593ebd46a59dcb7fab5'}, 'certificate_sha256': '06c090f9bcca6c214621b85222ddc86d672aee3085c1e3bc278a40f8c5d8ef11', 'preference': 'owned-features-98116f3fbefcfc95.xml', 'members': {'MANIFEST.json': {'bytes': 16943, 'sha256': '943aa4b47117d5a164dd8f69fecbc3be975d936bb78d17a2eef3d0d1c4823c0f'}, 'SOURCE.json': {'bytes': 2389, 'sha256': 'f6c5426f1363bd16d259a14676696e9353efd630d52b562481975e1d2a7782c8'}, 'STATE-SOURCE.json': {'bytes': 15992, 'sha256': '55aa42d39f0659449b50ebd257e9e0b57a0d832a7ebb49ab7b1920060bf665bb'}, 'helper.apk': {'bytes': 24838, 'sha256': '368e9c52f391c0f11f78da4b1c3c9e72abe31f4d001fa593ebd46a59dcb7fab5'}, 'signer.der': {'bytes': 1083, 'sha256': '06c090f9bcca6c214621b85222ddc86d672aee3085c1e3bc278a40f8c5d8ef11'}, 'source/AndroidManifest.xml': {'bytes': 721, 'sha256': 'bf3848131b913324665cf85ce1648b388d1ba2deda6386487703a0b7ea3a3ebf'}, 'source/SOURCE_PINS.json': {'bytes': 2389, 'sha256': 'f6c5426f1363bd16d259a14676696e9353efd630d52b562481975e1d2a7782c8'}, 'source/contract.json': {'bytes': 3302, 'sha256': '68f18ac35676090c1a05fb7709bf90de475bc4c31cf0642ac6fe92aad4343828'}, 'source/res/values/ids.xml': {'bytes': 451, 'sha256': '2cb07cba41fa376ebc3d8f72f7e9491a8dc88ae87672d75ab1fcba1f0fb82083'}, 'source/src/org/droidloom/qa/documents/r12/n98116f3fbefcfc95/FeaturesActivity.java': {'bytes': 19190, 'sha256': 'a3339fc610064e5b91a91e138cbb7707b04e4aa9fc62f5f4b7571f5ede22cfe9'}, 'state/FixedStateProvider.java': {'bytes': 11630, 'sha256': 'f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545'}}}, 'rotation': {'kind': 'rotation', 'package': 'org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03', 'run_id': 'd24b61ed8f7c9a03', 'apk': {'bytes': 24838, 'sha256': 'd53ba35fdb2252126fef94ce7da2d43bff78560cc90111206b0c2c9e766777d3'}, 'certificate_sha256': 'f122e9201c86a547b8cbaa37cbe2cd7962bb96eabe3c07365204d392b580244f', 'preference': 'owned-rotation-d24b61ed8f7c9a03.xml', 'members': {'MANIFEST.json': {'bytes': 16172, 'sha256': '69e35a784613abf7f63d1fe794d3b0cc47fd3d0b5b9d443f01534eabbf324a63'}, 'SOURCE.json': {'bytes': 924, 'sha256': 'cf0fb33c74e066afcfc660bd9dadfafdd8cd5b77c361d649bf0680100c019193'}, 'STATE-SOURCE.json': {'bytes': 15995, 'sha256': '2c38c042ac2eea340faf0e2203b7c1cc6acd115fcccb0bcbb5f783df9d33c503'}, 'helper.apk': {'bytes': 24838, 'sha256': 'd53ba35fdb2252126fef94ce7da2d43bff78560cc90111206b0c2c9e766777d3'}, 'signer.der': {'bytes': 1084, 'sha256': 'f122e9201c86a547b8cbaa37cbe2cd7962bb96eabe3c07365204d392b580244f'}, 'state/FixedStateProvider.java': {'bytes': 11630, 'sha256': 'f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545'}}}, 'video': {'kind': 'video', 'package': 'org.droidloom.qa.media.r12.nc92c3d79180955ef', 'run_id': 'c92c3d79180955ef', 'apk': {'bytes': 41286, 'sha256': 'f47d64fe943bb77fb8ad07288b4ae1c69e3db8cc8866b0e02230882134599820'}, 'certificate_sha256': '011632c9e2a1693585594df2bcc4b4fdb4cd074a05ccbdc5aa951aa1de9ad0b2', 'preference': 'owned-media-c92c3d79180955ef-video.xml', 'members': {'MANIFEST.json': {'bytes': 16071, 'sha256': 'ce4e38dd0c556987330d700a3130e22e898bd649fd50c2ceb4a352059031c13b'}, 'SOURCE.json': {'bytes': 1053, 'sha256': 'c06e5e21187d5b5b3a813b9d70e23f20ac0a51092cc530b79b289fa01b7c7552'}, 'STATE-SOURCE.json': {'bytes': 16188, 'sha256': '1b3bb25444ed190edac68bb7ff95e72d2ff16ea271c192ca4349a185c7aa68c2'}, 'helper.apk': {'bytes': 41286, 'sha256': 'f47d64fe943bb77fb8ad07288b4ae1c69e3db8cc8866b0e02230882134599820'}, 'signer.der': {'bytes': 1083, 'sha256': '011632c9e2a1693585594df2bcc4b4fdb4cd074a05ccbdc5aa951aa1de9ad0b2'}, 'state/FixedStateProvider.java': {'bytes': 11630, 'sha256': 'f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545'}}}}
FIXTURE_LIMITS={'begin':1141,'guard':448,'state':463,'retire':566}

def _fixture_bytes(value,maximum):
    need(type(value) is list and len(value)<=maximum and all(number(n,0,255) for n in value),
         'BOUNDED_ACTUAL_FIXTURE_OUTPUT_REQUIRED')
    return bytes(value)

def _fixture_b64(value,maximum):
    need(type(value) is str and len(value)<=4*((maximum+2)//3),'BOUNDED_FIXTURE_BASE64_REQUIRED')
    raw=base64.b64decode(value,validate=True)
    need(len(raw)<=maximum and base64.b64encode(raw).decode('ascii')==value,
         'COMPLETE_CANONICAL_FIXTURE_BASE64_REQUIRED')
    return raw

def _fixture_command(value,expected,remove=False):
    need(type(value) is dict and set(value)=={'stdout','stderr','receipt'},'EXACT_FIXTURE_COMMAND_COMPARISON_REQUIRED')
    out=_fixture_bytes(value['stdout'],65536);err=_fixture_bytes(value['stderr'],65536)
    need(out==expected and err==b'','ACTUAL_FIXED_PACKAGE_RESPONSE_DIFFERS')
    _apk_query_receipt(value['receipt'],out,'fixture_install' if remove else 'identity',110000 if remove else 8000)

def _fixture_absence(value,core,spec):
    need(type(value) is dict and set(value)=={'schema','package','user','framework_root','data_root','parents',
            'ce_errno','de_errno','private_file_bodies_read','comparison_only'} and
         value['schema']=='droidloom.fixed-fixture-data-absence.v1' and value['package']==spec['package'] and
         value['user']==0 and value['framework_root']==core['data']['framework_root'] and
         value['data_root']==core['data']['data_root'] and value['parents']==core['data']['directories'][:2] and
         value['ce_errno']==value['de_errno']==2 and value['private_file_bodies_read'] is False and
         value['comparison_only'] is True,'ACTUAL_ORIGINAL_HELPER_CE_DE_ABSENCE_REQUIRED')

def _fixture_data(value,core,app):
    need(type(value) is dict and set(value)==set(core['data']) and
         value['schema']=='droidloom.native-leaf-data.v1' and value['package']==app['package'] and
         value['user']==0 and value['android_uid']==app['uid'] and
         all(value[k]==core['data'][k] for k in ('framework_root','user_namespace','uid_map','gid_map','data_root')),
         'ACTUAL_LATE_BORN_DATA_MUST_USE_ORIGINAL_MAIN_AND_WORKING_IMAGE')
    owners=[]
    for key in ('uid_map','gid_map'):
        rows=[r for r in value[key] if r['inside']<=app['uid']<r['inside']+r['count']]
        need(len(rows)==1,'NEW_FIXTURE_UID_MUST_HAVE_ONE_ACTUAL_NAMESPACE_MAPPING')
        owners.append(rows[0]['outside']+app['uid']-rows[0]['inside'])
    need(owners[0]==owners[1]==value['mapped_host_uid'],'FIXTURE_UID_AND_GID_MAPPING_DIFFERS')
    ds=value['directories']
    need(type(ds) is list and len(ds)==4 and ds[:2]==core['data']['directories'][:2] and
         [d['path'] for d in ds[2:]]==['/data/user/0/'+app['package'],'/data/user_de/0/'+app['package']],
         'ONLY_ACTUAL_NEW_FIXTURE_CE_DE_DIRECTORIES_REQUIRED')
    for d in ds[2:]:
        need(type(d) is dict and set(d)==set(ds[0]) and
             all(number(d[k]) for k in ('device','inode','mount_id','mode','host_uid','host_gid')) and
             d['device']==value['data_root']['device'] and d['inode']>0 and d['mount_id']>0 and
             stat.S_ISDIR(d['mode']) and d['mode']&0o022==0 and
             d['host_uid']==d['host_gid']==value['mapped_host_uid'],
             'ACTUAL_FIXTURE_DIRECTORY_OWNERSHIP_OR_INODE_DIFFERS')
    need(ds[2]['inode']!=ds[3]['inode'],'FIXTURE_CE_DE_MUST_BE_DISTINCT')

def validate_fixture_state(raw,spec,app,data):
    need(type(raw) is bytes and len(raw)<=262144,'COMPLETE_FIXED_PROVIDER_OUTPUT_BOUND')
    prefix=b'Result: Bundle[{reply=';suffix=b'}]\n'
    need(raw.startswith(prefix) and raw.endswith(suffix),'EXACT_SINGLE_STOCK_CONTENT_BUNDLE_REQUIRED')
    encoded=raw[len(prefix):-len(suffix)].decode('ascii','strict')
    value=parse(_fixture_b64(encoded,147456))
    need(type(value) is dict and set(value)=={'schema','package','run','uid','pid','caller_uid','ce','de','prefs',
         'process_selinux','started_elapsed_ns','finished_elapsed_ns','state_mutated','activity_started'} and
         value['schema']=='droidloom.owned-fixture-state.v1' and value['package']==spec['package'] and
         value['run']==spec['run_id'] and value['uid']==app['uid'] and number(value['uid'],10000,19999) and
         number(value['pid'],1,2**31-1) and value['caller_uid']==2000 and
         value['state_mutated'] is False and value['activity_started'] is False and
         number(value['started_elapsed_ns'],1) and
         number(value['finished_elapsed_ns'],value['started_elapsed_ns'],value['started_elapsed_ns']+15*10**9),
         'FIXED_PROVIDER_ACTUAL_IDENTITY_OR_READONLY_SCOPE_DIFFERS')
    label=value['process_selinux']
    need(type(label) is dict and set(label)=={'value','bytes','sha256','terminal_nul'} and
         type(label['value']) is str and type(label['terminal_nul']) is bool,
         'ACTUAL_PROVIDER_KERNEL_CONTEXT_BYTES_REQUIRED')
    match=re.fullmatch(r'u:r:untrusted_app_32:s0:(c[0-9]+(?:,c[0-9]+){3})',label['value'])
    need(match is not None,'ACTUAL_PROVIDER_MUST_BE_SELECTED_TARGET33_APP_DOMAIN')
    cats=[int(c[1:]) for c in match[1].split(',')]
    need(cats==sorted(set(cats)) and all(0<=c<1024 for c in cats) and
         ','.join('c'+str(c) for c in cats)==match[1],'CANONICAL_ACTUAL_PROVIDER_MCS_REQUIRED')
    # Independently checked in the selected system image's actual libselinux.so
    # f53a7a8514698a3c8d047e60247e760f9d8a2f3bce845f6feb28c9da2755e0de.
    app_id=value['uid']-10000
    need(cats==[app_id&255,256+((app_id>>8)&255),512,768],
         'ACTUAL_PROVIDER_MCS_MUST_MATCH_ORDINARY_USER_ZERO_UID')
    context=label['value'].encode('ascii')+(b'\0' if label['terminal_nul'] else b'')
    need(len(context)<=256 and label['bytes']==len(context) and label['sha256']==sha(context),
         'PROVIDER_KERNEL_CONTEXT_FULL_RAW_HASH_DIFFERS')
    for key,d in zip(('ce','de'),data['directories'][2:]):
        need(value[key]==[d['device'],d['inode'],d['mode'],app['uid'],app['uid']],
             'PROVIDER_MUST_READ_ACTUALLY_HELD_NEW_CE_DE_INODES')
    p=value['prefs'];body=None
    if p is not None:
        need(type(p) is dict and set(p)=={'name','metadata','bytes','sha256','base64'} and
             p['name']==spec['preference'],'PROVIDER_CHANGED_FIXED_PREFERENCE_SELECTION')
        body=_fixture_b64(p['base64'],65536)
        need(body and p['bytes']==len(body) and p['sha256']==sha(body),'COMPLETE_PROVIDER_PREFERENCE_BODY_HASH_DIFFERS')
        m=p['metadata']
        need(type(m) is list and len(m)==11 and all(type(n) is int for n in m) and
             m[0]==value['ce'][0] and m[1]>0 and stat.S_ISREG(m[2]) and m[2]&0o022==0 and
             m[3]==m[4]==app['uid'] and m[5]==1 and m[6]==len(body) and
             number(m[8],0,999999999) and number(m[10],0,999999999),
             'ACTUAL_PROVIDER_PREFERENCE_OWNERSHIP_OR_SINGLE_FILE_DIFFERS')
    return value,body

class FixedFixture:
    """Comparison consumer of one actual source-owned Rust helper lease.

    Methods transmit single fixed opcodes. No saved receipt can recreate the
    lease, and none of these methods accepts package/URI/argv/path authority.
    """
    def __init__(self,channel):
        self.channel=channel;self.pid=os.getpid();self.failed=False;self.retired=False
        self._begin=None;self.last=None;self.begin_digest=None;self.last_state=None
        self.apk=channel.apk_custody();scope=self.apk.value['scope']
        need(scope.get('kind')=='business' and scope.get('route') in FIXTURE_ROUTES,
             'ONLY_SIX_ORIGINAL_BUSINESS_ROUTES_HAVE_A_FIXED_FIXTURE')
        self.route=scope['route'];self.spec=FIXTURE_PINS[FIXTURE_ROUTES[self.route]]
    def local(self):
        need(self.pid==os.getpid() and not self.failed and not self.retired,
             'FIXTURE_OWNER_CLOSED_FAILED_OR_FORKED_PRESERVE_WITHOUT_RETRY')
        self.channel.remaining(7200)
    def source(self):
        self.local();return parse(canonical(self.spec))
    def _validate(self,wrapper,action):
        core=self.channel.core;spec=self.spec
        need(type(wrapper) is dict and set(wrapper)=={'schema','transaction','original_absence','actual_data',
             'retirement_absence','comparison_only','business_accepted'} and
             wrapper['schema']=='droidloom.native-fixture-observation.v1' and
             wrapper['comparison_only'] is True and wrapper['business_accepted'] is False,
             'ACTUAL_ORIGINAL_OWNER_FIXTURE_COMPARISON_REQUIRED')
        _fixture_absence(wrapper['original_absence'],core,spec)
        t=wrapper['transaction'];r=t.get('request') if type(t) is dict else None
        need(type(t) is dict and set(t)=={'schema','request','before_main','after_main','before_inventory','after_inventory',
             'helper','retained_before','retained_after','installation','payload_creator','retirement','state',
             'comparison_only','business_accepted'} and t['schema']=='droidloom.native-fixture-reply.v1' and
             t['comparison_only'] is True and t['business_accepted'] is False and
             t['before_main']==t['after_main']==core['main'] and
             type(r) is dict and set(r)=={'schema','action','route','main','primary','begin_sha256',
                 'retention_monotonic_ns','deadline_monotonic_ns'} and
             r['schema']=='droidloom.native-fixture-request.v1' and r['action']==action and r['route']==self.route and
             r['main']==core['main'] and r['primary']==core['application'] and
             number(r['deadline_monotonic_ns'],1) and
             number(r['retention_monotonic_ns'],r['deadline_monotonic_ns'],self.channel.deadline_ns),
             'FIXTURE_REQUEST_MUST_MATCH_ORIGINAL_MAIN_SCOPE_AND_DEADLINE')
        app=_apk_application(t['helper'],spec['package'],core['main']['epoch'],1,262144)
        need(app['version_code']==1 and len(app['apks'])==1 and app['apks'][0]['name']=='base.apk' and
             number(app['uid'],10000,99999) and app['apks'][0]['path'].startswith('/data/app/') and
             app['apks'][0]['path'].endswith('/base.apk') and
             app['apks'][0]['bytes']==spec['apk']['bytes'] and app['apks'][0]['sha256']==spec['apk']['sha256'],
             'ACTUAL_HELPER_COMPLETE_PM_APK_IDENTITY_DIFFERS')
        _fixture_data(wrapper['actual_data'],core,app)
        before=inventory_table(t['before_inventory'],core,fixture=True)
        after=inventory_table(t['after_inventory'],core,fixture=True)
        installed=('package:'+spec['package']+' uid:'+str(app['uid'])+'\n').encode()
        if action=='begin':
            need(self._begin is None and r['begin_sha256'] is None and spec['package'] not in before and
                 app['uid'] not in before.values() and after=={**before,spec['package']:app['uid']} and
                 wrapper['retirement_absence'] is None and t['retirement'] is None and t['retained_after'] is None,
                 'EXACTLY_ONE_NEW_PACKAGE_AND_FRESH_UID_REQUIRED')
            _fixture_command(t['retained_before'],b'')
        else:
            need(self._begin is not None and _hash(r['begin_sha256']) and
                 r['retention_monotonic_ns']==self._begin['transaction']['request']['retention_monotonic_ns'] and
                 (self.begin_digest is None or self.begin_digest==r['begin_sha256']) and
                 all(t[k]==self._begin['transaction'][k] for k in ('helper','installation','payload_creator')) and
                 wrapper['original_absence']==self._begin['original_absence'] and
                 wrapper['actual_data']==self._begin['actual_data'] and
                 before==inventory_table(self._begin['transaction']['after_inventory'],core,fixture=True),
                 'CONTINUATION_MUST_MATCH_RETAINED_ACTUAL_INSTALLATION')
            _fixture_command(t['retained_before'],installed)
            if action=='retire':
                _fixture_command(t['retirement'],b'Success\n',remove=True)
                _fixture_command(t['retained_after'],b'')
                _fixture_absence(wrapper['retirement_absence'],core,spec)
                need(after==inventory_table(self._begin['transaction']['before_inventory'],core,fixture=True),
                     'RETIREMENT_MUST_RESTORE_COMPLETE_ORIGINAL_UID_TABLE')
            else:
                need(after==before and t['retirement'] is None and t['retained_after'] is None and
                     wrapper['retirement_absence'] is None,'READONLY_FIXTURE_CONTINUATION_CHANGED_INSTALLATION')
            self.begin_digest=r['begin_sha256']
        installation=t['installation']
        need(type(installation) is dict and set(installation)=={'session','user','bytes','segments','commands'} and
             number(installation['session'],1,2**31-1) and installation['user']==0 and
             installation['bytes']==spec['apk']['bytes'] and installation['segments']==[
                 {'index':0,'bytes':spec['apk']['bytes'],'sha256':spec['apk']['sha256']}],
             'NORMAL_ATOMIC_CREATE_ONLY_INSTALLATION_REQUIRED')
        commands=installation['commands'];session=installation['session']
        expected=[{'install':'CreateOnly','bytes':spec['apk']['bytes']},
                  {'install':'Write','session':session,'index':0,'bytes':spec['apk']['bytes']},
                  {'install':'Commit','session':session}]
        need(type(commands) is list and len(commands)==3,'ONE_NORMAL_CREATE_WRITE_COMMIT_SEQUENCE_REQUIRED')
        for command,wanted in zip(commands,expected):
            need(type(command) is dict and set(command)=={'command','receipt'} and command['command']==wanted,
                 'FIXED_NORMAL_INSTALL_COMMAND_DIFFERS')
            _apk_query_receipt(command['receipt'],None,'fixture_install',110000)
        creator=t['payload_creator']
        need(type(creator) is dict and set(creator)=={'schema','kind','apk_bytes','apk_sha256','material','creator',
             'creation_limit_seconds','retirement_reserve_seconds','caller_path_accepted','broker_created_payload'} and
             creator['schema']=='droidloom.working-apk-payload.v1' and
             creator['kind']=={'saf':'documents_saf','features':'documents_features','rotation':'gallery_rotation','video':'gallery_video'}[spec['kind']] and
             creator['apk_bytes']==spec['apk']['bytes'] and creator['apk_sha256']==spec['apk']['sha256'] and
             creator['creation_limit_seconds']==120 and creator['retirement_reserve_seconds']==3 and
             creator['caller_path_accepted'] is False and creator['broker_created_payload'] is False,
             'INDEPENDENT_FIXED_COMPLETE_PAYLOAD_CREATOR_REQUIRED')
        c=creator['creator']
        need(type(c) is dict and set(c)=={'pid','pidfd_device','pidfd_inode','waitid_code','waitid_status','actual_reaped'} and
             number(c['pid'],2,2**31-1) and number(c['pidfd_device'],1) and number(c['pidfd_inode'],1) and
             c['waitid_code']==1 and c['waitid_status']==0 and c['actual_reaped'] is True,
             'ACTUAL_ORIGINAL_PAYLOAD_CREATOR_MUST_BE_REAPED')
        m=creator['material'];b=m.get('material') if type(m) is dict else None
        need(type(m) is dict and set(m)=={'schema','kind','package','run_id','version_code','apk_bytes','apk_sha256',
             'certificate_sha256','material','guest_staging_used','installation_authority'} and
             m['schema']=='droidloom.native-leaf-fixture-material.v2' and m['kind']==creator['kind'] and
             m['package']==spec['package'] and m['run_id']==spec['run_id'] and m['version_code']==1 and
             m['apk_bytes']==spec['apk']['bytes'] and m['apk_sha256']==spec['apk']['sha256'] and
             m['certificate_sha256']==spec['certificate_sha256'] and m['guest_staging_used'] is False and
             m['installation_authority'] is False and type(b) is dict and set(b)=={'schema','kind','package','manifest',
             'members','installation_authority','Main_authority','whole_app_business_accepted'} and
             b['schema']=='droidloom.held-prebuilt-helper-material.v2' and b['kind']==spec['kind'] and
             b['package']==spec['package'] and b['installation_authority'] is False and b['Main_authority'] is False and
             b['whole_app_business_accepted'] is False,'ACTUAL_HELD_CURRENT_GENERATION_MATERIAL_REQUIRED')
        sources={FIXTURE_ROOT+'/'+spec['kind']+'/'+n:{'path':FIXTURE_ROOT+'/'+spec['kind']+'/'+n,**p}
                 for n,p in spec['members'].items()}
        need(b['manifest']==sources[FIXTURE_ROOT+'/'+spec['kind']+'/MANIFEST.json'] and
             type(b['members']) is list and len(b['members'])==len(sources),'COMPLETE_FIXED_SOURCE_MEMBER_ROSTER_REQUIRED')
        seen=set()
        for row in b['members']:
            need(type(row) is dict and set(row)=={'source','actual_inode'} and type(row['source']) is dict,
                 'HELD_FIXED_SOURCE_MEMBER_COMPARISON_REQUIRED')
            path=row['source'].get('path');i=row['actual_inode']
            need(path in sources and path not in seen and row['source']==sources[path] and
                 type(i) is list and len(i)==9 and all(type(n) is int for n in i) and i[0]>0 and i[1]>0 and
                 i[2]==stat.S_IFREG|0o444 and i[3]==i[4]==0 and i[5]==1 and i[6]==sources[path]['bytes'],
                 'ACTUAL_SOURCE_INODE_OR_COMPLETE_SIGNED_BYTES_DIFFER')
            seen.add(path)
        if action=='state':
            s=t['state'];need(type(s) is dict and set(s)=={'stdout','stderr','receipt'},'ACTUAL_FIXED_STATE_READ_REQUIRED')
            raw=_fixture_bytes(s['stdout'],262144);need(_fixture_bytes(s['stderr'],262144)==b'','FIXTURE_STATE_STDERR_NOT_EMPTY')
            _apk_query_receipt(s['receipt'],raw,'fixture_state',15000)
            self.last_state=validate_fixture_state(raw,spec,app,wrapper['actual_data'])
        else:need(t['state'] is None,'STATE_RESULT_WITH_WRONG_FIXED_ACTION')
        return wrapper
    def _request(self,action):
        self.local();opcode={'begin':b'B','guard':b'H','state':b'S','retire':b'D'}[action]
        try:
            self.channel.guard();value=self.channel._read_fixed_comparison(opcode)
            self._validate(value,action);self.channel.guard()
            self.last=value
            if action=='begin':self._begin=value
            if action=='retire':self.retired=True
            return parse(canonical(value))
        except BaseException:
            self.failed=True
            raise
    def begin(self):
        need(self._begin is None,'FIXED_INSTALLATION_CANNOT_BE_REPEATED')
        return self._request('begin')
    def guard(self):
        need(self._begin is not None,'FIXED_INSTALLATION_HAS_NOT_BEGUN')
        return self._request('guard')
    def state(self):
        need(self._begin is not None,'FIXED_INSTALLATION_HAS_NOT_BEGUN')
        comparison=self._request('state');value,body=self.last_state
        return parse(canonical(value)),body,comparison
    def prefs(self):
        value,body,comparison=self.state()
        if body is None:return None,comparison
        import xml.etree.ElementTree as ET
        need(b'<!DOCTYPE' not in body and b'<!ENTITY' not in body,'NO_DTD_IN_FIXED_PREFERENCE_BODY')
        root=ET.fromstring(body);need(root.tag=='map' and not root.attrib,'FIXED_PREFERENCE_MAP_REQUIRED')
        result={}
        for item in root:
            key=item.get('name');need(key and key not in result and len(item)==0,'FIXED_PREFERENCE_KEYS_MUST_BE_UNIQUE')
            if item.tag=='string':
                need(set(item.attrib)=={'name'},'FIXED_STRING_PREFERENCE_ATTRIBUTES');result[key]=item.text or ''
            elif item.tag in ('int','long'):
                need(set(item.attrib)=={'name','value'} and re.fullmatch(r'-?[0-9]+',item.get('value','')),
                     'FIXED_INTEGER_PREFERENCE_REQUIRED');result[key]=int(item.get('value'))
            else:raise RuntimeError('UNKNOWN_OWNED_PREFERENCE_TYPE')
        need(result.get('run')==self.spec['run_id'],'FIXED_PREFERENCE_RUN_CHANGED')
        return result,comparison
    def identity(self,refresh=True):
        if refresh:self.guard()
        need(self._begin is not None,'ACTUAL_FIXTURE_IDENTITY_UNAVAILABLE')
        app=self._begin['transaction']['helper'];apk=app['apks'][0];data=self._begin['actual_data']
        return {'package':app['package'],'uid':app['uid'],'version_code':app['version_code'],
            'apk_path':apk['path'],'apk_sha256':apk['sha256'],'apk_bytes':apk['bytes'],
            'directories':{name:{'st_dev':d['device'],'st_ino':d['inode'],'st_mode':d['mode'],
                'st_uid':d['host_uid'],'st_gid':d['host_gid']} for name,d in zip(('ce','de'),data['directories'][2:])}}
    def retire(self):
        need(self._begin is not None,'ONLY_THE_ACTUAL_NEW_FIXTURE_CAN_BE_RETIRED')
        return self._request('retire')

def fixture_phase_budget(original_business,original_cleanup):
    # These are the two existing source-owned activity/cleanup windows. The
    # actual Rust route still owns the absolute case deadline and authority.
    need((original_business,original_cleanup) in ((600,120),(750,150)),
         'ONLY_FIXED_EXISTING_FIXTURE_PHASES')
    return (original_business+FIXTURE_LIMITS['begin'],original_cleanup+FIXTURE_LIMITS['retire'])

def fixed_original_identity(channel,package,expected_sha,expected_uid=None,expected_code=1):
    """Compare an original role through its existing complete-APK owner."""
    apk=channel.apk_custody();ordinal=apk.role(package);app=apk.value['packages'][ordinal]['application']
    need(app['version_code']==expected_code and (expected_uid is None or app['uid']==expected_uid) and
         len(app['apks'])==1 and app['apks'][0]['sha256']==expected_sha,'ORIGINAL_ROLE_IDENTITY_CHANGED')
    apk.guard(full=True);apk.package_read('identity',package);apk.package_read('paths',package)
    a=app['apks'][0]
    value={'package':package,'uid':app['uid'],'version_code':app['version_code'],'apk_path':a['path'],
           'apk_sha256':a['sha256'],'apk_bytes':a['bytes']}
    if package==channel.core['application']['package']:
        # The primary directories remain borrowed from the original Rust
        # working-data owner; other source roles receive no invented data facts.
        channel.guard()
        value['directories']={name:{'st_dev':d['device'],'st_ino':d['inode'],'st_mode':d['mode'],
            'st_uid':d['host_uid'],'st_gid':d['host_gid']}
            for name,d in zip(('ce','de'),channel.core['data']['directories'][2:])}
    return value

class ComparisonChannel:
    def __init__(self):
        self.pid=os.getpid()
        values=[]
        for key in (FACTS_ENV,GUARD_ENV):
            raw=os.environ.get(key,'')
            need(raw.isdecimal() and len(raw)<=10 and 3<=int(raw)<2**31,
                 'NORMAL_RUST_LEAF_CHANNEL_REQUIRED')
            values.append(int(raw))
        self.facts_fd,self.guard_fd=values
        need(self.facts_fd!=self.guard_fd,'DISTINCT_NORMAL_COMPARISON_DESCRIPTORS')
        # They remain borrowed from the actual invocation. No duplicate survives
        # a single check, and neither original is closed by a comparison object.
        for fd in values:os.set_inheritable(fd,False)
        self.before=metadata(self.facts_fd)
        st=os.fstat(self.facts_fd)
        need(stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==0 and st.st_nlink==0 and
             0<st.st_size<=MAX_FACTS and
             fcntl.fcntl(self.facts_fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY and
             fcntl.fcntl(self.facts_fd,fcntl.F_GET_SEALS)==SEALS,
             'SEALED_READONLY_NORMAL_COMPARISON_MEMFD_REQUIRED')
        self.raw=os.pread(self.facts_fd,MAX_FACTS+1,0)
        need(len(self.raw)==st.st_size and metadata(self.facts_fd)==self.before,
             'COMPLETE_NORMAL_COMPARISON_MEMFD_REQUIRED')
        envelope=parse(self.raw)
        need(type(envelope) is dict and set(envelope)=={
            'schema','baseline','normal_source_recipe','host_source_entries','user_zero_package_inventory','working_source_owner',
            'deadline_monotonic_ns','comparison_only'} and
            envelope['schema']=='droidloom.native-leaf-channel.v1' and
            envelope['comparison_only'] is True and
            number(envelope['deadline_monotonic_ns'],1) and
            0<envelope['deadline_monotonic_ns']-time.monotonic_ns()<=7200*10**9,
            'ORIGINAL_NORMAL_LEAF_ABSOLUTE_DEADLINE_REQUIRED')
        self.deadline_ns=envelope['deadline_monotonic_ns']
        self.core=validate_core(envelope['baseline'])
        self.working_source_owner=envelope['working_source_owner']
        need(self.working_source_owner is None or type(self.working_source_owner) is dict,
             'NORMAL_WORKING_SOURCE_COMPARISON_TYPE_REQUIRED')
        self.user_zero_package_inventory=envelope['user_zero_package_inventory']
        self.user_zero_records=inventory_table(self.user_zero_package_inventory,self.core)
        self.normal_host_release=self.core['main']['normal_host_release']
        self.normal_source_recipe=envelope['normal_source_recipe']
        need(type(self.normal_source_recipe) is dict and set(self.normal_source_recipe)=={'bytes','sha256'} and
             number(self.normal_source_recipe['bytes'],1,16*1024*1024) and
             type(self.normal_source_recipe['sha256']) is str and
             re.fullmatch('[0-9a-f]{64}',self.normal_source_recipe['sha256']),
             'SAME_COMPILED_NORMAL_SOURCE_RECIPE_REQUIRED')
        self.host_source_entries=envelope['host_source_entries']
        need(type(self.host_source_entries) is dict and set(self.host_source_entries)==HOST_CHILDREN,
             'EXACT_FIXED_HOST_SOURCE_ENTRY_SET_REQUIRED')
        for path,pin in self.host_source_entries.items():
            need(type(pin) is dict and set(pin)=={'path','bytes','sha256'} and pin['path']==path and
                 number(pin['bytes'],1,2*1024*1024) and type(pin['sha256']) is str and
                 re.fullmatch('[0-9a-f]{64}',pin['sha256']),
                 'EXACT_COMPILED_HOST_ENTRY_PIN_REQUIRED')
        self.guard_identity=metadata(self.guard_fd)
        need(stat.S_ISSOCK(os.fstat(self.guard_fd).st_mode),'PRIVATE_CHECK_ENDPOINT_REQUIRED')
        with socket.socket(fileno=os.dup(self.guard_fd)) as sock:
            need(sock.family==socket.AF_UNIX and sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)==socket.SOCK_DGRAM and
                 sock.getsockname() in ('',b'') and sock.getpeername() in ('',b''),
                 'UNNAMED_NORMAL_CHECK_SOCKETPAIR_REQUIRED')
        self.guard()

    def validate_inventory_comparison(self,value):
        # A stored pre-install table is compared explicitly by the fixed IHG
        # source/install chain. It is never a replacement for this live token.
        return inventory_table(value,self.core)

    @property
    def deadline(self):return self.deadline_ns/10**9
    def remaining(self,maximum=2):
        need(self.pid==os.getpid(),'COMPARISON_CHANNEL_CANNOT_BE_REUSED_AFTER_FORK')
        left=(self.deadline_ns-time.monotonic_ns())/10**9
        need(left>0,'ORIGINAL_NATIVE_LEAF_BUDGET_EXPIRED')
        return min(maximum,left)
    def guard(self):
        timeout=self.remaining()
        need(metadata(self.facts_fd)==self.before and
             metadata(self.guard_fd)==self.guard_identity and
             fcntl.fcntl(self.facts_fd,fcntl.F_GET_SEALS)==SEALS and
             os.pread(self.facts_fd,MAX_FACTS+1,0)==self.raw,
             'HELD_NORMAL_COMPARISON_DESCRIPTOR_CHANGED')
        with socket.socket(fileno=os.dup(self.guard_fd)) as sock:
            sock.settimeout(timeout)
            need(sock.send(b'G')==1,'NORMAL_CUSTODY_CHECK_NOT_SENT')
            raw,ancillary,flags,_=sock.recvmsg(2,0)
            need(raw==b'0' and not ancillary and flags==0,
                 'ACTUAL_NORMAL_CUSTODY_CHECK_FAILED')
        self.remaining()
        return {'schema':'droidloom.native-leaf-local-check.v1',
            'actual_main_epoch':self.core['main']['epoch'],
            'core_sha256':sha(canonical(self.core)),
            'local_held_peer_proc_namespace_data_checked':True,
            'fresh_full_main_rpc':False,'business_acceptance_evaluated':False}
    def preparation_reads(self):
        return PreparationReadChannel(self)

    def fixture(self):
        if not hasattr(self,'_fixed_fixture'):
            self._fixed_fixture=FixedFixture(self)
        return self._fixed_fixture

    def original_identity(self,package,expected_sha,expected_uid=None,expected_code=1):
        return fixed_original_identity(self,package,expected_sha,expected_uid,expected_code)

    def apk_custody(self):
        return OriginalApkCustody(self)

    def observe_running_engine(self):
        """Synchronize one parent-owned live observation after cleanup ownership.
        Only the sealed original work deadline bounds this wait. The parent
        keeps its fixed <=70-second request inside that same deadline.
        """
        end_ns=self.deadline_ns
        def left():
            self.remaining(7200)
            value=(end_ns-time.monotonic_ns())/10**9
            need(value>0,'ORIGINAL_RUNNING_ENGINE_WINDOW_EXPIRED')
            return value
        def held():
            need(metadata(self.facts_fd)==self.before and
                 metadata(self.guard_fd)==self.guard_identity and
                 fcntl.fcntl(self.facts_fd,fcntl.F_GET_SEALS)==SEALS and
                 os.pread(self.facts_fd,MAX_FACTS+1,0)==self.raw,
                 'HELD_NORMAL_COMPARISON_DESCRIPTOR_CHANGED')
        held()
        interrupted=None;reply=None;pending=False
        try:
            with socket.socket(fileno=os.dup(self.guard_fd)) as sock:
                try:
                    sock.settimeout(left())
                    # Mark before send: an interrupted send has unknown delivery.
                    # It is never resent, and an unsynchronized endpoint is retired.
                    pending=True
                    need(sock.send(b'E')==1,'FIXED_RUNNING_ENGINE_CHECK_NOT_SENT')
                    while reply is None:
                        sock.settimeout(left())
                        try:
                            reply=sock.recvmsg(2,0)
                        except OSError:
                            raise
                        except BaseException as error:
                            # Preserve a signal exception, but consume the one
                            # outstanding reply before the original finally sends G.
                            if interrupted is None:interrupted=error
                finally:
                    if pending and reply is None:
                        try:sock.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
                        os.environ.pop(GUARD_ENV,None)
                        try:os.close(self.guard_fd)
                        except OSError:pass
        except BaseException as error:
            if interrupted is not None and error is not interrupted:
                interrupted.add_note('RUNNING_ENGINE_REPLY_NOT_SYNCHRONIZED_ENDPOINT_RETIRED')
                raise interrupted from error
            raise
        if interrupted is not None:raise interrupted
        raw,ancillary,flags,_=reply
        need(raw==b'E' and not ancillary and flags==0,
             'ACTUAL_RUNNING_ENGINE_OBSERVATION_FAILED')
        left();held()
        # Consume the E reply before a subsequent local G. No new JSON/PID/UID/
        # ABI/path authority is returned; the real opaque fact stays in Rust.
        return None


    def _read_fixed_comparison(self, opcode, ordinal=None):
        """Receive one comparison from the retained parent's closed read set.
        This has no pathname listener, arbitrary request body or authority input.
        """
        need(type(opcode) is bytes and opcode in (b'I', b'P', b'L', b'C', b'A', b'V', b'R', b'B', b'H', b'S', b'D'),
             'FIXED_NATIVE_READ_OPCODE_REQUIRED')
        need(ordinal is None or (opcode in (b'I',b'P',b'L') and number(ordinal,0,2)),
             'FIXED_NATIVE_READ_ROLE_ORDINAL_REQUIRED')
        maximum=1048576 if opcode in (b'B',b'H',b'S',b'D') else MAX_FACTS
        request=opcode if ordinal is None else opcode+bytes((ordinal,))
        def held():
            self.remaining(7200)
            need(metadata(self.facts_fd)==self.before and
                 metadata(self.guard_fd)==self.guard_identity and
                 fcntl.fcntl(self.facts_fd,fcntl.F_GET_SEALS)==SEALS and
                 os.pread(self.facts_fd,MAX_FACTS+1,0)==self.raw,
                 'HELD_NORMAL_COMPARISON_DESCRIPTOR_CHANGED')
        def left():
            held()
            return self.remaining(7200)
        held()
        interrupted=None;reply=None;pending=False;received=[]
        itemsize=array.array('i').itemsize
        try:
            with socket.socket(fileno=os.dup(self.guard_fd)) as sock:
                try:
                    sock.settimeout(left())
                    # A send interrupted before acknowledgement is not retried.
                    pending=True
                    need(sock.send(request)==len(request),'FIXED_NATIVE_READ_NOT_SENT')
                    while reply is None:
                        sock.settimeout(left())
                        try:
                            reply=sock.recvmsg(2,socket.CMSG_SPACE(8*itemsize),
                                               socket.MSG_CMSG_CLOEXEC)
                        except OSError:
                            raise
                        except BaseException as error:
                            if interrupted is None:interrupted=error
                finally:
                    if pending and reply is None:
                        try:sock.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
                        os.environ.pop(GUARD_ENV,None)
                        try:os.close(self.guard_fd)
                        except OSError:pass
            token,ancillary,flags,_=reply
            proper=True
            for level,kind,data in ancillary:
                if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                    descriptors=array.array('i')
                    descriptors.frombytes(data[:len(data)-(len(data)%itemsize)])
                    received.extend(descriptors)
                    proper=proper and len(data)==itemsize
                else:
                    proper=False
            # Close all received descriptors even for a failed, interrupted,
            # truncated, foreign or malformed response.
            if interrupted is not None:raise interrupted
            need(token==opcode and flags&~socket.MSG_CMSG_CLOEXEC==0 and proper
                 and len(ancillary)==1 and len(received)==1,
                 'ACTUAL_FIXED_NATIVE_READ_COMPARISON_FAILED')
            fd=received[0]
            need(fd>=3 and fd not in (self.facts_fd,self.guard_fd),
                 'DISTINCT_FIXED_NATIVE_READ_DESCRIPTOR_REQUIRED')
            before=metadata(fd);st=os.fstat(fd)
            need(stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==0 and st.st_nlink==0
                 and 0<st.st_size<=maximum
                 and fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY
                 and fcntl.fcntl(fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC==fcntl.FD_CLOEXEC
                 and fcntl.fcntl(fd,fcntl.F_GET_SEALS)==SEALS,
                 'ACTUAL_SEALED_READONLY_COMPARISON_REQUIRED')
            raw=os.pread(fd,maximum+1,0)
            need(len(raw)==st.st_size and metadata(fd)==before
                 and fcntl.fcntl(fd,fcntl.F_GET_SEALS)==SEALS,
                 'COMPLETE_FIXED_NATIVE_READ_COMPARISON_REQUIRED')
            value=parse(raw)
            held()
            return value
        except BaseException as error:
            if interrupted is not None and error is not interrupted:
                interrupted.add_note('FIXED_NATIVE_READ_REPLY_FAILED_OR_ENDPOINT_RETIRED')
                raise interrupted from error
            raise
        finally:
            for fd in received:
                try:os.close(fd)
                except OSError:pass

    @contextmanager
    def _read_apk_copy(self):
        """Keep both actual received descriptors held through one copy."""
        opcode=b'N'
        def held():
            self.remaining(7200)
            need(metadata(self.facts_fd)==self.before and
                 metadata(self.guard_fd)==self.guard_identity and
                 fcntl.fcntl(self.facts_fd,fcntl.F_GET_SEALS)==SEALS and
                 os.pread(self.facts_fd,MAX_FACTS+1,0)==self.raw,
                 'HELD_NORMAL_COMPARISON_DESCRIPTOR_CHANGED')
        def left():
            held()
            return self.remaining(7200)
        held()
        interrupted=None;reply=None;pending=False;received=[]
        itemsize=array.array('i').itemsize
        try:
            with socket.socket(fileno=os.dup(self.guard_fd)) as sock:
                try:
                    sock.settimeout(left())
                    # A send interrupted before acknowledgement is not retried.
                    pending=True
                    need(sock.send(opcode)==1,'FIXED_NATIVE_APK_COPY_NOT_SENT')
                    while reply is None:
                        sock.settimeout(left())
                        try:
                            reply=sock.recvmsg(2,socket.CMSG_SPACE(8*itemsize),
                                               socket.MSG_CMSG_CLOEXEC)
                        except OSError:
                            raise
                        except BaseException as error:
                            if interrupted is None:interrupted=error
                finally:
                    if pending and reply is None:
                        try:sock.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
                        os.environ.pop(GUARD_ENV,None)
                        try:os.close(self.guard_fd)
                        except OSError:pass
            token,ancillary,flags,_=reply
            proper=True
            for level,kind,data in ancillary:
                if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                    descriptors=array.array('i')
                    descriptors.frombytes(data[:len(data)-(len(data)%itemsize)])
                    received.extend(descriptors)
                    proper=proper and len(data)==2*itemsize
                else:
                    proper=False
            # Close all received descriptors even for a failed, interrupted,
            # truncated, foreign or malformed response.
            if interrupted is not None:raise interrupted
            need(token==opcode and flags&~socket.MSG_CMSG_CLOEXEC==0 and proper
                 and len(ancillary)==1 and len(received)==2,
                 'ACTUAL_FIXED_NATIVE_APK_COPY_COMPARISON_FAILED')
            fd,copy_fd=received
            need(copy_fd>=3 and copy_fd not in (fd,self.facts_fd,self.guard_fd)
                 and fcntl.fcntl(copy_fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC==fcntl.FD_CLOEXEC,
                 'DISTINCT_ACTUAL_APK_COPY_DESCRIPTOR_REQUIRED')
            need(fd>=3 and fd not in (self.facts_fd,self.guard_fd),
                 'DISTINCT_FIXED_NATIVE_APK_COPY_DESCRIPTOR_REQUIRED')
            before=metadata(fd);st=os.fstat(fd)
            need(stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==0 and st.st_nlink==0
                 and 0<st.st_size<=MAX_FACTS
                 and fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY
                 and fcntl.fcntl(fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC==fcntl.FD_CLOEXEC
                 and fcntl.fcntl(fd,fcntl.F_GET_SEALS)==SEALS,
                 'ACTUAL_SEALED_READONLY_COMPARISON_REQUIRED')
            raw=os.pread(fd,MAX_FACTS+1,0)
            need(len(raw)==st.st_size and metadata(fd)==before
                 and fcntl.fcntl(fd,fcntl.F_GET_SEALS)==SEALS,
                 'COMPLETE_FIXED_NATIVE_APK_COPY_COMPARISON_REQUIRED')
            value=parse(raw)
            held()
            yield value,copy_fd
        except BaseException as error:
            if interrupted is not None and error is not interrupted:
                interrupted.add_note('FIXED_NATIVE_APK_COPY_REPLY_FAILED_OR_ENDPOINT_RETIRED')
                raise interrupted from error
            raise
        finally:
            for fd in received:
                try:os.close(fd)
                except OSError:pass

    def calendar_counts(self):
        self.guard()
        value=self._read_fixed_comparison(b'C')
        validate_calendar_counts_comparison(value,self.core,self.deadline_ns)
        self.guard()
        return value

    def inherit_for_host(self,argv,environment,pass_fds=()):
        self.guard()
        return inherit_for_host(argv,environment,pass_fds)
    def require_core(self,value):
        self.guard()
        need(value==self.core,'SAVED_NATIVE_LEAF_COMPARISON_DIFFERS_FROM_LIVE_OWNER')
        return self.guard()

def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None
def _absolute(value):
    return type(value) is str and len(value)<=4096 and value.startswith('/') and \
        '\0' not in value and all(p not in ('','.','..') for p in value.split('/')[1:])
def fixed_child(argv,pass_fds):
    """Pure exact call-shape selection. It grants no caller-selected command."""
    if type(argv) not in (list,tuple) or len(argv)<4:return None
    argv=list(argv)
    # The two real UI callers use -I without -B. Keep that exact source shape
    # separate from the three other fixed host children.
    if argv[:2]==['/usr/bin/python3','-I'] and argv[2] in UI_CHILDREN:
        entry=argv[2]
        need(len(argv)>=12 and argv[3] in ('client','backend') and
             argv[4]=='--scope' and _absolute(argv[5]) and
             argv[6]=='--expect-scope-sha256' and _hash(argv[7]) and
             argv[8]=='--step' and type(argv[9]) is str and
             re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',argv[9]) and
             argv[10]=='--command' and type(argv[11]) is str and
             re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',argv[11]) and
             ((argv[3]=='backend' and len(argv)==12) or
              (argv[3]=='client' and 13<=len(argv)<=128 and argv[12]=='--')) and
             not pass_fds,'EXACT_FIXED_UI_HOST_CHILD_REQUIRED')
        return entry,None
    if argv[:3]!=['/usr/bin/python3','-I','-B']:return None
    entry=argv[3]
    common=(len(argv)>=13 and argv[4]=='--preparation' and
        _absolute(argv[5]) and str(Path(argv[5]).parent)==str(ROOT/'preparations') and
        argv[6]=='--expect-preparation-sha256' and _hash(argv[7]))
    if entry==CLOCK_CHILD:
        need(common and len(argv)==19 and argv[8:10]==['execute-worker','--request'] and
             _absolute(argv[10]) and argv[11]=='--expect-request-sha256' and _hash(argv[12]) and
             argv[13]=='--monitor-fd' and type(argv[14]) is str and argv[14].isdecimal() and
             argv[15]=='--monitor-parent' and _absolute(argv[16]) and
             argv[17]=='--expect-monitor-parent-sha256' and _hash(argv[18]) and
             tuple(pass_fds)==(int(argv[14]),) and int(argv[14])>=3,
             'EXACT_CLOCK_WORKER_WITH_ITS_MONITOR_FD_REQUIRED')
        need(stat.S_ISSOCK(os.fstat(pass_fds[0]).st_mode),'ACTUAL_CLOCK_MONITOR_SOCKET_REQUIRED')
        return entry,None
    if entry==IHG_CHILD:
        coordinator=(common and len(argv)==13 and argv[8] in ('clock-worker','ihg-coordinator') and
            argv[9]=='--request' and _absolute(argv[10]) and
            argv[11]=='--expect-request-sha256' and _hash(argv[12]))
        phase=(common and len(argv)==15 and argv[8:10]==['ihg-worker','--scope'] and
            _absolute(argv[10]) and argv[11]=='--expect-scope-sha256' and _hash(argv[12]) and
            argv[13]=='--phase' and argv[14] in ('launch','inspect','cleanup'))
        need((coordinator or phase) and not pass_fds,'EXACT_IHG_HOST_WORKER_REQUIRED')
        return entry,None
    if type(entry) is str and re.fullmatch(r'/proc/self/fd/[0-9]+',entry):
        fd=int(entry.rsplit('/',1)[1])
        # This branch is only the already-held fixed Camera source, not a
        # delegation to another descriptor or arbitrary /proc executable.
        if not (common and len(argv)==13 and argv[8:10]==['execute','--request'] and
                _absolute(argv[10]) and argv[11]=='--expect-request-sha256' and _hash(argv[12]) and
                tuple(pass_fds)==(fd,) and fd>=3):
            return None
        need(os.readlink(entry)==CAMERA_CHILD,'ONLY_NAMED_FIXED_CAMERA_SOURCE_FD_MAY_INHERIT')
        return CAMERA_CHILD,fd
    return None

def verify_host_source(channel,path,held_fd=None):
    pin=channel.host_source_entries[path]
    source=Path(path);owned=[]
    try:
        parent=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);owned.append(parent)
        parents=[]
        for part in source.parts[1:-1]:
            child=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            owned.append(child);st=os.fstat(child)
            need(stat.S_ISDIR(st.st_mode) and st.st_uid==st.st_gid==0 and
                 stat.S_IMODE(st.st_mode)==0o755,'NORMAL_INSTALLED_HOST_SOURCE_PARENT_REQUIRED')
            parents.append((parent,part,child,(st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid)))
            parent=child
        fd=os.open(source.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);owned.append(fd)
        first=metadata(fd);st=os.fstat(fd)
        need(stat.S_ISREG(st.st_mode) and st.st_uid==st.st_gid==0 and st.st_nlink==1 and
             stat.S_IMODE(st.st_mode)==0o444 and st.st_size==pin['bytes'],
             'EXACT_INSTALLED_HOST_SOURCE_REQUIRED')
        if held_fd is not None:need(metadata(held_fd)==first,'HELD_CAMERA_SOURCE_DIFFERS_FROM_NAMED_RECIPE_SOURCE')
        raw=bytearray()
        while len(raw)<=pin['bytes']:
            channel.remaining();part=os.read(fd,min(65536,pin['bytes']+1-len(raw)))
            if not part:break
            raw.extend(part)
        need(len(raw)==pin['bytes'] and sha(raw)==pin['sha256'] and
             first==metadata(fd)==tuple(getattr(os.stat(source.name,dir_fd=parent,follow_symlinks=False),k) for k in META),
             'COMPILED_HOST_SOURCE_FULL_READBACK_REQUIRED')
        if held_fd is not None:need(metadata(held_fd)==first,'HELD_CAMERA_SOURCE_CHANGED')
        for directory,name,child,identity in parents:
            named=os.stat(name,dir_fd=directory,follow_symlinks=False);held=os.fstat(child)
            need(identity==(named.st_dev,named.st_ino,named.st_mode,named.st_uid,named.st_gid)==
                 (held.st_dev,held.st_ino,held.st_mode,held.st_uid,held.st_gid),
                 'HOST_SOURCE_PARENT_CHANGED')
    finally:
        for fd in reversed(owned):os.close(fd)

def inherit_for_host(argv,environment,pass_fds):
    """Only exact fixed host callers receive the two comparison descriptors."""
    env=dict(environment)
    for key in (FACTS_ENV,GUARD_ENV):env.pop(key,None)
    selected=fixed_child(argv,pass_fds)
    if selected is None:
        # In particular the seven-FD mapped namespace helper keeps exactly its
        # original authority set and receives no host-only comparison endpoint.
        return env,tuple(pass_fds)
    channel=ComparisonChannel();channel.guard()
    path,held_fd=selected
    verify_host_source(channel,path,held_fd)
    pair=(channel.facts_fd,channel.guard_fd)
    need(not set(pass_fds)&set(pair),'COMPARISON_AND_EXISTING_FDS_MUST_BE_DISTINCT')
    for key,fd in zip((FACTS_ENV,GUARD_ENV),pair):env[key]=str(fd)
    channel.guard()
    return env,tuple(pass_fds)+pair

PREPARATION_ENV='DROIDLOOM_NATIVE_PREPARATION_FD'
PREPARATION_NAMES=('guest-uid','guest-gid','boot-completed')
PREPARATION_KINDS=('guest_uid','guest_gid','boot_completed')
PREPARATION_TOKENS=(b'U',b'D',b'B')
PREPARATION_REPLY_LIMIT=131072

def validate_preparation_reply(value,core,name):
    """Comparison validation only; the Rust parent retains the opaque facts."""
    need(name in PREPARATION_NAMES,'EXACT_PREPARATION_DIAGNOSTIC_NAME')
    index=PREPARATION_NAMES.index(name)
    need(type(value) is dict and set(value)=={'schema','request','before_main','after_main',
         'stdout','stderr','stderr_bytes','stderr_sha256','receipt'} and
         value['schema']=='droidloom.preparation-read-reply.v1',
         'EXACT_NORMAL_PREPARATION_REPLY_REQUIRED')
    request=value['request']
    need(type(request) is dict and set(request)=={'schema','main','application','kind','deadline_monotonic_ns'}
         and request['schema']=='droidloom.preparation-read-request.v1'
         and request['main']==value['before_main']==value['after_main']==core['main']
         and request['application']==core['application'] and request['kind']==PREPARATION_KINDS[index]
         and number(request['deadline_monotonic_ns'],1),'SAME_ACTUAL_PREPARATION_MAIN_AND_PACKAGE')
    for key in ('stdout','stderr'):
        need(type(value[key]) is list and len(value[key])<=4096 and
             all(number(v,0,255) for v in value[key]),'COMPLETE_PREPARATION_OUTPUT_BYTES_REQUIRED')
    out,err=bytes(value['stdout']),bytes(value['stderr'])
    need(value['stderr_bytes']==len(err) and value['stderr_sha256']==sha(err),
         'COMPLETE_PREPARATION_STDERR_REQUIRED')
    receipt=value['receipt']
    need(type(receipt) is dict and set(receipt)=={'schema','lifecycle','query_pid','query_waitid_code',
         'query_waitid_status','exec','output_bytes','output_sha256','elapsed_millis','cgroup_removed'}
         and receipt['schema']==2 and receipt['cgroup_removed'] is True
         and number(receipt['query_pid'],2,2**31-1)
         and receipt['query_waitid_code'] in (1,2,3)
         and number(receipt['query_waitid_status'],0,255)
         and receipt['output_bytes']==len(out) and receipt['output_sha256']==sha(out)
         and number(receipt['elapsed_millis'],0,15000),'ACTUAL_PREPARATION_RETIREMENT_COMPARISON_REQUIRED')
    life=receipt['lifecycle'];stdio=life.get('stdio_creator') if type(life) is dict else None
    need(type(life) is dict and set(life)=={'owner','factory_pid','factory_tid','factory_pidfd_device',
         'factory_pidfd_inode','query_pidfd_device','query_pidfd_inode','stdio_creator','release_acknowledged'}
         and life['owner']=='instance_factory' and life['release_acknowledged'] is True
         and number(life['factory_pid'],2,2**31-1) and life['factory_pid']==life['factory_tid']
         and life['factory_pid']!=receipt['query_pid']
         and all(number(life[k],1) for k in ('factory_pidfd_device','factory_pidfd_inode',
             'query_pidfd_device','query_pidfd_inode'))
         and (life['factory_pidfd_device'],life['factory_pidfd_inode'])!=
             (life['query_pidfd_device'],life['query_pidfd_inode'])
         and type(stdio) is dict and set(stdio)=={'pid','waitid_code','waitid_status'}
         and number(stdio['pid'],2,2**31-1) and stdio['pid'] not in (receipt['query_pid'],life['factory_pid'])
         and stdio['waitid_code']==1 and stdio['waitid_status']==0,
         'ACTUAL_PREPARATION_FACTORY_AND_STDIO_RETIREMENT_REQUIRED')
    executed=receipt['exec'];node=executed.get('executable') if type(executed) is dict else None
    need(type(executed) is dict and set(executed)=={'query_start_ticks','original_parent_pid',
         'tracer_tid','waitid_code','waitid_status','event_previous_tid','executable',
         'executable_mount_id','executable_sha256','executable_selinux','process_selinux',
         'process_apparmor','uid','gid','no_new_privileges','seccomp_filter_mode'}
         and number(executed['query_start_ticks'],1) and executed['original_parent_pid']==life['factory_pid']
         and executed['tracer_tid']==life['factory_tid'] and executed['waitid_code']==4
         and executed['waitid_status']==(5|(4<<8)) and executed['event_previous_tid']==receipt['query_pid']
         and executed['process_selinux']=='u:r:droidloom_preparation_read:s0'
         and executed['process_apparmor']=='droidloom-production-android (enforce)'
         and executed['executable_selinux']=='u:object_r:droidloom_query_exec:s0'
         and number(executed['executable_mount_id'],1) and _hash(executed['executable_sha256'])
         and executed['no_new_privileges'] is True and executed['seccomp_filter_mode']==2
         and type(node) is dict and set(node)=={'dev','ino','mode','uid','gid','nlink','bytes',
             'mtime','mtime_nsec','ctime','ctime_nsec'}
         and number(node['dev'],1) and number(node['ino'],1) and node['mode']==stat.S_IFREG|0o555
         and node['nlink']==1 and number(node['bytes'],1) and
         executed['uid']==executed['gid']==node['uid']==node['gid'],
         'ACTUAL_PREPARATION_TRACEEXEC_AND_MAPPED_GUEST_ZERO_REQUIRED')
    return out,err

class PreparationReadChannel:
    def __init__(self,channel):
        self.channel=channel;self.pid=os.getpid();self.index=0;self.received=0;self.closed=0
        raw=os.environ.get(PREPARATION_ENV,'')
        need(raw.isdecimal() and len(raw)<=10 and 3<=int(raw)<2**31,'NORMAL_PREPARATION_CHANNEL_REQUIRED')
        self.fd=int(raw)
        need(self.fd not in (channel.facts_fd,channel.guard_fd),'DISTINCT_PREPARATION_ENDPOINT_REQUIRED')
        os.set_inheritable(self.fd,False);self.identity=metadata(self.fd)
        need(stat.S_ISSOCK(os.fstat(self.fd).st_mode),'PRIVATE_PREPARATION_SOCKET_REQUIRED')
        with socket.socket(fileno=os.dup(self.fd)) as sock:
            need(sock.family==socket.AF_UNIX and sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)==socket.SOCK_DGRAM
                 and sock.getsockname() in ('',b'') and sock.getpeername() in ('',b''),
                 'UNNAMED_PREPARATION_SOCKETPAIR_REQUIRED')
    def read(self,name):
        import array
        need(self.pid==os.getpid() and self.index<3 and name==PREPARATION_NAMES[self.index],
             'FIXED_PREPARATION_ORDER_AND_NO_RETRY_REQUIRED')
        need(metadata(self.fd)==self.identity,'PREPARATION_ENDPOINT_CHANGED')
        self.channel.guard();fds=[];reply=None
        token=PREPARATION_TOKENS[self.index];self.index+=1
        try:
            with socket.socket(fileno=os.dup(self.fd)) as sock:
                sock.settimeout(self.channel.remaining(15))
                # The command is attempted before send; interrupted/unknown
                # outcomes do not reset this index or resend an operation.
                need(sock.send(token)==1,'PREPARATION_REQUEST_NOT_SENT')
                reply=sock.recvmsg(2,socket.CMSG_SPACE(array.array('i').itemsize),socket.MSG_CMSG_CLOEXEC)
            raw,ancillary,flags,_=reply
            malformed=False
            for level,kind,data in ancillary:
                if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                    values=array.array('i');values.frombytes(data[:len(data)-len(data)%values.itemsize])
                    fds.extend(values);malformed|=len(data)%values.itemsize!=0
                else:malformed=True
            need(raw==b'R' and flags&~socket.MSG_CMSG_CLOEXEC==0 and not malformed and len(fds)==1,
                 'COMPLETE_NORMAL_PREPARATION_REPLY_FD_REQUIRED')
            fd=fds[0];self.received+=1;first=metadata(fd);info=os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_uid==info.st_gid==0 and info.st_nlink==0
                 and 0<info.st_size<=PREPARATION_REPLY_LIMIT
                 and fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY
                 and fcntl.fcntl(fd,fcntl.F_GET_SEALS)==SEALS,'SEALED_PREPARATION_REPLY_REQUIRED')
            body=os.pread(fd,PREPARATION_REPLY_LIMIT+1,0)
            need(len(body)==info.st_size and metadata(fd)==first,'COMPLETE_PREPARATION_REPLY_READBACK')
            value=parse(body);validate_preparation_reply(value,self.channel.core,name)
            need(time.monotonic_ns()<value['request']['deadline_monotonic_ns']<=self.channel.deadline_ns,
                 'ORIGINAL_PREPARATION_COMMAND_END_REQUIRED')
            self.channel.remaining();need(metadata(self.fd)==self.identity,'PREPARATION_ENDPOINT_CHANGED')
            return value
        finally:
            for fd in fds:
                os.close(fd);self.closed+=1
    def finish(self):
        need(self.pid==os.getpid() and self.index==self.received==self.closed==3,
             'ALL_ACTUAL_PREPARATION_REPLY_HANDLES_CLOSED')
        self.channel.guard()
        return {'sealed_reply_files_received':self.received,'sealed_reply_files_closed':self.closed,
                'remaining':0,'namespace_authority_transferred':False}
