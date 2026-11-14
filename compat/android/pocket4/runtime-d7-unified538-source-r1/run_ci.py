#!/usr/bin/env python3
"""Run fresh D7 runtime289, four current tool tests, and four complete unified release products."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time
import traceback

SPEC = importlib.util.spec_from_file_location('d7_verifier', Path(__file__).with_name('verify.py'))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


def destinations(recipe, target, report):
    recipe = Path(recipe).absolute()
    VERIFY.need(recipe.resolve() == recipe and recipe.is_dir() and not recipe.is_relative_to(VERIFY.HERE),
                'independent canonical producer directory required')
    report = VERIFY.fresh_destination(report, [VERIFY.HERE, recipe])
    logdir = VERIFY.fresh_destination(report.parent / (report.stem + '-logs'), [VERIFY.HERE, recipe, report])
    target = VERIFY.fresh_destination(target, [VERIFY.HERE, recipe, report, logdir])
    VERIFY.need(not report.is_relative_to(target) and not logdir.is_relative_to(target),
                'fresh Cargo target cannot contain reports or logs')
    return recipe, target, report, logdir


def release_binary(path):
    path = path.absolute()
    VERIFY.need(path.resolve() == path, 'release binary parent is aliased')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        VERIFY.need(stat.S_ISREG(before.st_mode) and before.st_mode & 0o111 and 0 < before.st_size <= 128 * 1024 * 1024,
                    'actual bounded executable release binary required')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read()
        VERIFY.need(raw.startswith(b'\x7fELF') and len(raw) == before.st_size
                    and VERIFY.f9(before) == VERIFY.f9(os.fstat(fd)) == VERIFY.f9(path.lstat()),
                    'complete same-generation release ELF required')
        return {'path': str(path), **VERIFY.digest(raw), 'identity': VERIFY.f9(before)}
    finally:
        os.close(fd)


def select_release_artifacts(messages):
    wanted = {'droidloom-supervisor', 'droidloomd', 'droidloom-source', 'droidloom-update'}
    artifacts = [row for row in messages if row.get('reason') == 'compiler-artifact'
                 and row.get('executable') and row.get('profile', {}).get('test') is False]
    VERIFY.need(len(artifacts) == 4 and {row['target']['name'] for row in artifacts} == wanted
                and all(row['fresh'] is False and row['target']['kind'] == ['bin'] for row in artifacts),
                'four source-bound fresh release artifacts required')
    return artifacts


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--inventory-sha256',required=True)
    parser.add_argument('--producer',required=True,type=Path);parser.add_argument('--target',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path);parser.add_argument('--jobs',type=int,default=2)
    args=parser.parse_args();VERIFY.need(args.jobs in (1,2),'one or two Cargo jobs required')
    manifest=VERIFY.verify_capsule(args.inventory_sha256)
    recipe,target,report,logdir=destinations(args.producer,args.target,args.report)
    rows=VERIFY.catalog(manifest,'head');tc=VERIFY.test_catalog(manifest)
    before=VERIFY.source_snapshot(recipe,rows,VERIFY.HEAD_TREE)
    logdir.parent.mkdir(parents=True,exist_ok=True);logdir.mkdir(mode=0o700);target.mkdir(mode=0o700)
    runtime_cwd = VERIFY.fresh_destination(logdir / 'runtime-working-directory', [VERIFY.HERE, recipe, target])
    runtime_cwd.mkdir(mode=0o700)
    env=dict(os.environ,CARGO_BUILD_JOBS=str(args.jobs),CARGO_TARGET_DIR=str(target),CARGO_INCREMENTAL='0',CARGO_TERM_COLOR='never',GIT_OPTIONAL_LOCKS='0')
    result={'schema':'d7-fresh-CI-runtime289-tool4-and-four-release-products-v1','state':'RUNNING',
        'source_commit':VERIFY.HEAD_COMMIT,'source_tree':VERIFY.HEAD_TREE,'source_files':1595,
        'actual_fresh_runtime_ordinary_tests':0,'actual_fresh_current_tool_tests':0,'historical_tests_counted_as_fresh':0,
        'historical_ELFs_reused':False,'fresh_Cargo_target':str(target),'runtime_test_cwd':str(runtime_cwd),'commands':[],'errors':[],
        'explicitly_unqualified_privileged_tests':tc['runtime_privileged_ignored'],
        'Android_builds':0,'Android_starts':0,'runtime_qualified':False,'production_ready':False,
        'ExecutionAdmission_constructible':False,'actual_SELinux_transition_qualified':False,
        'host334_counted_as_fresh_CI':False,'private_DMA_fixture_materialized':False,'started_ns':time.time_ns()}

    def run(name,argv,timeout=1800,cwd=None):
        command_cwd = recipe if cwd is None else cwd
        outp,errp=logdir/(name+'.stdout'),logdir/(name+'.stderr');timed_out=False;began=time.time_ns()
        with outp.open('xb') as out,errp.open('xb') as err:
            child=subprocess.Popen(argv,cwd=command_cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
            try:code=child.wait(timeout=timeout)
            except BaseException:
                timed_out=True
                try:os.killpg(child.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:code=child.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);code=child.wait(timeout=10)
        stdout,stderr=VERIFY.regular(outp),VERIFY.regular(errp)
        row={'name':name,'argv':argv,'cwd':str(command_cwd),'pid':child.pid,'exit_code':code,'actual_child_reaped':True,'timed_out':timed_out,
             'started_ns':began,'finished_ns':time.time_ns(),'stdout':{'path':str(outp),**VERIFY.digest(stdout)},'stderr':{'path':str(errp),**VERIFY.digest(stderr)}}
        result['commands'].append(row)
        VERIFY.need(not timed_out and code==0,'actual fresh CI command failed: '+name)
        return row,stdout,stderr

    try:
        command,stdout,_=run('compile-runtime-harness',['cargo','test','--locked','-j',str(args.jobs),'-p','droidloom-supervisor','--lib','--no-run','--message-format=json'])
        messages=VERIFY.successful_cargo_stream(stdout)
        artifacts=[x for x in messages if x.get('reason')=='compiler-artifact' and x.get('executable') and x.get('profile',{}).get('test')]
        VERIFY.need(len(artifacts)==1 and artifacts[0]['target']['name']=='droidloom_supervisor' and artifacts[0]['target']['kind']==['lib'] and artifacts[0]['fresh'] is False,
                    'one actual freshly compiled current runtime harness required')
        binary=Path(artifacts[0]['executable'])
        VERIFY.need(binary.parent==target/'debug/deps' and Path(artifacts[0]['target']['src_path']).is_relative_to(recipe),'runtime harness must come from this complete source and fresh target')
        _,stdout,_=run('runtime-full-catalog',[str(binary),'--list','--format=terse'],60,cwd=runtime_cwd)
        names=[line[:-6] for line in stdout.decode().splitlines() if line.endswith(': test')]
        VERIFY.need(len(names)==len(stdout.decode().splitlines())==310 and len(set(names))==310 and set(names)==set(tc['runtime_registered']),
                    'complete actual310 runtime catalog required')
        _,stdout,_=run('runtime-privileged-ignored-catalog',[str(binary),'--ignored','--list','--format=terse'],60,cwd=runtime_cwd)
        names=[line[:-6] for line in stdout.decode().splitlines() if line.endswith(': test')]
        VERIFY.need(len(names)==len(stdout.decode().splitlines())==21 and len(set(names))==21 and set(names)==set(tc['runtime_privileged_ignored']),
                    'all21 privileged ignored cases must remain explicit')
        command,stdout,_=run('runtime289-ordinary',[str(binary),'--test-threads=1','--color','never'],1200,cwd=runtime_cwd)
        command['actual_tests']=VERIFY.test_terminal(stdout.decode(),tc['runtime_ordinary'],tc['runtime_privileged_ignored'],0)
        result['actual_fresh_runtime_ordinary_tests']=len(command['actual_tests']['passed'])
        for name,package,selection,expected,filtered in [
            ('source-libueventd-test','droidloom-source',['--lib'],tc['fresh_source_tests'],42),
            ('updater-libueventd-tests','droidloom-update',['--bin','droidloom-update'],tc['fresh_updater_tests'],285)]:
            command,stdout,_=run(name,['cargo','test','--locked','-j',str(args.jobs),'-p',package,*selection,'libueventd538','--','--test-threads=1','--color','never'])
            command['actual_tests']=VERIFY.test_terminal(stdout.decode(),expected,filtered=filtered)
            result['actual_fresh_current_tool_tests']+=len(command['actual_tests']['passed'])
        VERIFY.need(result['actual_fresh_runtime_ordinary_tests']==289 and result['actual_fresh_current_tool_tests']==4,'all293 fresh ordinary/current tests required')
        release,stdout,_=run('four-fresh-release-binaries',['cargo','build','--release','--locked','-j',str(args.jobs),
            '-p','droidloom-supervisor','-p','droidloom-source','-p','droidloom-update',
            '--bin','droidloom-supervisor','--bin','droidloomd','--bin','droidloom-source','--bin','droidloom-update','--message-format=json'])
        messages=VERIFY.successful_cargo_stream(stdout)
        wanted={'droidloom-supervisor','droidloomd','droidloom-source','droidloom-update'}
        artifacts=select_release_artifacts(messages)
        fresh=logdir/'fresh-release';fresh.mkdir(mode=0o700);bins={};originals={}
        for item in artifacts:
            name=item['target']['name'];path=Path(item['executable'])
            VERIFY.need(path==target/'release'/name and Path(item['target']['src_path']).is_relative_to(recipe),
                        'release artifact must come from this actual producer and fresh target')
            original=release_binary(path)
            VERIFY.need(release['started_ns']<=original['identity'][7]<=release['finished_ns'] and
                        release['started_ns']<=original['identity'][8]<=release['finished_ns'],
                        'actual release ELF must be generated inside this command interval')
            aliases=[]
            for member in (target/'release').rglob('*'):
                st=member.lstat()
                if stat.S_ISREG(st.st_mode) and (st.st_dev,st.st_ino)==tuple(original['identity'][:2]):
                    VERIFY.need(VERIFY.f9(st)==original['identity'],'release hardlink identity changed')
                    aliases.append(member)
            VERIFY.need(len(aliases)==original['identity'][5] and len(aliases) in (1,2) and path in aliases and
                        all(p==path or p.parent==target/'release/deps' for p in aliases),'all original Cargo aliases must be owned inside this fresh target')
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                VERIFY.need(VERIFY.f9(os.fstat(fd))==original['identity'],'held release identity changed')
                with os.fdopen(os.dup(fd),'rb') as stream:body=stream.read()
                VERIFY.need(VERIFY.digest(body)=={k:original[k] for k in ('bytes','sha256')} and body[:6]==b'\x7fELF\x02\x01' and int.from_bytes(body[18:20],'little')==62,
                            'complete actual x86_64 release ELF required')
                dest=fresh/name
                with dest.open('xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
                dest.chmod(0o555);copy=release_binary(dest)
                VERIFY.need(copy['sha256']==original['sha256'] and copy['identity'][5]==1 and copy['identity'][:2]!=original['identity'][:2],
                            'independent single-link current release copy required')
                VERIFY.need(release_binary(path)==original,'original release changed during independent copy')
            finally:os.close(fd)
            bins[name]=copy;originals[name]={'artifact':original,'aliases':[str(p) for p in aliases]}
        for name in sorted(wanted):
            command,stdout,_=run('help-'+name,[bins[name]['path'],'--help'],60)
            VERIFY.need(b'Usage:' in stdout,'normal fresh release help contract missing')
        for name,row in bins.items():
            VERIFY.need(release_binary(Path(row['path']))==row,'fresh release copy changed after CLI execution')
            VERIFY.need(release_binary(target/'release'/name)==originals[name]['artifact'],'original Cargo release changed after CLI execution')
        result['four_fresh_independent_0555_release_binaries']=bins
        result['original_Cargo_alias_provenance']=originals
        VERIFY.need(VERIFY.source_snapshot(recipe,rows,VERIFY.HEAD_TREE)==before,'all1595 source byte/mode/member/F9 bookends must match')
        result['all1595_after_bytes_Git_blobs_modes_members_F9_verified']=True
        result['state']='RUNTIME289_CURRENT_TOOL4_AND_FOUR_FRESH_UNIFIED_RELEASES_PASSED'
    except BaseException as error:
        result['state']='FAILED';result['errors'].append({'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
        try:result['all1595_after_bytes_Git_blobs_modes_members_F9_verified']=VERIFY.source_snapshot(recipe,rows,VERIFY.HEAD_TREE)==before
        except BaseException as after:
            result['all1595_after_bytes_Git_blobs_modes_members_F9_verified']=False;result['errors'].append({'producer_after_error':str(after)})
    result['finished_ns']=time.time_ns()
    VERIFY.write_report(report,result,[VERIFY.HERE,recipe,target,logdir])
    print(json.dumps({'state':result['state'],'fresh_runtime_tests':result['actual_fresh_runtime_ordinary_tests'],
        'fresh_tool_tests':result['actual_fresh_current_tool_tests'],'report':str(report),'Android_builds':0},sort_keys=True))
    return 0 if result['state']=='RUNTIME289_CURRENT_TOOL4_AND_FOUR_FRESH_UNIFIED_RELEASES_PASSED' else 1


if __name__=='__main__':
    raise SystemExit(main())
