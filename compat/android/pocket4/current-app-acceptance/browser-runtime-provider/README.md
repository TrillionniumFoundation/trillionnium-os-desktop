# Native browser input provider

This packet adds the finite browser input provider to the complete native Droidloom supervisor source at commit `9ecce4f94dec80500c05322106907e48a0668b05`, tree `12fe22ce02be9759963835faa4e7a7d0a762ddc2`. It supplies, transfers, observes, borrows and retires a separate private `cmd` executable through the existing owned runtime. The production `OpenBrowser` request remains rejected. This packet does not add an action worker, install a policy, select a runtime generation, or establish application acceptance.

The native source base is distinct from the GitHub compatibility packet's base. Applying this patch requires the complete native source identified above. The files in this compatibility directory are not a replacement supervisor crate, and compiling a standalone substitute would not qualify this change.

This packet does not contain that complete native base and cannot by itself provide a reproducible GitHub CI build. The owner must first publish or otherwise supply the exact complete native source generation before connecting such CI. The private complete-crate qualification described below is not a claim that the native commit can be checked out from this GitHub branch.

## Exact source inputs

`BASE.json` identifies the native commit, tree, tracked membership and the eight existing files changed by the patch. `CANDIDATE.json` identifies all 17 final source inputs: nine native/Cargo files supplied by the patch, plus eight unchanged files from the adjacent `browser-action-contract` packet. The patch includes the complete new `production_runtime_browser_assets.rs` module.

The contract dependency must exist at `compat/android/pocket4/current-app-acceptance/browser-action-contract/` in the native candidate. Preserve its eight exact files from the published contract packet, including its independent workspace declaration. Do not replace it with a stub, omit it because the patch applies, or copy a different contract revision. The candidate manifest records its complete file hashes. The native workspace explicitly excludes that independent workspace and depends on its actual crate by path; the native lockfile includes that dependency.

## Manifest and descriptor roles

The existing runtime manifest has an optional, strict `browser` object. Its six fields map to the fixed contract's `RoleDeclaration`:

```json
{
  "scope": "fixed_browser_action_v1",
  "source_system_sha256": "<complete selected system digest>",
  "source_path": "/system/bin/cmd",
  "cmd_sha256": "<complete original cmd digest>",
  "cmd_bytes": 4096,
  "interpreter": "/system/bin/linker64"
}
```

The size above is illustrative. The actual manifest must identify the actual original executable, with a size from 64 bytes through 128 MiB. The second allowed interpreter is `/apex/com.android.runtime/bin/linker64`. An absent interpreter and the bootstrap linker are still accepted where the existing query declaration permits them, but cannot qualify a browser declaration.

Browser inputs require the existing query declaration. Both declarations must identify the same selected system and exactly the same original `cmd` path, size, complete digest and interpreter. No label, private destination, source filename, PID, Ready claim or arbitrary command field can be supplied. Unknown fields are rejected. Declaration consistency is only a prerequisite; actual sealed files and live ownership are checked separately.

| Transfer shape | Fixed descriptor order | Meaning |
| --- | --- | --- |
| Two descriptors | Runtime filesystem, original init mount | Existing base runtime |
| Three descriptors | Runtime filesystem, original init mount, query filesystem | Existing query runtime |
| Four descriptors | Runtime filesystem, original init mount, query filesystem, browser filesystem | Explicitly selected query plus browser inputs |

There is no browser-only three-descriptor alternative. The child accepts only the exact three complete SCM_RIGHTS lengths, checks the original packet nonce and parent identity, rejects truncation, extra control messages and duplicate received descriptors, and validates each fixed role before attachment. The fourth role is attached only at `/.droidloom-browser`, containing exactly `cmd` with the fixed `droidloom_browser_action_exec` object label. The existing query filesystem remains separate.

## Ownership and sealing

The provider consumes the same real `OwnedNamespaceWitness` as the existing runtime preparation. It opens the fixed root-sealed `cmd-original` input, rejects user backing storage, verifies the full original bytes, original object label, absent file capabilities and ELF interpreter, and copies the complete executable into a fresh inode on a new detached private tmpfs. It applies the fixed browser entrypoint label only to its own new inode and directory. It closes writable executable descriptors, seals the initial-user-namespace-owned superblock read-only, and applies the existing read-only, nosuid, nodev and idmapped mount requirements before transfer.

The parent observes the exact browser root and leaf, checks the private filesystem and label, rejects an alias of the query roles, and verifies the same inode and mount projection in the owned child. Label reads use an ordinary read-only descriptor reopened from the held inode; an O_PATH descriptor is not treated as readable label evidence. The child independently checks its fixed target, complete leaf set, mapped-root ownership, mode and label.

`PreparedRuntime::browser_executable` returns a borrowed input role only to the existing opaque `ApplicationAuthority`. It binds the actual runtime owner, selected cohort and manifest, host UID, original user namespace and mapped root. Before returning the borrow, and when revalidating it, the provider reads `/system/bin/cmd` and `/.droidloom-browser/cmd` through the actual held child root and verifies the complete original bytes and private projection. There is no constructor from a pathname, digest, serialized success flag or caller-chosen process.

The new resources remain inside the original `PreparedRuntime`. Untransferred failures close local resources; transferred custody is retained until the existing genuine owned-tree retirement witness permits release. Unknown transfer or retirement retains custody as before. Retirement reporting adds the browser executable and filesystem counts; it does not create a separate retirement authority.

## Capability boundary

The daemon, `ApplicationRead`, existing 15-descriptor read-worker protocol, process/exec checks, query MAC rules, production entry points and original namespace execution admission are unchanged. The only query-module addition checks that two manifest declarations name the same original `cmd`; it does not grant activity-service access.

No label is accepted as configuration. If the actually selected loaded MAC policy cannot create, label or inspect the new private role, preparation fails through the real kernel operation. There is no fallback to the query label, host execution, numeric PID entry, or a weaker policy. This failure behavior has not been exercised against the production loaded policy in this qualification.

## Rebuild and source qualification

Create a new isolated worktree or archive of the exact native base. Verify its clean tracked source and the eight base file hashes in `BASE.json`. Copy the eight frozen contract inputs into the fixed dependency location and verify their hashes in `CANDIDATE.json`. Apply `native-browser-provider.patch` with `git apply --check` followed by `git apply` in the isolated native candidate. Verify all 17 final files against `CANDIDATE.json` before compiling. Do not apply the patch directly to an actively owned runtime tree.

Use the native `rust-toolchain.toml` and an existing isolated offline Cargo registry. Give Cargo a target directory owned by this candidate, keep compilation to one job, and leave at least two logical CPUs available. The following commands qualify the actual native crate:

```sh
cargo test --locked --offline -j 1 -p droidloom-supervisor --lib browser_provider -- --test-threads=1
cargo test --locked --offline -j 1 -p droidloom-supervisor --lib production_mounts::runtime_assets::tests:: -- --test-threads=1 --skip browser_provider
cargo test --locked --offline -j 1 -p droidloom-supervisor --lib production_runtime_roles_reject_extra_targets_and_mutated_existing_ids -- --test-threads=1
cargo test --locked --offline -j 1 -p droidloom-supervisor --lib production_runtime_query_mount_requires_selected_fixed_readonly_tmpfs -- --test-threads=1
cargo test --locked --offline -j 1 -p droidloom-supervisor --lib production_runtime_fixed_component_walk_rejects_actual_symlinks -- --test-threads=1
cargo test --locked --offline -j 1 -p droidloom-supervisor --lib production_runtime_diagnostics_are_disjoint_from_previous_phases -- --test-threads=1
cargo check --locked --offline -j 1 -p droidloom-supervisor --all-targets
```

Expected test groups contain 8, 10, 1, 1, 1 and 1 tests, respectively: 22 distinct tests, with no failures or ignored tests. Reject a zero-test run. The eight new tests cover strict declaration consistency and rejection of authority fields, exact control-message lengths, actual two/three/four-descriptor SCM_RIGHTS transfer order and CLOEXEC, mount inventory rejection, real symlink/FIFO/type rejection, unqualified-label rejection, and full-byte/identity checks. They do not manufacture a successful namespace witness or MAC transition.

The final candidate was compiled as the complete native crate using rustc `1.93.0` (`254b59607d4417e9dffbc307138ae5c86280fe4c`, LLVM `21.1.8`) and Cargo `1.93.0` (`083ac5135`). All 22 focused tests and `cargo check --all-targets` completed successfully. The six edited Rust files passed the actual toolchain's rustfmt check. All 2,118 archived tracked source blobs were verified against the native Git tree, and all 2,127 final candidate files were compared before and after compilation; no unlisted source changes were accepted. The original native tree and the source registry remained unchanged. These are source and host-file/descriptor tests, not Android runtime acceptance.

## Remaining owner qualification

The next owner must issue a new coherent runtime selection and provider inputs, with the actual same-generation production MAC contract and policy. It must test successful private-role construction, idmapping and attachment with the real owned namespace and reservation, and verify both loaded LSM boundaries. It must also exercise label denial, swapped roles, stale owner/selection/namespace, changed original/projection, failed transfer and actual retirement against the real runtime. The source tests above do not supply these positive or negative kernel results.

A later finite browser action worker must still borrow current actual Ready, hold the framework epoch and package identity, bind an approved HTTPS target and explicit Firefox component, verify the actual executable/interpreter/library closure and dual-LSM execution, and prove command and leaf retirement on every path. That worker must receive a separate reviewed action protocol. The read worker must remain unable to execute browser actions. Production dispatch may be connected only after these conditions and the action's actual business acceptance have been verified.

No new production Android start, browser action, application acceptance, policy installation, canonical selection update or old-runtime cleanup is performed by this packet.
