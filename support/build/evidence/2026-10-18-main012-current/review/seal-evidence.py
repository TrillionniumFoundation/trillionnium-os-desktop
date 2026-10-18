#!/usr/bin/env python3
"""Seal A01 evidence payloads and preserve the actual checksum command result."""
import datetime,hashlib,json,pathlib,re,shutil,subprocess
REPO=pathlib.Path('/workspace/scratch/d7da9e7650f0/a01-current')
DEST=REPO/'support/build/evidence/2026-10-18-main012-current'
def sha(raw):return hashlib.sha256(raw).hexdigest()
review=pathlib.Path('/tmp/a01-current-build-review/publication-review.json')
assert sha(review.read_bytes())=='170fb1cf555a782e2a7142b02bfe1bece305fd2990f49db937002bd0fe4fa2e2'
result=json.loads(review.read_text())
assert result['content_review_passed'] and result['checks_passed']==33 and result['checks_failed']==0
shutil.copyfile(review,DEST/'review/publication-review.json')
shutil.copyfile(pathlib.Path(__file__),DEST/'review/seal-evidence.py')
assert not (DEST/'SHA256SUMS').exists()
excluded={'SHA256SUMS','review/checksum-verification.json'}
payloads=[]
for path in sorted(DEST.rglob('*')):
    if not path.is_file():continue
    rel=str(path.relative_to(DEST))
    if rel in excluded:continue
    assert not path.is_symlink()
    raw=path.read_bytes()
    if path.suffix=='.json':json.loads(raw)
    payloads.append({'path':rel,'size':len(raw),'sha256':sha(raw)})
index=json.loads((DEST/'archive-index.json').read_text())
for entry in index['archives']:
    actual=next(p for p in payloads if p['path']==entry['path'])
    assert actual['size']==entry['size'] and actual['sha256']==entry['sha256']
manifest='# Excludes SHA256SUMS and review/checksum-verification.json; the receipt binds this manifest.\n'
manifest+=''.join(p['sha256']+'  '+p['path']+'\n' for p in payloads)
(DEST/'SHA256SUMS').write_text(manifest)
links=[]
for document in [DEST/'REPORT.md',DEST/'HANDOFF.md']:
    for target in re.findall(r'\]\(([^)]+)\)',document.read_text()):
        if '://' in target or target.startswith('#'):continue
        local=(document.parent/target.split('#')[0]).resolve()
        assert local.exists(),(document,target)
        links.append({'document':document.name,'target':target})
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
command=['sha256sum','-c','SHA256SUMS']
check=subprocess.run(command,cwd=DEST,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
assert check.returncode==0 and len(check.stdout.decode().splitlines())==len(payloads)
receipt={'schema':'trillionnium.a01.evidence-checksum-verification.v1',
    'started_at_utc':start,'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'command':command,'cwd':str(DEST),'exit_code':check.returncode,'payload_files':len(payloads),
    'manifest':'SHA256SUMS','manifest_sha256':sha((DEST/'SHA256SUMS').read_bytes()),
    'manifest_exclusions':sorted(excluded),'exclusion_reason':'Avoid circular hashes; Git binds the manifest and this receipt.',
    'stdout':check.stdout.decode(),'stderr':check.stderr.decode(),'stdout_sha256':sha(check.stdout),
    'archive_outer_hashes_match':True,'json_documents_parse':True,'local_markdown_links_checked':len(links),
    'publication_review_checks_passed':33,'source_producer':'b39e154ae5a1e9853f57e23f9bee84712ee8ef7e',
    'root_readme_bytes':(REPO/'README.md').stat().st_size,'passed':True,
    'script_sha256':sha(pathlib.Path(__file__).read_bytes())}
assert receipt['root_readme_bytes']==0
(DEST/'review/checksum-verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert sha((DEST/'SHA256SUMS').read_bytes())==receipt['manifest_sha256']
print(json.dumps({'passed':True,'payload_files':len(payloads),'archive_hashes':5,'local_links':len(links),
    'manifest_sha256':receipt['manifest_sha256'],'receipt_sha256':sha((DEST/'review/checksum-verification.json').read_bytes())}))
