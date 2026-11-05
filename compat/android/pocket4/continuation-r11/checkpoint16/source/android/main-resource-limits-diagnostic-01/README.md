# Fixed Main resource diagnostic

This is a new read-only collection after Amazon search-entry02 stopped in its
initial `main_guard` with `Main resource limits differ`. It does not rerun that
job, call `main_guard`, qualify Main, modify a limit, start a child, enter Android,
create device evidence files, or change a frozen activation.

The exact reference is `readonly_r3_coordinator.py`, 16900 bytes, SHA256
`e2769eeeae2d620456a67959dfaff3b07545f2352cd9a60692450451004c39fd`.
Its `read()` default is 1 MiB; that is the activation input bound here, **not a
claim about the actual activation file size**, which has not been read locally.
The exact activation SHA256 is
`7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615`.
Only its five `limits` basenames supply expected values and file names. No
synthetic local parser input is used as an actual Main expectation.

Every component of the two full fixed paths is opened without following
symlinks. The service directory must be device 30, inode 26651611. Five original
file descriptors remain held while two new named reads compare to each anchor;
both complete paths and all five names are checked again before completion.
Each pseudo-file read is bounded at 4 KiB without equating its data length to
`st_size`, which may be zero. Reads must finish within an 8-second admission
deadline; final FD cleanup and output serialization are included in the separate
30-second outer process timeout. Python bytecode writes are disabled with `-B`.

The original activation bytes are preserved in a base64 field, with exact byte
count and SHA256. Complete output is bounded at 2 MiB and is never truncated into
a success record. This original activation payload is evidence for this private
diagnostic; it is not added to a source publication by this package.

`collection_complete` means the specified inputs and both sequential snapshots
were collected with the stated identity and input checks. A limit mismatch or
change between complete snapshots is reported separately and is not an execution
qualification. `runtime_authorized` is always false. The two observations are
not an atomic multi-file snapshot and do not identify who changed a value.

Local checks exercised only owned temporary files, symlink rejection, byte
bounds, and synthetic basename parsing plus default PLAN. The collector has not
run on Pocket4 or on a local Main cgroup. Root owns exact request review and any
single device submission.
