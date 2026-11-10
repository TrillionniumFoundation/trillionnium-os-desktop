# Release08 device update and acceptance sources

The installation source was reviewed and frozen before the actual single update.
Its source hash is `b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470`.
Twelve offline tests passed, including real local child-process cleanup on a
command timeout. The actual update then completed as `INSTALLED_VERIFIED`; the
installed bytes, current Main epoch, UID, CE/DE directory identities, first-install
time and permissions were read back. The source README and manifest retain their
pre-execution status as historical preparation records.

The acceptance source hash is
`93cf4567c19f6033dce0b120d068a7120a2b27952a4a1d0d4cfdd8b988ebfbcb`.
Thirteen offline controls passed. They validate the script's scoped task ownership,
new-media matching, parsing and failure handling; they do not prove a working
camera. The real `accept-01` run observed the Camera connection-error dialog before
any shutter action and normally closed its single owned Camera task. That failure
is preserved in the parent evidence directory. Do not rerun an old attempt or
weaken its qualification predicates to turn it into a pass.

Both tools use the existing action lock and the pinned R16 held-root/namespace
transport. The installed helper and permanent camera-provider owner are unchanged.
Unknown install or input outcomes are not automatically retried. The acceptance
tool permits one semantic shutter action, reads only its uniquely new image, and
requires actual decode, persistence and separately verified normal close/reopen.
Pictures and raw UI captures stay private on the device and are not included here.

Camera remains unqualified for production. Refer to the current release status and
actual receipts before planning another attempt.
