# One kernel boot identity for HOS2 and procfs

This stage exposes the existing HOS2 boot identity at
`/proc/sys/kernel/random/boot_id`.
It does not create another owner, authorization issuer, or restart ledger.
The identifier is public correlation data, not a capability.

## Technical contract

`device/misc/hepta_control.rs` owns one `Once<[u8; 16]>` per kernel boot.
After the kernel random generator is initialized, the first kernel thread
fills these bytes once and fixes the UUID version 4 and RFC variant bits.
HOS2 responses use these exact bytes.
Procfs prints them in byte order as lowercase `8-4-4-4-12` hexadecimal groups,
followed by one newline (37 bytes).
There is no UUID integer endian conversion and no second random draw in procfs.

The original G1-d boot page keeps its existing layout: bytes 96 through 111
contain this same 16-byte identity.
Its magic, version, length, roles and all other offsets are unchanged.
`TrustedControlSlots::new_pair` obtains the same fallible identity before
constructing its original owner and capability-space objects.
The identifier does not assign a process a trusted role.

The random generator and the quality of its actual seed are published in
one `Once` value.
This prevents repeated initialization calls from pairing one generator with
a different call's seed-quality result.
The x86 path trusts successful hardware random reads; non-x86 device-tree
seeds require a trusted bootloader that supplies fresh entropy.
If hardware reads are absent or fail and only the timestamp fallback remains,
the general generator retains its existing fallback behavior but protected
boot identity access returns `EOPNOTSUPP`.
Procfs reads, opening `/dev/hepta-control`, trusted boot page creation and
trusted control-slot construction all propagate that refusal.
The quality cannot be upgraded later without replacing the generator;
there is no reseeding or recovery transition in this stage.

The procfs inode initially has mode 0444.
It implements only reading, including short reads, offsets and EOF.
Even root changing the generic procfs metadata to writable does not add a
write implementation: writes still fail with `EPERM` and cannot alter the ID.
The usual procfs metadata operations are not presented as immutable metadata.
The value is global to this kernel instance and stays the same across open,
fork, exec and unprivileged reads.

## Development and verification

The real guest entry point is documented in
[the boot-id probe README](../../tests/kernel/boot-id/README.md).
The wrapper uses the original safety runner, ordinary kernel build, static C
probe, source snapshots, retained artifact hashes and per-run nonce markers.
It has no host disk, network or device passthrough and never executes the probe
on the host.

The cross-boot profile performs two fresh QEMU boots with CPU `max`, then a
third with `max,-rdrand` using the same kernel ELF.
It requires different canonical IDs in the two positive boots, procfs/HOS2
byte equality within each boot, and no exported ID plus `EOPNOTSUPP` from
procfs and HOS2 open in the negative boot.
All three source snapshots and ELF hashes must agree.
A missing or malformed child result remains a failed report with the original
child log retained; a provisional `passed: false` during compilation is not a
completed guest failure.

This verifies the ordinary product's procfs and HOS2 paths.
The G1-d call sites are reviewed to propagate the same error; this probe does
not enable that feature or claim a completed trusted-role guest qualification.
Two fresh boots establish the tested lifecycle behavior, not a statistical
proof of entropy or uniqueness.
VM snapshots or clones that replay already initialized RNG and boot-ID state
are outside this contract; their identities can repeat.
A malicious hypervisor, faulty hardware RNG or replayed device-tree seed is
also outside this entropy trust assumption.

## Evidence checkpoint

The first cross-boot run in `work/goal-logs/boot-id-cross-boot-first` passed all
three profiles with ELF SHA256
`b1a3eff5d7d232899a421869469d7406a7394f52f5f1475d77063f055075c40c`.
Independent review then combined RNG/seed-quality publication and extended
read-only and unprivileged-reader checks; that earlier run is retained as an
intermediate checkpoint, not the final artifact qualification.

The initial native attempt had two import errors and did not pass compilation.
The corrected intermediate native run in
`work/goal-logs/integration-bootid-native-second` passed 314 tests.
The final native run in `work/goal-logs/integration-bootid-native-final`
again passed all 314 tests after the RNG publication change.
The final cross-boot run in `work/goal-logs/boot-id-cross-boot-final`
passed 16 actual guest assertions in each positive boot and two in the
missing-RDRAND control, with unchanged source snapshots and artifact hashes.
All three used kernel ELF SHA256
`574d10d6b879a95a2e1ddf548c07f09169899f2cdca59a931ad43ddfb946b87a`.
The positive IDs were `0b351667-5f77-47c8-8b40-2dabb8af1bb0` and
`a5299b7f-5cad-49e2-92b4-a5bb1f45b94d`; the negative boot exported neither.
The source was tested as development working bytes before its delivery commit;
this is not a claim that an already committed clean product was rebuilt.
Earlier failed or intermediate logs are not overwritten.
This stage does not claim full Root/Agentd convergence, Android readiness,
production qualification or a globally secure system RNG fallback.
