# Pinned native bridge source input

This input repairs the normal vendor build's missing Git provenance for the existing native bridge source. The 926 working source files retain their prior bytes and modes. A real commit, parent, tree and upstream ancestry now accompany that source; the normal preparation function and its integrity checks are unchanged.

## Source identity

| Item | Pinned identity |
| --- | --- |
| Official upstream | https://github.com/denialwm/teto.git |
| Upstream and parent commit | `917021cf3ecd077eb1581146a79d2265011755b8` |
| Current input commit | `9587399bccdbb7ec6f7de3edd3452609b974eb7c` |
| Current input tree | `cfe7f91f5afe6758e9dd94c7d4c09ae8e50eb150` |
| Working source members | 926 |
| Existing changes from upstream | 30 modified files, 24 added files, zero removed files |
| Archive SHA256 | `6d91f04bb9d5c59663704002d5c95d584fd0c529fea1395812f9495a8cebac38` |
| Archive size | 599,000 bytes |

## Reproducible inputs and actual checks

`SOURCE.tar.xz` contains the exact source manifest, existing changes as a patch, a real Git bundle, the source preparation code, original preparation-function test source, complete actual test output and retirement records. The Git bundle has the pinned official upstream prerequisite; this capsule does not claim to embed that upstream repository's entire history. Use the actual upstream commit and verify the bundle prerequisite before applying the fixed input commit.

The original normal preparation entry passed eight actual tests. Its one existing network test stayed ignored; the upstream was separately fetched and checked using real Git operations, ancestry, object verification and the complete working source inventory. Root independently checked all 22 archive members, all 21 frozen body hashes and the held-file/path identities.

The bounded R4 normal vendor build actually consumed this input, completed Mesa and Go bootstrap, and then stopped at the independent Soong reference to `trendy_team_desktop_display`. Normal recovery succeeded. The full 651-project source and all 926 native-source members, Git identities and provenance matched their original bookends after recovery. This is evidence for the repaired source input, not a successful vendor image or Android boot.

## Scope

The full-source, strict neverallow, projection recovery, original lock and resource checks remain required. No host installation, Android start, application acceptance or production readiness is granted by this capsule. `SOURCE_FREEZE.json` preserves the original observations; `ROOT-VERIFICATION.json` records the independent verification without converting later build failures into success.
