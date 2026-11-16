"""Original fixed assets and one network-namespace-only server. Import is inert."""
from pathlib import Path
import argparse,base64,ctypes,fcntl,hashlib,http.server,json,os,re,select,signal,stat,subprocess,time,struct,zlib,urllib.parse,types

def build(video=None):
    if video is not None:raise RuntimeError("BUSINESS10_HAS_NO_MEDIA_INPUT")
    PAGES = ('a.html', 'b.html', 'reopen.html')
    CLONE_NEWNET = 1073741824

    MAX_LEASE = 600

    VALUE = 'Pocket4 中文 café 😀 — r12'

    SCRIPT = '"use strict";\n(() => {\n  const expected = "Pocket4 中文 café 😀 — r12";\n  const match = location.pathname.match(/^\\/p4\\/([a-f0-9]{32})\\/(a|b|reopen)\\.html$/);\n  const out = document.getElementById("result");\n  const show = (text) => { out.textContent = text; };\n  const fail = (e) => { show("FAIL: " + String(e.message || e)); };\n  if (!match) { fail("unrecognized fixture path"); return; }\n  const run = match[1], phase = match[2], key = "pocket4.webview.r12." + run;\n  document.getElementById("run").textContent = run;\n  document.getElementById("expected").textContent = expected;\n  document.getElementById("js").textContent = "JavaScript ready: " + (19 * 23);\n  const read = () => {\n    const raw = localStorage.getItem(key);\n    if (raw === null) return null;\n    const value = JSON.parse(raw);\n    if (Object.keys(value).sort().join(",") !== "counter,run,schema,value" ||\n        value.schema !== 1 || value.run !== run || value.value !== expected ||\n        ![1,2].includes(value.counter)) throw Error("unexpected owned-key content");\n    return value;\n  };\n  const saved = (value) => {\n    localStorage.setItem(key, JSON.stringify(value));\n    if (JSON.stringify(read()) !== JSON.stringify(value)) throw Error("storage readback differs");\n  };\n  try {\n    if (phase === "a") {\n      const entry = document.getElementById("entry");\n      let inputs = 0, initialAbsent = read() === null, didSave = false;\n      entry.addEventListener("input", () => { inputs++; });\n      show(initialAbsent ? "BASELINE_EMPTY; input is empty" : "EXISTING_OWNED_RECORD; initial gate not satisfied");\n      document.getElementById("save").onclick = () => {\n        try {\n          if (!initialAbsent || didSave || read() !== null) throw Error("fresh-key precondition changed");\n          if (inputs < 1 || entry.value !== expected) throw Error("real Unicode input/readback required");\n          saved({schema:1,run:run,value:entry.value,counter:1}); didSave = true;\n          show("INPUT_AND_STORAGE_OK counter=1 value=" + read().value);\n          document.getElementById("next").hidden = false;\n        } catch (e) { fail(e); }\n      };\n      const backReadback = () => {\n        try {\n          const record = read();\n          if (record && record.counter === 2) show("BACK_READBACK_OK counter=2 value=" + record.value);\n        } catch (e) { fail(e); }\n      };\n      addEventListener("pageshow", backReadback);\n      backReadback();\n    } else if (phase === "b") {\n      const value = read();\n      if (!value || value.counter !== 1) throw Error("navigation record missing or changed");\n      show("SECOND_PAGE_READBACK_OK counter=1 value=" + value.value);\n      document.getElementById("increment").onclick = () => {\n        try {\n          const current = read();\n          if (!current || current.counter !== 1) throw Error("increment precondition changed");\n          saved({schema:1,run:run,value:current.value,counter:2});\n          show("COUNTER_INCREMENT_OK counter=2 value=" + read().value);\n          document.getElementById("increment").disabled = true;\n          document.getElementById("back").hidden = false;\n        } catch (e) { fail(e); }\n      };\n      document.getElementById("back").onclick = () => {\n        try {\n          const current = read();\n          if (!current || current.counter !== 2) throw Error("back precondition changed");\n          history.back();\n        } catch (e) { fail(e); }\n      };\n    } else {\n      const value = read();\n      if (!value || value.counter !== 2) throw Error("reopen persistence record missing or changed");\n      show("REOPEN_READBACK_OK counter=2 value=" + value.value);\n      document.getElementById("cleanup").onclick = () => {\n        try {\n          const current = read();\n          if (!current || current.counter !== 2) throw Error("cleanup precondition changed");\n          localStorage.removeItem(key);\n          if (localStorage.getItem(key) !== null) throw Error("owned-key removal not verified");\n          show("OWNED_KEY_REMOVED"); document.getElementById("cleanup").disabled = true;\n        } catch (e) { fail(e); }\n      };\n    }\n  } catch (e) { fail(e); }\n})();\n'.encode('utf-8')

    def page(title, controls):
        return ('<!doctype html><html lang="en"><meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<link rel="icon" href="data:,"><title>Pocket4 WebView fixture</title>\n<style>body{font:20px sans-serif;padding:18px;color:#152338;background:#fff;line-height:1.5}\ninput,button,a{font:inherit;display:block;margin:14px 0;padding:12px;max-width:100%;box-sizing:border-box}\ninput{width:100%}#result{white-space:pre-wrap;overflow-wrap:anywhere;border:2px solid #256;background:#eef;padding:12px}\n[hidden]{display:none!important}</style><main><h1>' + title + '</h1>\n<p>Run: <span id="run">Waiting for JavaScript</span></p>\n<p id="js">Waiting for JavaScript</p><p>Test text: <span id="expected"></span></p>\n' + controls + '<p id="result" role="status" aria-live="polite">Waiting for JavaScript</p>\n</main><script src="app.js"></script></html>').encode('utf-8')

    ASSETS = {'a.html': ('text/html; charset=utf-8', page('Pocket4 input page', '<label for="entry">Unicode test input</label><input id="entry" type="text" autocomplete="off" maxlength="160"><button id="save">Verify input and store</button><a id="next" href="b.html" hidden>Open second page</a>')), 'b.html': ('text/html; charset=utf-8', page('Pocket4 second page', '<button id="increment">Increment stored counter</button><button id="back" hidden>Return to input page</button>')), 'reopen.html': ('text/html; charset=utf-8', page('Pocket4 reopen page', '<button id="cleanup">Remove this run storage key</button>')), 'app.js': ('text/javascript; charset=utf-8', SCRIPT)}

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

            def do_GET(self):
                name = self.path.removeprefix(prefix) if self.path.startswith(prefix) else None
                valid = name in ASSETS and self.headers.get_all('Host') == ['127.0.0.1:%d' % self.server.server_port] and (self.client_address[0] == '127.0.0.1')
                if not valid:
                    rejected[0] += 1
                    self.send_error(404)
                    return
                content_type, body = ASSETS[name]
                requests[name] += 1
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)

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
                if sum(requests.values()) + rejected[0] >= 64:
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

    return types.SimpleNamespace(assets=ASSETS,pages=PAGES,child=child)
