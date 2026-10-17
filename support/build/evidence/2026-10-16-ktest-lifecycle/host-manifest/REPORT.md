# Host manifest custody proof

The original shell cleanup could validate its owned inode, then unlink a foreign replacement at the same public pathname. The deterministic baseline host probe actually returned **0** while deleting foreign inode **1581465**, after checking owned inode **1581458**. The original observation is unchanged (`baseline-observation.json`, SHA256 `06b46f59a93527824280a36113880a11056cc9844b687a27b8d6690b6874c79e`). It used a disposable fixture and never touched the production manifest, Cargo target or QEMU.

The original controller/heredoc and stdout were recovered verbatim from the original tool call after the event. `baseline-supplement.json` explicitly labels them **post-hoc transcription, not a rerun**. The actual exec receipt records chunk `88f1da`, exit 0. Four baseline support sources were recovered from recorded HEAD `84040737`; they are byte-identical at the requested `8fcf645`. Only `kernel.sh` had an individual execution-time source digest. The other recovered fixture files are not represented as independent runtime snapshots.

The fix is published at **`a770f31a868d805524065c65a2bcfcbcf10ede2e`**, tree **`af2e1bc4d215ac4dc6eadd0cecc147e1673b1c1e`**, identical to local reviewed commit `b386cba658de0185164405148c2664723452db1a`. All four frozen file hashes match the published Git blobs. The exact patch, source-ready record, publication receipt and source snapshots are retained.

The worker pins its original regular inode with FD 8 before publication and retains workspace lock FD 9 through cleanup. Cleanup atomically captures the public entry in fresh private 0700 custody. Only a captured matching owned inode is deleted. Foreign regular files, symlinks and directories are restored with `renameat2(RENAME_NOREPLACE)`, or retained with an explicit recovery path and failure status. This does not keep the public pathname continuously occupied. An otherwise successful run fails on cleanup retention; an original nonzero build exit remains unchanged.

The real host runner/supervisor suites passed **31/31 under `-I`** and **31/31 under `-I -O`**, with actual session exits 0. Tests include replacement immediately before atomic capture, a new public entry after capture, foreign symlink/directory preservation, restoration conflicts, unavailable NOREPLACE, exceptions after capture, publication interruption, lock/descendant lifecycle and shell exit propagation (make 0 becomes failure; make 37 remains 37). Full original verbose logs and exact commands are in the raw archive and `source-ready.json`. These are host fixtures, not kernel or VM pass counts.

## Reproduce the fixed host tests

Extract `raw.tar.gz` into a new scratch directory. Its `final/source/` includes the four changed sources plus three unchanged supporting fixture files, so the host suite can be replayed without a Cargo target or kernel source build:

```sh
tar -xzf raw.tar.gz -C /absolute/new/replay-directory
python3 -I -m unittest discover \
  -s /absolute/new/replay-directory/final/source/support/build/tests \
  -p 'test_kernel*.py' -v
python3 -I -O -m unittest discover \
  -s /absolute/new/replay-directory/final/source/support/build/tests \
  -p 'test_kernel*.py' -v
```

Alternatively check out publication `a770f31` and use the original commands in `source-ready.json`. For the old failure, use the recorded baseline commit and preserved controller. **Do not run the original hardcoded controller against the fixed live repository or its frozen report path.** Copy it to new scratch and explicitly change only its `repo` and `scratch` paths to a detached baseline worktree and new output directory. The original controller was not replayed during archival.

## Excluded ktest manifest hypothesis

The generated intermediate `kernel/OSDK.toml` was suspected of affecting `aster-core` tests. Actual read-only Cargo metadata from both `ostd/` and `kernel/core/` returned workspace root `kernel/asterinas`; neither current directory had an OSDK manifest. The loader source checks current directory, then workspace root, rather than every ancestor. That generated intermediate manifest is therefore not selected by this route, and no speculative guard was added.

The attempted `strace` probe failed at `PTRACE_TRACEME` with **Operation not permitted** before the intended traced OSDK command ran. Its stderr, empty trace/stdout and post-hoc command description are retained. The precise strace exit number was not separately saved and is not invented. The selection conclusion relies on actual Cargo metadata plus loader source, not a claimed runtime open trace. The full metadata outputs and original exclusion report are in `raw.tar.gz#excluded-hypothesis/`.

## Integrity and scope

`raw.tar.gz` has **30 members**: original observations, labelled controller/source recovery, complete host-test output, fixed sources/patch, publication receipt and excluded-hypothesis material. `members.json` records every original size/SHA and the compressed archive hash. The tar was finalized atomically, reopened and every member checked. Key JSON copies remain readable and byte-identical. No production target, actual production manifest, tool binary or kernel implementation is included. No test or VM was run during archival. `SHA256SUMS` covers all final files except itself.
