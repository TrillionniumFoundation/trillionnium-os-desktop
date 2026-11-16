# Native600 RKPD APEX input continuation

The strict Native r5 graph reached `rkpd-sdk` and stopped because its original `com.android.rkpd` APEX provider was outside the selected sparse source. This continuation adds the provider's complete `apex` directory from the same locked RemoteKeyProvisioning commit, `d88e2305f9186661fe75ee2f00c8b250a76fdabe`.

## Source change

Apply `native600-rkpd-apex-inputs.patch` after the source change in `native600-original-provider-closure-r1`. The normal recipe moves from commit `a538dae77820882a534ee79e0eb6d2984508a712` to `c90b25bdc326cd35dc77698c83a4cf3671d73f47`. Only the native pair lock and its normal Rust validator change. The recipe retains 458 files and the AOSP lock retains all 600 projects and their exact commits. Every previous sparse path remains selected.

The six original APEX inputs are bound by Git blob ID and SHA-256 in `original-apex-inputs.json`. `fixtures/apex.Android.bp` contains the original provider declaration. Signing input entries are public AOSP build test inputs; this capsule includes only their identities, with no key bodies. Adding those source inputs does not provide production signature or APEX validation.

The Rust regression tests reconstruct the actual old600 lock and reject the former selection, incomplete single-file selections, a different commit and an unapproved wider cone. They retain the original historical lock checks. The complete normal build targets remain `libberberis_arm64` and `com.android.art`, with missing dependencies rejected.

## Actual validation

The normal Rust tool build completed 23 owned commands, including the source-tool, ordinary-pair and pair-producer test filters. All returned zero and retired their owned children. Test filter counts overlap and are not combined into a unique test count.

The new Linux builder independently imported and checked the 458-file recipe, self-contained Git objects and both executable loaders in 15 successful commands. Normal source verification of the previous600 selection, reconciliation of the six original RKPD inputs and verification of the updated600 selection all completed. The source continuation completed eight commands, released the three original owner locks and left no updater projection.

The Python completion consumer changes only its exact source-lock SHA. Its 12 portable controls ran on Linux with zero skips, failures or errors, including rejection of the actual prior600 lock. Run the same suite with:

```sh
python3 -B -m unittest discover -s controls -p 'test_native_pair_control.py' -v
```

This capsule records no macOS execution. Its tests use ordinary Python interfaces and declare no operating-system skips.

## Full build boundary

r5 remains a failed, restored and retired build. Its resource and allocation gates passed; the missing RKPD provider was a real strict graph failure. These historical results are preserved.

At this capsule's explicit snapshot, r6 had started its independent inner service and passed normal lock verification; source-before verification was running. The retained allocation observer, process identity controls, exact executed command and temporary environment checks, source recovery, and all resource gates remain in force. The new full keeps MemoryHigh22 GiB, MemoryMax24 GiB, eight CPUs, no swap, normal `-j6`, a 96 GiB owned work budget and a 32 GiB shared disk reserve. Its admission retains the combined58 GiB memory requirement.

A source or tool pass does not establish a complete Native/ART artifact, production signing, QPR1 runtime compatibility or production readiness. Those fields remain false in `validation.json`. The earlier public capsule remains an unchanged historical checkpoint.

`source-pins.json` records exact public source identities and compact receipt pins. Private host paths, original execution logs, account data and private signing material are excluded. `FILES.json` binds every payload file.
