# Independent private OSDK root review

Approved the final four-file fix against published `09aea79c71dc9f48ba519757078dd8a20f5c8fb3`, with source hashes in `final-review.json`.

The independent review found a concrete problem in the first candidate: the fixed real Cargo normalizes an absolute Cargo-home path containing `..`, prepends its normalized home/bin, and selects a global SDK despite private/bin appearing first. The same failure was reproduced with unset CARGO_HOME and HOME containing `..`. The corrected wrapper rejects exact parent components before selecting its supervisor, lock or output. Eight actual wrapper invocations now reject these forms with status 2 and create no output parent. The tests include all three public targets and terminal `/..`. No compiler or kernel is reached.

Real pinned Cargo was independently checked with tiny external-command fixtures. Ordinary absolute paths, `/./`, symlinked home, trailing slash, double leading slash and repeated slash all select the private SDK when home/bin follows private/bin in PATH. A private SDK returning 47 causes Cargo to return 47 without running the global SDK. Raw actual-Cargo observations are retained in the sibling lookup directories.

Seven selected existing host runner tests were independently rerun through real GNU make and fixture Cargo: every developer target selects its private SDK; global replacement does not change it; separate calls install separately while sharing the registry cache; an inherited install-root variable cannot override it; failed installation stops without SDK fallback and cleans its owned manifest; invalid Cargo-home ingress rejects; and default home/bin remains behind private/bin. These are host fixtures, not Rust kernel or QEMU tests.

Static inspection verifies the SDK prerequisite is phony, `cargo install` retains `--locked` and uses the explicit private `--root`, the installed binary is hashed, and error propagation remains through existing make/supervisor handling. Five lifecycle helper files are byte-equal to the published baseline; tracked upstream OSDK runtime has no diff.

No remaining concrete issue was found in the scoped review. The private directory is ordinary mutable same-UID storage. This result establishes normal selection and failure behavior, not immutable storage or a new kernel boot. The reviewer changed no repository file, Git state or remote.

An initial independent guard-result checker expected an incorrect diagnostic substring and marked eight correct status-2 rejections false; its raw result remains unchanged. The corrected checker and all eight fresh actual invocations are in `actual-guard-results-v2.json`.
