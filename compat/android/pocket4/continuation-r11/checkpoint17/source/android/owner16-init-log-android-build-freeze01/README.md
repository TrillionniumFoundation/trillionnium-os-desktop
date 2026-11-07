# Owner16 paired Android init logging build

Create-only CPU1/512MiB/180s successor to the actual ABI3 Android build.
Its original147 input pins remain unchanged. Exactly two actually observed
inputs are added: dlfcn.h8723/4fe89c… and libdl.so50760/cac32e… . The explicit
libdl path is the only new Android link argument; --no-undefined remains.
Preflight and real MD must match the exact141 headers/source set. Expected
DT_NEEDED is exactly libc.so and libdl.so, with original versioned ABI export,
INIT_ARRAY and x86_64 retained. The new source payload has9 exact members.

The original20/20/7/8 owned controls remain. New9 controls execute only host
owned memfd/fd/env/exec, use an explicit KernelLogger call seam, and require
their complete187-assertion receipt. They cannot qualify the Android logger.
19 actual commands, all source/header/compiler/link/tool before-after gates,
child cleanup and original own resource gate must pass for a build receipt.

The actual libdl observation qualifies this link input, not the defining
libbase KernelLogger bytes/cache/ABI. Only a future matched Owner runtime can
qualify its real logger markers after held HELLO and before broker startup.
This package performs no Android constructor, namespace, Main deployment or
Owner runtime. Its new ELF must be actually returned and externally bound.
