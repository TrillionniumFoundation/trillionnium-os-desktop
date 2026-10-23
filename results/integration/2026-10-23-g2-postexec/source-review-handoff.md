# G2 post-exec observation prerequisite — source review handoff

## Status and fixed source pair

This is an internal kernel prerequisite, with no default boot caller and no new userspace ABI. It does not close G2 or establish a production FinalUse issuer.

- Desktop base: `cfe28e3efb5e025d58a9d663d1dd6a681c224892`.
- Hepta reference: `0adaca4375fdfefe0fbae7f1cb7f25c437360c6e`, tree `ea0efaf5806349291f67aff19c26d455df9da98b`.
- Apply `g2-external-fences-v1.patch` first, then `g2-postexec-observe-v1.patch`.
- A: SHA-256 `58092ce658c72ae01f9e8f124fc858a384f7f0cc0b4ad7a05a1e23b6e5226dc3`.
- B: SHA-256 `1f5230314fda05da4eea1a2fb02ed6a56548d58bb0de76eaba1fdcb51ff6c463`.
- Exact per-file before/after identities are in `g2-postexec-prerequisite-manifest-v1.json`.
- A modifies 10 files; B modifies 8, of which 2 overlap A. Total: 16 files.

Local verification completed: both patches apply in order to the exact sparse source base, every resulting file matches the authoring tree byte for byte, and `git diff --check` passes. This scratch environment has no Rust toolchain. **Rust builds, kernel ktests, and a native grant/read have not been run here.** Remote build/test receipts must be recorded separately.

## Authority construction and recipient binding

`PreparedInitialProcess::prepare_observe_launcher` is the sole production constructor of `SealedObserveLauncher`. It consumes the existing loader's sealed-initial-image proof and explicitly arms a launcher role before that initial process is scheduled. Existing G1-c and G1-d profiles do not call it. Matching an ELF hash, owning a control fd, or possessing a CPU observer pin does not automatically confer this role.

The resulting `ObserveLaunchAuthority` is not Clone and can bind one child. `bind_child` consumes it, even if binding fails. It requires the actual kernel caller to be the exact original launcher Process allocation; it resolves the recipient through a real `PidFile`, verifies the original parent's children map and the child's parent weak reference, then captures the live post-exec `ProcessImageKey`. The launch nonce is an identity selector derived from the non-reused launcher image nonce, not a bearer credential or random secret.

The eventual broker must pass an actual open control file to `control_session_recipient`. The resolver rejects the wrong file kind and O_PATH through the existing `InodeHandle` downcast. It extracts the `HeptaControlFile`'s own Process and full image key. Installation requires those to match the already-bound child and nonce. A sibling fd, a pre-exec fd, a new fd opened after an intervening exec, a reparented child, or an ended issuer cannot substitute for that recipient. Existing ioctl checks still require the caller to be the file's original Process image: receiving the fd does not let the Supervisor perform an observation as its child.

There is no userspace endpoint or HOS2 bootstrap-version change in this patch. A subsequent reviewed slice must connect this typed seam to the actual original Supervisor/Registry child launch. The current Hepta `UnixProcessDriver` and `SpawnSpec` do not carry this authority or a post-exec observation bootstrap; ordinary identity environment variables remain configuration only.

## External modification protection

The running recipient is not protected by the loader's initial-image seal. The initial seal assumes an unpublished, single-handle VMAR; its short check in `write_alien` cannot close a runtime check/copy race.

This slice adds an admission counter to each original Process and VMAR owner. `enter` checks an irreversible fence and increments a bounded counter under a short sleeping mutex. The returned RAII admission retains only the counter reference, so faults, user copies, clone construction, and cleanup occur without holding that mutex. Every return and error path drops the admission. `prepare_fence` rejects nonzero active work with EBUSY and then keeps new admissions out while the remaining checks complete. Dropping an uncommitted preparation changes nothing.

The Process admission covers actual ptrace attachment and all public trace access wrappers, including read/peek operations. The read/peek coverage is needed because those operations can hold tracee state before waiting for a Process VMAR lock. The VMAR admission covers the shared writable `access_alien` entry, including both `write_alien` and `fill_zeros_alien`, plus cross-Process `CLONE_VM` construction, including vfork. Ordinary same-Process threads are allowed after protection; ordinary fork gets a new VMAR and no inherited observation grant.

The handle check uses the existing `VmarHandle` count, not `Arc::strong_count`. These handles belong to POSIX threads; cached VMAR pins and old proc-mem file snapshots are not counted. First installation requires an unshared, single-thread VMAR. Once fenced, an exact retry can coexist with the owner's subsequently created threads. An external shared-VM clone is either active, already represented by a second handle, or refused by the committed fence.

The Process fence lasts for the **entire Process allocation**, including later execs. It is deliberately conservative and has no reopen API. The VMAR fence lasts for that VMAR allocation. The observation grant remains image-local and is revoked by exec/exit. These are different lifetimes. This protection does not claim to suppress ordinary signals, `PTRACE_KILL`, or all denial-of-service mechanisms; it closes the external register, memory, attachment and trace mutation paths relevant to the new authority.

## Installation transaction and lock order

The bounded lock order is:

1. Original Supervisor children map, then child's parent relation.
2. Child's Process VMAR, then child TaskSet.
3. Issuer image, then child image.
4. Process external-access preparation, then VMAR external-write preparation.
5. Existing tracer state for a bounded check.

All parent/allocation/nonce/image/lifecycle/slot checks happen before either irreversible fence. The image slot is prepared as a borrowed `PreparedPostexecObserve` reservation. A failed preparation leaves the slot untouched. In particular, the Process active check happens before inspecting tracer state: an existing ptrace operation waiting on the outer VMAR causes EBUSY instead of a VMAR/tracee-state lock cycle. Neither preparation performs user copy or I/O.

After confirming that no tracer, in-flight access, or disallowed VMAR handle remains, the transaction commits both fences and then the already-checked borrowed slot. Slot assignment cannot fail. There is no rollback/unseal path after commitment. A retained `BoundObserveLaunch` accepts only an exact repeat of the same child, both live images, nonce, original observer pin, and lease; it does not extend the lease or rebind a different child.

An already executing proc-mem operation also holds the Process VMAR lock, so the original outer lock may serialize it before installation reaches the admission check. Lower-level alien writers and cross-Process clone admissions are rejected with EBUSY when observed active. Neither ordering permits a writer to begin before commitment and mutate after commitment without being included in the admission.

## Observation and original owners

The new grant references an existing `NativeCpuObserver` and a saved lease. Attachment never invokes `NativeCpuObserver::prepare`, replaces the original CPU owner, resets accounting, or changes a CPU cap. ReadUsage brackets the real original-owner sample with child image and issuer liveness checks. It does not hold image locks across CPU membership, runqueue, or bandwidth work. A closed issuer image cannot become valid again with the same key.

The recipient obtains only the observation slot. It receives no manage grant, history capability, delivery namespace, journal, SQLite writer, ACK permission, or retirement permit. G1-d effect/history dispatch still resolves its existing control slots. The original HOS2 history owner is unchanged. A later complete G2 implementation must preserve that history owner across manager exec/recovery and must use the original writer's durable terminal/retirement path.

The current source pair still lacks a verified production Notes/organ FinalUse authority factory with the required protected clock, external authority frontier, issuer keyring/revocation inputs, original writer, and current-cut dependencies. The deployed Bao secrets authority and H7 grant registry are different domains and are not substituted here. No production key, policy, state, service, or issuer is modified or fabricated.

## Tests included and required execution

A includes five ktests:

- Admission EBUSY and uncommitted-preparation rollback.
- An actual already-open `MemFileHandle`: positive write, fence, rejected old-handle write, original-byte readback.
- An actual captured ptrace target: option mutation before protection, refusal after protection and after subsequent exec.
- The real writable alien-copy callback: active writer blocks fencing, then `fill_zeros_alien` is refused and the original byte remains.
- The real shared-VM handle constructor: CLONE_VM and vfork admissions block early fencing, a published second handle blocks later fencing, and a committed fence refuses new foreign sharing while allowing own threads.

B includes eleven ktests:

- Exact original child pidfd/live post-exec image admission, without granting rights from identity alone.
- Foreign caller and nonchild rejection.
- Pre-exec fork image rejection.
- Sibling control session and wrong-nonce rejection.
- Both old and newly opened sessions rejected after intervening child exec.
- Child exit and issuer exec rejection.
- Reparenting and second issuer activation rejection.
- Invalid recipient cannot reach the irreversible protection step.
- A real attached tracer blocks installation without closing either fence; after detachment, the captured target reference cannot attach again after protection.
- Either owner active rejects installation without partially fencing the other; exact protection retry is idempotent; exec invalidates the old recipient.
- An actual `HeptaControlFile` per-open object rejects a foreign caller and an ended recipient.

The tests use real unscheduled Process, TaskSet, VMAR, pidfd, ptrace and per-open file objects. They intentionally do not fabricate a CPU observer or consume a fake loader authority. They do not demonstrate userspace descriptor transfer, the actual original Supervisor binary, or a native CPU grant/read. Required gates are ordinary full-core compilation, g1-c and g1-d compilation, ordinary A ktests, feature-enabled B ktests, and a later explicit sealed-Supervisor/native-read integration gate before enabling a caller. Negative grant/image/fd cases must remain failures; no test issuer may be introduced to make that integration pass.

## Remaining integration boundary

The next production slice needs an explicit original owner factory that can provide the sealed Supervisor launch authority and the existing CPU observer/lease; a reviewed child launch handshake using an actual pidfd, original Registry/Supervisor identity and source-pair pin; a new typed observation bootstrap for Agentd; and a bounded userspace transport for the recipient's real control fd. Manage, recovery, durable writer receipt, history observation and retirement must be separate follow-on capabilities under the existing owners. This patch does not turn current F1 lifecycle evidence or a bare Agentd executable into G2 qualification.
