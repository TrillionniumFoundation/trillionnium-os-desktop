// SPDX-License-Identifier: Apache-2.0
#ifndef DROIDLOOM_ART_NATIVE_GENERATION_H_
#define DROIDLOOM_ART_NATIVE_GENERATION_H_
#ifndef DROIDLOOM_NATIVE_GENERATION_RUNTIME
#define DROIDLOOM_NATIVE_GENERATION_RUNTIME 0
#endif
namespace android::droidloom_generation {
bool Prepare(void* engine_handle);
bool BeforeFork();
bool AfterSpecialize();
bool BeforeUnload();
bool RequireReady();
int LastError();
}
#endif
