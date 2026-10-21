#!/usr/bin/env python3
"""Offline validation of a bounded historical owner readback; no execution replay."""
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile

ROOT=Path(__file__).resolve().parent
ORIGINAL_SUM='3416ac3789de0a29bed99483d89dc91dff4d4c7d45447e2878eedfddf04d3e8f'
REPO='TrillionniumFoundation/trillionnium-os-desktop'
SHA=re.compile(r'[0-9a-f]{64}\Z')


def require(condition,message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def path_name(value):
    require(isinstance(value,str) and value, 'missing relative name')
    p=PurePosixPath(value)
    require(not p.is_absolute() and '..' not in p.parts and str(p)==value and '\\' not in value,
            'invalid relative name: '+value)
    return value


def sums(raw):
    result={}
    for line in raw.decode('utf-8').splitlines():
        parts=line.split('  ',1)
        require(len(parts)==2 and SHA.fullmatch(parts[0]),'invalid checksum row')
        h,name=parts;path_name(name)
        require(name not in result,'duplicate checksum row')
        result[name]=h
    return result


def outer_files():
    files={}
    for p in ROOT.rglob('*'):
        require(not p.is_symlink(),'outer symlink rejected')
        if p.is_dir():
            continue
        require(stat.S_ISREG(p.stat().st_mode),'outer nonregular entry rejected')
        files[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    expected=sums(files['SHA256SUMS'])
    require(set(expected)==set(files)-{'SHA256SUMS'},'outer checksum coverage differs')
    for name,h in expected.items():
        require(digest(files[name])==h,'outer checksum differs: '+name)
    return files


def read_json(raw,name):
    value=json.loads(raw[name].decode('utf-8'))
    return value


def unpack_checked(files):
    archive=read_json(files,'archive.json');members=read_json(files,'members.json')
    name=path_name(archive['path'])
    payload=files[name]
    require(0<len(payload)<=2*1024*1024,'archive exceeds2MiB storage bound')
    require(len(payload)==archive['bytes'] and digest(payload)==archive['sha256'],'archive storage differs')
    require(archive['members']==39 and archive['original_total_bytes']==357755,'original inventory metadata differs')
    require(archive['original_sha256sums_sha256']==ORIGINAL_SUM,'original checksum binding differs')
    require(isinstance(members,list) and len(members)==39,'expected39 archive members')
    expected={}
    for item in members:
        n=path_name(item['path'])
        require(n not in expected and type(item['bytes']) is int and 0<=item['bytes']<=357755,
                'invalid member metadata')
        require(SHA.fullmatch(item['sha256']) and item['mode']==0o644,'invalid member hash/mode')
        expected[n]=item
    raw={};order=[]
    with tarfile.open(ROOT/name,'r:gz') as archive_stream:
        for member in archive_stream:
            n=path_name(member.name)
            require(n in expected and n not in raw and member.isfile(),'unexpected archive member')
            require(member.mode==0o644 and member.uid==0 and member.gid==0 and member.mtime==0
                    and member.uname=='' and member.gname=='','nondeterministic tar metadata')
            require(member.size==expected[n]['bytes'],'member size differs')
            source=archive_stream.extractfile(member)
            require(source is not None,'missing member payload')
            with source:
                data=source.read(member.size+1)
            require(len(data)==member.size and digest(data)==expected[n]['sha256'],'member bytes differ')
            raw[n]=data;order.append(n)
    require(set(raw)==set(expected) and order==sorted(expected),'archive inventory/order differs')
    require(len(raw)==39 and sum(map(len,raw.values()))==357755,'original total differs')
    require(digest(raw['SHA256SUMS'])==ORIGINAL_SUM,'original checksum file was changed')
    original=sums(raw['SHA256SUMS'])
    require(len(original)==38 and set(original)==set(raw)-{'SHA256SUMS'},'original closure incomplete')
    for n,h in original.items():
        require(digest(raw[n])==h,'original payload was changed: '+n)
    return raw


def structured(raw,label):
    item=read_json(raw,label+'.json')
    require(item['label']==label and item['result'].get('isError') is False,'failed/mismatched readback')
    return item,item['result']['structuredContent']


def time_value(value):
    require(isinstance(value,str) and value.endswith('Z'),'expected original UTC request time')
    result=datetime.datetime.fromisoformat(value[:-1]+'+00:00')
    return result


def verify_requests(raw):
    saved=read_json(raw,'requests.json')
    require(saved['record_kind'].startswith('Posthoc literal transcription'),'request provenance label differs')
    requests=saved['requests']
    require(isinstance(requests,list) and len(requests)==18,'expected18 actual request records')
    expect={}
    for n in (87,18,8,22,93):
        expect['pr'+str(n)]=('mcp__codex_apps__github_get_pr_info',{'pr_number':n,'repository_full_name':REPO})
    expect['issue63']=('mcp__codex_apps__github_fetch_issue',{'issue_number':63,'repository_full_name':REPO})
    heads={'a01':'d879a9d2ffae8d0eb0df441370da54f9e3a38431',
           'a05':'25cbffe6080bdf397f4911f85111cc966ac951d3',
           'a06':'57b23ede7e242711ef142b672f04c896383a264a',
           'a04':'da4107f8bf525b773c8b40899f443c292c3e6dbd'}
    for label,head in heads.items():
        for suffix,tool in (('runs','github_fetch_commit_workflow_runs'),('status','github_get_commit_combined_status')):
            expect[label+'-'+suffix]=('mcp__codex_apps__'+tool,{'commit_sha':head,'repo_full_name':REPO})
    for label,query in (('a07-title-search','repo:'+REPO+' A07 in:title'),('a07-head-search','repo:'+REPO+' head:agents/A07')):
        expect[label]=('mcp__codex_apps__github_search_prs',{'query':query,'repository_full_name':REPO,'state':'all','topn':30})
    for label,run in (('a01-latest-jobs',38992415807),('a05-current-g0-jobs',38988938901)):
        expect[label]=('mcp__codex_apps__github_fetch_workflow_run_jobs',{'repo_full_name':REPO,'run_id':run})
    seen=set();starts=[];ends=[]
    for request in requests:
        label=request['label']
        require(label in expect and label not in seen,'unexpected/duplicate request')
        seen.add(label)
        require((request['tool'],request['arguments'])==expect[label],'request tool/arguments differ')
        item,_=structured(raw,label)
        require(request['saved']==label+'.json' and request['started']==item['started']
                and request['ended']==item['ended'],'request timestamps/source differ')
        start,end=time_value(item['started']),time_value(item['ended'])
        require(start<=end,'inverted request times')
        starts.append(item['started']);ends.append(item['ended'])
    require(seen==set(expect),'missing request')
    require((min(starts),max(ends))==('2026-10-17T01:52:52.607Z','2026-10-17T01:53:47.412Z'),
            'original readback window differs')


def verify_remote_facts(raw):
    _,a01=structured(raw,'pr22')
    require(a01['state']=='open' and a01['draft'] is False and a01['merged'] is False,'A01 PR state differs')
    require(a01['head_sha']=='d879a9d2ffae8d0eb0df441370da54f9e3a38431'
            and a01['base_sha']=='40ca002fac0726b366726d3353916637b29adeae','A01/main observed refs differ')
    for label,head in (('pr87','25cbffe6080bdf397f4911f85111cc966ac951d3'),
                       ('pr18','57b23ede7e242711ef142b672f04c896383a264a'),
                       ('pr8','da4107f8bf525b773c8b40899f443c292c3e6dbd')):
        _,pr=structured(raw,label)
        require(pr['state']=='open' and pr['draft'] is True and pr['merged'] is False
                and pr['head_sha']==head,'owner Draft/ref differs')
    _,issue=structured(raw,'issue63');issue=issue['issue']
    require(issue['issue_number']==63 and issue['state']=='open' and issue['comments']==0,'issue63 differs')
    for label in ('a07-title-search','a07-head-search'):
        _,result=structured(raw,label)
        require(result['issues']==[],'limited A07 query differs')
    _,runs=structured(raw,'a01-runs')
    require(len(runs['workflow_runs'])==1,'A01 run count differs')
    run=runs['workflow_runs'][0]
    require(run['id']==38992415807 and run['status']=='queued' and run['conclusion'] is None,'A01 queue differs')
    _,jobs=structured(raw,'a01-latest-jobs')
    require(len(jobs['jobs'])==1,'A01 job count differs')
    job=jobs['jobs'][0]
    require(job['id']==117277478013 and job['run_id']==38992415807
            and job['status']=='queued' and job['conclusion'] is None,'A01 job queue differs')
    _,a05=structured(raw,'a05-runs');_,a06=structured(raw,'a06-runs');_,a04=structured(raw,'a04-runs')
    require(any(x['id']==38988938901 and x['conclusion']=='success' for x in a05['workflow_runs']),
            'associated A05 host run differs')
    require(any(x['id']==38932286139 and x['conclusion']=='failure' for x in a06['workflow_runs']),
            'A06 G0 failure differs')
    require(a04['workflow_runs']==[],'A04 returned run list differs')
    for label in ('a01-status','a05-status','a06-status','a04-status'):
        _,status=structured(raw,label)
        require(status['statuses']==[],'returned status list differs')
    _,pr93=structured(raw,'pr93')
    require(pr93['state']=='open' and pr93['draft'] is True
            and pr93['head_sha']=='ecdd6275b4ce4c100a41a5632920a01fb5937c65','separate A05 handoff differs')


def verify_sources(files,raw):
    index=read_json(raw,'local-readback-index.json');bindings=read_json(files,'source-bindings.json')
    require(len(index['files'])==15 and bindings['source_inventory']==index['files'],'source inventory differs')
    require(bindings['original_sha256sums_sha256']==ORIGINAL_SUM,'source closure binding differs')
    require(bindings['source_capture_utc']==index['captured_utc'],'source capture time differs')
    require(bindings['original_summary_sha256']==digest(raw['review-report.json']),'original summary binding differs')
    for entry in index['files']:
        p=path_name(entry['path'])
        if p.startswith('support/build/evidence/'):
            selected='frozen-phase-readback/'+p.removeprefix('support/build/evidence/')
        else:
            selected='local-source/'+p
        data=raw[selected]
        require(len(data)==entry['bytes'] and digest(data)==entry['sha256'],'source bytes differ: '+p)
        if 'lines' in entry:
            require(len(data.splitlines())==entry['lines'],'source line count differs')
    summary=read_json(files,'summary.json');original=read_json(raw,'review-report.json')
    require(summary['raw_files']==39 and summary['raw_bytes']==357755 and summary['requests']==18,'wrapper counts differ')
    require(summary['original_snapshot_not_current_status'] is True
            and summary['later_results_outside_this_package'] is True,'historical/current scope lost')
    require(summary['remote_at_original_window']==original['remote'],'original remote summary was relabeled')
    require(summary['original_readback_window_utc']==original['remote_readback_window_utc'],
            'original summary window differs')


def main():
    files=outer_files();raw=unpack_checked(files)
    verify_requests(raw);verify_remote_facts(raw);verify_sources(files,raw)
    print(json.dumps({'pass':True,'scope':'historical_readback_only','raw_files':39,'requests':18,
                      'source_bindings':15,'original_inner_checksums':38,'original_raw_unchanged':True},sort_keys=True))
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,tarfile.TarError) as error:
        print('verification failed: '+str(error),file=sys.stderr)
        raise SystemExit(1)
