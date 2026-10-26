# Same-instance Root administration

The product launcher creates its administrative lane only from the opaque
capability minted by its actual already-prepared Root session. It opens no
second authority service, issuer, clock or registry. The same native launch
and five-listener ready/handoff path still runs once.

The lane is `root-admin.sock` (Root0600) inside the current episode's Root0700
administrative directory. Its write-once `root-admin-instance.json` describes
the socket and original boot/PID/start ticks/fresh nonce. Fresh initialization
uses `admin/`; explicit recovery uses its original `admin/recovery/` episode.
This descriptor is an observation and selector, not a bearer capability.
Existing initialize/recover and one-recovery admission rules are unchanged.

An actual Root administrator can use the installed entry:

```sh
hepta-desktop-root admin --instance-file <Root0600 descriptor> observe
hepta-desktop-root admin --instance-file <same descriptor> revoke-writer \
  --expected-revision <observed original writer revision> \
  --reason-sha256 <nonzero lowercase 64-hex reason digest>
```

The finite client does not initialize/open any authority owner. It requires
the original private descriptor and socket custody, real SO_PEERCRED Root PID,
exact boot/birth, a pidfd opened for that actual connected peer, and the same
instance in the response. The server admits only actual UID0 peers and passes
bounded strict requests into the original live capability. Ordinary UI/model
messages cannot select an administrative operation or connect to this lane.

`observe` reads the actual original Current/material and lease/frontier/head;
it cannot make a Current, lease or grant. After writer revoke it reports that
original revocation without claiming fresh Current. `revoke-writer` uses the
original registry CAS and returns its receipt. It is distinct from revoking
one specific signed Notes effect/FinalUse grant.

Malformed, duplicate or extra arguments, wrong peer/instance/birth/nonce,
stale CAS, changed custody, expired owner/service and unavailable outcome fail
closed. The adapter never retries a mutation. If a reply is lost or the
deadline expires, use original read-only observation; a CLI error does not
prove the revoke was absent. Actual writer revoke may fence/stop the original
Agentd and its human write route. Process exit/expiry is never labelled an
explicit revoke.

Serving is scoped to the original launch. On return the administrative worker
stops, its capability is inactive, and only the exact original socket inode is
removed. A retained descriptor after a crash cannot revive the Root or connect
to a different process. The old recovery rules continue to refuse a live
predecessor, partial ceremony, unsafe material or repeated recovery episode.

Parser/frame/lifetime tests are ordinary component checks. Actual Root
same-object/registry/clock tests and final installed product tests need their
own exact-source results. Neither this document nor an API's existence records
an installed product pass.
