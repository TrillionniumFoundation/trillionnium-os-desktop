# Linux native Root product

This product composes the existing Hepta Root, Fleet supervisor, Agentd and Core
with the Rust Makepad Desktop. The original Session owns Notes and its two
private application channels. Packaging metadata does not grant an operation.
The original administrator and human checks still run after installation.

## Source and package contract

Freeze one clean Desktop commit/tree and one clean Hepta commit/tree after
updating [the shared dependency contract](DEPENDENCIES.md). All three Desktop
manifests, every Hepta entry in the five ordinary Cargo locks and the declared
prepared UI lock, the native resource profile and its source-tool checkout must
select that same Hepta commit. The prepared Makepad SDK must pass
the complete original source verifier; a default SDK build cannot inherit its
input-method or accessibility evidence.

[build_text_product.py](build_text_product.py) produces the native Desktop
build receipt, final stripped ELF records, resources and original five-program
package. [build_root_product.py](build_root_product.py) consumes that actual
package and its build receipt. It checks both clean source trees, original
resolved Cargo source, immutable locks and compiler identities, then builds:

| Executable | Owner |
| --- | --- |
| `hepta-desktop-root` | Desktop's explicit Root composition binary |
| `codex-hepta-agentd` | Original Hepta Agentd and original Core owner |
| `hepta-authority-host` | Original Root diagnosis/authority entry |
| `codex-app-server` | Same-source Core used for unused thread seeding |

The builder accepts two explicit cache directories outside either checkout.
It does not accept a replacement owner dependency or rewrite a committed lock.
It records the actual distribution bytes after GNU `strip --strip-unneeded`.
`--jobs` selects 1–8 compiler jobs, defaults to one, and is retained in the
receipt. It changes build concurrency only.
Each product builder holds an exclusive advisory cache lease across all Cargo
commands and packaging, so another cooperating builder cannot replace its
final binaries between commands. Root builds reserve both caches in a fixed
order and refuse contention. Direct Cargo commands must leave those caches
alone until the builder finishes; Cargo's per-command lock alone is insufficient.

[product/root_bundle.py](product/root_bundle.py) packages both parts and verifies
their complete file sets. `desktop/` retains its original package manifest and
five binaries, resources, SDK notices and source profile. `bin/` contains the
four Root tools, and `libexec/native_human.py` contains the reviewed local-login
provider. Both build receipts and the Root manifest travel with the package.
The manifest binds the exact Desktop manifest and supplement hashes; a release
identifier includes a digest of its supplement. The unchanged size bounds are
128 MiB per file and 512 MiB per payload part. The complete compressed archive
also has a 512 MiB bound. These are two explicitly bounded parts, not permission
to put an unbounded extra executable into the existing Desktop package.

The explicit installer uses a Root-owned, canonical installation prefix, such
as `/opt/trill-product`. Every ancestor and every installed descendant must
remain in Root custody and reject shared writes. Files are copied into a
private staging directory and reverified before publishing an immutable
release. Existing releases must match their complete manifests. Installing or
switching a release does not start services, create a human identity or reset
an existing authority directory.

## Runtime composition

The Root entry is a separate `product-root` binary in `hepta-session-host`.
The existing library continues to forbid unsafe code. Its explicit first
deployment is for a new dedicated private state prefix; existing or partial
authority state must not fall back to fresh initialization.

The original Fleet registry and supervisor spawn the actual unprivileged
Agentd. Retained process handles, pidfds, process birth, UID/GID and capability
checks bind the original incarnation. The Root composition creates the
anonymous startup pairs in the same process that serves Root; a helper cannot
impersonate their original creator. A one-use supervisor driver cannot reuse
the same inherited descriptors after an uncertain spawn. The original
supervisor continues to poll health and own process cleanup.

Before the bounded Notes startup episode, the same-source Core creates one
unused original thread with the exact Notes tool catalog. No prompt or model
turn is submitted during seeding. The final owner must resume and verify the
original thread, Core session, catalog, metadata bytes and configured model
tuple. A retained seed receipt alone is insufficient.

The actual Session reserves its Notes document. Root obtains the exact target
and nonce from the kernel-credential-bound reservation; it does not invent a
target for bootstrap policy. Reservation observation and later original
consumption share one cumulative startup deadline. The two application
descriptors stay in Session until the original Agentd recovery and activation
checks complete.

The physical human provider is described in [NATIVE_HUMAN.md](NATIVE_HUMAN.md).
It checks the actual local logind session and passes its retained leader pidfd
to its actual Root parent. Root independently checks that login and binds the
same human, original UI process and live route. A profile file, user-written
session name, model response or generic signed text cannot establish that
provenance. Leader-exit detection does not claim instant notification of every
logind state transition.

The prepared Root object launches the final `trill-shell --renderer makepad`
and serves the original authority lanes. It does not reopen the exclusive
clock/issuer through a second service. Human text is retained together with its
human binding in the existing issuer transaction, then delivered through the
original AuthBus to the original Core turn. Notes tools require the admitted
AuthBus delivery, original Core reconciliation and current Root human proof.
The model cannot authorize itself by directly starting another turn.

The first eligible Notes call in that original turn uses its original durable
writer identity. Before preparing and before signing, the original checks read
the current human proof again. A later call cannot turn a lost reply into a
second effect. The Notes application commits the actual document and returns
the original receipt; status/readback uses the same run, call and document
identity. Document format and migration rules are in
[NOTES_DURABILITY.md](NOTES_DURABILITY.md).

## Recovery and acceptance

Root retains a bounded, immutable SQLite image independently of Agentd before
publishing its corresponding original `Current`. Recovery reads the actual
protected `Current`, requires original retirement and lease fences, verifies
that independent image, installs under the original store lock, and performs
the original adoption CAS. The old database and WAL remain preserved. Dirty or
unrecognized state cannot be promoted to `Current`. Interrupted UID handoff is
reconciled against the retained original image; it does not capture the
possibly changed live database or repeat adoption.

| Evidence | What it establishes |
| --- | --- |
| Clean-source builds and package verification | The recorded source combination produced these exact package bytes |
| Controlled Root recovery tests | Original guards, real process descriptors and storage recovery in the recorded test environment |
| Installed-package product operation | Actual Root, physical human, original thread and real model completed the recorded Notes operation |
| Installed-ELF input/accessibility checks | Only the actually exercised Chinese/preedit, undo/redo, navigation, reader, focus and scale cases |

Neither the package schema nor a successful compilation claims the last two
rows. Preserve the installed package hash, process identities, original thread
and tool item, Root observation, exact document before/after identity and
readback when qualifying the product. Unknown outcomes remain fenced until
their original result is reconciled. Android original-signer qualification and
Asterinas native guest/driver qualification require their own source-bound
execution evidence.

The product builders use the selected optimized release profile for both native
UI tests and distribution binaries. The unoptimized 2026-10-26 runtime attempt
produced an actual 338,058,032-byte stripped Agentd and 304,151,824-byte stripped
App Server, both above the original 128 MiB per-file limit. That attempt is not
an installable product; stripping cannot remove already stripped code. The
release build must pass the unchanged file and bundle size guards. Root and
native UI build receipts retain their actual profile and compiler identities.
