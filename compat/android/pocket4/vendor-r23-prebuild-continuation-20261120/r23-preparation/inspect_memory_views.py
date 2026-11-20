from pathlib import Path
import os,json,time,resource,signal
resource.setrlimit(resource.RLIMIT_AS,(96*1024**2,96*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(5,5));signal.alarm(15)
values={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/meminfo').read_text().splitlines()}
namespaces={name:os.readlink('/proc/self/ns/'+name) for name in ('user','mnt','pid','net','ipc','uts','cgroup','time')}
own_cgroup=Path('/proc/self/cgroup').read_text()
root=Path('/sys/fs/cgroup')/own_cgroup.strip()[4:]
cg={}
for name in ('memory.max','memory.high','memory.current','memory.swap.current','memory.stat'):
 try:cg[name]=(root/name).read_text()
 except (OSError,ValueError) as error:cg[name]=type(error).__name__
mounts=[line for line in Path('/proc/self/mountinfo').read_text().splitlines() if line.split()[4] in ('/proc','/proc/meminfo','/sys/fs/cgroup')]
print(json.dumps({'observed_ns':time.time_ns(),'pid':os.getpid(),'ppid':os.getppid(),'uid':os.getuid(),'exe':os.readlink('/proc/self/exe'),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'MemAvailable':values['MemAvailable'],'MemTotal':values['MemTotal'],'MemFree':values['MemFree'],'Cached':values['Cached'],'Shmem':values['Shmem'],'AnonPages':values['AnonPages'],'SwapFree':values['SwapFree'],'self_namespaces':namespaces,'self_cgroup':own_cgroup,'own_memory_controls':cg,'relevant_mountinfo':mounts,'source_mutations':0,'runtime_qualified':False,'production_ready':False}),flush=True)
