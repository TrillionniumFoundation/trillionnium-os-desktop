# GNU make environment controls: preserved host evidence

The original 30-file, 251,823-byte package is retained byte for byte in
`raw-originals.tar.gz` under `original/`, including its original checksum list.
The independent review found no blocking issue in committed local source
`6b68e196fc95c7da7159e464dd5b2f2a50d136f3`; `source-publication.json` binds
its exact tree and six blobs to publisher-verified remote commit
`ff040c6d5afbc4e26a249022093b8090181f6176`. Original records retain their
earlier tested-base identity and were not rewritten.

Real GNU make 4.3 plus the actual upstream Makefile/minimal overlay skipped
`cargo osdk build` under inherited `MAKEFLAGS=n` and `t`, while both wrapper
statuses were zero. Empty MAKEFLAGS executed the recipe. The first `i` case
was a successful control; the later saved red log proves ignored exit42.
Six red methods produced nine assertion failures including subtests, with
zero harness errors. All failure JSON and raw text are retained.

The repaired runner passed 30 methods and supervisor 9 methods under each
Python mode: 78 method executions, 39 distinct methods. Exact-context patch
reconstruction and all eight before/after Git source bindings were checked
without running the tests. The four original logs report OK. Their separate
subprocess argv/exit receipts were not saved; original README replay argv
and root-attested exit0 metadata are distinguished in `independent-review.json`.
Later final-source revalidation is separate and does not replace these logs.

To replay, extract the raw tar into fresh scratch, enter `original/` and use
the commands in `README.md`, which run only disposable host fixtures. The
historical controller paths identify the actual original context; adapting
them to another checkout must preserve the recorded before/after source.
`members.json` and `RAW_MEMBER_SHA256SUMS` cover every regular tar member;
all members were read back and byte-compared to their frozen inputs.

This package claims no Rust kernel compile, QEMU launch, boot or whole-phase
green verdict. The separate merged-main Clippy run has two A02 test lints
(exit101), reported in the publisher context. No target/cache or pycache is
included. Packaging ran no tests, Cargo, rustc or VM and changed no source.
