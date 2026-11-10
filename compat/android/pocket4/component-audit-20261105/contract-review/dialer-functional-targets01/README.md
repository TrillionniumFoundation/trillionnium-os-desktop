# Dialer: actual job and voicemail component targets

The fixed installed APK was read at 2026-11-05 18:20:51–53 UTC with the original
Main guard before and after. Two legacy manifest names remain absent from its
DEX. The same APK also declares and defines the separate implementation names
that its actual code uses: CallLogConfigImpl$PollingJob and the Dialer voicemail
settings VoicemailChangePinActivity.

The selected installed code shows the user-unlocked application branch building
JobInfo400 for the existing polling service. VoicemailSettingsFragment builds
an explicit Intent for the existing PIN activity and enables that preference
only when voicemail is enabled and activated. These are code-path observations;
the scheduled service and voicemail action were not run by this capture.

The original13 missing references across12 classes remain the historical audit
result. This review does not turn the two extra legacy declarations into proven
business failures. Their lack of exact DEX/XML literals also does not establish
absence of every external or reflective caller. The manifest remains unchanged.

MANIFEST.json preserves the source owner's frozen11-file selection. The root
review independently checks every file against the351,709-byte actual result,
and all four component rows against the original complete APK component audit.
No App launch, call, SIM, account, user-data write or readiness gate occurred.
