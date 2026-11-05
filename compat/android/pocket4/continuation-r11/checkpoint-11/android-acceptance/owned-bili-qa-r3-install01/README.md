# R3 owned QA install plus state, candidate 01

This request installs only `org.droidloom.qa.bili.r3` from the actual r3
build01 receipt and runs one fresh state request. The state operation never
connects UiAutomation. There is no Bilibili launch, inspection, click, text,
audio or settings action. UID remains unknown until actual package readback;
commercial UID 10117, legacy helper UID 10125 and old r1/r2 UIDs 10164/10165
are rejected. No old package is replaced, uninstalled or invoked.

## Actual inputs and narrow changes

INPUTS.json binds the full actual r3 build and stage receipts, the new signed
24720-byte APK and its new signer. The exact source consumer independently
validated all nine source files, seven unchanged tool inputs, all eleven
joined rc0 commands, API31 compile/target33 manifest and successful stage.
The actual stage used one CPU, 512 MiB, no swap and TasksMax128; peak was
195723264 bytes and all memory.events values were zero. The Java compiler's
nonempty stderr is preserved in its receipt, not relabelled as empty.

The install/stage functions are inherited from the successful r2 install.
The only install operational function change is adding UID10165 to rejection.
Constants bind the independent r3 package/source/build/signature and fresh
nonces/root/flow/step. session_binding.py directly constructs the actual r3
adapter's R4 Session after checking its exact source, recorder and package;
it overrides no Session method.

The R4 transport, all 44 private recorder copy pins, Main epoch, action lock,
joined independent CLI ownership, evidence/error handling and precise cleanup
are unchanged. The actual r3 parser consumes the new bounded gzip wire,
requires one finish(-1) and binds the request/UID/source/APK. The supplied
state has no accessibility tree and cannot perform an action.

## Admission and retention

Before installation the new package must be absent across all actual users,
including uninstalled retained records. Installation uses the original exact
`cmd package install -R -t --user 0 --pkg` command. `-R` prohibits replacement;
unsupported options remain failures with no fallback. No permission grant,
automatic retry or automatic uninstall is introduced. The Main guard does
not import an old package-inventory count.

The signed APK is staged under a new held-root directory. Cleanup removes
only that held file/directory identity. After the single installation command,
the actual UID and unique all-user package mapping are checked. Installed
base APK bytes are streamed through the held root and checked before and
after state. A successful installation retains this owned package for a
separate reviewed UI flow; unknown outcomes require original-job reconciliation.

The generated request is the only candidate for this fresh root/key. Its
publication is not execution. Root reviews and dispatches it. No private
commercial tree, journal, APK bytes or signing material is published here.
Only accessibility mode booleans and enabled-service digest/count appear in
state, without other service names. Full Bilibili readiness remains open.
