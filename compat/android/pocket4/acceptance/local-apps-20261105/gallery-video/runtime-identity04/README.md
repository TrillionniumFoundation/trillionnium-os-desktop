# Gallery04 observed runtime identity

Five saved stable maps observations across two actual Gallery process generations
bind this exact signed APK, UID10064, Android user0 and framework epoch to the
process executable,381 mapped ELF files, ART, Android runtime and the nativebridge
and lazy-bridge files. Both reviewers checked the held process-root/device/inode
binding, before/after process identity and unchanged maps, full ELF hashes and the
earlier independent v3 signature audit for the identical APK.

The original sampler reports zero complete samples and remains unchanged. Its
two unresolved name candidates were a property mapping and a resource idmap;
the actual retained permissions for both are r--s. A similarly name-matched
overlay APK is also r--s. These are read-only, non-executable mappings. Their
contents are not read or qualified. The first launch's unstable maps observation
is explicitly excluded. Two named JIT caches, vDSO and vsyscall remain visible in
the review, without process-memory hashing or an anonymous-code integrity claim.

DERIVED_OBSERVATIONS preserves the pre-peer derivation. PEER_REVIEW and the
separate ROOT_QUALIFICATION approve only the observed per-App runtime identity
gate. They do not assert that ARM translation ran, identify an unobserved active
ARM backend protocol, exclude future translation, or award business, stress,
audio, rotation or whole-App production readiness. No new device/process reads
or App actions occurred during this saved-record review.
