# a286 native v1 — host archive preparation failed

The [original result](result.json) and [authoritative status](process-status.json) record job `1a1a3f74e02-96a-77aa`, exit 1, no timeout or cancellation. The failure is `ValueError: archive exceeds limit` at `inputs_frozen`. Native execution was not attempted; controls and scenarios are both empty.

The previously [successful original kernel](../g2-a286-kernel-v4-20261104/README.md) and exact original owner were retained, but the host did not reach QEMU. The fixed base plus owner creates a cpio above the generic codec's original 16 MiB limit. The later [exact-profile source repair](../g2-exact-archive-source-20261104/README.md) uses a source-owned finite envelope and keeps the shared codec default unchanged.

The [independent review](independent-review.json) and [index](evidence-index.json) retain the original binary-read SDK payload in two contiguous immutable pages. The file is complete at 12,664 bytes, independently checked against SHA256 `250f3d7715aea0ab7c88685b7e32a48f4e861fffa4ac588e640f3c8cef8e3e36`. A temporary reviewer decoding error did not cause an execution replay. There is no guest, G2, reply-loss or production acceptance in this attempt.
