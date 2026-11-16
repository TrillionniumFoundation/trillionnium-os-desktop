import pathlib,json,hashlib,os,datetime
R=pathlib.Path('/data/pocket4-audio-source316-offload-20261108-8b88-r1')
recipe=R/'recipe-sdk33-zygote-r1'; C=R/'control/full-desktop-r13'; Q=R/'qualification/full-desktop-r13'
out={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'one static original file pin read; no status polling, no build actions'}
def ref(p,include=False):
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  a=os.fstat(fd);h=hashlib.sha256();chunks=[]
  while True:
   b=os.read(fd,1024*1024)
   if not b:break
   h.update(b)
   if include:chunks.append(b)
  z=os.fstat(fd)
  before=[a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns];after=[z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns]
  result={'path':str(p),'bytes':a.st_size,'sha256':h.hexdigest(),'identity_before':before,'identity_after':after,'stable_during_read':before==after}
  if include:result['text']=b''.join(chunks).decode('utf8')
  return result
 finally:os.close(fd)
lock=json.loads((recipe/'android/manifest/audio-bridge-source-lock.json').read_bytes())
out['sdk_zygote_selectors']=[{'path':x['path'],'commit':x['commit'],'sparse_paths':x['sparse_paths']} for x in lock['projects'] if x['path'] in ('prebuilts/sdk','system/zygote')]
out['source_delta']=ref(R/'control/source-sdk33-zygote-continuation-r1/origin-files/home/alex/work/pocket4-audio430-sdk33-zygote-20261109-8b88-r1/control/source-delta.json',True)
out['normal_command']=ref(Q/'commands/normal-full-audio-apex.json',True)
out['logs']=[ref(Q/'commands'/('normal-full-audio-apex.'+x)) for x in ('stdout','stderr')]
print(json.dumps(out,ensure_ascii=False))
