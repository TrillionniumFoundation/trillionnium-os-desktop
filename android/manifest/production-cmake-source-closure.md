# Production source closure for the retained Binder SDK tools

The normal strict production build now selects production-full-cmake-source-lock.json: the unchanged 651-project Audio/Native union plus one complete original project, platform/prebuilts/cmake/linux-x86, at d3078fda401bc334507d7831e30fca9273630e8c.

The exact revision and project name come from the selected platform/superproject commit 28f0bbddc24d56c8ec5a8df5342ac7a292184039, whose complete Gitlinks and .gitmodules were freshly obtained through the official public Git protocol. All 651 prior entries matched that same original tree. The original CMake Blueprint supplies cmake, ctest and the CMake 4.1 cmake_root resources used by the retained Binder SDK host tests. The new lock takes the complete project; a bin-only sparse checkout is rejected.

The historical production-full CLI profile and 651-project lock remain unchanged. The new explicit production-full-cmake profile validates the original projects and the one exact addition. Existing source trees require a separately recorded normal reconcile operation. A production request refuses a stale 651 manifest and does not silently modify shared source.

The Binder tests and their original dependencies remain enabled. ALLOW_MISSING_DEPENDENCIES=false, SELINUX_IGNORE_NEVERALLOWS=false, original source projection restoration and all runtime acceptance gates remain required. This source closure change does not assert successful Soong, vendor output, Android runtime or production readiness.
