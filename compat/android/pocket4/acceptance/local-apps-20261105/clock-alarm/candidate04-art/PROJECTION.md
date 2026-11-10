# Text-only projection of the Clock ART04 evidence package

This directory selects 30 original files byte-for-byte from the frozen `public-art04` package. Its parent manifest has SHA-256 `a459e2d034d76bed16a5495cae06763ae777a85dd24aa6a260f0b428c4efccc3`. The parent package remains unchanged.

`SOURCE_MANIFEST.json` is the complete manifest for this projection. The parent `MANIFEST.json` is not copied or presented as this projection’s manifest. The projection omits the compiled `current-oat.bin` and three complete remote request JSON payloads. Every omission has its original size, whole SHA-256 and reason in the new manifest. Original source, actual result receipts and complete classpath closures remain byte-identical.

The original README and review describe the retained parent package. Commands that consume the omitted OAT or request payloads require that original package; the source and original parsed OAT key-table review remain available here. This projection does not claim those omitted bytes are present.

ART verified the four modified candidate classes under the captured context. The candidate was not installed by this evidence package, and no alarm, timer or whole-App qualification is awarded.
