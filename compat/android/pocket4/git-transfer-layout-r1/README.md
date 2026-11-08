# Required Git directory preservation after a file-only source transfer

A detached Git checkout may retain all references in packed form and have no loose ref files. A file-only allowlist therefore omits the empty `.git/refs` directory. Git rejects that otherwise intact checkout as not a repository.

`ensure_refs_container` creates only the missing required empty directory inside an already owned, real `.git` directory with existing HEAD, object storage, and configuration. It does not initialize a repository or write any reference, commit, object, configuration, index, hook, or working-tree file. Existing directories are preserved; symlinks and wrong owners are rejected. The caller must first bind a completed source-only transfer and verify the corresponding original directory.

Run `python3 -B -m unittest -v test_git_transfer_layout.py`. The eight controls include an actual detached-head Git fixture that reproduces the original failure, then restores normal Git recognition with unchanged commit and all regular-file hashes. Negative cases cover symlink, file, owner, type, and missing-object boundaries.

This helper establishes only source checkout layout. It does not grant build, payload, runtime, or production readiness.
