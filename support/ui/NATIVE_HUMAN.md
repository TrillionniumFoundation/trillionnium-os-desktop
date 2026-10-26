# Local-login provider for the original Root native launcher

`product/native_human.py` is an explicit Linux Root administrator/provider
preparation entry. The ordinary desktop launch does not invoke it. It captures
one actual, active, local physical systemd-logind user session for the UID in an
existing original daemon configuration. It uses the Root-owned system bus and
the checked loginctl executable inode, retains that login's actual leader pidfd,
and rechecks its start identity and session after the original native diagnostic.
With `--lifetime-channel-fd`, it also transfers that same held leader descriptor
and bounded capture receipt to its actual UID0 parent over the original unnamed
Unix datagram pair. It verifies the kernel peer credentials before sending.
The receiver must verify the sender's original child credentials, descriptor
count, exact receipt/profile hash and source before installing the lifetime.
It requires the original supervisor's already-held daemon pidfd as input; a PID
lookup cannot supply a replacement owner descriptor.

The protected template supplies the native program, its full digest, arguments,
working directory, allowed environment, fresh socket, exact AppServer route,
finite lifetime, and explicit interrupt/approval choices. Human principal,
session, revision and expiry fields are forbidden template inputs. The principal
namespace derives from the actual machine and UID; the session namespace binds
the actual boot, logind session and leader start ticks. These names correlate
the authenticated local login. They do not constitute a grant by themselves.

All input files and the new output require canonical Root0700 parent directories
and Root0600 single-link regular files. Duplicate JSON fields reject. The
profile expires within five minutes and no later than the existing writer
lease; its permission revision is that lease's revision. The original
`hepta-authority-host diagnose-native` must independently accept the exact
program, original daemon, protected Root mount/state, writer, route and human
profile before the output is published without replacement. This preparation
entry never initializes or renews authority, registers a daemon/writer, creates
a thread, reads provider credentials, or invokes a model.

Root initialization, registration and launch remain explicit original APIs.
First deployment must create the real original AppServer thread and preserve
its actual returned route, obtain the actual supervisor registration, initialize
the dedicated protected Root state, then capture the real login and launch.
The original process and human lifetimes must remain supervised during runtime;
this point-in-time capture is not logout supervision or a product acceptance
receipt. A native diagnostic reports `production_ready=false`. A real model
operation, original Notes effect and independent exact result/recovery checks
remain separate required acceptance gates.

Run trust-boundary tests from `support/ui/product` with
`python3 -m unittest test_native_human`. Two filesystem cases require explicit
real Root execution; additional Root cases cover shared ancestry refusal and
actual pidfd transfer to the original parent. They are skipped for ordinary users. Parser
fixtures are local boundary tests, never authenticated production evidence.
