# CI-only temporary debugging profile. Never attach this to system Python.
abi <abi/4.0>,
include <tunables/global>
profile @@PROFILE@@ "@@INTERPRETER@@" flags=(unconfined) {
  userns,
}
