# Genuine O_NOFOLLOW snapshot reopening: source freeze 01

This is an independent candidate. The ordinary snapshot source/build01 and candidate07 remain untouched. The original V2 ELOOP defect is still an actual red observation, and no privileged successful file-handle reopen has yet been observed. This freeze does not change the V2 wire/tag layout or the four Registry/context core files.

## Production change

Both the existing V2 factory MakeSnapshot and the new role-authorized MakeSnapshot use one small shared helper only when their actual source F_GETFL contains O_NOFOLLOW. The helper asks the kernel for a decodable handle of the factory's own freshly created, held, root-owned and sealed memfd with AT_EMPTY_PATH. It then uses that same held descriptor as mount_fd in open_by_handle_at, with the original status flags plus CLOEXEC. No peer handle, mount id, pathname or inode claim enters this step; the legacy internal mount id may be zero and is not used as authority. The buffer is fixed at Linux MAX_HANDLE_SZ 128 bytes and malformed returned sizes/types are rejected. All integer varargs are explicitly machine-word-sized.

O_NOFOLLOW is never cleared. There is no fabricated F_GETFL result, no new guest fcntl adapter, no capability adjustment and no alternate opening fallback on error. The factory's existing CAP_DAC_READ_SEARCH and kernel implementation are prerequisites. Missing support/permission remains a real error; enabled deployment must qualify the actual factory capability and syscall policy. The ordinary no-O_NOFOLLOW branch keeps its original proc/thread-self fd-directory operations. Both makers keep full final real inode/root/mode/link-count/size/seals/F_GETFL/FD_CLOEXEC/offset/tag checks. The role Authorize/Finish/revoke wrapper and all raw metadata field mappings remain byte-identical.

The V2 source is an explicit new copy derived from references/factory_main.v2.cc; it is not an assertion that an old deployed factory has changed. The production.diff names that preimage through INPUT_BINDINGS.json. No existing service or listener is started.

## Meaningful new runtime case

The four ordinary cases from source-freeze01 retain their behavior. A fifth fresh owned child opens its own canonical maps with O_NOFOLLOW and sends the real source/payload through the same actual Registry. The same tag/stat/raw-statfs/content/seal checks apply. The original source and snapshot F_GETFL must match exactly, including O_NOFOLLOW. A real kernel duplicate must keep the same flags; native F_SETFL on both the real source and snapshot must ignore attempts to clear O_NOFOLLOW and must share the same O_NONBLOCK changes through the duplicate. Original flags are restored before authenticated child handoff. The receiving child independently compares exact kernel status flags. Both parent and child also require the original V2 memfd readlink representation, so a different file-handle dentry cannot silently bypass the old client path check.

The fixture creates only fixed owned text, uses the original limited-role setup and exact PIDFD/fork parent approval, and requires five direct children normally reaped with no forced/unreaped children and full FD restoration. Its role filter still is not the production early platform policy. This five-case proposal does not directly exercise FinishCreate's own failure branch, complete V2 service transport, guest outer open syscall, arbitrary fork/namespace transitions or enabled ART lifecycle.

## Actual evidence and limits

Both new complete programs linked under local GCC -Wall -Wextra -Werror and their default no-action invocations passed. The exact compiler/plan receipt and logs are preserved under evidence/local-build01. No root snapshot case or service ran locally.

Separate nofollow-handle-mechanism-evidence-freeze01 retains the first Python missing-constant failure and the subsequent own sealed-memfd observation. The latter encoded a 12-byte/type1 handle with mount_id0, but open_by_handle_at returned EPERM in this local CapEff0/NNP1/seccomp2 environment. This does not establish a Pocket4 failure or success, and cannot distinguish the exact EPERM enforcement layer. The old O_NOFOLLOW red gate remains until a separately reviewed matching target build and actual owned positive demonstrate the complete real flags contract.

Root will first complete the ordinary O_RDONLY snapshot positive, then review/dispatch the new matching target build and actual-ELF-bound five-case run. No Main, Android, policy, filesystem mount, account or external service action is authorized by this source freeze.
