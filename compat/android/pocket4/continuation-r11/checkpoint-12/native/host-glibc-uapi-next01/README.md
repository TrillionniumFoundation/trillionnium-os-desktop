# Host glibc UAPI compatibility, candidate07 input

Candidate06's actual full build02 reached the host static `libberberis_kernel_api_arm64` compilation and failed at the unconditional `linux/memfd.h` include in `proc_maps_provenance.cc`. This was a compiler error, not an OOM-kill result. The exact original compiler argv and effective source receipts are retained here. Candidate06, its failed outputs, the compiled450 updater, and all Android/Main state remain unchanged.

The fixed sixteen-path observation additionally established that the selected sysroot lacks `linux/nsfs.h`. Five absent fixed paths were recorded: the other three are asm/bits paths that may instead exist in a multiarch directory. Their absence does not prove that the compiler has no corresponding macros. The actual compiler macro query in the prepared TU gate resolves that distinction.

## Source delta

Four private implementation files include one new `proc_maps_linux_compat.h`. The unconditional memfd and nsfs includes move into `__has_include` guards in that header. All function bodies, raw worker/trampoline assembly, namespace and credential checks, seals validation, error propagation, syscall argument widths, feature flags and warning settings remain unchanged.

The compatibility header fills only missing Linux UAPI constants. It checks all resulting values at compile time against the observed Bionic UAPI definitions. The four syscall numbers are supplied only for the already-qualified x86-64 LP64 host ABI, excluding x32; existing declarations are retained and asserted. This makes older libc declarations usable with the same Linux syscalls. It does not fake kernel availability, suppress runtime ENOSYS, weaken fd identity, change ownership, or bypass user-namespace/capability verification.

The fd-owner and path implementations receive the same private definitions because they conditionally use pidfd syscall declarations. The gate records the original actual macro set. A header declaration's absence must not silently select a different host-only ENOSYS path while Android uses the supported syscall. No syscall is invoked by this compile gate.

The source count changes explicitly from 925 to 926 engine files and 948 to 949 overlay files. Four existing files change; all other existing files stay byte-identical. No manifest or compiled binary is presented as already qualified.

## Matched complete-TU gate

The prepared request uses the exact failed Clang entry, target, glibc sysroot, C++ standard, macros, optimization and warning options. It redirects only source/object/dependency outputs into its own new root and adds a leading include directory containing the byte-pinned private source headers. It does not edit the live AOSP tree, original source, or old build output.

It first records the actual compiler-resolved UAPI macros and reproduces the unmodified provenance source's missing-memfd-header failure. It then compiles the five complete candidate translation units: provenance, raw metadata owner, pthread fd owner, path and factory wire. A dependency-only pass using the same flags records all actual inputs before each compilation; the actual emitted dependency set and bytes must match afterward. ELF REL output identity, frozen sources, compiler identity, all observed UAPI files/absences, owned child cleanup and invocation resource events are checked again.

This gate is a complete TU compilation, not a linked engine, Android ABI/runtime test, worker-call-graph audit or 3793-suite result. The factory-wire source is unchanged and is included to cover its shared protocol/header use. The old negative result is preserved even if all candidate compiles succeed. No warnings are disabled or converted to success.

## Following steps

After an actual gate PASS, compose candidate07 in a new root from the complete verified candidate06 manifest, apply exactly the five-file delta, and emit a new 949/926 source manifest. The full build must bind that actual composition receipt and the unchanged compiled450 builder/runtime450 Go5 data. It must preserve normal source projection, lock/recovery, fresh output, both existing engine and host-test targets, resource admission and Main pre/post observations. The already-failed candidate06 receipts remain separate.

Actual artifact qualification still requires the complete 3793-registration host suite and four owned Android signal cases against newly bound output hashes. Default feature flag remains zero. Paired ART lifecycle and production enablement are separate open gates.
