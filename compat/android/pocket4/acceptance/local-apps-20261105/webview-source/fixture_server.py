#!/usr/bin/python3 -I
"""Fixed WebView fixture. Default: plan only, no socket or child process.

FixtureOwner is for a future caller already holding the Android UI action lock
and a frozen CameraSession. It gives its child only the held network namespace
FD and a private parent-lifetime pipe. No Android namespace/settings are changed.
"""
from pathlib import Path
import argparse, base64, ctypes, fcntl, hashlib, http.server, json, os, re
import select, signal, stat, subprocess, time

CLONE_NEWNET = 0x40000000
MAX_LEASE = 600
VALUE = 'Pocket4 中文 café 😀 — r12'
SCRIPT = r'''"use strict";
(() => {
  const expected = "Pocket4 中文 café 😀 — r12";
  const match = location.pathname.match(/^\/p4\/([a-f0-9]{32})\/(a|b|reopen)\.html$/);
  const out = document.getElementById("result");
  const show = (text) => { out.textContent = text; };
  const fail = (e) => { show("FAIL: " + String(e.message || e)); };
  if (!match) { fail("unrecognized fixture path"); return; }
  const run = match[1], phase = match[2], key = "pocket4.webview.r12." + run;
  document.getElementById("run").textContent = run;
  document.getElementById("expected").textContent = expected;
  document.getElementById("js").textContent = "JavaScript ready: " + (19 * 23);
  const read = () => {
    const raw = localStorage.getItem(key);
    if (raw === null) return null;
    const value = JSON.parse(raw);
    if (Object.keys(value).sort().join(",") !== "counter,run,schema,value" ||
        value.schema !== 1 || value.run !== run || value.value !== expected ||
        ![1,2].includes(value.counter)) throw Error("unexpected owned-key content");
    return value;
  };
  const saved = (value) => {
    localStorage.setItem(key, JSON.stringify(value));
    if (JSON.stringify(read()) !== JSON.stringify(value)) throw Error("storage readback differs");
  };
  try {
    if (phase === "a") {
      const entry = document.getElementById("entry");
      let inputs = 0, initialAbsent = read() === null, didSave = false;
      entry.addEventListener("input", () => { inputs++; });
      show(initialAbsent ? "BASELINE_EMPTY; input is empty" : "EXISTING_OWNED_RECORD; initial gate not satisfied");
      document.getElementById("save").onclick = () => {
        try {
          if (!initialAbsent || didSave || read() !== null) throw Error("fresh-key precondition changed");
          if (inputs < 1 || entry.value !== expected) throw Error("real Unicode input/readback required");
          saved({schema:1,run:run,value:entry.value,counter:1}); didSave = true;
          show("INPUT_AND_STORAGE_OK counter=1 value=" + read().value);
          document.getElementById("next").hidden = false;
        } catch (e) { fail(e); }
      };
      const backReadback = () => {
        try {
          const record = read();
          if (record && record.counter === 2) show("BACK_READBACK_OK counter=2 value=" + record.value);
        } catch (e) { fail(e); }
      };
      addEventListener("pageshow", backReadback);
      backReadback();
    } else if (phase === "b") {
      const value = read();
      if (!value || value.counter !== 1) throw Error("navigation record missing or changed");
      show("SECOND_PAGE_READBACK_OK counter=1 value=" + value.value);
      document.getElementById("increment").onclick = () => {
        try {
          const current = read();
          if (!current || current.counter !== 1) throw Error("increment precondition changed");
          saved({schema:1,run:run,value:current.value,counter:2});
          show("COUNTER_INCREMENT_OK counter=2 value=" + read().value);
          document.getElementById("increment").disabled = true;
          document.getElementById("back").hidden = false;
        } catch (e) { fail(e); }
      };
      document.getElementById("back").onclick = () => {
        try {
          const current = read();
          if (!current || current.counter !== 2) throw Error("back precondition changed");
          history.back();
        } catch (e) { fail(e); }
      };
    } else {
      const value = read();
      if (!value || value.counter !== 2) throw Error("reopen persistence record missing or changed");
      show("REOPEN_READBACK_OK counter=2 value=" + value.value);
      document.getElementById("cleanup").onclick = () => {
        try {
          const current = read();
          if (!current || current.counter !== 2) throw Error("cleanup precondition changed");
          localStorage.removeItem(key);
          if (localStorage.getItem(key) !== null) throw Error("owned-key removal not verified");
          show("OWNED_KEY_REMOVED"); document.getElementById("cleanup").disabled = true;
        } catch (e) { fail(e); }
      };
    }
  } catch (e) { fail(e); }
})();
'''.encode('utf-8')


def page(title, controls):
    return ('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,"><title>Pocket4 WebView fixture</title>
<style>body{font:20px sans-serif;padding:18px;color:#152338;background:#fff;line-height:1.5}
input,button,a{font:inherit;display:block;margin:14px 0;padding:12px;max-width:100%;box-sizing:border-box}
input{width:100%}#result{white-space:pre-wrap;overflow-wrap:anywhere;border:2px solid #256;background:#eef;padding:12px}
[hidden]{display:none!important}</style><main><h1>''' + title + '''</h1>
<p>Run: <span id="run">Waiting for JavaScript</span></p>
<p id="js">Waiting for JavaScript</p><p>Test text: <span id="expected"></span></p>
''' + controls + '''<p id="result" role="status" aria-live="polite">Waiting for JavaScript</p>
</main><script src="app.js"></script></html>''').encode('utf-8')


ASSETS = {
    'a.html': ('text/html; charset=utf-8', page('Pocket4 input page',
        '<label for="entry">Unicode test input</label><input id="entry" type="text" autocomplete="off" maxlength="160">'
        '<button id="save">Verify input and store</button><a id="next" href="b.html" hidden>Open second page</a>')),
    'b.html': ('text/html; charset=utf-8', page('Pocket4 second page',
        '<button id="increment">Increment stored counter</button><button id="back" hidden>Return to input page</button>')),
    'reopen.html': ('text/html; charset=utf-8', page('Pocket4 reopen page',
        '<button id="cleanup">Remove this run storage key</button>')),
    'app.js': ('text/javascript; charset=utf-8', SCRIPT),
}


def require(value, reason):
    if not value: raise RuntimeError(reason)


def child(net_fd, owner_fd, run, expected_net, lease):
    require(os.getuid() == os.geteuid() == 0 and 15 <= lease <= MAX_LEASE, 'CHILD_ROOT_OR_LEASE_INVALID')
    require(re.fullmatch('[a-f0-9]{32}', run), 'INVALID_RUN_NONCE')
    require(stat.S_ISFIFO(os.fstat(owner_fd).st_mode), 'PRIVATE_PARENT_PIPE_REQUIRED')
    require(fcntl.ioctl(net_fd, 0xb703) == CLONE_NEWNET and
            expected_net == 'net:[%d]' % os.fstat(net_fd).st_ino, 'HELD_NETWORK_FD_MISMATCH')
    before = {n: os.readlink('/proc/self/ns/' + n) for n in ('mnt','pid','uts','ipc','user','cgroup')}
    libc = ctypes.CDLL(None, use_errno=True)
    libc.setns.argtypes = [ctypes.c_int, ctypes.c_int]; libc.setns.restype = ctypes.c_int
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    require(libc.setns(net_fd, CLONE_NEWNET) == 0, 'NETWORK_ONLY_SETNS_FAILED')
    os.close(net_fd)
    require(os.readlink('/proc/self/ns/net') == expected_net and
            before == {n: os.readlink('/proc/self/ns/' + n) for n in before}, 'NAMESPACE_SCOPE_CHANGED')
    os.setgroups([]); os.setgid(1000); os.setuid(1000)
    require(os.getresuid() == os.getresgid() == (1000,1000,1000) and os.getgroups() == [], 'IDENTITY_DROP_FAILED')
    require(libc.prctl(38, 1, 0, 0, 0) == 0, 'NO_NEW_PRIVILEGES_FAILED')
    process_status = Path('/proc/self/status').read_text()
    require(all(re.findall(r'^' + name + r':\s*(\S+)$', process_status, re.M) == ['0000000000000000']
                for name in ('CapEff', 'CapPrm', 'CapAmb')), 'CAPABILITIES_NOT_DROPPED')
    os.set_blocking(owner_fd, False)
    def parent_gone():
        if select.select([owner_fd], [], [], 0)[0]:
            # Parent sends no data; EOF or unexpected data ends the lease.
            os.read(owner_fd, 1)
            return True
        return False
    require(not parent_gone(), 'PARENT_GONE_BEFORE_BIND')
    class LeaseEnded(BaseException): pass
    def end_lease(number, frame):
        if number == signal.SIGALRM:
            if parent_gone(): raise LeaseEnded('PARENT_PIPE_CLOSED')
            if time.monotonic() - start >= lease: raise LeaseEnded('LEASE_EXPIRED')
            return
        raise LeaseEnded('SIGNAL_RECEIVED')
    prefix = '/p4/' + run + '/'
    requests = {name: 0 for name in ASSETS}; rejected = [0]
    class Handler(http.server.BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(1.0)
            super().setup()
        def log_message(self, format, *args): pass
        def do_GET(self):
            name = self.path.removeprefix(prefix) if self.path.startswith(prefix) else None
            valid = (name in ASSETS and self.headers.get_all('Host') == ['127.0.0.1:%d' % self.server.server_port]
                     and self.client_address[0] == '127.0.0.1')
            if not valid:
                rejected[0] += 1; self.send_error(404); return
            content_type, body = ASSETS[name]; requests[name] += 1
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(body)
    class StaticServer(http.server.HTTPServer):
        def handle_error(self, request, client_address): rejected[0] += 1
    server = StaticServer(('127.0.0.1', 0), Handler)
    server.timeout = .25
    start = time.monotonic()
    fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
    reason = 'LEASE_EXPIRED'
    try:
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM):
            signal.signal(number, end_lease)
        # Check the private parent pipe and hard lease even while a client
        # trickles bytes below its per-read socket timeout.
        signal.setitimer(signal.ITIMER_REAL, .25, .25)
        print(json.dumps({'state':'FIXTURE_READY','pid':os.getpid(),'start_ticks':int(fields[19]),
            'uid':os.getuid(),'gid':os.getgid(),'groups':os.getgroups(),'net_namespace':expected_net,
            'other_namespaces_unchanged':True,'address':'127.0.0.1','port':server.server_port,
            'socket_inode':os.fstat(server.socket.fileno()).st_ino,'run':run,'lease_seconds':lease,
            'assets':{name:hashlib.sha256(data).hexdigest() for name,(_,data) in ASSETS.items()}}), flush=True)
        while time.monotonic() - start < lease:
            if parent_gone(): reason = 'PARENT_PIPE_CLOSED'; break
            server.handle_request()
            if sum(requests.values()) + rejected[0] >= 64: reason = 'REQUEST_BUDGET_REACHED'; break
    except LeaseEnded as ended:
        reason = str(ended)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM):
            signal.signal(number, signal.SIG_IGN)
        server.server_close(); os.close(owner_fd)
        print(json.dumps({'state':'FIXTURE_CLOSED','reason':reason,'requests':requests,
                          'rejected_requests':rejected[0],'socket_closed':True}), flush=True)


class FixtureOwner:
    """Future UI caller owns this scope; close uses its exact child pidfd only."""
    def __init__(self, session, source_path, source_sha256, run, journal, lease=MAX_LEASE):
        require(re.fullmatch('[a-f0-9]{32}', run) and 15 <= lease <= MAX_LEASE, 'RUN_OR_LEASE_INVALID')
        self.s, self.path, self.pin, self.run = session, Path(source_path), source_sha256, run
        self.journal, self.lease = Path(journal), lease
        self.process = None; self.pidfd = self.owner_write = None; self.trailing = b''
        self.closed = False
        self.result = {'server_started':False,'own_child_reaped':False,'other_process_signals':0}

    def __enter__(self):
        self.journal.mkdir(mode=0o700)
        raw = self.path.read_bytes()
        require(len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == self.pin, 'FIXTURE_SOURCE_CHANGED')
        self.s.guard(); net = self.s.target.namespaces['net']
        expected = 'net:[%d]' % os.fstat(net).st_ino
        reader, self.owner_write = os.pipe2(os.O_CLOEXEC)
        wrapper = ('import base64,hashlib;raw=base64.b64decode(' + repr(base64.b64encode(raw).decode()) + ');'
                   'assert hashlib.sha256(raw).hexdigest()==' + repr(self.pin) + ';'
                   "exec(compile(raw,'owned-webview-fixture','exec'),{'__name__':'__main__'})")
        try:
            self.process = subprocess.Popen(['/usr/bin/python3','-I','-c',wrapper,'--child',
                str(net),str(reader),self.run,expected,str(self.lease)],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},close_fds=True,pass_fds=(net,reader),start_new_session=True)
            self.result['server_started'] = True
            self.pidfd = os.pidfd_open(self.process.pid, 0)
        except BaseException:
            self.close(); raise
        finally:
            os.close(reader)
        try:
            received, deadline = b'', time.monotonic() + 8
            while b'\n' not in received:
                require(time.monotonic() < deadline and len(received) < 8192, 'FIXTURE_READY_TIMEOUT_OR_OVERSIZE')
                if select.select([self.process.stdout],[],[],.25)[0]:
                    chunk = os.read(self.process.stdout.fileno(), 4096)
                    require(bool(chunk), 'FIXTURE_EXITED_BEFORE_READY'); received += chunk
            line, self.trailing = received.split(b'\n', 1)
            self.ready = json.loads(line)
            require(self.ready['state']=='FIXTURE_READY' and self.ready['pid']==self.process.pid and
                    self.ready['uid']==self.ready['gid']==1000 and self.ready['groups']==[] and
                    self.ready['net_namespace']==expected and self.ready['address']=='127.0.0.1' and
                    1024 <= self.ready['port'] <= 65535 and self.ready['run']==self.run and
                    self.ready['assets']=={n:hashlib.sha256(b).hexdigest() for n,(_,b) in ASSETS.items()},
                    'FIXTURE_READY_BINDING_CHANGED')
            self.s.guard(); self.ensure_alive()
            self.result['ready'] = self.ready
            (self.journal/'ready.json').write_text(json.dumps(self.ready,indent=2)+'\n')
            return self
        except BaseException:
            self.close(); raise

    def ensure_alive(self):
        self.s.guard()
        require(self.process is not None and self.process.poll() is None, 'OWNED_FIXTURE_NOT_RUNNING')

    def url(self, name):
        require(name in ('a.html','b.html','reopen.html'), 'FIXTURE_PATH_NOT_ALLOWED')
        self.ensure_alive()
        return 'http://127.0.0.1:%d/p4/%s/%s' % (self.ready['port'],self.run,name)

    def close(self):
        if self.closed: return
        if self.owner_write is not None:
            os.close(self.owner_write); self.owner_write = None
        if self.process is not None and not self.result['own_child_reaped']:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                require(self.pidfd is not None, 'MISSING_OWNED_PIDFD_NO_NUMERIC_SIGNAL')
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try: signal.pidfd_send_signal(self.pidfd, sig)
                    except ProcessLookupError: pass
                    try: self.process.wait(timeout=2); break
                    except subprocess.TimeoutExpired: continue
            require(self.process.poll() is not None, 'OWN_CHILD_NOT_REAPED')
            out, err = self.process.communicate(timeout=1)
            self.result.update(own_child_reaped=True,exit_code=self.process.returncode,
                               child_stdout=(self.trailing+out).decode('utf-8','strict'),
                               child_stderr=err.decode('utf-8','replace'),source_sha256=self.pin)
        if self.pidfd is not None: os.close(self.pidfd); self.pidfd = None
        if self.journal.is_dir():
            with (self.journal/'owner-result.json').open('x') as output:
                json.dump(self.result,output,indent=2); output.write('\n')
        self.closed = True

    def __exit__(self, typ, value, trace): self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',nargs=5,metavar=('NET_FD','OWNER_FD','RUN','NET_ID','LEASE'))
    args = parser.parse_args()
    if args.child:
        net, owner, run, expected, lease = args.child
        child(int(net),int(owner),run,expected,int(lease)); return
    print(json.dumps({'state':'PLAN_ONLY','socket_created':False,'child_started':False,
        'bind_address':'127.0.0.1','port_selection':'kernel port 0','maximum_lease_seconds':MAX_LEASE,
        'requires_held_android_net_namespace':True,'child_uid':1000,'child_gid':1000,
        'assets':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,(_,data) in ASSETS.items()}},indent=2))


if __name__ == '__main__': main()
