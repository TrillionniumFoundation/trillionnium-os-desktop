# Receipt format and error-localization addendum

This addendum corrects wording in the frozen Gallery history bundle whose manifest is `a59935b485b26a15fedc93791c270929701c420dba26945af2186a1daf64eaf3`. That original bundle is unchanged.

**The flow01 published receipt is original stdout.** Its SHA-256 is `23ab3c6f0cccf56d0607fadb5c0cf4dac6a1376d41ec2ebf52e3652acb459c52`. The remote result file was serialized by the fixed transaction `write_new` implementation with sorted keys and a trailing newline; its SHA-256 is `836a9aef54eb5ea0ac623ff30635e3cd0aca595ff130931cc332bf749109bd77`. Python reconstruction gives exactly that hash, and the parsed JSON values are identical. Subsequent hash-bound readers verified the actual remote file. Do not describe the stdout artifact as byte-for-byte identical to that remote file. Both are 11,346 bytes.

**Cleanup02's precise ENOENT stack frame was not captured.** The original terminal receipt contains the exception type and message, but no traceback. The saved row92-absence journal and source ordering point to the following deleted-FUSE-FD `fstat` as a source-based inference. They do not prove that call was the failing stack frame, nor that its old FD returned nlink0. The separate current-state reconciliation proves image92's row and paths were absent. Cleanup03 independently proves the held backing directory inode reached nlink0 and that the remaining directory/index/helper were removed.

These clarifications change no execution result or qualification. The original flow01 and cleanup02 failed/unknown records remain unchanged, final cleanup is separately verified, and no Gallery business or rotation gate is added. No new device operation was performed to produce this addendum.
