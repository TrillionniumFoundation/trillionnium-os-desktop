# Gallery camera entry: installed-code contract

Two bounded, read-only captures inspected the exact installed Gallery APK
`347c376f…`, DEX `0c5e61f6…`. The camera Activity calls IntentHelper, launches
`com.android.camera2/com.android.camera.CameraLauncher`, and finishes. The
independent installed Camera manifest audit confirms that target is a declared
alias to CameraActivity. No forwarding UI or hardware test was performed here.

Gallery's manifest still names MediaSaveService, while that class is absent from
the APK DEX set. Only CameraActivity and DisableCameraReceiver are defined under
com.android.camera. Neither dot nor slash MediaSaveService literals occur in the
DEX bytes. Those bounded observations do not prove reflection or external
class-loader absence, service reachability, or a reproduced runtime failure.

The declaration remains an unresolved packaging/contract finding. No feature was
removed, no empty substitute was added, and no unrelated capture implementation
was imported. Current Gallery video evidence and Camera hardware prerequisites
are tracked separately. The original component audit and its counts are retained.
