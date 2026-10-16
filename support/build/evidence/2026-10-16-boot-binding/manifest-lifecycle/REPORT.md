# Temporary OSDK manifest publication and interruption

The isolated regression demonstrates a specific publication window. The old
runner publishes its temporary file with a real hard link, then records that
file's device/inode identity. A fixture sends SIGTERM to the runner immediately
after the actual `ln` succeeds. The EXIT trap runs before identity registration:
the temporary path is removed but the owned `OSDK.toml` remains. The new
regression fails against the old runner, as retained in `before.log` (exit 1).

The fix records the temporary inode before publishing the hard link. The same
real-signal regression and all existing runner checks pass: **10 passed** in
`after.log` (exit 0). Existing foreign files, a file created during preparation,
and replacement inodes remain protected. These are temporary fake-project host
tests; they compile no kernel and run no QEMU guest.

## Exact measured source

The logs and `*-command.json` files were copied byte-for-byte from the original
scratch run. The measured before runner has SHA256
`9176bf7bdb80aae53f75723b5c372771167d7e1c36e3e7a0786bf1472a42430f`,
matching `support/build/kernel.sh` at
`3d561fed0f106a3c7af0330e1d722d31b8ce7a9a`. The measured fixed runner has
SHA256 `3a5a210c365a565c2d1e57def0413e5a7c33e972130e2d0879b68ed678c60740`.
The committed fix is in `2c658089bb90aa5b254ddf336ef3dc1333e755c9`; that final
commit also adds the later `--live-artifacts` checker argument. Reversing just
that argument change reconstructs the actual measured fixed bytes. The
measurement is not relabelled as a byte-identical run of the final commit.

`reconstruct.py` obtains production files from those Git commits rather than
archiving another implementation. It checks the exact runner and test hashes
with explicit exceptions, including under Python optimization. It supplies the
pre-change boot checker only as a fixture dependency; the injected SIGTERM case
never reaches the checker. The original full-suite after run did not separately
record that helper's hash, so its exact helper bytes are not newly asserted.

```sh
python3 -I reconstruct.py --repository /path/to/trillionnium-os-desktop --output /path/to/new-scratch
```

Run the two commands printed by the script: the focused before case must exit
1, and the after suite must exit 0 with 10 tests. `reconstruction-check.json`
records the additional reconstruction and host-only rerun; it does not replace
the original before/after measurements.

## Separate real-build observation

The later real `next3-kernel` build exited 0 but a matching-content profile was
found afterward with a later inode creation/change time than its modification
time. A subsequent boot attempt refused that existing manifest. The file was
preserved by the parent while holding the build lock. Its hash and observation
metadata are in `real-build-observations.json`; the original file and complete
raw logs are retained separately by the parent.

This is an **unexplained replacement observation**. The prior real build has no
inode lifecycle trace proving who created or replaced that inode. Concurrent
`git fetch` and `git reset --soft` metadata alignment were reported, but those
operations normally do not modify the working tree and are not established as
the cause. The deterministic SIGTERM model above does not establish the cause
of this real residual file either.

The subsequent `bash -x` boot completed with raw QEMU 33 and live-artifact
checker success. Its exit trace records the owned identity `27:1572904`, the
same identity at cleanup, and an actual `rm` of the owned manifest. The file was
absent at this read-only observation. OSDK's manifest-loading path reads
`OSDK.toml`; the examined bundle writer writes `bundle.toml`. This review found
no production build path that explains the earlier inode replacement, and does
not claim all possible external replacement mechanisms have been excluded.
