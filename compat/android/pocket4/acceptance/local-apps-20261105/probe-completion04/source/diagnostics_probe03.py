"""Bounded UID/package diagnostics; partial log coverage stays explicitly partial."""
import hashlib,re,time

TARGETS={'local.pocket4.fixture':10115}
PROCESSES={'local.pocket4.fixture':{'local.pocket4.fixture'}}

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

def exits(text,package,uid):
    need(text.startswith('ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)'),
        'EXIT_INFO_HEADER_UNKNOWN')
    blocks=re.split(r'(?=^\s*ApplicationExitInfo #\d+:)',text,flags=re.M)[1:]
    if not blocks:
        # Android's observed empty result consists of the complete dump header
        # and its persistence timestamp, without a package/record section.
        # Match the entire output so an unknown/truncated body is never empty.
        header=re.escape('ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)')
        persisted=(r'Last Timestamp of Persistence Into Persistent Storage: '
            r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\n')
        explicit=r'[ \t]*(?:No records\.?|\(nothing\))[ \t]*\n?'
        need(re.fullmatch(header+r'\n(?:'+persisted+r'(?:'+explicit+r')?|'+explicit+r')',text)
            is not None,'EXIT_INFO_EMPTY_FORMAT_UNKNOWN')
    out=set()
    patterns={'timestamp':r'\btimestamp=([^\n]+)','pid':r'\bpid=(\d+)',
        'uid':r'\brealUid=(\d+)','reason':r'\breason=(\d+)\s*\(','process':r'\bprocess=([^\s]+)'}
    for block in blocks:
        row={}
        for key,pattern in patterns.items():
            found=re.findall(pattern,block);need(len(found)==1,'EXIT_INFO_FIELD_UNKNOWN');row[key]=found[0].strip()
        need(int(row['uid'])==uid and row['process'] in PROCESSES[package],'EXIT_UID_OR_PROCESS_OUTSIDE_SCOPE')
        out.add(tuple(row[k] for k in patterns))
    return out

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
        old=exits(initial['exits'],package,uid);new=exits(final['exits'],package,uid)
        added=new-old;fatal=[r for r in added if int(r[3]) in (3,4,5,6,7)]
        crash,crash_unknown=timed_lines(final['crash'])
        recent_crash=[l for t,l in crash if t>=since]
        recent_events=[l for t,l in events if t>=since and re.search(r'\bam_(?:crash|anr)\s*:',l)
            and any(re.search(r'(?<![A-Za-z0-9_.:])'+re.escape(p)+r'(?![A-Za-z0-9_.:])',l) for p in PROCESSES[package])]
        crash_bound=not crash_unknown and (len(crash)<512 or (crash and min(t for t,l in crash)<=since))
        # We report bounded retained-buffer evidence, never proof against an
        # external log clear or omitted history. Engine/runtime qualification is separate.
        results[package]={'android_uid':uid,'new_exit_events':len(added),
            'new_crash_or_anr_exits':len(fatal),'new_uid_crash_lines':len(recent_crash),
            'new_package_crash_anr_events':len(recent_events),'old_exit_records_retained':old<=new,
            'bounded_log_window_retained':bool(event_coverage and crash_bound),
            'no_new_crash_or_anr_observed':not(fatal or recent_crash or recent_events),
            'full_historical_or_external_log_reset_exclusion':False,
            'raw_log_unknown_line_count':len(crash_unknown)+len(event_unknown)}
    return {'since_guest_seconds':since,'through_guest_seconds':after['guest_seconds'],
        'packages':results,'whole_app_production_ready':False,
        'no_new_crash_or_anr_observed':all(v['no_new_crash_or_anr_observed'] for v in results.values())}
