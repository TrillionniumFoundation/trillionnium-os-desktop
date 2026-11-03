# Actual ordinary boot and bounded SMP2 CPU quota evidence

The original product kernel was rebuilt from clean Desktop commit
`e26207a5b731ef7b43b0f5661c1f7b757409c857`, tree
`1c805f128161d99acc01a0295850b23d61fd1682`, with the pinned
`nightly-2026-07-21` compiler and committed dependency locks. The resulting
8,606,608-byte ELF SHA256 is
`c90cb30bd5e6d081193ea26d71bbaf585719dc9eefa9eab081a2ba06b1056965`.
No previously built kernel substituted for this build.

`execution.json` retains the actual commands, source identities, tools, host
resource envelope and every result. `operator-terminal.json` is the observed
durable process terminal for `1a16ee51095-1b6abb-4e44`: exit 0, complete output,
no timeout, cancellation, missing log bytes or truncation. `capsule.json`
binds the original 29 retained artifact byte streams. The separate copy
transport archive SHA256 was
`5683f1d3e6dcf675ed3599660a96ed8f79eecdc7a1827265bf13736493bf623d`.

## Observed results

- The actual ordinary product boot passed. The subsequently booted QueryAbi
  probe passed all 18 exact marker counts, including inherited-fd denial,
  non-root open denial, process/thread session identity, exec rotation and
  the four explicitly disabled control operations. This profile does not
  claim production control authority or native resource effects.
- The same new ELF ran nine distinct two-vCPU TCG guests: three runs each of
  leaf CPU quota, parent quota and real-time-thread quota. All guests exited
  with raw QEMU code 33, complete markers and no observed panic.
- The configured quota was **10,000 / 100,000 microseconds (10% of one CPU)**.
  The historical probe label `one-percent-configured` is misleading; the
  retained original raw label is preserved, and the actual configured values
  and CPU-nanoseconds/wall-nanoseconds are authoritative. Measured quota
  utilization ranged from 10.020% to 10.384%; the frozen limit was 12%.
- Unlimited controls used more than 145% of one CPU in every run. The
  `iterations` field is zero in this probe; it is not a throughput result.
  The final real-time capped sample lasted about 10.11 seconds rather than
  the nominal five-second sampling request, which remains visible in raw
  counters and is not a latency guarantee.

The diagnostic uses a host envelope of two CPUs and 8 GiB. These are bounded
CPU quota results under the recorded QEMU profile. General SMP safety, IRQ
latency, physical hardware drivers, resource-exhaustion recovery reachability,
native G2 original-owner durability and AI-policy benefit remain separate
gates. The original receipt therefore retains `smp_qualified=false`,
`hepta_hos2_qualified=false` and `production_ready=false`.
