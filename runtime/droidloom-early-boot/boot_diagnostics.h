// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef DROIDLOOM_BOOT_DIAGNOSTICS_H
#define DROIDLOOM_BOOT_DIAGNOSTICS_H

enum droidloom_boot_diagnostic_phase {
    DROIDLOOM_DIAGNOSTIC_POLICY,
    DROIDLOOM_DIAGNOSTIC_PID1,
};

/* Original real-root PID 1 only, before the first policy load. The descriptor
 * is never passed over IPC and retires at the already-required self exec. */
int droidloom_boot_diagnostics_prepare(void);
void droidloom_boot_diagnostics_report(enum droidloom_boot_diagnostic_phase phase,
                                      const char *stage, int error);
#endif
