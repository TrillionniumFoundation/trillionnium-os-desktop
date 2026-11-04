# Proposed Bilibili continuation — not executed

The retained r10 flow is
`/home/alex/work/pocket4-app-production-20261104-r10/business-flows/bili-01`.
Its public receipt is the scoped search/visual-playback/owned-close evidence
from commit `0894ebe5c269af391ea4ac4940c6e82c34e69eac`. The public search was
“微积分” and the opened public video was “很水的微积分000：课程介绍”. Three
inspected frames showed progress. The historic task IDs and UI observations
must never be reused for new actions.

That evidence did not establish audio listened, seeking/pause, in-app Back,
reopen, or cold start. A PLAYING state with position zero is not a second
progress observation and is not evidence that output was audible. The older
failed/unknown observations remain retained as such.

## Read-only admission first

After independent source review and an allocated parent-owned device window:

1. Verify the create-only source copy against the externally supplied
   `source-manifest.json` hash. Verify the fixed Main epoch, helper source,
   helper binary and actual qualification receipts. Use a new flow directory;
   do not adopt or rewrite the old r10 flow.
2. Run the existing `init` with package `tv.danmaku.bili`, component
   `tv.danmaku.bili/tv.danmaku.bili.MainActivityV2`, and the exact activation
   path/hash in `EXTERNAL_INPUTS.json`. This writes only new private flow
   evidence and performs the original read-only guards.
3. Run one new step using `admission`. It verifies real held Main namespace
   authorities, actual fixed zygote/init classpath file equivalence, Bili UID
   10117/data-directory identities and action-runner UID 10125, then makes
   exactly one held read-only package/UID query. There is no instrumentation
   or UI action in this operation.
4. Independently bind the installed `local.pocket4.actions.v2` APK to its
   retained source/build evidence. Its UID is in the activation, but this
   artifact has not seen a matching APK hash/source receipt. Do not silently
   call that missing provenance qualified. Retain the exact installed path,
   held-root file identity and streamed hash without copying the APK into the
   public source tree.

The exact new directory, source pin and device resource protocol must be
specified in the reviewed execution request. No new remote directory, nonce,
service, flow or source copy has been created for this proposal.

## One new app flow after admission

Reserve the Main UI window with the parent so it does not overlap other app
work. Every action uses the original recorder's global action lock and the
unchanged 48cb/Main/process/config/limits fences. If an existing Bili task is
present, preserve it and stop before launching.

Use one native launch and the new actual task receipt. Inspect the newly
observed page. Any navigation must be decided from that observation using
the original supported selectors; do not replay stale search/click evidence.
If the previous public video is available, verify continuation with new
spaced observations of actual changing frames/progress. If navigation is
necessary, keep it within public content and record that it was a fresh
navigation. A successful visible launch alone closes only a launch/reopen
gate. It does not close continued playback or audio.

Finish with one explicit original cleanup step for only the newly created
task, then verify its absence and preservation of other task IDs. Unknown
launch/action/removal results retain their claims and are not automatically
retried. Account state, app data, permissions and engine files are preserved.

Do not force-stop or kill the app to manufacture a cold start. Classify a
natural process start from actual UID/process birth evidence if it occurs;
otherwise this is a warm reopen and cold-start remains untested.

## Audio: exact attribution remains an open gate

The retained source patch `0015-droidloom-pcm-output.patch` describes host
stream acceptance, not physical speaker output. Its policy describes a
shared primary mix output, and its bridge packet does not carry an app UID.
The patch/policy have not yet been matched to the installed active audio
components for this app observation.

A useful next audio observation is bounded read-only metadata tying the
actual Bili UID/process generation to its AudioFlinger client/track/session,
the actual output thread/HAL, an authenticated host stream, the corresponding
PipeWire object/ports/links, and the actual sink/route. The exact installed
AudioFlinger and PipeWire schema must be used: a client column can be a PID;
a client-supplied application name/PID is not authenticated app identity; a
Pulse proxy peer PID can name the proxy rather than the Android app.

No audio capture is included in this revision. Do not record a microphone,
default sink monitor, or a shared mixed stream that could contain private
audio. Do not change routes, volume, permissions or the audio graph to make
the test pass. If the existing shared output cannot provide an independently
attributed app-only observation, report that precise limitation.

Tracks running, advancing frame counters, a bridge ACK, an established link,
or a visible video do not prove that the user heard sound. Keep the audible
output gate open until actual app-attributed output has been observed within
the privacy boundary. Nothing in the 42 local tool controls changes that.
