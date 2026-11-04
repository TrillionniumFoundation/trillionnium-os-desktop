# Original App Server signal component build

This is the completed Rust 1.96 component build of Hepta
`857d8f61b96453c06a7f93dfba79dcdebca31bf8` and the original Desktop seed test at
`92a06c4b4b041a9e94d83480bc2c4cdcd6afa3d2`. The seed test links the original
`a39a0871d9601ffccb5e0d95d8f39d54b3a63360` library. These are explicitly
separate component sources; this record grants no combined product or actual
seed execution result.

All 19 commands in [the original result](result.json) returned zero, and both
source trees remained unchanged. The three isolated TERM/HUP/INT parent tests
and two original drain tests passed on their first attempt: 5 selected passes,
304 skipped, no retries or flaky results. The ignored child helper is not
counted again. See [the complete selected-test log](signal-and-drain.stderr.log).

The product-linux App Server is 103,449,400 bytes, SHA256
`fd1fed2f97e218f77d6a3d682579d1681785e93de72781419684d849bd278254`.
The seed test executable is 70,664,232 bytes, SHA256
`e3519ccd0efdbd919876d77875976ab825a6823ae6935134670133802ffb926c`.
The executables remain on the build host and were not downloaded for this
archive. Their recorded hashes alone do not qualify an installed application.

[The original evidence archive](original-component-evidence.tar.gz) contains
41 complete original members: the result, all 38 command stdout/stderr logs,
and the two source Git bundles. Its compressed size is 102,286 bytes and SHA256
is `2e80f7ef20b340aface1f035ddc93ac08112008da393950f6e4ae04dc5d7dbbe`.
The original members total 1,255,687 bytes; the 1,111,575-byte seed compile JSON
stream is preserved whole inside the archive. The readable copies in this
directory are exact original members, not rewritten summaries.

[The original archive index](original-component-evidence-index.json) gives
every member's size and SHA256. [Root verification](root-verification.json)
records independent full archive, member, Cargo JSON and transport checks.
The final pipeline and complete [job stdout](job.stdout.log) and
[job stderr](job.stderr.log) were observed. The two direct metadata reads
timed out, so this record does not invent a job-level exit status from EOF.

The once-only real seed lifecycle has a separate request, fresh deployment
prefix and result. This archive does not stand in for that result, a user
submission, Core turn, GUI effect, independent application readback, original
writer terminal or reconnect/restart recovery.
