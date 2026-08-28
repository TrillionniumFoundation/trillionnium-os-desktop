# Evidence and claim boundary

| Evidence | It proves | It does not prove |
| --- | --- | --- |
| schema parses | document syntax | runtime enforcement |
| Rust unit test | pure contract/state behavior | Servo, display, transport, image |
| browserd self-check | deterministic D0 transition sequence | browser or network operation |
| host Servo fixture | pinned host embedding behavior | Debian image or hardware readiness |
| QEMU boot | image and virtual-device behavior | fixed-hardware qualification |
| hardware test | one selected hardware lane | public release or general compatibility |
| signed release evidence | exact released artifacts and gates | future versions or other hardware |

Every stage promotion updates `CURRENT_STATE.md`, `docs/MANIFEST.json`, and
`manifests/repository-state.json`. Missing evidence remains an explicit
non-claim.
