# Typed AppZygote ingress V1 — disabled authorization endpoint

This candidate changes four exact current AOSP source files and adds one native header. It repairs the missing typed data path without treating a role label, sampled seccomp mode, or an immutable Java object as authority. It does not enable a factory or a platform role.

## Actual production call path

ZygoteArguments recognizes one new explicit requirement, `--require-droidloom-app-zygote-role-v1`. Duplicate requirements are rejected. A requirement cannot be combined with another child-zygote entry class, query or non-child launch. No existing production sender is changed to emit the requirement.

ZygoteConnection calls the new parser after its existing kernel SO_PEERCRED/System UID check and after the original UID, invoke-with, debugger and wrapper-property policies. Without the requirement the helper returns null immediately; the old AppZygote/ordinary fork route remains intact. With the requirement, explicit nonzero initial UID/GID and no wrapper/capability request are required. Only the exact AppZygoteInit entry plus one socket, one ABI list and canonical positive int32 range endpoints are accepted. Duplicates, unknown/missing fields, NUL, signed/leading-zero/overflow range spellings and reversed/below-platform-minimum ranges are rejected. The range is the same UID/GID range supplied by the actual existing ZygoteProcess producer.

The immutable specification stores primitive final fields and immutable Strings; it does not retain or expose the mutable argument array. The child argument copy is reconstructed canonically from the captured range. Zygote's actual private JNI declaration passes the original UID/GID/child marker plus eight fixed V1 fields, with the matching `(IIZIIIIIIII)V` registration in the actual native method table.

The native entry copies those fields into a const-field value and validates their structural relationship. It then always rejects: invalid shape raises IllegalArgumentException, nonroot credentials raise SecurityException, and a structurally valid root call raises UnsupportedOperationException. A compile-time assertion prevents changing the disabled constant into an enabled role. Both Java callers reject an unexpected JNI return. This happens before preFork, pipe setup, thread suspension or the original native fork; it makes no capability, NNP, seccomp, factory, guest or Main operation. Existing JNI fork signatures and function bodies remain unchanged.

## What is still missing

This endpoint does not prove initial-user-namespace/root-parent identity merely from numeric UID checks. It does not install the immutable base policy plus the range policy, set all-thread NNP, establish the actual child PIDFD/fork-return-PID exchange, or obtain the one-time factory parent approval. Those production implementations must replace this explicit rejection before a role can run. It is not acceptable to return from the endpoint and enter the old fork as a fallback. No production caller currently requests it, and no enabled ART/engine/factory image pairing is claimed.

The ordinary V2 zero-cap path, native raw metadata, NOFILE26, Registry, listener, OwnerLease and snapshot sources are not changed. This is a new current-source candidate; it is not automatically the installed ART or compiled builder462 source, and it has not been projected through the normal builder or deployed.

## Verification

The four old files retain every existing line; additions are bound to the exact source hashes in INPUT_BINDINGS.json. The Java native declaration, fixed field order and C++ registration descriptor agree. The actual inserted native function is extracted byte-for-byte, compiled with the actual production header using local g++ C++17/Wall/Wextra/Werror, and all 20 rejection/boundary controls pass (60 assertions). JNI exception delivery and numeric process credentials are explicit seams. No fork, grant or Android action occurs.

The local environment has no javac. Java parser/JVM execution and the complete Android translation unit remain NOT_RUN. The extracted native controls do not replace those gates, policy verification or an actual early-fork integration test.
