#!/usr/bin/env python3
"""Reassemble one retained input into a NEW directory, verifying every byte first."""
from pathlib import Path
import gzip,hashlib,json,os,stat,sys
manifest=Path(sys.argv[1]).resolve();key=sys.argv[2];output=Path(sys.argv[3]);data=json.loads(manifest.read_text());entry=data['unique_artifacts'][key]
if key!=entry['raw_sha256'] or len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise SystemExit('invalid raw identity')
output.mkdir(exist_ok=False);storage=manifest.parent/'storage';packed=output/'input.gz.partial';raw=output/'input.bin.partial';compressed=hashlib.sha256();compressed_size=0
with packed.open('xb') as stream:
 for part in entry['ordered_parts']:
  relative=Path(part['path'])
  if relative.is_absolute() or '..' in relative.parts:raise SystemExit('invalid part path')
  path=storage/relative;fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
  try:
   before=os.fstat(fd)
   if not stat.S_ISREG(before.st_mode):raise SystemExit('part is not regular')
   body=b''
   while chunk:=os.read(fd,1024*1024):body+=chunk
   after=os.fstat(fd)
   state=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
   if state(before)!=state(after) or len(body)!=part['bytes'] or hashlib.sha256(body).hexdigest()!=part['sha256']:raise SystemExit('part changed, size differs or hash differs')
   compressed.update(body);compressed_size+=len(body);stream.write(body)
  finally:os.close(fd)
if compressed_size!=entry['gzip_bytes'] or compressed.hexdigest()!=entry['gzip_sha256']:raise SystemExit('ordered gzip identity differs')
digest=hashlib.sha256();size=0
with gzip.open(packed,'rb') as source,raw.open('xb') as target:
 while chunk:=source.read(1024*1024):
  size+=len(chunk)
  if size>entry['raw_bytes']:raise SystemExit('decompressed size exceeded identity')
  digest.update(chunk);target.write(chunk)
if size!=entry['raw_bytes'] or digest.hexdigest()!=key:raise SystemExit('decompressed input identity differs')
final=output/(key+'.bin');raw.rename(final);final.chmod(0o400);packed.rename(output/(key+'.gz'))
receipt={'schema':1,'passed':True,'manifest':str(manifest),'raw_path':str(final),'raw_bytes':size,'raw_sha256':key,'gzip_bytes':compressed_size,'gzip_sha256':compressed.hexdigest(),'verified_parts':len(entry['ordered_parts'])}
(output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
