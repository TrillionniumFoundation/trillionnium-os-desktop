# D0R-02 signed Debian snapshot evidence

**Date:** 2026-08-29  
**Requested snapshot:** `20260828T000000Z`  
**Architecture:** `amd64`  
**Status:** `PASS_SIGNED_INPUT_AND_PACKAGE_CLOSURE_ONLY`

## Exact qualifying execution

Source head `6825f9bd4bd012212559d187315bca285a6ae3d2` passed the permanent
`debian-snapshot-lock` workflow in run `33196743127`. The uploaded
evidence was artifact `9696135492`, named
`debian-snapshot-lock-2c019cb8f42423af42f518cdf5d434789991b0aa`, with ZIP SHA-256
`a55b04bb56b94fe5fa4dd055fc38e71e535be1d45bcfb4071176c0cdc6f3e9f8`.

The canonical machine lock is committed at `manifests/debian-snapshot.lock.v1.json`. Its exact file
SHA-256 is `cd7118481f0b6875d16352b682a8880da923b44893cab884483b307abb64deae`. The permanent workflow regenerates that
lock and requires a byte-for-byte match before the checkpoint can remain green.

## Signed archive inputs

| Archive | Suite | InRelease SHA-256 | Accepted valid primary key |
| --- | --- | --- | --- |
| Debian | `trixie` | `98b25b5cd185c59d34aa6e4c3e9b5b8f01bbe9d104fe2dcfbcd30dc0a14a59ed` | `04B54C3CDCA79751B16BC6B5225629DF75B188BD`, `41587F7DB8C774BCCF131416762F67A0B2C39DE4` |
| Debian updates | `trixie-updates` | `e7e983b7c9f67a4c3f007e6a0ca808fbe855dededdac9e94d6e4b0cc84fe21a0` | `04B54C3CDCA79751B16BC6B5225629DF75B188BD` |
| Debian security | `trixie-security` | `324858a9652243a987a7bbbe812fc41aabfc2a9cd86c65bd9a9c17bbe4fd8ee4` | `5E04A1E3223A19A20706E20F9904613D4CCE68C6` |

The minimal keyring SHA-256 is `dbc72305245c79a3087dd1cffb35e9fdf56ee0df7cc0a8637a5662a9110305db`. Additional
unknown co-signers are recorded but cannot replace the required valid signature
from an accepted pinned primary key. Bad, expired, revoked, missing-data and
internal signature failure states remain fatal.

## Exact package closure

APT resolved from an empty isolated dpkg status database with recommends
disabled and unauthenticated/insecure repositories forbidden. It selected and
downloaded `319` packages. Every `.deb` byte length
and SHA-256 matched signed APT metadata. The canonical sorted package-set
SHA-256 is `89918a968afafdbabe03e43794565cb1dc936f3f24a09ec81030be4a4085333a`.

## Claim ceiling

This checkpoint proves signed immutable Debian inputs and their complete amd64
package closure only. It did not create a root filesystem or disk image, did
not boot QEMU, did not start systemd or Wayland, did not enable Secure Boot,
and does not claim product or release readiness. The next gate is `D1-01`.
