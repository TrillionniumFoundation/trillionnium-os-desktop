# Selected CP3A stock DEX and task-API review

## Result

The selected official CP3A.260905.010 / 16176746 image itself now supplies static binary evidence for the Java wrapper sequence and the task/Intent observations below. No CP2A source was substituted as proof of this implementation.

The evidence supports keeping official ART unchanged while evaluating a separately reviewed launch/grant design. It does **not** establish an approved wrapper launch, a new post-specialization grant, an Android boot, an app business-flow pass, or an owned-task cleanup authority. All runtime, production, selected-QPR1 ABI, and new-grant qualification fields remain false.

## Origin and extraction

The image was opened once O_RDONLY / O_NOFOLLOW, fully SHA256-checked, and passed to read-only debugfs through that same held FD. The image's device/inode/size/mtime/ctime were unchanged afterward. It remained root-owned mode 0400. All extracted copies and derived files are inside the unique audit root; no mounted image, Android process, Android command, user data, owner source, canonical CURRENT, or shared build lock was used.

| Original object | Bytes | SHA256 |
|---|---:|---|
| Selected raw system.img | 2,294,853,632 | dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4 |
| /system/framework/framework.jar | 49,754,098 | bc8a175a95dcb50b5ae62a03a0ec2ba0fdea34169f83b2aab3c8bf2790707587 |
| /system/framework/services.jar | 25,716,529 | bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86 |
| /system/framework/boot-framework.vdex | 735,560 | bd2f35b4a6d315b17e407c9f48e8034c2968e5a155e0a90e5fa7e115c3b9fcd4 |
| /system/build.prop | 5,609 | 810fc1db84f7ae7574598a02496610e0b808c9f495fed61fe4b180662f549fac |

The copied build.prop binds CP3A.260905.010 / 16176746 and the user/release-keys fingerprint. The audit does not infer a ro.debuggable value from that fingerprint.

All nine DEX entries (six framework and three services) were extracted with ZIP CRC verification. Every DEX is version 039. A later independent input pass rehashed all four container/metadata copies plus all nine DEX files, matching the original extraction pins. The complete DEX hashes are in method-excerpts/INDEX.json and extraction.stdout.

Only the existing Java 25/baksmali installation was used, with 256 MiB Java heap, one active processor, one disassembly job, a private temp/user directory, and no host application environment inherited into the disassembly command. H jobs were CPU-limited to one core and bounded at 512 MiB or less. No compiler or new analysis dependency was installed. The Java launcher and seven classpath JAR identities, exact argv, exits, and empty Java stderr/stdout are retained.

Fourteen actual classes were disassembled. An initially requested ActivityTaskManagerShellCommand class was absent; this was not counted as success for that class. The actual shell implementation, com.android.server.am.ActivityManagerShellCommand, was then found and disassembled from services/classes.dex. The package includes 55 complete relevant method records in 56 chunks. The only split method is Intent.parseCommandArgs; concatenating its two numbered chunks reproduces the full method hash.

## What the selected wrapper bytecode establishes

1. ZygoteConnection.processCommand applies the UID and explicit invoke-with security policies before applying the debugger and wrap-property settings.
2. An existing nonempty mInvokeWith takes the Java forkAndSpecialize path instead of the forkSimpleApps fast path. The selected method calls nativeForkAndSpecialize, then postForkCommon, and returns its PID result.
3. Only the child PID-zero branch calls handleChildProc. A nonempty wrapper reaches WrapperInit.execApplication; the ordinary and child-zygote paths are separate branches.
4. execApplication constructs the stock app_process64/32 command with WrapperInit, preserves capabilities, and calls execShell. The actual execShell method executes /system/bin/sh with -c using Os.execv.
5. The new WrapperInit.main writes its PID to the inherited pipe when present, closes that pipe, preloads the framework, calls wrapperInit, and runs the returned entry. wrapperInit calls nativePreApplicationInit and then RuntimeInit.applicationInit.

This is the Java-to-native boundary order actually encoded in CP3A. It is not a disassembly or qualification of nativeForkAndSpecialize internals, shell execution, stock ART initialization timing, or real final credentials.

The explicit-wrapper guard rejects a non-root peer lacking the relevant runtime debug bits; its tested mask in the DEX is 0x02000001. Root acceptance by that guard is not authority to substitute a root peer or bypass the normal launch origin. getWrapProperty reads wrap.<appName> and returns a nonempty value; this particular method has no ro.debuggable check. Property-service and SELinux permission to set such a property were not established or modified.

### Credential implication from the actual wrapper

preserveCapabilities copies permitted capabilities into inheritable where needed, then attempts to raise each inheritable bit into the ambient set. Its capget, capset, and per-bit prctl failure paths log and return/continue. Therefore a pre-wrapper credential observation cannot be treated as an unchanged post-exec credential state.

Any alternative to the existing required private grant still needs a reviewed trusted producer and one-use receipt bound to the actual owned process/exec generation, final UID/GID/groups, every capability set, namespaces, executable identity, PIDFD, and nonce. The receipt must be validated at the engine's real required initialization point. An in-memory grant does not survive exec. The existing grant, raw-metadata ownership, worker retirement, credential/thread isolation, and deterministic cleanup requirements remain in force. No source change is justified merely by the existence of these Java methods.

## What the selected task/Intent bytecode establishes

| Static fact | Consequence for the proposed observation |
|---|---|
| Intent.parseCommandArgs maps the exact option **-i** to setIdentifier. Its packed-switch path and complete method are retained. | A candidate correlation protocol can use a reviewed identifier input; no command was executed here. |
| setIdentifier/getIdentifier operate on mIdentifier; the copy constructor and cloneFilter retain it; filterEquals compares it. Parcel write/read also retain it. | The identifier has an actual field and wire representation in this cohort. It is not a guessed extra or JSON-only assertion. |
| Intent.toShortString emits that value with the exact text prefix **id=**. | A future text parser must use the observed format and full structural context, rather than an assumed ident= spelling. |
| Task.setIntent retains the incoming/copy Intent on its recorded branches. Task.fillTaskInfo copies baseIntent, taskId, effectiveUid, display/user data, a WindowContainerToken, and launchCookies. | Typed task information has potential correlation and opaque-identity material. Reachability, permissions, sanitization, and launch-to-observation binding still need validation. |
| ActivityTaskManagerService.getTasks performs its permission/profile checks and obtains running tasks under the framework global lock. | A typed query is an observed read path; this audit does not prove the eventual caller can observe the required task fields. |
| cmd activity stack list calls getAllRootTaskInfos and prints RootTaskInfo.toString. That complete override omits baseIntent and identifier. | The existing stack-list delta cannot establish a launch nonce relationship. |
| WaitResult's complete parcel write/read carries result, timeout, component, totalTime, and launchState, with no task ID. The shell start-activity result prints the corresponding status/component/timing fields. | A successful wait/launch acknowledgement does not supply a created-task ownership receipt. |
| removeTask(int) checks REMOVE_TASKS and uses the integer ID; there is no expected identifier argument. | An earlier observational match plus this later call is not an atomic conditional cleanup contract. |

The new Settings route must remain blocked until it has a real framework-bound launch/observation/cleanup authority. A host flock, before/after task-name difference, launch status string, or self-reported JSON cannot provide that authority. A one-use identifier plus typed task/opaque token observations is a possible design input, not a qualified implementation. Task reuse, concurrent activity, atomic cleanup, permissions, lost replies, and end-to-end Android retirement remain pending. There was no launch, removal, instrumentation, account operation, or UI interaction in this audit.

## Evidence, replay and retirement

- method-excerpts/INDEX.json pins each full disassembled class and every method's exact contiguous lines, signature, bytes, SHA256, and chunks. Its line numbers refer to the **disassembled SMALI file**, not an authenticated source repository.
- additional-native-methods/INDEX.json covers execShell, getWrapProperty, nativePreApplicationInit's native declaration, and preserveCapabilities.
- evidence/disassembly-r1.json and shell-disassembly-r1.json retain the exact existing-tool argv and complete class directory identities. The remote scope manifest pins all remaining audit inputs and derived objects, excluding itself.
- Full raw H stdout/terminal receipts are included. The first unprivileged stat attempt failed EACCES before returning inventory; its failure remains preserved. The following expressly authorized read-only sudo extraction succeeded. No permission was changed to avoid that failure.
- The independent retirement receipt found all seven completed input-job units not-found/inactive/dead, MainPID 0, and no cgroup path. A process scan found zero Java/baksmali processes referencing this audit scope, with zero unreadable cmdline entries. The observer itself then reached succeeded / exit 0 / complete / durable.
- To reproduce, use the same pinned image, read-only extraction of the listed objects, the pinned installed disassembler and recorded class filters, then compare the class/method and input hashes. No floating source or alternate image may replace these inputs.

The remote root is pocket4:/home/alex/work/pocket4-native-qpr1-dex-audit-20261109-2840-r1. It is retained for independent review; its inputs can be retired after publication/recovery and live-reference checks. Parent/owner assets are outside that scope.

This package supplements qpr1-coherence with actual selected-image method evidence. It does not resolve the separate public-CI source-binding denial, authenticate a complete CP3A manifest, qualify a Native601/official-ART pair, or resolve the original import PTY launch_unknown state. That operation remains unreplayed.
