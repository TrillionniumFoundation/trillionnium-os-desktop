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

The same finite client also supports the actual issued-artifact path:

```sh
hepta-desktop-root admin --instance-file <same descriptor> observe-grant --latest \
  --export-grant <new Root0600 file under Root0700 parent>
hepta-desktop-root admin --instance-file <same descriptor> observe-grant \
  --grant-id <actual original signed grant ID>
hepta-desktop-root admin --instance-file <same descriptor> revoke-grant \
  --signed-grant-file <actual exported artifact> \
  --expected-effect-lease-revision <original version> \
  --expected-issuer-head-revision <original observed version> \
  --reason-sha256 <nonzero lowercase 64-hex reason digest>
```

Export verifies the exact captured bytes/digest and strict artifact shape, then
creates and synchronizes a new private file without replacement or re-signing.
The file is an existing artifact, never a Root/admin capability. Its signature,
current original issuer epoch/time and complete existing Notes lease/policy
binding are independently verified by the original live Root before either CAS.
Evicted/missed/restarted observations remain Unknown; latest never substitutes an
older successful capture after a newer capture was lost.

The exact revoke reports success only when both original stores returned and
both existing protected consumer frontiers confirmed the same issuer head via
the original authenticated observation/synchronization path. A known first-store
receipt remains printed even if the second store or synchronization is unknown.
The client exits unsuccessfully for partial/pending/unknown and never retries.
Expiry or writer process exit is not recorded as precise effect/grant revoke.

After a lost/partial revoke reply, read the original two-store result without
resending a mutation:

```sh
hepta-desktop-root admin --instance-file <same descriptor> observe-grant-state \
  --signed-grant-file <same actual exported artifact>
```

It reads the actual exact effect lease/revocation and protected frontier, current
original issuer head and original consumer synchronization. An expired original
artifact can identify this read-only result, explicitly labelled `grant_expired`;
it never authorizes mutation. The original Root/owner/human/issuer lifetime and
current issuer epoch remain mandatory. A missing record is Unknown and never
created, and a returned DTO cannot be supplied in place of a Root capability.

## Development and scoped checks

After selecting one clean compatible Hepta/Desktop combination and regenerating
its real Cargo locks, compile the explicit product entry and run its finite
parser/frame/artifact/outcome tests:

```sh
cargo check --manifest-path services/hepta-session-host/Cargo.toml \
  --features product-root --bin hepta-desktop-root --tests --locked --offline
cargo test --manifest-path services/hepta-session-host/Cargo.toml \
  --features product-root --bin hepta-desktop-root --locked --offline \
  product_root::admin_client:: -- --test-threads=1
python3 support/docs/check_modules.py
```

Hepta's selected crate-local `ROOT_ADMIN.md` gives its original lease, actual
signature/epoch, weak lifetime, cumulative-deadline and session-resource scopes.
Use its `just test` recipe, one test thread and zero retries. Root-only physical
and installed-package cases must be invoked explicitly with their real objects;
ordinary parser/store cases cannot stand in for them. A candidate test result
never upgrades an earlier timeout/failure or another source combination.
