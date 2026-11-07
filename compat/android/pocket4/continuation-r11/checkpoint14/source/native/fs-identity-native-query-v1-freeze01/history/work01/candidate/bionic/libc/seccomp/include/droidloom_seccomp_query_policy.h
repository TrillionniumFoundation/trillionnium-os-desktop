/*
 * Copyright (C) 2026 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
#pragma once

// Private, explicitly selected base policy. Existing stock policy entry points
// keep their original behavior. This is not an app-zygote role authorization:
// the caller must separately establish the pre-guest lifecycle, UID/GID range,
// all-thread coverage, no-new-privileges and authenticated factory generation.
// No runtime caller is added by this revision.
bool set_droidloom_app_zygote_seccomp_filter_v1();
