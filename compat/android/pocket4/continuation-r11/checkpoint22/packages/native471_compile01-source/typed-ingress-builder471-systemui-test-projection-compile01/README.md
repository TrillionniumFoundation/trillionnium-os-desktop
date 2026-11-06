# Builder471: fixed SystemUI test Blueprint boundary

Status: source-only; compilation and all new tests are unrun. Root is the sole dispatcher.

Normal07 reached strict Soong analysis and failed because the original SystemUI/tests/Android.bp retained SystemUITests_defaults, whose systemui-non-platform-apis-defaults provider had been excluded by the existing three-provider parent projection. The same defaults also referenced excluded SystemUI-tests. The selected two targets remain framework-minus-apex and libandroid_runtime. This patch consistently excludes exactly the five modules in the locked 3392-byte child Blueprint from that typed-ingress route, retaining its package and license reference. It does not enumerate or ignore other directories. The full upstream original is preserved as a fixture and by the unchanged projection journal.

The direct/defaults/source-group evidence is static, not a complete generated Soong variant graph. The separate framework-minus-apex-install-dependencies module points to framework-minus-apex; it is not evidence that the selected target requires the SystemUI test application. Any remaining required edge is still subject to ALLOW_MISSING_DEPENDENCIES=false. This route does not qualify SystemUI application or test builds.

Production delta from actual builder470: one Rust source replacement and one complete upstream fixture addition; 498 existing map entries unchanged, 500 entries total. The exact 225-project 72848909… lock, both original locks, three parent providers, flags/JNI/target BPs and restoration implementation remain unchanged. The published lock writer remains UNKNOWN.

The new compile-only request copies and fully verifies actual builder470's 499-entry source tree into its own fresh root, applies the exact two-file delta, and verifies all 500 entries. It retains compiler, dependency/archive, tool, config, resource and cleanup gates. It builds the updater and runs the original 18 updater controls, three new real-file projection/rejection/recovery controls, and the original nine source-resume controls. Expected 68 commands, 30 focused results, 211 updater and 20 source test registrations. New labels 200–202 avoid the inherited reserved fakeroot index20; original labels remain unchanged.

Request root: /home/alex/work/pocket4-native-typed-ingress-builder471-systemui-test-projection-compile-01-20261106

Resources: one CPU, 1 GiB RAM, nice15, 550-second work deadline and 600-second outer timeout; original swap observation and failure gates unchanged. No Android, Soong, Main service or installed engine execution, deployment, or ref updates are part of this request.

Reproduction: load make_request.js as a pure function and call generate(exact five packet source strings, exact stage.py, verified UTF-8/SHA256 helper). Its exact request and stdin assertions must match request-pins.json. inverse-edits.json and the four diffs reconstruct all edited sources from the immutable baseline references. Python/Rust execution remains for Root's reviewed single admission. Full original Normal07 failures remain in evidence tree 8dece274c70366c22ff71248b2362c4cf8790719.
