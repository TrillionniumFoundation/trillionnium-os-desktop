import os,sys,json,hashlib,urllib.request,urllib.parse,re,html,time,datetime,pathlib,base64,gzip
P=pathlib.Path
ROOT=P('/home/alex/work/pocket4-official-source-resolution-20261106-s1')
assert os.getuid()==1000 and os.geteuid()==1000
os.umask(0o077);ROOT.mkdir(mode=0o700)
SOURCES=[
 ('pdd_api','https://home-api.pinduoduo.com/homesite/download-app-v2?lang_only=1'),
 ('pdd_download_page','https://www.yangkeduo.com/home/download/'),
 ('pdd_index_js','https://cdn.pinduoduo.com/home/_next/static/shwSaZy9FCe~Hy_zNtqKB/pages/index.js'),
 ('jd_download_plugin','https://storage.360buyimg.com/unionfe/mkt/prod/yinliu/js/wq.imk.downloadAppPlugin.min.js'),
 ('zbj_index_js','https://app.zbj.com/bz/pc/js/index.js?13213'),
 ('zbj_download_page','https://app.zbj.com/bz/pc/'),
 ('didi_main_js','https://website.didiglobal.com/dist/js/main.9a074ac6.js'),
 ('didi_download_page','https://www.didiglobal.com/download/index.html'),
 ('taobao_mobile','https://m.taobao.com/')
]
START=time.monotonic();rows=[]
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
class Redirect(urllib.request.HTTPRedirectHandler):
 def __init__(self):self.chain=[]
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  assert len(self.chain)<5,'redirect bound'
  self.chain.append({'status':code,'from':req.full_url,'to':newurl})
  return super().redirect_request(req,fp,code,msg,headers,newurl)
for name,url in SOURCES:
 row={'name':name,'source_url':url,'method':'GET','started_utc':now(),'automatic_retry':False,'App_actions':0,'installs':0}
 body=None
 try:
  assert time.monotonic()-START<175,'metadata deadline'
  handler=Redirect();opener=urllib.request.build_opener(handler)
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/html,application/javascript,*/*;q=0.5'})
  with opener.open(req,timeout=14) as response:
   row.update(final_url=response.url,http_status=response.status,content_type=response.headers.get('Content-Type'),declared_length=response.headers.get('Content-Length'),redirect_chain=handler.chain)
   raw=response.read(2*1024*1024+1);assert len(raw)<=2*1024*1024,'metadata body bound'
  path=ROOT/(name+'.response');path.write_bytes(raw)
  row.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),raw_path=str(path))
  body=raw.decode('utf-8','strict')
  row['links']=list(dict.fromkeys(html.unescape(x) for x in re.findall(r'(?:https?:)?//[^\s"\'<>\x60]+',body)))[:100]
  row['contexts']=[]
  seen=set()
  for m in re.finditer(r'\.apk|downloadApp|downloadUrl|download_url|androidUrl|android_url|/api/|appVersion|clientVersion|download-app|AndroidDownload|appDown|window\.location',body,re.I):
   a=max(0,m.start()-220);z=min(len(body),m.end()+360);s=body[a:z]
   if s not in seen:row['contexts'].append(s);seen.add(s)
   if len(row['contexts'])>=35:break
  if len(raw)<=65536:row['public_response']=body
  row['status']='PUBLIC_METADATA_READ'
 except Exception as error:
  row.update(status='PUBLIC_METADATA_READ_FAILED',error_type=type(error).__name__,error=str(error)[:512])
 row['finished_utc']=now();rows.append(row)
 print(json.dumps({'event':'PUBLIC_METADATA_FINISHED','name':name,'status':row['status'],'http_status':row.get('http_status'),'bytes':row.get('bytes')},ensure_ascii=False),flush=True)
data={'schema':'pocket4-official-source-resolution-v1','root':str(ROOT),'source':'actual_public_GET_responses','records':rows,'account_actions':0,'App_actions':0,'installs':0,'permission_changes':0,'production_ready':False}
b=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode();(ROOT/'result.json').write_bytes(b)
packed=gzip.compress(b,mtime=0)
print(json.dumps({'event':'RESULT_CAPTURE','path':str(ROOT/'result.json'),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'gzip_base64':base64.b64encode(packed).decode()}),flush=True)

