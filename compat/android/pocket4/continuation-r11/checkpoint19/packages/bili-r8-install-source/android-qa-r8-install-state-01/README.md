# R8 helper installation and no-automation state

This request binds the complete actual R8 build/stage receipts, actual APK and signer, and two actual secrets nonces. It retains the prior R7 install implementation with only identity, actual binding and prior-UID exclusion changes. The four R3/R4 references are byte-identical.

The complete R8 build passed all 22 Java production-gate controls, 32 actual protocol controls, and 13 joined build commands. This generator independently checked the original receipt bytes and all qualification fields in V8; it did not execute Python qualified_build locally. The actual installer must call the pinned R8 adapter qualified_build, including both control reports and their source/command bindings, before any Android install.

One package-absence check covers uninstalled records and all users. Installation keeps -R no replacement and a fresh owned staging directory. The helper UID remains unknown until actual package-list output; two exact installed-byte observations surround one no-UiAutomation state command. Main guards, held leases, the original global action lock, nine-command plan, worker/parent limits and precise staging cleanup remain unchanged. Failed or unknown installation is not replayed.

This state operation does not enter the R8 inspect idle gate. No app launch, UI, playback, text, permission or settings action is authorized by this request. A future UI flow needs complete actual install records and a fresh owned task. Whole-app readiness remains unqualified.
