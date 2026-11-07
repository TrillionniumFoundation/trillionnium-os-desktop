# Gallery rotation02: fixture cleanup after a pre-input selector failure

The original run remains FAILED with ONE_EXPLICIT_OWNED_ALBUM_BUTTON. It seeded
two owned images but stopped before Open or rotation. The observed button was
uppercase; the old selector expected title case. This does not prove an App
failure or a rotation pass.

The owned task1000 closed normally. Cleanup removed both images and their exact
empty directories, two matching directory index rows, the temporary helper and
its CE/DE directories, and the staged APK. Original media, Gallery identity and
permissions, Main and the task baseline were preserved; all pending fields were
empty. These are separate fixture-cleanup proofs, with no Gallery UI-delete
credit and no cross-row SQL atomicity claim.

Rotation03 is a later separate run outside this retained02 result. Its outcome
is never inferred from02 cleanup.
