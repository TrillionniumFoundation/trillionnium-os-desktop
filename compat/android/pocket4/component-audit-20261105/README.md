# Installed system and QA component audit

Fourteen exact installed Apps were inspected without executing their code, launching an Activity, changing a permission or reading account/user content. The complete 45-launcher inventory remained identical. Full APK bytes and current file identities matched before and after each bounded observation.

| Package | APK classes | Class references | Missing references |
| --- | ---: | ---: | ---: |
| com.android.calendar | 445 | 24 | 3 |
| com.android.camera2 | 9682 | 13 | 0 |
| com.android.contacts | 4706 | 44 | 1 |
| com.android.deskclock | 2941 | 30 | 0 |
| com.android.dialer | 3828 | 82 | 2 |
| com.android.documentsui | 4591 | 19 | 0 |
| com.android.gallery3d | 2055 | 34 | 1 |
| com.android.messaging | 4056 | 61 | 0 |
| com.android.quicksearchbox | 586 | 8 | 0 |
| com.android.settings | 29840 | 498 | 0 |
| com.android.threadnetwork.demoapp | 2725 | 4 | 0 |
| local.pocket4.fixture | 5 | 1 | 0 |
| org.chromium.webview_shell | 19 | 12 | 6 |
| org.droidloom.qa.editorcontract | 6 | 1 | 0 |

The 831 references resolve to 818 definitions in the examined base/split DEX files and 13 unresolved references, representing 12 distinct classes in five Apps. Alias names are not treated as classes; their targetActivity is checked. Each App has its own class universe. Previously verified signing certificates are bound by identical whole-APK hashes; this audit did not rerun signature verification.

The unresolved references require class-loader and actual feature-contract review. In particular, instrumentation test containers may intentionally be supplied by a test APK. No missing-reference count is presented as a reproduced crash count. Calendar already has a separately reproduced missing editor failure and an uninstalled functional candidate.

The job used one CPU and a 768MiB memory limit, with a recorded 193,699,840-byte peak and zero memory.max/OOM events. Its actual swap limit was `max`, not zero. No functional, runtime-engine or whole-App release gate is granted.
