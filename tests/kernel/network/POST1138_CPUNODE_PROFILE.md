# Post-1138 CPUNODE source profile

`post-1138-cpunode-v1` binds the composition of the post-1138 CPU route lifetime
and first-spawn placement changes with the Linux vDSO CPUNODE descriptor. The
GDT, descriptor tests, pinned CPU identity probe and runner, ABI documentation
and A06 workflow have explicit source roles. The complete profile has 84 unique
literal role/path/SHA256 entries.

`run_unix_stream_cpunode_guest.py` checks the historical engine SHA256 before
executing those exact bytes in a private module. It adds only the fixed profile
name and source selection. The original ordinary build, head/tree admission,
ELF and artifact checks, nonce, initramfs handling, Unix parser, timeouts and
oracle remain unchanged. Historical mutation variants cannot select this
positive profile. Operator-provided hashes or manifests cannot extend it.

Freeze a clean composition and build its OSDK from that checkout. Run both Unix
selections into separate external directories:

```sh
python3 -I -B tests/kernel/network/run_unix_stream_cpunode_guest.py \
  --expected-source-head FULL_HEAD --expected-source-tree FULL_TREE \
  --target-dir /independent/kernel/target --output /new/evidence/unix-all \
  --source-profile post-1138-cpunode-v1 --variant positive --selection all
```

Repeat with `--selection shutdown_race` and a new output directory. Both ordinary
ELFs must match the separately verified QueryAbi product. Record every tracked
source mode, Git blob and SHA before and after the matrix. Source admission
alone provides no guest qualification.

Run `python3 -I -B -m unittest discover -s tests/kernel/network -p 'test_*.py'`
and the same command with `-O`. The new tests check current bytes, missing and
drifting owners, duplicate roles and paths, private engine isolation, old-profile
refusal and explicit coverage of all component paths. The old 76-role
`post-1138-kernel-v1` remains unchanged. Its positive host tests read complete
real Git blobs from source `62301dd25cc9fd57baa04dc9e86cda2bef205fa1`, tree
`08cde53405dea5e98b26d4a2f99cb38c674527d8`, in a checksummed in-memory fixture.
The exporter checks all 76 files against those Git objects:

```sh
python3 -I -B tests/kernel/network/export_post1138_source_fixture.py --check
```

The fixture is decoded in memory and verifies regular modes, unique paths and
roles, SHA256 and Git blob identities. No fixture paths are extracted. The live
CPUNODE composition must pass the new profile and fail all older strict profiles.

The GDT change also requires real OSTD/Core tests and the same static CPU identity
probe on one, two and four CPUs. Verify libc, direct syscall, raw vDSO and LSL
results together with affinity migration, TLS, unchanged segment selectors and
monotonic time. Run the existing quota, handoff, affinity, isolation and seven
strict kernel negative controls on the exact final composition. These checks
retain their existing assertions and limits. NUMA, rseq, native Hepta authority,
mobile hardware and physical DMA isolation need their own qualification.
