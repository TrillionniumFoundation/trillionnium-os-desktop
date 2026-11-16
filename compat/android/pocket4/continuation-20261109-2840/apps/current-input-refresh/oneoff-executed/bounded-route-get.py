import os,sys,json,pathlib,urllib.request,urllib.error,urllib.parse,datetime,hashlib,re
os.umask(0o077)
root=pathlib.Path("/home/alex/work/pocket4-official-route-followup-20261109-2840-r1");root.mkdir(mode=0o700,exist_ok=False)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  parsed=urllib.parse.urlsplit(newurl)
  if parsed.scheme!="https":raise RuntimeError("non-HTTPS publisher redirect refused")
  redirects.append({"status":code,"from":req.full_url,"location":newurl})
  if len(redirects)>6:raise RuntimeError("redirect limit")
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def fetch(name,url,limit,range_header=False):
 global redirects
 redirects=[];d={"name":name,"url":url,"observed_utc":now(),"method":"GET","request_headers":{"User-Agent":"Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"}}
 if range_header:d["request_headers"]["Range"]="bytes=0-65535"
 try:
  request=urllib.request.Request(url,headers=d["request_headers"])
  try:r=urllib.request.build_opener(HTTPSRedirect()).open(request,timeout=25)
  except urllib.error.HTTPError as e:r=e
  with r:
   body=r.read(limit+1)
   d.update({"status":r.status,"effective_url":r.url,"headers":{k.lower():v for k,v in r.headers.items() if k.lower() in ["content-type","content-length","content-range","etag","last-modified","date","location","accept-ranges"]},"redirects":redirects,"truncated":len(body)>limit})
   saved=body[:limit];p=root/(name+".body");p.write_bytes(saved)
   d["body"]={"path":str(p),"bytes":len(saved),"sha256":hashlib.sha256(saved).hexdigest()}
   d["body_prefix_hex"]=saved[:32].hex()
   if not saved.startswith(b"PK"):
    text=saved.decode("utf-8","replace")
    urls=sorted(set(re.findall(r'https?://[^"\'<>\s\\]+',text)))
    apk=[u for u in urls if re.search(r"\.apk(?:[?#]|$)|ugapk|download-app|api/app/channel",u)]
    scripts=sorted(set(re.findall(r'<script[^>]*\bsrc=["\']([^"\']+)["\']',text,re.I)))
    d["apk_or_route_literals"]=apk[:100];d["script_srcs"]=scripts[:80]
    needles=["download-app","guanwang","ugapk","android","apkUrl","apk_url","downloadUrl"]
    contexts=[]
    for needle in needles:
     for m in list(re.finditer(re.escape(needle),text,re.I))[:8]:
      contexts.append({"needle":needle,"text":text[max(0,m.start()-100):m.end()+240]})
    d["source_contexts"]=contexts
 except Exception as e:d["error"]={"type":type(e).__name__,"message":str(e)}
 (root/(name+".json")).write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n")
 return d
results=[fetch("pdd-page","https://www.yangkeduo.com/home/download/",524288),fetch("pdd-route-get","https://home-api.pinduoduo.com/homesite/download-app-v2?rs=0&arch=arm64",65536,True),fetch("douyin-short-get","https://ugapk.com/mGFG",65536,True),fetch("douyin-page","https://www.douyin.com/downloadpage/app",4194304)]
final={"schema":"pocket4-official-route-bounded-get-discovery-v1","completed_utc":now(),"observations":results,"APK_complete_download":False,"runtime_qualified":False,"production_ready":False}
b=(json.dumps(final,ensure_ascii=False,indent=2)+"\n").encode();p=root/"RESULT.json";p.write_bytes(b)
print(json.dumps({"result":{"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()},"observations":results},ensure_ascii=False),flush=True)

