# Frozen fd/a39 window execution and separate Root package refusal

## Exact sources and retained originals

Desktop is `fd8d56c52b971c2d5d0e6430f296803b43ef60a3`, tree
`347fbb7e9931006c749b5bef0e1550c54bc08f27`; original Hepta is
`a39a0871d9601ffccb5e0d95d8f39d54b3a63360`, tree
`e03f9b3eca364222029298496d3e4f1f5e1bf5de`. This is the explicit prepared
preedit profile, SDK tree `6b422b3120f5f9b5c7ada579b55f647d51bd7fcf`.
The declared build source selects the committed prepared lock as `ui/Cargo.lock`;
it records that exact override and unchanged Rust sources. It is not the default
SDK or clipboard profile.

[complete-raw-receipts.tar.gz](complete-raw-receipts.tar.gz) preserves all ten
original files, including the complete 2,048,376-byte UI build receipt with
all source/dependency metadata. The archive is 87,261 bytes, SHA-256
`2b83a3b28b520e5691bc385b2ea108e8c1425285b790ab0a1fce205825069372`.
[original-archive-index.json](original-archive-index.json) records every member's
length and digest. The archive was read in two version-bound chunks; both chunk
hashes, the full archive and all ten extracted member hashes were independently
checked. Selected smaller original JSON files are also readable beside this page.
The complete UI receipt remains in the archive with original SHA-256
`49c1937fb340f1b806888ebf86d3a2bc6a2283839f8efa1ce5050b802352a4a1`.

## Actual UI and private-window outcome

The UI builder completed all 16 recorded commands with exit 0 on Rust 1.96.0,
including the original prepared UI tests, native-text/observer/support/host
contracts, SDK focus/text selections, strict Clippy, all native binaries,
resources and host packaging. This is a command count, not a count of test cases.
The packaged Shell is 131,321,264 bytes, SHA-256
`342c2bbb53a2f258186462fe4959a36bf7803d78ecf9615f968686c4fd293c4c`.
The build receipt, Shell and NATIVE-ASSETS digest agree with the
[window provenance](window/provenance.json). `window/inventory.json` describes
the host test environment; it is a different file from NATIVE-ASSETS.json.

The original private-window job `1a1a2e1fd54-96a-7544` completed successfully,
exit 0, with complete output and no stderr. The independently read
[authoritative process status](window/process-status.json) is retained.
An additional attempt to fetch its 114-byte stdout timed out at the transport;
that does not change the observed process result or replace the complete
[on-disk window receipt](window/receipt.json).

| Original acceptance part | Actual result | Scope |
| --- | --- | --- |
| AT-SPI | [7/7](window/atspi-receipt.json) | Actual original window identity, role/focus, clipboard and UTF-8 selection, undo/redo, disabled unauthenticated Send, stale-room object isolation |
| Atomic EditableText | [5/5](window/editable-text-receipt.json) | Supported standard methods, original edit/undo history, bounded ranges and stale-room refusal |
| Real IBus | [5/5](window/ibus-receipt.json) | libpinyin preedit, Chinese commit from ASCII XTEST keys, transaction undo/redo, focus loss/return and draft/checkpoint isolation |

The original Xvfb 15-second, window 30-second and input-stage 90-second limits
were retained. This execution took 55.305 seconds overall; the second Xvfb
readiness observation succeeded. All three acceptance subprocesses returned
0; all five long-lived owned children have cleanup exits and private state was
removed. The earlier [15-second startup failure](../xvfb-fd-diagnostic/result.json)
remains preserved. [Host pressure](window/host-before.json) was observed after
the owned compiler stopped; neither the observation nor one later success proves
that competing build I/O was the unique earlier cause.

The original receipt still reports physical keyboard, Wayland IME, full
EditableText, Orca, visual font/candidate positioning, system installation,
original Agentd and authenticated Send as unqualified. This private X11/IBus
result is not an installed Root/Notes effect or a phone/Calculator window result.
No original human-visual flag was promoted by the receipt review.

## Separate Root dev-small refusal

The original Root builder used the same fd/a39 sources, default features,
committed locks and `dev-small` profile. The Hepta binaries compiled in
1,979.416 seconds, the Desktop Root companion in 1,742.232 seconds, and both
recorded strip commands returned 0. Packaging then failed at the existing
128 MiB per-file bound. The actual stripped Agentd was a regular single-link
file of 341,288,592 bytes; [the retained stat transcript](root/file-stat-and-receipts.log)
distinguishes size from a link/type failure. The Root companion was
87,571,952 bytes with SHA-256
`303e15091c40dcefe6f36496f61fdf40f4854138782b79163799e89f61f890e9`.

[build-receipt.json](root/build-receipt.json) remains `status: failed`,
`production_ready: false` and `source_clean_after: false`; final source checks,
complete packaging and the builder's later original host tests were not reached.
The [outer runner](root/runner-result.json) recorded `blocked`; its wrapper
process returned 0 after catching that failure, as explicitly distinguished in
[terminal-observation.json](root/terminal-observation.json). Process exit alone
must not be credited as a successful package.

A separately recorded build may use the already-defined `product-linux`
optimization profile while retaining the original 128 MiB / 512 MiB archive
bounds, features and locks. Its result must come from its own actual execution;
this archive grants it no build, installation or production qualification.
