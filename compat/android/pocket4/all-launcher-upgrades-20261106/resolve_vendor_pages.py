#!/usr/bin/env python3
"""Read public vendor download pages; no APK install, App/UI or account access."""
import concurrent.futures,datetime,hashlib,html,json,pathlib,re,urllib.parse,urllib.request
ROOT=pathlib.Path('/home/alex/work/pocket4-vendor-page-discovery-20261106-r1')
PAGES={
 'wechat':'https://weixin.qq.com/',
 'railway':'https://mobile.12306.cn/otsmobile/h5/otsbussiness/downloadapp/downloadapp.html',
 'jd':'https://wqs.jd.com/downloadApp/download.html',
 'douyin':'https://www.douyin.com/downloadpage/app',
 'ctrip':'https://m.ctrip.com/html5/mkt/centerpage/download/',
 'airchina':'https://m.airchina.com.cn/apps/',
 'airchina_android':'https://m.airchina.com.cn/down/android.jsp',
 'meituan':'https://waimai.meituan.com/download?channel=1013',
}
class HttpsOnly(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if urllib.parse.urlsplit(newurl).scheme!='https':
   raise RuntimeError('NON_HTTPS_REDIRECT:'+newurl)
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def fetch(item):
 name,url=item;out={'name':name,'source_url':url,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  opener=urllib.request.build_opener(HttpsOnly)
  with opener.open(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25) as response:
   out['final_url']=response.url;out['http_status']=response.status
   data=response.read(1048577)
   if len(data)>1048576:raise RuntimeError('HTML_BOUND')
  text=data.decode('utf-8','replace');out.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
  with (ROOT/(name+'.html')).open('xb') as f:f.write(data)
  urls=set(re.findall(r'''(?:https?:)?//[^\s<>"']+''',text))
  attrs=re.findall(r'''(?:href|src)\s*=\s*["']([^"']+)["']''',text,re.I)
  relevant=[html.unescape(x) for x in urls if any(s in x.lower() for s in ('.apk','download','android','down/'))]
  out['download_links']=sorted(relevant)[:35]
  out['script_links']=[urllib.parse.urljoin(out['final_url'],html.unescape(x)) for x in attrs if '.js' in x][-12:]
  out['relative_download_links']=[urllib.parse.urljoin(out['final_url'],html.unescape(x)) for x in attrs if any(s in x.lower() for s in ('.apk','download','android','down/'))][:25]
  out['inline_download_code']=[line[:1000] for line in text.splitlines() if any(s in line.lower() for s in ('downandroid','store.get','store.set','s.set(','s.get(','androiddownload'))][:8]
  out['status']='PUBLIC_PAGE_READ'
 except BaseException as e:out.update(status='PAGE_FAILED',error_type=type(e).__name__,error=str(e)[:700])
 print(json.dumps(out),flush=True);return out
def main():
 ROOT.mkdir(mode=0o700)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(fetch,PAGES.items()))
 with (ROOT/'result.json').open('x') as f:json.dump({'pages':rows,'installs':0,'UI_actions':0},f,indent=2)
if __name__=='__main__':main()
