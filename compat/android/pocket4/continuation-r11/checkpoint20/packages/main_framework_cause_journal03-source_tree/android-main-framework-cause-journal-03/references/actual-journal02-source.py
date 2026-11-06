#!/usr/bin/env python3
"""One fixed host-journal window; private records never leave this process.

SOURCE_ONLY until the exact request receives its actual terminal receipt.
No Android namespace entry, App operation, restart, epoch authorization, or retry.
"""
import hashlib,json,os,re,select,selectors,signal,stat,subprocess,time
DEADLINE=time.monotonic()+40
BOOT_ID="981ff371-cd72-4f81-9be3-a862111afdb1"
BOOT_COMPACT=BOOT_ID.replace("-","")
INVOCATION="67cdc2375f394012ad9d7f39b0d77426"
CG="/sys/fs/cgroup/system.slice/droidloomd.service"
SINCE="2026-11-06 04:35:00 UTC"
UNTIL="2026-11-06 04:47:30 UTC"
LOW_US=1793939700000000
HIGH_US=1793940450000000
PROPERTIES=('MainPID','ControlGroup','InvocationID','ActiveState','SubState','Result','NRestarts','ExecMainStartTimestampMonotonic','StateChangeTimestampMonotonic','MemoryCurrent','MemoryPeak','TasksCurrent')
STATUS_KEYS={'Uid','Gid','Groups','NSpid','CapInh','CapPrm','CapEff','CapBnd','CapAmb','Threads','State','PPid'}
EXPECTED=json.loads("{\"android_init\":{\"pid\":3588093,\"start_ticks\":80797014,\"ppid\":3588092,\"uids\":[0,0,0,0],\"namespace_pids\":[3588093,1],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533284]\",\"pid\":\"pid:[4026533288]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"daemon\":{\"pid\":3588022,\"start_ticks\":80796995,\"ppid\":1,\"uids\":[0,0,0,0],\"namespace_pids\":[3588022],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026531832]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"launcher\":{\"pid\":3588089,\"start_ticks\":80797013,\"ppid\":3588022,\"uids\":[0,0,0,0],\"namespace_pids\":[3588089],\"cgroup\":\"0::/system.slice/droidloomd.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533281]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"presenter\":{\"pid\":3588024,\"start_ticks\":80796995,\"ppid\":2472,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3588024],\"cgroup\":\"0::/user.slice/user-1000.slice/user@1000.service/app.slice/droidloom.service\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026531832]\",\"pid\":\"pid:[4026531836]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":66306,\"inode\":2}},\"surfaceflinger\":{\"pid\":3588912,\"start_ticks\":80797155,\"ppid\":3588093,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[3588912,672],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_1000/pid_672\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533284]\",\"pid\":\"pid:[4026533288]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"zygote64\":{\"pid\":90360,\"start_ticks\":96586437,\"ppid\":3588093,\"uids\":[0,0,0,0],\"namespace_pids\":[90360,1160345],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_0/pid_1160345\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533070]\",\"pid\":\"pid:[4026533288]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}},\"system_server\":{\"pid\":90516,\"start_ticks\":96586493,\"ppid\":90360,\"uids\":[1000,1000,1000,1000],\"namespace_pids\":[90516,1160408],\"cgroup\":\"0::/system.slice/droidloomd.service/system/uid_1000/pid_1160408\\n\",\"namespaces\":{\"mnt\":\"mnt:[4026533239]\",\"pid\":\"pid:[4026533288]\",\"user\":\"user:[4026531837]\"},\"root_identity\":{\"device\":106,\"inode\":1}}}")
LIMITS={"cpu.max":"200000 100000","memory.high":"5368709120","memory.max":"6442450944","memory.swap.max":"max","pids.max":"12288"}
SERVICE_SOURCE="Main_service"
KERNEL_SOURCE="host_kernel"
ENV={"PATH":"/usr/bin:/bin","LANG":"C","LC_ALL":"C","TZ":"UTC","SYSTEMD_PAGER":"","SYSTEMD_COLORS":"0"}
STDOUT_LIMIT=4*1024*1024
STDERR_LIMIT=16384
RECORD_LIMIT=8192
EVENT_LIMIT=64
LINE_LIMIT=65536
MESSAGE_LIMIT=16384
SOURCE_PINS={"Root_read02_source_sha256":"1fe8a4813901de264e17fd968244171f0e9458373fff936905e466ae8fe89fd7","Root_read02_stdout_sha256":"b49bbb4276c5a95de610956c878b0d23a1abdde0a8411bea310dbaca585396a6","original_development_source_sha256":"a66cc37191a5bc8d6aac7b55cdc6aba715e4ba8269ed13bc019608fe6c3f7869","original_control_source_sha256":"2edcbc5a75d48ceb7371bcaa3462c3acc43f119c2a3b81e806f4eae46be522cb"}

def need(v,m):
    if not v:raise RuntimeError(m)

def check():need(time.monotonic()<DEADLINE,'DIAGNOSTIC_DEADLINE')

def read(path,limit):
    check();fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        chunks=[];n=0
        while True:
            check();b=os.read(fd,min(8192,limit+1-n))
            if not b:break
            chunks.append(b);n+=len(b);need(n<=limit,'FIXED_READ_BOUND')
        return b''.join(chunks)
    finally:os.close(fd)

def statrow(pid):
    b=read('/proc/%d/stat'%pid,8192);at=b.rfind(b') ')
    need(at>0 and b[:at].startswith(str(pid).encode()+b' ('),'PROC_STAT_SCHEMA')
    f=b[at+2:].split();need(len(f)>=20,'PROC_STAT_FIELDS')
    return {'pid':pid,'start_ticks':int(f[19]),'state':f[0].decode('ascii'),'ppid':int(f[1])}

def process(pid,birth):
    row={'pid':pid,'expected_start_ticks':birth};held=None
    try:
        first=statrow(pid);row['before']=first
        if birth is not None:need(first['start_ticks']==birth,'ORIGINAL_PID_REUSED')
        held=os.pidfd_open(pid,0)
        poll=select.poll();poll.register(held,select.POLLIN)
        need(not poll.poll(0),'PROCESS_ALREADY_DEAD')
        status=read('/proc/%d/status'%pid,65536).decode('ascii','strict')
        row['status']={k:v.strip() for k,v in (line.split(':',1) for line in status.splitlines() if ':' in line) if k in STATUS_KEYS}
        row['cgroup']=read('/proc/%d/cgroup'%pid,8192).decode('ascii','strict')
        row['namespaces']={k:os.readlink('/proc/%d/ns/%s'%(pid,k)) for k in ('mnt','pid','user')}
        st=os.stat('/proc/%d/root'%pid);row['root_identity']={'device':st.st_dev,'inode':st.st_ino}
        last=statrow(pid);row['after']=last
        need(first['start_ticks']==last['start_ticks'] and not poll.poll(0),'PROCESS_CHANGED_DURING_READ')
        row['alive_identity_verified']=True
    except OSError as e:row['error']={'type':type(e).__name__,'errno':e.errno}
    except RuntimeError as e:row['error']={'type':type(e).__name__,'code':str(e)}
    finally:
        if held is not None:os.close(held)
    return row

def cg():
    rows={}
    for name in ('memory.current','memory.peak','memory.events','memory.events.local','memory.max','memory.high','memory.swap.current','memory.swap.peak','memory.swap.max','cpu.max','pids.current','pids.max','pids.events'):
        try:rows[name]=read(CG+'/'+name,8192).decode('ascii','strict').strip()
        except OSError as e:rows[name]={'errno':e.errno}
    return rows

def safe_error(error):
    row={"type":type(error).__name__}
    if isinstance(error,OSError):
        row["errno"]=error.errno
    elif isinstance(error,RuntimeError) and re.fullmatch(r"[A-Z0-9_]{1,96}",str(error)):
        row["code"]=str(error)
    else:
        row["code"]="UNEXPECTED_DIAGNOSTIC_FAILURE"
    return row

def bounded_command(argv,seconds,stdout_limit,stderr_limit):
    """Own one session; drain both pipes; kill before reap on every failed path."""
    check()
    need(type(seconds) is int and 1<=seconds<=8,"COMMAND_TIME_POLICY")
    started=time.monotonic()
    end=min(started+seconds,DEADLINE-4)
    need(end>started,"NO_COMMAND_BUDGET")
    record={"argv":argv,"pid":None,"returncode":None,"joined":False,
            "stdout_eof":False,"stderr_eof":False,"termination_attempted":False,
            "errors":[],"complete":False,"timed_out":False,"pipes_created":0,"pipes_closed":0,"selector_closed":False}
    buffers={"stdout":bytearray(),"stderr":bytearray()}
    hashes={"stdout":hashlib.sha256(),"stderr":hashlib.sha256()}
    seen={"stdout":0,"stderr":0}
    limits={"stdout":stdout_limit,"stderr":stderr_limit}
    child=None
    selector=selectors.DefaultSelector()
    pipes=[]
    try:
        child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,env=ENV,cwd="/",close_fds=True,start_new_session=True)
        record["pid"]=child.pid
        for name,pipe in (("stdout",child.stdout),("stderr",child.stderr)):
            pipes.append(pipe)
            record["pipes_created"]+=1
            os.set_blocking(pipe.fileno(),False)
            selector.register(pipe,selectors.EVENT_READ,name)
        while selector.get_map():
            need(time.monotonic()<end,"COMMAND_TIMEOUT")
            events=selector.select(min(.1,max(0,end-time.monotonic())))
            for key,_ in events:
                name=key.data
                try:
                    part=os.read(key.fileobj.fileno(),min(65536,limits[name]+1-seen[name]))
                except BlockingIOError:
                    continue
                if not part:
                    record[name+"_eof"]=True
                    selector.unregister(key.fileobj)
                    continue
                hashes[name].update(part)
                seen[name]+=len(part)
                keep=max(0,limits[name]-len(buffers[name]))
                buffers[name].extend(part[:keep])
                need(seen[name]<=limits[name],name.upper()+"_BOUND")
        child.wait(timeout=max(.01,min(1,end-time.monotonic())))
        record["joined"]=True
        record["returncode"]=child.returncode
    except BaseException as error:
        record["timed_out"]=isinstance(error,subprocess.TimeoutExpired) or (isinstance(error,RuntimeError) and str(error)=="COMMAND_TIMEOUT")
        record["errors"].append(safe_error(error))
    finally:
        # No poll() before this point: the child PID cannot have been reaped and
        # reused before a required group kill. journalctl has no pager or shell.
        if child is not None and child.returncode is None:
            record["termination_attempted"]=True
            try:
                os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException as error:
                record["errors"].append({"phase":"kill_owned_session",**safe_error(error)})
            try:
                child.wait(timeout=2)
                record["joined"]=True
                record["returncode"]=child.returncode
            except BaseException as error:
                record["errors"].append({"phase":"join_owned_child",**safe_error(error)})
        for pipe in pipes:
            try:
                pipe.close()
                record["pipes_closed"]+=1
            except BaseException as error:
                record["errors"].append({"phase":"close_owned_pipe",**safe_error(error)})
        try:
            selector.close()
            record["selector_closed"]=True
        except BaseException as error:
            record["errors"].append({"phase":"close_selector",**safe_error(error)})
        for name in ("stdout","stderr"):
            record[name+"_bytes_seen"]=seen[name]
            record[name+"_bytes_retained"]=len(buffers[name])
            record[name+"_sha256_seen"]=hashes[name].hexdigest()
        record["elapsed_ms"]=round((time.monotonic()-started)*1000,3)
        record["complete"]=bool(record["joined"] and record["returncode"]==0 and
                record["stdout_eof"] and record["stderr_eof"] and not record["errors"] and seen["stderr"]==0)
    return bytes(buffers["stdout"]),bytes(buffers["stderr"]),record

def service():
    argv=['/usr/bin/systemctl','show','droidloomd.service','--no-pager']+['--property='+p for p in PROPERTIES]
    out,err,record=bounded_command(argv,3,16384,8192)
    result={"command":record,"properties":None}
    if record["complete"]:
        lines=out.decode("ascii","strict").splitlines()
        need(all("=" in line for line in lines),"SERVICE_ROW_SCHEMA")
        pairs=[line.split("=",1) for line in lines]
        need(len(pairs)==len(PROPERTIES) and len({p[0] for p in pairs})==len(PROPERTIES),"SERVICE_ROW_DUPLICATE")
        rows=dict(pairs)
        need(set(rows)==set(PROPERTIES),"FIXED_SERVICE_FIELDS")
        result["properties"]=rows
    return result

def verify_service(value):
    need(value["command"]["complete"] and value["properties"] is not None,"FIXED_SERVICE_QUERY_FAILED")
    rows=value["properties"]
    need(rows["MainPID"]=="3588022" and rows["ControlGroup"]=="/system.slice/droidloomd.service" and
         rows["InvocationID"]==INVOCATION and rows["ActiveState"]=="active" and
         rows["SubState"]=="running" and rows["NRestarts"]=="0","MAIN_SERVICE_CHANGED")

def identity(row):
    need(row.get("alive_identity_verified") is True and "error" not in row,"FIXED_PROCESS_UNAVAILABLE")
    need(row["before"]["state"] not in ("Z","X") and row["after"]["state"] not in ("Z","X"),"FIXED_PROCESS_DEAD")
    need(row["before"]["ppid"]==row["after"]["ppid"] and
         row["before"]["start_ticks"]==row["after"]["start_ticks"],"FIXED_PROCESS_CHANGED")
    return {"pid":row["pid"],"start_ticks":row["before"]["start_ticks"],
            "ppid":row["before"]["ppid"],"uids":[int(x) for x in row["status"]["Uid"].split()],
            "namespace_pids":[int(x) for x in row["status"]["NSpid"].split()],
            "cgroup":row["cgroup"],"namespaces":row["namespaces"],"root_identity":row["root_identity"]}

def snapshot_processes():
    rows={}
    for role,expected in EXPECTED.items():
        row=process(expected["pid"],expected["start_ticks"])
        rows[role]=row
        need(identity(row)==expected,"FIXED_IDENTITY_DIFFERS_FROM_ACTUAL_READ02")
    return rows

def verify_limits(value):
    need(all(value.get(k)==v for k,v in LIMITS.items()),"ORIGINAL_MAIN_LIMITS_CHANGED")

def no_duplicates(pairs):
    out={}
    for key,value in pairs:
        need(key not in out,"DUPLICATE_JOURNAL_FIELD")
        out[key]=value
    return out

ROLE=r"(?:zygote64|zygote32|zygote|system_server|surfaceflinger|init)"
DEC=r"[0-9]{1,10}"
PATTERNS=[
 ("init_service_signal","init",re.compile(r"(?:init: )?Service '(?P<role>"+ROLE+r")' \(pid (?P<pid>"+DEC+r")\) (?:killed by|received) signal (?P<signal>[0-9]{1,3})(?: service ran [0-9]{1,10}(?:\.[0-9]{1,9})? seconds)?\.?")),
 ("init_service_exit","init",re.compile(r"(?:init: )?Service '(?P<role>"+ROLE+r")' \(pid (?P<pid>"+DEC+r")\) exited with status (?P<status>[0-9]{1,3})(?: service ran [0-9]{1,10}(?:\.[0-9]{1,9})? seconds)?\.?")),
 ("init_service_signal_sent","init",re.compile(r"(?:init: )?Sending signal (?P<signal>[0-9]{1,3}) to service '(?P<role>"+ROLE+r")' \(pid (?P<pid>"+DEC+r")\) process group\.\.\.")),
 ("init_service_start","init",re.compile(r"(?:init: )?starting service '(?P<role>"+ROLE+r")'\.\.\.")),
 ("init_service_restart","init",re.compile(r"(?:init: )?Service '(?P<role>"+ROLE+r")' is being restarted\.\.\.")),
 ("zygote_system_server_died","zygote",re.compile(r"(?:Zygote: )?System server process (?P<pid>"+DEC+r") has died\. Restarting Zygote!")),
 ("system_server_watchdog","system_server",re.compile(r"(?:Watchdog: )?\*\*\* WATCHDOG KILLING SYSTEM PROCESS: [^\r\n]{1,8192}")),
 ("kernel_oom_killed","kernel",re.compile(r"(?:Out of memory|Memory cgroup out of memory): Killed process (?P<pid>"+DEC+r") \((?P<role>"+ROLE+r")\) total-vm:[0-9]{1,16}kB, anon-rss:[0-9]{1,16}kB, file-rss:[0-9]{1,16}kB, shmem-rss:[0-9]{1,16}kB, UID:(?P<uid>[0-9]{1,10}) pgtables:[0-9]{1,16}kB oom_score_adj:-?[0-9]{1,4}")),
 ("system_role_fatal_signal","signal",re.compile(r"(?:libc: )?Fatal signal (?P<signal>[0-9]{1,3}) \((?:SIGABRT|SIGSEGV|SIGILL|SIGBUS|SIGKILL|SIGTERM|SIGFPE|SIGTRAP)\), code -?[0-9]{1,4}(?: \([A-Z0-9_]{1,32}\))?, fault addr (?:0x[0-9a-fA-F]{1,16}|-{3,4}) in tid (?P<tid>"+DEC+r") \([^()\r\n]{1,64}\), pid (?P<pid>"+DEC+r") \((?P<role>"+ROLE+r")\)"))
]
HOST_PIDS={"init":{3588093},"zygote":{3588887,90360},"zygote64":{3588887,90360},
           "zygote32":set(),"system_server":{3589120,90516},"surfaceflinger":{3588912}}
KNOWN_ROLE_TOKEN=re.compile(r"(?<![A-Za-z0-9_])"+ROLE+r"(?![A-Za-z0-9_])")
FIELDS="__REALTIME_TIMESTAMP,__MONOTONIC_TIMESTAMP,_BOOT_ID,_SYSTEMD_UNIT,_SYSTEMD_INVOCATION_ID,_TRANSPORT,_PID,MESSAGE"

def decimal(value,limit,optional=False):
    if value is None and optional:
        return None
    need(isinstance(value,str) and re.fullmatch(r"[0-9]{1,20}",value) is not None,"JOURNAL_NUMERIC_FIELD")
    number=int(value)
    need(0<=number<=limit,"JOURNAL_NUMERIC_BOUND")
    return number

def validate_record(row,source):
    need(isinstance(row,dict),"JOURNAL_RECORD_SCHEMA")
    need(row.get("_BOOT_ID")==BOOT_COMPACT,"JOURNAL_BOOT_MISMATCH")
    realtime=decimal(row.get("__REALTIME_TIMESTAMP"),2**64-1)
    mono=decimal(row.get("__MONOTONIC_TIMESTAMP"),2**64-1)
    need(LOW_US<=realtime<=HIGH_US,"JOURNAL_RECORD_OUTSIDE_FIXED_WINDOW")
    if source==SERVICE_SOURCE:
        need(row.get("_SYSTEMD_UNIT")=="droidloomd.service" and
             row.get("_SYSTEMD_INVOCATION_ID")==INVOCATION,"JOURNAL_SERVICE_BINDING")
    elif source==KERNEL_SOURCE:
        need(row.get("_TRANSPORT")=="kernel","JOURNAL_KERNEL_BINDING")
    else:
        raise RuntimeError("UNKNOWN_JOURNAL_SOURCE")
    pid=decimal(row.get("_PID"),2**31-1,optional=True)
    message=row.get("MESSAGE")
    need(isinstance(message,str),"JOURNAL_MESSAGE_NOT_TEXT")
    encoded=message.encode("utf-8","strict")
    need(len(encoded)<=MESSAGE_LIMIT,"JOURNAL_MESSAGE_BOUND")
    return realtime,mono,pid,message,encoded

def project_record(row,source,record_sha256):
    realtime,mono,source_pid,message,encoded=validate_record(row,source)
    selected=None
    for kind,family,pattern in PATTERNS:
        matched=pattern.fullmatch(message)
        if matched:
            need(selected is None,"AMBIGUOUS_EVENT_CLASSIFICATION")
            selected=(kind,family,matched)
    if selected is None:
        return None,bool(KNOWN_ROLE_TOKEN.search(message))
    kind,family,matched=selected
    values=matched.groupdict()
    role=values.get("role") or "system_server"
    need(role in HOST_PIDS,"UNKNOWN_SYSTEM_ROLE")
    numbers={name:int(value) for name,value in values.items() if name!="role" and value is not None}
    need(all(0<=n<=2**31-1 for n in numbers.values()),"EVENT_NUMERIC_BOUND")
    if "signal" in numbers:
        need(numbers["signal"]<=255,"EVENT_SIGNAL_BOUND")
    if "status" in numbers:
        need(numbers["status"]<=255,"EVENT_STATUS_BOUND")
    relation="service_invocation_only" if source==SERVICE_SOURCE else "kernel_role_unattributed"
    if source==SERVICE_SOURCE:
        if family=="init" and source_pid==3588093:
            relation="fixed_Main_init_host_pid"
        elif family=="zygote" and source_pid in HOST_PIDS["zygote"]:
            relation="fixed_Main_zygote_host_pid"
        elif family in ("system_server","signal") and source_pid in HOST_PIDS[role]:
            relation="fixed_Main_role_host_pid"
    elif kind=="kernel_oom_killed" and numbers.get("pid") in HOST_PIDS[role]:
        relation="fixed_historical_or_current_host_pid_and_role_match"
    event={"kind":kind,"role":role,"numbers":numbers,"source":source,
           "realtime_us":realtime,"monotonic_us":mono,"journal_source_pid":source_pid,
           "Main_relation":relation,"record_sha256":record_sha256,
           "message_sha256":hashlib.sha256(encoded).hexdigest(),"message_bytes":len(encoded),
           "raw_message_exported":False,"cause_of_epoch_change_proved":False}
    return event,False

def reject_constant(_value):
    raise RuntimeError("JOURNAL_NONFINITE_JSON")

def project_stream(raw,source,stream_complete):
    report={"records_parsed":0,"events":[],"unclassified_records":0,
            "unclassified_known_role_records":0,"unclassified_known_role_record_hashes":[],
            "errors":[],"all_retained_bytes_parsed":False,
            "fixed_window_query_complete":False,"retention_completeness_proved":False}
    lines=raw.splitlines(keepends=True)
    for line in lines:
        if not line.endswith(b"\n"):
            report["errors"].append({"code":"JOURNAL_FINAL_LINE_INCOMPLETE","sha256":hashlib.sha256(line).hexdigest()})
            break
        try:
            need(len(line)<=LINE_LIMIT,"JOURNAL_LINE_BOUND")
            need(report["records_parsed"]<RECORD_LIMIT,"JOURNAL_RECORD_BOUND")
            row=json.loads(line,object_pairs_hook=no_duplicates,parse_constant=reject_constant)
            digest=hashlib.sha256(line).hexdigest()
            event,known=project_record(row,source,digest)
            report["records_parsed"]+=1
            if event is not None:
                need(len(report["events"])<EVENT_LIMIT,"JOURNAL_EVENT_BOUND")
                report["events"].append(event)
            else:
                report["unclassified_records"]+=1
                if known:
                    report["unclassified_known_role_records"]+=1
                    if len(report["unclassified_known_role_record_hashes"])<8:
                        report["unclassified_known_role_record_hashes"].append(digest)
        except BaseException as error:
            report["errors"].append({**safe_error(error),"sha256":hashlib.sha256(line).hexdigest()})
            break
    report["all_retained_bytes_parsed"]=not report["errors"]
    report["fixed_window_query_complete"]=bool(stream_complete and report["all_retained_bytes_parsed"])
    return report

def journal_argv(source):
    argv=["/usr/bin/journalctl","--no-pager","--quiet","--utc","--all",
          "--boot="+BOOT_COMPACT,"--since="+SINCE,"--until="+UNTIL,
          "--output=json","--output-fields="+FIELDS]
    if source==SERVICE_SOURCE:
        return argv+["_SYSTEMD_UNIT=droidloomd.service","_SYSTEMD_INVOCATION_ID="+INVOCATION]
    need(source==KERNEL_SOURCE,"UNKNOWN_JOURNAL_SOURCE")
    return argv+["_TRANSPORT=kernel"]

def journal(source):
    out,err,command=bounded_command(journal_argv(source),8,STDOUT_LIMIT,STDERR_LIMIT)
    projection=project_stream(out,source,command["complete"])
    del out,err
    return {"command":command,"projection":projection}

def pure_controls():
    """Twenty in-memory production-parser controls before proc or child access."""
    passed=[]
    private="PRIVATE_NONEXPORT_SENTINEL"
    def row(message,source=SERVICE_SOURCE,pid="3588093"):
        value={"_BOOT_ID":BOOT_COMPACT,"__REALTIME_TIMESTAMP":str(LOW_US+1),
               "__MONOTONIC_TIMESTAMP":"965500000000","_PID":pid,"MESSAGE":message}
        if source==SERVICE_SOURCE:
            value.update(_SYSTEMD_UNIT="droidloomd.service",_SYSTEMD_INVOCATION_ID=INVOCATION)
        else:
            value["_TRANSPORT"]="kernel"
        return value
    def project(value,source=SERVICE_SOURCE):
        return project_record(value,source,"0"*64)[0]
    def ok(name,value):
        need(value,"PURE_CONTROL_FAILED")
        passed.append(name)
    def rejected(name,value,code,source=SERVICE_SOURCE):
        try:
            project(value,source)
        except RuntimeError as error:
            ok(name,str(error)==code)
        else:
            raise RuntimeError("PURE_NEGATIVE_CONTROL_ACCEPTED")
    value=project(row("init: Service 'zygote' (pid 508) killed by signal 9"))
    ok("fixed_init_signal",value["kind"]=="init_service_signal" and value["numbers"]=={"pid":508,"signal":9} and value["Main_relation"]=="fixed_Main_init_host_pid")
    value=project(row("Service 'zygote64' (pid 509) exited with status 1 service ran 120.123456789 seconds"))
    ok("fixed_init_exit",value["kind"]=="init_service_exit" and value["numbers"]["status"]==1)
    value=project(row("Zygote: System server process 710 has died. Restarting Zygote!",pid="3588887"))
    ok("zygote_system_server_death",value["kind"]=="zygote_system_server_died" and value["role"]=="system_server" and value["Main_relation"]=="fixed_Main_zygote_host_pid")
    value=project(row("Watchdog: *** WATCHDOG KILLING SYSTEM PROCESS: "+private,pid="3589120"))
    ok("watchdog_private_suffix_suppressed",value["kind"]=="system_server_watchdog" and private not in json.dumps(value) and value["cause_of_epoch_change_proved"] is False)
    oom="Out of memory: Killed process 3589120 (system_server) total-vm:100kB, anon-rss:80kB, file-rss:2kB, shmem-rss:0kB, UID:1000 pgtables:16kB oom_score_adj:-900"
    value=project(row(oom,KERNEL_SOURCE,"0"),KERNEL_SOURCE)
    ok("kernel_fixed_pid_role_match_only",value["Main_relation"]=="fixed_historical_or_current_host_pid_and_role_match" and value["cause_of_epoch_change_proved"] is False)
    value=project(row(oom.replace("3589120","123456"),KERNEL_SOURCE,"0"),KERNEL_SOURCE)
    ok("kernel_foreign_pid_unattributed",value["Main_relation"]=="kernel_role_unattributed")
    fatal="libc: Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr -------- in tid 42 (watchdog), pid 90516 (system_server)"
    fatal=fatal.replace("--------","----")
    value=project(row(fatal,pid="90516"))
    ok("fatal_signal_fixed_role",value["kind"]=="system_role_fatal_signal" and value["numbers"]["signal"]==6)
    rejected("foreign_boot",dict(row("unknown"),_BOOT_ID="0"*32),"JOURNAL_BOOT_MISMATCH")
    rejected("foreign_invocation",dict(row("unknown"),_SYSTEMD_INVOCATION_ID="0"*32),"JOURNAL_SERVICE_BINDING")
    rejected("foreign_service",dict(row("unknown"),_SYSTEMD_UNIT="other.service"),"JOURNAL_SERVICE_BINDING")
    rejected("wrong_kernel_transport",dict(row("unknown",KERNEL_SOURCE),_TRANSPORT="stdout"),"JOURNAL_KERNEL_BINDING",KERNEL_SOURCE)
    rejected("fixed_time_window",dict(row("unknown"),__REALTIME_TIMESTAMP=str(HIGH_US+1)),"JOURNAL_RECORD_OUTSIDE_FIXED_WINDOW")
    rejected("numeric_metadata_schema",dict(row("unknown"),_PID="1 "+private),"JOURNAL_NUMERIC_FIELD")
    rejected("binary_message_not_exported",dict(row("unknown"),MESSAGE=[1,2,3]),"JOURNAL_MESSAGE_NOT_TEXT")
    rejected("message_byte_bound",row("x"*(MESSAGE_LIMIT+1)),"JOURNAL_MESSAGE_BOUND")
    value=project(row(private+" init: Service 'zygote' (pid 508) killed by signal 9"))
    ok("prefixed_message_no_false_event",value is None)
    value=project(row("init: Service 'com.private.account' (pid 508) killed by signal 9"))
    ok("unknown_role_never_exported",value is None)
    try:
        json.loads('{"MESSAGE":"a","MESSAGE":"b"}',object_pairs_hook=no_duplicates)
    except RuntimeError as error:
        ok("duplicate_json_fields",str(error)=="DUPLICATE_JOURNAL_FIELD")
    else:
        raise RuntimeError("PURE_NEGATIVE_CONTROL_ACCEPTED")
    raw=(json.dumps(row("init: starting service 'zygote'..."),sort_keys=True)+"\n").encode()
    value=project_stream(raw[:-1],SERVICE_SOURCE,False)
    ok("partial_line_is_incomplete",not value["fixed_window_query_complete"] and value["errors"][0]["code"]=="JOURNAL_FINAL_LINE_INCOMPLETE")
    value=project_stream(raw*(EVENT_LIMIT+1),SERVICE_SOURCE,True)
    ok("event_bound_never_false_complete",not value["fixed_window_query_complete"] and len(value["events"])==EVENT_LIMIT and value["errors"][0]["code"]=="JOURNAL_EVENT_BOUND")
    need(len(passed)==20,"PURE_CONTROL_COUNT")
    return {"passed":len(passed),"cases":passed,"filesystem_access":False,"subprocesses":0,"device_operations":0}

def main():
    result={"schema":1,"kind":"fixed-Main-framework-cause-host-journal02",
            "window":{"since_utc":SINCE,"until_utc":UNTIL,"low_realtime_us":LOW_US,"high_realtime_us":HIGH_US},
            "old_epoch_sha256":"48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f",
            "source_pins":SOURCE_PINS,"errors":[],"secondary_errors":[],"journals":{},
            "Main_mutations":0,"Android_commands":0,"namespace_entry":False,
            "raw_journal_exported":False,"raw_UI_read":False,
            "old_epoch_reauthorized":False,"new_epoch_authorized":False,
            "system_server_cause_proved":False,"automatic_retry":False,
            "held_pidfds_acquired":0,"held_pidfds_closed":0,
            "fixed_process_observations_unchanged":False,
            "journal_retention_completeness_proved":False}
    held=[]
    entered=False
    def remember(phase,error,secondary=False):
        result["secondary_errors" if secondary else "errors"].append({"phase":phase,**safe_error(error)})
    try:
        result["pure_controls"]=pure_controls()
        result["boot_id_before"]=read("/proc/sys/kernel/random/boot_id",128).decode("ascii","strict").strip()
        need(result["boot_id_before"]==BOOT_ID,"HOST_BOOT_CHANGED")
        result["service_before"]=service()
        verify_service(result["service_before"])
        result["cgroup_before"]=cg()
        verify_limits(result["cgroup_before"])
        result["fixed_processes_before"]=snapshot_processes()
        for role,expected in EXPECTED.items():
            fd=os.pidfd_open(expected["pid"],0)
            held.append((role,fd))
            result["held_pidfds_acquired"]+=1
            poll=select.poll()
            poll.register(fd,select.POLLIN)
            need(not poll.poll(0) and statrow(expected["pid"])["start_ticks"]==expected["start_ticks"],"FIXED_PROCESS_CHANGED_WHILE_HOLDING")
        entered=True
        for source in (SERVICE_SOURCE,KERNEL_SOURCE):
            check()
            for role,fd in held:
                poll=select.poll()
                poll.register(fd,select.POLLIN)
                need(not poll.poll(0),"FIXED_PROCESS_EXITED_BEFORE_JOURNAL")
            section=journal(source)
            result["journals"][source]=section
            if not section["command"]["complete"] or not section["projection"]["fixed_window_query_complete"]:
                result["errors"].append({"phase":source,"code":"JOURNAL_QUERY_OR_PROJECTION_INCOMPLETE"})
    except BaseException as error:
        remember("primary",error)
    finally:
        # Independent final observations do not replace the first cause.
        if entered:
            for phase,operation in (
                ("fixed_processes_after",snapshot_processes),
                ("service_after",service),
                ("cgroup_after",cg),
                ("boot_id_after",lambda:read("/proc/sys/kernel/random/boot_id",128).decode("ascii","strict").strip())):
                try:
                    result[phase]=operation()
                except BaseException as error:
                    remember(phase,error,True)
            try:
                verify_service(result["service_after"])
                verify_limits(result["cgroup_after"])
                need(result["boot_id_after"]==BOOT_ID,"HOST_BOOT_CHANGED_AFTER_JOURNAL")
                need(all(identity(result["fixed_processes_before"][role])==identity(result["fixed_processes_after"][role])==expected for role,expected in EXPECTED.items()),"FIXED_PROCESS_OBSERVATION_CHANGED")
                result["fixed_process_observations_unchanged"]=True
            except BaseException as error:
                remember("final_binding",error,True)
        result["held_pidfds_live_before_close"]={}
        for role,fd in held:
            try:
                poll=select.poll()
                poll.register(fd,select.POLLIN)
                live=not bool(poll.poll(0))
                result["held_pidfds_live_before_close"][role]=live
                need(live,"FIXED_PROCESS_EXITED_DURING_JOURNAL")
            except BaseException as error:
                remember("final_pidfd_liveness",error,True)
            finally:
                try:
                    os.close(fd)
                    result["held_pidfds_closed"]+=1
                except BaseException as error:
                    remember("close_held_pidfd",error,True)
    result["deadline_met"]=time.monotonic()<DEADLINE
    result["complete_bounded_queries"]=bool(set(result["journals"])=={SERVICE_SOURCE,KERNEL_SOURCE} and all(x["command"]["complete"] and x["projection"]["fixed_window_query_complete"] for x in result["journals"].values()))
    result["ok"]=bool(not result["errors"] and not result["secondary_errors"] and
                      result["deadline_met"] and result["complete_bounded_queries"] and
                      result["fixed_process_observations_unchanged"] and
                      result["held_pidfds_acquired"]==result["held_pidfds_closed"]==7)
    raw=(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n").encode()
    need(len(raw)<=131072,"REPORT_BOUND")
    print(raw.decode(),end="",flush=True)
    return 0 if result["ok"] else 1

raise SystemExit(main())
