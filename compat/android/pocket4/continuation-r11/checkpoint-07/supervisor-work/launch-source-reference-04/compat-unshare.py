#!/usr/bin/python3 -I
"""Compatibility wrapper for util-linux without unshare --forward-signals."""
import signal,subprocess,sys
args=[a for a in sys.argv[1:] if a != '--forward-signals']
child=subprocess.Popen(['/usr/bin/unshare',*args])
def forward(sig,frame):
    try: child.send_signal(sig)
    except ProcessLookupError: pass
for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP,signal.SIGQUIT):
    signal.signal(sig,forward)
while True:
    try:
        rc=child.wait()
        break
    except InterruptedError:
        continue
raise SystemExit(rc)
