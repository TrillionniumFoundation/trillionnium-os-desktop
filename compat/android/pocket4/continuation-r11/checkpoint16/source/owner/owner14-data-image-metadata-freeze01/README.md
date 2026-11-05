# Owner14 retired data image: metadata only

This fresh request reads exactly the original prepared/runtime records, the first 4096 bytes of the original data.img, and the held debugfs ELF. It does not execute debugfs, open either proposed directory inside the image, mount a filesystem, replay an ext4 journal, write the image, or read the global kernel journal.

The original Owner14 NORMAL result remains FAILED. Its completed owned retirement and external cleanup authorize reading retained owned data; they do not qualify Android startup or LMKD enrollment.

The data image is the fresh sparse inode created by this exact prepared receipt: device 66306, inode 44189317, 8589934592 bytes, UUID cb90133d-9e2c-4477-85cc-a0636da228eb. Its content is expected to have changed during Android boot, so this metadata request does not compare it to a nonexistent preboot full-file digest. It checks the original inode/size/root ownership/0600/nlink1, the UUID and geometry, both named and held identities, and a stable 4096-byte header. Full-image SHA and exclusivity against all possible external openers are not claimed.

The actual-bound development.rs (95133 bytes, f73b823d53e7bd6a6daca9fff34f7c1ff5844ab39ba55171384414d6d58544c4) mounts this ext4 file directly on guest /data. Therefore the two later, separately bound directory reads would be image-root /tombstones and /system/shutdown-checkpoints, not image-root /data/.... Actual packaged init.rc (58845 bytes, 86d9d3a995a5bb70ea89431dca096bf21fa2310221c1cab90a4f23664e1a791b) declares those guest directories. Their presence/content in this failed boot is not yet observed.

Tool provenance: producer07-image-inspect01/result.json, 3887 bytes, SHA256 04b8c44dce6b42cb3d9a9675db037bdf0ef7d2e37d5289a1c6cbb8ce98843599 actually observed /usr/sbin/debugfs, ELF 231368 bytes / SHA256 864e1d7b445e7b5bfc831da78330dbcafc590fa82b89ea9de60b7527f989954f, root:root0755 with no file capabilities, and joined its -V child. This request rechecks that full original file identity and digest without executing it. A changed tool fails rather than silently rebinding.

The current request is CPU 1, memory 128 MiB, nice 10, outer timeout 30 seconds; the bounded reader has a 10-second checked work deadline and 64 KiB JSON output bound. It reads no arbitrary paths, runs no child, and uses no user-supplied filename. All opened descriptors are retained through final named/held checks and closed in reverse order. The local controls use the retained exact JSON receipts and only newly created temporary local files, not the Pocket4 image or tool.
