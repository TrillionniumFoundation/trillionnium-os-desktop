# Fixed ART APEX manifests supplemental reader

The original two-file reader actually obtained Android.bp and correctly reported ENOENT for the guessed apex_manifest.json. This revision preserves that partial failure. The complete pinned Android.bp names manifest-art.json for release defaults and manifest-art-debug.json for debug/testing. Only those two 16KiB-bounded files are now requested, after a held 32KiB-bounded reread of Android.bp must retain its observed 14519-byte SHA. If authority changed, no manifest is read.

The four observation helpers are byte-equivalent in AST to reader01. Held/named/ancestor identity, regular-file, full byte count/SHA/UTF8 and failures remain unchanged. No directories are scanned, no source or image tool is executed, no signing key is read, no service starts, and no Main or build source is modified. This only reads current AOSP sources; it does not bind installed ART or either updater binary.

Envelope remains reader01's schema: gzip_bytes/gzip_sha256, uncompressed_bytes/sha256, payload, all_two_complete. This source and exact request are unexecuted; root owns dispatch.
