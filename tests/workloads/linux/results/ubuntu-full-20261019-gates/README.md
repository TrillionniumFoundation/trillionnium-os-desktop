# Ubuntu full32 runner gate evidence

This archive records host gate tests and the original BusyBox shell syntax
check. It contains no Linux32 or guest32 workload qualification.

- `normal-01` and `optimized-01` retain the earlier 23-test draft results. Their
  historical receipts did not record source hashes and are not promoted to the
  final implementation's results.
- `normal-02` and `optimized-02` each ran all 27 maintained tests with actual
  exit 0. Their receipts bind the runner, capture helper and test source bytes
  in source commit `6f2c6af8b17eb0c71c424831bb060caa7e1fad8b`.
- `busybox-syntax-01` binds the original A01 image, its actual BusyBox ELF, the
  generated guest script and its generator. The ELF ran through a Linux memfd
  with explicit argv[0] `busybox`; `--list` and `sh -n` exited 0. The generated
  workload commands were not executed.
- Unit fixtures are explicitly synthetic controls for rejecting incorrect
  facts, incomplete denominators, malformed byte frames or altered receipts.
  Their fabricated frames are not application or kernel evidence.

The earlier exploratory BusyBox call used a descriptor pathname as argv[0]
and returned `3: applet not found`. Its raw output was not retained as a file.
The corrected argv[0] metadata/syntax run above is retained. This error was not
an actual full-profile workload failure.

All original retained bytes are listed in `MANIFEST.json`. Real full-profile
qualification requires the frozen build bundle, the original Linux 32-case
reference, and an ordinary-kernel run of the same image in project CI.
