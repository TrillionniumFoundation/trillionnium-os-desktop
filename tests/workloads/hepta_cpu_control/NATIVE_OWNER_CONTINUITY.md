# Original native owner continuity gates

The two additional scenarios execute the reviewed original Hepta entry with
the same source-bound G2 product kernel. They use the original Supervisor,
Root authority, writer, Current publication, FinalUse consumers and HOS2
transport. The Python modules only read evidence. A kernel test, parser
fixture, successful compilation or an unrelated small ELF cannot qualify
either scenario.

The four earlier scenarios retain their event schemas and checks. The shared
immutable K/D request, terminal, Current, history acknowledgment and CPU-window
checks are reused for every new Manager effect. Original owner file size is
still at most 8 MiB and total ELF LOAD memory at most 16 MiB. The original
default features, build profile and kernel authority limits remain unchanged.

## Accepted additional scopes

| Scenario | Required observations | Outer execution bound |
| --- | --- | --- |
| `successor-renewal-v1` | Original finite owners successfully release and reap; at least two fresh kernel pairs; a new actual Manager Applied receipt strictly after the initial Manager ReadUsage sample plus 330 seconds; a real progressing CPU/heartbeat window of at least two periods after every effect/ACK | 600 seconds, at most 64 Manager cycles and 1024 events |
| `history-only-after-both-owner-exit-v1` | Actual EBUSY before and after both initial privileged images die; pidfd SIGKILL/WNOWAIT observations; original failed Recovery-slot transaction/reap; original lease expiry; actual role-5 query/retirement with null usage; successful release/reap; fresh Manager Applied effect and two-period usage window | Original 120-second maximum and 128 events |

The long campaign does not extend a previously issued lease. Root/Host
sessions remain 120 seconds, writer leases 20 seconds, native Manager grants
300 seconds, Recovery grace 30 seconds and the independent watchdog 5 seconds.
Every complete authority lease, signed writer proof and Current binding must
match the actual original DTO. The parser reconstructs canonical proof and
grant-bound fencing digests; signature/current-authority verification remains
the original Host/RootSession's responsibility, bound by the compiled source
review and actual execution. An unprovided key is not reconstructed or assumed.

The cold-open-capable original entry names every writer authority lease
`native-cpu.writer.<actual Root boot UUID>.<Supervisor spawn generation>` and
every successor Root lease `native-cpu.root.<actual UUID>.<spawn generation>`.
The initial Root keeps `native-cpu-root-installation`. The oracle binds these
names to the actual Root peer and complete registered writer; local writer
generation is not substituted for Supervisor spawn, and older ID spellings
are rejected. Lease duration, signature, scope, payload and uniqueness checks
remain enforced. This naming check alone supplies no cross-boot evidence.

Each recovered writer additionally uses the original checkpoint activation
preparation. Its finite lease payload commits to the complete candidate (only
the output digest field is zeroed for hashing), whole predecessor token,
retained physical-cut digest, and actual Root and publisher lifetimes. The
earlier cut/spawn/local-generation payload is rejected, with no fallback.
The complete original candidate and its independently saved Root observation
must agree. See `NATIVE_OWNER_ACTIVATION.md` for the exact commitment and the
additional physical checks shared with single-crash and prior-boot recovery.

The initial real ReadUsage sample is no earlier than the initial kernel grant
issue cut. Its checked sum with 330 seconds is therefore a conservative bound
beyond both initial finite grants. Only a subsequent Applied receipt on the
same boot and stable CPU object can cross that bound. Elapsed host wall time,
fresh PIDs or current cap values do not prove it. New namespaces and owner
generations preserve the original revision and CPU accounting history.

## Exact kernel and original owner lineage

The initial four image commits and bootstrap v3 remain mandatory. Each actual
factory generation needs the exact kernel activation marker and either two
fresh images or one history-only image of the same reviewed ELF. Complete
128-byte HOS2LRES and HOS2LWDR records must match the actual 240-byte bootstrap,
Process IDs, boot, local/history namespaces and predecessor generation.
Reserved bytes, handle layouts and unchanged limits are checked explicitly.

The original policy retirement receipt is distinct from a D terminal. A
Restored watchdog receipt retains its actual stable ID, revision, time and
consumed CPU. History-only flags do not falsely retire that policy. The later
fresh pair must preserve the previously observed watchdog receipt at the
actual final owner cut. Some(0) and an absent evaluation time remain distinct.

Each actual original Supervisor snapshot must retain Starting, Spawned,
Running and Healthy for its registered spawn generation. A normal handoff
requires the actual writer release receipt, independently observed Current
and physical material, then original Draining/StopRequested/Stopped and
successful exit-zero/reap. Local writer generation, owner epoch and Supervisor
generation are separate fields and must follow the original transitions.

The history scenario's dead initial Recovery slot is a specific original
failure. The original `record_fault` uses generation zero when no runtime
remains; the producer's snapshot filter excludes that event. Its independently
returned TickReport `driver_fault`, actual failed lifecycle registry and reap
observations are checked. No invented nonzero DriverFault event is required.

Every recovery consumes the previous exact Current and physical material and
preserves both original complete FinalUse frontiers before a new effect.
History-only inspection/reconciliation has null usage and zero CPU handles.
It may query and retire the old D; it cannot become a CPU issuer or reinterpret
the independent watchdog result as the old D terminal.

## Independent retained state check

A continuity transcript alone returns `passed=false`. After the actual QEMU
run ends with its original success exit, the runner opens that same retained
raw ext2 disk using read-only `debugfs` and independently checks:

- Root-owned, non-writable ancestors and the mode-0700 observation directory.
- The exact set of original observation files and their original persistent
  `.json.lock` inodes; no missing record, unexpected temporary file or extra
  launch is accepted.
- Each observation's actual Root UID, mode 0600, one link, regular-file inode
  and original 16-KiB bound. Original lock inodes are distinct, Root 0600,
  single-link and empty.
- The original `RootStoredObservation` envelope, full UTF-8 payload bytes,
  hash-derived filename, boot/generation and complete launch/retirement arrays.

The physical path is
`/state/hepta-native/protected-source/authority/native-launch-observations`.
These bounded observations and lock metadata are extracted; private
issuer keys are never read. Manager and
Recovery can report the same immutable launch observation; it is verified
once as the same actual inode/file, not counted as another launch.

The runner also reads every original activation preparation from the actual
checkpoint directory and hashes the exact predecessor material. Its complete
candidate commitment and physical file must match the actual owner chain.
All expected witness records and locks are required; an unsigned extra
candidate, missing file or replaced material fails. Output is retained in
`checkpoint-activation-witnesses/` alongside the launch-observation evidence.

Every debugfs command records its exact argv, selected binary hash, exit,
elapsed time, stdout/stderr bytes and hashes. Missing paths can produce exit
zero in debugfs, so its output and normal version banner are checked as well.
The whole state disk and actual tool hashes must be unchanged across read-only
extraction. Raw outputs, extracted file bytes and `root-launch-observations/`
`result.json` remain in each scenario's retained directory.

Only after transcript, launch files and activation witnesses pass does the runner set the corresponding finite
`grant_renewal_verified` or `history_only_recovery_verified` field. Unbounded
persistent control, cross-boot Unknown preservation, host power loss, complete
G2 and production readiness remain false. Normal repeated handoffs do not
become a claim of repeated crash recovery.

## Running and reviewing

Use `run_native_owner.py` with the existing explicit source review plus SHA,
both complete sources, actual same-source owner build receipt plus SHA,
owner ELF, complete retained product-kernel pipeline plus SHA and frozen QEMU
identity. Select either additional name with `--scenario`; all six are selected
when no scenario is given. `--debugfs` selects the read-only extractor, whose
actual binary is hashed and retained. `--timeout` remains within 1..120 for
the earlier cases and history-only; only the named renewal campaign uses 600.

The source review belongs to compiled sources. The runner's own clean source
identity is retained independently. A new source pair does not inherit an old
owner build, kernel boot or scenario qualification. Existing ordinary kernel,
ABI and F1 runtime/store gates retain their independent source-bound scope.

Run the host gate from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tests/workloads/hepta_cpu_control -p 'test_native_owner*.py' -v
```

The gate includes the original 19 transcript and 10 runner tests, the earlier
9 copyout tests, 10 additional continuity parser tests and 4 real private ext2
extraction tests. Complete synthetic records in
`native_owner_continuity_test_records.py` are inert test input. They neither
launch an owner nor produce native qualification evidence. The ext2 tests use
private synthetic disks; `-w` appears only while constructing/mutating those
test inputs. The production extractor never opens a disk for writing.
