# Physical camera producer

The normal vendor build compiles this platform Java library against the selected
AOSP virtual_camera_service_aidl-java. The fourth Android image contains the
DEX JAR, its fixed init service, the provider built from that same AOSP source,
and an init override for the existing virtual_camera service. The original
system provider bytes remain part of the immutable base; normal init parses
system_ext after system and replaces the one service definition.

The init-owned producer runs as guest root with an empty capability set and the
dedicated droidloom_camera_producer domain. It waits for actual boot completion,
uses the original platform CREATE_VIRTUAL_DEVICE permission check, and runs ART
without JIT. It has no shell, user path, arbitrary command, test image or fallback
capture input. The broker socket context is verified through the platform
SELinux peer-context API. Host root is not assumed to appear as guest UID 0.

## Capture protocol

The only endpoint is /dev/socket/droidloom-frontend/camera. A request is
DLCAM01 followed by a zero byte, then one big-endian u32: 1 for availability,
2 for a stream. The 32-byte reply contains that magic followed by status, width,
height, FPS, maximum JPEG size and a reserved field. Available means exactly
0, 640, 480, 30, 4194304, 0; unavailable means 1 and five zero fields.
Availability probes end after the reply and do not start physical capture.
A stream is requested only after the actual virtual camera supplies a valid
Surface.

Every real frame has a big-endian length, sequence and CLOCK_MONOTONIC timestamp
(4 + 8 + 8 bytes), then JPEG bytes. Size, format, exact dimensions, advancing
sequence/timestamp and age of at most one second are checked before software
Canvas presentation. EOF, stale data or capture failure closes the connection
and retires the token. Capture-request callbacks never replay the last frame.

## Original token and device retirement

virtual-camera-token-death.patch is applied only in the normal Vendor source
projection. It adds NDK token death observation with the documented
onUnlinked cookie lifetime, an exact registration identity and a held original
camera object. Creation that loses a concurrent death/unregister race retires
only its own object. Provider removal rejects a stale object even when its name
has been reused. The name remains reserved until the original NOT_PRESENT
callback has completed; no service or provider mutex spans a Binder callback.

Retirement permanently prevents the original ICameraDevice from opening another
session and closes its existing session with a device error independently of
feature flags. Ordinary closeSession remains reusable. Both explicit unregister
and token death use the same retirement path.

The original provider test target includes bounded concurrent name-reuse and
stale-object tests. Normal builds compile virtual_camera_tests; these binaries
are not installed as production services. The standalone CameraProtocolTest
exercises wire rejection without requiring Android.

## Evidence boundary

The cohort contract binds the SHA-256 of all four fixed files. The normal image
publisher verifies source RC bytes, ELF/DEX structure, labels, metadata, exact
inventory and ext4 readback. The host consumes only a typed four-file declaration
from the same admitted cohort; a historical cohort without it has no camera
endpoint.

Host mechanism tests and successful compilation do not establish camera hardware
or Android Binder runtime qualification. Actual producer death, session close,
single provider identity, physical availability, and original frame consumption
must still be observed in the enforcing shared-kernel runtime.
