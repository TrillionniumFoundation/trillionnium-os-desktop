#!/usr/bin/env python3
"""Continue the known, joined Beike transfer failure; no install or UI."""
import datetime,hashlib,json,os,pathlib,subprocess
ROOT=pathlib.Path('/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1')
PART=ROOT/'com.lianjia.beike.part'
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    out={'package':'com.lianjia.beike','automatic_retry':False,'prior_terminal_failure_retained':True,
         'source_url':'https://file.ljcdn.com/app-packages/shell/channel/20f1e58d/Android_ke_m.apk',
         'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'installs':0,'UI_actions':0,'signature_verified':False,'claimed_latest_usable':False}
    process=None
    try:
        assert PART.stat().st_size==228097118
        assert digest(PART)=='7e91b56efbd7b032aeb3c2e4da19b423a58e31f3e299533efff20521db7ee568'
        assert digest(ROOT/'com.lianjia.beike.resume-r2.stderr')=='4fbeb3b068dfd0a00fd3fcd95b81af2190310bf9d119abbd0a75dfe1725b0c16'
        (ROOT/'com.lianjia.beike.resume-r3.claim').open('x').close()
        with (ROOT/'com.lianjia.beike.resume-r3.stderr').open('xb') as err:
            process=subprocess.Popen(['/usr/bin/curl','--fail','--location','--proto','=https','--proto-redir','=https',
                '--connect-timeout','25','--max-time','180','--max-filesize',str(512*1024*1024),'--silent','--show-error',
                '--user-agent','Mozilla/5.0','--dump-header',str(ROOT/'com.lianjia.beike.resume-r3.headers'),
                '--continue-at','228097118','--output',str(PART),out['source_url']],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=err)
            out['download_pid']=process.pid
            try:
                out['returncode']=process.wait(timeout=195)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                out['joined']=True
                raise RuntimeError('OWNED_DOWNLOAD_TIMED_OUT_AND_JOINED')
        out['joined']=True
        assert out['returncode']==0,'CURL_DOWNLOAD_FAILED'
        assert PART.stat().st_size==228933721,'FULL_SIZE_MISMATCH'
        final=ROOT/'com.lianjia.beike.apk'
        assert not final.exists(),'FINAL_ALREADY_EXISTS'
        sha=digest(PART)
        os.rename(PART,final)
        out.update(status='STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION',bytes=228933721,
                   sha256=sha,path=str(final))
    except BaseException as e:
        out.update(status='DOWNLOAD_FAILED',error_type=type(e).__name__,error=str(e)[:200])
    out['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (ROOT/'beike-resume-r3-result.json').open('x') as f:
        json.dump(out,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps(out),flush=True)
if __name__=='__main__':main()
