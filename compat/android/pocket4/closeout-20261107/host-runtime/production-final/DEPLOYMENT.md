# Exact eleven-target deployment

## Frozen inputs

All paths below are on host pocket4.

- Deployment directory: /home/alex/work/pocket4-status-readiness-finalize-20261107-r1/deployment
- manifest.json: 25769 bytes, SHA-256 b9d5c284356744e3f6a9d90389a72cb41dd946598c0858b7fa49f87ccab9cbbc
- deploy_cohort.py: SHA-256 fee5480b05302eb2bf129fb143a13389072289ac91968a7ea27923ebeddc6373
- prepare-result.json: 481 bytes, SHA-256 bbec71971f03620a83f1708f503342a2e4918b1d7ab7db3f0017c0fbd577e3fd
- Preparation job: 1a1b3b3f110-fc05-8460

The complete deployment manifest contains private old Main identities and is kept outside this public source package. It is an original UTF-8 file, not a JSON object reserialized through JavaScript. Its exact eleven targets are the four /usr/bin Droidloom binaries, three retained /usr/local/bin Android consumers, three actual /usr/local/libexec consumers, and:

/opt/pocket4-wifi-disabled-api-20261023-chat2-v2/payload/services-candidate.jar

The reviewed Storage replacement changes that one selected framework provider from f33987e633e476f47ea043af3f7fb94907fd2431fa2b5b49df84cb586bce5c50 to f1acb56e23cd9082a77ef686f2e840a736e7769dd8843830e53e56b1ac31566f and preserves root:root mode 0444. The v2 Storage input member is pinned at dc36c6712d184e39eb5f7b0fbc22631cb90da85e06e613035b712dcd66f69dfa; the original held read receipt remains 4491a171914fed71d22518272718b14fccb8592b8d94116d1c6a558dace3a104.

Preparation copied candidate and rollback payloads into this private deployment directory, verified all installed targets were still their exact baseline bytes, checked the old eight processes and system/user MainPID identities, and executed the ten transaction regressions in owned temporary files on Pocket4. It did not stop, replace or restart installed services.

## Transaction boundary

The default check is read-only. apply-stopped and rollback-stopped require an external manifest SHA, the exact eleven-target allowlist, complete frozen payloads and evidence, root authority and two nonblocking locks. They require all of the following before changes, before every rename and after readback:

- System droidloomd.service inactive with MainPID=0 and ControlPID=0.
- User droidloom.service and droidloom-applications.service inactive with the same zero-PID conditions.
- All eight old process identities gone and no process remaining in the old Android PID namespace.
- The recorded boot, data directory identity, current alias, package marker/state and protected files unchanged.

Protected files and modified targets have an empty intersection. The current compat/unshare wrapper, Python3.14, util-linux unshare/ip, service definitions/drop-ins and presenter remain protected. No Status, Readiness, Android command or lifecycle operation is issued inside the installer.

The existing paired transaction core stages every payload in its target directory, preserves the verified uid/gid/mode/mtime/xattrs, fsyncs each staged file, renames each target and fsyncs its directory, then verifies every installed hash and attribute. It also checks named-path versus held-FD identity while reading.

On a commit failure it restores the entire baseline cohort only while stopped guards still pass and every target contains a recognized baseline or candidate hash. Unknown bytes, changed attributes or newly active services stop automatic recovery. A durable execution guard and journal prevent blind replay. The transaction is a matched set of atomic file replacements while consumers are stopped; it is not a claim that eleven files share one atomic filesystem rename.

## Normal lifecycle sequence

The root coordinator owns this sequence and preserves each command's real stdout, stderr, exit and terminal evidence. Do not run it concurrently with Android business flows, namespace entry or package installation.

First run the read-only check as root:

~~~sh
sudo -n /usr/bin/python3 -I /home/alex/work/pocket4-status-readiness-finalize-20261107-r1/deployment/deploy_cohort.py --mode check --manifest-sha256 b9d5c284356744e3f6a9d90389a72cb41dd946598c0858b7fa49f87ccab9cbbc
~~~

Run normal stop as uid 1000 with a bounded 175-second controller timeout:

~~~sh
env -u WAYLAND_DISPLAY -u DISPLAY -u XDG_CURRENT_DESKTOP XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus /usr/bin/droidloomctl --json stop
~~~

Explicitly stop the user application service and check the result; do not merely assume PartOf propagation completed:

~~~sh
env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus /usr/bin/systemctl --user stop droidloom-applications.service
~~~

Then run the frozen installer as root:

~~~sh
sudo -n /usr/bin/python3 -I /home/alex/work/pocket4-status-readiness-finalize-20261107-r1/deployment/deploy_cohort.py --mode apply-stopped --manifest-sha256 b9d5c284356744e3f6a9d90389a72cb41dd946598c0858b7fa49f87ccab9cbbc
~~~

Require a successful durable apply-result.json, final_pair=candidate, all eleven after snapshots, and complete remote terminal evidence. A command timeout or lost result is an unknown outcome to reconcile from the execution guard, journal, installed files and process state; it does not authorize automatic retry.

Start normally as uid 1000, then wait through the existing readiness gate, each with a bounded 180-second controller timeout:

~~~sh
env -u WAYLAND_DISPLAY -u DISPLAY -u XDG_CURRENT_DESKTOP XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus /usr/bin/droidloomctl --json start --no-wait --mode desktop --spec /etc/droidloom/cell.json
env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus /usr/bin/droidloomctl --json wait
~~~

After startup, verify active services, exact installed cohort, the running daemon ELF and selected guest services.jar backing. Use Readiness only when fresh Android readiness is intended. Lifecycle Status must report the same authenticated owner without adding a child; it must not claim Android readiness.

Create a new explicit Main baseline and R7 shared contract from actual new identities. The old baseline's inode equality is not an upgrade qualification. The new v3 lineage must match the exact deployment receipt/cohort while retaining full Main8, unique-child, owner, namespace, package/UID, source and nonce requirements. Historical failures and unknown outcomes stay historical. Old R6 source and nonce values are not reauthorized.

Only after the new contract is qualified should the Storage lifecycle state machine perform its reviewed normal unmount/mount and holder/FUSE retirement/reopen checks through a new held context. droidloomctl has no public arbitrary exec/shell interface.

## Post-start failure and rollback

A failed startup or post-start validation does not permit replacement while Main is active.

1. Preserve the failed startup/verification receipt.
2. Stop normally using the same uid-1000 lifecycle command and explicitly stop the application service.
3. Confirm the current failed generation has fully exited. The installer independently requires inactive services and the old namespace empty; the coordinator must also retire the newly started failed generation and its held descriptors.
4. Run the explicit rollback while stopped:

~~~sh
sudo -n /usr/bin/python3 -I /home/alex/work/pocket4-status-readiness-finalize-20261107-r1/deployment/deploy_cohort.py --mode rollback-stopped --manifest-sha256 b9d5c284356744e3f6a9d90389a72cb41dd946598c0858b7fa49f87ccab9cbbc
~~~

5. Require complete all-target rollback readback, then start and wait normally. This restored startup is another new generation and requires its own actual observation; do not copy old PID, namespace, inode or nonce values.

If stopped-state or recognized-byte checks fail, stop the sequence and reconcile the recorded state before another action. Do not delete the execution guard or change allowlists to make a retry pass.

## Cleanup after acceptance

Keep the final source checkout, one current production binary cohort, the dependencies needed to rebuild it, and compact source/test/deployment receipts. After the root coordinator verifies the new Main and Storage result, the cleanup owner can remove the initial incompatible target directory, superseded consumer staging trees and obsolete isolation files while retaining their failure/pass records and source/hash lineage. Retire old QA/v2/before-discovery launchers only after active references and user-facing QA suggestions have been removed.

