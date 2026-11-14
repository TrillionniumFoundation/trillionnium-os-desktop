# Exact source-transfer batches

A large, already sorted NUL `rsync --files-from` list can spend substantial receiver CPU before it writes source files. This helper partitions that list into at most 8,192 exact entries per call, preserving the complete original byte sequence when the batches are concatenated. It never widens selected files into recursive parent-directory copies.

The caller retains the original allowlist hash and records each batch hash. Use explicit `--from0 --files-from`, `--relative --no-recursive`, and normal file/symlink copying. Preserve checksums during resumed copies and complete a checksum dry run across every batch. Generated operational Git configuration and directory metadata are separate from the selected source files. No credentials, account configuration, guest images, or private signing inputs are selected by this helper.

This module neither starts a transfer nor cancels jobs. The production continuation retires the original owned receiver and sender, preserves its cancelled terminal, observes the partial target, and only then creates a separately identified continuation. A successful partition test does not qualify copied source or a build.

Run the eight portable controls from this directory:

```sh
python3 -B -m unittest discover -s tests -v
```

The controls cover complete disjoint partitions, exact source bytes, spaces and Unicode, shell-looking filenames, duplicates, ordering, path escapes, directory expansion, and strict integer limits. They require only Python 3.9 or later.
