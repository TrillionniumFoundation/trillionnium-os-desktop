# Fixed trusted ingress / host-thread-exit source reader

Source-only request, not dispatched by its author. It reads five fixed AOSP paths under the same previously observed AOSP root: ZygoteConnection, ZygoteArguments, ZygoteProcess, AppZygote and Bionic pthread_exit.cpp. The range ingress is needed before changing Java/native fork signatures; the exit source is needed to close the unregistered raw worker lifetime.

The existing held-file/named identity checks, regular-file/ancestor rejection, byte limits, strict UTF-8, full SHA and bounded single gzip transfer remain unchanged. Missing or over-limit paths are recorded as failures without fallback or scanning. This reader neither executes source nor opens an Android service. CPU25%, memory128MiB, nice15 and timeout30s remain unchanged. It proves only the bytes observed, not their installed/compiled binding. Root owns any eventual dispatch.
