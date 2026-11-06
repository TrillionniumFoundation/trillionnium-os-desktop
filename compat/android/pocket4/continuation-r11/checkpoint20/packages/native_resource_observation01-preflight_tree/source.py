import json,os,stat,time
def need(value,reason):
    if not value: raise RuntimeError(reason)
need(os.getuid()==os.geteuid()==1000,'operator UID required')
fd=os.open('/proc/meminfo',os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW)
try:
    need(stat.S_ISREG(os.fstat(fd).st_mode),'meminfo regular proc file')
    raw=bytearray()
    while True:
        part=os.read(fd,min(4096,65537-len(raw)))
        if not part:break
        raw.extend(part)
        need(len(raw)<=65536,'meminfo bound')
finally:
    os.close(fd)
wanted={'MemTotal','MemAvailable','SwapTotal','SwapFree','SwapCached'}
values={}
for line in bytes(raw).decode('ascii','strict').splitlines():
    key,body=line.split(':',1)
    if key in wanted:
        fields=body.split()
        need(key not in values and len(fields)==2 and fields[0].isdigit() and fields[1]=='kB','meminfo field')
        values[key]=int(fields[0])*1024
need(set(values)==wanted,'exact five meminfo fields')
need(0<=values['MemAvailable']<=values['MemTotal'] and 0<=values['SwapFree']<=values['SwapTotal'],'meminfo ranges')
out={'schema':1,'kind':'native-build-resource-observation01','uid':os.getuid(),'observed_unix_ns':time.time_ns(),'memory_bytes':values,'source':'/proc/meminfo','fd_closed':True,'children':0,'Main_actions':0,'Android_actions':0,'build_authorized_by_observation':False,'production_ready':False}
body=(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n').encode()
need(len(body)<=4096,'output bound')
os.write(1,body)
