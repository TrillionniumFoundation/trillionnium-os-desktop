# Pocket4 continuation — checkpoint 07

This checkpoint preserves the next native repair, pressure-owner integration and acceptance-tool corrections. Work continues. **Whole-App production readiness remains 0/45, and production activation remains NO-GO.** Main is still on its existing R16 activation; no Main engine or supervisor deployment is part of this checkpoint.

## Native descriptor ownership

The original V2 factory rejected an unexpected kernel `SCM_PIDFD` message but did not own and close its delivered descriptor. A real Pocket4 listener test demonstrated that `SO_PASSPIDFD` propagates from the listening socket to the accepted socket: the request failed with `EPROTO`, its two ordinary rights were closed, and one PID descriptor leaked. The original failure is retained.

Revision 2 adopts the known `SOL_SOCKET/SCM_PIDFD` capability before rejecting the message. It applies the same ownership rule to the client reply receiver. Ordinary credentials are not interpreted as descriptors. The private reply-receive refactoring preserves the surrounding factory authentication and provenance checks.

Candidate05 changes two production files and one reference manifest in the complete 948-file candidate, including 925 engine files. All six earlier signal-fix outputs remain identical. Its manifest is `4e2f7f9ea09c6977afbe8d97c040fd2f1344772429f78fe0f16edc913dadc7ba`.

The actual Pocket4 small gate completed eight commands successfully: Android provenance compilation with the feature both disabled and enabled, eight checks through the actual host ARM64 syscall adapter, 34 actual ancillary-message controls, and the actual listener-inheritance regression. The source and compiler inputs were unchanged. Its full report SHA256 is `e53c3e9e5846d36f971bae6140c394b837fa54525c0e2df4ac153c9ef5540803`.

The earlier host fixture build is retained as compile evidence for its original inputs. Build02 has now compiled the repaired candidate with the same client and worker-audit sources: all 21 commands passed, the actual 291-input dependency closure matched its preflight, all inputs remained unchanged, and the final host worker binary audit passed. Its build receipt is `fd4a8d8a3b4b037bdf9ee72992cda69544ce8c94ea44e46696d028c0ad041142`.

The first actual isolated host runtime then failed. The owned factory reached READY, but its first `same-wire_snapshot` client (UID/GID 61171) returned stage 1 / `EPERM` before sending a request or starting the raw metadata owner. The exact failing namespace/credential substep is not yet observed. The original result is `b91c34d11b134965d6b4fd69df4eca5d2dbcc07637c3d372f934934bcf849faf`. The client, factory, control owner and namespace init were reaped. The fixture also records `normal-owner` as unexpectedly alive at cleanup; its forced-cleanup flag is true while its actual return code is zero. That cleanup observation is preserved. Outer cleanup completed, Main's checked state was unchanged, and recorded own/Main memory-event deltas were zero. Swap usage/peak was not sampled. The run does not qualify factory authority/lifecycle, Android factory trust or outer ARM64 behavior.

## Complete engine build

Candidate05 now has an independent Git working tree and an exact copy of the 449-file normal builder source. The actual preparation receipt contains all 925 engine input hashes and has SHA256 `bb6e0d92c8b0df36ca8ccf1f25dd4286491c09999fa9225ff9f15955e00cd9d0` (115,794 bytes). Two earlier MCP dispatch timeouts remain recorded; the same stable key was reconciled, and the observed preparation job completed successfully.

The new complete build request uses the normal builder, one build job, CPUQuota 200%, 11 GiB RAM, 1 GiB owned swap and the original two-core placement. Its first actual attempt failed the 15 GiB MemAvailable admission threshold before starting the inner builder. The original failure is retained. Before/after Main checks passed, with unchanged identities and limits and zero deltas for the recorded memory events. A subsequent fixed-file diagnostic observed 14.088741 GiB MemAvailable and 3.832428 GiB SwapFree; it did not stop processes, drop caches or alter limits. A separate Go5 / 10 GiB build profile is under local review, preserving the same 4 GiB admission headroom and requiring a new actual admission observation. It has not run at this snapshot. The candidate's default feature remains disabled. A successful preparation is not a successful engine build, a passing 3,793-test host suite, an Android run or an ART build.

## Supervisor and startup prefix

Producer05 repairs the explicit pressure-relay launch path to use `/usr/bin/ip` and `/usr/bin/unshare`. The installed Python compatibility wrapper forks without preserving the capability descriptors and cannot maintain the required direct-parent contract. The explicit path also omits the native unshare program's unsupported `--forward-signals` option; the existing legacy `None` path is unchanged.

The actual matching host build passed 122 supervisor tests, 23 relay tests, seven ordinary IPC controls, the worker-context controls and the compiled entry ABI. All 31 input pins and the complete source inventory remained unchanged. The actual build receipt SHA256 is `1623811c108a7cac8af3460d828c063ed9e7064519d2d4e41d70bce4ab25e64c`.

A separate host prefix stand-in was compiled on Pocket4 and passed 40 Python ordinary/pure controls and six native ordinary controls. The exact probe SHA256 is `79b30f9fa4a1e7635ae4786a50372b3fcaa84ad619269476e40a1badd65c0e82`; its preparation receipt SHA256 is `1e70d9df93309ff5be991f0a20e4b5b4493e57a0b64fcc3881075e652a5ae712`. The normal runtime plan requires the full `ip netns exec` prefix, exact inherited descriptor identities, externally captured unit invocation/cgroup identities and exact unit/netns retirement. This preparation does not execute namespaces, the actual Rust Owner, Android init, the init-barrier constructor or pressure enrollment.

The normal plan's first read-only preflight failed with `Main original process changed: system_server` after its exact input/probe checks passed. No runtime, namespace or Android action started. Its original receipt is `0b29fe07377483c57406145b838e38a3854a64276a09e16ac9aa4bd5fddb35ad`. A local source comparison found different handling of empty NUL-padded argv entries between the prefix actor and the original framework binding; actual capture bytes are still required before attributing this failure to that difference. The original plan is not rewritten or treated as a passing runtime.

## Bilibili acceptance-tool failure and correction work

The new recorder's first actual read-only admission failed before a held Main binding or Android command intent was created. Initialization and admission were separate processes and both were joined. No Bilibili launch, close, playback or audio action occurred. Main's checked identity/configuration/resource boundaries remained unchanged. The original flow and its failure are retained.

A subsequent fixed-path metadata diagnostic established the offending input: the original held-namespace helper ELF has size **4,366,312 bytes**, exceeding this one call site's **4,194,304-byte** bound. All three inspected helper inputs were regular files with one link. The helper source and qualification JSON fit their bounds, and the qualification JSON matched its original hash. A separate bounded, identity-bound full ELF hash check then read exactly 4,366,312 bytes and matched the original qualified helper SHA256 `21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689`; its observed metadata was stable. This establishes the artifact-specific bound error.

Recorder revision 3 now requires that exact artifact length and its original full hash. Generic source and evidence bounds are unchanged. Nine real owned-file boundary controls passed, including the retained old-bound failure, size ±1, same-size wrong content, hardlink and symlink cases. Root verified all 44 frozen payloads, all 45 archive files, the single changed production file and the fresh read-only request. Its source manifest is `4ff896b75c4c7751a28eee34ab512583c3a26eb43f5e28598a776d40ee496906`. R3 admission has not run at this snapshot; it does not qualify Bilibili business behavior.

The recorder sources also retain the earlier fixes for primary-error preservation during release, held namespace transport, once-only action claims and the original task cleanup behavior. Local controls and source reviews are distinct from device admission. The installed action-runner APK/source binding, continued playback, controls and attributed audible output remain open.

## Other preserved source corrections

- The host factory controller retains child output, observed byte counts, hashes and its first error when bounded-output failure is followed by cleanup. A real 65,537-byte child-output regression verifies the corrected behavior.
- Its Main resource check always uses the fixed `droidloomd.service` cgroup. The membership predicate now permits Main init at that root itself as well as a descendant; the actual a04 evidence places init at the root. Similar-prefix siblings remain outside the admitted hierarchy.
- The original local ancillary, namespace-view and interpreter-ownership failures are retained with their narrow fixes. The supervisor publication set explicitly records which exact source bytes are included and which remain references; it is not represented as a complete standalone checkout.

## Qualification still required

The R21 `NOFILE=0` raw/ordinary TMPFS `EMFILE` cases remain red. Complete repaired-engine build and host/Android regression, real factory authority/lifecycle, paired ART integration, actual finite-domain init/broker/native-LMKD enrollment, abandoned-generation recovery and all commercial business-flow gates remain open. SMC and SVC remain distinct instructions; no repair translates an SMC into an SVC.

Main's engine remains `c8b9bae4466d4f66525fdef6bcec140b29612581efeb6ceb621f96e17277d26d`, its presenter remains `47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24`, and its framework epoch remains `48cb65c93ff81edbf160455af6506f5c703f0958363f15de4a80ece57c37e93f`. The prior 1,858 committed payloads are preserved. This checkpoint adds UTF-8 sources, bounded evidence and review records; it does not commit APKs, ELFs, archives, build caches or private commercial runtime journals.
