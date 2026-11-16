"""Original fixed assets and one network-namespace-only server. Import is inert."""
from pathlib import Path
import argparse,base64,ctypes,fcntl,hashlib,http.server,json,os,re,select,signal,stat,subprocess,time,struct,zlib,urllib.parse,types

def build(video=None):
    if type(video) is not bytes or len(video)!=58199 or hashlib.sha256(video).hexdigest()!='7148402273737217b6906704ac430fcfd77268e9f0dbfe19d5f334a496a58d69':
        raise RuntimeError('EXACT_ORIGINAL_IMMUTABLE_VIDEO_BYTES_REQUIRED')
    def fixed_video():return video
    CLONE_NEWNET = 1073741824

    MAX_LEASE = 600

    VALUE = 'Pocket4 中文 café 😀 — r12'

    VIDEO_SHA = '7148402273737217b6906704ac430fcfd77268e9f0dbfe19d5f334a496a58d69'

    HTTPS_ASSET_URL = 'https://raw.githubusercontent.com/chromium/chromium/cb9500488bdd2ffdfdd6b9b49e3389bf284e6f1c/media/test/data/bear.webm'

    PAGES = ('image.html', 'form.html', 'submitted.html', 'media.html', 'network.html', 'missing.html')

    def fixed_png():

        def chunk(name, body):
            return struct.pack('>I', len(body)) + name + body + struct.pack('>I', zlib.crc32(name + body) & 4294967295)
        pixels = bytes([0, 255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 0, 255, 255, 255, 255, 255, 255])
        return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels, 9)) + chunk(b'IEND', b'')

    SCRIPT = '"use strict";\n(() => {\n  const expected = "Pocket4 中文 café 😀 — r12";\n  const videoHash = "7148402273737217b6906704ac430fcfd77268e9f0dbfe19d5f334a496a58d69";\n  const httpsURL = "https://raw.githubusercontent.com/chromium/chromium/cb9500488bdd2ffdfdd6b9b49e3389bf284e6f1c/media/test/data/bear.webm";\n  const m = location.pathname.match(/^\\/p4\\/([a-f0-9]{32})\\/(image|form|submitted|media|network|missing)\\.html$/);\n  const out=document.getElementById("result"), detail=document.getElementById("details");\n  const show=s=>{out.textContent=s;}, fail=e=>{show("FAIL: "+String(e.message||e));};\n  if(!m){fail("unrecognized fixture path");return;}\n  const run=m[1],phase=m[2],prefix="/p4/"+run+"/";\n  document.getElementById("run").textContent=run;\n  document.getElementById("js").textContent="JavaScript ready: 437";\n  const need=(x,s)=>{if(!x)throw Error(s);};\n  const nav=performance.getEntriesByType("navigation");\n  if(phase==="image"){\n    const img=document.getElementById("fixture-image");\n    const verify=()=>{\n      try{\n        need(img.complete&&img.naturalWidth===2&&img.naturalHeight===2,"image dimensions");\n        const c=document.createElement("canvas");c.width=c.height=2;\n        const cx=c.getContext("2d",{willReadFrequently:true});need(cx,"2D canvas context");\n        cx.drawImage(img,0,0);const pixels=Array.from(cx.getImageData(0,0,2,2).data);\n        need(pixels.join(",")==="255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255","decoded image pixels");\n        detail.textContent=JSON.stringify({width:img.naturalWidth,height:img.naturalHeight,pixels:pixels,navigation:nav.map(x=>x.type)});\n        show(nav.length===1&&nav[0].type==="reload"?"IMAGE_RELOAD_OK":"IMAGE_DECODE_OK");\n        document.getElementById("next-form").hidden=false;document.getElementById("reload").disabled=false;\n      }catch(e){fail(e);}\n    };\n    img.addEventListener("load",verify,{once:true});img.addEventListener("error",()=>fail("image load error"),{once:true});\n    if(img.complete&&img.naturalWidth)verify();\n    document.getElementById("reload").onclick=()=>{location.reload();};\n  }else if(phase==="form"){\n    const form=document.getElementById("fixture-form"),entry=document.getElementById("entry");\n    let inputs=0;entry.addEventListener("input",()=>inputs++);\n    show("FORM_EMPTY");\n    form.addEventListener("submit",e=>{\n      try{\n        need(e.isTrusted===true,"trusted form submission required");\n        need(inputs>0&&entry.value===expected&&document.getElementById("agree").checked,"form values or input event");\n        const data=Array.from(new FormData(form).entries());\n        need(JSON.stringify(data)===JSON.stringify([["entry",expected],["agree","1"]]),"form serialization");\n      }catch(err){e.preventDefault();fail(err);}\n    });\n  }else if(phase==="submitted"){\n    try{\n      const values=Array.from(new URLSearchParams(location.search).entries());\n      need(JSON.stringify(values)===JSON.stringify([["entry",expected],["agree","1"]]),"submitted query");\n      need(document.referrer===location.origin+prefix+"form.html","same run form referrer");\n      detail.textContent=JSON.stringify({method:"GET",values:values,referrer:document.referrer});\n      show("FORM_SUBMIT_OK value="+expected);document.getElementById("next-media").hidden=false;\n    }catch(e){fail(e);}\n  }else if(phase==="media"){\n    const v=document.getElementById("video"),play=document.getElementById("play"),pause=document.getElementById("pause"),\n      resume=document.getElementById("resume"),next=document.getElementById("next-network");\n    let state="loading",samples=[],events=[],pausedAt=null,playStart=null,playSeen=false;\n    const capture=name=>{\n      events.push({event:name,time:v.currentTime,paused:v.paused,ended:v.ended,ready:v.readyState});\n      if(events.length>64)events.shift();\n      detail.textContent=JSON.stringify({width:v.videoWidth,height:v.videoHeight,duration:v.duration,state:state,\n        currentTime:v.currentTime,pausedAt:pausedAt,samples:samples.slice(-8),events:events});\n    };\n    ["loadedmetadata","loadeddata","canplay","playing","pause","ended","error"].forEach(name=>v.addEventListener(name,()=>capture(name)));\n    v.addEventListener("error",()=>fail("media error code="+(v.error?v.error.code:"unknown")));\n    const ready=()=>{\n      try{\n        if(state!=="loading")return;\n        need(v.videoWidth>0&&v.videoHeight>0&&Number.isFinite(v.duration)&&v.duration>0.2&&v.duration<30,"video metadata");\n        need(v.readyState>=2,"video ready state");state="ready";play.disabled=false;show("MEDIA_READY");capture("fixture-ready");\n      }catch(e){fail(e);}\n    };\n    v.addEventListener("canplay",ready);if(v.readyState>=2)ready();\n    v.addEventListener("timeupdate",()=>{\n      if(state==="starting"||state==="playing"){\n        if(samples.length<64)samples.push(v.currentTime);\n        if(playSeen&&performance.now()-playStart>=150&&samples.length>=2&&Math.max(...samples)>0.05&&!v.paused&&!v.ended){\n          state="playing";pause.disabled=false;show("MEDIA_PLAYING");capture("progress-verified");\n        }\n      }\n    });\n    play.onclick=async()=>{\n      try{\n        need(state==="ready"&&v.paused,"play precondition");state="starting";play.disabled=true;\n        v.muted=true;v.loop=true;playStart=performance.now();await v.play();playSeen=true;\n        need(!v.paused,"play promise state");capture("play-promise-resolved");\n      }catch(e){fail(e);}\n    };\n    pause.onclick=()=>{\n      try{\n        need(state==="playing"&&!v.paused&&samples.length>=2,"pause precondition");\n        v.pause();need(v.paused,"pause readback");pausedAt=v.currentTime;state="pausing";pause.disabled=true;\n        setTimeout(()=>{\n          try{need(v.paused&&Math.abs(v.currentTime-pausedAt)<0.02,"paused time not stable");\n            state="paused";resume.disabled=false;show("MEDIA_PAUSED");capture("pause-stable");}\n          catch(e){fail(e);}\n        },250);\n      }catch(e){fail(e);}\n    };\n    resume.onclick=async()=>{\n      try{\n        need(state==="paused"&&v.paused&&pausedAt!==null,"resume precondition");state="resuming";resume.disabled=true;v.loop=false;\n        await v.play();need(!v.paused||v.ended,"resume readback");capture("resume-promise-resolved");\n      }catch(e){fail(e);}\n    };\n    v.addEventListener("ended",()=>{\n      try{\n        need(state==="resuming"&&v.ended&&v.paused&&Math.abs(v.currentTime-v.duration)<0.1,"ended after resume");\n        state="ended";show("MEDIA_ENDED");capture("ended-verified");next.hidden=false;\n      }catch(e){fail(e);}\n    });\n  }else if(phase==="network"){\n    const button=document.getElementById("https"),next=document.getElementById("next-missing");let ready=false,done=false;\n    (async()=>{\n      try{\n        const response=await fetch("missing.html",{credentials:"omit",cache:"no-store",redirect:"error"});\n        need(response.status===404&&response.url===location.origin+prefix+"missing.html","controlled HTTP404 status");\n        const text=await response.text();need(text.length<16384&&text.includes("Pocket4 controlled 404"),"controlled HTTP404 body");\n        ready=true;button.disabled=false;detail.textContent=JSON.stringify({httpStatus:response.status,url:response.url});\n        show("HTTP_404_HANDLED");\n      }catch(e){fail(e);}\n    })();\n    button.onclick=async()=>{\n      let timer;\n      try{\n        need(ready&&!done,"HTTPS request precondition");button.disabled=true;\n        need(window.isSecureContext&&crypto.subtle,"browser crypto context");\n        const abort=new AbortController();timer=setTimeout(()=>abort.abort(),20000);\n        const r=await fetch(httpsURL,{credentials:"omit",cache:"no-store",redirect:"error",signal:abort.signal});\n        need(r.status===200&&r.url===httpsURL&&!r.redirected&&r.type==="cors","HTTPS response");\n        const reader=r.body.getReader();const chunks=[];let length=0;\n        for(;;){const part=await reader.read();if(part.done)break;length+=part.value.length;\n          if(length>58199){await reader.cancel();throw Error("HTTPS response size bound");}chunks.push(part.value);}\n        need(length===58199,"HTTPS response size");const data=new Uint8Array(length);let offset=0;\n        chunks.forEach(x=>{data.set(x,offset);offset+=x.length;});\n        const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",data))).map(x=>x.toString(16).padStart(2,"0")).join("");\n        need(hash===videoHash,"HTTPS exact asset hash");done=true;\n        detail.textContent=JSON.stringify({httpsURL:httpsURL,status:r.status,type:r.type,bytes:length,sha256:hash,credentials:"omit",redirect:"error"});\n        show("HTTPS_BYTES_OK");next.hidden=false;\n      }catch(e){fail("HTTPS_DEPENDENCY_OR_FEATURE: "+String(e.message||e));}\n      finally{if(timer)clearTimeout(timer);}\n    };\n  }else{\n    detail.textContent=JSON.stringify({path:location.pathname,expected_http_status:404});\n    show("HTTP_404_PAGE_RENDERED");\n  }\n})();\n'.encode('utf-8')

    def page(title, controls):
        return ('<!doctype html><html lang="en"><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<link rel="icon" href="data:,"><title>Pocket4 media fixture</title>\n<style>body{font:16px sans-serif;padding:8px;color:#152338;background:white;line-height:1.3}\nh1{font-size:20px;margin:4px 0}p{margin:5px 0}#run{font-size:11px}\ninput[type=text]{display:block;width:95%;padding:8px;margin:6px 0;font:inherit}\nbutton,a{font:inherit;padding:8px;margin:5px 3px;display:inline-block}\n#result{border:2px solid #256;background:#eef;padding:8px;white-space:pre-wrap;overflow-wrap:anywhere}\n#details{font-size:10px;max-height:38px;overflow:auto;overflow-wrap:anywhere}\nvideo{display:block;width:160px;height:120px;background:#111}img{width:64px;height:64px;image-rendering:pixelated}\n[hidden]{display:none!important}</style><main><h1>' + title + '</h1>\n<p id="run">Waiting for JavaScript</p><p id="js">Waiting for JavaScript</p>' + controls + '\n<p id="result" role="status" aria-live="polite">Waiting for JavaScript</p><p id="details"></p>\n</main><script src="app.js"></script></html>').encode('utf-8')

    ASSETS = {'image.html': ('text/html; charset=utf-8', page('Pocket4 image', '<img id="fixture-image" src="grid.png" alt="Four fixture pixels"><button id="reload" disabled>Reload image page</button><a id="next-form" href="form.html" hidden>Open form</a>')), 'form.html': ('text/html; charset=utf-8', page('Pocket4 form', '<form id="fixture-form" action="submitted.html" method="GET"><label for="entry">Unicode test input</label><input id="entry" name="entry" type="text" autocomplete="off" maxlength="160" required><label for="agree"><input id="agree" name="agree" type="checkbox" value="1" required>Agree to fixture</label><button id="submit" type="submit">Submit fixture form</button></form>')), 'submitted.html': ('text/html; charset=utf-8', page('Pocket4 submitted form', '<a id="next-media" href="media.html" hidden>Open video</a>')), 'media.html': ('text/html; charset=utf-8', page('Pocket4 video', '<video id="video" src="bear.webm" preload="auto" muted playsinline></video><button id="play" disabled>Play video</button><button id="pause" disabled>Pause video</button><button id="resume" disabled>Resume video</button><a id="next-network" href="network.html" hidden>Open network checks</a>')), 'network.html': ('text/html; charset=utf-8', page('Pocket4 network', '<button id="https" disabled>Fetch exact HTTPS asset</button><a id="next-missing" href="missing.html" hidden>Open controlled 404</a>')), 'missing.html': ('text/html; charset=utf-8', page('Pocket4 controlled 404', '<p>This known fixture page has HTTP status 404.</p>')), 'app.js': ('text/javascript; charset=utf-8', SCRIPT), 'grid.png': ('image/png', fixed_png()), 'bear.webm': ('video/webm', fixed_video())}

    def select_asset(path, prefix, range_values):
        if not (isinstance(path, str) and len(path) <= 1024 and isinstance(range_values, list) and (len(range_values) <= 1)):
            return None
        uri = urllib.parse.urlsplit(path)
        if uri.scheme or uri.netloc or uri.fragment or (not uri.path.startswith(prefix)):
            return None
        name = uri.path[len(prefix):]
        if name not in ASSETS:
            return None
        if name == 'submitted.html':
            try:
                values = urllib.parse.parse_qs(uri.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2, encoding='utf-8', errors='strict')
            except (ValueError, UnicodeError):
                return None
            if values != {'entry': [VALUE], 'agree': ['1']}:
                return None
        elif uri.query:
            return None
        mime, body = ASSETS[name]
        status = 404 if name == 'missing.html' else 200
        extra = {}
        if range_values:
            if name != 'bear.webm':
                return None
            match = re.fullmatch('bytes=(\\d*)-(\\d*)', range_values[0])
            if match is None or not (match[1] or match[2]):
                return (name, 416, mime, b'', {'Content-Range': 'bytes */%d' % len(body)})
            if match[1]:
                start = int(match[1])
                end = min(int(match[2]) if match[2] else len(body) - 1, len(body) - 1)
            else:
                count = int(match[2])
                start = max(0, len(body) - count)
                end = len(body) - 1
            if start > end or start >= len(body):
                return (name, 416, mime, b'', {'Content-Range': 'bytes */%d' % len(body)})
            extra['Content-Range'] = 'bytes %d-%d/%d' % (start, end, len(body))
            body = body[start:end + 1]
            status = 206
        if name == 'bear.webm':
            extra['Accept-Ranges'] = 'bytes'
        return (name, status, mime, body, extra)

    def require(value, reason):
        if not value:
            raise RuntimeError(reason)

    def child(net_fd, owner_fd, run, expected_net, lease):
        require(os.getuid() == os.geteuid() == 0 and 15 <= lease <= MAX_LEASE, 'CHILD_ROOT_OR_LEASE_INVALID')
        require(re.fullmatch('[a-f0-9]{32}', run), 'INVALID_RUN_NONCE')
        require(stat.S_ISFIFO(os.fstat(owner_fd).st_mode), 'PRIVATE_PARENT_PIPE_REQUIRED')
        require(fcntl.ioctl(net_fd, 46851) == CLONE_NEWNET and expected_net == 'net:[%d]' % os.fstat(net_fd).st_ino, 'HELD_NETWORK_FD_MISMATCH')
        before = {n: os.readlink('/proc/self/ns/' + n) for n in ('mnt', 'pid', 'uts', 'ipc', 'user', 'cgroup')}
        libc = ctypes.CDLL(None, use_errno=True)
        libc.setns.argtypes = [ctypes.c_int, ctypes.c_int]
        libc.setns.restype = ctypes.c_int
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        require(libc.setns(net_fd, CLONE_NEWNET) == 0, 'NETWORK_ONLY_SETNS_FAILED')
        os.close(net_fd)
        require(os.readlink('/proc/self/ns/net') == expected_net and before == {n: os.readlink('/proc/self/ns/' + n) for n in before}, 'NAMESPACE_SCOPE_CHANGED')
        os.setgroups([])
        os.setgid(1000)
        os.setuid(1000)
        require(os.getresuid() == os.getresgid() == (1000, 1000, 1000) and os.getgroups() == [], 'IDENTITY_DROP_FAILED')
        require(libc.prctl(38, 1, 0, 0, 0) == 0, 'NO_NEW_PRIVILEGES_FAILED')
        process_status = Path('/proc/self/status').read_text()
        require(all((re.findall('^' + name + ':\\s*(\\S+)$', process_status, re.M) == ['0000000000000000'] for name in ('CapEff', 'CapPrm', 'CapAmb'))), 'CAPABILITIES_NOT_DROPPED')
        os.set_blocking(owner_fd, False)

        def parent_gone():
            if select.select([owner_fd], [], [], 0)[0]:
                os.read(owner_fd, 1)
                return True
            return False
        require(not parent_gone(), 'PARENT_GONE_BEFORE_BIND')

        class LeaseEnded(BaseException):
            pass

        def end_lease(number, frame):
            if number == signal.SIGALRM:
                if parent_gone():
                    raise LeaseEnded('PARENT_PIPE_CLOSED')
                if time.monotonic() - start >= lease:
                    raise LeaseEnded('LEASE_EXPIRED')
                return
            raise LeaseEnded('SIGNAL_RECEIVED')
        prefix = '/p4/' + run + '/'
        requests = {name: 0 for name in ASSETS}
        rejected = [0]

        class Handler(http.server.BaseHTTPRequestHandler):

            def setup(self):
                self.request.settimeout(1.0)
                super().setup()

            def log_message(self, format, *args):
                pass

            def serve_asset(self, send_body):
                valid = self.headers.get_all('Host') == ['127.0.0.1:%d' % self.server.server_port] and self.client_address[0] == '127.0.0.1'
                item = select_asset(self.path, prefix, self.headers.get_all('Range') or []) if valid else None
                if item is None:
                    rejected[0] += 1
                    self.send_error(404)
                    return
                name, status, content_type, body, extra = item
                requests[name] += 1
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self' https://raw.githubusercontent.com; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
                for key, value in extra.items():
                    self.send_header(key, value)
                self.end_headers()
                if send_body:
                    self.wfile.write(body)

            def do_GET(self):
                self.serve_asset(True)

            def do_HEAD(self):
                self.serve_asset(False)

        class StaticServer(http.server.HTTPServer):

            def handle_error(self, request, client_address):
                rejected[0] += 1
        server = StaticServer(('127.0.0.1', 0), Handler)
        server.timeout = 0.25
        start = time.monotonic()
        fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
        reason = 'LEASE_EXPIRED'
        try:
            for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM):
                signal.signal(number, end_lease)
            signal.setitimer(signal.ITIMER_REAL, 0.25, 0.25)
            print(json.dumps({'state': 'FIXTURE_READY', 'pid': os.getpid(), 'start_ticks': int(fields[19]), 'uid': os.getuid(), 'gid': os.getgid(), 'groups': os.getgroups(), 'net_namespace': expected_net, 'other_namespaces_unchanged': True, 'address': '127.0.0.1', 'port': server.server_port, 'socket_inode': os.fstat(server.socket.fileno()).st_ino, 'run': run, 'lease_seconds': lease, 'assets': {name: hashlib.sha256(data).hexdigest() for name, (_, data) in ASSETS.items()}}), flush=True)
            while time.monotonic() - start < lease:
                if parent_gone():
                    reason = 'PARENT_PIPE_CLOSED'
                    break
                server.handle_request()
                if sum(requests.values()) + rejected[0] >= 96:
                    reason = 'REQUEST_BUDGET_REACHED'
                    break
        except LeaseEnded as ended:
            reason = str(ended)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM):
                signal.signal(number, signal.SIG_IGN)
            server.server_close()
            os.close(owner_fd)
            print(json.dumps({'state': 'FIXTURE_CLOSED', 'reason': reason, 'requests': requests, 'rejected_requests': rejected[0], 'socket_closed': True}), flush=True)

    return types.SimpleNamespace(assets=ASSETS,pages=PAGES,child=child,select_asset=select_asset)
