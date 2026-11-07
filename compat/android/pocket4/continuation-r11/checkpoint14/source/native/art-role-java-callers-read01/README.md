# Fixed Java zygote caller source observation

This request reads exactly three current AOSP Java files: ZygoteHooks.java for parent/child post-fork dispatch, Zygote.java for the native fork and post-fork ordering, and AppZygoteInit.java for guest preload and the app-zygote event loop. Each maximum is 262144 bytes. The fixed AOSP root and all four held-fd observation helpers are unchanged from the reviewed APEX reader.

The reader retains missing, oversized, alias, non-regular, changed or invalid-UTF8 observations as failures. It performs no source execution, recursive discovery, filesystem writes, policy changes, service actions or build. It returns one gzip envelope with full sizes and SHA-256 digests. The request retains CPU 25%, RAM 128 MiB and 30 seconds.

The source observation cannot by itself bind installed ART, the compiled updater, or prove a runtime role/capability lifecycle. No remote request was submitted while freezing this package.
