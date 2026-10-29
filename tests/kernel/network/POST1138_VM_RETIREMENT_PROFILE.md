# Post-1138 VM retirement source profile

`post-1138-vm-retirement-v1` binds the x86 VM-space retirement repair to the
CPUNODE, CPU route lifetime and first-spawn placement composition. Its 90 unique
literal role/path/SHA256 entries inherit the previous 84 paths, update the three
changed task/thread owners and the CPU marker guard runner, and add five VM
implementation/test/contract paths plus the unchanged historical CPUNODE wrapper.

`run_unix_stream_retirement_guest.py` verifies the historical engine SHA256
before executing those exact bytes in a private module. It adds only this fixed
positive source profile. The ordinary build, expected head/tree admission, ELF
and artifact checks, nonce, Unix parser, timeouts, assertions and mutation
oracles retain their original implementations. No operator hash or manifest can
extend the profile. Historical mutations cannot select this positive profile.

The CPU runner now normalizes archive paths without removing the private
marker's leading dot. Two synthetic CPIO tests verify refusal of four existing
marker aliases and normal admission that preserves the original entries and
adds exactly one private marker with its nonce. They use in-memory synthetic
data and execute no guest. The C probe and its expected cases are unchanged.

The previous 84-role `post-1138-cpunode-v1`, 76-role `post-1138-kernel-v1` and
historical engine remain byte-for-byte unchanged. The old 84-role positive host
tests read complete real Git blobs from source
`cab93cfb2a7c5e3dddd67e63895cb5a86ff2eb33`, tree
`3f9e99c02d509576f6af1c960b2cedbca7ddc049`, in the fixed checksummed archive
`controls/post1138-cpunode-v1-source.json.gz`. The fixture verifies regular
Git modes, exact roles/paths, SHA256 and Git blob identities in memory. No
fixture paths are extracted. The reproducible exporter checks those Git objects:

```sh
python3 -I -B tests/kernel/network/export_cpunode_source_fixture.py --check
```

Run source-admission tests in normal and optimized Python modes:

```sh
python3 -I -B -m unittest discover -s tests/kernel/network -p 'test_*.py'
python3 -I -B -O -m unittest discover -s tests/kernel/network -p 'test_*.py'
```

Freeze a clean composition and build its own OSDK from that checkout. Execute
both Unix selections in separate new external directories:

```sh
python3 -I -B tests/kernel/network/run_unix_stream_retirement_guest.py \
  --expected-source-head FULL_HEAD --expected-source-tree FULL_TREE \
  --target-dir /independent/kernel/target --output /new/evidence/unix-all \
  --source-profile post-1138-vm-retirement-v1 --variant positive --selection all
```

Repeat with `--selection shutdown_race` and a new output directory. Both ordinary
ELFs must match the separately verified QueryAbi product. Record all tracked
source modes, Git blobs and SHA256 values before and after the matrix. Also run
the full OSTD/Core tests, unchanged page-memory 177 assertions, CPU ABI on one,
two and four CPUs, quota/lifecycle/affinity/isolation lanes and all seven strict
negative controls on that exact final composition. Preserve any older failed
receipts under their original source identities.

The VM retirement contract is in
`support/kernel-safety/VMSPACE_RETIREMENT.md`. Only the x86 user-to-kernel
retirement behavior changes; other architectures require separate evidence.
Source admission and component results do not establish the final matrix,
production Hepta authority, mobile hardware or physical DMA isolation.
