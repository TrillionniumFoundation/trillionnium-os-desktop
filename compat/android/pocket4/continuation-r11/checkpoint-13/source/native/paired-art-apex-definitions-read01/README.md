# Fixed ART APEX definition observation

This request reuses the actually exercised held-fd source reader. It observes only `art/build/apex/Android.bp` (256 KiB) and `art/build/apex/apex_manifest.json` (16 KiB) under the already known AOSP checkout. The paths are prospective observations; missing or oversized files remain failed observations. There is no directory search, source execution, private-key read, tool installation, build or Main action. The two definitions establish possible target/key configuration only, not a binding to an installed ART binary, the newly compiled 451 builder, or a signed APEX.

The four identity/read helper functions remain byte-identical; only the fixed list and scope labels change. No remote call has been made by this freeze. Request resource limits remain 25 percent CPU, 128 MiB and 30 seconds.
