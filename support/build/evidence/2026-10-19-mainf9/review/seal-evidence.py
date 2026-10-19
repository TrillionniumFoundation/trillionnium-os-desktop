#!/usr/bin/env python3
"""Seal all final evidence payloads; exclude only the manifest and its receipt."""
import datetime,hashlib,json,pathlib,shutil,subprocess
R=pathlib.Path('/workspace/scratch/d7da9e7650f0/a01-mainf9')
E=R/'support/build/evidence/2026-10-19-mainf9'
shutil.copyfile(__file__,E/'review/seal-evidence.py')
excluded={'SHA256SUMS','review/checksum-verification.json'}
files=sorted(p for p in E.rglob('*') if p.is_file() and str(p.relative_to(E)) not in excluded)
assert all(not p.is_symlink() for p in files)
assert (E/'review/publication-review.json').is_file()
assert not (E/'SHA256SUMS').exists()
manifest=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(E))+'\n' for p in files)
(E/'SHA256SUMS').write_text(manifest)
args=['sha256sum','--check','SHA256SUMS']
p=subprocess.run(args,cwd=E,text=True,capture_output=True)
record={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':args,'cwd':str(E),'manifest':'SHA256SUMS','manifest_sha256':hashlib.sha256(manifest.encode()).hexdigest(),'covered_payload_files':len(files),'excluded_files':sorted(excluded),'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'all_payload_hashes_match':p.returncode==0,'scope':'The manifest covers all final evidence payloads except itself and this verification receipt. Git commits bind both excluded files. No checksum self-reference is claimed.'}
(E/'review/checksum-verification.json').write_text(json.dumps(record,indent=2)+'\n')
assert set(str(q.relative_to(E)) for q in E.rglob('*') if q.is_file())=={str(q.relative_to(E)) for q in files}|excluded
if p.returncode:raise SystemExit(p.stderr)
assert (R/'README.md').stat().st_size==0
print(json.dumps({k:record[k] for k in ['manifest_sha256','covered_payload_files','exit_code','all_payload_hashes_match','excluded_files']},indent=2))
