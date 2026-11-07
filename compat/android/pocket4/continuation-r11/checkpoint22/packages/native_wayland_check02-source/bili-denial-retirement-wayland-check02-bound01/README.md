# Actual vendor binding for Wayland check02

This immutable candidate binds the completed vendor preparation to the existing full Wayland crate checker. It is UNRUN. The preparation is qualified; metadata and compilation are not yet qualified.

The fixed 193-package Cargo.lock set, 8,004 vendor files (192,608,580 bytes including checksum metadata), all archive identities and 193 reconstructed Cargo checksum records match the complete actual originals. The raw report, manifest and 204-byte config are referenced by immutable tree/path/blob and remain unchanged.

`packet/check_wayland.py` differs from the frozen template only in six actual byte/SHA256 literals. The nine production sources, 500-entry source map, original workspace/Cargo.lock, 15-command plan, three child lifecycle controls, cleanup, resource profile and fail-closed checks remain unchanged.

## Reproduction

Load this directory's text files into a filename-to-raw-string object. Fetch the three exact raw originals named by `actual-vendor-reference.json` from tree `4c4cb128c17d3b6a55871e78da9185adcba3f423`; do not reserialize JSON. Use the UTF-8/SHA256 helpers from `pure_js_binary.js`, then:

```javascript
const bound = bindPreparedVendorActual(files['check_wayland.template.py'], actual, H);
const reproduced = reproduceVendorWaylandCheckRequest(files, H, bound);
// Require exact raw string equality for reproduced.request, .stdin, .stage and .boundary.
```

The binder and request generator are unchanged copies of the reviewed template. `binding-diff.patch` shows the complete actual binding. `request-pins.json` records all 11 transferred and 8 existing fixed authorities. The 4 MB vendor manifest is read from its already-owned fixed path; it is not sent in stdin.

Only Root may dispatch `exact-request.json`. This candidate does not run a Wayland binary, touch Main, modify the shared cache, deploy software or qualify Android/GPU behavior. The original Wayland01 offline failure remains preserved.
