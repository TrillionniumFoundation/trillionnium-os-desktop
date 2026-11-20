# Gallery current image consumer

This source packet connects the official Gallery image member to the native
image custody producer and preserves four existing bounded business cases. It
does not install or patch Gallery, adopt a native release, start Android, or
grant runtime, data continuity or whole-application acceptance.

The former Gallery routes required a standalone modified APK and historical
installation/ART receipts. Those historical entry points remain retired. The
new entry obtains custody from a fresh call to the original production daemon
through the adopted `droidloom-applications` executable, and binds the response
to the actual current held Main before using any business helper.

## Source and runtime contracts

| Item | Exact contract |
| --- | --- |
| Package | `com.android.gallery3d`, Android user `0`, version code `40030` |
| Image member | `/system/product/app/Gallery2/Gallery2.apk` |
| Package Manager alias | `/product/app/Gallery2/Gallery2.apk`, proved to name the same inode |
| APK | 7,390,425 bytes; SHA-256 `835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439` |
| Complete system image | 2,294,853,632 bytes; SHA-256 `dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4` |
| Producer wire schema | `droidloom-image-application-custody-v1` |
| Canonical native executable | `/usr/bin/droidloom-applications` |
| Canonical production socket | `/run/droidloom/control.sock` |
| Request schema | `pocket4-gallery-image-request-v1` |
| Request fields | `schema`, `baseline`, `qualification`, `output`, `native_release` |
| Result schema | `pocket4-gallery-image-scope-v1` |
| Identity result | `CURRENT_IMAGE_OBSERVED_BUSINESS_PENDING` |
| Finite business result | `CURRENT_IMAGE_SCOPE_AND_CLEANUP_VERIFIED` |
| Standard output result reference | Exact `{path, bytes, sha256}` FilePin |
| Native overall budget | 1,530 seconds, including both captures and bounded retirement |

The complete wire validator is based on the actual producer source in
[`current-runtime-successor-20261120`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/1af163b21f5c7dcaaf94084d7cc1ef19aed05ae1/compat/android/pocket4/current-runtime-successor-20261120).
It checks whole system/vendor/APK read bookends, current owner and physical
epoch, namespace identities, UID/GID mappings, read-only loop/mount ownership,
the exact seven queries and output hashes, worker retirement, and the original
MAC/seccomp execution receipt. Parsing an internally coherent JSON document
does not create a live capture or execution authority.

The native executable hash is supplied by an adopted detached release, not by
the preparation. This avoids a binary-hash → preparation → compiled-catalog →
binary-hash cycle. The release validator must hold the original two lock OFDs,
the current owner, the exact canonical CURRENT successor, the complete source
selector and catalog, and the final native executable throughout execution.
An arbitrary root-owned manifest is insufficient without the canonical
adoption relation. The request supplies only the manifest's external FilePin.

Each business run performs an actual fresh native capture, the original
600-second business phase with a separate 120-second cleanup phase, and a
second actual fresh native capture. Both captures must bind to the same image
and owner cohort. The outer entry never imports a saved custody receipt or
installation receipt. A cancellation, unknown effect, missing prior terminal
reconciliation, failed cleanup or changed final image cannot become a success.

The native parent owns a nested child cgroup within its existing cancellation
scope. The live `OwnedLeafResources` object proves the actual parent process,
executable, pidfd, held resource controls and child membership. The consumer
independently checks the reported effective limits and its own process state:
at most two CPUs, a 2 GiB ancestor memory ceiling, zero swap, 64 PIDs, no OOM
events, CPU affinity within `{20, 21}`, and disabled core dumps. It never
changes a shared ancestor, accepts a caller-supplied cgroup path, or interprets
a saved JSON resource report as permission. Without a bound live object, the
original strict local resource checker remains intact.

## Repairs in the bridge

1. Gallery UID is observed in the current image; it is not copied from a
   historical `10064` constant. Package and logcat commands retain the guest
   UID, while host `fstat` ownership checks use the actual held UID/GID maps.
2. Native capture uses the existing zero-FD host command interface. The
   original recorder accepts zero or the exact seven held Android descriptors;
   the bridge does not relax that rule. The fixed native path has held file,
   complete SHA-256 and metadata bookends under the adopted release lease.
3. Rotation reads and compares all 29 permission rows. Its 27 Android
   permission rows remain separately available for diagnostics. Missing or
   duplicated custom permission rows are rejected.
4. The new copies use the reviewed CP3A MediaProvider source binding and the
   original official Gallery APK identity. Old install and ART replacement
   modules are excluded from the executable source graph.
5. The request, result FilePin, overall deadline and source catalog are explicit
   native-driver contracts. Changing selector metadata alone is insufficient
   to adopt or execute this protocol.

The existing task, fixture, media, descriptor and terminal cleanup functions
remain unchanged. This packet's finite success is still narrower than the
original application's enumeration/open/persistence, stability, lifecycle,
permissions, dependency and whole-release gates.

## Reproduce the source packet

From this directory in a checkout containing the earlier source adapter:

```sh
python3 adapt_sources.py
python3 prepare_sources.py
python3 -m unittest discover -s tests -v
```

`inputs/source-origin-pins.json` identifies all 59 exact original files.
Thirty-two are independently matched to their existing Git blobs; the 27 video
and seek originals absent from that committed adapter are retained under
`inputs/additional-originals` with exact original host identities. The five
original preparation bodies are separate immutable provenance inputs. They do
not confer current runtime authority. `adapt_sources.py` fails on a missing
group or a source hash mismatch before generating the 51 derived files.

`prepare_sources.py` creates five source preparations. The source graph reads
the reviewed candidate host consumers under `pocket4-android-final/consumers`;
the actual business APIs still require those exact bodies at their production
installation paths. The older live installed consumer hashes are never
silently substituted for the new candidates.

`inspect-source` runs the real original support bootstrap and verifies the
entire pinned source graph without constructing a MainView, opening the native
release lease, invoking the native CLI or dispatching an Android command.
`SOURCE-INSPECTION.json` records five successful host bootstraps, two actual
invalid-input refusals, and unchanged SHA/F9 bookends for 70 references. The
initial failed inspection is retained separately; it identified the distinction
between reviewed host-consumer candidates and their older installed bodies.
Fourteen unit controls exercise the actual recorder argument checks and the
wire/permission/resource consumers; model fixtures explicitly grant no live
execution credit.

After the host inspection report is present, `prepare_selection.py` creates a
complete 13-entry selector, catalog and 42-package route map. Indices 0–7 and
the other 41 package rows remain unchanged. This command does not write
CURRENT. Formal source adoption uses the original locks and a fresh complete
CURRENT compare-and-swap. Native release adoption is a later distinct gate
after the actual binary has been built and verified.

## Remaining actual execution gates

The new native leaf driver and its final compiled catalog must match these
five preparations and the complete selector. Its final artifact must be
adopted under the unchanged canonical owner protocol. The coherent Android
system/vendor/runtime cohort, current held Main, reviewed installed host
consumers and exact per-App engine mapping must then pass their original
runtime requirements. The four finite cases, cleanup, persistence, required
repeat/soak budget and whole-application release acceptance remain actual
execution work. Every runtime, business, data continuity and production flag
in this source packet remains false until those independent gates succeed.
