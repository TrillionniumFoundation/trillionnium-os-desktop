from pathlib import Path
import json,time,signal,resource,os
resource.setrlimit(resource.RLIMIT_AS,(64*1024**2,64*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(5,5));signal.alarm(70)
started=time.monotonic();rows=[]
for i in range(61):
 values={x.split(':',1)[0]:x.split(':',1)[1].strip() for x in Path('/proc/meminfo').read_text().splitlines()}
 row={'observed_ns':time.time_ns(),'available':int(values['MemAvailable'].split()[0])*1024,'free':int(values['MemFree'].split()[0])*1024,'cached':int(values['Cached'].split()[0])*1024,'shmem':int(values['Shmem'].split()[0])*1024}
 rows.append(row)
 if i%10==0:print(json.dumps({'sample':i,**row}),flush=True)
 if i<60:time.sleep(max(0,started+i+1-time.monotonic()))
print(json.dumps({'schema':'p4-r23-readonly-resource-stability-v1','samples':rows,'minimum_available':min(x['available'] for x in rows),'maximum_available':max(x['available'] for x in rows),'all_at_least_original_42_GiB':all(x['available']>=42*1024**3 for x in rows),'source_mutations':0,'build_admission_granted':False,'runtime_qualified':False,'production_ready':False}),flush=True)
