# Exact metadata for the retained installed B release

These files retain the exact manifest and selected original source/resource
metadata for Desktop `a7621d8022f52add679bd6edba5d0bad6772dabc`, Hepta
`22e87e0dd6560a7b925e716a33011378ae07a9a2`, release
`a7621d8022f5-7bb3f08ce5c1`. The package manifest SHA256 is
`b1872f83b9e882ddc4f241be5b7a50039c8f40c24c6fc50cf3845c3ba4a53aa7`.

Every retained file other than this README and `manifest.json` has the exact
byte length and SHA256 recorded in that manifest. The manifest came from the
original package and Root deployment inventory. The SDK patch/notice files and
native inventories are the original Hepta commit's bytes. `bundle.json` was
reconstructed from the retained Cargo source and resource identities, then
required to match the manifest's exact 1729 bytes and SHA256
`0c3d8f8890fe262ac8b3320a5a4e7603d03c94f72b2b678487c71b77e2833011`.

This is a partial metadata fixture. It omits the real ELF programs, fonts and
other original asset bytes. It is not an installable package or evidence of an
original Root launch. Cross-version transaction tests use explicitly synthetic
ELFs and assets and replace only the fixture's release, package-manifest hash
and resource-bundle hash in test scope. All SDK patches, source-profile and
notice-profile hashes remain the retained historical identities.

The original SDK notices and their licenses are retained under
`resources/dependency-notices/makepad/`. Tests never import or execute package
content, and the production installer has no fixture or hash-override option.
