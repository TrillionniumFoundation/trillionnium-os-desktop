# Preparation revision 02

No preparation or runtime from freeze01 has been submitted. The sole executable
source change is in `input_file`: the raw Cargo/native build inputs may have a
positive hard-link count; the existing sealed root-owned base still requires one
link. Actual inode/device, bytes, mode when recorded, full SHA and held pre/post
metadata remain mandatory. The copied package always creates fresh root-owned
files and revalidates the original sealed nlink=1 contract before any execution.

The audit02 compile and ordinary-run receipts did not record or require nlink.
This change does not assert that any observed device failure was caused by a
hard link. Freeze01 is historical, unexecuted, and preserved byte for byte.
All actor, coordinator, qualifier, plan/nonce, limits and runtime template bytes
are unchanged. Only the preparation packet and key are revised. Runtime still
requires this revision's actual successful prepared.json SHA and separate review.
