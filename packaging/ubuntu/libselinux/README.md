# Ubuntu libselinux native exec and keycreate attributes

The shared Linux/Android policy keeps systemd executors from writing files with
their own process label. This also protects process memory. Ubuntu's libselinux
3.9-4build1 sets exec and keycreate contexts through procfs files with that label.
Systemd sets exec contexts; Ubuntu PAM also sets and restores the key creation
context. This component maps only these two fixed setters to the native
lsm_set_self_attr API: LSM_ATTR_EXEC and LSM_ATTR_KEYCREATE, both explicitly
selecting LSM_ID_SELINUX.

The target kernel runs the same SELinux setexec/setkeycreate, target key creation
and exec transition checks as procattr. The change preserves the public ABI,
per-thread cache, other attributes and the original procattr implementation for
kernels returning ENOSYS or EOPNOTSUPP. EACCES, EPERM and every other real error
return without fallback. A NULL context is encoded as one NUL and clears the
pending exec or key creation label. EINTR is retried.

This component replaces neither libapparmor nor systemd. Neither patched setter
requires self:file write permission. No policy load, dyntransition, ptrace or
proc-memory write permission is granted.

## Build with the original Debian packaging

Use an isolated source/output directory on Ubuntu resolute. Download the exact
source package through authenticated APT metadata, then verify the sizes and
SHA-256 values in `source.lock.json` before extraction:

```sh
apt-get source --download-only libselinux=3.9-4build1
dpkg-source -x libselinux_3.9-4build1.dsc libselinux-3.9
```

Copy `p4-native-lsm-exec-attribute.patch` into the extracted
`debian/patches/`, append its name once to `debian/patches/series`, and prepend
the supplied `changelog-entry` to the original `debian/changelog`. Preserve all
other distribution patches and packaging. The original `.orig.tar.gz` remains
beside the source directory.

Run the original source/package tools, with the normal declared dependencies
actually installed and checked:

```sh
dpkg-source --before-build libselinux-3.9
cd libselinux-3.9
dpkg-checkbuilddeps -P nopython,noruby,noudeb
SOURCE_DATE_EPOCH=1795528800 dpkg-buildpackage -F -us -uc --build-profiles=nopython,noruby,noudeb -j1
```

The profiles omit Python, Ruby and installer bindings; they do not disable the
library build or compiler hardening. The original Debian rules select PCRE2,
large-file support, hardening and LTO. The output has a distinct version:
`libselinux1_3.9-4build1+p4lsmexec2_amd64.deb`, with normal source, changes and
buildinfo files. Record the real command, tool packages, compiler flags, exit,
logs, archive hashes and extracted library hash outside Git. Do not replace the
host library during construction.

## Validate the real packaged library

Extract the package with `dpkg-deb -x` into a fresh directory. Its sole library
member is `usr/lib/x86_64-linux-gnu/libselinux.so.1`, SONAME
`libselinux.so.1`. Compare all defined versioned GLOBAL/WEAK FUNC/OBJECT exports
with the pinned original library, and inspect its actual DT_NEEDED dependencies.

`native-exec-api-test.c` calls the public APIs of that actual shared library.
It interposes syscall and procattr operations only inside its disposable test
process to verify cache/reset handling, EINTR, the two unsupported-kernel
fallbacks including NULL clear, denial/error propagation without cache damage,
separate exec/keycreate caches, actual thread-local isolation, both PAM-facing
public setters and unchanged current/fscreate/sockcreate handling:

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror -rdynamic -pthread native-exec-api-test.c -ldl -o native-exec-api-test
for attribute in exec keycreate; do
    for case_name in cache-and-clear eintr enosys eopnotsupp eacces eperm einval e2big efault enomem null-first enosys-null eopnotsupp-null fallback-failure failure-retains-cache thread-local public-wrapper; do
        ./native-exec-api-test /absolute/extracted/usr/lib/x86_64-linux-gnu/libselinux.so.1 "$attribute" "$case_name" || exit
    done
done
./native-exec-api-test /absolute/extracted/usr/lib/x86_64-linux-gnu/libselinux.so.1 exec independent-cache
for attribute in current fscreate sockcreate; do
    ./native-exec-api-test /absolute/extracted/usr/lib/x86_64-linux-gnu/libselinux.so.1 "$attribute" other-attribute || exit
done
```

These are ABI unit tests. Target-kernel acceptance additionally requires the
real systemd executor and original units under enforcing SELinux and AppArmor,
a successful authorized exec transition, rejection of unauthorized contexts,
and rejection of actual proc-memory open/write. A fixture overlay must pin the
original and candidate package/member, modify only a fresh fixture, and record
its DPKG database as unchanged. Physical installation must use the normal package
manager after runtime qualification; an extracted fixture overlay is not an
installed-package claim.
