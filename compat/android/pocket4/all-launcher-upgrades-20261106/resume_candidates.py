#!/usr/bin/env python3
"""Explicit continuation of reconciled partial downloads; no install or App action."""
import concurrent.futures, datetime, hashlib, json, os, pathlib, subprocess, time

ROOT=pathlib.Path("/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1")
PREVIOUS=ROOT/"download-results.json"
EXPECTED={
 "tv.danmaku.bili":("https://dl.hdslb.com/mobile/latest/android64/iBiliPlayer-bili.apk",114294784,"3b4982dc03358eafd3bb9f17c5af4f757340019b700d52281b81ed946668c8cd"),
 "com.lianjia.beike":("https://file.ljcdn.com/app-packages/shell/channel/20f1e58d/Android_ke_m.apk",39845888,"63f74afe7414cbaad66f2734ceabc8b56edbbdccd227b5482aed6065ecacca1a"),
 "com.rytong.ceair":("https://ecresource-app.ceair.com/apk/ceair_release_v9_5_16_20261105.apk",0,None)
}
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
def run(item):
 package,(url,size,prefix)=item
 part=ROOT/(package+".part")
 row={"package":package,"url":url,"started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "app_installed":False,"automatic_retry":False,"prior_terminal_failure_retained":True}
 try:
  if size:
   if part.stat().st_size!=size or digest(part)!=prefix:raise RuntimeError("PARTIAL_PREFIX_CHANGED")
  elif part.exists():raise RuntimeError("UNEXPECTED_PARTIAL_PATH")
  claim=ROOT/(package+".resume-r2.claim")
  claim.open("x").close()
  stderr_path=ROOT/(package+".resume-r2.stderr")
  header_path=ROOT/(package+".resume-r2.headers")
  argv=["/usr/bin/curl","--fail","--location","--proto","=https","--proto-redir","=https",
        "--connect-timeout","25","--max-time","1100","--max-filesize",str(512*1024*1024),
        "--silent","--show-error","--user-agent","Mozilla/5.0","--dump-header",str(header_path),
        "--output",str(part)]
  if size:argv+=["--continue-at",str(size)]
  argv += [url]
  with stderr_path.open("xb") as err:
   process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=err)
   row["download_pid"]=process.pid
   row["returncode"]=process.wait(timeout=1120)
  row["joined"]=True
  row["stderr_sha256"]=digest(stderr_path)
  if row["returncode"]!=0:raise RuntimeError("CURL_DOWNLOAD_FAILED")
  n=part.stat().st_size
  if not 1024<n<=512*1024*1024:raise RuntimeError("FINAL_SIZE_BOUND")
  final=ROOT/(package+".apk")
  if final.exists():raise RuntimeError("CANDIDATE_ALREADY_EXISTS")
  file_hash=digest(part)
  os.rename(part,final)
  row.update(status="STAGED_PENDING_SIGNATURE_AND_IDENTITY_VERIFICATION",bytes=n,sha256=file_hash,
             local_path=str(final),signature_verified=False,claimed_latest_usable=False)
 except Exception as e:
  row.update(status="DOWNLOAD_FAILED",error_type=type(e).__name__,error=str(e)[:200],
             partial_bytes=part.stat().st_size if part.exists() else 0)
 row["finished_utc"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
 print(json.dumps(row),flush=True)
 return row
def main():
 prior=json.loads(PREVIOUS.read_bytes())
 assert len(prior["candidates"])==4 and all(r["status"]=="DOWNLOAD_FAILED" for r in prior["candidates"])
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(run,EXPECTED.items()))
 report={"schema":"pocket4-official-download-continuation-v1","previous_report_sha256":digest(PREVIOUS),
         "download_only":True,"installs":0,"UI_actions":0,"candidates":rows}
 p=ROOT/"resume-results-r2.json"
 with p.open("x") as f:json.dump(report,f,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
 print(json.dumps({"report":str(p),"staged":sum(x["status"].startswith("STAGED_") for x in rows)}),flush=True)
if __name__=="__main__":main()
