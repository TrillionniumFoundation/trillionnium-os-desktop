# Fixed host-stage parent metadata read

Root reported stage01 refused the parent permissions before mkdir. The original request/failure stay unchanged. This four-path, read-only diagnostic records caller IDs/groups, fixed named and held O_PATH identities, modes, realpath and exact errors. It reads no contents, enumerates no directory, creates no file or child, and changes no permissions. Default PLAN does not observe even these paths.

The first two paths are the original parent and nonce target. The last two are the already-known exclusive native owner root and a proposed child path. Their presence or absence is evidence only: no path, nonce reuse, staging or runtime is admitted automatically. The resulting actual metadata will determine the next separately frozen revision; missing or inaccessible entries stay explicit.
