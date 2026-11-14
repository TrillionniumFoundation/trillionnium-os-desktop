"""Bounded WebView owner diagnostics. Main UID crash logs; owned renderer exits.
Only the actual observed main/renderer identity contract is accepted. Oldest
baseline exit eviction is distinct from loss of the observation interval.
"""
import hashlib,re,time
TARGETS={'org.chromium.webview_shell':10060}
PROCESSES={'org.chromium.webview_shell':{'org.chromium.webview_shell'}}
RENDERER='com.android.webview:sandboxed_process0:org.chromium.content.app.SandboxedProcessService0:0'
EXIT_KEYS=('timestamp','pid','uid','reason','process','package_uid','defining_uid','user','subreason')

def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()

def uid_census(session,record,label):
    raw=session.android(['/system/bin/pm','list','packages','-U','--user','0'],15)
    rows=[]
    for line in raw.decode().splitlines():
        m=re.fullmatch(r'package:([A-Za-z][A-Za-z0-9_.]*) uid:(\d+)',line)
        need(m is not None,'UID_CENSUS_UNPARSED_LINE');rows.append((m[1],int(m[2])))
    need(len(rows)==len({p for p,u in rows}),'UID_CENSUS_DUPLICATE_PACKAGE')
    matched={p:sorted(q for q,v in rows if v==u) for p,u in TARGETS.items()}
    need(all(matched[p]==[p] for p in TARGETS),'TARGET_UID_HAS_UNEXPECTED_PACKAGE_MEMBERS')
    proof={'target_uids':TARGETS,'same_uid_packages':matched,'total_packages':len(rows),'raw_sha256':sha(raw)}
    record(label,proof);return proof

def permissions(session,record,label):
    result={}
    for package in TARGETS:
        raw=session.android(['/system/bin/dumpsys','package',package],15).decode()
        blocks=re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)',raw,re.M|re.S)
        need(len(blocks)==1 and re.findall(r'^  Package \[([^]]+)\]',blocks[0],re.M)==[package],
            'PERMISSION_PACKAGE_SCOPE')
        lines=sorted(line.strip() for line in blocks[0].splitlines()
            if re.search(r'android\.permission\.[A-Za-z0-9_]+: granted=',line))
        need(lines,'PERMISSION_ROWS_EMPTY_OR_UNPARSED')
        result[package]={'permission_rows':lines,'rows_sha256':sha('\n'.join(lines).encode())}
    record(label,result);return result

def exit_rows(text,package,uid):
    need(package=='org.chromium.webview_shell' and uid==10060,'FIXED_WEBVIEW_TARGET')
    header='ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)'
    need(text.startswith(header),'EXIT_INFO_HEADER_UNKNOWN')
    blocks=re.split(r'(?=^\s*ApplicationExitInfo #\d+:)',text,flags=re.M)[1:]
    if not blocks:
        persisted=(r'Last Timestamp of Persistence Into Persistent Storage: '
            r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\n')
        explicit=r'[ \t]*(?:No records\.?|\(nothing\))[ \t]*\n?'
        need(re.fullmatch(re.escape(header)+r'\n(?:'+persisted+r'(?:'+explicit+r')?|'+explicit+r')',text) is not None,
            'EXIT_INFO_EMPTY_FORMAT_UNKNOWN')
    else:
        prefix=text[:text.index(blocks[0])]
        need(re.findall(r'^\s*package: (\S+)$',prefix,re.M)==[package] and
            re.findall(r'Historical Process Exit for uid=(\d+)',prefix)==[str(uid)],'EXIT_PACKAGE_OWNER_HEADER')
    patterns={'timestamp':r'\btimestamp=([^\n]+)','pid':r'\bpid=(\d+)',
        'uid':r'\brealUid=(\d+)','reason':r'\breason=(\d+)\s*\(','process':r'\bprocess=([^\s]+)',
        'package_uid':r'\bpackageUid=(\d+)','defining_uid':r'\bdefiningUid=(\d+)',
        'user':r'\buser=(\d+)','subreason':r'\bsubreason=(\d+)\s*\('}
    rows=[]
    for block in blocks:
        row={}
        for key,pattern in patterns.items():
            found=re.findall(pattern,block);need(len(found)==1,'EXIT_INFO_FIELD_UNKNOWN:'+key);row[key]=found[0].strip()
        main=(row['process']==package and int(row['uid'])==int(row['defining_uid'])==uid)
        renderer=(row['process']==RENDERER and 99000<=int(row['uid'])<=99999 and int(row['defining_uid'])==10071)
        need(int(row['package_uid'])==uid and row['user']=='0' and (main or renderer),'EXIT_OWNER_OR_PROCESS_OUTSIDE_SCOPE')
        rows.append(tuple(row[k] for k in EXIT_KEYS))
    need(len(rows)==len(set(rows)),'EXIT_RECORD_DUPLICATE')
    return rows

def exits(text,package,uid):return set(exit_rows(text,package,uid))

def exit_coverage(old_order,new_order):
    old_set=set(old_order)
    if not old_order:
        return {'retained_session_exit_history':len(new_order)<16,'baseline_oldest_suffix_evicted':0,
            'coverage_method':'empty baseline with fewer than observed 16-record retention bound'}
    first=next((i for i,row in enumerate(new_order) if row in old_set),None)
    retained=[] if first is None else new_order[first:]
    ok=(first is not None and retained==old_order[:len(retained)] and
        all(row not in old_set for row in new_order[:first]))
    return {'retained_session_exit_history':bool(ok),
        'baseline_oldest_suffix_evicted':len(old_order)-len(retained) if ok else None,
        'coverage_method':'new prefix plus unmodified recent baseline prefix; only oldest baseline suffix may be evicted'}

def timed_lines(text):
    rows=[];unknown=[]
    for line in text.splitlines():
        m=re.match(r'^\s*(\d+\.\d+)\s+',line)
        if m:rows.append((float(m[1]),line))
        elif line.strip() and not line.startswith('--------- beginning of '):unknown.append(line)
    return rows,unknown

def capture(session,record,label):
    clock=session.android(['/system/bin/date','+%s'],8).decode().strip()
    need(clock.isdecimal() and abs(time.time()-int(clock))<=3,'GUEST_CLOCK_NOT_BOUND')
    out={'guest_seconds':int(clock),'packages':{}}
    events=session.android(['/system/bin/logcat','-b','events','-d','-v','epoch','-t','2048'],15)
    need(len(events)<=4*1024*1024,'EVENT_LOG_BYTE_BOUND');out['events']=events.decode()
    for package,uid in TARGETS.items():
        exitraw=session.android(['/system/bin/dumpsys','activity','exit-info',package],15)
        crash=session.android(['/system/bin/logcat','--uid='+str(uid),'-b','crash','-d','-v','epoch','-t','512'],15)
        need(len(exitraw)<=1024*1024 and len(crash)<=1024*1024,'DIAGNOSTIC_BYTE_BOUND')
        item={'exits':exitraw.decode(),'crash':crash.decode()};exits(item['exits'],package,uid)
        out['packages'][package]=item
    record(label,out);return out

def compare(before,after):
    need(after['guest_seconds']>=before['guest_seconds'],'DIAGNOSTIC_CLOCK_REVERSED')
    since=before['guest_seconds'];results={};events,event_unknown=timed_lines(after['events'])
    event_coverage=not event_unknown and (len(events)<2048 or (events and min(t for t,l in events)<=since))
    for package,uid in TARGETS.items():
        initial=before['packages'][package];final=after['packages'][package]
        old_order=exit_rows(initial['exits'],package,uid);new_order=exit_rows(final['exits'],package,uid)
        old,new=set(old_order),set(new_order);added=new-old
        fatal=[r for r in added if int(r[3]) in (3,4,5,6,7)]
        crash,crash_unknown=timed_lines(final['crash'])
        recent_crash=[l for t,l in crash if t>=since]
        recent_events=[l for t,l in events if t>=since and re.search(r'\bam_(?:crash|anr)\s*:',l)
            and any(re.search(r'(?<![A-Za-z0-9_.:])'+re.escape(p)+r'(?![A-Za-z0-9_.:])',l) for p in PROCESSES[package])]
        crash_bound=not crash_unknown and (len(crash)<512 or (crash and min(t for t,l in crash)<=since))
        coverage=exit_coverage(old_order,new_order)
        results[package]={'android_uid':uid,'new_exit_events':len(added),
            'new_exit_records':[dict(zip(EXIT_KEYS,row)) for row in sorted(added)],
            'new_crash_or_anr_exits':len(fatal),'new_uid_crash_lines':len(recent_crash),
            'new_package_crash_anr_events':len(recent_events),'old_exit_records_retained':old<=new,
            'bounded_log_window_retained':bool(event_coverage and crash_bound),
            'no_new_crash_or_anr_observed':not(fatal or recent_crash or recent_events),
            'full_historical_or_external_log_reset_exclusion':False,
            'isolated_renderer_uid_log_buffers_collected':False,
            'raw_log_unknown_line_count':len(crash_unknown)+len(event_unknown),**coverage}
    return {'since_guest_seconds':since,'through_guest_seconds':after['guest_seconds'],
        'packages':results,'whole_app_production_ready':False,
        'no_new_crash_or_anr_observed':all(v['no_new_crash_or_anr_observed'] for v in results.values())}
