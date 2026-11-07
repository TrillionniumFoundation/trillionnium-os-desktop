# ActionRunner source-location plan, stage 1

This request only indexes directory names and metadata. It does not qualify the installed ActionRunner package or permit UI operations.

## Fixed first stage

Open `/home/alex/work` through held, no-follow directory descriptors for `/`, `home`, `alex`, and `work`. Require the final directory to be owned by the original operator UID 1000. Enumerate its direct children once, selecting only ordinary directories whose names begin `pocket4-` or `droidloom-`. Matching regular files and symlinks are skipped. Do not enumerate any child directory or read any file body.

The report contains only selected paths, directory type, size and ordinary inode metadata, plus counts and errors. It does not include contents, source-file hashes, unrelated directory names, APK contents, commercial app data or journals. The held root's metadata must remain equal across the index; any error, limit, change or deadline leaves the index failed. No automatic retry or larger scan follows.

Limits: 2,048 direct entries, 256 matching directories, five seconds of collection, and 256 KiB of output. The exact remote request uses one stable key, a 25% CPU quota, 128 MiB memory limit, nice 10 and a 20-second outer deadline. It runs as the existing unprivileged operator and writes no remote files. Default invocation is PLAN_ONLY.

## Subsequent selection, not included in this request

Review this metadata index together with already pinned source inventories. Select a small set of exact task roots plausibly containing the prior ActionRunner build. A separately reviewed second request may search names within only those selected roots for `ActionRunner.java`, action-runner paths, related `AndroidManifest.xml`, build recipes or source manifests. It must exclude commercial app/data paths, `.git` objects, images, build output, target/out/cache trees, set count/depth/time limits, and avoid general content grep. Only then select exact small text files for bounded source reads and hashes in another explicit request.

Directory naming cannot prove ownership or build provenance. The remaining gate is an exact chain from the currently installed `local.pocket4.actions.v2` APK and signer to retained source and its matching build receipt. This first-stage request performs no Android command, instrumentation, UI, audio, launch/close, installation, permission change or data mutation.

## Current execution state

NOT SUBMITTED. Local controls use an isolated owned temporary directory, not `/home/alex/work`; they check directory selection, file/symlink skipping, no recursion, entry-limit rejection and the actual default PLAN. The parent must authorize a new device communication window before submission.
