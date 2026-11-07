# Actual run02 original log collection

Reads only the exact registry stdout and stderr named by the already-verified 11715-byte runtime result bc5c8e59a963828c6c59a8b1cd183e575c8903fbb4efa850369a23666dd1dcd9. It verifies that protected authority before and after the two reads. The runtime observed descriptor identities, sizes and full SHA values must match each log. Empty stderr is a valid pinned original.

Root access is read-only. Every original is opened without following its final symlink, held across the bounded read, and compared with the named inode before/after. Each file retains explicit errors; no broad scan, writes, chmod, process creation, runtime replay, Main or Android action. The source and exact request are frozen separately from the original run and its full-result review.

The reader does not independently assess the ten cases. After collection, use the frozen runtime validator offline on the original stdout and compare it with the original full result. CPU25%, memory128MiB, timeout30s.
